#!/bin/bash

# MANUAL UPGRADE - Step by step with verification
# This script performs a manual upgrade with detailed verification at each step

echo "🔧 MANUAL UPGRADE - Phoenix Nexus Router"
echo "========================================="
echo ""
echo "This will guide you through a step-by-step upgrade with verification"
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

# Step 1: Check current status
check_current_status() {
    echo "📊 STEP 1: Checking current system status"
    echo "========================================="
    echo ""
    
    # Check network
    log "Testing network connectivity..."
    if test_network; then
        success "✅ Network connectivity confirmed"
    else
        error "❌ No network connectivity! Cannot proceed."
        return 1
    fi
    
    # Check current services
    echo ""
    log "Checking current services..."
    
    if systemctl is-active phoenix-router-safe > /dev/null 2>&1; then
        success "✅ Safe mode is running"
    else
        warning "⚠️  Safe mode is not running"
    fi
    
    # Check what's installed
    echo ""
    log "Checking installation directories..."
    
    if [ -d "/opt/phoenix-router-safe" ]; then
        success "✅ Safe mode directory exists"
        ls -la /opt/phoenix-router-safe/
    else
        error "❌ Safe mode directory not found!"
        return 1
    fi
    
    if [ -d "/opt/routeros" ]; then
        success "✅ RouterOS directory exists"
        ls -la /opt/routeros/
    else
        warning "⚠️  RouterOS directory not found - will create"
    fi
    
    return 0
}

# Step 2: Create proper directory structure
create_directories() {
    echo ""
    echo "📁 STEP 2: Creating directory structure"
    echo "========================================"
    echo ""
    
    log "Creating RouterOS directory structure..."
    
    mkdir -p /opt/routeros/{routing,watchdog,web,config,scripts,systemd,logs}
    
    # Set proper permissions
    chmod 755 /opt/routeros
    chown -R root:root /opt/routeros
    
    success "✅ Directory structure created"
    echo ""
    log "Created directories:"
    ls -la /opt/routeros/
    
    return 0
}

# Step 3: Copy files from safe installation
copy_files() {
    echo ""
    echo "📋 STEP 3: Copying files from safe installation"
    echo "==============================================="
    echo ""
    
    log "Looking for files in safe installation..."
    
    # Check what's available in safe installation
    if [ -d "/opt/phoenix-router-safe" ]; then
        echo "Contents of safe installation:"
        find /opt/phoenix-router-safe -type f -name "*.py" -o -name "*.service" -o -name "*.json" | head -20
        
        log "Copying Python files..."
        # Copy routing files
        if [ -f "/opt/phoenix-router-safe/routing/routing_manager.py" ]; then
            cp /opt/phoenix-router-safe/routing/routing_manager.py /opt/routeros/routing/
            success "✅ Copied routing_manager.py"
        fi
        
        if [ -f "/opt/phoenix-router-safe/routing/route_manager.py" ]; then
            cp /opt/phoenix-router-safe/routing/route_manager.py /opt/routeros/routing/
            success "✅ Copied route_manager.py"
        fi
        
        if [ -f "/opt/phoenix-router-safe/routing/interface_detector.py" ]; then
            cp /opt/phoenix-router-safe/routing/interface_detector.py /opt/routeros/routing/
            success "✅ Copied interface_detector.py"
        fi
        
        # Copy watchdog files
        if [ -f "/opt/phoenix-router-safe/watchdog/watchdog_service.py" ]; then
            cp /opt/phoenix-router-safe/watchdog/watchdog_service.py /opt/routeros/watchdog/
            success "✅ Copied watchdog_service.py"
        fi
        
        if [ -f "/opt/phoenix-router-safe/watchdog/health_monitor.py" ]; then
            cp /opt/phoenix-router-safe/watchdog/health_monitor.py /opt/routeros/watchdog/
            success "✅ Copied health_monitor.py"
        fi
        
        # Copy web files
        if [ -f "/opt/phoenix-router-safe/web/enhanced_app.py" ]; then
            cp /opt/phoenix-router-safe/web/enhanced_app.py /opt/routeros/web/
            success "✅ Copied enhanced_app.py"
        fi
        
        if [ -f "/opt/phoenix-router-safe/web/wan_manager.py" ]; then
            cp /opt/phoenix-router-safe/web/wan_manager.py /opt/routeros/web/
            success "✅ Copied wan_manager.py"
        fi
        
        # Copy systemd files
        if [ -d "/opt/phoenix-router-safe/systemd" ]; then
            cp /opt/phoenix-router-safe/systemd/*.service /opt/routeros/systemd/ 2>/dev/null || true
            success "✅ Copied systemd service files"
        fi
    else
        error "❌ Safe installation directory not found!"
        return 1
    fi
    
    # Make scripts executable
    chmod +x /opt/routeros/*/*.py
    
    echo ""
    log "Files copied to RouterOS:"
    find /opt/routeros -name "*.py" -o -name "*.service" | sort
    
    return 0
}

