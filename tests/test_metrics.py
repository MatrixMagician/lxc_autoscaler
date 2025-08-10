"""Tests for metrics collection."""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from lxc_autoscaler.metrics.models import (
    ResourceMetrics,
    ContainerMetrics,
    NodeMetrics,
    ClusterMetrics,
)


class TestResourceMetrics:
    """Test ResourceMetrics model."""
    
    def test_create_from_rrd_data(self):
        """Test creating ResourceMetrics from RRD data."""
        rrd_data = {
            'time': 1640995200.0,  # Example timestamp
            'cpu': 0.45,  # 45% CPU usage
            'mem': 1073741824,  # 1GB in bytes
            'maxmem': 2147483648,  # 2GB in bytes
        }
        
        config = {
            'cores': 2
        }
        
        metrics = ResourceMetrics.from_rrd_data(rrd_data, config)
        
        assert metrics.timestamp == 1640995200.0
        assert metrics.cpu_usage_percent == 45.0
        assert metrics.memory_usage_percent == 50.0  # 1GB / 2GB * 100
        assert metrics.memory_used_mb == 1024  # 1GB in MB
        assert metrics.memory_total_mb == 2048  # 2GB in MB
        assert metrics.cpu_cores == 2
    
    def test_string_representation(self):
        """Test ResourceMetrics string representation."""
        metrics = ResourceMetrics(
            timestamp=time.time(),
            cpu_usage_percent=45.5,
            memory_usage_percent=60.0,
            memory_used_mb=1024,
            memory_total_mb=2048,
            cpu_cores=2
        )
        
        str_repr = str(metrics)
        assert "CPU: 45.5%" in str_repr
        assert "Memory: 60.0%" in str_repr
        assert "1024/2048MB" in str_repr
        assert "Cores: 2" in str_repr


class TestContainerMetrics:
    """Test ContainerMetrics model."""
    
    def test_add_metrics(self):
        """Test adding metrics to container."""
        container = ContainerMetrics(
            vmid=101,
            node="proxmox-01",
            name="test-container",
            status="running",
            uptime=3600
        )
        
        metrics = ResourceMetrics(
            timestamp=time.time(),
            cpu_usage_percent=45.0,
            memory_usage_percent=60.0,
            memory_used_mb=1024,
            memory_total_mb=2048,
            cpu_cores=2
        )
        
        container.add_metrics(metrics)
        
        assert container.current_metrics == metrics
        assert len(container.historical_metrics) == 1
        assert container.historical_metrics[0] == metrics
    
    def test_get_average_metrics(self):
        """Test calculating average metrics."""
        container = ContainerMetrics(
            vmid=101,
            node="proxmox-01",
            name="test-container",
            status="running",
            uptime=3600
        )
        
        # Add multiple metrics
        for i, cpu_usage in enumerate([40.0, 50.0, 60.0]):
            metrics = ResourceMetrics(
                timestamp=time.time() + i,
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=50.0 + i * 5,  # 50%, 55%, 60%
                memory_used_mb=1024,
                memory_total_mb=2048,
                cpu_cores=2
            )
            container.add_metrics(metrics)
        
        avg_metrics = container.get_average_metrics(3)
        assert avg_metrics is not None
        assert avg_metrics.cpu_usage_percent == 50.0  # (40 + 50 + 60) / 3
        assert avg_metrics.memory_usage_percent == 55.0  # (50 + 55 + 60) / 3
    
    def test_get_peak_metrics(self):
        """Test calculating peak metrics."""
        container = ContainerMetrics(
            vmid=101,
            node="proxmox-01",
            name="test-container",
            status="running",
            uptime=3600
        )
        
        # Add multiple metrics
        for i, cpu_usage in enumerate([40.0, 80.0, 60.0]):
            metrics = ResourceMetrics(
                timestamp=time.time() + i,
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=50.0 + i * 10,  # 50%, 60%, 70%
                memory_used_mb=1024,
                memory_total_mb=2048,
                cpu_cores=2
            )
            container.add_metrics(metrics)
        
        peak_metrics = container.get_peak_metrics(3)
        assert peak_metrics is not None
        assert peak_metrics.cpu_usage_percent == 80.0  # Peak CPU
        assert peak_metrics.memory_usage_percent == 70.0  # Peak memory
    
    def test_insufficient_data(self):
        """Test behavior with insufficient data."""
        container = ContainerMetrics(
            vmid=101,
            node="proxmox-01",
            name="test-container",
            status="running",
            uptime=3600
        )
        
        # No metrics added
        assert container.get_average_metrics(3) is None
        assert container.get_peak_metrics(3) is None
        
        # Add one metric, request 3
        metrics = ResourceMetrics(
            timestamp=time.time(),
            cpu_usage_percent=45.0,
            memory_usage_percent=60.0,
            memory_used_mb=1024,
            memory_total_mb=2048,
            cpu_cores=2
        )
        container.add_metrics(metrics)
        
        assert container.get_average_metrics(3) is None
        assert container.get_peak_metrics(3) is None


