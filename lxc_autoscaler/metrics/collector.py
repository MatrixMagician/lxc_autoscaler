"""Metrics collection service for LXC containers and Proxmox nodes."""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from ..api.exceptions import ProxmoxAPIError, ProxmoxResourceNotFoundError
from ..api.proxmox_client import ProxmoxClient
from ..config.models import AutoscalerConfig, ContainerConfig
from .models import ClusterMetrics, ContainerMetrics, NodeMetrics, ResourceMetrics


logger = logging.getLogger(__name__)


class MetricsCollectionError(Exception):
    """Error during metrics collection."""
    pass


class MetricsCollector:
    """Collects and manages metrics from Proxmox cluster."""
    
    def __init__(self, client: ProxmoxClient, config: AutoscalerConfig) -> None:
        """Initialize metrics collector.
        
        Args:
            client: Proxmox API client.
            config: Autoscaler configuration.
        """
        self.client = client
        self.config = config
        self.container_metrics: Dict[int, ContainerMetrics] = {}
        self.node_metrics: Dict[str, NodeMetrics] = {}
        self._last_collection_time: Optional[float] = None
        
    async def collect_all_metrics(self) -> ClusterMetrics:
        """Collect metrics for all monitored containers and nodes.
        
        Returns:
            Complete cluster metrics.
            
        Raises:
            MetricsCollectionError: If metrics collection fails.
        """
        try:
            logger.debug("Starting metrics collection cycle")
            collection_start = time.time()
            
            # Collect node metrics
            await self._collect_node_metrics()
            
            # Collect container metrics
            await self._collect_container_metrics()
            
            # Build cluster metrics
            cluster_metrics = self._build_cluster_metrics()
            
            collection_time = time.time() - collection_start
            logger.debug(f"Metrics collection completed in {collection_time:.2f}s")
            
            self._last_collection_time = time.time()
            return cluster_metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            raise MetricsCollectionError(f"Metrics collection failed: {e}")
    
    async def _collect_node_metrics(self) -> None:
        """Collect metrics for all Proxmox nodes."""
        try:
            nodes = await self.client.list_nodes()
            
            # Collect metrics for each node concurrently
            tasks = [
                self._collect_single_node_metrics(node_info['node'])
                for node_info in nodes
                if node_info.get('status') == 'online'
            ]
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except ProxmoxAPIError as e:
            logger.error(f"Failed to collect node metrics: {e}")
            raise MetricsCollectionError(f"Node metrics collection failed: {e}")
    
    async def _collect_single_node_metrics(self, node_name: str) -> None:
        """Collect metrics for a single node.
        
        Args:
            node_name: Name of the node.
        """
        try:
            logger.debug(f"Collecting metrics for node {node_name}")
            
            # Get node status
            status_data = await self.client.get_node_status(node_name)
            
            # Create node metrics
            node_metrics = NodeMetrics.from_node_status(node_name, status_data)
            self.node_metrics[node_name] = node_metrics
            
            logger.debug(f"Node {node_name}: CPU {node_metrics.cpu_usage_percent:.1f}%, "
                        f"Memory {node_metrics.memory_usage_percent:.1f}%")
            
        except ProxmoxAPIError as e:
            logger.warning(f"Failed to collect metrics for node {node_name}: {e}")
    
    async def _collect_container_metrics(self) -> None:
        """Collect metrics for all monitored containers."""
        # Get containers to monitor
        container_configs = [
            container for container in self.config.containers
            if container.enabled
        ]
        
        if not container_configs:
            logger.warning("No containers configured for monitoring")
            return
        
        # Collect metrics for each container concurrently
        tasks = [
            self._collect_single_container_metrics(container_config)
            for container_config in container_configs
        ]
        
        # Execute with limited concurrency to avoid overwhelming Proxmox
        semaphore = asyncio.Semaphore(5)
        
        async def collect_with_semaphore(container_config: ContainerConfig):
            async with semaphore:
                return await self._collect_single_container_metrics(container_config)
        
        semaphore_tasks = [
            collect_with_semaphore(config) for config in container_configs
        ]
        
        await asyncio.gather(*semaphore_tasks, return_exceptions=True)
    
    async def _collect_single_container_metrics(self, container_config: ContainerConfig) -> None:
        """Collect metrics for a single container.
        
        Args:
            container_config: Container configuration.
        """
        vmid = container_config.vmid
        
        try:
            logger.debug(f"Collecting metrics for container {vmid}")
            
            # Find which node the container is on
            node = await self.client.find_container_node(vmid)
            if not node:
                logger.warning(f"Container {vmid} not found on any node")
                return
            
            # Get container status and config
            status_task = self.client.get_container_status(node, vmid)
            config_task = self.client.get_container_config(node, vmid)
            rrd_task = self.client.get_container_rrd_data(
                node, vmid, timeframe="hour", cf="AVERAGE"
            )
            
            status, config, rrd_data = await asyncio.gather(
                status_task, config_task, rrd_task
            )
            
            # Check if container is running
            if status.get('status') != 'running':
                logger.debug(f"Container {vmid} is not running (status: {status.get('status')})")
                # Keep container in metrics but don't update resource data
                if vmid in self.container_metrics:
                    self.container_metrics[vmid].status = status.get('status', 'unknown')
                return
            
            # Get or create container metrics object
            if vmid not in self.container_metrics:
                self.container_metrics[vmid] = ContainerMetrics(
                    vmid=vmid,
                    node=node,
                    name=config.get('hostname', f'ct-{vmid}'),
                    status=status.get('status', 'unknown'),
                    uptime=int(status.get('uptime', 0)),
                )
            
            container_metrics = self.container_metrics[vmid]
            container_metrics.status = status.get('status', 'unknown')
            container_metrics.uptime = int(status.get('uptime', 0))
            container_metrics.node = node
            
            # Process RRD data to get latest metrics
            if rrd_data:
                # Get the most recent data point
                latest_rrd = rrd_data[-1] if rrd_data else {}
                
                # Create resource metrics from RRD data
                resource_metrics = ResourceMetrics.from_rrd_data(latest_rrd, config)
                
                # Add to container metrics
                container_metrics.add_metrics(resource_metrics)
                
                logger.debug(f"Container {vmid} metrics: {resource_metrics}")
            else:
                logger.warning(f"No RRD data available for container {vmid}")
                
        except ProxmoxResourceNotFoundError:
            logger.warning(f"Container {vmid} not found")
            # Remove from metrics if it was being tracked
            if vmid in self.container_metrics:
                del self.container_metrics[vmid]
        except ProxmoxAPIError as e:
            logger.error(f"Failed to collect metrics for container {vmid}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error collecting metrics for container {vmid}: {e}")
    
    def _build_cluster_metrics(self) -> ClusterMetrics:
        """Build comprehensive cluster metrics from collected data.
        
        Returns:
            Complete cluster metrics.
        """
        # Container statistics
        container_list = list(self.container_metrics.values())
        total_containers = len(container_list)
        running_containers = sum(
            1 for c in container_list 
            if c.status == 'running'
        )
        
        # Calculate cluster totals and averages
        node_list = list(self.node_metrics.values())
        
        if node_list:
            total_cpu_cores = sum(
                # Estimate cores from load average length or use a default
                len(n.load_average) if n.load_average else 1
                for n in node_list
            )
            
            total_memory_gb = sum(n.memory_total_gb for n in node_list)
            
            avg_cpu_usage = sum(n.cpu_usage_percent for n in node_list) / len(node_list)
            avg_memory_usage = sum(n.memory_usage_percent for n in node_list) / len(node_list)
        else:
            total_cpu_cores = 0
            total_memory_gb = 0.0
            avg_cpu_usage = 0.0
            avg_memory_usage = 0.0
        
        return ClusterMetrics(
            total_containers=total_containers,
            running_containers=running_containers,
            total_cpu_cores=total_cpu_cores,
            total_memory_gb=total_memory_gb,
            avg_cpu_usage_percent=avg_cpu_usage,
            avg_memory_usage_percent=avg_memory_usage,
            node_metrics=node_list,
            container_metrics=container_list,
        )
    
    def get_container_metrics(self, vmid: int) -> Optional[ContainerMetrics]:
        """Get metrics for a specific container.
        
        Args:
            vmid: Container VMID.
            
        Returns:
            Container metrics or None if not found.
        """
        return self.container_metrics.get(vmid)
    
    def get_node_metrics(self, node_name: str) -> Optional[NodeMetrics]:
        """Get metrics for a specific node.
        
        Args:
            node_name: Node name.
            
        Returns:
            Node metrics or None if not found.
        """
        return self.node_metrics.get(node_name)
    
    def is_recent_data(self, max_age_seconds: int = 300) -> bool:
        """Check if collected metrics are recent.
        
        Args:
            max_age_seconds: Maximum age of data in seconds.
            
        Returns:
            True if data is recent.
        """
        if self._last_collection_time is None:
            return False
        
        age = time.time() - self._last_collection_time
        return age <= max_age_seconds
    
    def get_collection_age(self) -> Optional[float]:
        """Get age of last metrics collection in seconds.
        
        Returns:
            Age in seconds or None if never collected.
        """
        if self._last_collection_time is None:
            return None
        
        return time.time() - self._last_collection_time
    
    async def health_check(self) -> bool:
        """Perform health check on metrics collection.
        
        Returns:
            True if metrics collection is healthy.
        """
        try:
            # Try to collect a subset of metrics
            await self._collect_node_metrics()
            return True
        except Exception as e:
            logger.error(f"Metrics collector health check failed: {e}")
            return False