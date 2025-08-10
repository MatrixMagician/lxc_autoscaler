"""Tests for scaling engine."""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from lxc_autoscaler.scaling.models import (
    ScalingAction,
    ScalingDecision,
    ScalingHistory,
    ScalingOperation,
    ScalingReason,
)


class TestScalingDecision:
    """Test ScalingDecision model."""
    
    def test_no_action_decision(self):
        """Test scaling decision with no action."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.NO_ACTION,
            reason=ScalingReason.INSUFFICIENT_DATA,
            current_cpu_cores=2,
            current_memory_mb=2048
        )
        
        assert not decision.requires_scaling
        assert decision.cpu_change == 0
        assert decision.memory_change_mb == 0
    
    def test_scale_up_cpu_decision(self):
        """Test CPU scale-up decision."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4,
            current_cpu_usage=85.0
        )
        
        assert decision.requires_scaling
        assert decision.cpu_change == 2  # 4 - 2
        assert decision.memory_change_mb == 0
        assert decision.current_cpu_usage == 85.0
    
    def test_scale_down_memory_decision(self):
        """Test memory scale-down decision."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_DOWN_MEMORY,
            reason=ScalingReason.MEMORY_LOW,
            current_cpu_cores=2,
            current_memory_mb=4096,
            target_memory_mb=2048,
            current_memory_usage=25.0
        )
        
        assert decision.requires_scaling
        assert decision.cpu_change == 0
        assert decision.memory_change_mb == -2048  # 2048 - 4096
        assert decision.current_memory_usage == 25.0
    
    def test_string_representation(self):
        """Test ScalingDecision string representation."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4
        )
        
        str_repr = str(decision)
        assert "Container 101" in str_repr
        assert "scale_up_cpu" in str_repr
        assert "CPU: 2 → 4" in str_repr
        assert "cpu_usage_high" in str_repr


class TestScalingOperation:
    """Test ScalingOperation model."""
    
    def test_operation_lifecycle(self):
        """Test scaling operation lifecycle."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4
        )
        
        operation = ScalingOperation(decision=decision, started_at=time.time())
        
        # Initial state
        assert not operation.is_completed
        assert not operation.is_successful
        assert operation.duration is None
        
        # Complete successfully
        operation.complete_success()
        
        assert operation.is_completed
        assert operation.is_successful
        assert operation.duration is not None
        assert operation.error_message is None
    
    def test_operation_failure(self):
        """Test scaling operation failure."""
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4
        )
        
        operation = ScalingOperation(decision=decision, started_at=time.time())
        
        # Complete with failure
        error_msg = "API connection failed"
        operation.complete_failure(error_msg)
        
        assert operation.is_completed
        assert not operation.is_successful
        assert operation.error_message == error_msg


class TestScalingHistory:
    """Test ScalingHistory model."""
    
    def test_record_successful_operation(self):
        """Test recording successful operation."""
        history = ScalingHistory(vmid=101)
        
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4
        )
        
        operation = ScalingOperation(decision=decision, started_at=time.time())
        operation.complete_success()
        
        # Record operation
        history.record_operation(operation)
        
        assert history.operation_count == 1
        assert history.success_count == 1
        assert history.failure_count == 0
        assert history.last_scaling_action == ScalingAction.SCALE_UP_CPU
        assert history.success_rate == 100.0
    
    def test_record_failed_operation(self):
        """Test recording failed operation."""
        history = ScalingHistory(vmid=101)
        
        decision = ScalingDecision(
            vmid=101,
            node="proxmox-01",
            action=ScalingAction.SCALE_UP_CPU,
            reason=ScalingReason.CPU_HIGH,
            current_cpu_cores=2,
            current_memory_mb=2048,
            target_cpu_cores=4
        )
        
        operation = ScalingOperation(decision=decision, started_at=time.time())
        operation.complete_failure("Test error")
        
        # Record operation
        history.record_operation(operation)
        
        assert history.operation_count == 1
        assert history.success_count == 0
        assert history.failure_count == 1
        assert history.success_rate == 0.0
    
    def test_cooldown_period(self):
        """Test cooldown period functionality."""
        history = ScalingHistory(vmid=101)
        
        # No scaling yet - not in cooldown
        assert not history.is_in_cooldown(300)
        assert history.get_cooldown_remaining(300) == 0.0
        
        # Record recent scaling
        history.last_scaling_time = time.time()
        
        # Should be in cooldown
        assert history.is_in_cooldown(300)
        remaining = history.get_cooldown_remaining(300)
        assert 290 < remaining <= 300  # Should be close to 300 seconds
        
        # Set scaling time in the past
        history.last_scaling_time = time.time() - 400
        
        # Should not be in cooldown
        assert not history.is_in_cooldown(300)
        assert history.get_cooldown_remaining(300) == 0.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        history = ScalingHistory(vmid=101)
        
        # No operations - 0% success rate
        assert history.success_rate == 0.0
        
        # Simulate operations
        history.operation_count = 10
        history.success_count = 7
        history.failure_count = 3
        
        assert history.success_rate == 70.0


if __name__ == '__main__':
    pytest.main([__file__])