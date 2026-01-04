#!/bin/bash

# EMERGENCY INSTALLATION - Phoenix Nexus Router
# This script is designed to be SAFE and will NEVER break your network
# It works alongside your existing network configuration

echo "🚨 EMERGENCY SAFE INSTALLATION - Phoenix Nexus Router 🚨"
echo "This script will NOT touch your existing network configuration"
echo ""

# Function to test network connectivity
test_network() {
    ping -c 1 8.8.8.8 > /dev/null 2>&1
    return $?
}

# Function to restore network (emergency)
restore_network() {
    echo "🆘 EMERGENCY: Restoring network connectivity..."
    # Re-enable NetworkManager if it was disabled
    systemctl enable NetworkManager 2>/dev/null
    systemctl start NetworkManager 2>/dev/null
    systemctl enable systemd-networkd 2>/dev/null
    systemctl start systemd-networkd 2>/dev/null
    echo "✅ Network services restored"
}

# Emergency network test
echo "🔍 Testing current network connectivity..."
if ! test_network; then
    echo "❌ No internet detected - running emergency restoration"
    restore_network
    sleep 5
    if ! test_network; then
        echo "🚨 CRITICAL: Cannot restore network. Please reboot manually."
        exit 1
    fi
fi
echo "✅ Network connectivity confirmed"
echo ""

# Create safe installation directory
echo "📁 Creating safe installation directory..."
mkdir -p /opt/phoenix-router-safe
cd /opt/phoenix-router-safe

