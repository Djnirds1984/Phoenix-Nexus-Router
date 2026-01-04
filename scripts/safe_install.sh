#!/bin/bash

# Safe Installation Script for Phoenix Nexus Router
# Preserves existing network connectivity and prevents SSH access loss

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/tmp/phoenix-router-backup-$(date +%Y%m%d-%H%M%S)"
LOG_FILE="/tmp/phoenix-router-install.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
        exit 1
    fi
}

# Backup current network configuration
backup_network_config() {
    log "Creating backup of current network configuration..."
    mkdir -p "$BACKUP_DIR"
    
    # Backup network interfaces
    cp /etc/network/interfaces "$BACKUP_DIR/" 2>/dev/null || true
    cp -r /etc/netplan "$BACKUP_DIR/" 2>/dev/null || true
    
    # Backup current routing table
    ip route show > "$BACKUP_DIR/routes.txt"
    ip rule show > "$BACKUP_DIR/rules.txt"
    
    # Backup current network services status
    systemctl is-active NetworkManager > "$BACKUP_DIR/networkmanager.status" 2>/dev/null || echo "inactive" > "$BACKUP_DIR/networkmanager.status"
    systemctl is-active systemd-networkd > "$BACKUP_DIR/systemd-networkd.status" 2>/dev/null || echo "inactive" > "$BACKUP_DIR/systemd-networkd.status"
    
    # Backup SSH configuration
    cp /etc/ssh/sshd_config "$BACKUP_DIR/" 2>/dev/null || true
    
    # Get current IP addresses
    ip addr show > "$BACKUP_DIR/ip_addrs.txt"
    
    success "Network configuration backed up to $BACKUP_DIR"
}

# Test network connectivity
test_connectivity() {
    local test_host="8.8.8.8"
    local test_count=3
    
    log "Testing network connectivity to $test_host..."
    
    if ping -c $test_count "$test_host" > /dev/null 2>&1; then
        success "Network connectivity is working"
        return 0
    else
        error "Network connectivity test failed"
        return 1
    fi
}

# Get current active interfaces
get_active_interfaces() {
    ip link show | grep -E '^[0-9]+:' | awk '{print $2}' | sed 's/://g' | grep -v lo
}

# Get current default gateway
get_default_gateway() {
    ip route show default | awk '{print $3}' | head -n1
}

# Interactive network configuration wizard
network_wizard() {
    log "Starting network configuration wizard..."
    
    echo -e "\n${YELLOW}=== Phoenix Nexus Router Network Configuration Wizard ===${NC}"
    echo "This wizard will help you safely configure WAN interfaces."
    echo "Your current SSH connection will be preserved."
    echo ""
    
    # Show current network status
    echo -e "${BLUE}Current Network Status:${NC}"
    echo "Active Interfaces:"
    get_active_interfaces | while read iface; do
        local ip=$(ip addr show "$iface" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
        local gateway=$(ip route show dev "$iface" | grep default | awk '{print $3}' | head -n1)
        echo "  $iface: IP=$ip, Gateway=$gateway"
    done
    echo ""
    
    # Test current connectivity
    if test_connectivity; then
        echo -e "${GREEN}✓ Current network connectivity is working${NC}"
    else
        echo -e "${RED}✗ Current network connectivity is broken${NC}"
        echo "Please fix your network before proceeding."
        return 1
    fi
    echo ""
    
    # Ask user about configuration mode
    echo -e "${YELLOW}Configuration Mode:${NC}"
    echo "1) Automatic - Detect and configure primary WAN automatically"
    echo "2) Manual - Manually specify WAN interfaces"
    echo "3) Skip - Keep current network configuration"
    echo ""
    
    read -p "Select configuration mode (1-3): " mode
    
    case $mode in
        1)
            configure_automatic_wan
            ;;
        2)
            configure_manual_wan
            ;;
        3)
            log "Skipping network configuration. Current settings will be preserved."
            ;;
        *)
            error "Invalid option selected"
            return 1
            ;;
    esac
}

