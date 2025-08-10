#!/bin/bash

# LXC Autoscaler Uninstallation Script
# This script removes the LXC Autoscaler service from Proxmox VE hosts

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

# Function to confirm uninstallation
confirm_uninstall() {
    echo
    print_warning "This will completely remove LXC Autoscaler from your system."
    print_warning "Configuration files and logs will also be removed."
    echo
    read -p "Are you sure you want to continue? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Uninstallation cancelled"
        exit 0
    fi
}

# Function to stop and disable services
stop_services() {
    print_status "Stopping and disabling services..."
    
    # Stop services
    systemctl stop lxc-autoscaler.service || true
    systemctl stop lxc-autoscaler.timer || true
    
    # Disable services
    systemctl disable lxc-autoscaler.service || true
    systemctl disable lxc-autoscaler.timer || true
    
    print_status "Services stopped and disabled"
}

# Function to remove systemd files
remove_systemd_files() {
    print_status "Removing systemd files..."
    
    # Remove service files
    rm -f "$SYSTEMD_DIR/lxc-autoscaler.service"
    rm -f "$SYSTEMD_DIR/lxc-autoscaler-healthcheck.service"
    rm -f "$SYSTEMD_DIR/lxc-autoscaler.timer"
    
    # Remove tmpfiles configuration
    rm -f "$TMPFILES_DIR/lxc-autoscaler.conf"
    
    # Reload systemd
    systemctl daemon-reload
    
    print_status "Systemd files removed"
}

# Function to remove executables
remove_executables() {
    print_status "Removing executables..."
    
    rm -f "$BIN_DIR/lxc-autoscaler"
    rm -f "$BIN_DIR/lxc-autoscaler-healthcheck"
    rm -f "$BIN_DIR/lxc-autoscaler-status"
    
    print_status "Executables removed"
}

# Function to remove package files
remove_package() {
    print_status "Removing package files..."
    
    rm -rf "$INSTALL_DIR"
    
    print_status "Package files removed"
}

# Function to remove directories and files
remove_directories() {
    print_status "Removing directories..."
    
    # Ask about configuration
    if [ -d "$CONFIG_DIR" ]; then
        echo
        read -p "Remove configuration directory $CONFIG_DIR? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$CONFIG_DIR"
            print_status "Configuration directory removed"
        else
            print_warning "Configuration directory preserved"
        fi
    fi
    
    # Ask about logs
    if [ -d "$LOG_DIR" ]; then
        echo
        read -p "Remove log directory $LOG_DIR? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$LOG_DIR"
            print_status "Log directory removed"
        else
            print_warning "Log directory preserved"
        fi
    fi
    
    # Remove lib directory
    rm -rf "$LIB_DIR" || true
    
    print_status "Directories cleaned up"
}

# Function to remove logrotate configuration
remove_logrotate() {
    print_status "Removing logrotate configuration..."
    
    rm -f /etc/logrotate.d/lxc-autoscaler
    
    print_status "Logrotate configuration removed"
}

# Function to remove Python packages (optional)
remove_python_packages() {
    echo
    read -p "Remove Python packages installed for LXC Autoscaler? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Removing Python packages..."
        
        # List of packages to remove (be careful not to remove system packages)
        packages="proxmoxer aiohttp pyyaml"
        
        for package in $packages; do
            pip3 uninstall -y "$package" 2>/dev/null || true
        done
        
        print_status "Python packages removed"
    else
        print_warning "Python packages preserved"
    fi
}

# Function to show post-uninstall information
show_post_uninstall_info() {
    print_status "Uninstallation completed successfully!"
    echo
    
    if [ -d "$CONFIG_DIR" ]; then
        print_warning "Configuration preserved at: $CONFIG_DIR"
    fi
    
    if [ -d "$LOG_DIR" ]; then
        print_warning "Logs preserved at: $LOG_DIR"
    fi
    
    echo "LXC Autoscaler has been removed from your system."
}

# Main uninstallation function
main() {
    print_status "Starting LXC Autoscaler uninstallation..."
    
    check_root
    confirm_uninstall
    stop_services
    remove_systemd_files
    remove_executables
    remove_package
    remove_directories
    remove_logrotate
    remove_python_packages
    show_post_uninstall_info
}

# Check if script is being run directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi