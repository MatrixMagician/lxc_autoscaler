"""Data models for metrics collection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ResourceMetrics:
    """Resource usage metrics for a container."""
    
    timestamp: float
    cpu_usage_percent: float
    memory_usage_percent: float
    memory_used_mb: int
    memory_total_mb: int
    cpu_cores: int
    
    @classmethod
    def from_rrd_data(cls, rrd_point: Dict, config: Dict) -> ResourceMetrics:
        """Create metrics from RRD data point.
        
        Args:
            rrd_point: RRD data point from Proxmox API.
            config: Container configuration.
            
        Returns:
            ResourceMetrics instance.
        """
        # Extract values from RRD data
        timestamp = rrd_point.get('time', time.time())
        
        # CPU usage as percentage
        cpu_usage = float(rrd_point.get('cpu', 0)) * 100
        
        # Memory calculations
        memory_used = int(rrd_point.get('mem', 0))  # bytes
        memory_max = int(rrd_point.get('maxmem', 1))  # bytes
        
        memory_used_mb = memory_used // (1024 * 1024)
        memory_total_mb = memory_max // (1024 * 1024)
        
        memory_usage_percent = (memory_used / memory_max * 100) if memory_max > 0 else 0
        
        # Get CPU cores from config
        cpu_cores = config.get('cores', 1)
        
        return cls(
            timestamp=timestamp,
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            cpu_cores=cpu_cores,
        )
    
    def __str__(self) -> str:
        """String representation of metrics."""
        return (
            f"CPU: {self.cpu_usage_percent:.1f}%, "
            f"Memory: {self.memory_usage_percent:.1f}% "
            f"({self.memory_used_mb}/{self.memory_total_mb}MB), "
            f"Cores: {self.cpu_cores}"
        )


@dataclass
class ContainerMetrics:
    """Metrics for a specific container."""
    
    vmid: int
    node: str
    name: str
    status: str
    uptime: int
    current_metrics: Optional[ResourceMetrics] = None
    historical_metrics: List[ResourceMetrics] = None
    
    def __post_init__(self) -> None:
        """Initialize historical metrics if not provided."""
        if self.historical_metrics is None:
            self.historical_metrics = []
    
    def add_metrics(self, metrics: ResourceMetrics) -> None:
        """Add new metrics data point.
        
        Args:
            metrics: Resource metrics to add.
        """
        self.current_metrics = metrics
        self.historical_metrics.append(metrics)
        
        # Keep only last 100 data points to prevent memory growth
        if len(self.historical_metrics) > 100:
            self.historical_metrics = self.historical_metrics[-100:]
    
    def get_average_metrics(self, periods: int = 3) -> Optional[ResourceMetrics]:
        """Get average metrics over the last N periods.
        
        Args:
            periods: Number of periods to average over.
            
        Returns:
            Average metrics or None if insufficient data.
        """
        if len(self.historical_metrics) < periods:
            return None
        
        recent_metrics = self.historical_metrics[-periods:]
        
        avg_cpu = sum(m.cpu_usage_percent for m in recent_metrics) / len(recent_metrics)
        avg_memory = sum(m.memory_usage_percent for m in recent_metrics) / len(recent_metrics)
        
        # Use the most recent values for other fields
        latest = recent_metrics[-1]
        
        return ResourceMetrics(
            timestamp=latest.timestamp,
            cpu_usage_percent=avg_cpu,
            memory_usage_percent=avg_memory,
            memory_used_mb=latest.memory_used_mb,
            memory_total_mb=latest.memory_total_mb,
            cpu_cores=latest.cpu_cores,
        )
    
    def get_peak_metrics(self, periods: int = 3) -> Optional[ResourceMetrics]:
        """Get peak metrics over the last N periods.
        
        Args:
            periods: Number of periods to check.
            
        Returns:
            Peak metrics or None if insufficient data.
        """
        if len(self.historical_metrics) < periods:
            return None
        
        recent_metrics = self.historical_metrics[-periods:]
        
        peak_cpu = max(m.cpu_usage_percent for m in recent_metrics)
        peak_memory = max(m.memory_usage_percent for m in recent_metrics)
        
        # Use the most recent values for other fields
        latest = recent_metrics[-1]
        
        return ResourceMetrics(
            timestamp=latest.timestamp,
            cpu_usage_percent=peak_cpu,
            memory_usage_percent=peak_memory,
            memory_used_mb=latest.memory_used_mb,
            memory_total_mb=latest.memory_total_mb,
            cpu_cores=latest.cpu_cores,
        )


@dataclass
class NodeMetrics:
    """Metrics for a Proxmox node."""
    
    node_name: str
    cpu_usage_percent: float
    memory_usage_percent: float
    memory_used_gb: float
    memory_total_gb: float
    uptime: int
    load_average: List[float]
    
    @classmethod
    def from_node_status(cls, node_name: str, status_data: Dict) -> NodeMetrics:
        """Create node metrics from status data.
        
        Args:
            node_name: Name of the node.
            status_data: Node status data from Proxmox API.
            
        Returns:
            NodeMetrics instance.
        """
        # CPU usage
        cpu_usage = float(status_data.get('cpu', 0)) * 100
        
        # Memory calculations
        memory_used = int(status_data.get('memory', {}).get('used', 0))
        memory_total = int(status_data.get('memory', {}).get('total', 1))
        
        memory_used_gb = memory_used / (1024 ** 3)
        memory_total_gb = memory_total / (1024 ** 3)
        memory_usage_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0
        
        # System info
        uptime = int(status_data.get('uptime', 0))
        load_avg = status_data.get('loadavg', [0.0, 0.0, 0.0])
        
        return cls(
            node_name=node_name,
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            uptime=uptime,
            load_average=load_avg,
        )


@dataclass
class ClusterMetrics:
    """Metrics for the entire Proxmox cluster."""
    
    total_containers: int
    running_containers: int
    total_cpu_cores: int
    total_memory_gb: float
    avg_cpu_usage_percent: float
    avg_memory_usage_percent: float
    node_metrics: List[NodeMetrics]
    container_metrics: List[ContainerMetrics]
    
    def get_resource_availability(self) -> Dict[str, float]:
        """Calculate available cluster resources.
        
        Returns:
            Dictionary with available CPU and memory percentages.
        """
        if not self.node_metrics:
            return {'cpu_available_percent': 0.0, 'memory_available_percent': 0.0}
        
        avg_cpu_available = 100 - self.avg_cpu_usage_percent
        avg_memory_available = 100 - self.avg_memory_usage_percent
        
        return {
            'cpu_available_percent': max(0, avg_cpu_available),
            'memory_available_percent': max(0, avg_memory_available),
        }