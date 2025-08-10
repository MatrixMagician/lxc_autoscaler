#!/bin/bash

# LXC Autoscaler Installation Script
# This script installs the LXC Autoscaler service on Proxmox VE hosts

set -e  # Exit on any error
set -u  # Exit on undefined variables

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/usr/local/lib/python3/dist-packages/lxc_autoscaler"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="/etc/lxc-autoscaler"
LOG_DIR="/var/log/lxc-autoscaler"
LIB_DIR="/var/lib/lxc-autoscaler"
SYSTEMD_DIR="/etc/systemd/system"
TMPFILES_DIR="/etc/tmpfiles.d"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

# Function to detect OS and install Python dependencies
install_dependencies() {
    print_status "Installing system dependencies..."
    
    # Detect OS
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        apt-get update
        apt-get install -y python3 python3-pip python3-venv python3-dev build-essential
    elif [ -f /etc/redhat-release ]; then
        # RHEL/CentOS/Fedora
        if command -v dnf &> /dev/null; then
            dnf install -y python3 python3-pip python3-devel gcc
        else
            yum install -y python3 python3-pip python3-devel gcc
        fi
    else
        print_error "Unsupported operating system"
        exit 1
    fi
    
    print_status "System dependencies installed"
}

# Function to install Python packages
install_python_packages() {
    print_status "Installing Python packages..."
    
    pip3 install --upgrade pip
    pip3 install -r requirements.txt
    
    print_status "Python packages installed"
}

# Function to create directories
create_directories() {
    print_status "Creating directories..."
    
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$LIB_DIR"
    
    # Set permissions
    chown root:root "$CONFIG_DIR"
    chmod 750 "$CONFIG_DIR"
    
    chown root:root "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    
    chown root:root "$LIB_DIR"
    chmod 755 "$LIB_DIR"
    
    print_status "Directories created"
}

