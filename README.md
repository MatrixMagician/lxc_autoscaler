# LXC Autoscaler for Proxmox VE

A production-ready containerized service that automatically scales LXC container resources (CPU and memory) based on workload metrics in Proxmox Virtual Environment.

## Features

- **Automatic Resource Scaling**: Dynamically adjust CPU cores and memory allocation based on container workload
- **Safety Mechanisms**: Comprehensive safety checks to prevent resource overcommitment and system instability
- **Flexible Configuration**: Per-container and global configuration with YAML support
- **Production Ready**: Docker containerization, structured logging, error handling, and monitoring
- **Async Architecture**: High-performance async/await implementation for efficient API operations
- **Comprehensive Testing**: Full test suite with pytest and type checking with mypy
- **Health Monitoring**: Built-in health checks and monitoring capabilities

## Requirements

- **Proxmox VE**: 8.4.6 or later
- **Docker**: 20.10 or later
- **Docker Compose**: 2.0 or later (optional but recommended)
- **Operating System**: Any Docker-compatible OS (Linux, macOS, Windows)

## Quick Start

### 1. Clone and Build

```bash
git clone https://github.com/MatrixMagician/lxc-autoscaler.git
cd lxc-autoscaler

# Build the Docker image
make build

# Or using Docker directly
docker build -t lxc_autoscaler .
```

### 2. Initialize Configuration

```bash
# Copy example configuration
cp examples/config.yaml config/config.yaml

# Edit configuration
nano config/config.yaml
```

Minimal configuration:

```yaml
proxmox:
  host: "192.168.2.90"
  user: "root@pam"
  token_name: "lxc_autoscaler"
  token_value: "ac1e95ab-8c07-4c7a-bd46-6788786c97f3"

containers:
  - vmid: 101
    enabled: true
  - vmid: 102
    enabled: true
```

### 3. Deploy and Run

```bash
# Validate configuration
make validate-config

# Start with Docker Compose (recommended)
make up

# Or run directly
make run
```

### 4. Monitor

```bash
# Check container status
make status

# View logs
make logs

# Follow logs in real-time
make logs-follow
```

## Deployment Methods

### Docker Compose (Recommended)

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Manual Docker Run

```bash
# Basic run
docker run -d \
  --name lxc_autoscaler \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  lxc_autoscaler

# With environment variables
docker run -d \
  --name lxc_autoscaler \
  -v $(pwd)/config:/app/config \
  -e PROXMOX_HOST="192.168.2.90" \
  -e PROXMOX_USER="root@pam" \
  -e PROXMOX_TOKEN_NAME="lxc_autoscaler" \
  -e PROXMOX_TOKEN_VALUE="ac1e95ab-8c07-4c7a-bd46-6788786c97f3" \
  lxc_autoscaler
```

### Environment Variables

```bash
# Proxmox connection
PROXMOX_HOST=192.168.2.90
PROXMOX_PORT=8006
PROXMOX_USER=root@pam
PROXMOX_TOKEN_NAME=lxc_autoscaler
PROXMOX_TOKEN_VALUE=your-token-value

# Logging
LOG_LEVEL=INFO
LOG_FILE=/app/logs/lxc_autoscaler.log

# Configuration
CONFIG_FILE=/app/config/config.yaml
```

## Configuration

### Proxmox Connection

```yaml
proxmox:
  host: "192.168.2.90"
  port: 8006
  user: "root@pam"
  
  # Token authentication (recommended)
  token_name: "lxc_autoscaler"
  token_value: "ac1e95ab-8c07-4c7a-bd46-6788786c97f3"
  
  # OR password authentication
  password: "your-password"
  
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

### Global Settings

```yaml
global:
  monitoring_interval: 60     # Check metrics every 60 seconds
  log_level: "INFO"
  enable_dry_run: false

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

### Available Make Commands

