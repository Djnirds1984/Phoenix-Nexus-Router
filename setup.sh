#!/bin/bash

# Smart Multi-WAN Router OS Setup Script
# Ubuntu 24.04 x64 Installation Script

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ROUTEROS_DIR="/opt/routeros"
SERVICE_USER="routeros"
SERVICE_GROUP="routeros"
WEB_PORT=8080
API_PORT=8081

# Logging
LOG_FILE="/var/log/routeros-setup.log"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

# Function to detect network interfaces
detect_interfaces() {
    print_status "Detecting network interfaces..."
    
    # Get all network interfaces
    INTERFACES=$(ip link show | grep -E '^[0-9]+:' | awk '{print $2}' | sed 's/://g' | grep -v lo)
    
    print_status "Available interfaces:"
    for iface in $INTERFACES; do
        print_status "  - $iface"
    done
    
    # Auto-detect WAN interfaces (usually eth0, eth1)
    WAN_INTERFACES=$(echo "$INTERFACES" | grep -E '^(eth|enp|ens)' | head -2)
    
    if [[ -n "$WAN_INTERFACES" ]]; then
        print_status "Auto-detected WAN interfaces:"
        for iface in $WAN_INTERFACES; do
            print_status "  - $iface"
        done
    else
        print_warning "Could not auto-detect WAN interfaces. Manual configuration required."
    fi
}

# Function to install system dependencies
install_dependencies() {
    print_status "Installing system dependencies..."
    
    # Update package list
    apt-get update -y
    
    # Install required packages
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        iproute2 \
        nftables \
        conntrack \
        iptables \
        net-tools \
        curl \
        wget \
        jq \
        git \
        build-essential \
        linux-headers-$(uname -r) \
        tcpdump \
        traceroute \
        mtr \
        nmap \
        ethtool \
        iftop \
        vnstat \
        htop \
        tree \
        logrotate \
        cron \
        systemd \
        python3-dev \
        python3-setuptools \
        python3-wheel
    
    # Install Python packages
    pip3 install --upgrade pip
    pip3 install -r requirements.txt
    
    print_success "Dependencies installed successfully"
}

