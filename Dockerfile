# Multi-stage production Dockerfile for LXC Autoscaler
# This follows Docker best practices for security, efficiency, and layer caching

# =============================================================================
# Build Stage
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

# Build arguments
ARG BUILD_DATE
ARG VERSION="1.0.0"
ARG VCS_REF

# Metadata
LABEL org.opencontainers.image.title="LXC Autoscaler" \
      org.opencontainers.image.description="Production-ready LXC container autoscaler for Proxmox VE" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/MatrixMagician/lxc-autoscaler" \
      org.opencontainers.image.licenses="MIT"

# Set build environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create build user
RUN useradd --create-home --shell /bin/bash --user-group --uid 1000 builder
USER builder
WORKDIR /home/builder

# Install pip and build tools
RUN python -m pip install --user --upgrade pip setuptools wheel

# Copy dependency files
COPY --chown=builder:builder pyproject.toml ./

# Copy source code first
COPY --chown=builder:builder . .

# Install dependencies and build wheels for all dependencies
RUN python -m pip wheel --wheel-dir wheels .

# =============================================================================
# Production Runtime Stage
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Build arguments for metadata
ARG BUILD_DATE
ARG VERSION="1.0.0"
ARG VCS_REF

# Metadata
LABEL org.opencontainers.image.title="LXC Autoscaler" \
      org.opencontainers.image.description="Production-ready LXC container autoscaler for Proxmox VE" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/MatrixMagician/lxc-autoscaler" \
      org.opencontainers.image.licenses="MIT"

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Application environment
    LXC_AUTOSCALER_CONFIG_PATH=/app/config/config.yaml \
    LXC_AUTOSCALER_LOG_LEVEL=INFO \
    LXC_AUTOSCALER_PID_FILE=/app/run/lxc-autoscaler.pid \
    LXC_AUTOSCALER_LOG_FILE=/app/logs/lxc-autoscaler.log

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove

# Create non-root application user and group
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

# Create application directories with proper permissions
RUN mkdir -p /app/config /app/logs /app/run /app/data && \
    chown -R appuser:appuser /app

# Switch to application user
USER appuser
WORKDIR /app

# Copy wheels from builder stage and install
COPY --from=builder --chown=appuser:appuser /home/builder/wheels /tmp/wheels
RUN python -m pip install --user --no-index --find-links /tmp/wheels lxc-autoscaler && \
    rm -rf /tmp/wheels

# Add user Python bin to PATH
ENV PATH="/home/appuser/.local/bin:$PATH"

# Create example configuration
COPY --chown=appuser:appuser examples/config.yaml /app/config/config.yaml.example
COPY --chown=appuser:appuser examples/minimal-config.yaml /app/config/minimal-config.yaml.example
COPY --chown=appuser:appuser examples/production-config.yaml /app/config/production-config.yaml.example

# Create entrypoint script
RUN cat > /app/entrypoint.sh << 'EOF' && chmod +x /app/entrypoint.sh
#!/bin/bash
set -e

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Check if configuration exists
if [ ! -f "${LXC_AUTOSCALER_CONFIG_PATH}" ]; then
    log "ERROR: Configuration file not found at ${LXC_AUTOSCALER_CONFIG_PATH}"
    log "Please mount your configuration file to /app/config/config.yaml"
    log "Example: docker run -v /path/to/config.yaml:/app/config/config.yaml lxc_autoscaler"
    exit 1
fi

# Validate configuration if requested
if [ "$1" = "--validate-config" ]; then
    log "Validating configuration..."
    exec lxc-autoscaler --config "${LXC_AUTOSCALER_CONFIG_PATH}" --validate-config
fi

# Handle dry-run mode
ARGS=""
if [ "${DRY_RUN:-false}" = "true" ]; then
    ARGS="--dry-run"
    log "Running in dry-run mode - no actual scaling operations will be performed"
fi

# Start the daemon
log "Starting LXC Autoscaler daemon..."
log "Configuration: ${LXC_AUTOSCALER_CONFIG_PATH}"
log "Log level: ${LXC_AUTOSCALER_LOG_LEVEL}"
log "PID file: ${LXC_AUTOSCALER_PID_FILE}"
log "Log file: ${LXC_AUTOSCALER_LOG_FILE}"

exec lxc-autoscaler --config "${LXC_AUTOSCALER_CONFIG_PATH}" $ARGS "$@"
EOF

# Create health check script
RUN cat > /app/health_check.py << 'EOF'
import sys
import os
from pathlib import Path

# Check if PID file exists and process is running
pid_file = Path(os.environ.get('LXC_AUTOSCALER_PID_FILE', '/app/run/lxc-autoscaler.pid'))
if not pid_file.exists():
    print('PID file not found', file=sys.stderr)
    sys.exit(1)

try:
    pid = int(pid_file.read_text().strip())
    os.kill(pid, 0)  # Check if process exists
    print('Daemon is running')
    sys.exit(0)
except (ValueError, OSError, ProcessLookupError):
    print('Daemon process not found or not responding', file=sys.stderr)
    sys.exit(1)
EOF

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/health_check.py || exit 1

# Expose ports (none needed for this daemon)
# EXPOSE 8080

# Set volumes for configuration, logs, and runtime data
VOLUME ["/app/config", "/app/logs", "/app/data"]

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]

# Default command
CMD []

# Security and compliance
USER appuser:appuser
WORKDIR /app

# Final metadata
LABEL org.opencontainers.image.documentation="https://lxc-autoscaler.readthedocs.io/" \
      org.opencontainers.image.authors="Oliver H <support@example.com>" \
      org.opencontainers.image.url="https://github.com/MatrixMagician/lxc-autoscaler" \
      org.opencontainers.image.vendor="LXC Autoscaler Project"