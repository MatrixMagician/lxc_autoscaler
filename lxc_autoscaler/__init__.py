"""
LXC Autoscaler for Proxmox VE

A production-ready Python service for automatically scaling LXC containers
based on workload metrics in Proxmox Virtual Environment.
"""

__version__ = "1.0.0"
__author__ = "LXC Autoscaler Team"
__email__ = "support@example.com"

from .core.daemon import AutoscalerDaemon
from .config.manager import ConfigManager
from .api.proxmox_client import ProxmoxClient
from .metrics.collector import MetricsCollector
from .scaling.engine import ScalingEngine

__all__ = [
    "AutoscalerDaemon",
    "ConfigManager",
    "ProxmoxClient", 
    "MetricsCollector",
    "ScalingEngine",
]