# Function to install Python package
install_package() {
    print_status "Installing LXC Autoscaler package..."
    
    # Copy package files
    cp -r lxc_autoscaler/* "$INSTALL_DIR/"
    
    # Set ownership and permissions
    chown -R root:root "$INSTALL_DIR"
    chmod -R 644 "$INSTALL_DIR"
    find "$INSTALL_DIR" -name "*.py" -exec chmod 644 {} \;
    
    print_status "Package installed"
}

# Function to install executables
install_executables() {
    print_status "Installing executables..."
    
    # Create main executable
    cat > "$BIN_DIR/lxc-autoscaler" << 'EOF'
#!/usr/bin/env python3
import sys
import asyncio
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')
from lxc_autoscaler.core.daemon import main

if __name__ == '__main__':
    asyncio.run(main())
EOF
    
    # Create health check executable
    cat > "$BIN_DIR/lxc-autoscaler-healthcheck" << 'EOF'
#!/usr/bin/env python3
import sys
import requests
import json

def check_service_health():
    """Check if the service is running and healthy."""
    try:
        # Check if systemd service is active
        import subprocess
        result = subprocess.run(
            ['systemctl', 'is-active', 'lxc-autoscaler'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip() == 'active':
            print("Service is active and running")
            return True
        else:
            print("Service is not active")
            return False
            
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

if __name__ == '__main__':
    if check_service_health():
        sys.exit(0)
    else:
        sys.exit(1)
EOF
    
    # Create status check executable
    cat > "$BIN_DIR/lxc-autoscaler-status" << 'EOF'
#!/usr/bin/env python3
import sys
import subprocess
import json

def get_service_status():
    """Get detailed service status."""
    try:
        # Get systemd status
        result = subprocess.run(
            ['systemctl', 'status', 'lxc-autoscaler'],
            capture_output=True,
            text=True
        )
        
        print("=== Systemd Status ===")
        print(result.stdout)
        
        # Get recent logs
        log_result = subprocess.run(
            ['journalctl', '-u', 'lxc-autoscaler', '--lines=20', '--no-pager'],
            capture_output=True,
            text=True
        )
        
        print("\n=== Recent Logs ===")
        print(log_result.stdout)
        
    except Exception as e:
        print(f"Failed to get status: {e}")
        sys.exit(1)

if __name__ == '__main__':
    get_service_status()
EOF
    
    # Make executables
    chmod 755 "$BIN_DIR/lxc-autoscaler"
    chmod 755 "$BIN_DIR/lxc-autoscaler-healthcheck"
    chmod 755 "$BIN_DIR/lxc-autoscaler-status"
    
    print_status "Executables installed"
}

# Function to install systemd files
install_systemd_files() {
    print_status "Installing systemd service files..."
    
    # Copy service files
    cp systemd/lxc-autoscaler.service "$SYSTEMD_DIR/"
    cp systemd/lxc-autoscaler-healthcheck.service "$SYSTEMD_DIR/"
    cp systemd/lxc-autoscaler.timer "$SYSTEMD_DIR/"
    
    # Copy tmpfiles configuration
    cp systemd/tmpfiles.d/lxc-autoscaler.conf "$TMPFILES_DIR/"
    
    # Set permissions
    chmod 644 "$SYSTEMD_DIR/lxc-autoscaler.service"
    chmod 644 "$SYSTEMD_DIR/lxc-autoscaler-healthcheck.service"
    chmod 644 "$SYSTEMD_DIR/lxc-autoscaler.timer"
    chmod 644 "$TMPFILES_DIR/lxc-autoscaler.conf"
    
    # Create runtime directories
    systemd-tmpfiles --create /etc/tmpfiles.d/lxc-autoscaler.conf
    
    # Reload systemd
    systemctl daemon-reload
    
    print_status "Systemd files installed"
}

# Function to install default configuration
install_default_config() {
    if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
        print_status "Installing default configuration..."
        
        if [ -f "examples/config.yaml" ]; then
            cp examples/config.yaml "$CONFIG_DIR/config.yaml"
            chown root:root "$CONFIG_DIR/config.yaml"
            chmod 640 "$CONFIG_DIR/config.yaml"
            
            print_warning "Default configuration installed at $CONFIG_DIR/config.yaml"
            print_warning "Please edit this file with your Proxmox settings before starting the service"
        else
            print_warning "No example configuration found. You'll need to create $CONFIG_DIR/config.yaml manually"
        fi
    else
        print_status "Configuration file already exists, skipping"
    fi
}

# Function to setup logrotate
setup_logrotate() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/lxc-autoscaler << 'EOF'
/var/log/lxc-autoscaler/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    create 644 root root
}
EOF
    
    print_status "Log rotation configured"
}

# Function to enable and start service
enable_service() {
    print_status "Enabling systemd service..."
    
    systemctl enable lxc-autoscaler.service
    systemctl enable lxc-autoscaler.timer
    
    print_status "Service enabled (not started yet)"
    print_warning "Edit $CONFIG_DIR/config.yaml before starting the service"
}

# Function to show post-installation information
show_post_install_info() {
    print_status "Installation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Edit the configuration file: $CONFIG_DIR/config.yaml"
    echo "2. Test the configuration: lxc-autoscaler --validate-config"
    echo "3. Start the service: systemctl start lxc-autoscaler"
    echo "4. Check service status: systemctl status lxc-autoscaler"
    echo "5. View logs: journalctl -u lxc-autoscaler -f"
    echo
    echo "Available commands:"
    echo "  lxc-autoscaler --help              Show help"
    echo "  lxc-autoscaler --validate-config   Validate configuration"
    echo "  lxc-autoscaler --dry-run          Run without making changes"
    echo "  lxc-autoscaler-status             Show detailed status"
    echo "  lxc-autoscaler-healthcheck        Perform health check"
    echo
    echo "Configuration file: $CONFIG_DIR/config.yaml"
    echo "Log file: /var/log/lxc-autoscaler.log"
}

# Main installation function
main() {
    print_status "Starting LXC Autoscaler installation..."
    
    check_root
    install_dependencies
    create_directories
    install_python_packages
    install_package
    install_executables
    install_systemd_files
    install_default_config
    setup_logrotate
    enable_service
    show_post_install_info
}

# Check if script is being run directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi