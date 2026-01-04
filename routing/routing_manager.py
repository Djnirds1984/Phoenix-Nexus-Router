#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Routing Manager Service
Main service that coordinates routing, load balancing, and interface management
"""

import os
import sys
import json
import time
import logging
import signal
import threading
from typing import Dict, List, Optional
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from route_manager import RouteManager
from interface_detector import DynamicInterfaceDetector

class RoutingManagerService:
    """Main routing manager service that coordinates all routing operations"""
    
    def __init__(self):
        self.config_file = "/opt/routeros/config/interfaces.json"
        self.status_file = "/opt/routeros/web/status.json"
        self.running = False
        self.logger = self._setup_logging()
        self.route_manager = None
        self.interface_detector = DynamicInterfaceDetector()
        self.update_interval = 30  # seconds
        self.service_thread = None
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for the routing manager service"""
        logger = logging.getLogger('routing-manager-service')
        logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        os.makedirs('/var/log', exist_ok=True)
        
        # File handler
        file_handler = logging.FileHandler('/var/log/routeros-routing-manager.log')
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
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)
    
    def load_configuration(self) -> Dict:
        """Load interface configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                self.logger.warning(f"Configuration file {self.config_file} not found, using defaults")
                return self.create_default_config()
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            return self.create_default_config()
    
    def create_default_config(self) -> Dict:
        """Create default configuration if none exists"""
        default_config = {
            "interfaces": {
                "eth0": {
                    "type": "wan",
                    "weight": 2,
                    "enabled": True,
                    "gateway": "192.168.1.1",
                    "health_check": {
                        "enabled": True,
                        "target": "8.8.8.8",
                        "interval": 10,
                        "timeout": 2,
                        "retries": 3
                    }
                }
            }
        }
        
        # Save default config
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            self.logger.info("Created default configuration file")
        except Exception as e:
            self.logger.error(f"Error saving default configuration: {e}")
        
        return default_config
    
    def initialize_route_manager(self, config: Dict):
        """Initialize the route manager with configuration"""
        try:
            # Try to initialize with config file
            if os.path.exists(self.config_file):
                self.route_manager = RouteManager(self.config_file)
            else:
                # Create route manager with default config
                self.route_manager = RouteManager()
            self.logger.info("Route manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing route manager: {e}")
            # Create a minimal route manager as fallback
            try:
                self.route_manager = RouteManager(config_file=None)
                self.logger.info("Created minimal route manager with fallback settings")
            except Exception as e2:
                self.logger.error(f"Failed to create minimal route manager: {e2}")
                self.route_manager = None
    
    def update_service_status(self, status: str, message: str = ""):
        """Update service status file for web interface"""
        try:
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            
            status_data = {
                "routing_manager": {
                    "status": status,
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "uptime": time.time() - getattr(self, 'start_time', time.time()),
                    "interfaces": self.get_interface_status() if self.route_manager else {}
                }
            }
            
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error updating service status: {e}")
    
    def get_interface_status(self) -> Dict:
        """Get current interface status from route manager"""
        if not self.route_manager:
            return {}
        
        try:
            # This would interface with the route manager's interface tracking
            return {
                "total_interfaces": len(self.route_manager.interfaces),
                "active_interfaces": len([i for i in self.route_manager.interfaces.values() if i.state.value == "up"]),
                "interface_details": {
                    name: {
                        "state": iface.state.value,
                        "weight": iface.weight,
                        "latency": iface.latency,
                        "packet_loss": iface.packet_loss
                    }
                    for name, iface in self.route_manager.interfaces.items()
                }
            }
        except Exception as e:
            self.logger.error(f"Error getting interface status: {e}")
            return {}
    
    def service_loop(self):
        """Main service loop that runs continuously"""
        self.logger.info("Starting routing manager service loop...")
        self.start_time = time.time()
        
        while self.running:
            try:
                # Update service status
                self.update_service_status("running", "Service operational")
                
                # Check for configuration changes
                current_config = self.load_configuration()
                
                # Update routing tables if needed
                if self.route_manager:
                    # This would handle dynamic configuration updates
                    pass
                
                # Log status periodically
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    self.logger.info(f"Service running - {self.get_interface_status()}")
                
                # Sleep for update interval
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in service loop: {e}")
                self.update_service_status("error", str(e))
                time.sleep(10)  # Shorter sleep on error
    
    def start(self):
        """Start the routing manager service"""
        self.logger.info("Starting Phoenix Nexus Router OS Routing Manager Service...")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        try:
            # Load configuration
            config = self.load_configuration()
            self.logger.info(f"Loaded configuration: {json.dumps(config, indent=2)}")
            
            # Initialize route manager
            self.initialize_route_manager(config)
            
            # Start service loop
            self.running = True
            self.service_thread = threading.Thread(target=self.service_loop)
            self.service_thread.daemon = True
            self.service_thread.start()
            
            self.logger.info("Routing Manager Service started successfully")
            self.update_service_status("running", "Service started")
            
            # Keep main thread alive
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Failed to start routing manager service: {e}")
            self.update_service_status("error", str(e))
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Stop the routing manager service"""
        self.logger.info("Stopping Phoenix Nexus Router OS Routing Manager Service...")
        self.running = False
        
        if self.service_thread and self.service_thread.is_alive():
            self.service_thread.join(timeout=5)
        
        self.update_service_status("stopped", "Service stopped")
        self.logger.info("Routing Manager Service stopped")

def main():
    """Main entry point for the routing manager service"""
    service = RoutingManagerService()
    
    try:
        service.start()
    except KeyboardInterrupt:
        service.logger.info("Received keyboard interrupt, shutting down...")
        service.stop()
    except Exception as e:
        service.logger.error(f"Unexpected error: {e}")
        service.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()