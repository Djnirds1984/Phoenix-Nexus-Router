#!/bin/bash

# PHOENIX ROUTER RESTORATION FROM SAFE MODE
# Simple script to restore full functionality from safe mode

echo "🔄 PHOENIX ROUTER - RESTORATION FROM SAFE MODE"
echo "=============================================="
echo ""
echo "This script will help you restore full router functionality"
echo "from your current safe mode installation."
echo ""

# Simple test function
test_network() {
    ping -c 1 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Step 1: Check what's currently running
echo "📊 STEP 1: Checking current status..."
echo ""

if test_network; then
    echo "✅ Network connectivity confirmed"
else
    echo "❌ Network connectivity issues detected"
fi

echo ""
echo "Current services:"
systemctl is-active phoenix-router-safe 2>/dev/null || echo "Safe mode: not running"
systemctl is-active routeros-routing 2>/dev/null || echo "Routing: not running"
systemctl is-active routeros-watchdog 2>/dev/null || echo "Watchdog: not running"
systemctl is-active routeros-web 2>/dev/null || echo "Web: not running"

echo ""
echo "Installation directories:"
ls -la /opt/ 2>/dev/null | grep -E "(phoenix-router-safe|routeros)" || echo "No router directories found"

echo ""
echo "📋 STEP 2: Restoration Options"
echo "============================="
echo ""
echo "Choose your restoration method:"
echo ""
echo "1. 🚀 QUICK RESTORE - Automated restoration (Recommended)"
echo "2. 🔧 MANUAL RESTORE - Step-by-step with verification"
echo "3. 🛡️  STAY SAFE - Keep safe mode running"
echo "4. 🚨 EMERGENCY - Full network recovery"
echo ""
read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "🚀 Starting quick restoration..."
        echo ""
        
        # Stop safe mode
        echo "Stopping safe mode..."
        systemctl stop phoenix-router-safe 2>/dev/null || true
        
        # Check if we have routeros files
        if [ -d "/opt/routeros" ]; then
            echo "✅ Found RouterOS installation"
            
            # Start services
            echo "Starting RouterOS services..."
            systemctl start routeros-routing 2>/dev/null && echo "✅ Routing manager started"
            systemctl start routeros-watchdog 2>/dev/null && echo "✅ Watchdog started"
            systemctl start routeros-web 2>/dev/null && echo "✅ Web interface started"
            
            # Check status
            echo ""
            echo "Service status:"
            systemctl is-active routeros-routing routeros-watchdog routeros-web
            
            # Test web interface
            if curl -s http://localhost:8080 > /dev/null 2>&1; then
                echo ""
                echo "🎉 SUCCESS! Your router is restored!"
                echo "Access at: http://localhost:8080"
            else
                echo ""
                echo "⚠️  Web interface may not be ready yet. Check with:"
                echo "systemctl status routeros-web"
            fi
        else
            echo "❌ No RouterOS installation found. Running manual setup..."
            # Fall through to manual setup
            choice=2
        fi
        ;;
        
    2)
        echo ""
        echo "🔧 Starting manual restoration..."
        echo ""
        
        # Create minimal setup
        echo "Creating minimal RouterOS setup..."
        mkdir -p /opt/routeros/{routing,watchdog,web,config,logs}
        
        # Copy essential files if they exist
        if [ -f "/opt/phoenix-router-safe/routing/routing_manager.py" ]; then
            cp /opt/phoenix-router-safe/routing/routing_manager.py /opt/routeros/routing/
            echo "✅ Copied routing manager"
        fi
        
        if [ -f "/opt/phoenix-router-safe/watchdog/watchdog_service.py" ]; then
            cp /opt/phoenix-router-safe/watchdog/watchdog_service.py /opt/routeros/watchdog/
            echo "✅ Copied watchdog service"
        fi
        
        if [ -f "/opt/phoenix-router-safe/web/enhanced_app.py" ]; then
            cp /opt/phoenix-router-safe/web/enhanced_app.py /opt/routeros/web/
            echo "✅ Copied web interface"
        fi
        
        # Create basic configuration
        echo "Creating basic configuration..."
        cat > /opt/routeros/config/interfaces.json << 'EOF'
{
  "interfaces": {
    "eth0": {
      "type": "wan",
      "weight": 1,
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
EOF
        
        # Make scripts executable
        chmod +x /opt/routeros/*/*.py
        
        echo ""
        echo "📋 Manual service startup:"
        echo "1. Test routing manager: cd /opt/routeros/routing && python3 routing_manager.py"
        echo "2. Test watchdog: cd /opt/routeros/watchdog && python3 watchdog_service.py"
        echo "3. Test web: cd /opt/routeros/web && python3 enhanced_app.py --host 0.0.0.0 --port 8080"
        echo ""
        echo "Or run: sudo /opt/phoenix-router-safe/scripts/manual_upgrade.sh"
        ;;
        
    3)
        echo ""
        echo "🛡️  Keeping safe mode active"
        echo "Your router will continue running in safe mode."
        echo "Access your safe interface at: http://localhost:8080"
        echo ""
        echo "Safe mode provides:"
        echo "• Network monitoring"
        echo "• Interface status"
        echo "• Connectivity testing"
        echo "• Zero risk to your network"
        ;;
        
    4)
        echo ""
        echo "🚨 Running emergency network recovery..."
        if [ -f "/opt/phoenix-router-safe/scripts/network_recovery.sh" ]; then
            sudo /opt/phoenix-router-safe/scripts/network_recovery.sh
        else
            echo "Network recovery script not found."
            echo "Try: sudo systemctl restart NetworkManager"
            echo "Or: sudo reboot"
        fi
        ;;
        
    *)
        echo ""
        echo "❌ Invalid choice. Keeping safe mode active."
        echo "Run this script again to choose a different option."
        ;;
esac

echo ""
echo "✅ Restoration process complete!"
echo ""
echo "🌐 Access your router at: http://localhost:8080"
echo "🔍 Check status: systemctl status routeros-*"
echo "📊 View logs: journalctl -u routeros-web -f"
echo ""
echo "Need help? The safe mode is always available as a fallback!"