# LXC Autoscaler for Proxmox VE

A production-ready Python service that automatically scales LXC container resources (CPU and memory) based on workload metrics in Proxmox Virtual Environment.

## Features

- **Automatic Resource Scaling**: Dynamically adjust CPU cores and memory allocation based on container workload
- **Safety Mechanisms**: Comprehensive safety checks to prevent resource overcommitment and system instability
- **Flexible Configuration**: Per-container and global configuration with YAML support
- **Production Ready**: Systemd integration, structured logging, error handling, and monitoring
- **Async Architecture**: High-performance async/await implementation for efficient API operations
- **Comprehensive Testing**: Full test suite with pytest and type checking with mypy

## Requirements

- **Proxmox VE**: 8.4.6 or later
- **Python**: 3.8 or later
- **Operating System**: Debian Linux
- **Permissions**: Root access for system service installation

## Quick Start

### 1. Installation

Clone the repository and run the installation script on the Proxmox host:

```bash
git clone https://github.com/example/lxc-autoscaler.git
cd lxc-autoscaler
sudo ./scripts/install.sh
```

### 2. Configuration

Edit the configuration file:

```bash
sudo nano /etc/lxc-autoscaler/config.yaml
```

Minimal configuration:

```yaml
proxmox:
  host: "192.168.1.100"
  user: "root@pam"
  password: "your-password"

containers:
  - vmid: 101
    enabled: true
  - vmid: 102
    enabled: true
```

### 3. Start the Service

```bash
# Validate configuration
sudo lxc-autoscaler --validate-config

# Start the service
sudo systemctl start lxc-autoscaler

# Enable auto-start
sudo systemctl enable lxc-autoscaler
```

### 4. Monitor

```bash
# Check service status
sudo systemctl status lxc-autoscaler

# View logs
sudo journalctl -u lxc-autoscaler -f

# Get detailed status
sudo lxc-autoscaler-status
```

## Configuration

### Proxmox Connection

```yaml
proxmox:
  host: "proxmox.example.com"
  port: 8006
  user: "root@pam"
  
  # Password authentication
  password: "secret"
  
  # OR token authentication (recommended)
  token_name: "autoscaler-token"
  token_value: "secret-token-value"
  
  verify_ssl: true
  timeout: 30
```

### Container Configuration

```yaml
containers:
  - vmid: 101
    enabled: true
    
    # Custom thresholds
    thresholds:
      cpu_scale_up: 80.0      # Scale up at 80% CPU
      cpu_scale_down: 30.0    # Scale down at 30% CPU
      memory_scale_up: 85.0   # Scale up at 85% memory
      memory_scale_down: 40.0 # Scale down at 40% memory
    
    # Resource limits
    limits:
      min_cpu_cores: 1
      max_cpu_cores: 8
      min_memory_mb: 512
      max_memory_mb: 8192
      cpu_step: 1             # Cores to add/remove
      memory_step_mb: 512     # MB to add/remove
    
    cooldown_seconds: 300     # Wait 5 minutes between operations
    evaluation_periods: 3     # Average over 3 periods
```

### Safety Configuration

```yaml
safety:
  max_concurrent_operations: 3
  max_cpu_usage_threshold: 95.0
  max_memory_usage_threshold: 95.0
  emergency_scale_down_threshold: 98.0
  enable_host_protection: true
```

## How It Works

### Scaling Logic

1. **Metrics Collection**: Collects CPU and memory usage from Proxmox API every monitoring interval
2. **Evaluation**: Averages metrics over configured evaluation periods
3. **Decision Making**: Compares averages against thresholds to determine scaling needs
4. **Safety Checks**: Verifies cluster resources and safety constraints
5. **Execution**: Performs scaling operations via Proxmox API
6. **Cooldown**: Waits for cooldown period before next scaling operation

### Scaling Triggers

**Scale Up Conditions:**
- CPU usage ≥ `cpu_scale_up` threshold
- Memory usage ≥ `memory_scale_up` threshold
- Container is running
- Not in cooldown period
- Target resources within limits
- Cluster resources available

**Scale Down Conditions:**
- CPU usage ≤ `cpu_scale_down` threshold
- Memory usage ≤ `memory_scale_down` threshold
- Container is running
- Not in cooldown period
- Target resources within limits

