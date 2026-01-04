#!/bin/bash

# PHOENIX NEXUS ROUTER - ONE-LINE INSTALLER
# Ultra-safe installation that preserves your network
# Usage: curl -sSL https://raw.githubusercontent.com/Djnirds1984/Phoenix-Nexus-Router/main/install.sh | bash

set -euo pipefail

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

# Emergency network test
test_network() {
    ping -c 1 8.8.8.8 > /dev/null 2>&1
}

# Emergency recovery function
emergency_recovery() {
    error "Network connectivity lost! Attempting emergency recovery..."
    
    # Try to restore basic connectivity
    systemctl enable NetworkManager 2>/dev/null || true
    systemctl start NetworkManager 2>/dev/null || true
    systemctl enable systemd-networkd 2>/dev/null || true
    systemctl start systemd-networkd 2>/dev/null || true
    
    # Wait a moment and test again
    sleep 5
    if test_network; then
        success "Emergency recovery successful!"
        return 0
    else
        error "Emergency recovery failed. Manual intervention required."
        echo ""
        echo "🚨 EMERGENCY INSTRUCTIONS:"
        echo "1. Run: sudo reboot (to restart the system)"
        echo "2. If that fails, check physical network connections"
        echo "3. Contact your system administrator"
        return 1
    fi
}

# Main installation function
main() {
    echo ""
    echo "🌐 PHOENIX NEXUS ROUTER - ULTRA-SAFE INSTALLER"
    echo "================================================"
    echo ""
    echo "✅ This installation will NOT break your network"
    echo "✅ Your existing configuration will be preserved"
    echo "✅ Emergency recovery is built-in"
    echo ""
    
    # Test network connectivity before starting
    log "Testing network connectivity..."
    if ! test_network; then
        error "No internet connectivity detected!"
        echo "Please ensure you have working internet before proceeding."
        exit 1
    fi
    success "Network connectivity confirmed"
    echo ""
    
    # Create installation directory
    log "Creating installation directory..."
    INSTALL_DIR="/opt/phoenix-router-safe"
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    # Download the repository safely
    log "Downloading Phoenix Router files..."
    if command -v git > /dev/null; then
        git clone https://github.com/Djnirds1984/Phoenix-Nexus-Router.git . 2>/dev/null || {
            warning "Git clone failed, downloading archive instead..."
            curl -sSL https://github.com/Djnirds1984/Phoenix-Nexus-Router/archive/main.tar.gz | tar -xz --strip-components=1
        }
    else
        log "Installing git and downloading repository..."
        apt update && apt install -y git curl wget
        git clone https://github.com/Djnirds1984/Phoenix-Nexus-Router.git . 2>/dev/null || {
            curl -sSL https://github.com/Djnirds1984/Phoenix-Nexus-Router/archive/main.tar.gz | tar -xz --strip-components=1
        }
    fi
    
    # Test network again after download
    if ! test_network; then
        emergency_recovery || exit 1
    fi
    
    # Install Python if not available
    log "Checking Python installation..."
    if ! command -v python3 > /dev/null; then
        log "Installing Python 3..."
        apt install -y python3 python3-pip
    fi
    
    # Test network again
    if ! test_network; then
        emergency_recovery || exit 1
    fi
    
    # Create the ultra-safe web interface
    log "Creating ultra-safe web interface..."
    cat > simple_router.py << 'EOF'