# Automatic WAN configuration
configure_automatic_wan() {
    log "Detecting primary WAN interface automatically..."
    
    # Find interface with default route
    local default_iface=$(ip route show default | awk '{print $5}' | head -n1)
    
    if [[ -n "$default_iface" ]]; then
        echo -e "${GREEN}Detected primary WAN interface: $default_iface${NC}"
        
        # Get interface details
        local ip=$(ip addr show "$default_iface" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
        local gateway=$(ip route show dev "$default_iface" | grep default | awk '{print $3}' | head -n1)
        
        echo "Interface: $default_iface"
        echo "IP Address: $ip"
        echo "Gateway: $gateway"
        echo ""
        
        read -p "Use this as primary WAN? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            # Create initial configuration
            create_initial_config "$default_iface" "$ip" "$gateway"
        else
            log "Automatic configuration cancelled"
        fi
    else
        error "Could not detect primary WAN interface"
        return 1
    fi
}

# Manual WAN configuration
configure_manual_wan() {
    log "Manual WAN configuration selected..."
    
    echo -e "\n${YELLOW}Available Network Interfaces:${NC}"
    get_active_interfaces | nl
    echo ""
    
    read -p "Enter the number of your primary WAN interface: " iface_num
    local selected_iface=$(get_active_interfaces | sed -n "${iface_num}p")
    
    if [[ -z "$selected_iface" ]]; then
        error "Invalid interface selection"
        return 1
    fi
    
    echo -e "${GREEN}Selected interface: $selected_iface${NC}"
    
    # Get current IP (if any)
    local current_ip=$(ip addr show "$selected_iface" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
    if [[ -n "$current_ip" ]]; then
        echo "Current IP: $current_ip"
        read -p "Keep this IP address? (Y/n): " keep_ip
        if [[ "$keep_ip" =~ ^[Nn]$ ]]; then
            read -p "Enter new IP address (with CIDR, e.g., 192.168.1.100/24): " new_ip
            current_ip="$new_ip"
        fi
    else
        read -p "Enter IP address (with CIDR, e.g., 192.168.1.100/24): " current_ip
    fi
    
    # Get gateway
    read -p "Enter gateway IP address: " gateway
    
    echo ""
    echo "Configuration Summary:"
    echo "Interface: $selected_iface"
    echo "IP Address: $current_ip"
    echo "Gateway: $gateway"
    echo ""
    
    read -p "Proceed with this configuration? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        create_initial_config "$selected_iface" "$current_ip" "$gateway"
    else
        log "Manual configuration cancelled"
    fi
}

# Create initial configuration
create_initial_config() {
    local iface="$1"
    local ip="$2"
    local gateway="$3"
    
    log "Creating initial router configuration..."
    
    # Create configuration directory
    mkdir -p "$PROJECT_ROOT/config"
    
    # Create main configuration file
    cat > "$PROJECT_ROOT/config/router.conf" << EOF
# Phoenix Nexus Router Configuration
# Generated on $(date)

[primary_wan]
interface = $iface
ip_address = $ip
gateway = $gateway

[system]
project_root = $PROJECT_ROOT
backup_directory = $BACKUP_DIR
log_level = INFO
EOF
    
    # Create interface configuration
    cat > "$PROJECT_ROOT/config/interfaces.json" << EOF
{
    "interfaces": {
        "$iface": {
            "type": "wan",
            "ip_address": "$ip",
            "gateway": "$gateway",
            "weight": 1,
            "enabled": true,
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
    
    success "Initial configuration created"
    log "Configuration files created in $PROJECT_ROOT/config/"
}

# Safe service installation
install_services_safely() {
    log "Installing services safely..."
    
    # Check if we can still connect
    if ! test_connectivity; then
        error "Network connectivity lost. Stopping installation."
        restore_network_config
        return 1
    fi
    
    # Install Python dependencies first (safest)
    log "Installing Python dependencies..."
    apt update
    apt install -y python3 python3-pip python3-venv sqlite3 curl wget net-tools
    
    # Create Python virtual environment
    python3 -m venv "$PROJECT_ROOT/venv"
    source "$PROJECT_ROOT/venv/bin/activate"
    
    # Install Python packages
    pip install flask requests psutil netifaces
    
    # Copy systemd service files (but don't enable yet)
    log "Copying systemd service files..."
    cp "$PROJECT_ROOT/systemd/routeros-"*.service /etc/systemd/system/ 2>/dev/null || true
    
    # Reload systemd to recognize new services
    systemctl daemon-reload
    
    # Create safe startup script
    cat > "$PROJECT_ROOT/start_router.sh" << 'EOF'
#!/bin/bash
# Safe router startup script

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Test connectivity before starting
echo "Testing network connectivity..."
if ! ping -c 3 8.8.8.8 > /dev/null 2>&1; then
    echo "ERROR: Network connectivity test failed!"
    echo "Please check your network configuration before starting the router."
    exit 1
fi

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Start services safely
echo "Starting Phoenix Nexus Router services..."

# Start routing manager first (dependency for watchdog)
if systemctl list-unit-files | grep -q routeros-routing.service; then
    systemctl start routeros-routing.service
    echo "✓ Routing manager started"
fi

# Start watchdog service
if systemctl list-unit-files | grep -q routeros-watchdog.service; then
    systemctl start routeros-watchdog.service
    echo "✓ Watchdog service started"
fi

# Start web interface
if systemctl list-unit-files | grep -q routeros-web.service; then
    systemctl start routeros-web.service
    echo "✓ Web interface started"
fi

echo "Router services started successfully!"
echo "Web interface should be available at: http://$(hostname -I | awk '{print $1}'):8080"
EOF
    
    chmod +x "$PROJECT_ROOT/start_router.sh"
    
    success "Services installed safely"
}

# Restore network configuration
restore_network_config() {
    log "Restoring network configuration..."
    
    if [[ -d "$BACKUP_DIR" ]]; then
        # Restore network files
        cp "$BACKUP_DIR/interfaces" /etc/network/ 2>/dev/null || true
        cp -r "$BACKUP_DIR/netplan" /etc/ 2>/dev/null || true
        
        # Restore service states
        local nm_status=$(cat "$BACKUP_DIR/networkmanager.status" 2>/dev/null || echo "inactive")
        local netd_status=$(cat "$BACKUP_DIR/systemd-networkd.status" 2>/dev/null || echo "inactive")
        
        if [[ "$nm_status" == "active" ]]; then
            systemctl start NetworkManager
        fi
        
        if [[ "$netd_status" == "active" ]]; then
            systemctl start systemd-networkd
        fi
        
        success "Network configuration restored from backup"
    else
        warning "No backup found to restore"
    fi
}

# Rollback function
rollback() {
    error "Installation failed. Performing rollback..."
    restore_network_config
    
    # Stop any started services
    systemctl stop routeros-watchdog.service 2>/dev/null || true
    systemctl stop routeros-web.service 2>/dev/null || true
    systemctl stop routeros-routing.service 2>/dev/null || true
    
    # Disable services
    systemctl disable routeros-watchdog.service 2>/dev/null || true
    systemctl disable routeros-web.service 2>/dev/null || true
    systemctl disable routeros-routing.service 2>/dev/null || true
    
    error "Rollback completed. Network should be restored."
    exit 1
}

# Main installation function
main() {
    log "Starting Phoenix Nexus Router Safe Installation"
    log "This installation will preserve your existing network connectivity"
    
    # Set up error handling
    trap rollback ERR
    
    # Check prerequisites
    check_root
    
    # Create backup
    backup_network_config
    
    # Test initial connectivity
    if ! test_connectivity; then
        error "Initial network connectivity test failed. Please check your network before proceeding."
        exit 1
    fi
    
    # Run network configuration wizard
    if ! network_wizard; then
        error "Network configuration wizard failed"
        rollback
        exit 1
    fi
    
    # Install services safely
    install_services_safely
    
    # Final connectivity test
    if ! test_connectivity; then
        error "Final connectivity test failed after installation"
        rollback
        exit 1
    fi
    
    # Success message
    success "Phoenix Nexus Router installed successfully!"
    echo ""
    echo -e "${GREEN}=== Installation Complete ===${NC}"
    echo "Your network connectivity has been preserved."
    echo ""
    echo "Next steps:"
    echo "1. Review the configuration in $PROJECT_ROOT/config/"
    echo "2. Start the router with: $PROJECT_ROOT/start_router.sh"
    echo "3. Access the web interface at: http://$(hostname -I | awk '{print $1}'):8080"
    echo "4. Add additional WAN interfaces through the web interface"
    echo ""
    echo "If you encounter issues, your network backup is stored at: $BACKUP_DIR"
    echo "You can restore it with: $0 --restore"
    
    # Remove error trap on successful completion
    trap - ERR
}

# Handle command line arguments
case "${1:-}" in
    --restore)
        restore_network_config
        ;;
    --test)
        test_connectivity
        ;;
    --wizard)
        check_root
        backup_network_config
        network_wizard
        ;;
    *)
        main
        ;;
esac