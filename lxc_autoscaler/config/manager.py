"""Configuration manager for loading and validating YAML configurations."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import (
    AutoscalerConfig,
    ContainerConfig,
    GlobalConfig,
    ProxmoxConfig,
    ResourceLimits,
    SafetyConfig,
    ScalingThresholds,
)


logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Configuration validation or loading error."""
    pass


class ConfigManager:
    """Manages configuration loading, validation, and updates."""
    
    DEFAULT_CONFIG_PATHS = [
        "/etc/lxc-autoscaler/config.yaml",
        "/usr/local/etc/lxc-autoscaler/config.yaml",
        "./config.yaml",
    ]
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file. If None, searches default paths.
        """
        self.config_path = self._find_config_file(config_path)
        self._config: Optional[AutoscalerConfig] = None
        
    def _find_config_file(self, config_path: Optional[str] = None) -> Path:
        """Find configuration file path.
        
        Args:
            config_path: Explicit path to check first.
            
        Returns:
            Path to configuration file.
            
        Raises:
            ConfigurationError: If no configuration file is found.
        """
        paths_to_check = []
        
        if config_path:
            paths_to_check.append(config_path)
        
        paths_to_check.extend(self.DEFAULT_CONFIG_PATHS)
        
        for path_str in paths_to_check:
            path = Path(path_str)
            if path.exists() and path.is_file():
                logger.info(f"Found configuration file: {path}")
                return path
        
        raise ConfigurationError(
            f"No configuration file found. Searched paths: {paths_to_check}"
        )
    
    def load_config(self) -> AutoscalerConfig:
        """Load and validate configuration from file.
        
        Returns:
            Validated configuration object.
            
        Raises:
            ConfigurationError: If configuration is invalid or cannot be loaded.
        """
        try:
            logger.info(f"Loading configuration from {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if not isinstance(config_data, dict):
                raise ConfigurationError("Configuration file must contain a YAML object")
            
            # Substitute environment variables
            config_data = self._substitute_environment_variables(config_data)
            
            # Parse and validate configuration
            self._config = self._parse_config(config_data)
            
            logger.info("Configuration loaded successfully")
            return self._config
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML syntax: {e}")
        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {self.config_path}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def _substitute_environment_variables(self, data: Any) -> Any:
        """Recursively substitute environment variables in configuration data.
        
        Args:
            data: Configuration data structure.
            
        Returns:
            Configuration data with environment variables substituted.
        """
        if isinstance(data, dict):
            return {key: self._substitute_environment_variables(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._substitute_environment_variables(item) for item in data]
        elif isinstance(data, str) and data.startswith('${') and data.endswith('}'):
            env_var = data[2:-1]
            default_value = None
            
            # Handle ${VAR:default} syntax
            if ':' in env_var:
                env_var, default_value = env_var.split(':', 1)
            
            return os.getenv(env_var, default_value)
        else:
            return data
    
    def _parse_config(self, config_data: Dict[str, Any]) -> AutoscalerConfig:
        """Parse configuration dictionary into typed objects.
        
        Args:
            config_data: Raw configuration dictionary.
            
        Returns:
            Validated configuration object.
            
        Raises:
            ConfigurationError: If configuration is invalid.
        """
        try:
            # Parse Proxmox configuration
            proxmox_data = config_data.get('proxmox', {})
            if not proxmox_data:
                raise ConfigurationError("Proxmox configuration is required")
            
            proxmox_config = ProxmoxConfig(**proxmox_data)
            
            # Parse global configuration
            global_data = config_data.get('global', {})
            global_config = GlobalConfig(**global_data)
            
            # Parse safety configuration
            safety_data = config_data.get('safety', {})
            safety_config = SafetyConfig(**safety_data)
            
            # Parse default thresholds
            thresholds_data = config_data.get('default_thresholds', {})
            default_thresholds = ScalingThresholds(**thresholds_data)
            
            # Parse default limits
            limits_data = config_data.get('default_limits', {})
            default_limits = ResourceLimits(**limits_data)
            
            # Parse container configurations
            containers = []
            containers_data = config_data.get('containers', [])
            
            for container_data in containers_data:
                container_config = self._parse_container_config(
                    container_data, 
                    default_thresholds, 
                    default_limits
                )
                containers.append(container_config)
            
            return AutoscalerConfig(
                proxmox=proxmox_config,
                global_config=global_config,
                safety=safety_config,
                default_thresholds=default_thresholds,
                default_limits=default_limits,
                containers=containers,
            )
            
        except TypeError as e:
            raise ConfigurationError(f"Invalid configuration parameter: {e}")
        except ValueError as e:
            raise ConfigurationError(f"Invalid configuration value: {e}")
    
    def _parse_container_config(
        self, 
        container_data: Dict[str, Any],
        default_thresholds: ScalingThresholds,
        default_limits: ResourceLimits,
    ) -> ContainerConfig:
        """Parse container configuration with defaults.
        
        Args:
            container_data: Container configuration dictionary.
            default_thresholds: Default scaling thresholds.
            default_limits: Default resource limits.
            
        Returns:
            Container configuration object.
        """
        if 'vmid' not in container_data:
            raise ConfigurationError("Container configuration must include 'vmid'")
        
        # Parse custom thresholds if provided
        thresholds = None
        if 'thresholds' in container_data:
            thresholds_data = container_data['thresholds']
            # Merge with defaults
            merged_thresholds = {
                'cpu_scale_up': default_thresholds.cpu_scale_up,
                'cpu_scale_down': default_thresholds.cpu_scale_down,
                'memory_scale_up': default_thresholds.memory_scale_up,
                'memory_scale_down': default_thresholds.memory_scale_down,
                **thresholds_data
            }
            thresholds = ScalingThresholds(**merged_thresholds)
        
        # Parse custom limits if provided
        limits = None
        if 'limits' in container_data:
            limits_data = container_data['limits']
            # Merge with defaults
            merged_limits = {
                'min_cpu_cores': default_limits.min_cpu_cores,
                'max_cpu_cores': default_limits.max_cpu_cores,
                'min_memory_mb': default_limits.min_memory_mb,
                'max_memory_mb': default_limits.max_memory_mb,
                'cpu_step': default_limits.cpu_step,
                'memory_step_mb': default_limits.memory_step_mb,
                **limits_data
            }
            limits = ResourceLimits(**merged_limits)
        
        # Create container configuration
        container_config = ContainerConfig(
            vmid=container_data['vmid'],
            enabled=container_data.get('enabled', True),
            thresholds=thresholds,
            limits=limits,
            cooldown_seconds=container_data.get('cooldown_seconds', 300),
            evaluation_periods=container_data.get('evaluation_periods', 3),
        )
        
        return container_config
    
    def reload_config(self) -> AutoscalerConfig:
        """Reload configuration from file.
        
        Returns:
            Reloaded configuration object.
        """
        logger.info("Reloading configuration")
        return self.load_config()
    
    def get_config(self) -> Optional[AutoscalerConfig]:
        """Get current configuration.
        
        Returns:
            Current configuration or None if not loaded.
        """
        return self._config
    
    def validate_config_file(self, config_path: str) -> bool:
        """Validate configuration file without loading it.
        
        Args:
            config_path: Path to configuration file.
            
        Returns:
            True if configuration is valid.
            
        Raises:
            ConfigurationError: If configuration is invalid.
        """
        try:
            original_path = self.config_path
            self.config_path = Path(config_path)
            self.load_config()
            self.config_path = original_path
            return True
        except ConfigurationError:
            self.config_path = original_path
            raise