class TestNodeMetrics:
    """Test NodeMetrics model."""
    
    def test_create_from_status_data(self):
        """Test creating NodeMetrics from Proxmox status data."""
        status_data = {
            'cpu': 0.25,  # 25% CPU usage
            'memory': {
                'used': 4294967296,  # 4GB used
                'total': 17179869184,  # 16GB total
            },
            'uptime': 86400,  # 1 day
            'loadavg': [0.5, 0.6, 0.7]
        }
        
        metrics = NodeMetrics.from_node_status("proxmox-01", status_data)
        
        assert metrics.node_name == "proxmox-01"
        assert metrics.cpu_usage_percent == 25.0
        assert metrics.memory_usage_percent == 25.0  # 4GB / 16GB * 100
        assert metrics.memory_used_gb == 4.0
        assert metrics.memory_total_gb == 16.0
        assert metrics.uptime == 86400
        assert metrics.load_average == [0.5, 0.6, 0.7]


class TestClusterMetrics:
    """Test ClusterMetrics model."""
    
    def test_get_resource_availability(self):
        """Test calculating resource availability."""
        # Create mock node metrics
        node1 = NodeMetrics(
            node_name="node1",
            cpu_usage_percent=50.0,
            memory_usage_percent=60.0,
            memory_used_gb=6.0,
            memory_total_gb=10.0,
            uptime=86400,
            load_average=[1.0, 1.0, 1.0]
        )
        
        node2 = NodeMetrics(
            node_name="node2",
            cpu_usage_percent=30.0,
            memory_usage_percent=40.0,
            memory_used_gb=4.0,
            memory_total_gb=10.0,
            uptime=86400,
            load_average=[0.5, 0.5, 0.5]
        )
        
        cluster = ClusterMetrics(
            total_containers=5,
            running_containers=4,
            total_cpu_cores=16,
            total_memory_gb=20.0,
            avg_cpu_usage_percent=40.0,  # Average of 50% and 30%
            avg_memory_usage_percent=50.0,  # Average of 60% and 40%
            node_metrics=[node1, node2],
            container_metrics=[]
        )
        
        availability = cluster.get_resource_availability()
        
        assert availability['cpu_available_percent'] == 60.0  # 100 - 40
        assert availability['memory_available_percent'] == 50.0  # 100 - 50
    
    def test_empty_cluster_metrics(self):
        """Test cluster metrics with no nodes."""
        cluster = ClusterMetrics(
            total_containers=0,
            running_containers=0,
            total_cpu_cores=0,
            total_memory_gb=0.0,
            avg_cpu_usage_percent=0.0,
            avg_memory_usage_percent=0.0,
            node_metrics=[],
            container_metrics=[]
        )
        
        availability = cluster.get_resource_availability()
        
        assert availability['cpu_available_percent'] == 0.0
        assert availability['memory_available_percent'] == 0.0


if __name__ == '__main__':
    pytest.main([__file__])