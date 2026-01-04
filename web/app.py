#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Web Management Dashboard
Provides real-time monitoring, configuration management, and manual controls
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import json
import os
import time
import logging
import subprocess
from datetime import datetime
from threading import Lock

app = Flask(__name__)
app.config['SECRET_KEY'] = 'routeros-secret-key-change-in-production'

# Global lock for thread safety
status_lock = Lock()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/routeros-web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RouterOSWebInterface:
    """Web interface for RouterOS management"""
    
    def __init__(self):
        self.status_file = '/opt/routeros/web/status.json'
        self.config_file = '/opt/routeros/config/interfaces.json'
        self.watchdog_script = '/opt/routeros/watchdog/watchdog_service.py'
        self.status_cache = {}
        self.cache_timestamp = 0
        self.cache_duration = 5  # seconds
        
    def get_system_status(self) -> dict:
        """Get current system status with caching"""
        current_time = time.time()
        
        with status_lock:
            if current_time - self.cache_timestamp < self.cache_duration:
                return self.status_cache.copy()
        
        try:
            # Read status from watchdog service
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r') as f:
                    status = json.load(f)
            else:
                # Fallback status if watchdog hasn't created file yet
                status = {
                    'timestamp': current_time,
                    'overall_health': 'unknown',
                    'service_running': False,
                    'components': {}
                }
            
            # Add web interface specific data
            status['web_interface'] = {
                'version': '1.0.0',
                'uptime': current_time - getattr(self, 'start_time', current_time),
                'last_update': datetime.now().isoformat()
            }
            
            # Cache the result
            with status_lock:
                self.status_cache = status.copy()
                self.cache_timestamp = current_time
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {
                'timestamp': current_time,
                'overall_health': 'error',
                'error': str(e),
                'web_interface': {
                    'version': '1.0.0',
                    'last_update': datetime.now().isoformat()
                }
            }
    
    def get_interface_config(self) -> dict:
        """Get interface configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                # Default configuration
                return {
                    'wan_interfaces': [
                        {'name': 'eth0', 'gateway': '192.168.100.1', 'weight': 2, 'dns': ['8.8.8.8']},
                        {'name': 'eth1', 'gateway': '192.168.200.1', 'weight': 1, 'dns': ['1.1.1.1']}
                    ]
                }
        except Exception as e:
            logger.error(f"Failed to get interface config: {e}")
            return {'error': str(e)}
    
    def save_interface_config(self, config: dict) -> bool:
        """Save interface configuration"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save interface config: {e}")
            return False
    
    def control_watchdog_service(self, action: str) -> dict:
        """Control the watchdog service"""
        try:
            if action == 'status':
                # Check if service is running
                result = subprocess.run(['systemctl', 'is-active', 'routeros-watchdog'], 
                                      capture_output=True, text=True)
                return {'status': result.stdout.strip(), 'running': result.returncode == 0}
            
            elif action == 'start':
                result = subprocess.run(['systemctl', 'start', 'routeros-watchdog'], 
                                      capture_output=True, text=True)
                return {'success': result.returncode == 0, 'message': result.stdout or result.stderr}
            
            elif action == 'stop':
                result = subprocess.run(['systemctl', 'stop', 'routeros-watchdog'], 
                                      capture_output=True, text=True)
                return {'success': result.returncode == 0, 'message': result.stdout or result.stderr}
            
            elif action == 'restart':
                result = subprocess.run(['systemctl', 'restart', 'routeros-watchdog'], 
                                      capture_output=True, text=True)
                return {'success': result.returncode == 0, 'message': result.stdout or result.stderr}
            
            else:
                return {'error': f'Unknown action: {action}'}
                
        except Exception as e:
            logger.error(f"Failed to control watchdog service: {e}")
            return {'error': str(e)}
    
    def control_interface(self, interface: str, action: str) -> dict:
        """Control individual interface"""
        try:
            # Use the watchdog service to control interfaces
            if action in ['enable', 'disable']:
                # This would interface with the watchdog service
                # For now, we'll simulate the action
                logger.info(f"Interface {interface} {action}d (simulated)")
                return {'success': True, 'message': f'Interface {interface} {action}d'}
            else:
                return {'error': f'Unknown action: {action}'}
                
        except Exception as e:
            logger.error(f"Failed to control interface {interface}: {e}")
            return {'error': str(e)}
    
    def get_system_logs(self, lines: int = 100) -> str:
        """Get system logs"""
        try:
            log_files = [
                '/var/log/routeros-watchdog.log',
                '/var/log/routeros-health.log',
                '/var/log/routeros-routing.log'
            ]
            
            logs = []
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r') as f:
                            file_logs = f.readlines()
                            logs.extend([f"[{os.path.basename(log_file)}] {line.strip()}" 
                                       for line in file_logs[-lines//len(log_files):]])
                    except Exception as e:
                        logs.append(f"Error reading {log_file}: {e}")
            
            # Sort by timestamp and limit lines
            logs.sort()
            return '\n'.join(logs[-lines:]) if logs else "No logs available"
            
        except Exception as e:
            logger.error(f"Failed to get system logs: {e}")
            return f"Error retrieving logs: {e}"
    
    def get_network_statistics(self) -> dict:
        """Get network interface statistics"""
        try:
            # Get interface statistics using ip command
            result = subprocess.run(['ip', '-s', 'link'], capture_output=True, text=True)
            if result.returncode != 0:
                return {'error': 'Failed to get interface statistics'}
            
            # Parse the output (simplified parsing)
            interfaces = {}
            lines = result.stdout.strip().split('\n')
            current_iface = None
            
            for line in lines:
                if line.startswith(':'):
                    parts = line.split(':')
                    if len(parts) >= 3:
                        current_iface = parts[1].strip()
                        interfaces[current_iface] = {'status': parts[2].strip()}
                elif current_iface and line.strip():
                    # This is statistics line - simplified parsing
                    if 'RX:' in line or 'TX:' in line:
                        continue
                    stats = line.strip().split()
                    if len(stats) >= 2 and current_iface in interfaces:
                        if 'rx_bytes' not in interfaces[current_iface]:
                            interfaces[current_iface]['rx_bytes'] = stats[0]
                            interfaces[current_iface]['rx_packets'] = stats[1]
                        else:
                            interfaces[current_iface]['tx_bytes'] = stats[0]
                            interfaces[current_iface]['tx_packets'] = stats[1]
            
            return {'interfaces': interfaces}
            
        except Exception as e:
            logger.error(f"Failed to get network statistics: {e}")
            return {'error': str(e)}

# Initialize the web interface
web_interface = RouterOSWebInterface()
web_interface.start_time = time.time()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API endpoint for system status"""
    return jsonify(web_interface.get_system_status())

@app.route('/api/interfaces')
def api_interfaces():
    """API endpoint for interface configuration"""
    return jsonify(web_interface.get_interface_config())

@app.route('/api/interfaces', methods=['POST'])
def api_save_interfaces():
    """API endpoint to save interface configuration"""
    try:
        config = request.get_json()
        success = web_interface.save_interface_config(config)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/watchdog/<action>')
def api_watchdog_control(action):
    """API endpoint for watchdog service control"""
    result = web_interface.control_watchdog_service(action)
    return jsonify(result)

@app.route('/api/interface/<interface>/<action>')
def api_interface_control(interface, action):
    """API endpoint for interface control"""
    result = web_interface.control_interface(interface, action)
    return jsonify(result)

@app.route('/api/logs')
def api_logs():
    """API endpoint for system logs"""
    lines = request.args.get('lines', 100, type=int)
    logs = web_interface.get_system_logs(lines)
    return jsonify({'logs': logs})

@app.route('/api/network-stats')
def api_network_stats():
    """API endpoint for network statistics"""
    return jsonify(web_interface.get_network_statistics())

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

def main():
    """Main function to run the web interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='RouterOS Web Management Interface')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    logger.info(f"Starting RouterOS Web Interface on {args.host}:{args.port}")
    
    # Create template directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create a simple template if it doesn't exist
    template_path = 'templates/dashboard.html'
    if not os.path.exists(template_path):
        with open(template_path, 'w') as f:
            f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RouterOS Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #333; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .card { background: white; border-radius: 5px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .interface-status { padding: 10px; border-radius: 3px; margin: 5px 0; }
        .healthy { background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .degraded { background-color: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }
        .failed { background-color: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .controls { display: flex; gap: 10px; margin: 10px 0; }
        button { padding: 8px 16px; border: none; border-radius: 3px; cursor: pointer; }
        .btn-primary { background-color: #007bff; color: white; }
        .btn-danger { background-color: #dc3545; color: white; }
        .btn-success { background-color: #28a745; color: white; }
        .logs { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .latency-chart { height: 200px; background: #f8f9fa; border: 1px solid #dee2e6; display: flex; align-items: center; justify-content: center; color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>RouterOS Dashboard</h1>
            <p>Smart Multi-WAN Router Management</p>
        </div>
        
        <div class="status-grid">
            <div class="card">
                <h2>System Status</h2>
                <div id="system-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>Interface Status</h2>
                <div id="interface-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>Controls</h2>
                <div class="controls">
                    <button class="btn-primary" onclick="refreshStatus()">Refresh</button>
                    <button class="btn-success" onclick="startWatchdog()">Start Watchdog</button>
                    <button class="btn-danger" onclick="stopWatchdog()">Stop Watchdog</button>
                    <button class="btn-primary" onclick="restartWatchdog()">Restart Watchdog</button>
                </div>
            </div>
            
            <div class="card">
                <h2>Latency Monitoring</h2>
                <div class="latency-chart">
                    <div>Real-time latency charts will appear here</div>
                </div>
            </div>
            
            <div class="card">
                <h2>System Logs</h2>
                <div id="system-logs" class="logs">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        function refreshStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('system-status').innerHTML = `
                        <div>Overall Health: <strong>${data.overall_health || 'Unknown'}</strong></div>
                        <div>Service Running: ${data.service_running ? 'Yes' : 'No'}</div>
                        <div>Last Update: ${new Date(data.timestamp * 1000).toLocaleString()}</div>
                    `;
                })
                .catch(error => {
                    document.getElementById('system-status').innerHTML = `<div style="color: red;">Error: ${error.message}</div>`;
                });
            
            fetch('/api/interfaces')
                .then(response => response.json())
                .then(data => {
                    let html = '';
                    if (data.wan_interfaces) {
                        data.wan_interfaces.forEach(iface => {
                            html += `
                                <div class="interface-status healthy">
                                    <strong>${iface.name}</strong><br>
                                    Gateway: ${iface.gateway}<br>
                                    Weight: ${iface.weight}<br>
                                    DNS: ${iface.dns.join(', ')}
                                </div>
                            `;
                        });
                    }
                    document.getElementById('interface-status').innerHTML = html || 'No interfaces configured';
                })
                .catch(error => {
                    document.getElementById('interface-status').innerHTML = `<div style="color: red;">Error: ${error.message}</div>`;
                });
            
            fetch('/api/logs?lines=50')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('system-logs').innerHTML = data.logs || 'No logs available';
                    document.getElementById('system-logs').scrollTop = document.getElementById('system-logs').scrollHeight;
                })
                .catch(error => {
                    document.getElementById('system-logs').innerHTML = `Error: ${error.message}`;
                });
        }
        
        function startWatchdog() {
            fetch('/api/watchdog/start')
                .then(response => response.json())
                .then(data => {
                    alert(data.message || 'Watchdog started');
                    refreshStatus();
                });
        }
        
        function stopWatchdog() {
            fetch('/api/watchdog/stop')
                .then(response => response.json())
                .then(data => {
                    alert(data.message || 'Watchdog stopped');
                    refreshStatus();
                });
        }
        
        function restartWatchdog() {
            fetch('/api/watchdog/restart')
                .then(response => response.json())
                .then(data => {
                    alert(data.message || 'Watchdog restarted');
                    refreshStatus();
                });
        }
        
        // Auto-refresh every 10 seconds
        setInterval(refreshStatus, 10000);
        
        // Initial load
        refreshStatus();
    </script>
</body>
</html>''')
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()