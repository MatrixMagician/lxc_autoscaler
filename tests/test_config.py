"""Tests for configuration management."""

import pytest
import tempfile
import yaml
from pathlib import Path

from lxc_autoscaler.config.manager import ConfigManager, ConfigurationError
from lxc_autoscaler.config.models import (
    AutoscalerConfig,
    ProxmoxConfig,
    ContainerConfig,
    ResourceLimits,
    ScalingThresholds,
)


class TestConfigModels:
    """Test configuration data models."""
    
    def test_proxmox_config_password_auth(self):
        """Test ProxmoxConfig with password authentication."""
        config = ProxmoxConfig(
            host="192.168.1.100",
            user="root@pam",
            password="secret123"
        )
        assert config.host == "192.168.1.100"
        assert config.port == 8006
        assert config.user == "root@pam"
        assert config.password == "secret123"
        assert config.verify_ssl is True
    
    def test_proxmox_config_token_auth(self):
        """Test ProxmoxConfig with token authentication."""
        config = ProxmoxConfig(
            host="192.168.1.100",
            token_name="api-token",
            token_value="secret-token-value"
        )
        assert config.token_name == "api-token"
        assert config.token_value == "secret-token-value"
    
    def test_proxmox_config_no_auth_fails(self):
        """Test ProxmoxConfig fails without authentication."""
        with pytest.raises(ValueError, match="Either password or token authentication"):
            ProxmoxConfig(host="192.168.1.100")
    
    def test_scaling_thresholds_validation(self):
        """Test ScalingThresholds validation."""
        # Valid thresholds
        thresholds = ScalingThresholds(
            cpu_scale_up=80.0,
            cpu_scale_down=30.0,
            memory_scale_up=85.0,
            memory_scale_down=40.0
        )
        assert thresholds.cpu_scale_up == 80.0
        
        # Invalid threshold order
        with pytest.raises(ValueError, match="CPU scale up threshold must be greater"):
            ScalingThresholds(cpu_scale_up=30.0, cpu_scale_down=80.0)
    
    def test_resource_limits_validation(self):
        """Test ResourceLimits validation."""
        # Valid limits
        limits = ResourceLimits(
            min_cpu_cores=1,
            max_cpu_cores=8,
            min_memory_mb=512,
            max_memory_mb=8192
        )
        assert limits.min_cpu_cores == 1
        assert limits.max_cpu_cores == 8
        
        # Invalid limits
        with pytest.raises(ValueError, match="Min CPU cores must be less than max"):
            ResourceLimits(min_cpu_cores=8, max_cpu_cores=4)
    
    def test_container_config_defaults(self):
        """Test ContainerConfig with defaults."""
        config = ContainerConfig(vmid=101)
        assert config.vmid == 101
        assert config.enabled is True
        assert config.thresholds is not None
        assert config.limits is not None
        assert config.cooldown_seconds == 300
        assert config.evaluation_periods == 3


class TestConfigManager:
    """Test configuration manager."""
    
    def create_test_config_file(self, config_data: dict) -> Path:
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.safe_dump(config_data, f)
            return Path(f.name)
    
    def test_load_valid_config(self):
        """Test loading valid configuration."""
        config_data = {
            'proxmox': {
                'host': '192.168.1.100',
                'user': 'root@pam',
                'password': 'secret123'
            },
            'global': {
                'monitoring_interval': 60,
                'log_level': 'INFO'
            },
            'containers': [
                {
                    'vmid': 101,
                    'enabled': True
                }
            ]
        }
        
        config_file = self.create_test_config_file(config_data)
        try:
            manager = ConfigManager(str(config_file))
            config = manager.load_config()
            
            assert isinstance(config, AutoscalerConfig)
            assert config.proxmox.host == '192.168.1.100'
            assert config.global_config.monitoring_interval == 60
            assert len(config.containers) == 1
            assert config.containers[0].vmid == 101
        finally:
            config_file.unlink()
    
    def test_load_config_with_env_vars(self):
        """Test loading configuration with environment variable substitution."""
        import os
        
        # Set test environment variable
        os.environ['TEST_PROXMOX_HOST'] = '192.168.1.200'
        
        config_data = {
            'proxmox': {
                'host': '${TEST_PROXMOX_HOST}',
                'user': 'root@pam',
                'password': 'secret123'
            }
        }
        
        config_file = self.create_test_config_file(config_data)
        try:
            manager = ConfigManager(str(config_file))
            config = manager.load_config()
            
            assert config.proxmox.host == '192.168.1.200'
        finally:
            config_file.unlink()
            del os.environ['TEST_PROXMOX_HOST']
    
    def test_load_config_missing_proxmox(self):
        """Test loading configuration without Proxmox section fails."""
        config_data = {
            'global': {
                'monitoring_interval': 60
            }
        }
        
        config_file = self.create_test_config_file(config_data)
        try:
            manager = ConfigManager(str(config_file))
            with pytest.raises(ConfigurationError, match="Proxmox configuration is required"):
                manager.load_config()
        finally:
            config_file.unlink()
    
    def test_load_nonexistent_config(self):
        """Test loading non-existent configuration file."""
        with pytest.raises(ConfigurationError, match="No configuration file found"):
            manager = ConfigManager("/nonexistent/config.yaml")
            manager.load_config()
    
    def test_validate_config_file(self):
        """Test configuration file validation."""
        config_data = {
            'proxmox': {
                'host': '192.168.1.100',
                'user': 'root@pam',
                'password': 'secret123'
            }
        }
        
        config_file = self.create_test_config_file(config_data)
        try:
            manager = ConfigManager()
            result = manager.validate_config_file(str(config_file))
            assert result is True
        finally:
            config_file.unlink()


if __name__ == '__main__':
    pytest.main([__file__])