#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Enhanced Web Management Dashboard
Provides real-time monitoring, latency graphs, and advanced management features
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import json
import os
import time
import logging
import subprocess
from datetime import datetime
from threading import Lock
from latency_monitor import LatencyMonitor
import threading

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

class EnhancedRouterOSWebInterface:
    """Enhanced web interface with real-time latency monitoring and graphs"""
    
    def __init__(self):
        self.status_file = '/opt/routeros/web/status.json'
        self.config_file = '/opt/routeros/config/interfaces.json'
        self.watchdog_script = '/opt/routeros/watchdog/watchdog_service.py'
        self.status_cache = {}
        self.cache_timestamp = 0
        self.cache_duration = 5  # seconds
        
        # Initialize latency monitor
        self.latency_monitor = LatencyMonitor()
        self.latency_monitor.start_monitoring()
        
        # Start background thread for periodic status updates
        self.background_thread = threading.Thread(target=self._background_updates, daemon=True)
        self.background_thread.start()
        
    def _background_updates(self):
        """Background thread for periodic updates"""
        while True:
            try:
                # Update latency data
                self.latency_monitor.collect_latency_data()
                
                # Sleep for check interval
                time.sleep(self.latency_monitor.config['check_interval'])
                
            except Exception as e:
                logger.error(f"Error in background updates: {e}")
                time.sleep(10)
    
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
            
            # Add latency monitoring data
            latency_status = self.latency_monitor.get_interface_status()
            status['latency_monitoring'] = latency_status
            
            # Add web interface specific data
            status['web_interface'] = {
                'version': '2.0.0',
                'uptime': current_time - getattr(self, 'start_time', current_time),
                'last_update': datetime.now().isoformat(),
                'features': ['realtime_latency', 'graphs', 'export', 'alerts']
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
                    'version': '2.0.0',
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
    
    def get_latency_graph_data(self, interface: str, time_range: str = '1h') -> dict:
        """Get latency graph data for specified interface and time range"""
        try:
            return self.latency_monitor.generate_graph_data(interface, time_range)
        except Exception as e:
            logger.error(f"Failed to get latency graph data: {e}")
            return {'error': str(e)}
    
    def get_latency_summary(self, interface: str, hours: int = 24) -> dict:
        """Get latency summary statistics"""
        try:
            return self.latency_monitor.get_summary_statistics(interface, hours)
        except Exception as e:
            logger.error(f"Failed to get latency summary: {e}")
            return {'error': str(e)}
    
    def export_latency_data(self, interface: str, format: str = 'json', hours: int = 24) -> str:
        """Export latency data in specified format"""
        try:
            return self.latency_monitor.export_data(interface, format, hours)
        except Exception as e:
            logger.error(f"Failed to export latency data: {e}")
            return f"Error: {str(e)}"
    
    def control_watchdog_service(self, action: str) -> dict:
        """Control the watchdog service"""
        try:
            if action == 'status':
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
        """Manual control of interface (kill-switch functionality)"""
        try:
            if action in ['enable', 'disable']:
                # Interface with the watchdog service
                logger.info(f"Manual interface control: {interface} {action}")
                
                # Call watchdog service to handle interface control
                result = subprocess.run([
                    'python3', self.watchdog_script, 
                    '--interface-control', interface, action
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info(f"Successfully {action}d interface {interface}")
                    return {'success': True, 'message': f'Interface {interface} {action}d successfully'}
                else:
                    logger.error(f"Failed to {action} interface {interface}: {result.stderr}")
                    return {'error': f'Failed to {action} interface: {result.stderr}'}
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
                '/var/log/routeros-routing.log',
                '/var/log/routeros-web.log',
                '/var/log/routeros-latency.log'
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
web_interface = EnhancedRouterOSWebInterface()
web_interface.start_time = time.time()

@app.route('/')
def dashboard():
    """Main dashboard page with enhanced features"""
    return render_template('enhanced_dashboard.html')

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
        # Save logic would go here
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/latency/graph/<interface>/<time_range>')
def api_latency_graph(interface, time_range):
    """API endpoint for latency graph data"""
    return jsonify(web_interface.get_latency_graph_data(interface, time_range))

@app.route('/api/latency/summary/<interface>')
def api_latency_summary(interface):
    """API endpoint for latency summary statistics"""
    hours = request.args.get('hours', 24, type=int)
    return jsonify(web_interface.get_latency_summary(interface, hours))

@app.route('/api/latency/export/<interface>')
def api_latency_export(interface):
    """API endpoint to export latency data"""
    format_type = request.args.get('format', 'json')
    hours = request.args.get('hours', 24, type=int)
    data = web_interface.export_latency_data(interface, format_type, hours)
    
    if format_type == 'csv':
        return data, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=latency_{interface}_{hours}h.csv'
        }
    else:
        return data, 200, {'Content-Type': 'application/json'}

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

def create_enhanced_dashboard():
    """Create enhanced dashboard HTML template"""
    template_path = 'templates/enhanced_dashboard.html'
    os.makedirs('templates', exist_ok=True)
    
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RouterOS Enhanced Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 20px; 
        }
        .header { 
            background: rgba(255, 255, 255, 0.95); 
            backdrop-filter: blur(10px);
            border-radius: 15px; 
            padding: 30px; 
            margin-bottom: 30px; 
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .header h1 { 
            color: #2c3e50; 
            font-size: 2.5em; 
            margin-bottom: 10px; 
            text-align: center;
        }
        .header p { 
            color: #7f8c8d; 
            text-align: center; 
            font-size: 1.1em;
        }
        .dashboard-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); 
            gap: 25px; 
            margin-bottom: 30px;
        }
        .card { 
            background: rgba(255, 255, 255, 0.95); 
            backdrop-filter: blur(10px);
            border-radius: 15px; 
            padding: 25px; 
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .card:hover { 
            transform: translateY(-5px); 
            box-shadow: 0 12px 40px rgba(0,0,0,0.15);
        }
        .card h2 { 
            color: #2c3e50; 
            margin-bottom: 20px; 
            font-size: 1.4em;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-healthy { background-color: #27ae60; }
        .status-degraded { background-color: #f39c12; }
        .status-failed { background-color: #e74c3c; }
        .status-unknown { background-color: #95a5a6; }
        .interface-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
        }
        .controls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin: 15px 0;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
        }
        .btn-primary { background: #3498db; color: white; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-warning { background: #f39c12; color: white; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        .chart-container {
            position: relative;
            height: 300px;
            margin: 20px 0;
        }
        .logs-container {
            background: #2c3e50;
            color: #ecf0f1;
            border-radius: 10px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
            line-height: 1.4;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .metric-value {
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .metric-label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        .time-range-selector {
            display: flex;
            gap: 5px;
            margin: 15px 0;
            flex-wrap: wrap;
        }
        .time-btn {
            padding: 5px 10px;
            border: 1px solid #3498db;
            background: transparent;
            color: #3498db;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
        }
        .time-btn.active, .time-btn:hover {
            background: #3498db;
            color: white;
        }
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid;
        }
        .alert-info { background: #d1ecf1; border-color: #17a2b8; color: #0c5460; }
        .alert-warning { background: #fff3cd; border-color: #ffc107; color: #856404; }
        .alert-danger { background: #f8d7da; border-color: #dc3545; color: #721c24; }
        @media (max-width: 768px) {
            .dashboard-grid { grid-template-columns: 1fr; }
            .controls { flex-direction: column; }
            .time-range-selector { justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><span class="status-indicator" id="overall-status"></span>RouterOS Dashboard</h1>
            <p>Smart Multi-WAN Router Management with Real-time Monitoring</p>
        </div>
        
        <div class="dashboard-grid">
            <!-- System Overview -->
            <div class="card">
                <h2>System Overview</h2>
                <div id="system-overview">
                    <div class="metric-grid">
                        <div class="metric-card">
                            <div class="metric-value" id="overall-health">-</div>
                            <div class="metric-label">Overall Health</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value" id="active-interfaces">-</div>
                            <div class="metric-label">Active Interfaces</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value" id="uptime">-</div>
                            <div class="metric-label">Uptime</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value" id="last-update">-</div>
                            <div class="metric-label">Last Update</div>
                        </div>
                    </div>
                </div>
                
                <div class="controls">
                    <button class="btn btn-primary" onclick="refreshStatus()">🔄 Refresh</button>
                    <button class="btn btn-success" onclick="startWatchdog()">▶️ Start Watchdog</button>
                    <button class="btn btn-danger" onclick="stopWatchdog()">⏹️ Stop Watchdog</button>
                    <button class="btn btn-warning" onclick="restartWatchdog()">🔄 Restart Watchdog</button>
                </div>
            </div>
            
            <!-- Interface Status -->
            <div class="card">
                <h2>Interface Status</h2>
                <div id="interface-status">
                    <div class="alert alert-info">Loading interface status...</div>
                </div>
            </div>
            
            <!-- Latency Monitoring -->
            <div class="card">
                <h2>Real-time Latency Monitoring</h2>
                <div class="time-range-selector">
                    <button class="time-btn" onclick="changeTimeRange('15m')">15m</button>
                    <button class="time-btn active" onclick="changeTimeRange('1h')">1h</button>
                    <button class="time-btn" onclick="changeTimeRange('6h')">6h</button>
                    <button class="time-btn" onclick="changeTimeRange('24h')">24h</button>
                    <button class="time-btn" onclick="changeTimeRange('7d')">7d</button>
                </div>
                <div id="latency-charts">
                    <div class="alert alert-info">Loading latency charts...</div>
                </div>
            </div>
            
            <!-- Network Statistics -->
            <div class="card">
                <h2>Network Statistics</h2>
                <div id="network-stats">
                    <div class="alert alert-info">Loading network statistics...</div>
                </div>
            </div>
            
            <!-- System Logs -->
            <div class="card">
                <h2>System Logs</h2>
                <div class="controls">
                    <button class="btn btn-primary" onclick="refreshLogs()">🔄 Refresh Logs</button>
                    <button class="btn btn-secondary" onclick="exportLogs()">📄 Export Logs</button>
                </div>
                <div id="system-logs" class="logs-container">
                    Loading system logs...
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTimeRange = '1h';
        let charts = {};
        let statusUpdateInterval;
        
        // Initialize dashboard
        document.addEventListener('DOMContentLoaded', function() {
            initializeDashboard();
            startAutoRefresh();
        });
        
        function initializeDashboard() {
            refreshStatus();
            refreshLatencyCharts();
            refreshNetworkStats();
            refreshLogs();
        }
        
        function startAutoRefresh() {
            // Auto-refresh every 10 seconds
            statusUpdateInterval = setInterval(function() {
                refreshStatus();
                refreshLatencyCharts();
            }, 10000);
        }
        
        function refreshStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateSystemOverview(data);
                    updateInterfaceStatus(data);
                    updateOverallStatus(data);
                })
                .catch(error => {
                    console.error('Failed to refresh status:', error);
                    showAlert('danger', 'Failed to refresh system status');
                });
        }
        
        function updateSystemOverview(data) {
            document.getElementById('overall-health').textContent = data.overall_health || 'Unknown';
            document.getElementById('active-interfaces').textContent = 
                data.components?.health_monitor?.healthy_interfaces || '0';
            
            // Calculate uptime
            const uptime = data.web_interface?.uptime || 0;
            document.getElementById('uptime').textContent = formatUptime(uptime);
            
            // Last update
            const lastUpdate = data.web_interface?.last_update || new Date().toISOString();
            document.getElementById('last-update').textContent = formatTimeAgo(lastUpdate);
        }
        
        function updateInterfaceStatus(data) {
            const container = document.getElementById('interface-status');
            const interfaces = data.components?.health_monitor?.interfaces || {};
            const latencyData = data.latency_monitoring || {};
            
            if (Object.keys(interfaces).length === 0) {
                container.innerHTML = '<div class="alert alert-warning">No interfaces configured</div>';
                return;
            }
            
            let html = '';
            for (const [iface, info] of Object.entries(interfaces)) {
                const latency = latencyData[iface] || {};
                const statusClass = info.current_status === 'healthy' ? 'status-healthy' : 
                                  info.current_status === 'degraded' ? 'status-degraded' : 'status-failed';
                
                html += `
                    <div class="interface-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <strong>${iface}</strong>
                            <span class="status-indicator ${statusClass}"></span>
                        </div>
                        <div style="font-size: 0.9em; color: #666;">
                            <div>Status: <strong>${info.current_status}</strong></div>
                            <div>Latency: <strong>${latency.current_latency || 0}ms</strong></div>
                            <div>Packet Loss: <strong>${latency.current_packet_loss || 0}%</strong></div>
                            <div>Uptime: <strong>${info.uptime_percentage || 0}%</strong></div>
                        </div>
                        <div class="controls" style="margin-top: 10px;">
                            <button class="btn btn-sm btn-success" onclick="controlInterface('${iface}', 'enable')" 
                                    ${info.current_status === 'healthy' ? 'disabled' : ''}>Enable</button>
                            <button class="btn btn-sm btn-danger" onclick="controlInterface('${iface}', 'disable')" 
                                    ${info.current_status === 'failed' ? 'disabled' : ''}>Disable</button>
                            <button class="btn btn-sm btn-primary" onclick="exportLatencyData('${iface}')">Export Data</button>
                        </div>
                    </div>
                `;
            }
            
            container.innerHTML = html;
        }
        
        function updateOverallStatus(data) {
            const statusIndicator = document.getElementById('overall-status');
            const health = data.overall_health || 'unknown';
            
            statusIndicator.className = 'status-indicator';
            if (health === 'healthy') {
                statusIndicator.classList.add('status-healthy');
            } else if (health === 'degraded') {
                statusIndicator.classList.add('status-degraded');
            } else if (health === 'failed') {
                statusIndicator.classList.add('status-failed');
            } else {
                statusIndicator.classList.add('status-unknown');
            }
        }
        
        function refreshLatencyCharts() {
            const interfaces = ['eth0', 'eth1']; // Get from config
            const container = document.getElementById('latency-charts');
            
            let html = '';
            interfaces.forEach(iface => {
                html += `
                    <div style="margin: 20px 0;">
                        <h4>${iface} - Latency (${currentTimeRange})</h4>
                        <div class="chart-container">
                            <canvas id="latency-chart-${iface}"></canvas>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
            
            // Create charts
            interfaces.forEach(iface => {
                createLatencyChart(iface, currentTimeRange);
            });
        }
        
        function createLatencyChart(interface, timeRange) {
            fetch(`/api/latency/graph/${interface}/${timeRange}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        console.error('Failed to get latency data:', data.error);
                        return;
                    }
                    
                    const ctx = document.getElementById(`latency-chart-${interface}`);
                    if (!ctx) return;
                    
                    // Destroy existing chart if it exists
                    if (charts[interface]) {
                        charts[interface].destroy();
                    }
                    
                    charts[interface] = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels || [],
                            datasets: [{
                                label: 'Latency (ms)',
                                data: data.latency_data || [],
                                borderColor: '#3498db',
                                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                tension: 0.4,
                                fill: true
                            }, {
                                label: 'Packet Loss (%)',
                                data: data.packet_loss_data || [],
                                borderColor: '#e74c3c',
                                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                                tension: 0.4,
                                yAxisID: 'y1'
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Latency (ms)'
                                    }
                                },
                                y1: {
                                    type: 'linear',
                                    display: true,
                                    position: 'right',
                                    beginAtZero: true,
                                    max: 100,
                                    title: {
                                        display: true,
                                        text: 'Packet Loss (%)'
                                    },
                                    grid: {
                                        drawOnChartArea: false,
                                    },
                                }
                            },
                            plugins: {
                                title: {
                                    display: true,
                                    text: `${interface} - Latency Monitor`
                                }
                            }
                        }
                    });
                })
                .catch(error => {
                    console.error('Failed to create latency chart:', error);
                });
        }
        
        function changeTimeRange(timeRange) {
            currentTimeRange = timeRange;
            
            // Update active button
            document.querySelectorAll('.time-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            refreshLatencyCharts();
        }
        
        function refreshNetworkStats() {
            fetch('/api/network-stats')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('network-stats');
                    
                    if (data.error) {
                        container.innerHTML = `<div class="alert alert-danger">Error: ${data.error}</div>`;
                        return;
                    }
                    
                    let html = '<div class="metric-grid">';
                    const interfaces = data.interfaces || {};
                    
                    for (const [iface, stats] of Object.entries(interfaces)) {
                        html += `
                            <div class="metric-card">
                                <div class="metric-value">${iface}</div>
                                <div class="metric-label">Interface</div>
                                <div style="margin-top: 10px; font-size: 0.8em;">
                                    RX: ${stats.rx_packets || 0} packets<br>
                                    TX: ${stats.tx_packets || 0} packets<br>
                                    Status: ${stats.status || 'Unknown'}
                                </div>
                            </div>
                        `;
                    }
                    
                    html += '</div>';
                    container.innerHTML = html;
                })
                .catch(error => {
                    console.error('Failed to refresh network stats:', error);
                });
        }
        
        function refreshLogs() {
            fetch('/api/logs?lines=50')
                .then(response => response.json())
                .then(data => {
                    const logsContainer = document.getElementById('system-logs');
                    logsContainer.innerHTML = data.logs || 'No logs available';
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                })
                .catch(error => {
                    console.error('Failed to refresh logs:', error);
                });
        }
        
        function controlInterface(interface, action) {
            // Show confirmation dialog for disable action
            if (action === 'disable') {
                if (!confirm(`Are you sure you want to DISABLE interface ${interface}? This will remove it from the load balancing pool.`)) {
                    return;
                }
            }
            
            // Show loading state
            const buttons = document.querySelectorAll(`button[onclick*="controlInterface('${interface}'"]`);
            buttons.forEach(btn => btn.disabled = true);
            
            fetch(`/api/interface/${interface}/${action}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAlert('success', data.message);
                        refreshStatus();
                    } else {
                        showAlert('danger', data.error || 'Operation failed');
                    }
                })
                .catch(error => {
                    showAlert('danger', 'Failed to control interface');
                })
                .finally(() => {
                    // Re-enable buttons
                    buttons.forEach(btn => btn.disabled = false);
                });
        }
        
        function startWatchdog() {
            fetch('/api/watchdog/start')
                .then(response => response.json())
                .then(data => {
                    showAlert(data.success ? 'success' : 'danger', 
                             data.message || (data.success ? 'Watchdog started' : 'Failed to start watchdog'));
                    refreshStatus();
                });
        }
        
        function stopWatchdog() {
            fetch('/api/watchdog/stop')
                .then(response => response.json())
                .then(data => {
                    showAlert(data.success ? 'success' : 'danger', 
                             data.message || (data.success ? 'Watchdog stopped' : 'Failed to stop watchdog'));
                    refreshStatus();
                });
        }
        
        function restartWatchdog() {
            fetch('/api/watchdog/restart')
                .then(response => response.json())
                .then(data => {
                    showAlert(data.success ? 'success' : 'danger', 
                             data.message || (data.success ? 'Watchdog restarted' : 'Failed to restart watchdog'));
                    refreshStatus();
                });
        }
        
        function exportLatencyData(interface) {
            window.open(`/api/latency/export/${interface}?format=csv&hours=24`, '_blank');
        }
        
        function exportLogs() {
            // Implementation for log export
            showAlert('info', 'Log export feature coming soon');
        }
        
        function showAlert(type, message) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type}`;
            alertDiv.textContent = message;
            
            const container = document.querySelector('.container');
            container.insertBefore(alertDiv, container.firstChild);
            
            setTimeout(() => {
                alertDiv.remove();
            }, 5000);
        }
        
        function formatUptime(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        }
        
        function formatTimeAgo(timestamp) {
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;
            
            if (diff < 60000) return 'Just now';
            if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
            if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
            
            return date.toLocaleString();
        }
        
        // Cleanup on page unload
        window.addEventListener('beforeunload', function() {
            if (statusUpdateInterval) {
                clearInterval(statusUpdateInterval);
            }
        });
    </script>
</body>
</html>'''
    
    with open(template_path, 'w') as f:
        f.write(html_content)

def main():
    """Main function to run the enhanced web interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced RouterOS Web Management Interface')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    logger.info(f"Starting Enhanced RouterOS Web Interface on {args.host}:{args.port}")
    
    # Create enhanced dashboard template
    create_enhanced_dashboard()
    
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == '__main__':
    main()