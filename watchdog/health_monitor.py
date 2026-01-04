#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Health Monitor Watchdog
Performs continuous health checks, ICMP probing, and intelligent failover
"""

import subprocess
import time
import logging
import threading
import json
import signal
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    TESTING = "testing"

@dataclass
class HealthCheckResult:
    interface: str
    status: HealthStatus
    latency: float
    packet_loss: float
    timestamp: float
    consecutive_failures: int
    last_success: float
    error_message: str = ""

class HealthMonitor:
    """Monitors WAN interface health and triggers failover when needed"""
    
    def __init__(self, config_file: str = "/opt/routeros/config/health_monitor.json"):
        self.config_file = config_file
        self.interfaces: Dict[str, Dict] = {}
        self.health_results: Dict[str, HealthCheckResult] = {}
        self.monitoring_active = False
        self.monitor_thread = None
        self.logger = logging.getLogger(__name__)
        
        # Default configuration
        self.config = {
            'ping_target': '1.1.1.1',
            'timeout_seconds': 2,
            'retry_count': 3,
            'check_interval': 5,
            'recovery_interval': 30,
            'max_latency_ms': 2000,
            'max_packet_loss': 5.0,
            'interfaces': [
                {'name': 'eth0', 'gateway': '192.168.100.1', 'weight': 2},
                {'name': 'eth1', 'gateway': '192.168.200.1', 'weight': 1}
            ]
        }
        
        self._setup_logging()
        self._load_config()
        self._initialize_health_tracking()
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_logging(self):
        """Configure logging for health monitor"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/routeros-health.log'),
                logging.StreamHandler()
            ]
        )
    
    def _load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                loaded_config = json.load(f)
                self.config.update(loaded_config)
            self.logger.info(f"Loaded configuration from {self.config_file}")
        except FileNotFoundError:
            self.logger.warning(f"Config file {self.config_file} not found, using defaults")
            self._save_config()
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}, using defaults")
    
    def _save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            self.logger.info(f"Saved configuration to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
    
    def _initialize_health_tracking(self):
        """Initialize health tracking for all interfaces"""
        current_time = time.time()
        
        for iface_config in self.config['interfaces']:
            iface_name = iface_config['name']
            
            self.interfaces[iface_name] = {
                'config': iface_config,
                'enabled': True,
                'last_check': 0,
                'consecutive_failures': 0,
                'total_checks': 0,
                'successful_checks': 0,
                'failed_checks': 0
            }
            
            # Initialize health result
            self.health_results[iface_name] = HealthCheckResult(
                interface=iface_name,
                status=HealthStatus.TESTING,
                latency=0.0,
                packet_loss=0.0,
                timestamp=current_time,
                consecutive_failures=0,
                last_success=current_time
            )
            
            self.logger.info(f"Initialized health tracking for {iface_name}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop_monitoring()
        sys.exit(0)
    
    def _run_ping_test(self, interface: str, target: str, count: int = 3) -> Tuple[float, float, str]:
        """
        Run ping test through specific interface
        Returns: (avg_latency, packet_loss, error_message)
        """
        try:
            # Use ping with specific interface binding
            cmd = [
                'ping', '-I', interface, '-c', str(count), '-W', '2',
                '-q', target
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return 0.0, 100.0, f"Ping failed: {result.stderr}"
            
            # Parse ping output
            output_lines = result.stdout.strip().split('\n')
            stats_line = None
            
            for line in output_lines:
                if 'packet loss' in line:
                    stats_line = line
                    break
            
            if not stats_line:
                return 0.0, 100.0, "Could not parse ping output"
            
            # Extract packet loss percentage
            packet_loss = 0.0
            if 'packet loss' in stats_line:
                parts = stats_line.split(',')
                for part in parts:
                    if 'packet loss' in part:
                        packet_loss = float(part.strip().split('%')[0])
                        break
            
            # Extract average latency
            latency = 0.0
            for line in output_lines:
                if 'rtt' in line and 'avg' in line:
                    # Parse: rtt min/avg/max/mdev = 10.123/15.456/20.789/3.123 ms
                    parts = line.split('=')[1].strip().split('/')
                    if len(parts) >= 2:
                        latency = float(parts[1])
                    break
            
            return latency, packet_loss, ""
            
        except subprocess.TimeoutExpired:
            return 0.0, 100.0, "Ping timeout"
        except Exception as e:
            return 0.0, 100.0, f"Ping error: {str(e)}"
    
    def _check_interface_health(self, interface: str) -> HealthCheckResult:
        """Perform health check on specific interface"""
        iface_info = self.interfaces[interface]
        config = self.config
        current_time = time.time()
        
        # Update check counters
        iface_info['total_checks'] += 1
        iface_info['last_check'] = current_time
        
        # Perform ping test
        latency, packet_loss, error_msg = self._run_ping_test(
            interface, config['ping_target'], config['retry_count']
        )
        
        # Determine health status
        if packet_loss >= 100.0:
            status = HealthStatus.FAILED
            iface_info['consecutive_failures'] += 1
            iface_info['failed_checks'] += 1
            error_msg = "Complete packet loss"
        elif packet_loss > config['max_packet_loss'] or latency > config['max_latency_ms']:
            status = HealthStatus.DEGRADED
            iface_info['consecutive_failures'] += 1
            iface_info['failed_checks'] += 1
        else:
            status = HealthStatus.HEALTHY
            iface_info['consecutive_failures'] = 0
            iface_info['successful_checks'] += 1
        
        # Create health result
        health_result = HealthCheckResult(
            interface=interface,
            status=status,
            latency=latency,
            packet_loss=packet_loss,
            timestamp=current_time,
            consecutive_failures=iface_info['consecutive_failures'],
            last_success=current_time if status == HealthStatus.HEALTHY else iface_info.get('last_success', current_time),
            error_message=error_msg
        )
        
        # Store result
        self.health_results[interface] = health_result
        
        # Log results
        self.logger.info(
            f"Health check {interface}: {status.value} "
            f"(latency: {latency:.1f}ms, loss: {packet_loss:.1f}%, "
            f"failures: {iface_info['consecutive_failures']})"
        )
        
        return health_result
    
    def _should_trigger_failover(self, interface: str) -> bool:
        """Determine if failover should be triggered for interface"""
        health_result = self.health_results[interface]
        config = self.config
        
        # Check consecutive failure threshold
        if health_result.consecutive_failures >= config['retry_count']:
            self.logger.warning(f"Interface {interface} failed {health_result.consecutive_failures} consecutive checks")
            return True
        
        # Check if completely failed
        if health_result.status == HealthStatus.FAILED:
            self.logger.warning(f"Interface {interface} completely failed (100% packet loss)")
            return True
        
        return False
    
    def _trigger_failover(self, interface: str):
        """Trigger failover for specific interface"""
        self.logger.warning(f"Triggering failover for interface {interface}")
        
        # Disable interface in health tracking
        self.interfaces[interface]['enabled'] = False
        
        # Update health status
        self.health_results[interface].status = HealthStatus.FAILED
        
        # Trigger routing reconfiguration (this would interface with RouteManager)
        self._reconfigure_routing()
        
        # Log failover event
        self._log_event('FAILOVER', f"Interface {interface} failed over", {
            'interface': interface,
            'latency': self.health_results[interface].latency,
            'packet_loss': self.health_results[interface].packet_loss,
            'consecutive_failures': self.health_results[interface].consecutive_failures
        })
        
        self.logger.warning(f"Failover completed for interface {interface}")
    
    def _reconfigure_routing(self):
        """Reconfigure routing based on current interface states"""
        # This would interface with the RouteManager class
        # For now, we'll log the action
        active_interfaces = [
            iface for iface, info in self.interfaces.items() 
            if info['enabled'] and self.health_results[iface].status == HealthStatus.HEALTHY
        ]
        
        self.logger.info(f"Reconfiguring routing with active interfaces: {active_interfaces}")
        
        # In a real implementation, this would call RouteManager.update_interface_state()
        # For demonstration, we'll create a simple routing update script
        self._update_routing_tables(active_interfaces)
    
    def _update_routing_tables(self, active_interfaces: List[str]):
        """Update system routing tables based on active interfaces"""
        try:
            # Remove old default routes
            subprocess.run(['ip', 'route', 'flush', 'table', 'main'], 
                         capture_output=True, check=False)
            
            # Add multipath routes for active interfaces
            if active_interfaces:
                route_cmd = ['ip', 'route', 'add', 'default']
                
                for interface in active_interfaces:
                    iface_info = self.interfaces[interface]
                    gateway = iface_info['config']['gateway']
                    weight = iface_info['config']['weight']
                    
                    route_cmd.extend(['nexthop', 'via', gateway, 'dev', interface, 'weight', str(weight)])
                
                # Execute route command
                result = subprocess.run(route_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.logger.info(f"Updated routing: {' '.join(route_cmd)}")
                else:
                    self.logger.error(f"Failed to update routing: {result.stderr}")
            else:
                self.logger.warning("No active interfaces available for routing")
                
        except Exception as e:
            self.logger.error(f"Error updating routing tables: {e}")
    
    def _check_recovery(self, interface: str) -> bool:
        """Check if a failed interface has recovered"""
        iface_info = self.interfaces[interface]
        
        # Skip if interface is not failed
        if iface_info['enabled']:
            return False
        
        # Check if enough time has passed for recovery attempt
        current_time = time.time()
        last_check = iface_info.get('last_recovery_check', 0)
        
        if current_time - last_check < self.config['recovery_interval']:
            return False
        
        iface_info['last_recovery_check'] = current_time
        
        # Perform recovery test
        self.logger.info(f"Testing recovery for interface {interface}")
        
        # Temporarily enable for testing
        iface_info['enabled'] = True
        health_result = self._check_interface_health(interface)
        
        if health_result.status == HealthStatus.HEALTHY:
            self.logger.info(f"Interface {interface} has recovered!")
            
            # Log recovery event
            self._log_event('RECOVERY', f"Interface {interface} recovered", {
                'interface': interface,
                'latency': health_result.latency,
                'packet_loss': health_result.packet_loss
            })
            
            return True
        else:
            # Still failed, disable again
            iface_info['enabled'] = False
            self.logger.info(f"Interface {interface} still failed, will retry later")
            return False
    
    def _log_event(self, event_type: str, message: str, data: Dict = None):
        """Log system event"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'message': message,
            'data': data or {}
        }
        
        # Log to file
        self.logger.info(f"EVENT: {event_type} - {message}")
        
        # Store in event log (would be in database in production)
        try:
            with open('/var/log/routeros-events.log', 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write event log: {e}")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        self.logger.info("Health monitoring started")
        
        while self.monitoring_active:
            try:
                # Check all interfaces
                for interface in self.interfaces:
                    iface_info = self.interfaces[interface]
                    
                    # Skip disabled interfaces (unless checking for recovery)
                    if not iface_info['enabled']:
                        self._check_recovery(interface)
                        continue
                    
                    # Perform health check
                    health_result = self._check_interface_health(interface)
                    
                    # Check if failover should be triggered
                    if self._should_trigger_failover(interface):
                        self._trigger_failover(interface)
                
                # Wait for next check interval
                time.sleep(self.config['check_interval'])
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.config['check_interval'])
        
        self.logger.info("Health monitoring stopped")
    
    def start_monitoring(self):
        """Start health monitoring"""
        if self.monitoring_active:
            self.logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Health monitoring started")
        self._log_event('START', "Health monitoring service started")
    
    def stop_monitoring(self):
        """Stop health monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        self.logger.info("Health monitoring stopped")
        self._log_event('STOP', "Health monitoring service stopped")
    
    def get_health_status(self) -> Dict[str, HealthCheckResult]:
        """Get current health status for all interfaces"""
        return self.health_results.copy()
    
    def get_interface_stats(self) -> Dict:
        """Get interface statistics"""
        stats = {}
        
        for interface, iface_info in self.interfaces.items():
            health_result = self.health_results[interface]
            
            stats[interface] = {
                'enabled': iface_info['enabled'],
                'total_checks': iface_info['total_checks'],
                'successful_checks': iface_info['successful_checks'],
                'failed_checks': iface_info['failed_checks'],
                'consecutive_failures': health_result.consecutive_failures,
                'uptime_percentage': (
                    (iface_info['successful_checks'] / max(iface_info['total_checks'], 1)) * 100
                ),
                'current_status': health_result.status.value,
                'current_latency': health_result.latency,
                'current_packet_loss': health_result.packet_loss,
                'last_check': datetime.fromtimestamp(health_result.timestamp).isoformat()
            }
        
        return stats
    
    def manual_interface_control(self, interface: str, action: str) -> bool:
        """Manual control of interface (for maintenance)"""
        if interface not in self.interfaces:
            self.logger.error(f"Interface {interface} not found")
            return False
        
        if action == "disable":
            self.interfaces[interface]['enabled'] = False
            self.health_results[interface].status = HealthStatus.FAILED
            self._log_event('MANUAL_DISABLE', f"Interface {interface} manually disabled")
            self.logger.info(f"Manually disabled interface {interface}")
            return True
        
        elif action == "enable":
            self.interfaces[interface]['enabled'] = True
            self.health_results[interface].status = HealthStatus.TESTING
            self._log_event('MANUAL_ENABLE', f"Interface {interface} manually enabled")
            self.logger.info(f"Manually enabled interface {interface}")
            return True
        
        else:
            self.logger.error(f"Unknown action: {action}")
            return False
    
    def get_system_status(self) -> Dict:
        """Get overall system status"""
        healthy_interfaces = sum(
            1 for result in self.health_results.values() 
            if result.status == HealthStatus.HEALTHY
        )
        
        total_interfaces = len(self.interfaces)
        
        return {
            'monitoring_active': self.monitoring_active,
            'healthy_interfaces': healthy_interfaces,
            'total_interfaces': total_interfaces,
            'system_health': 'healthy' if healthy_interfaces > 0 else 'failed',
            'uptime': time.time() - getattr(self, 'start_time', time.time()),
            'config': {
                'ping_target': self.config['ping_target'],
                'check_interval': self.config['check_interval'],
                'timeout_seconds': self.config['timeout_seconds']
            }
        }

def main():
    """Main function for testing the health monitor"""
    monitor = HealthMonitor()
    
    # Test health checks
    print("Testing health checks...")
    for interface in monitor.interfaces:
        result = monitor._check_interface_health(interface)
        print(f"{interface}: {result.status.value} (latency: {result.latency:.1f}ms, loss: {result.packet_loss:.1f}%)")
    
    # Test failover logic
    print("\nTesting failover logic...")
    for interface in monitor.interfaces:
        should_failover = monitor._should_trigger_failover(interface)
        print(f"{interface}: Should failover: {should_failover}")
    
    # Display system status
    print("\nSystem Status:")
    status = monitor.get_system_status()
    print(json.dumps(status, indent=2))
    
    # Display interface stats
    print("\nInterface Statistics:")
    stats = monitor.get_interface_stats()
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()