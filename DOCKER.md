# Docker Deployment Guide

This guide covers running the LXC Autoscaler in Docker containers for development and production environments.

## Quick Start

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/MatrixMagician/lxc-autoscaler.git
cd lxc-autoscaler

# Quick setup (builds image and initializes config)
make setup

# Edit configuration
nano config/config.yaml
```

### 2. Configuration

Copy and customize the configuration:

```bash
# Copy example configuration
cp examples/config.yaml config/config.yaml

# For production, use the production example
cp examples/production-config.yaml config/config.yaml
```

Edit `config/config.yaml` with your Proxmox VE settings:

```yaml
proxmox:
  host: "your-proxmox-host.com"
  user: "root@pam"
  password: "${PROXMOX_PASSWORD}"  # Set via environment variable
```

### 3. Environment Variables

Create a `.env` file for sensitive configuration:

```bash
# .env file (do not commit to version control)
PROXMOX_PASSWORD=your_proxmox_password
# or use token authentication
PROXMOX_TOKEN=your_proxmox_token
LOG_LEVEL=INFO
DRY_RUN=false
```

### 4. Run the Service

```bash
# Validate configuration
make validate

# Start in dry-run mode (recommended first)
make dry-run

# Start normally
make run

# View logs
make logs
```

## Docker Images

### Multi-Stage Build

The Dockerfile uses a multi-stage build pattern:

- **Builder stage**: Installs build dependencies and compiles the application
- **Runtime stage**: Minimal production image with only runtime dependencies

### Image Features

- **Base**: Python 3.11 slim-bookworm for security and size
- **Security**: Non-root user, minimal attack surface
- **Health checks**: Built-in health monitoring
- **Logging**: Structured logging with configurable levels
- **Signals**: Proper signal handling for graceful shutdowns
- **Init system**: Uses tini for proper process management

## Running Options

### Using Docker Compose (Recommended)

```bash
# Production deployment
docker-compose up -d

# Development with override
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

# View status
docker-compose ps
```

### Using Docker CLI

```bash
# Build image
docker build -t lxc-autoscaler .

# Run with volume mounts
docker run -d \
  --name lxc-autoscaler \
  --restart unless-stopped \
  -v $(pwd)/config:/app/config:ro \
  -v lxc-logs:/app/logs \
  -e PROXMOX_PASSWORD=your_password \
  lxc-autoscaler
```

### Using Makefile Commands

```bash
# See all available commands
make help

# Common operations
make build        # Build Docker image
make run          # Start with docker-compose
make stop         # Stop containers
make logs         # View logs
make health       # Check health status
make clean        # Clean up containers
```

## Configuration

### Volume Mounts

- `/app/config` - Configuration files (required, read-only)
- `/app/logs` - Log files (persistent)
- `/app/run` - Runtime files like PID files
- `/app/data` - Future data storage

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LXC_AUTOSCALER_CONFIG_PATH` | `/app/config/config.yaml` | Configuration file path |
| `LXC_AUTOSCALER_LOG_LEVEL` | `INFO` | Logging level |
| `LXC_AUTOSCALER_LOG_FILE` | `/app/logs/lxc-autoscaler.log` | Log file path |
| `LXC_AUTOSCALER_PID_FILE` | `/app/run/lxc-autoscaler.pid` | PID file path |
| `PROXMOX_PASSWORD` | - | Proxmox password (if using password auth) |
| `PROXMOX_TOKEN` | - | Proxmox API token (if using token auth) |
| `DRY_RUN` | `false` | Enable dry-run mode |
| `TZ` | `UTC` | Timezone |

### Security Configuration

The container follows security best practices:

- Runs as non-root user (UID 1001)
- Uses `no-new-privileges` security option
- Read-only root filesystem option available
- Minimal base image with only necessary packages
- Regular security updates via base image updates

## Development

### Development Environment

```bash
# Build development image
make build-dev

# Start development environment
make dev

# Open development shell
make dev-shell
```

### Testing

```bash
# Run tests in container
make test

# Validate configuration
make validate

# Test with dry-run mode
make dry-run
```

### Debugging

```bash
# View detailed logs
make logs

# Open shell in running container
make shell

# Open root shell (for debugging only)
make shell-root

# Check container health
make health
```

## Production Deployment

### Resource Limits

The docker-compose configuration includes resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 128M
```

### Monitoring

Monitor the service using:

```bash
# Check status
make status

# View health
make health

# Monitor logs
make logs
```

### Updates

```bash
# Pull latest image
make pull

# Rebuild and restart
make build && make restart
```

## Backup and Recovery

### Configuration Backup

```bash
# Backup configuration
cp config/config.yaml config/config.yaml.backup.$(date +%s)
```

### Log Archival

Logs are automatically rotated using Docker's logging driver:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Volume Backup

```bash
# Backup persistent volumes
docker run --rm -v lxc-autoscaler-logs:/data -v $(pwd):/backup alpine \
  tar czf /backup/logs-backup-$(date +%s).tar.gz -C /data .
```

## Troubleshooting

### Common Issues

1. **Configuration not found**
   ```bash
   # Ensure config is mounted correctly
   ls -la config/
   make validate
   ```

2. **Permission errors**
   ```bash
   # Fix ownership
   sudo chown -R 1001:1001 config/ logs/
   ```

3. **Connection issues**
   ```bash
   # Test connectivity
   make shell
   curl -k https://your-proxmox-host:8006/api2/json/version
   ```

### Health Checks

The container includes built-in health checks:

```bash
# Check health status
docker inspect lxc-autoscaler --format='{{.State.Health.Status}}'

# View health history
docker inspect lxc-autoscaler --format='{{json .State.Health}}'
```

### Log Analysis

```bash
# Follow logs in real-time
make logs

# Search logs
docker-compose logs | grep ERROR

# Export logs
docker-compose logs > lxc-autoscaler.log
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]
    tags: [v*]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker image
        run: |
          docker build \
            --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
            --build-arg VERSION=${GITHUB_REF#refs/tags/} \
            --build-arg VCS_REF=${GITHUB_SHA} \
            -t lxc-autoscaler:${GITHUB_REF#refs/tags/} \
            .
      
      - name: Run tests
        run: make test
      
      - name: Push to registry
        if: startsWith(github.ref, 'refs/tags/')
        run: make push
```

## Support and Documentation

- [Main README](README.md) - General project information
- [Configuration Guide](examples/) - Configuration examples
- [API Documentation](https://lxc-autoscaler.readthedocs.io/)
- [Issues](https://github.com/MatrixMagician/lxc-autoscaler/issues) - Bug reports and feature requests