```bash
# Build and deployment
make build          # Build Docker image
make up             # Start with Docker Compose
make down           # Stop Docker Compose
make restart        # Restart the service

# Running and testing
make run            # Run container directly
make run-dev        # Run in development mode
make validate-config # Validate configuration
make dry-run        # Test run without making changes

# Monitoring and debugging
make status         # Check container status
make logs           # View logs
make logs-follow    # Follow logs in real-time
make shell          # Open shell in container
make health-check   # Run health check

# Development
make test           # Run tests
make lint           # Run linting
make format         # Format code
make type-check     # Run type checking

# Cleanup
make clean          # Remove containers and images
make clean-all      # Remove everything including volumes
```

### Container Management

```bash
# Check container status
docker ps | grep lxc_autoscaler

# View real-time logs
docker logs -f lxc_autoscaler

# Execute commands in container
docker exec -it lxc_autoscaler lxc-autoscaler --help

# Restart container
docker restart lxc_autoscaler

# Stop container
docker stop lxc_autoscaler
```

### Configuration Management

```bash
# Validate configuration
docker exec lxc_autoscaler lxc-autoscaler --validate-config

# Test with dry run
docker exec lxc_autoscaler lxc-autoscaler --dry-run

# Check container health
docker exec lxc_autoscaler lxc-autoscaler --health-check
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/example/lxc-autoscaler.git
cd lxc-autoscaler

# Build development image
make build

# Run development container with code mounted
make run-dev
```

### Code Quality

```bash
# Run all quality checks
make lint           # Ruff linting
make format         # Ruff formatting  
make type-check     # MyPy type checking
make test           # Pytest testing

# Individual checks
docker run --rm -v $(pwd):/app lxc_autoscaler ruff check .
docker run --rm -v $(pwd):/app lxc_autoscaler mypy .
docker run --rm -v $(pwd):/app lxc_autoscaler pytest
```

### Running Tests

```bash
# All tests
make test

# Specific test file
docker run --rm -v $(pwd):/app lxc_autoscaler pytest tests/test_config.py

# With coverage
docker run --rm -v $(pwd):/app lxc_autoscaler pytest --cov=lxc_autoscaler --cov-report=html

# Interactive testing
make run-dev
pytest tests/test_scaling.py -v
```

### Development Workflow

```bash
# 1. Make code changes
# 2. Test changes
make test

# 3. Check code quality
make lint
make type-check

# 4. Format code
make format

# 5. Build updated image
make build

# 6. Test in container
make validate-config
make dry-run
```

## Production Deployment

### Docker Swarm

```yaml
# docker-stack.yml
version: '3.8'
services:
  lxc-autoscaler:
    image: lxc_autoscaler:latest
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    environment:
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "lxc-autoscaler", "--health-check"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lxc-autoscaler
spec:
  replicas: 1
  selector:
    matchLabels:
      app: lxc-autoscaler
  template:
    metadata:
      labels:
        app: lxc-autoscaler
    spec:
      containers:
      - name: lxc-autoscaler
        image: lxc_autoscaler:latest
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: config
        configMap:
          name: lxc-autoscaler-config
      - name: logs
        emptyDir: {}
```

### Backup and Recovery

```bash
# Backup configuration
docker cp lxc_autoscaler:/app/config ./backup/config-$(date +%Y%m%d)

# Backup logs
docker cp lxc_autoscaler:/app/logs ./backup/logs-$(date +%Y%m%d)

# Restore configuration
docker cp ./backup/config-20240101 lxc_autoscaler:/app/config
docker restart lxc_autoscaler
```

## Troubleshooting

### Common Issues

**Container won't start:**
```bash
# Check configuration
make validate-config

# Check container logs
make logs

# Verify Proxmox connectivity
docker exec lxc_autoscaler ping 192.168.2.90

# Check container health
make health-check
```

**No scaling operations:**
```bash
# Check container status
make status

# Enable debug logging
docker exec lxc_autoscaler sed -i 's/INFO/DEBUG/' /app/config/config.yaml
docker restart lxc_autoscaler

# Monitor real-time logs
make logs-follow
```

