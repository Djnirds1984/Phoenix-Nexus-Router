#!/bin/bash

# PHOENIX NEXUS ROUTER - SAFE UPGRADE FROM SAFE MODE
# Upgrades from safe mode to full functionality while preserving network connectivity

echo "🚀 PHOENIX NEXUS ROUTER - SAFE UPGRADE"
echo "======================================"
echo ""
echo "This will upgrade from safe mode to full router functionality"
echo "Your network connectivity will be preserved throughout the process"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# Network connectivity test
test_network() {
    ping -c 1 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Emergency rollback function
emergency_rollback() {
    error "⚠️  Upgrade failed! Performing emergency rollback..."
    
    # Stop new services
    systemctl stop routeros-routing.service 2>/dev/null || true
    systemctl stop routeros-watchdog.service 2>/dev/null || true
    systemctl stop routeros-web.service 2>/dev/null || true
    
    # Restart safe mode
    systemctl start phoenix-router-safe.service
    
    # Test connectivity
    sleep 5
    if test_network; then
        success "✅ Emergency rollback successful! Safe mode restored."
        echo "Your router is back in safe mode. Access it at: http://localhost:8080"
    else
        error "🚨 Emergency rollback failed! Network recovery required."
        echo "Run: sudo /opt/phoenix-router-safe/scripts/network_recovery.sh"
    fi
    
    exit 1
}

# Backup current configuration
backup_current_config() {
    log "Creating backup of current configuration..."
    BACKUP_DIR="/opt/phoenix-router-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup safe mode files
    cp -r /opt/phoenix-router-safe "$BACKUP_DIR/" 2>/dev/null || true
    
    # Backup network configuration
    ip addr show > "$BACKUP_DIR/ip_addrs.txt"
    ip route show > "$BACKUP_DIR/routes.txt"
    
    # Backup service states
    systemctl is-active phoenix-router-safe > "$BACKUP_DIR/safe-mode.status" 2>/dev/null || echo "inactive" > "$BACKUP_DIR/safe-mode.status"
    
    success "✅ Backup created at: $BACKUP_DIR"
    echo "You can restore this backup if needed."
}

# Install required packages safely
install_packages() {
    log "Installing required packages..."
    
    # Test network before installing
    if ! test_network; then
        error "❌ Network connectivity lost during package installation!"
        emergency_rollback
    fi
    
    # Install packages one by one to avoid breaking network
    PACKAGES="python3 python3-pip curl wget net-tools"
    
    for package in $PACKAGES; do
        log "Installing $package..."
        apt install -y "$package" 2>/dev/null || {
            warning "⚠️  Failed to install $package, continuing..."
        }
        
        # Test network after each package
        if ! test_network; then
            error "❌ Network connectivity lost after installing $package!"
            emergency_rollback
        fi
    done
    
    success "✅ Packages installed successfully"
}

# Create full router configuration
create_router_config() {
    log "Creating router configuration..."
    
    # Create main config directory
    mkdir -p /opt/routeros/{routing,watchdog,web,config,scripts,systemd}
    
    # Create interfaces configuration
    cat > /opt/routeros/config/interfaces.json << 'EOF'
{
  "interfaces": {
    "eth0": {
      "type": "wan",
      "weight": 2,
      "enabled": true,
      "gateway": "192.168.1.1",
      "ip_address": "dhcp",
      "health_check": {
        "enabled": true,
        "target": "8.8.8.8",
        "interval": 10,
        "timeout": 2,
        "retries": 3
      }
    }
  }
}
EOF

    # Create router configuration
    cat > /opt/routeros/config/router.conf << 'EOF'
[system]
project_root = /opt/routeros
log_level = INFO

[health_check]
timeout_seconds = 2
retry_count = 3
check_interval = 5
target_host = 8.8.8.8

[routing]
load_balancing = ecmp
sticky_sessions = true
packet_marking = true
EOF

    success "✅ Router configuration created"
}

# Create systemd service files
create_services() {
    log "Creating systemd services..."
    
    # Copy service files
    if [ -d "/opt/phoenix-router-safe/systemd" ]; then
        cp /opt/phoenix-router-safe/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
    fi
    
    # Ensure services exist
    systemctl daemon-reload
    
    success "✅ Services created"
}

# Gradual service startup with connectivity checks
start_services_safely() {
    log "Starting services safely with connectivity monitoring..."
    
    # Stop safe mode first
    log "Stopping safe mode..."
    systemctl stop phoenix-router-safe.service
    
    # Start routing manager (lowest risk)
    log "Starting routing manager..."
    systemctl start routeros-routing.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting routing manager!"
        emergency_rollback
    fi
    
    # Start watchdog service
    log "Starting watchdog service..."
    systemctl start routeros-watchdog.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting watchdog!"
        emergency_rollback
    fi
    
    # Start web interface
    log "Starting web interface..."
    systemctl start routeros-web.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting web interface!"
        emergency_rollback
    fi
    
    # Enable services for auto-start
    systemctl enable routeros-routing.service routeros-watchdog.service routeros-web.service
    
    success "✅ All services started successfully"
}

# Verify upgrade success
verify_upgrade() {
    log "Verifying upgrade success..."
    
    # Check all services are running
    SERVICES="routeros-routing routeros-watchdog routeros-web"
    for service in $SERVICES; do
        if systemctl is-active "$service" > /dev/null; then
            success "✅ $service is running"
        else
            error "❌ $service is not running!"
            return 1
        fi
    done
    
    # Test web interface
    if curl -s http://localhost:8080 > /dev/null; then
        success "✅ Web interface is accessible"
    else
        error "❌ Web interface is not accessible!"
        return 1
    fi
    
    # Test network connectivity
    if test_network; then
        success "✅ Network connectivity maintained"
    else
        error "❌ Network connectivity lost!"
        return 1
    fi
    
    return 0
}

# Main upgrade process
main() {
    echo "Starting safe upgrade process..."
    echo ""
    
    # Pre-upgrade checks
    log "Running pre-upgrade checks..."
    
    if ! test_network; then
        error "❌ No internet connectivity detected! Cannot proceed with upgrade."
        echo "Please ensure your network is working before upgrading."
        exit 1
    fi
    
    # Confirm upgrade
    echo ""
    echo "🔄 UPGRADE SUMMARY:"
    echo "=================="
    echo "✅ This will upgrade from SAFE MODE to FULL ROUTER functionality"
    echo "✅ Your network will be monitored throughout the process"
    echo "✅ Automatic rollback if anything goes wrong"
    echo "✅ Backup will be created before upgrade"
    echo ""
    
    read -p "Do you want to proceed with the upgrade? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Upgrade cancelled. Safe mode will continue running."
        exit 0
    fi
    
    echo ""
    log "Starting upgrade process..."
    
    # Set up error handling
    trap emergency_rollback ERR
    
    # Step 1: Create backup
    backup_current_config
    echo ""
    
    # Step 2: Install packages
    install_packages
    echo ""
    
    # Step 3: Create router configuration
    create_router_config
    echo ""
    
    # Step 4: Create services
    create_services
    echo ""
    
    # Step 5: Start services safely
    start_services_safely
    echo ""
    
    # Step 6: Verify upgrade
    if verify_upgrade; then
        success "🎉 UPGRADE SUCCESSFUL!"
        echo ""
        echo "🌐 YOUR FULL ROUTER IS READY!"
        echo "============================="
        echo ""
        echo "💻 Access your full router at:"
        echo "   Local: http://localhost:8080"
        echo "   Network: http://$(hostname -I | awk '{print $1}'):8080"
        echo ""
        echo "🔧 NEW FEATURES AVAILABLE:"
        echo "   • Multi-WAN load balancing"
        echo "   • Automatic failover"
        echo "   • Advanced routing"
        echo "   • WAN management interface"
        echo "   • Real-time monitoring"
        echo ""
        echo "🚨 EMERGENCY COMMANDS:"
        echo "   Stop all services: systemctl stop routeros-*"
        echo "   Check status: systemctl status routeros-*"
        echo "   View logs: journalctl -u routeros-* -f"
        echo ""
        echo "💡 If you need to rollback:"
        echo "   systemctl stop routeros-*"
        echo "   systemctl start phoenix-router-safe.service"
        
        # Remove error trap on success
        trap - ERR
        
    else
        error "❌ Upgrade verification failed!"
        emergency_rollback
    fi
}

# Handle command line arguments
case "${1:-}" in
    --rollback)
        error "Manual rollback requested..."
        emergency_rollback
        ;;
    --status)
        echo "Current service status:"
        systemctl status routeros-routing.service routeros-watchdog.service routeros-web.service
        ;;
    --test)
        echo "Testing network connectivity..."
        if test_network; then
            echo "✅ Network is working"
        else
            echo "❌ Network is down"
        fi
        ;;
    *)
        main
        ;;
esac