# Step 4: Test individual components
test_components() {
    echo ""
    echo "🧪 STEP 4: Testing individual components"
    echo "========================================="
    echo ""
    
    log "Testing Python imports..."
    cd /opt/routeros
    
    # Test routing manager import
    log "Testing routing manager..."
    if python3 -c "import sys; sys.path.append('routing'); from routing_manager import RoutingManagerService; print('✅ RoutingManagerService import successful')" 2>/dev/null; then
        success "✅ Routing manager imports work"
    else
        error "❌ Routing manager import failed"
        python3 -c "import sys; sys.path.append('routing'); from routing_manager import RoutingManagerService" 2>&1
        return 1
    fi
    
    # Test watchdog service import
    log "Testing watchdog service..."
    if python3 -c "import sys; sys.path.append('watchdog'); from watchdog_service import RouterOSWatchdog; print('✅ RouterOSWatchdog import successful')" 2>/dev/null; then
        success "✅ Watchdog service imports work"
    else
        error "❌ Watchdog service import failed"
        python3 -c "import sys; sys.path.append('watchdog'); from watchdog_service import RouterOSWatchdog" 2>&1
        return 1
    fi
    
    # Test web interface import
    log "Testing web interface..."
    if python3 -c "import sys; sys.path.append('web'); from enhanced_app import app; print('✅ Web interface import successful')" 2>/dev/null; then
        success "✅ Web interface imports work"
    else
        error "❌ Web interface import failed"
        python3 -c "import sys; sys.path.append('web'); from enhanced_app import app" 2>&1
        return 1
    fi
    
    return 0
}

# Step 5: Create configuration files
create_config() {
    echo ""
    echo "⚙️  STEP 5: Creating configuration files"
    echo "======================================"
    echo ""
    
    log "Creating router configuration..."
    
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

    success "✅ Configuration files created"
    
    echo ""
    log "Configuration files:"
    ls -la /opt/routeros/config/
    
    return 0
}

# Step 6: Manual service testing
manual_service_test() {
    echo ""
    echo "🚀 STEP 6: Manual service testing"
    echo "==================================="
    echo ""
    
    log "Testing routing manager manually..."
    cd /opt/routeros/routing
    
    # Test routing manager
    timeout 10 python3 routing_manager.py &
    PID=$!
    sleep 3
    
    if kill -0 $PID 2>/dev/null; then
        success "✅ Routing manager started successfully"
        kill $PID
    else
        error "❌ Routing manager failed to start"
        return 1
    fi
    
    log "Testing watchdog service manually..."
    cd /opt/routeros/watchdog
    
    # Test watchdog
    timeout 10 python3 watchdog_service.py &
    PID=$!
    sleep 3
    
    if kill -0 $PID 2>/dev/null; then
        success "✅ Watchdog service started successfully"
        kill $PID
    else
        error "❌ Watchdog service failed to start"
        return 1
    fi
    
    log "Testing web interface manually..."
    cd /opt/routeros/web
    
    # Test web interface
    timeout 10 python3 enhanced_app.py --host 127.0.0.1 --port 8081 &
    PID=$!
    sleep 3
    
    if kill -0 $PID 2>/dev/null; then
        success "✅ Web interface started successfully"
        kill $PID
    else
        error "❌ Web interface failed to start"
        return 1
    fi
    
    return 0
}