### Safety Mechanisms

- **Host Protection**: Prevents scaling when host resources are constrained
- **Resource Limits**: Enforces minimum and maximum resource boundaries
- **Cooldown Periods**: Prevents rapid successive scaling operations
- **Concurrent Operation Limits**: Limits simultaneous scaling operations
- **Emergency Thresholds**: Triggers immediate scale-down at critical usage levels

## Commands

### Service Management

```bash
# Start/stop service
sudo systemctl start lxc-autoscaler
sudo systemctl stop lxc-autoscaler

# Check status
sudo systemctl status lxc-autoscaler
sudo lxc-autoscaler-status

# Reload configuration
sudo systemctl reload lxc-autoscaler
# OR
sudo kill -HUP $(cat /var/run/lxc-autoscaler.pid)
```

### Configuration Management

```bash
# Validate configuration
sudo lxc-autoscaler --validate-config

# Test with dry run
sudo lxc-autoscaler --dry-run

# Specify custom config file
sudo lxc-autoscaler --config /path/to/config.yaml
```

### Monitoring

```bash
# View real-time logs
sudo journalctl -u lxc-autoscaler -f

# View recent logs
sudo journalctl -u lxc-autoscaler --lines=100

# Get detailed status
sudo lxc-autoscaler-status

# Health check
sudo lxc-autoscaler-healthcheck
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/example/lxc-autoscaler.git
cd lxc-autoscaler

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Code Quality

```bash
# Linting
ruff check .

# Type checking
mypy .

# Formatting
ruff format .

# Testing
pytest
pytest --cov=lxc_autoscaler
```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_config.py

# With coverage
pytest --cov=lxc_autoscaler --cov-report=html

# Async tests
pytest tests/test_scaling.py -v
```

## Troubleshooting

### Common Issues

**Service won't start:**
- Check configuration: `lxc-autoscaler --validate-config`
- Check logs: `journalctl -u lxc-autoscaler -f`
- Verify Proxmox connectivity
- Check permissions on log/pid directories

**No scaling operations:**
- Verify containers are running
- Check that thresholds are appropriate
- Ensure containers are enabled in config
- Check cooldown periods
- Review safety constraints

**Authentication errors:**
- Verify Proxmox credentials
- Check user permissions in Proxmox
- Test API connectivity manually
- Verify SSL settings

### Log Analysis

```bash
# Filter by log level
journalctl -u lxc-autoscaler | grep ERROR

# Show only scaling operations
journalctl -u lxc-autoscaler | grep "scaling"

# Monitor specific container
journalctl -u lxc-autoscaler | grep "Container 101"
```

### Performance Tuning

**For large deployments:**
- Increase `monitoring_interval` (120-300 seconds)
- Reduce `max_concurrent_operations`
- Increase `cooldown_seconds`
- Use more `evaluation_periods`

**For responsive scaling:**
- Decrease `monitoring_interval` (30-60 seconds)
- Reduce `cooldown_seconds`
- Use fewer `evaluation_periods`
- Adjust thresholds to be more sensitive

## Security

### Best Practices

- **Use Token Authentication**: Create dedicated API tokens instead of passwords
- **Limit User Permissions**: Create dedicated user with minimal required permissions
- **Enable SSL Verification**: Always verify SSL certificates in production
- **Secure Configuration**: Protect configuration files with appropriate permissions
- **Regular Updates**: Keep the service and dependencies updated

### Proxmox Permissions

Required permissions for the autoscaler user:
- `VM.Monitor` - Read container metrics
- `VM.Config` - Modify container configuration
- `Sys.Audit` - Read node information

### File Permissions

```bash
# Configuration files
sudo chmod 640 /etc/lxc-autoscaler/config.yaml
sudo chown root:root /etc/lxc-autoscaler/config.yaml

# Log files
sudo chmod 644 /var/log/lxc-autoscaler.log
sudo chown root:root /var/log/lxc-autoscaler.log
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run code quality checks
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Issues**: Submit issues on GitHub
- **Documentation**: See the docs/ directory
- **Discussions**: Use GitHub Discussions for questions

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.
