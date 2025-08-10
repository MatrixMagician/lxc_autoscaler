"""Data models for scaling operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ScalingAction(Enum):
    """Types of scaling actions."""
    SCALE_UP_CPU = "scale_up_cpu"
    SCALE_DOWN_CPU = "scale_down_cpu"
    SCALE_UP_MEMORY = "scale_up_memory"
    SCALE_DOWN_MEMORY = "scale_down_memory"
    NO_ACTION = "no_action"


class ScalingReason(Enum):
    """Reasons for scaling decisions."""
    CPU_HIGH = "cpu_usage_high"
    CPU_LOW = "cpu_usage_low"
    MEMORY_HIGH = "memory_usage_high"
    MEMORY_LOW = "memory_usage_low"
    RESOURCE_LIMIT_REACHED = "resource_limit_reached"
    INSUFFICIENT_DATA = "insufficient_data"
    COOLDOWN_PERIOD = "cooldown_period"
    CONTAINER_NOT_RUNNING = "container_not_running"
    SAFETY_THRESHOLD_EXCEEDED = "safety_threshold_exceeded"
    DRY_RUN_MODE = "dry_run_mode"


@dataclass
class ScalingDecision:
    """Represents a scaling decision for a container."""
    
    vmid: int
    node: str
    action: ScalingAction
    reason: ScalingReason
    current_cpu_cores: int
    current_memory_mb: int
    target_cpu_cores: Optional[int] = None
    target_memory_mb: Optional[int] = None
    current_cpu_usage: Optional[float] = None
    current_memory_usage: Optional[float] = None
    timestamp: float = None
    
    def __post_init__(self) -> None:
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()
    
    @property
    def requires_scaling(self) -> bool:
        """Check if this decision requires actual scaling."""
        return self.action != ScalingAction.NO_ACTION
    
    @property
    def cpu_change(self) -> int:
        """Calculate CPU core change."""
        if self.target_cpu_cores is None:
            return 0
        return self.target_cpu_cores - self.current_cpu_cores
    
    @property
    def memory_change_mb(self) -> int:
        """Calculate memory change in MB."""
        if self.target_memory_mb is None:
            return 0
        return self.target_memory_mb - self.current_memory_mb
    
    def __str__(self) -> str:
        """String representation of scaling decision."""
        if not self.requires_scaling:
            return f"Container {self.vmid}: No scaling needed ({self.reason.value})"
        
        changes = []
        if self.cpu_change != 0:
            changes.append(f"CPU: {self.current_cpu_cores} → {self.target_cpu_cores}")
        if self.memory_change_mb != 0:
            changes.append(f"Memory: {self.current_memory_mb} → {self.target_memory_mb}MB")
        
        change_str = ", ".join(changes)
        return f"Container {self.vmid}: {self.action.value} ({change_str}) - {self.reason.value}"


@dataclass
class ScalingOperation:
    """Represents an ongoing scaling operation."""
    
    decision: ScalingDecision
    started_at: float
    completed_at: Optional[float] = None
    success: Optional[bool] = None
    error_message: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Set started timestamp if not provided."""
        if self.started_at is None:
            self.started_at = time.time()
    
    @property
    def is_completed(self) -> bool:
        """Check if operation is completed."""
        return self.completed_at is not None
    
    @property
    def duration(self) -> Optional[float]:
        """Get operation duration in seconds."""
        if not self.is_completed:
            return None
        return self.completed_at - self.started_at
    
    @property
    def is_successful(self) -> bool:
        """Check if operation was successful."""
        return self.success is True
    
    def complete_success(self) -> None:
        """Mark operation as successfully completed."""
        self.completed_at = time.time()
        self.success = True
    
    def complete_failure(self, error_message: str) -> None:
        """Mark operation as failed.
        
        Args:
            error_message: Error description.
        """
        self.completed_at = time.time()
        self.success = False
        self.error_message = error_message
    
    def __str__(self) -> str:
        """String representation of scaling operation."""
        status = "completed" if self.is_completed else "in progress"
        if self.is_completed:
            result = "successfully" if self.is_successful else f"failed: {self.error_message}"
            duration = f" in {self.duration:.2f}s" if self.duration else ""
            status = f"{status} {result}{duration}"
        
        return f"Scaling operation for container {self.decision.vmid}: {status}"


@dataclass
class ScalingHistory:
    """Tracks scaling history for a container."""
    
    vmid: int
    last_scaling_time: Optional[float] = None
    last_scaling_action: Optional[ScalingAction] = None
    operation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    
    def record_operation(self, operation: ScalingOperation) -> None:
        """Record a completed scaling operation.
        
        Args:
            operation: Completed scaling operation.
        """
        if not operation.is_completed:
            return
        
        self.last_scaling_time = operation.completed_at
        self.last_scaling_action = operation.decision.action
        self.operation_count += 1
        
        if operation.is_successful:
            self.success_count += 1
        else:
            self.failure_count += 1
    
    def is_in_cooldown(self, cooldown_seconds: int) -> bool:
        """Check if container is in cooldown period.
        
        Args:
            cooldown_seconds: Cooldown period in seconds.
            
        Returns:
            True if in cooldown period.
        """
        if self.last_scaling_time is None:
            return False
        
        time_since_last = time.time() - self.last_scaling_time
        return time_since_last < cooldown_seconds
    
    def get_cooldown_remaining(self, cooldown_seconds: int) -> float:
        """Get remaining cooldown time in seconds.
        
        Args:
            cooldown_seconds: Cooldown period in seconds.
            
        Returns:
            Remaining cooldown time or 0 if not in cooldown.
        """
        if not self.is_in_cooldown(cooldown_seconds):
            return 0.0
        
        time_since_last = time.time() - self.last_scaling_time
        return cooldown_seconds - time_since_last
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate of scaling operations.
        
        Returns:
            Success rate as percentage (0-100).
        """
        if self.operation_count == 0:
            return 0.0
        
        return (self.success_count / self.operation_count) * 100