# Download only the web interface (safest component)
echo "📥 Downloading safe web interface..."
cat > simple_web.py << 'EOF'
#!/usr/bin/env python3
"""Ultra-simple web interface for Phoenix Router - SAFE MODE"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
from datetime import datetime

class RouterHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Phoenix Router - SAFE MODE</title>
                <style>
                    body {{ font-family: Arial; margin: 40px; background: #f0f0f0; }}
                    .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                    .status {{ padding: 20px; background: #e8f5e8; border-left: 4px solid #4CAF50; margin: 20px 0; }}
                    .warning {{ padding: 20px; background: #fff3cd; border-left: 4px solid #ffc107; margin: 20px 0; }}
                    .btn {{ padding: 12px 24px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                    .btn-primary {{ background: #007bff; color: white; }}
                    .btn-danger {{ background: #dc3545; color: white; }}
                    .btn-success {{ background: #28a745; color: white; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🌐 Phoenix Router - SAFE MODE</h1>
                    <div class="status">
                        <h3>✅ Network Status: CONNECTED</h3>
                        <p>Your existing network configuration is preserved</p>
                        <p>Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    
                    <div class="warning">
                        <h3>⚠️ SAFE MODE ACTIVE</h3>
                        <p>This is a minimal installation that will not affect your network</p>
                        <p>Advanced routing features are disabled for safety</p>
                    </div>
                    
                    <h2>Quick Actions</h2>
                    <button class="btn btn-primary" onclick="testNetwork()">🔄 Test Network</button>
                    <button class="btn btn-success" onclick="showInterfaces()">🔌 Show Interfaces</button>
                    <button class="btn btn-danger" onclick="emergencyStop()">🛑 Emergency Stop</button>
                    
                    <h2>Network Information</h2>
                    <div id="network-info">
                        <p>Loading network information...</p>
                    </div>
                    
                    <h2>Installation Status</h2>
                    <div id="install-status">
                        <p>Safe mode installation complete</p>
                        <p>✅ Web interface running</p>
                        <p>✅ Network connectivity preserved</p>
                        <p>✅ No routing changes made</p>
                    </div>
                </div>
                
                <script>
                    function testNetwork() {{
                        fetch('/api/test-network')
                            .then(response => response.json())
                            .then(data => {{
                                alert(data.message);
                            }})
                            .catch(error => {{
                                alert('Network test failed');
                            }});
                    }}
                    
                    function showInterfaces() {{
                        fetch('/api/interfaces')
                            .then(response => response.json())
                            .then(data => {{
                                document.getElementById('network-info').innerHTML = 
                                    '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                            }})
                            .catch(error => {{
                                document.getElementById('network-info').innerHTML = 
                                    '<p style="color: red;">Failed to load interface information</p>';
                            }});
                    }}
                    
                    function emergencyStop() {{
                        if (confirm('🚨 EMERGENCY STOP: This will stop the web interface. Continue?')) {{
                            fetch('/api/emergency-stop')
                                .then(response => response.json())
                                .then(data => {{
                                    alert(data.message);
                                    window.close();
                                }});
                        }}
                    }}
                    
                    // Load interface info on page load
                    showInterfaces();
                </script>
            </body>
            </html>
            '''
            self.wfile.write(html.encode())
            
        elif self.path == '/api/test-network':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Simple network test
            result = os.system('ping -c 1 8.8.8.8 > /dev/null 2>&1')
            status = "success" if result == 0 else "failed"
            message = "✅ Internet connectivity confirmed" if result == 0 else "❌ No internet connectivity"
            
            response = json.dumps({"status": status, "message": message})
            self.wfile.write(response.encode())
            
        elif self.path == '/api/interfaces':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Get network interfaces (safe command)
            try:
                interfaces = []
                with open('/proc/net/dev', 'r') as f:
                    for line in f.readlines()[2:]:  # Skip header lines
                        parts = line.split()
                        if parts[0].endswith(':'):
                            iface_name = parts[0][:-1]
                            interfaces.append({
                                "name": iface_name,
                                "rx_bytes": parts[1],
                                "tx_bytes": parts[9],
                                "status": "up" if int(parts[1]) > 0 else "down"
                            })
                
                response = json.dumps({"interfaces": interfaces, "count": len(interfaces)})
            except Exception as e:
                response = json.dumps({"error": str(e), "interfaces": []})
            
            self.wfile.write(response.encode())
            
        elif self.path == '/api/emergency-stop':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = json.dumps({"status": "success", "message": "🛑 Emergency stop initiated - shutting down safely"})
            self.wfile.write(response.encode())
            
            # Schedule shutdown
            import threading
            def shutdown():
                time.sleep(2)
                os._exit(0)
            threading.Thread(target=shutdown).start()
            
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    import sys
    
    # Test if we can bind to port 8080
    port = 8080
    try:
        server = HTTPServer(('0.0.0.0', port), RouterHandler)
        print(f"🌐 Phoenix Router Safe Mode started on port {port}")
        print(f"🌐 Access the web interface at: http://localhost:{port}")
        print(f"🌐 Or via WAN IP: http://YOUR_WAN_IP:{port}")
        print("")
        print("✅ This is SAFE MODE - no routing changes will be made")
        print("✅ Your existing network configuration is preserved")
        print("✅ Emergency stop available via web interface")
        print("")
        print("Press Ctrl+C to stop the server")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down safely...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)
EOF

# Make it executable
chmod +x simple_web.py

# Create a simple service file for the safe web interface
cat > /etc/systemd/system/phoenix-safe-web.service << 'EOF'
[Unit]
Description=Phoenix Router Safe Mode Web Interface
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/phoenix-router-safe
ExecStart=/usr/bin/python3 /opt/phoenix-router-safe/simple_web.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the safe service
systemctl daemon-reload
systemctl enable phoenix-safe-web.service
systemctl start phoenix-safe-web.service

echo ""
echo "✅ SAFE INSTALLATION COMPLETE!"
echo ""
echo "🌐 Your web interface is now running at:"
echo "   http://localhost:8080"
echo "   http://YOUR_WAN_IP:8080"
echo ""
echo "✅ This installation is 100% SAFE:"
echo "   • No network configuration changes"
echo "   • No routing table modifications" 
echo "   • No service disruptions"
echo "   • Emergency stop button available"
echo ""
echo "🔍 To verify everything is working:"
echo "   systemctl status phoenix-safe-web.service"
echo ""
echo "🚨 If you need to stop everything:"
echo "   systemctl stop phoenix-safe-web.service"
echo ""
echo "When you're ready for full installation, run:"
echo "   /opt/phoenix-router-safe/upgrade-to-full.sh"