# Step 7: Gradual systemd service startup
gradual_startup() {
    echo ""
    echo "🔄 STEP 7: Gradual systemd service startup"
    echo "========================================="
    echo ""
    
    log "Stopping safe mode..."
    systemctl stop phoenix-router-safe.service 2>/dev/null || true
    
    log "Creating systemd service files..."
    
    # Create routing service
    cat > /etc/systemd/system/routeros-routing.service << 'EOF'
[Unit]
Description=Phoenix Nexus Router - Routing Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/routeros/routing
ExecStart=/usr/bin/python3 /opt/routeros/routing/routing_manager.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Create watchdog service
    cat > /etc/systemd/system/routeros-watchdog.service << 'EOF'
[Unit]
Description=Phoenix Nexus Router - Watchdog Service
After=network.target routeros-routing.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/routeros/watchdog
ExecStart=/usr/bin/python3 /opt/routeros/watchdog/watchdog_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Create web service
    cat > /etc/systemd/system/routeros-web.service << 'EOF'
[Unit]
Description=Phoenix Nexus Router - Web Interface
After=network.target routeros-watchdog.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/routeros/web
ExecStart=/usr/bin/python3 /opt/routeros/web/enhanced_app.py --host 0.0.0.0 --port 8080
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    log "Reloading systemd..."
    systemctl daemon-reload
    
    # Start services one by one with testing
    log "Starting routing manager..."
    systemctl start routeros-routing.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting routing manager!"
        systemctl stop routeros-routing.service
        return 1
    fi
    success "✅ Routing manager started and network preserved"
    
    log "Starting watchdog service..."
    systemctl start routeros-watchdog.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting watchdog!"
        systemctl stop routeros-*
        return 1
    fi
    success "✅ Watchdog service started and network preserved"
    
    log "Starting web interface..."
    systemctl start routeros-web.service
    sleep 5
    
    if ! test_network; then
        error "❌ Network connectivity lost after starting web interface!"
        systemctl stop routeros-*
        return 1
    fi
    success "✅ Web interface started and network preserved"
    
    # Enable services for auto-start
    systemctl enable routeros-routing.service routeros-watchdog.service routeros-web.service
    
    return 0
}

# Step 8: Final verification
final_verification() {
    echo ""
    echo "✅ STEP 8: Final verification"
    echo "============================="
    echo ""
    
    log "Checking all services..."
    
    SERVICES="routeros-routing routeros-watchdog routeros-web"
    for service in $SERVICES; do
        if systemctl is-active "$service" > /dev/null 2>&1; then
            success "✅ $service is running"
        else
            error "❌ $service is not running!"
            systemctl status "$service" --no-pager -l
            return 1
        fi
    done
    
    log "Testing web interface..."
    if curl -s http://localhost:8080 > /dev/null; then
        success "✅ Web interface is accessible"
    else
        error "❌ Web interface is not accessible!"
        return 1
    fi
    
    log "Testing network connectivity..."
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
    echo "Starting manual upgrade process..."
    echo ""
    
    # Run all steps
    STEPS=(
        "check_current_status"
        "create_directories" 
        "copy_files"
        "test_components"
        "create_config"
        "manual_service_test"
        "gradual_startup"
        "final_verification"
    )
    
    for step in "${STEPS[@]}"; do
        if ! $step; then
            error "❌ Upgrade failed at step: $step"
            echo ""
            echo "🚨 RECOVERY OPTIONS:"
            echo "1. Stop all services: sudo systemctl stop routeros-*"
            echo "2. Restart safe mode: sudo systemctl start phoenix-router-safe.service"
            echo "3. Full network recovery: sudo /opt/phoenix-router-safe/scripts/network_recovery.sh"
            exit 1
        fi
        echo ""
    done
    
    echo ""
    success "🎉 MANUAL UPGRADE SUCCESSFUL!"
    echo ""
    echo "🌐 YOUR PHOENIX ROUTER IS READY!"
    echo "============================="
    echo ""
    echo "💻 Access your router at:"
    echo "   Local: http://localhost:8080"
    echo "   Network: http://$(hostname -I | awk '{print $1}'):8080"
    echo ""
    echo "🔧 AVAILABLE FEATURES:"
    echo "   • Multi-WAN load balancing"
    echo "   • Automatic failover"
    echo "   • WAN management interface"
    echo "   • Real-time monitoring"
    echo ""
    echo "🚨 SERVICE COMMANDS:"
    echo "   Check status: systemctl status routeros-*"
    echo "   View logs: journalctl -u routeros-web.service -f"
    echo "   Stop all: systemctl stop routeros-*"
    echo ""
    echo "💡 If you need to rollback:"
    echo "   systemctl stop routeros-*"
    echo "   systemctl start phoenix-router-safe.service"
}

# Handle command line arguments
case "${1:-}" in
    --step)
        # Run specific step
        if [ -n "${2:-}" ]; then
            $2
        else
            echo "Usage: $0 --step <step_function_name>"
            echo "Available steps:"
            for step in "${STEPS[@]}"; do
                echo "  - $step"
            done
        fi
        ;;
    --status)
        check_current_status
        ;;
    --rollback)
        echo "Rolling back to safe mode..."
        systemctl stop routeros-* 2>/dev/null || true
        systemctl start phoenix-router-safe.service
        success "✅ Rolled back to safe mode"
        ;;
    *)
        main
        ;;
esac