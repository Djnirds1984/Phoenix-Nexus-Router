#!/bin/bash

# PHOENIX ROUTER UPGRADE DIAGNOSTIC SCRIPT
# Diagnoses why the upgrade failed and provides solutions

echo "🔍 PHOENIX ROUTER UPGRADE DIAGNOSTIC"
echo "====================================="
echo ""

# Colors
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

# Test network connectivity
test_network() {
    ping -c 1 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Check service status
check_service_status() {
    local service=$1
    log "Checking $service..."
    
    if systemctl is-active "$service" > /dev/null 2>&1; then
        success "✅ $service is running"
        return 0
    else
        error "❌ $service is not running"
        
        # Check why it's not running
        log "Checking service logs for $service..."
        journalctl -u "$service" --no-pager -n 10 2>/dev/null | tail -5
        
        # Check if service file exists
        if [ -f "/etc/systemd/system/$service" ]; then
            log "Service file exists, checking configuration..."
        else
            error "Service file /etc/systemd/system/$service does not exist!"
        fi
        
        return 1
    fi
}

# Check Python dependencies
check_python_deps() {
    log "Checking Python dependencies..."
    
    REQUIRED_MODULES=(
        "flask:Flask web framework"
        "requests:HTTP requests"
        "psutil:System utilities"
        "netifaces:Network interfaces"
    )
    
    for module_info in "${REQUIRED_MODULES[@]}"; do
        IFS=':' read -r module description <<< "$module_info"
        
        if python3 -c "import $module" 2>/dev/null; then
            success "✅ $module ($description) is available"
        else
            error "❌ $module ($description) is missing"
            echo "   Install with: pip3 install $module"
        fi
    done
}

# Check file permissions and existence
check_files() {
    log "Checking critical files..."
    
    CRITICAL_FILES=(
        "/opt/routeros/routing/routing_manager.py"
        "/opt/routeros/routing/route_manager.py"
        "/opt/routeros/routing/interface_detector.py"
        "/opt/routeros/watchdog/watchdog_service.py"
        "/opt/routeros/web/enhanced_app.py"
        "/opt/routeros/config/interfaces.json"
    )
    
    for file in "${CRITICAL_FILES[@]}"; do
        if [ -f "$file" ]; then
            if [ -r "$file" ]; then
                success "✅ $file exists and is readable"
            else
                error "❌ $file exists but is not readable"
                echo "   Fix with: chmod +r $file"
            fi
        else
            error "❌ $file does not exist"
        fi
    done
}

# Check directory structure
check_directories() {
    log "Checking directory structure..."
    
    REQUIRED_DIRS=(
        "/opt/routeros"
        "/opt/routeros/routing"
        "/opt/routeros/watchdog"
        "/opt/routeros/web"
        "/opt/routeros/config"
        "/opt/routeros/scripts"
        "/var/log"
    )
    
    for dir in "${REQUIRED_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            if [ -w "$dir" ]; then
                success "✅ $dir exists and is writable"
            else
                error "❌ $dir exists but is not writable"
                echo "   Fix with: chmod +w $dir"
            fi
        else
            error "❌ $dir does not exist"
            echo "   Create with: mkdir -p $dir"
        fi
    done
}

# Test individual service startup
test_service_startup() {
    local service=$1
    local script=$2
    
    log "Testing manual startup of $service..."
    
    # Stop the service first if running
    systemctl stop "$service" 2>/dev/null || true
    
    # Try to run the script manually
    if [ -f "$script" ]; then
        log "Running $script manually..."
        cd "$(dirname "$script")"
        timeout 10 python3 "$script" --help 2>&1 | head -5
        
        local exit_code=$?
        if [ $exit_code -eq 0 ]; then
            success "✅ $script runs without errors"
        elif [ $exit_code -eq 124 ]; then
            warning "⚠️ $script timed out (this might be normal)"
        else
            error "❌ $script failed with exit code $exit_code"
        fi
    else
        error "❌ Script $script not found"
    fi
}

# Check configuration files
check_config_files() {
    log "Checking configuration files..."
    
    if [ -f "/opt/routeros/config/interfaces.json" ]; then
        log "Checking interfaces.json..."
        if python3 -m json.tool /opt/routeros/config/interfaces.json > /dev/null 2>&1; then
            success "✅ interfaces.json is valid JSON"
        else
            error "❌ interfaces.json is invalid JSON"
            echo "   Content preview:"
            head -5 /opt/routeros/config/interfaces.json
        fi
    else
        error "❌ interfaces.json not found"
    fi
    
    if [ -f "/opt/routeros/config/router.conf" ]; then
        success "✅ router.conf exists"
    else
        warning "⚠️ router.conf not found (this is optional)"
    fi
}

# Network interface check
check_network_interfaces() {
    log "Checking network interfaces..."
    
    echo "Available interfaces:"
    ip link show | grep -E "^[0-9]+:" | awk '{print $2}' | sed 's/://g' | while read iface; do
        if [ "$iface" != "lo" ]; then
            local status=$(ip link show "$iface" | grep -o "state [A-Z]*" | awk '{print $2}')
            local ip=$(ip addr show "$iface" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
            
            if [ "$status" = "UP" ]; then
                success "✅ $iface is UP ($ip)"
            else
                warning "⚠️ $iface is $status"
            fi
        fi
    done
}

# System resource check
check_system_resources() {
    log "Checking system resources..."
    
    # Check memory
    local memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local memory_mb=$((memory_kb / 1024))
    
    if [ $memory_mb -gt 512 ]; then
        success "✅ Memory: ${memory_mb}MB (sufficient)"
    else
        warning "⚠️ Memory: ${memory_mb}MB (may be low)"
    fi
    
    # Check disk space
    local disk_space=$(df /opt | tail -1 | awk '{print $4}')
    local disk_mb=$((disk_space / 1024))
    
    if [ $disk_mb -gt 100 ]; then
        success "✅ Disk space: ${disk_mb}MB available (sufficient)"
    else
        error "❌ Disk space: ${disk_mb}MB available (very low)"
    fi
}

# Generate fix script
generate_fix_script() {
    log "Generating automatic fix script..."
    
    cat > /tmp/phoenix_fix.sh << 'EOF'
#!/bin/bash
# Phoenix Router Automatic Fix Script

echo "🛠️  Phoenix Router Automatic Fix"
echo "================================="

# Fix directory permissions
echo "Fixing directory permissions..."
mkdir -p /opt/routeros/{routing,watchdog,web,config,scripts}
chmod 755 /opt/routeros
chmod 755 /opt/routeros/*

# Fix file permissions
echo "Fixing file permissions..."
find /opt/routeros -name "*.py" -exec chmod +x {} \;
find /opt/routeros -name "*.sh" -exec chmod +x {} \;

# Install missing Python packages
echo "Installing Python packages..."
pip3 install flask requests psutil netifaces

# Create missing config files
echo "Creating default configuration..."
cat > /opt/routeros/config/interfaces.json << 'CONFIG'
{
  "interfaces": {
    "eth0": {
      "type": "wan",
      "weight": 2,
      "enabled": true,
      "gateway": "192.168.1.1",
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
CONFIG

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

echo "✅ Automatic fixes applied!"
echo "Now try: sudo /opt/phoenix-router-safe/scripts/safe_upgrade.sh"
EOF

    chmod +x /tmp/phoenix_fix.sh
    success "✅ Fix script created at /tmp/phoenix_fix.sh"
    echo "Run it with: sudo /tmp/phoenix_fix.sh"
}

# Main diagnostic function
main() {
    echo "Starting comprehensive diagnostic..."
    echo ""
    
    # Test network first
    log "Testing network connectivity..."
    if test_network; then
        success "✅ Network connectivity confirmed"
    else
        error "❌ No network connectivity! Fix network first."
        exit 1
    fi
    echo ""
    
    # Run all checks
    check_directories
    echo ""
    
    check_files
    echo ""
    
    check_python_deps
    echo ""
    
    check_config_files
    echo ""
    
    check_network_interfaces
    echo ""
    
    check_system_resources
    echo ""
    
    # Check services
    log "Checking systemd services..."
    check_service_status "routeros-routing.service"
    check_service_status "routeros-watchdog.service"
    check_service_status "routeros-web.service"
    echo ""
    
    # Test manual startup
    log "Testing manual service startup..."
    test_service_startup "routeros-routing.service" "/opt/routeros/routing/routing_manager.py"
    echo ""
    
    # Generate fix script
    generate_fix_script
    echo ""
    
    echo "🎯 DIAGNOSTIC COMPLETE!"
    echo "======================="
    echo ""
    echo "Next steps:"
    echo "1. Run the automatic fix script: sudo /tmp/phoenix_fix.sh"
    echo "2. Then retry the upgrade: sudo /opt/phoenix-router-safe/scripts/safe_upgrade.sh"
    echo "3. If still having issues, check the logs above"
    echo ""
    echo "Emergency recovery: sudo /opt/phoenix-router-safe/scripts/network_recovery.sh"
}

# Handle command line arguments
case "${1:-}" in
    --fix)
        echo "Running automatic fix..."
        if [ -f "/tmp/phoenix_fix.sh" ]; then
            sudo /tmp/phoenix_fix.sh
        else
            generate_fix_script
            sudo /tmp/phoenix_fix.sh
        fi
        ;;
    --network)
        check_network_interfaces
        ;;
    --services)
        check