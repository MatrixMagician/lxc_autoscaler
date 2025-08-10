"""Main autoscaler daemon service."""

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from ..api.exceptions import ProxmoxAPIError
from ..api.proxmox_client import ProxmoxClient
from ..config.manager import ConfigManager, ConfigurationError
from ..config.models import AutoscalerConfig
from ..logging.setup import setup_logging, get_logger, log_exception, with_log_context
from ..metrics.collector import MetricsCollector, MetricsCollectionError
from ..scaling.engine import ScalingEngine, ScalingEngineError


logger = get_logger(__name__)


class DaemonError(Exception):
    """Daemon operation error."""
    pass


class AutoscalerDaemon:
    """Main autoscaler daemon service."""
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize autoscaler daemon.
        
        Args:
            config_path: Path to configuration file.
        """
        self.config_path = config_path
        self.config: Optional[AutoscalerConfig] = None
        self.config_manager: Optional[ConfigManager] = None
        
        # Service components
        self.proxmox_client: Optional[ProxmoxClient] = None
        self.metrics_collector: Optional[MetricsCollector] = None
        self.scaling_engine: Optional[ScalingEngine] = None
        
        # Runtime state
        self.is_running = False
        self.should_stop = False
        self.main_task: Optional[asyncio.Task] = None
        self.health_check_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.start_time: Optional[float] = None
        self.cycles_completed = 0
        self.cycles_failed = 0
        self.last_cycle_time: Optional[float] = None
        
    async def initialize(self) -> None:
        """Initialize daemon components.
        
        Raises:
            DaemonError: If initialization fails.
        """
        try:
            logger.info("Initializing LXC Autoscaler daemon")
            
            # Load configuration
            self.config_manager = ConfigManager(self.config_path)
            self.config = self.config_manager.load_config()
            
            # Setup logging with configuration
            setup_logging(self.config.global_config, "lxc-autoscaler")
            logger.info("Logging configured")
            
            # Initialize Proxmox client
            self.proxmox_client = ProxmoxClient(self.config.proxmox)
            await self.proxmox_client.connect()
            logger.info("Proxmox client initialized")
            
            # Initialize metrics collector
            self.metrics_collector = MetricsCollector(self.proxmox_client, self.config)
            logger.info("Metrics collector initialized")
            
            # Initialize scaling engine
            self.scaling_engine = ScalingEngine(
                self.proxmox_client, self.metrics_collector, self.config
            )
            logger.info("Scaling engine initialized")
            
            # Create PID file
            await self._create_pid_file()
            
            logger.info("Daemon initialization completed successfully")
            
        except ConfigurationError as e:
            logger.error(f"Configuration error: {e}")
            raise DaemonError(f"Configuration error: {e}")
        except ProxmoxAPIError as e:
            logger.error(f"Proxmox API error: {e}")
            raise DaemonError(f"Proxmox API error: {e}")
        except Exception as e:
            log_exception(logger, "Daemon initialization failed", e)
            raise DaemonError(f"Daemon initialization failed: {e}")
    
    async def start(self) -> None:
        """Start the daemon service.
        
        Raises:
            DaemonError: If daemon cannot be started.
        """
        if self.is_running:
            raise DaemonError("Daemon is already running")
        
        try:
            # Initialize if not done already
            if not self.config:
                await self.initialize()
            
            logger.info("Starting LXC Autoscaler daemon")
            self.is_running = True
            self.should_stop = False
            self.start_time = time.time()
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Start main loop
            self.main_task = asyncio.create_task(self._main_loop())
            
            # Start health check loop
            self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info("Daemon started successfully")
            
            # Wait for tasks to complete
            await asyncio.gather(
                self.main_task,
                self.health_check_task,
                return_exceptions=True
            )
            
        except Exception as e:
            log_exception(logger, "Failed to start daemon", e)
            raise DaemonError(f"Failed to start daemon: {e}")
        finally:
            await self.cleanup()
    
    async def stop(self) -> None:
        """Stop the daemon service gracefully."""
        if not self.is_running:
            return
        
        logger.info("Stopping LXC Autoscaler daemon")
        self.should_stop = True
        
        # Cancel running tasks
        if self.main_task and not self.main_task.done():
            self.main_task.cancel()
            try:
                await self.main_task
            except asyncio.CancelledError:
                pass
        
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        self.is_running = False
        logger.info("Daemon stopped")
    
    async def cleanup(self) -> None:
        """Cleanup daemon resources."""
        try:
            # Close Proxmox client
            if self.proxmox_client:
                await self.proxmox_client.close()
            
            # Remove PID file
            await self._remove_pid_file()
            
            logger.info("Daemon cleanup completed")
            
        except Exception as e:
            log_exception(logger, "Error during cleanup", e)
    
    async def _main_loop(self) -> None:
        """Main daemon processing loop."""
        logger.info("Starting main processing loop")
        
        while not self.should_stop:
            cycle_start = time.time()
            
            try:
                with with_log_context(logger, cycle=self.cycles_completed + 1):
                    logger.debug("Starting scaling cycle")
                    
                    # Perform scaling evaluation and operations
                    decisions = await self.scaling_engine.evaluate_and_scale()
                    
                    # Log cycle results
                    scaling_count = sum(1 for d in decisions if d.requires_scaling)
                    logger.info(f"Scaling cycle completed: {len(decisions)} containers evaluated, "
                              f"{scaling_count} scaling operations executed")
                    
                    self.cycles_completed += 1
                    self.last_cycle_time = time.time()
                
            except ScalingEngineError as e:
                logger.error(f"Scaling engine error: {e}")
                self.cycles_failed += 1
            except MetricsCollectionError as e:
                logger.error(f"Metrics collection error: {e}")
                self.cycles_failed += 1
            except ProxmoxAPIError as e:
                logger.error(f"Proxmox API error: {e}")
                self.cycles_failed += 1
            except Exception as e:
                log_exception(logger, "Unexpected error in main loop", e)
                self.cycles_failed += 1
            
            # Calculate sleep time
            cycle_duration = time.time() - cycle_start
            sleep_time = max(0, self.config.global_config.monitoring_interval - cycle_duration)
            
            logger.debug(f"Cycle completed in {cycle_duration:.2f}s, sleeping for {sleep_time:.2f}s")
            
            # Sleep until next cycle, checking for stop signal
            sleep_elapsed = 0
            while sleep_elapsed < sleep_time and not self.should_stop:
                await asyncio.sleep(min(1.0, sleep_time - sleep_elapsed))
                sleep_elapsed += 1.0
    
    async def _health_check_loop(self) -> None:
        """Health check monitoring loop."""
        logger.debug("Starting health check loop")
        
        health_check_interval = self.config.safety.resource_check_interval
        
        while not self.should_stop:
            try:
                # Perform health checks
                proxmox_healthy = await self.proxmox_client.health_check()
                metrics_healthy = await self.metrics_collector.health_check()
                scaling_healthy = await self.scaling_engine.health_check()
                
                if not all([proxmox_healthy, metrics_healthy, scaling_healthy]):
                    logger.warning("Health check failed - some components unhealthy")
                    logger.warning(f"Proxmox: {'OK' if proxmox_healthy else 'FAIL'}")
                    logger.warning(f"Metrics: {'OK' if metrics_healthy else 'FAIL'}")
                    logger.warning(f"Scaling: {'OK' if scaling_healthy else 'FAIL'}")
                else:
                    logger.debug("Health check passed - all components healthy")
                
            except Exception as e:
                log_exception(logger, "Health check error", e)
            
            # Sleep until next health check
            await asyncio.sleep(health_check_interval)
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            asyncio.create_task(self.stop())
        
        # Handle termination signals
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Handle configuration reload signal
        def reload_handler(signum, frame):
            logger.info("Received SIGHUP, reloading configuration")
            asyncio.create_task(self._reload_configuration())
        
        signal.signal(signal.SIGHUP, reload_handler)
    
    async def _create_pid_file(self) -> None:
        """Create PID file."""
        try:
            pid_path = Path(self.config.global_config.pid_file)
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(pid_path, 'w') as f:
                f.write(str(os.getpid()))
            
            logger.debug(f"PID file created: {pid_path}")
            
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to create PID file: {e}")
    
    async def _remove_pid_file(self) -> None:
        """Remove PID file."""
        try:
            pid_path = Path(self.config.global_config.pid_file)
            if pid_path.exists():
                pid_path.unlink()
                logger.debug(f"PID file removed: {pid_path}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to remove PID file: {e}")
    
    async def _reload_configuration(self) -> None:
        """Reload configuration from file."""
        try:
            logger.info("Reloading configuration")
            
            # Reload config
            old_config = self.config
            self.config = self.config_manager.reload_config()
            
            # Update logging if changed
            if (self.config.global_config.log_level != old_config.global_config.log_level or
                self.config.global_config.log_file != old_config.global_config.log_file):
                setup_logging(self.config.global_config, "lxc-autoscaler")
                logger.info("Logging configuration updated")
            
            logger.info("Configuration reloaded successfully")
            
        except ConfigurationError as e:
            logger.error(f"Failed to reload configuration: {e}")
        except Exception as e:
            log_exception(logger, "Configuration reload error", e)
    
    def get_status(self) -> dict:
        """Get daemon status information.
        
        Returns:
            Status dictionary.
        """
        uptime = time.time() - self.start_time if self.start_time else 0
        
        status = {
            'running': self.is_running,
            'uptime_seconds': uptime,
            'cycles_completed': self.cycles_completed,
            'cycles_failed': self.cycles_failed,
            'last_cycle_time': self.last_cycle_time,
            'config_file': str(self.config_path) if self.config_path else None,
        }
        
        # Add component status if available
        if self.scaling_engine:
            status['scaling_engine'] = self.scaling_engine.get_scaling_status()
        
        if self.metrics_collector:
            data_age = self.metrics_collector.get_collection_age()
            status['metrics_data_age_seconds'] = data_age
        
        return status


async def main() -> None:
    """Main entry point for the daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(description='LXC Autoscaler Daemon')
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file',
        default=None
    )
    parser.add_argument(
        '--validate-config',
        action='store_true',
        help='Validate configuration and exit'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in dry-run mode (no actual scaling)'
    )
    
    args = parser.parse_args()
    
    # Validate configuration if requested
    if args.validate_config:
        try:
            config_manager = ConfigManager(args.config)
            config = config_manager.load_config()
            
            # Override dry-run if specified
            if args.dry_run:
                config.global_config.dry_run = True
            
            print("Configuration validation successful")
            print(f"Monitoring {len(config.containers)} containers")
            print(f"Proxmox host: {config.proxmox.host}:{config.proxmox.port}")
            sys.exit(0)
        except ConfigurationError as e:
            print(f"Configuration validation failed: {e}")
            sys.exit(1)
    
    # Start daemon
    daemon = AutoscalerDaemon(args.config)
    
    try:
        # Override dry-run if specified
        if args.dry_run:
            await daemon.initialize()
            daemon.config.global_config.dry_run = True
            logger.info("Dry-run mode enabled")
        
        await daemon.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except DaemonError as e:
        logger.error(f"Daemon error: {e}")
        sys.exit(1)
    except Exception as e:
        log_exception(logger, "Unexpected error", e)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())