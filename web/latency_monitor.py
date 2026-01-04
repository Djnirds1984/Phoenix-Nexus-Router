#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Real-time Latency Monitor
Provides real-time latency monitoring, graphing, and historical data analysis
"""

import time
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import deque
import subprocess
import os

@dataclass
class LatencyDataPoint:
    """Represents a single latency measurement"""
    timestamp: float
    interface: str
    latency: float
    packet_loss: float
    status: str
    target: str

class LatencyMonitor:
    """Real-time latency monitoring and graphing system"""
    
    def __init__(self, db_path: str = "/opt/routeros/web/latency_data.db", 
                 max_data_points: int = 1000):
        self.db_path = db_path
        self.max_data_points = max_data_points
        self.logger = logging.getLogger(__name__)
        
        # Real-time data storage
        self.realtime_data: Dict[str, deque] = {}
        self.monitoring_active = False
        self.monitor_thread = None
        
        # Configuration
        self.config = {
            'ping_targets': ['1.1.1.1', '8.8.8.8', '9.9.9.9'],
            'check_interval': 5,  # seconds
            'timeout_seconds': 2,
            'interfaces': ['eth0', 'eth1'],
            'graph_retention_hours': 24
        }
        
        self._setup_database()
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging for latency monitor"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/routeros-latency.log'),
                logging.StreamHandler()
            ]
        )
    
    def _setup_database(self):
        """Initialize SQLite database for latency data storage"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create latency data table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS latency_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    interface TEXT NOT NULL,
                    target TEXT NOT NULL,
                    latency REAL NOT NULL,
                    packet_loss REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON latency_data(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_interface ON latency_data(interface)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_interface_timestamp ON latency_data(interface, timestamp)
            ''')
            
            # Create summary statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS latency_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interface TEXT NOT NULL,
                    target TEXT NOT NULL,
                    hour_timestamp INTEGER NOT NULL,
                    avg_latency REAL,
                    min_latency REAL,
                    max_latency REAL,
                    avg_packet_loss REAL,
                    uptime_percentage REAL,
                    sample_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup database: {e}")
            raise
    
    def _run_ping_test(self, interface: str, target: str) -> Tuple[float, float, str]:
        """
        Run ping test and return latency, packet loss, and status
        Returns: (latency_ms, packet_loss_percentage, status)
        """
        try:
            cmd = [
                'ping', '-I', interface, '-c', '3', '-W', str(self.config['timeout_seconds']),
                '-q', target
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return 0.0, 100.0, 'failed'
            
            # Parse ping output
            output_lines = result.stdout.strip().split('\n')
            latency = 0.0
            packet_loss = 0.0
            
            for line in output_lines:
                if 'packet loss' in line:
                    parts = line.split(',')
                    for part in parts:
                        if 'packet loss' in part:
                            packet_loss = float(part.strip().split('%')[0])
                            break
                
                if 'rtt' in line and 'avg' in line:
                    parts = line.split('=')[1].strip().split('/')
                    if len(parts) >= 2:
                        latency = float(parts[1])
                    break
            
            # Determine status
            if packet_loss >= 100.0:
                status = 'down'
            elif packet_loss > 5.0 or latency > 2000:
                status = 'degraded'
            else:
                status = 'healthy'
            
            return latency, packet_loss, status
            
        except subprocess.TimeoutExpired:
            return 0.0, 100.0, 'timeout'
        except Exception as e:
            self.logger.error(f"Ping test failed for {interface}->{target}: {e}")
            return 0.0, 100.0, 'error'
    
    def collect_latency_data(self):
        """Collect latency data for all interfaces and targets"""
        current_time = time.time()
        
        for interface in self.config['interfaces']:
            for target in self.config['ping_targets']:
                try:
                    latency, packet_loss, status = self._run_ping_test(interface, target)
                    
                    data_point = LatencyDataPoint(
                        timestamp=current_time,
                        interface=interface,
                        target=target,
                        latency=latency,
                        packet_loss=packet_loss,
                        status=status
                    )
                    
                    # Store in real-time buffer
                    if interface not in self.realtime_data:
                        self.realtime_data[interface] = deque(maxlen=self.max_data_points)
                    
                    self.realtime_data[interface].append(data_point)
                    
                    # Store in database
                    self._store_data_point(data_point)
                    
                    self.logger.debug(f"Latency data collected: {interface}->{target} "
                                    f"({latency:.1f}ms, {packet_loss:.1f}% loss, {status})")
                    
                except Exception as e:
                    self.logger.error(f"Failed to collect latency data for {interface}->{target}: {e}")
    
    def _store_data_point(self, data_point: LatencyDataPoint):
        """Store data point in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO latency_data (timestamp, interface, target, latency, packet_loss, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (data_point.timestamp, data_point.interface, data_point.target,
                  data_point.latency, data_point.packet_loss, data_point.status))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to store data point: {e}")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        self.logger.info("Latency monitoring started")
        
        while self.monitoring_active:
            try:
                self.collect_latency_data()
                
                # Clean up old data
                self._cleanup_old_data()
                
                # Generate hourly summaries
                self._generate_hourly_summaries()
                
                time.sleep(self.config['check_interval'])
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.config['check_interval'])
        
        self.logger.info("Latency monitoring stopped")
    
    def _cleanup_old_data(self):
        """Remove old data beyond retention period"""
        try:
            cutoff_time = time.time() - (self.config['graph_retention_hours'] * 3600)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM latency_data WHERE timestamp < ?', (cutoff_time,))
            deleted_rows = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_rows > 0:
                self.logger.info(f"Cleaned up {deleted_rows} old latency data points")
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
    
    def _generate_hourly_summaries(self):
        """Generate hourly summary statistics"""
        try:
            current_hour = int(time.time() // 3600) * 3600
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if summaries already exist for this hour
            cursor.execute('''
                SELECT COUNT(*) FROM latency_summary 
                WHERE hour_timestamp = ?
            ''', (current_hour,))
            
            if cursor.fetchone()[0] > 0:
                return  # Already summarized
            
            # Generate summaries for each interface and target
            for interface in self.config['interfaces']:
                for target in self.config['ping_targets']:
                    cursor.execute('''
                        SELECT 
                            AVG(latency) as avg_latency,
                            MIN(latency) as min_latency,
                            MAX(latency) as max_latency,
                            AVG(packet_loss) as avg_packet_loss,
                            COUNT(*) as sample_count,
                            SUM(CASE WHEN status = 'healthy' THEN 1 ELSE 0 END) as healthy_count
                        FROM latency_data
                        WHERE interface = ? AND target = ? 
                        AND timestamp >= ? AND timestamp < ?
                    ''', (interface, target, current_hour - 3600, current_hour))
                    
                    result = cursor.fetchone()
                    if result and result[0] is not None:
                        avg_latency, min_latency, max_latency, avg_packet_loss, sample_count, healthy_count = result
                        uptime_percentage = (healthy_count / sample_count) * 100 if sample_count > 0 else 0
                        
                        cursor.execute('''
                            INSERT INTO latency_summary 
                            (interface, target, hour_timestamp, avg_latency, min_latency, max_latency, 
                             avg_packet_loss, uptime_percentage, sample_count)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (interface, target, current_hour, avg_latency, min_latency, max_latency,
                              avg_packet_loss, uptime_percentage, sample_count))
            
            conn.commit()
            conn.close()
            
            self.logger.info("Hourly latency summaries generated")
            
        except Exception as e:
            self.logger.error(f"Failed to generate hourly summaries: {e}")
    
    def get_realtime_data(self, interface: str, minutes: int = 60) -> List[Dict]:
        """Get realtime latency data for specified interface and time period"""
        try:
            if interface not in self.realtime_data:
                return []
            
            cutoff_time = time.time() - (minutes * 60)
            data = []
            
            for data_point in self.realtime_data[interface]:
                if data_point.timestamp >= cutoff_time:
                    data.append(asdict(data_point))
            
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to get realtime data: {e}")
            return []
    
    def get_historical_data(self, interface: str, hours: int = 24) -> List[Dict]:
        """Get historical latency data from database"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, interface, target, latency, packet_loss, status
                FROM latency_data
                WHERE interface = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            ''', (interface, cutoff_time))
            
            results = cursor.fetchall()
            conn.close()
            
            data = []
            for row in results:
                data.append({
                    'timestamp': row[0],
                    'interface': row[1],
                    'target': row[2],
                    'latency': row[3],
                    'packet_loss': row[4],
                    'status': row[5]
                })
            
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to get historical data: {e}")
            return []
    
    def get_summary_statistics(self, interface: str, hours: int = 24) -> Dict:
        """Get summary statistics for specified interface and time period"""
        try:
            cutoff_time = time.time() - (hours * 3600)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_samples,
                    AVG(latency) as avg_latency,
                    MIN(latency) as min_latency,
                    MAX(latency) as max_latency,
                    AVG(packet_loss) as avg_packet_loss,
                    SUM(CASE WHEN status = 'healthy' THEN 1 ELSE 0 END) as healthy_samples,
                    SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) as degraded_samples,
                    SUM(CASE WHEN status = 'down' THEN 1 ELSE 0 END) as down_samples
                FROM latency_data
                WHERE interface = ? AND timestamp >= ?
            ''', (interface, cutoff_time))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] > 0:
                total_samples, avg_latency, min_latency, max_latency, avg_packet_loss, \
                healthy_samples, degraded_samples, down_samples = result
                
                return {
                    'interface': interface,
                    'time_period_hours': hours,
                    'total_samples': total_samples,
                    'avg_latency': round(avg_latency, 2) if avg_latency else 0,
                    'min_latency': round(min_latency, 2) if min_latency else 0,
                    'max_latency': round(max_latency, 2) if max_latency else 0,
                    'avg_packet_loss': round(avg_packet_loss, 2) if avg_packet_loss else 0,
                    'uptime_percentage': round((healthy_samples / total_samples) * 100, 2),
                    'healthy_samples': healthy_samples,
                    'degraded_samples': degraded_samples,
                    'down_samples': down_samples
                }
            else:
                return {
                    'interface': interface,
                    'time_period_hours': hours,
                    'total_samples': 0,
                    'avg_latency': 0,
                    'min_latency': 0,
                    'max_latency': 0,
                    'avg_packet_loss': 0,
                    'uptime_percentage': 0,
                    'healthy_samples': 0,
                    'degraded_samples': 0,
                    'down_samples': 0
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get summary statistics: {e}")
            return {'error': str(e)}
    
    def get_interface_status(self) -> Dict[str, Dict]:
        """Get current status for all interfaces"""
        try:
            status = {}
            
            for interface in self.config['interfaces']:
                # Get latest data point
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT latency, packet_loss, status, timestamp
                    FROM latency_data
                    WHERE interface = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''', (interface,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    latency, packet_loss, status, timestamp = result
                    
                    # Calculate status age
                    age_minutes = (time.time() - timestamp) / 60
                    
                    status[interface] = {
                        'current_latency': round(latency, 2),
                        'current_packet_loss': round(packet_loss, 2),
                        'status': status,
                        'last_check_age_minutes': round(age_minutes, 1),
                        'is_recent': age_minutes < 10  # Consider recent if less than 10 minutes old
                    }
                else:
                    status[interface] = {
                        'current_latency': 0,
                        'current_packet_loss': 0,
                        'status': 'unknown',
                        'last_check_age_minutes': 999,
                        'is_recent': False
                    }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get interface status: {e}")
            return {'error': str(e)}
    
    def generate_graph_data(self, interface: str, time_range: str = '1h') -> Dict:
        """Generate graph data for specified time range"""
        try:
            time_ranges = {
                '15m': 15,
                '1h': 60,
                '6h': 360,
                '24h': 1440,
                '7d': 10080
            }
            
            minutes = time_ranges.get(time_range, 60)
            data = self.get_historical_data(interface, hours=minutes//60)
            
            # Generate graph data
            graph_data = {
                'labels': [],
                'latency_data': [],
                'packet_loss_data': [],
                'status_data': [],
                'interface': interface,
                'time_range': time_range,
                'generated_at': time.time()
            }
            
            # Sample data every minute for better visualization
            sample_interval = max(1, len(data) // 100)  # Max 100 data points
            
            for i, point in enumerate(data[::sample_interval]):
                timestamp = datetime.fromtimestamp(point['timestamp'])
                graph_data['labels'].append(timestamp.strftime('%H:%M'))
                graph_data['latency_data'].append(round(point['latency'], 2))
                graph_data['packet_loss_data'].append(round(point['packet_loss'], 2))
                graph_data['status_data'].append(point['status'])
            
            # Add summary statistics
            summary = self.get_summary_statistics(interface, hours=minutes//60)
            graph_data['summary'] = summary
            
            return graph_data
            
        except Exception as e:
            self.logger.error(f"Failed to generate graph data: {e}")
            return {'error': str(e)}
    
    def start_monitoring(self):
        """Start latency monitoring"""
        if self.monitoring_active:
            self.logger.warning("Latency monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Latency monitoring started")
    
    def stop_monitoring(self):
        """Stop latency monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        self.logger.info("Latency monitoring stopped")
    
    def export_data(self, interface: str, format: str = 'json', 
                   hours: int = 24) -> str:
        """Export latency data in specified format"""
        try:
            data = self.get_historical_data(interface, hours=hours)
            
            if format == 'json':
                return json.dumps({
                    'interface': interface,
                    'export_time': time.time(),
                    'time_period_hours': hours,
                    'data_points': len(data),
                    'data': data
                }, indent=2)
            
            elif format == 'csv':
                csv_data = "timestamp,interface,target,latency,packet_loss,status\n"
                for point in data:
                    csv_data += f"{point['timestamp']},{point['interface']},{point['target']},"
                    csv_data += f"{point['latency']},{point['packet_loss']},{point['status']}\n"
                return csv_data
            
            else:
                return f"Unsupported format: {format}"
                
        except Exception as e:
            self.logger.error(f"Failed to export data: {e}")
            return f"Error: {str(e)}"

def main():
    """Main function for testing latency monitor"""
    monitor = LatencyMonitor()
    
    # Start monitoring
    monitor.start_monitoring()
    
    print("Latency monitoring started. Collecting data...")
    
    # Collect data for 30 seconds
    time.sleep(30)
    
    # Get interface status
    status = monitor.get_interface_status()
    print("\nInterface Status:")
    print(json.dumps(status, indent=2))
    
    # Get summary statistics
    for interface in monitor.config['interfaces']:
        summary = monitor.get_summary_statistics(interface, hours=1)
        print(f"\nSummary for {interface}:")
        print(json.dumps(summary, indent=2))
    
    # Generate graph data
    graph_data = monitor.generate_graph_data('eth0', '1h')
    print(f"\nGraph data generated with {len(graph_data['labels'])} points")
    
    # Stop monitoring
    monitor.stop_monitoring()
    
    print("\nLatency monitoring test completed")

if __name__ == "__main__":
    main()