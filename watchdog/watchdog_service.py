#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Main Watchdog Service
Integrates health monitoring, routing management, and connection tracking
"""

import sys
import os
import time
import json
import logging
import signal
from typing import Dict, Optional

# Add the routing module to path
sys.path.append('/opt/routeros/routing')

from health_monitor import HealthMonitor, HealthStatus
from route_manager import RouteManager, InterfaceState
from connection_tracker import ConnectionTracker

class RouterOSWatchdog:
    """Main watchdog service that coordinates all components"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.running = False
        
        # Initialize components
        self.route_manager: Optional[RouteManager] = None
        self.health_monitor: Optional[HealthMonitor] = None
        self.connection_tracker: Optional[ConnectionTracker] = None
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("RouterOS Watchdog initializing...")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup comprehensive logging"""
        # Create logs directory if it doesn't exist
        os.makedirs('/var/log', exist_ok=True)
        
        logger = logging.getLogger('routeros-watchdog')
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler('/var/log/routeros-watchdog.log')
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def initialize_components(self):
        """Initialize all watchdog components"""
        try:
            self.logger.info("Initializing Route Manager...")
            self.route_manager = RouteManager()
            
            self.logger.info("Initializing Connection Tracker...")
            self.connection_tracker = ConnectionTracker()
            
            self.logger.info("Initializing Health Monitor...")
            self.health_monitor = HealthMonitor()
            
            # Set up component integration
            self._setup_component_integration()
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise
    
    def _setup_component_integration(self):
        """Set up integration between components"""
        # Override health monitor's routing update method to use our route manager
        original_reconfigure_routing = self.health_monitor._reconfigure_routing
        
        def integrated_reconfigure_routing():
            """Integrated routing reconfiguration"""
            self.logger.info("Integrated routing reconfiguration triggered")
            
            # Get current interface states from health monitor
            health_status = self.health_monitor.get_health_status()
            
            # Update route manager interface states
            for interface, health_result in health_status.items():
                if health_result.status == HealthStatus.HEALTHY:
                    self.route_manager.update_interface_state(
                        interface, InterfaceState.UP,
                        health_result.latency, health_result.packet_loss
                    )
                elif health_result.status == HealthStatus.FAILED:
                    self.route_manager.update_interface_state(
                        interface, InterfaceState.DOWN,
                        health_result.latency, health_result.packet_loss
                    )
                else:
                    self.route_manager.update_interface_state(
                        interface, InterfaceState.TESTING,
                        health_result.latency, health_result.packet_loss
                    )
            
            # Call original method for any additional processing
            original_reconfigure_routing()
        
        self.health_monitor._reconfigure_routing = integrated_reconfigure_routing
        
        # Override manual interface control to sync between components
        original_manual_control = self.health_monitor.manual_interface_control
        
        def integrated_manual_control(interface: str, action: str) -> bool:
            """Integrated manual interface control"""
            result = original_manual_control(interface, action)
            
            if result:
                # Sync with route manager
                if action == "disable":
                    self.route_manager.update_interface_state(interface, InterfaceState.DOWN)
                elif action == "enable":
                    self.route_manager.update_interface_state(interface, InterfaceState.UP)
                
                self.logger.info(f"Integrated manual control: {interface} {action}")
            
            return result
        
        self.health_monitor.manual_interface_control = integrated_manual_control
    
    def start(self):
        """Start the watchdog service"""
        if self.running:
            self.logger.warning("Watchdog service already running")
            return
        
        try:
            self.logger.info("Starting RouterOS Watchdog service...")
            
            # Initialize components
            self.initialize_components()
            
            # Start health monitoring
            if self.health_monitor:
                self.health_monitor.start_monitoring()
            
            self.running = True
            self.logger.info("RouterOS Watchdog service started successfully")
            
            # Create PID file
            with open('/var/run/routeros-watchdog.pid', 'w') as f:
                f.write(str(os.getpid()))
            
            # Main service loop
            self._service_loop()
            
        except Exception as e:
            self.logger.error(f"Failed to start watchdog service: {e}")
            self.stop()
            raise
    
    def _service_loop(self):
        """Main service loop"""
        self.logger.info("Entering main service loop...")
        
        while self.running:
            try:
                # Periodic health check and status reporting
                self._periodic_health_check()
                
                # Sleep for a short interval
                time.sleep(10)
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                self.logger.error(f"Error in service loop: {e}")
                time.sleep(5)
        
        self.logger.info("Exiting main service loop")
    
    def _periodic_health_check(self):
        """Perform periodic health checks and status reporting"""
        try:
            # Get current system status
            system_status = self.get_system_status()
            
            # Log periodic status
            healthy_count = system_status['health_monitor']['healthy_interfaces']
            total_count = system_status['health_monitor']['total_interfaces']
            
            if healthy_count == 0:
                self.logger.error(f"CRITICAL: No healthy interfaces available ({healthy_count}/{total_count})")
            elif healthy_count < total_count:
                self.logger.warning(f"WARNING: Some interfaces are down ({healthy_count}/{total_count})")
            else:
                self.logger.info(f"All interfaces healthy ({healthy_count}/{total_count})")
            
            # Write status to file for web interface
            self._write_status_file(system_status)
            
        except Exception as e:
            self.logger.error(f"Error in periodic health check: {e}")
    
    def _write_status_file(self, status: Dict):
        """Write system status to file for web interface"""
        try:
            status_file = '/opt/routeros/web/status.json'
            os.makedirs(os.path.dirname(status_file), exist_ok=True)
            
            with open(status_file, 'w') as f:
                json.dump(status, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to write status file: {e}")
    
    def stop(self):
        """Stop the watchdog service"""
        if not self.running:
            return
        
        self.logger.info("Stopping RouterOS Watchdog service...")
        self.running = False
        
        # Stop health monitoring
        if self.health_monitor:
            self.health_monitor.stop_monitoring()
        
        # Remove PID file
        try:
            os.remove('/var/run/routeros-watchdog.pid')
        except FileNotFoundError:
            pass
        
        self.logger.info("RouterOS Watchdog service stopped")
    
    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        status = {
            'timestamp': time.time(),
            'service_running': self.running,
            'components': {}
        }
        
        # Health monitor status
        if self.health_monitor:
            status['components']['health_monitor'] = self.health_monitor.get_system_status()
            status['components']['health_monitor']['interfaces'] = self.health_monitor.get_interface_stats()
        
        # Route manager status
        if self.route_manager:
            status['components']['route_manager'] = {
                'interfaces': self.route_manager.get_interface_stats(),
                'routing_info': self.route_manager.get_routing_info()
            }
        
        # Connection tracker status
        if self.connection_tracker:
            status['components']['connection_tracker'] = {
                'stats': self.connection_tracker.get_connection_stats(),
                'active_connections': len(self.connection_tracker.get_active_connections()),
                'sticky_sessions': len(self.connection_tracker.sticky_sessions)
            }
        
        # Overall system health
        if self.health_monitor:
            healthy_interfaces = status['components']['health_monitor']['healthy_interfaces']
            total_interfaces = status['components']['health_monitor']['total_interfaces']
            
            if healthy_interfaces == total_interfaces:
                status['overall_health'] = 'healthy'
            elif healthy_interfaces > 0:
                status['overall_health'] = 'degraded'
            else:
                status['overall_health'] = 'failed'
        else:
            status['overall_health'] = 'unknown'
        
        return status
    
    def manual_interface_control(self, interface: str, action: str) -> bool:
        """Manual control of interface through health monitor"""
        if not self.health_monitor:
            self.logger.error("Health monitor not available")
            return False
        
        return self.health_monitor.manual_interface_control(interface, action)
    
    def get_logs(self, lines: int = 100) -> str:
        """Get recent log entries"""
        try:
            with open('/var/log/routeros-watchdog.log', 'r') as f:
                log_lines = f.readlines()
                return ''.join(log_lines[-lines:])
        except Exception as e:
            return f"Failed to read logs: {e}"

def main():
    """Main entry point for the watchdog service"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Multi-WAN Router OS Watchdog Service')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--status', action='store_true', help='Show status and exit')
    parser.add_argument('--test', action='store_true', help='Run tests and exit')
    parser.add_argument('--interface-control', nargs=2, metavar=('INTERFACE', 'ACTION'), 
                       help='Manual interface control (enable/disable)')
    
    args = parser.parse_args()
    
    # Handle interface control command
    if args.interface_control:
        interface, action = args.interface_control
        if action not in ['enable', 'disable']:
            print(f"Error: Invalid action '{action}'. Must be 'enable' or 'disable'")
            sys.exit(1)
        
        # Create watchdog instance for interface control
        watchdog = RouterOSWatchdog()
        try:
            watchdog.initialize_components()
            result = watchdog.manual_interface_control(interface, action)
            if result:
                print(f"✓ Interface {interface} {action}d successfully")
                sys.exit(0)
            else:
                print(f"✗ Failed to {action} interface {interface}")
                sys.exit(1)
        except Exception as e:
            print(f"✗ Error controlling interface: {e}")
            sys.exit(1)
    
    if args.status:
        # Show status and exit
        try:
            with open('/opt/routeros/web/status.json', 'r') as f:
                status = json.load(f)
                print(json.dumps(status, indent=2))
        except Exception as e:
            print(f"Failed to get status: {e}")
        return
    
    if args.test:
        # Run tests
        print("Running watchdog tests...")
        watchdog = RouterOSWatchdog()
        
        # Test component initialization
        try:
            watchdog.initialize_components()
            print("✓ Components initialized successfully")
        except Exception as e:
            print(f"✗ Component initialization failed: {e}")
            return
        
        # Test status reporting
        status = watchdog.get_system_status()
        print("✓ System status retrieved successfully")
        print(f"Overall health: {status.get('overall_health', 'unknown')}")
        
        return
    
    # Run as service
    watchdog = RouterOSWatchdog()
    
    try:
        watchdog.start()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
        watchdog.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        watchdog.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()