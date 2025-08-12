"""Configuration data models."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union


@dataclass
class ProxmoxConfig:
    """Proxmox VE connection configuration."""
    
    host: str
    port: int = 8006
    user: str = "root@pam"
    password: Optional[str] = None
    token_name: Optional[str] = None
    token_value: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 30
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.password and not (self.token_name and self.token_value):
            raise ValueError("Either password or token authentication must be provided")


@dataclass
class ScalingThresholds:
    """Resource scaling thresholds."""
    
    cpu_scale_up: float = 80.0
    cpu_scale_down: float = 30.0
    memory_scale_up: float = 85.0
    memory_scale_down: float = 40.0
    
    def __post_init__(self) -> None:
        """Validate threshold values."""
        if not (0 < self.cpu_scale_up <= 100):
            raise ValueError("CPU scale up threshold must be between 0 and 100")
        if not (0 < self.cpu_scale_down <= 100):
            raise ValueError("CPU scale down threshold must be between 0 and 100")
        if not (0 < self.memory_scale_up <= 100):
            raise ValueError("Memory scale up threshold must be between 0 and 100")
        if not (0 < self.memory_scale_down <= 100):
            raise ValueError("Memory scale down threshold must be between 0 and 100")
        if self.cpu_scale_up <= self.cpu_scale_down:
            raise ValueError("CPU scale up threshold must be greater than scale down threshold")
        if self.memory_scale_up <= self.memory_scale_down:
            raise ValueError("Memory scale up threshold must be greater than scale down threshold")


@dataclass
class ResourceLimits:
    """Resource scaling limits."""
    
    min_cpu_cores: int = 1
    max_cpu_cores: int = 8
    min_memory_mb: int = 512
    max_memory_mb: int = 8192
    cpu_step: int = 1
    memory_step_mb: int = 256
    
    def __post_init__(self) -> None:
        """Validate resource limits."""
        if self.min_cpu_cores >= self.max_cpu_cores:
            raise ValueError("Min CPU cores must be less than max CPU cores")
        if self.min_memory_mb >= self.max_memory_mb:
            raise ValueError("Min memory must be less than max memory")
        if self.cpu_step <= 0:
            raise ValueError("CPU step must be positive")
        if self.memory_step_mb <= 0:
            raise ValueError("Memory step must be positive")


@dataclass
class ContainerConfig:
    """Per-container scaling configuration."""
    
    vmid: int
    enabled: bool = True
    thresholds: Optional[ScalingThresholds] = None
    limits: Optional[ResourceLimits] = None
    cooldown_seconds: int = 300
    evaluation_periods: int = 3
    
    def __post_init__(self) -> None:
        """Set defaults if not provided."""
        if self.thresholds is None:
            self.thresholds = ScalingThresholds()
        if self.limits is None:
            self.limits = ResourceLimits()
        if self.cooldown_seconds < 60:
            raise ValueError("Cooldown period must be at least 60 seconds")
        if self.evaluation_periods < 1:
            raise ValueError("Evaluation periods must be at least 1")


@dataclass
class GlobalConfig:
    """Global autoscaler configuration."""
    
    monitoring_interval: int = 60
    log_level: str = "INFO"
    log_file: Optional[str] = None  # Default to None for container stdout/stderr logging
    pid_file: str = "/tmp/lxc-autoscaler.pid"  # Use /tmp for containers instead of /var/run
    enable_notifications: bool = False
    notification_webhook: Optional[str] = None
    dry_run: bool = False
    
    def __post_init__(self) -> None:
        """Validate global configuration."""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_log_levels:
            raise ValueError(f"Log level must be one of {valid_log_levels}")
        if self.monitoring_interval < 30:
            raise ValueError("Monitoring interval must be at least 30 seconds")


@dataclass
class SafetyConfig:
    """Safety and resource protection configuration."""
    
    max_concurrent_operations: int = 3
    max_cpu_usage_threshold: float = 95.0
    max_memory_usage_threshold: float = 95.0
    emergency_scale_down_threshold: float = 98.0
    resource_check_interval: int = 30
    enable_host_protection: bool = True
    
    def __post_init__(self) -> None:
        """Validate safety configuration."""
        if self.max_concurrent_operations < 1:
            raise ValueError("Max concurrent operations must be at least 1")
        if not (50 <= self.max_cpu_usage_threshold <= 100):
            raise ValueError("Max CPU usage threshold must be between 50 and 100")
        if not (50 <= self.max_memory_usage_threshold <= 100):
            raise ValueError("Max memory usage threshold must be between 50 and 100")


@dataclass
class AutoscalerConfig:
    """Main autoscaler configuration."""
    
    proxmox: ProxmoxConfig
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    default_thresholds: ScalingThresholds = field(default_factory=ScalingThresholds)
    default_limits: ResourceLimits = field(default_factory=ResourceLimits)
    containers: List[ContainerConfig] = field(default_factory=list)
    
    def get_container_config(self, vmid: int) -> Optional[ContainerConfig]:
        """Get configuration for specific container."""
        for container in self.containers:
            if container.vmid == vmid:
                return container
        return None
    
    def add_container(self, container: ContainerConfig) -> None:
        """Add or update container configuration."""
        existing = self.get_container_config(container.vmid)
        if existing:
            # Update existing configuration
            idx = self.containers.index(existing)
            self.containers[idx] = container
        else:
            self.containers.append(container)
    
    def remove_container(self, vmid: int) -> bool:
        """Remove container from configuration."""
        container = self.get_container_config(vmid)
        if container:
            self.containers.remove(container)
            return True
        return False