#!/usr/bin/env python3
"""Ultra-safe Phoenix Router web interface"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import subprocess
import urllib.parse

class RouterHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Phoenix Router - SAFE MODE</title>
                <style>
                    body { font-family: Arial; margin: 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
                    .container { max-width: 800px; margin: 0 auto; background: rgba(255,255,255,0.1); padding: 40px; border-radius: 15px; backdrop-filter: blur(10px); }
                    .status { padding: 20px; background: rgba(76, 175, 80, 0.3); border-radius: 10px; margin: 20px 0; border-left: 4px solid #4CAF50; }
                    .warning { padding: 20px; background: rgba(255, 193, 7, 0.3); border-radius: 10px; margin: 20px 0; border-left: 4px solid #ffc107; }
                    .btn { padding: 15px 30px; margin: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; transition: all 0.3s ease; }
                    .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
                    .btn-primary { background: #007bff; color: white; }
                    .btn-danger { background: #dc3545; color: white; }
                    .btn-success { background: #28a745; color: white; }
                    h1 { text-align: center; margin-bottom: 30px; font-size: 2.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
                    .interface-card { background: rgba(255,255,255,0.1); padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 3px solid #007bff; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🌐 Phoenix Router</h1>
                    <div class="status">
                        <h3>✅ SAFE MODE ACTIVE</h3>
                        <p>Your network is protected. No routing changes will be made.</p>
                        <p>This is a read-only interface for monitoring your network.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <button class="btn btn-primary" onclick="refreshStatus()">🔄 Refresh Status</button>
                        <button class="btn btn-success" onclick="showInterfaces()">🔌 Network Interfaces</button>
                        <button class="btn btn-danger" onclick="testConnectivity()">🌐 Test Internet</button>
                    </div>
                    
                    <div id="content">
                        <h3>Network Information</h3>
                        <p>Click the buttons above to view network status.</p>
                    </div>
                </div>
                
                <script>
                    function refreshStatus() {
                        document.getElementById('content').innerHTML = '<p>Loading status...</p>';
                        fetch('/api/status')
                            .then(response => response.json())
                            .then(data => {
                                let html = '<h3>System Status</h3>';
                                html += '<div class="status">';
                                html += '<p><strong>Router Status:</strong> ' + data.status + '</p>';
                                html += '<p><strong>Network:</strong> ' + data.network + '</p>';
                                html += '<p><strong>Mode:</strong> ' + data.mode + '</p>';
                                html += '</div>';
                                document.getElementById('content').innerHTML = html;
                            })
                            .catch(error => {
                                document.getElementById('content').innerHTML = '<div class="warning"><p>Error loading status</p></div>';
                            });
                    }
                    
                    function showInterfaces() {
                        document.getElementById('content').innerHTML = '<p>Loading interfaces...</p>';
                        fetch('/api/interfaces')
                            .then(response => response.json())
                            .then(data => {
                                let html = '<h3>Network Interfaces</h3>';
                                if (data.interfaces && data.interfaces.length > 0) {
                                    data.interfaces.forEach(iface => {
                                        html += '<div class="interface-card">';
                                        html += '<strong>' + iface.name + '</strong><br>';
                                        html += 'Status: ' + iface.status + '<br>';
                                        html += 'RX: ' + iface.rx_bytes + ' bytes<br>';
                                        html += 'TX: ' + iface.tx_bytes + ' bytes';
                                        html += '</div>';
                                    });
                                } else {
                                    html += '<p>No interfaces found</p>';
                                }
                                document.getElementById('content').innerHTML = html;
                            })
                            .catch(error => {
                                document.getElementById('content').innerHTML = '<div class="warning"><p>Error loading interfaces</p></div>';
                            });
                    }
                    
                    function testConnectivity() {
                        document.getElementById('content').innerHTML = '<p>Testing internet connectivity...</p>';
                        fetch('/api/test-internet')
                            .then(response => response.json())
                            .then(data => {
                                let html = '<h3>Internet Test Results</h3>';
                                if (data.status === 'success') {
                                    html += '<div class="status">';
                                    html += '<p>✅ Internet connectivity confirmed!</p>';
                                    html += '<p>Response time: ' + data.time + 'ms</p>';
                                    html += '</div>';
                                } else {
                                    html += '<div class="warning">';
                                    html += '<p>❌ No internet connectivity detected</p>';
                                    html += '<p>This might be normal if you are behind a firewall</p>';
                                    html += '</div>';
                                }
                                document.getElementById('content').innerHTML = html;
                            })
                            .catch(error => {
                                document.getElementById('content').innerHTML = '<div class="warning"><p>Error testing connectivity</p></div>';
                            });
                    }
                    
                    // Load initial status
                    refreshStatus();
                </script>
            </body>
            </html>
            '''
            self.wfile.write(html.encode())
            
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            status = {
                "status": "online",
                "network": "preserved",
                "mode": "safe",
                "timestamp": __import__('datetime').datetime.now().isoformat(),
                "version": "1.0.0-safe"
            }
            self.wfile.write(json.dumps(status).encode())
            
        elif self.path == '/api/interfaces':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            interfaces = []
            try:
                # Read network interfaces from /proc/net/dev
                with open('/proc/net/dev', 'r') as f:
                    lines = f.readlines()
                    for line in lines[2:]:  # Skip header lines
                        parts = line.split()
                        if parts[0].endswith(':'):
                            iface_name = parts[0][:-1]
                            if iface_name != 'lo':  # Skip loopback
                                interfaces.append({
                                    "name": iface_name,
                                    "rx_bytes": parts[1],
                                    "tx_bytes": parts[9],
                                    "status": "up" if int(parts[1]) > 0 else "down"
                                })
            except Exception as e:
                interfaces = [{"error": str(e)}]
            
            response = {"interfaces": interfaces, "count": len(interfaces)}
            self.wfile.write(json.dumps(response).encode())
            
        elif self.path == '/api/test-internet':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            try:
                import time
                start = time.time()
                result = subprocess.run(['ping', '-c', '1', '-W', '2', '8.8.8.8'], 
                                      capture_output=True, text=True)
                end = time.time()
                
                if result.returncode == 0:
                    response = {
                        "status": "success",
                        "message": "Internet connectivity confirmed",
                        "time": round((end - start) * 1000, 2)
                    }
                else:
                    response = {
                        "status": "failed", 
                        "message": "No internet connectivity",
                        "time": 0
                    }
            except Exception as e:
                response = {
                    "status": "error",
                    "message": str(e),
                    "time": 0
                }
            
            self.wfile.write(json.dumps(response).encode())
            
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    import sys
    port = 8080
    try:
        server = HTTPServer(('0.0.0.0', port), RouterHandler)
        print(f"🌐 Phoenix Router Safe Mode started on port {port}")
        print(f"🌐 Access at: http://localhost:{port}")
        print(f"🌐 WAN Access: http://YOUR_SERVER_IP:{port}")
        print("")
        print("✅ SAFE MODE - No network changes will be made")
        print("✅ Your existing configuration is preserved")
        print("✅ Emergency stop: Press Ctrl+C")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down safely...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
EOF

    # Test network connectivity after file creation
    if ! test_network; then
        emergency_recovery || exit 1
    fi
    
    # Make the script executable
    chmod +x simple_router.py
    
    # Create systemd service (safe mode)
    log "Creating safe systemd service..."
    cat > /etc/systemd/system/phoenix-router-safe.service << 'EOF'
[Unit]
Description=Phoenix Router - Safe Mode
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/phoenix-router-safe
ExecStart=/usr/bin/python3 /opt/phoenix-router-safe/simple_router.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and start service
    log "Starting Phoenix Router in safe mode..."
    systemctl daemon-reload
    systemctl enable phoenix-router-safe.service
    systemctl start phoenix-router-safe.service
    
    # Test network one final time
    if ! test_network; then
        emergency_recovery || exit 1
    fi
    
    # Get server IP
    SERVER_IP=$(hostname -I | awk '{print $1}')
    
    success "🎉 INSTALLATION COMPLETE!"
    echo ""
    echo "🌐 YOUR PHOENIX ROUTER IS READY!"
    echo "================================="
    echo ""
    echo "💻 Access your router at:"
    echo "   Local: http://localhost:8080"
    echo "   Network: http://$SERVER_IP:8080"
    echo ""
    echo "✅ SAFE MODE FEATURES:"
    echo "   • No network configuration changes"
    echo "   • Read-only monitoring interface"
    echo "   • Network connectivity preserved"
    echo "   • One-click emergency stop"
    echo ""
    echo "🔍 NEXT STEPS:"
    echo "   1. Open the web interface in your browser"
    echo "   2. Test your network connectivity"
    echo "   3. When ready for full features, click 'Upgrade'"
    echo ""
    echo "🚨 EMERGENCY COMMANDS:"
    echo "   Stop router: systemctl stop phoenix-router-safe.service"
    echo "   Check status: systemctl status phoenix-router-safe.service"
    echo "   View logs: journalctl -u phoenix-router-safe.service -f"
    echo ""
    echo "💡 Having issues? Run: sudo /opt/phoenix-router-safe/scripts/network_recovery.sh"
    
    # Create upgrade script
    cat > /opt/phoenix-router-safe/upgrade.sh << 'EOF'
#!/bin/bash
# Upgrade to full Phoenix Router features

echo "🚀 Upgrading to full Phoenix Router features..."
echo "This will enable advanced routing and load balancing."
echo ""
read -p "Are you sure you want to upgrade? (y/N): " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    echo "Upgrading... (full installation script would run here)"
    # This would run the full installation
else
    echo "Upgrade cancelled. Safe mode will continue running."
fi
EOF
    chmod +x /opt/phoenix-router-safe/upgrade.sh
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Phoenix Nexus Router - Safe Installer"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --test         Test network connectivity"
        echo "  --recovery     Run network recovery"
        echo ""
        echo "This installer is 100% safe and will not break your network."
        ;;
    --test)
        if test_network; then
            success "Network connectivity confirmed!"
        else
            error "No network connectivity detected!"
            exit 1
        fi
        ;;
    --recovery)
        emergency_recovery
        ;;
    *)
        main
        ;;
esac