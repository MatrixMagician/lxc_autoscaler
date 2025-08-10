"""Autoscaling engine with safety mechanisms and decision logic."""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set

from ..api.exceptions import ProxmoxAPIError
from ..api.proxmox_client import ProxmoxClient
from ..config.models import AutoscalerConfig, ContainerConfig
from ..metrics.collector import MetricsCollector
from ..metrics.models import ClusterMetrics, ContainerMetrics, ResourceMetrics
from .models import (
    ScalingAction,
    ScalingDecision,
    ScalingHistory,
    ScalingOperation,
    ScalingReason,
)


logger = logging.getLogger(__name__)


class ScalingEngineError(Exception):
    """Error in scaling engine operation."""
    pass


class ScalingEngine:
    """Main autoscaling engine with safety mechanisms."""
    
    def __init__(
        self, 
        client: ProxmoxClient, 
        metrics_collector: MetricsCollector,
        config: AutoscalerConfig
    ) -> None:
        """Initialize scaling engine.
        
        Args:
            client: Proxmox API client.
            metrics_collector: Metrics collector.
            config: Autoscaler configuration.
        """
        self.client = client
        self.metrics_collector = metrics_collector
        self.config = config
        
        # Track scaling operations and history
        self.active_operations: Dict[int, ScalingOperation] = {}
        self.scaling_history: Dict[int, ScalingHistory] = {}
        
        # Safety mechanisms
        self._operation_semaphore = asyncio.Semaphore(
            self.config.safety.max_concurrent_operations
        )
        
    async def evaluate_and_scale(self) -> List[ScalingDecision]:
        """Evaluate all containers and perform scaling decisions.
        
        Returns:
            List of scaling decisions made.
        """
        try:
            logger.debug("Starting scaling evaluation cycle")
            
            # Collect latest metrics
            cluster_metrics = await self.metrics_collector.collect_all_metrics()
            
            # Check cluster safety constraints
            if not self._check_cluster_safety(cluster_metrics):
                logger.warning("Cluster safety constraints violated, skipping scaling")
                return []
            
            # Generate scaling decisions for all containers
            decisions = await self._generate_scaling_decisions(cluster_metrics)
            
            # Execute scaling operations
            executed_decisions = []
            for decision in decisions:
                if decision.requires_scaling:
                    success = await self._execute_scaling_decision(decision)
                    if success:
                        executed_decisions.append(decision)
                else:
                    executed_decisions.append(decision)
            
            # Log summary
            scaling_count = sum(1 for d in executed_decisions if d.requires_scaling)
            logger.info(f"Scaling evaluation completed: {scaling_count} scaling operations executed")
            
            return executed_decisions
            
        except Exception as e:
            logger.error(f"Scaling evaluation failed: {e}")
            raise ScalingEngineError(f"Scaling evaluation failed: {e}")
    
    def _check_cluster_safety(self, cluster_metrics: ClusterMetrics) -> bool:
        """Check cluster-wide safety constraints.
        
        Args:
            cluster_metrics: Current cluster metrics.
            
        Returns:
            True if safe to perform scaling operations.
        """
        if not self.config.safety.enable_host_protection:
            return True
        
        # Check if any node is under severe stress
        for node_metrics in cluster_metrics.node_metrics:
            if node_metrics.cpu_usage_percent > self.config.safety.max_cpu_usage_threshold:
                logger.warning(f"Node {node_metrics.node_name} CPU usage too high: "
                             f"{node_metrics.cpu_usage_percent:.1f}%")
                return False
            
            if node_metrics.memory_usage_percent > self.config.safety.max_memory_usage_threshold:
                logger.warning(f"Node {node_metrics.node_name} memory usage too high: "
                             f"{node_metrics.memory_usage_percent:.1f}%")
                return False
        
        # Check if cluster resources are available for scale-up operations
        availability = cluster_metrics.get_resource_availability()
        if availability['cpu_available_percent'] < 10:
            logger.warning(f"Cluster CPU availability too low: "
                         f"{availability['cpu_available_percent']:.1f}%")
            return False
        
        if availability['memory_available_percent'] < 10:
            logger.warning(f"Cluster memory availability too low: "
                         f"{availability['memory_available_percent']:.1f}%")
            return False
        
        return True
    
    async def _generate_scaling_decisions(self, cluster_metrics: ClusterMetrics) -> List[ScalingDecision]:
        """Generate scaling decisions for all monitored containers.
        
        Args:
            cluster_metrics: Current cluster metrics.
            
        Returns:
            List of scaling decisions.
        """
        decisions = []
        
        for container_config in self.config.containers:
            if not container_config.enabled:
                continue
            
            decision = await self._evaluate_container_scaling(
                container_config, cluster_metrics
            )
            decisions.append(decision)
        
        return decisions
    
    async def _evaluate_container_scaling(
        self, 
        container_config: ContainerConfig,
        cluster_metrics: ClusterMetrics
    ) -> ScalingDecision:
        """Evaluate scaling decision for a single container.
        
        Args:
            container_config: Container configuration.
            cluster_metrics: Current cluster metrics.
            
        Returns:
            Scaling decision.
        """
        vmid = container_config.vmid
        
        # Get container metrics
        container_metrics = self.metrics_collector.get_container_metrics(vmid)
        
        if not container_metrics:
            return ScalingDecision(
                vmid=vmid,
                node="unknown",
                action=ScalingAction.NO_ACTION,
                reason=ScalingReason.INSUFFICIENT_DATA,
                current_cpu_cores=0,
                current_memory_mb=0,
            )
        
        # Check if container is running
        if container_metrics.status != 'running':
            return ScalingDecision(
                vmid=vmid,
                node=container_metrics.node,
                action=ScalingAction.NO_ACTION,
                reason=ScalingReason.CONTAINER_NOT_RUNNING,
                current_cpu_cores=0,
                current_memory_mb=0,
            )
        
        # Check if there's an active operation for this container
        if vmid in self.active_operations:
            return ScalingDecision(
                vmid=vmid,
                node=container_metrics.node,
                action=ScalingAction.NO_ACTION,
                reason=ScalingReason.COOLDOWN_PERIOD,
                current_cpu_cores=container_metrics.current_metrics.cpu_cores if container_metrics.current_metrics else 0,
                current_memory_mb=container_metrics.current_metrics.memory_total_mb if container_metrics.current_metrics else 0,
            )
        
        # Check cooldown period
        history = self.scaling_history.get(vmid, ScalingHistory(vmid=vmid))
        if history.is_in_cooldown(container_config.cooldown_seconds):
            remaining = history.get_cooldown_remaining(container_config.cooldown_seconds)
            logger.debug(f"Container {vmid} in cooldown period ({remaining:.0f}s remaining)")
            return ScalingDecision(
                vmid=vmid,
                node=container_metrics.node,
                action=ScalingAction.NO_ACTION,
                reason=ScalingReason.COOLDOWN_PERIOD,
                current_cpu_cores=container_metrics.current_metrics.cpu_cores if container_metrics.current_metrics else 0,
                current_memory_mb=container_metrics.current_metrics.memory_total_mb if container_metrics.current_metrics else 0,
            )
        
        # Get evaluation metrics (average over configured periods)
        eval_metrics = container_metrics.get_average_metrics(container_config.evaluation_periods)
        
        if not eval_metrics:
            return ScalingDecision(
                vmid=vmid,
                node=container_metrics.node,
                action=ScalingAction.NO_ACTION,
                reason=ScalingReason.INSUFFICIENT_DATA,
                current_cpu_cores=container_metrics.current_metrics.cpu_cores if container_metrics.current_metrics else 0,
                current_memory_mb=container_metrics.current_metrics.memory_total_mb if container_metrics.current_metrics else 0,
            )
        
        # Evaluate scaling need
        return self._make_scaling_decision(
            container_config, container_metrics, eval_metrics, cluster_metrics
        )
    
    def _make_scaling_decision(
        self,
        container_config: ContainerConfig,
        container_metrics: ContainerMetrics,
        eval_metrics: ResourceMetrics,
        cluster_metrics: ClusterMetrics,
    ) -> ScalingDecision:
        """Make scaling decision based on metrics and thresholds.
        
        Args:
            container_config: Container configuration.
            container_metrics: Container metrics data.
            eval_metrics: Evaluation metrics (averaged).
            cluster_metrics: Cluster metrics.
            
        Returns:
            Scaling decision.
        """
        vmid = container_config.vmid
        thresholds = container_config.thresholds
        limits = container_config.limits
        
        current_cpu = eval_metrics.cpu_cores
        current_memory = eval_metrics.memory_total_mb
        cpu_usage = eval_metrics.cpu_usage_percent
        memory_usage = eval_metrics.memory_usage_percent
        
        # Check for scale-up conditions
        if cpu_usage >= thresholds.cpu_scale_up:
            # CPU scale-up needed
            target_cpu = min(current_cpu + limits.cpu_step, limits.max_cpu_cores)
            
            if target_cpu > current_cpu:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.SCALE_UP_CPU,
                    reason=ScalingReason.CPU_HIGH,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    target_cpu_cores=target_cpu,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
            else:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.NO_ACTION,
                    reason=ScalingReason.RESOURCE_LIMIT_REACHED,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
        
        elif memory_usage >= thresholds.memory_scale_up:
            # Memory scale-up needed
            target_memory = min(current_memory + limits.memory_step_mb, limits.max_memory_mb)
            
            if target_memory > current_memory:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.SCALE_UP_MEMORY,
                    reason=ScalingReason.MEMORY_HIGH,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    target_memory_mb=target_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
            else:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.NO_ACTION,
                    reason=ScalingReason.RESOURCE_LIMIT_REACHED,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
        
        # Check for scale-down conditions
        elif cpu_usage <= thresholds.cpu_scale_down:
            # CPU scale-down possible
            target_cpu = max(current_cpu - limits.cpu_step, limits.min_cpu_cores)
            
            if target_cpu < current_cpu:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.SCALE_DOWN_CPU,
                    reason=ScalingReason.CPU_LOW,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    target_cpu_cores=target_cpu,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
            else:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.NO_ACTION,
                    reason=ScalingReason.RESOURCE_LIMIT_REACHED,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
        
        elif memory_usage <= thresholds.memory_scale_down:
            # Memory scale-down possible
            target_memory = max(current_memory - limits.memory_step_mb, limits.min_memory_mb)
            
            if target_memory < current_memory:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.SCALE_DOWN_MEMORY,
                    reason=ScalingReason.MEMORY_LOW,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    target_memory_mb=target_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
            else:
                return ScalingDecision(
                    vmid=vmid,
                    node=container_metrics.node,
                    action=ScalingAction.NO_ACTION,
                    reason=ScalingReason.RESOURCE_LIMIT_REACHED,
                    current_cpu_cores=current_cpu,
                    current_memory_mb=current_memory,
                    current_cpu_usage=cpu_usage,
                    current_memory_usage=memory_usage,
                )
        
        # No scaling needed
        return ScalingDecision(
            vmid=vmid,
            node=container_metrics.node,
            action=ScalingAction.NO_ACTION,
            reason=ScalingReason.NO_ACTION,
            current_cpu_cores=current_cpu,
            current_memory_mb=current_memory,
            current_cpu_usage=cpu_usage,
            current_memory_usage=memory_usage,
        )
    
    async def _execute_scaling_decision(self, decision: ScalingDecision) -> bool:
        """Execute a scaling decision.
        
        Args:
            decision: Scaling decision to execute.
            
        Returns:
            True if scaling operation was successful.
        """
        if not decision.requires_scaling:
            return True
        
        # Check dry-run mode
        if self.config.global_config.dry_run:
            logger.info(f"DRY RUN: Would execute {decision}")
            return True
        
        # Create scaling operation
        operation = ScalingOperation(decision=decision, started_at=time.time())
        self.active_operations[decision.vmid] = operation
        
        try:
            async with self._operation_semaphore:
                logger.info(f"Executing scaling operation: {decision}")
                
                # Perform the scaling
                await self._perform_scaling(decision)
                
                # Mark operation as successful
                operation.complete_success()
                logger.info(f"Scaling operation completed successfully: {operation}")
                
                # Update history
                history = self.scaling_history.get(decision.vmid, ScalingHistory(vmid=decision.vmid))
                history.record_operation(operation)
                self.scaling_history[decision.vmid] = history
                
                return True
                
        except Exception as e:
            # Mark operation as failed
            error_msg = f"Scaling operation failed: {e}"
            operation.complete_failure(error_msg)
            logger.error(f"Scaling operation failed for container {decision.vmid}: {e}")
            
            # Update history
            history = self.scaling_history.get(decision.vmid, ScalingHistory(vmid=decision.vmid))
            history.record_operation(operation)
            self.scaling_history[decision.vmid] = history
            
            return False
            
        finally:
            # Remove from active operations
            if decision.vmid in self.active_operations:
                del self.active_operations[decision.vmid]
    
    async def _perform_scaling(self, decision: ScalingDecision) -> None:
        """Perform the actual scaling operation.
        
        Args:
            decision: Scaling decision to execute.
            
        Raises:
            ProxmoxAPIError: If scaling operation fails.
        """
        cpu_cores = decision.target_cpu_cores if decision.target_cpu_cores is not None else decision.current_cpu_cores
        memory_mb = decision.target_memory_mb if decision.target_memory_mb is not None else decision.current_memory_mb
        
        await self.client.resize_container(
            node=decision.node,
            vmid=decision.vmid,
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
        )
    
    def get_scaling_status(self) -> Dict[str, any]:
        """Get current scaling engine status.
        
        Returns:
            Status information.
        """
        active_operations = len(self.active_operations)
        total_containers = len(self.config.containers)
        
        # Calculate success rates
        total_operations = sum(h.operation_count for h in self.scaling_history.values())
        total_successes = sum(h.success_count for h in self.scaling_history.values())
        success_rate = (total_successes / total_operations * 100) if total_operations > 0 else 0
        
        return {
            'active_operations': active_operations,
            'monitored_containers': total_containers,
            'total_operations': total_operations,
            'total_successes': total_successes,
            'success_rate_percent': success_rate,
            'max_concurrent_operations': self.config.safety.max_concurrent_operations,
        }
    
    def get_container_history(self, vmid: int) -> Optional[ScalingHistory]:
        """Get scaling history for a specific container.
        
        Args:
            vmid: Container VMID.
            
        Returns:
            Scaling history or None if not found.
        """
        return self.scaling_history.get(vmid)
    
    async def health_check(self) -> bool:
        """Perform health check on scaling engine.
        
        Returns:
            True if scaling engine is healthy.
        """
        try:
            # Check if we can generate decisions (without executing them)
            cluster_metrics = await self.metrics_collector.collect_all_metrics()
            decisions = await self._generate_scaling_decisions(cluster_metrics)
            logger.debug(f"Health check: Generated {len(decisions)} scaling decisions")
            return True
        except Exception as e:
            logger.error(f"Scaling engine health check failed: {e}")
            return False