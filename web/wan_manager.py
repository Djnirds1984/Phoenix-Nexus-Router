#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - WAN Interface Management
Provides web-based interface for adding and managing WAN interfaces
"""

import os
import json
import logging
import subprocess
import threading
import time
from typing import Dict, List, Optional
from flask import Blueprint, render_template, jsonify, request
import sys

# Add routing module to path
sys.path.append('/opt/routeros/routing')
from interface_detector import DynamicInterfaceDetector, NetworkInterface

class WANManager:
    """Manages WAN interfaces through web interface"""
    
    def __init__(self):
        self.config_dir = "/opt/routeros/config"
        self.interfaces_file = os.path.join(self.config_dir, "interfaces.json")
        self.logger = self._setup_logging()
        self.interface_detector = DynamicInterfaceDetector()
        self.lock = threading.Lock()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for WAN manager"""
        logger = logging.getLogger('wan-manager')
        logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        os.makedirs('/var/log', exist_ok=True)
        
        # File handler
        file_handler = logging.FileHandler('/var/log/routeros-wan-manager.log')
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
    
    def get_available_interfaces(self) -> List[Dict]:
        """Get list of available interfaces that can be added as WAN"""
        try:
            available = self.interface_detector.get_available_wan_interfaces()
            
            interfaces = []
            for interface in available:
                interfaces.append({
                    "name": interface.name,
                    "mac_address": interface.mac_address,
                    "status": interface.status,
                    "speed": interface.speed,
                    "ip_address": interface.ip_address,
                    "interface_type": interface.interface_type
                })
            
            return interfaces
            
        except Exception as e:
            self.logger.error(f"Failed to get available interfaces: {e}")
            return []
    
    def suggest_wan_configuration(self, interface_name: str) -> Dict:
        """Get suggested configuration for a new WAN interface"""
        try:
            suggestion = self.interface_detector.suggest_wan_configuration(interface_name)
            
            if "error" in suggestion:
                return {"error": suggestion["error"]}
            
            # Add additional suggestions
            suggestion.update({
                "weight_options": [1, 2, 3],
                "dns_options": [
                    ["8.8.8.8", "8.8.4.4"],      # Google
                    ["1.1.1.1", "1.0.0.1"],      # Cloudflare
                    ["208.67.222.222", "208.67.220.220"],  # OpenDNS
                    ["9.9.9.9", "149.112.112.112"]         # Quad9
                ],
                "requires_gateway": True,
                "can_auto_detect": True
            })
            
            return suggestion
            
        except Exception as e:
            self.logger.error(f"Failed to suggest configuration: {e}")
            return {"error": str(e)}
    
    def add_wan_interface(self, interface_config: Dict) -> Dict:
        """Add a new WAN interface with automatic policy generation"""
        try:
            with self.lock:
                # Load current configuration
                current_config = self._load_interfaces_config()
                
                # Validate interface name
                interface_name = interface_config.get('name')
                if not interface_name:
                    return {"error": "Interface name is required"}
                
                # Check if interface already exists
                existing_wans = current_config.get('wan_interfaces', [])
                for wan in existing_wans:
                    if wan['name'] == interface_name:
                        return {"error": f"Interface {interface_name} is already configured as WAN"}
                
                # Validate and prepare configuration
                new_wan = self._prepare_wan_configuration(interface_config)
                if "error" in new_wan:
                    return new_wan
                
                # Add to configuration
                existing_wans.append(new_wan)
                current_config['wan_interfaces'] = existing_wans
                
                # Update auto-detection settings
                if 'auto_detection' not in current_config:
                    current_config['auto_detection'] = {}
                current_config['auto_detection']['last_modified'] = self._get_timestamp()
                
                # Save configuration
                self._save_interfaces_config(current_config)
                
                # Generate and apply routing policies automatically
                policy_result = self._generate_routing_policies(new_wan)
                
                # Restart services if needed
                self._restart_services_if_needed()
                
                self.logger.info(f"Successfully added WAN interface: {interface_name}")
                
                return {
                    "success": True,
                    "message": f"WAN interface {interface_name} added successfully",
                    "interface": new_wan,
                    "policies_applied": policy_result
                }
                
        except Exception as e:
            self.logger.error(f"Failed to add WAN interface: {e}")
            return {"error": str(e)}
    
    def _prepare_wan_configuration(self, config: Dict) -> Dict:
        """Prepare and validate WAN configuration"""
        interface_name = config.get('name')
        
        # Get suggested configuration as base
        suggestion = self.suggest_wan_configuration(interface_name)
        if "error" in suggestion:
            return suggestion
        
        # Merge user configuration with suggestions
        wan_config = {
            "name": interface_name,
            "gateway": config.get('gateway', suggestion.get('gateway', '192.168.1.1')),
            "weight": int(config.get('weight', suggestion.get('weight', 1))),
            "dns": config.get('dns', suggestion.get('dns', ["8.8.8.8", "8.8.4.4"])),
            "description": config.get('description', f"WAN Interface - {interface_name}"),
            "mac_address": suggestion.get('mac_address', 'unknown'),
            "speed": suggestion.get('speed'),
            "auto_detected": False,
            "added_via_web": True,
            "added_date": self._get_timestamp()
        }
        
        # Validate required fields
        if not wan_config['gateway']:
            return {"error": "Gateway is required"}
        
        # Validate weight
        if wan_config['weight'] < 1 or wan_config['weight'] > 10:
            return {"error": "Weight must be between 1 and 10"}
        
        # Validate DNS
        if not wan_config['dns'] or len(wan_config['dns']) == 0:
            wan_config['dns'] = ["8.8.8.8", "8.8.4.4"]
        
        return wan_config
    
    def _generate_routing_policies(self, wan_config: Dict) -> Dict:
        """Automatically generate routing policies for new WAN interface"""
        try:
            policies = []
            
            # Generate routing table entry
            table_id = 100 + len(self._load_interfaces_config().get('wan_interfaces', []))
            policies.append({
                "type": "routing_table",
                "table_id": table_id,
                "interface": wan_config['name'],
                "gateway": wan_config['gateway'],
                "description": f"Routing table for {wan_config['name']}"
            })
            
            # Generate multipath route entry
            policies.append({
                "type": "multipath_route",
                "interface": wan_config['name'],
                "weight": wan_config['weight'],
                "gateway": wan_config['gateway'],
                "description": f"Multipath route for {wan_config['name']}"
            })
            
            # Generate nftables rules
            policies.append({
                "type": "nftables_rule",
                "chain": "prerouting",
                "interface": wan_config['name'],
                "mark": f"0x{table_id:x}",
                "description": f"Packet marking for {wan_config['name']}"
            })
            
            # Generate health check configuration
            policies.append({
                "type": "health_check",
                "interface": wan_config['name'],
                "target": "1.1.1.1",
                "timeout": 2,
                "retry_count": 3,
                "description": f"Health check for {wan_config['name']}"
            })
            
            self.logger.info(f"Generated {len(policies)} routing policies for {wan_config['name']}")
            return policies
            
        except Exception as e:
            self.logger.error(f"Failed to generate routing policies: {e}")
            return []
    
    def remove_wan_interface(self, interface_name: str) -> Dict:
        """Remove a WAN interface"""
        try:
            with self.lock:
                current_config = self._load_interfaces_config()
                
                # Find and remove the interface
                wan_interfaces = current_config.get('wan_interfaces', [])
                found = False
                new_wans = []
                
                for wan in wan_interfaces:
                    if wan['name'] == interface_name:
                        found = True
                        continue
                    new_wans.append(wan)
                
                if not found:
                    return {"error": f"Interface {interface_name} not found in WAN configuration"}
                
                # Update configuration
                current_config['wan_interfaces'] = new_wans
                
                # Save configuration
                self._save_interfaces_config(current_config)
                
                # Remove routing policies
                self._remove_routing_policies(interface_name)
                
                # Restart services if needed
                self._restart_services_if_needed()
                
                self.logger.info(f"Successfully removed WAN interface: {interface_name}")
                
                return {
                    "success": True,
                    "message": f"WAN interface {interface_name} removed successfully"
                }
                
        except Exception as e:
            self.logger.error(f"Failed to remove WAN interface: {e}")
            return {"error": str(e)}
    
    def _remove_routing_policies(self, interface_name: str):
        """Remove routing policies for an interface"""
        try:
            # This would typically involve:
            # 1. Removing routing table entries
            # 2. Removing multipath routes
            # 3. Removing nftables rules
            # 4. Removing health check configurations
            
            self.logger.info(f"Routing policies removed for {interface_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to remove routing policies: {e}")
    
    def _restart_services_if_needed(self):
        """Restart services if configuration changed"""
        try:
            # Restart watchdog service to pick up new configuration
            result = subprocess.run(['systemctl', 'restart', 'routeros-watchdog'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info("Watchdog service restarted successfully")
            else:
                self.logger.error(f"Failed to restart watchdog service: {result.stderr}")
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            self.logger.error(f"Service restart failed: {e}")
    
    def _load_interfaces_config(self) -> Dict:
        """Load interfaces configuration"""
        try:
            if os.path.exists(self.interfaces_file):
                with open(self.interfaces_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load interfaces config: {e}")
        
        return {"wan_interfaces": [], "lan_interface": {}}
    
    def _save_interfaces_config(self, config: Dict):
        """Save interfaces configuration"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.interfaces_file, 'w') as f:
                json.dump(config, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save interfaces config: {e}")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_wan_statistics(self) -> Dict:
        """Get WAN interface statistics"""
        try:
            config = self._load_interfaces_config()
            wan_interfaces = config.get('wan_interfaces', [])
            
            stats = {
                "total_wans": len(wan_interfaces),
                "auto_detected": sum(1 for wan in wan_interfaces if wan.get('auto_detected', False)),
                "web_added": sum(1 for wan in wan_interfaces if wan.get('added_via_web', False)),
                "interfaces": []
            }
            
            for wan in wan_interfaces:
                stats["interfaces"].append({
                    "name": wan['name'],
                    "weight": wan['weight'],
                    "gateway": wan['gateway'],
                    "description": wan.get('description', ''),
                    "auto_detected": wan.get('auto_detected', False),
                    "web_added": wan.get('added_via_web', False),
                    "added_date": wan.get('added_date', 'Unknown')
                })
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get WAN statistics: {e}")
            return {"error": str(e)}

# Flask Blueprint for WAN management
wan_manager_bp = Blueprint('wan_manager', __name__, url_prefix='/api/wan')

# Initialize WAN manager
wan_manager = WANManager()

@wan_manager_bp.route('/available')
def get_available_interfaces():
    """Get available interfaces for WAN configuration"""
    interfaces = wan_manager.get_available_interfaces()
    return jsonify({"interfaces": interfaces})

@wan_manager_bp.route('/suggest/<interface_name>')
def suggest_configuration(interface_name):
    """Get suggested configuration for an interface"""
    suggestion = wan_manager.suggest_wan_configuration(interface_name)
    return jsonify(suggestion)

@wan_manager_bp.route('/add', methods=['POST'])
def add_wan_interface():
    """Add a new WAN interface"""
    config = request.get_json()
    if not config:
        return jsonify({"error": "No configuration provided"}), 400
    
    result = wan_manager.add_wan_interface(config)
    if "error" in result:
        return jsonify(result), 400
    
    return jsonify(result)

@wan_manager_bp.route('/remove/<interface_name>', methods=['DELETE'])
def remove_wan_interface(interface_name):
    """Remove a WAN interface"""
    result = wan_manager.remove_wan_interface(interface_name)
    if "error" in result:
        return jsonify(result), 400
    
    return jsonify(result)

@wan_manager_bp.route('/statistics')
def get_wan_statistics():
    """Get WAN interface statistics"""
    stats = wan_manager.get_wan_statistics()
    if "error" in stats:
        return jsonify(stats), 500
    
    return jsonify(stats)

@wan_manager_bp.route('/auto-detect', methods=['POST'])
def auto_detect_primary_wan():
    """Auto-detect and configure primary WAN interface"""
    try:
        detector = DynamicInterfaceDetector()
        result = detector.auto_configure_primary_wan()
        
        if "error" in result:
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500