**Authentication errors:**
```bash
# Test Proxmox API connectivity
docker exec -it lxc_autoscaler bash
curl -k https://192.168.2.90:8006/api2/json/version

# Verify token permissions
docker exec lxc_autoscaler lxc-autoscaler --validate-config --verbose
```

### Container Debugging

```bash
# Enter container shell
make shell

# Check container processes
docker exec lxc_autoscaler ps aux

# View container environment
docker exec lxc_autoscaler env

# Check file permissions
docker exec lxc_autoscaler ls -la /app/config/

# Monitor resource usage
docker stats lxc_autoscaler
```

### Log Analysis

```bash
# Filter by log level
make logs | grep ERROR

# Show only scaling operations
make logs | grep "scaling"

# Monitor specific container
make logs | grep "Container 101"

# Export logs for analysis
docker logs lxc_autoscaler > lxc_autoscaler.log
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
- **Secure Configuration**: Use Docker secrets or encrypted volumes for sensitive data
- **Regular Updates**: Keep container images and dependencies updated
- **Network Isolation**: Use Docker networks to isolate the autoscaler

### Proxmox Permissions

Required permissions for the autoscaler user:
- `VM.Monitor` - Read container metrics
- `VM.Config` - Modify container configuration
- `Sys.Audit` - Read node information

### Container Security

```bash
# Run with non-root user (already configured in Dockerfile)
docker run --user 1000:1000 lxc_autoscaler

# Use read-only filesystem
docker run --read-only -v /tmp lxc_autoscaler

# Limit container resources
docker run --memory=256m --cpus=0.5 lxc_autoscaler

# Use Docker secrets for sensitive data
echo "your-token" | docker secret create proxmox_token -
```

## Monitoring and Observability

### Health Checks

```bash
# Built-in health check
make health-check

# Custom health monitoring
docker exec lxc_autoscaler lxc-autoscaler --health-check --format json
```

### Metrics Integration

The service can integrate with monitoring solutions:
- **Prometheus**: Export metrics endpoint
- **Grafana**: Dashboard templates available
- **ELK Stack**: Structured JSON logging
- **Datadog**: Custom metrics and alerts

### Log Management

```bash
# Configure log rotation
docker run -v $(pwd)/logs:/app/logs \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  lxc_autoscaler

# Send logs to external system
docker run --log-driver syslog \
  --log-opt syslog-address=tcp://log-server:514 \
  lxc_autoscaler
```

## API Reference

### Configuration File Schema

The service uses YAML configuration files with the following structure:

- `/home/oliverh/repo/lxc_autoscaler/examples/config.yaml` - Full example
- `/home/oliverh/repo/lxc_autoscaler/examples/minimal-config.yaml` - Minimal example
- `/home/oliverh/repo/lxc_autoscaler/examples/production-config.yaml` - Production example

### Command Line Interface

```bash
# Available commands
docker exec lxc_autoscaler lxc-autoscaler --help

# Configuration validation
docker exec lxc_autoscaler lxc-autoscaler --validate-config

# Dry run mode
docker exec lxc_autoscaler lxc-autoscaler --dry-run

# Health check
docker exec lxc_autoscaler lxc-autoscaler --health-check

# Custom config file
docker exec lxc_autoscaler lxc-autoscaler --config /app/config/custom.yaml
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run code quality checks: `make lint && make test`
5. Build and test Docker image: `make build && make test`
6. Submit a pull request

### Project Structure

```
/home/oliverh/repo/lxc_autoscaler/
├── lxc_autoscaler/          # Main Python package
├── examples/                # Configuration examples
├── tests/                   # Test suite
├── Dockerfile              # Container definition
├── docker-compose.yml      # Orchestration
├── pyproject.toml         # Python project configuration
├── Makefile               # Development commands
└── README.md              # This file
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Issues**: Submit issues on GitHub
- **Documentation**: See `DOCKER.md` for Docker-specific documentation
- **Discussions**: Use GitHub Discussions for questions

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.