# Function to create system user and directories
setup_system() {
    print_status "Setting up system directories and user..."
    
    # Create service user
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$ROUTEROS_DIR" "$SERVICE_USER"
        print_success "Created service user: $SERVICE_USER"
    fi
    
    # Create directories
    mkdir -p "$ROUTEROS_DIR"/{routing,watchdog,web,scripts,config,logs,systemd}
    mkdir -p /var/log/routeros
    mkdir -p /var/run/routeros
    
    # Copy files to installation directory
    cp -r routing/* "$ROUTEROS_DIR/routing/"
    cp -r watchdog/* "$ROUTEROS_DIR/watchdog/"
    cp -r web/* "$ROUTEROS_DIR/web/"
    cp -r config/* "$ROUTEROS_DIR/config/"
    cp -r systemd/* "$ROUTEROS_DIR/systemd/"
    
    # Set permissions
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$ROUTEROS_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" /var/log/routeros
    chown -R "$SERVICE_USER:$SERVICE_GROUP" /var/run/routeros
    
    # Make scripts executable
    chmod +x "$ROUTEROS_DIR"/**/*.py
    chmod +x "$ROUTEROS_DIR"/scripts/*.sh 2>/dev/null || true
    
    print_success "System directories and permissions configured"
}

# Function to configure routing tables
configure_routing_tables() {
    print_status "Configuring routing tables..."
    
    # Backup original rt_tables
    cp /etc/iproute2/rt_tables /etc/iproute2/rt_tables.backup
    
    # Add custom routing tables
    cat >> /etc/iproute2/rt_tables << EOF

# Smart Multi-WAN Router OS Tables
100	wan1
200	wan2
300	wan3
EOF
    
    print_success "Routing tables configured"
}

# Function to configure nftables
configure_nftables() {
    print_status "Configuring nftables..."
    
    # Create nftables configuration
    cat > /etc/nftables.conf << 'EOF'
#!/usr/sbin/nft -f

# Smart Multi-WAN Router OS Firewall Configuration

table inet routeros {
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow loopback
        iif "lo" accept
        
        # Allow established connections
        ct state established,related accept
        
        # Allow ICMP
        ip protocol icmp accept
        ip6 nexthdr icmpv6 accept
        
        # Allow SSH (port 22)
        tcp dport 22 accept
        
        # Allow Web Management (port 8080)
        tcp dport 8080 accept
        
        # Allow API (port 8081)
        tcp dport 8081 accept
        
        # Log and drop everything else
        log prefix "ROUTEROS-INPUT-DROP: " drop
    }
    
    chain forward {
        type filter hook forward priority 0; policy accept;
        
        # Connection tracking
        ct state established,related accept
        ct state invalid drop
        
        # Allow LAN to WAN forwarding
        iifname "eth2" accept
        
        # Log suspicious traffic
        log prefix "ROUTEROS-FORWARD: " flags all
    }
    
    chain output {
        type filter hook output priority 0; policy accept;
    }
    
    chain prerouting {
        type filter hook prerouting priority -150; policy accept;
        
        # Connection tracking and marking
        ct state new ct mark set 0x1 random mod 100
        ct state established,related ct mark set ct mark
        
        # Mark high-priority traffic
        ip dport { 5060, 5061, 5062 } ct mark set 0x10
        ip dport { 27015, 27016, 27017 } ct mark set 0x20
        ip dport { 443, 8443, 9443 } ct mark set 0x30
        
        # Apply marks to packets
        ct mark 0x10 meta mark set 0x10
        ct mark 0x20 meta mark set 0x20
        ct mark 0x30 meta mark set 0x30
    }
}
EOF
    
    # Enable and start nftables
    systemctl enable nftables
    systemctl start nftables
    
    print_success "nftables configured and started"
}

# Function to configure sysctl parameters
configure_sysctl() {
    print_status "Configuring kernel parameters..."
    
    cat >> /etc/sysctl.conf << 'EOF'

# Smart Multi-WAN Router OS Kernel Parameters

# Enable IP forwarding
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1

# Enable connection tracking
net.netfilter.nf_conntrack_max=262144
net.nf_conntrack_max=262144

# TCP optimization
net.ipv4.tcp_syncookies=1
net.ipv4.tcp_timestamps=1
net.ipv4.tcp_sack=1
net.core.netdev_max_backlog=5000

# Routing optimization
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
net.ipv4.conf.all.accept_source_route=0
net.ipv4.conf.default.accept_source_route=0

# ICMP settings
net.ipv4.icmp_echo_ignore_broadcasts=1
net.ipv4.icmp_ignore_bogus_error_responses=1

# Security settings
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.default.accept_redirects=0
net.ipv4.conf.all.secure_redirects=0
net.ipv4.conf.default.secure_redirects=0

# ARP settings
net.ipv4.conf.all.arp_ignore=1
net.ipv4.conf.all.arp_announce=2
EOF
    
    # Apply sysctl settings
    sysctl -p
    
    print_success "Kernel parameters configured"
}

# Function to install systemd services
install_services() {
    print_status "Installing systemd services..."
    
    # Install watchdog service
    cp "$ROUTEROS_DIR/systemd/routeros-watchdog.service" /etc/systemd/system/
    
    # Install web service
    cat > /etc/systemd/system/routeros-web.service << EOF
[Unit]
Description=Smart Multi-WAN Router OS Web Interface
After=network.target network-online.target routeros-watchdog.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$ROUTEROS_DIR/web
ExecStart=/usr/bin/python3 $ROUTEROS_DIR/web/app.py --host 0.0.0.0 --port $WEB_PORT
Restart=always
RestartSec=10

# Security settings
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log /opt/routeros/config /var/run
NoNewPrivileges=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=routeros-web

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable services
    systemctl enable routeros-watchdog
    systemctl enable routeros-web
    
    print_success "Systemd services installed and enabled"
}

# Function to create log rotation
setup_log_rotation() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/routeros << 'EOF'
/var/log/routeros*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 routeros routeros
    postrotate
        systemctl reload routeros-watchdog 2>/dev/null || true
        systemctl reload routeros-web 2>/dev/null || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

# Function to create network configuration helper
create_network_helper() {
    print_status "Creating network configuration helper..."
    
    cat > "$ROUTEROS_DIR/scripts/configure_network.sh" << 'EOF'
#!/bin/bash

# Network Configuration Helper for RouterOS

print_help() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --wan1-interface IFACE    Set primary WAN interface (default: eth0)"
    echo "  --wan1-gateway IP        Set primary WAN gateway"
    echo "  --wan2-interface IFACE    Set secondary WAN interface (default: eth1)"
    echo "  --wan2-gateway IP        Set secondary WAN gateway"
    echo "  --lan-interface IFACE     Set LAN interface (default: eth2)"
    echo "  --lan-network NETWORK     Set LAN network (default: 192.168.1.0/24)"
    echo "  --help                    Show this help message"
}

# Default values
WAN1_INTERFACE="eth0"
WAN1_GATEWAY=""
WAN2_INTERFACE="eth1"
WAN2_GATEWAY=""
LAN_INTERFACE="eth2"
LAN_NETWORK="192.168.1.0/24"
LAN_IP="192.168.1.1"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --wan1-interface)
            WAN1_INTERFACE="$2"
            shift 2
            ;;
        --wan1-gateway)
            WAN1_GATEWAY="$2"
            shift 2
            ;;
        --wan2-interface)
            WAN2_INTERFACE="$2"
            shift 2
            ;;
        --wan2-gateway)
            WAN2_GATEWAY="$2"
            shift 2
            ;;
        --lan-interface)
            LAN_INTERFACE="$2"
            shift 2
            ;;
        --lan-network)
            LAN_NETWORK="$2"
            shift 2
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Validate inputs
if [[ -z "$WAN1_GATEWAY" ]]; then
    echo "Error: --wan1-gateway is required"
    exit 1
fi

if [[ -z "$WAN2_GATEWAY" ]]; then
    echo "Error: --wan2-gateway is required"
    exit 1
fi

# Create interface configuration
cat > /opt/routeros/config/interfaces.json << EOF
{
  "wan_interfaces": [
    {
      "name": "$WAN1_INTERFACE",
      "gateway": "$WAN1_GATEWAY",
      "weight": 2,
      "dns": ["8.8.8.8", "8.8.4.4"],
      "description": "Primary WAN - ISP 1"
    },
    {
      "name": "$WAN2_INTERFACE",
      "gateway": "$WAN2_GATEWAY",
      "weight": 1,
      "dns": ["1.1.1.1", "1.0.0.1"],
      "description": "Secondary WAN - ISP 2"
    }
  ],
  "lan_interface": {
    "name": "$LAN_INTERFACE",
    "ip": "$LAN_IP",
    "netmask": "255.255.255.0",
    "dhcp_range": "192.168.1.100-192.168.1.200"
  },
  "management": {
    "web_port": 8080,
    "api_port": 8081,
    "enable_ssh": true,
    "enable_web": true
  }
}
EOF

echo "Network configuration created successfully!"
echo "Configuration file: /opt/routeros/config/interfaces.json"
echo ""
echo "Next steps:"
echo "1. Review the configuration file"
echo "2. Start the RouterOS services: systemctl start routeros-watchdog routeros-web"
echo "3. Access the web interface at http://$LAN_IP:8080"
EOF
    
    chmod +x "$ROUTEROS_DIR/scripts/configure_network.sh"
    
    print_success "Network configuration helper created"
}

# Function to create systemd service for web interface
install_web_service() {
    print_status "Installing web interface service..."
    
    # Create systemd service for web interface
    cat > /etc/systemd/system/routeros-web.service << EOF
[Unit]
Description=Smart Multi-WAN Router OS Web Interface
After=network.target network-online.target routeros-watchdog.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$ROUTEROS_DIR/web
ExecStart=/usr/bin/python3 $ROUTEROS_DIR/web/app.py --host 0.0.0.0 --port $WEB_PORT
Restart=always
RestartSec=10

# Security settings
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log /opt/routeros/config /var/run
NoNewPrivileges=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=routeros-web

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Web interface service configured"
}

# Function to create firewall rules
configure_firewall() {
    print_status "Configuring firewall rules..."
    
    # Create firewall configuration script
    cat > "$ROUTEROS_DIR/scripts/configure_firewall.sh" << 'EOF'
#!/bin/bash

# Configure basic firewall rules for RouterOS

echo "Configuring firewall rules..."

# Flush existing rules
nft flush ruleset

# Load RouterOS nftables configuration
nft -f /etc/nftables.conf

echo "Firewall rules applied successfully!"
EOF
    
    chmod +x "$ROUTEROS_DIR/scripts/configure_firewall.sh"
    
    print_success "Firewall configuration created"
}

# Function to create management scripts
create_management_scripts() {
    print_status "Creating management scripts..."
    
    # Status check script
    cat > "$ROUTEROS_DIR/scripts/status.sh" << 'EOF'
#!/bin/bash

# RouterOS Status Check Script

echo "=== RouterOS Status ==="
echo "Date: $(date)"
echo ""

echo "Service Status:"
systemctl status routeros-watchdog routeros-web --no-pager -l

echo ""
echo "Interface Status:"
ip addr show | grep -E '^[0-9]+:' | grep -v lo

echo ""
echo "Routing Table:"
ip route show

echo ""
echo "Connection Tracking:"
conntrack -C 2>/dev/null || echo "Connection tracking not available"

echo ""
echo "Recent Logs:"
journalctl -u routeros-watchdog -u routeros-web --no-pager -n 10
EOF
    
    chmod +x "$ROUTEROS_DIR/scripts/status.sh"
    
    # Interface control script
    cat > "$ROUTEROS_DIR/scripts/interface_control.sh" << 'EOF'
#!/bin/bash

# RouterOS Interface Control Script

INTERFACE=$1
ACTION=$2

if [[ -z "$INTERFACE" || -z "$ACTION" ]]; then
    echo "Usage: $0 <interface> <enable|disable|status>"
    exit 1
fi

case $ACTION in
    enable)
        echo "Enabling interface $INTERFACE..."
        /opt/routeros/watchdog/watchdog_service.py --interface-control "$INTERFACE" enable
        ;;
    disable)
        echo "Disabling interface $INTERFACE..."
        /opt/routeros/watchdog/watchdog_service.py --interface-control "$INTERFACE" disable
        ;;
    status)
        echo "Interface $INTERFACE status:"
        ip link show "$INTERFACE"
        ;;
    *)
        echo "Unknown action: $ACTION"
        echo "Available actions: enable, disable, status"
        exit 1
        ;;
esac
EOF
    
    chmod +x "$ROUTEROS_DIR/scripts/interface_control.sh"
    
    # Kill-switch management tool
    print_status "Installing kill-switch management tool..."
    
    # Create symlink for system-wide access
    ln -sf "$ROUTEROS_DIR/scripts/kill_switch.py" /usr/local/bin/routeros-kill-switch
    chmod +x "$ROUTEROS_DIR/scripts/kill_switch.py"
    
    print_success "Kill-switch management tool installed"
    
    print_success "Management scripts created"
}

# Function to create installation summary
create_installation_summary() {
    print_status "Creating installation summary..."
    
    cat > "$ROUTEROS_DIR/INSTALLATION_SUMMARY.md" << EOF
# Smart Multi-WAN Router OS - Installation Summary

## Installation Date
$(date)

## Installation Path
$ROUTEROS_DIR

## Services
- **Watchdog Service**: routeros-watchdog.service
- **Web Interface**: routeros-web.service

## Configuration Files
- **Interfaces**: $ROUTEROS_DIR/config/interfaces.json
- **Health Monitor**: $ROUTEROS_DIR/config/health_monitor.json
- **Connection Rules**: $ROUTEROS_DIR/config/connection_rules.json

## Web Interface
- **URL**: http://$(hostname -I | awk '{print $1}'):$WEB_PORT
- **API Port**: $API_PORT

## Management Scripts
- **Status Check**: $ROUTEROS_DIR/scripts/status.sh
- **Interface Control**: $ROUTEROS_DIR/scripts/interface_control.sh
- **Kill-Switch Tool**: $ROUTEROS_DIR/scripts/kill_switch.py or routeros-kill-switch
- **Network Config**: $ROUTEROS_DIR/scripts/configure_network.sh
- **Firewall Config**: $ROUTEROS_DIR/scripts/configure_firewall.sh

## Log Files
- **Watchdog**: /var/log/routeros-watchdog.log
- **Health**: /var/log/routeros-health.log
- **Routing**: /var/log/routeros-routing.log
- **Web**: /var/log/routeros-web.log

## Quick Start Commands

### Start Services
\`\`\`bash
systemctl start routeros-watchdog routeros-web
\`\`\`

### Check Status
\`\`\`bash
$ROUTEROS_DIR/scripts/status.sh
\`\`\`

### Configure Network
\`\`\`bash
$ROUTEROS_DIR/scripts/configure_network.sh --wan1-interface eth0 --wan1-gateway 192.168.100.1 --wan2-interface eth1 --wan2-gateway 192.168.200.1 --lan-interface eth2
\`\`\`

### View Logs
\`\`\`bash
journalctl -u routeros-watchdog -f
journalctl -u routeros-web -f
\`\`\`

## Next Steps

1. **Configure Network Interfaces**: Use the network configuration helper
2. **Access Web Interface**: Open the web dashboard
3. **Monitor System**: Check logs and status regularly
4. **Configure Firewall**: Review and customize firewall rules
5. **Set Up Monitoring**: Configure alerting if needed

## Support

For issues and support:
- Check log files for errors
- Review system status with the status script
- Access the web interface for real-time monitoring
- Check the documentation in the docs/ directory

EOF
    
    print_success "Installation summary created"
}

# Function to start services
start_services() {
    print_status "Starting RouterOS services..."
    
    # Start nftables first
    systemctl start nftables
    
    # Start watchdog service
    systemctl start routeros-watchdog
    
    # Wait a moment for watchdog to initialize
    sleep 5
    
    # Start web service
    systemctl start routeros-web
    
    # Check service status
    if systemctl is-active --quiet routeros-watchdog; then
        print_success "Watchdog service started successfully"
    else
        print_error "Watchdog service failed to start"
        systemctl status routeros-watchdog --no-pager -l
        return 1
    fi
    
    if systemctl is-active --quiet routeros-web; then
        print_success "Web service started successfully"
    else
        print_error "Web service failed to start"
        systemctl status routeros-web --no-pager -l
        return 1
    fi
    
    print_success "All services started successfully"
}

# Function to create requirements file
create_requirements_file() {
    print_status "Creating requirements file..."
    
    cat > "$ROUTEROS_DIR/requirements.txt" << 'EOF'
# Smart Multi-WAN Router OS Dependencies
Flask>=2.3.0
Flask-CORS>=4.0.0
psutil>=5.9.0
netifaces>=0.11.0
PyYAML>=6.0
jsonschema>=4.17.0
python-json-logger>=2.0.0
requests>=2.31.0
EOF
    
    print_success "Requirements file created"
}

# Main installation function
main() {
    print_status "Starting Smart Multi-WAN Router OS installation..."
    
    # Check if running as root
    check_root
    
    # Create log file
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    print_status "Installation log: $LOG_FILE"
    
    # Installation steps
    detect_interfaces
    install_dependencies
    create_requirements_file
    setup_system
    configure_routing_tables
    configure_nftables
    configure_sysctl
    install_services
    setup_log_rotation
    create_network_helper
    configure_firewall
    create_management_scripts
    create_installation_summary
    
    # Start services
    start_services
    
    print_success "Smart Multi-WAN Router OS installation completed successfully!"
    print_status "Access the web interface at: http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
    print_status "Check the installation summary at: $ROUTEROS_DIR/INSTALLATION_SUMMARY.md"
    print_status "Use the status script to check system status: $ROUTEROS_DIR/scripts/status.sh"
    
    echo ""
    print_status "Next steps:"
    echo "1. Configure your network interfaces using: $ROUTEROS_DIR/scripts/configure_network.sh"
    echo "2. Access the web dashboard at http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
    echo "3. Monitor system logs with: journalctl -u routeros-watchdog -f"
    echo "4. Check system status with: $ROUTEROS_DIR/scripts/status.sh"
    echo "5. Use kill-switch tool: routeros-kill-switch --help"
}

# Run main function
main "$@"