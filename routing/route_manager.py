#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Route Manager
Handles multipath routing, load balancing, and traffic distribution
"""

import subprocess
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class InterfaceState(Enum):
    UP = "up"
    DOWN = "down"
    TESTING = "testing"

@dataclass
class WANInterface:
    name: str
    gateway: str
    weight: int = 1
    state: InterfaceState = InterfaceState.UP
    latency: float = 0.0
    packet_loss: float = 0.0
    last_check: float = 0.0

class RouteManager:
    """Manages multipath routing and load balancing across multiple WAN interfaces"""
    
    def __init__(self, config_file: str = "/opt/routeros/config/interfaces.json"):
        self.config_file = config_file
        self.interfaces: Dict[str, WANInterface] = {}
        self.logger = logging.getLogger(__name__)
        self.routing_tables = {
            "wan1": 100,
            "wan2": 200,
            "wan3": 300
        }
        
        self._setup_logging()
        self._load_config()
        self._initialize_routing()
    
    def _setup_logging(self):
        """Configure logging for the route manager"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/routeros-routing.log'),
                logging.StreamHandler()
            ]
        )
    
    def _load_config(self):
        """Load interface configuration from JSON file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
            for iface_config in config.get('wan_interfaces', []):
                iface = WANInterface(
                    name=iface_config['name'],
                    gateway=iface_config['gateway'],
                    weight=iface_config.get('weight', 1)
                )
                self.interfaces[iface.name] = iface
                
            self.logger.info(f"Loaded {len(self.interfaces)} WAN interfaces")
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            # Default configuration
            self.interfaces = {
                'eth0': WANInterface('eth0', '192.168.100.1', weight=2),
                'eth1': WANInterface('eth1', '192.168.200.1', weight=1)
            }

    def add_interface(self, interface_config: Dict) -> bool:
        """Dynamically add a new WAN interface"""
        try:
            interface_name = interface_config['name']
            gateway = interface_config['gateway']
            weight = interface_config.get('weight', 1)
            
            # Check if interface already exists
            if interface_name in self.interfaces:
                self.logger.warning(f"Interface {interface_name} already exists")
                return False
            
            # Create new interface
            interface = WANInterface(
                name=interface_name,
                gateway=gateway,
                weight=weight,
                state=InterfaceState.UP
            )
            
            self.interfaces[interface_name] = interface
            
            # Add routing table for new interface
            table_id = 100 + len(self.interfaces)
            self.routing_tables[interface_name] = table_id
            
            # Configure routing for new interface
            self._update_interface_routing(interface, interface_name)
            
            # Update multipath routing
            self._configure_multipath_routing()
            
            self.logger.info(f"Successfully added interface {interface_name} with gateway {gateway}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add interface: {e}")
            return False
    
    def _run_command(self, command: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Execute system command and return result"""
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=check)
            return result
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {' '.join(command)} - {e}")
            raise
    
    def _initialize_routing(self):
        """Initialize routing tables and multipath configuration"""
        self.logger.info("Initializing routing configuration...")
        
        # Create custom routing tables
        for table_name, table_id in self.routing_tables.items():
            self._create_routing_table(table_name, table_id)
        
        # Configure multipath routing
        self._configure_multipath_routing()
        
        # Set up packet marking for sticky sessions
        self._setup_packet_marking()
        
        self.logger.info("Routing initialization complete")
    
    def _create_routing_table(self, name: str, table_id: int):
        """Create custom routing table"""
        try:
            # Add table to /etc/iproute2/rt_tables if not exists
            with open('/etc/iproute2/rt_tables', 'r') as f:
                content = f.read()
            
            if f"{table_id}\t{name}" not in content:
                with open('/etc/iproute2/rt_tables', 'a') as f:
                    f.write(f"{table_id}\t{name}\n")
                
            self.logger.info(f"Created routing table {name} (ID: {table_id})")
            
        except Exception as e:
            self.logger.error(f"Failed to create routing table {name}: {e}")
    
    def _configure_multipath_routing(self):
        """Configure ECMP (Equal-Cost Multi-Path) routing"""
        # Clear existing default routes
        self._run_command(['ip', 'route', 'del', 'default'], check=False)
        
        # Build multipath route command
        route_parts = []
        for iface_name, iface in self.interfaces.items():
            if iface.state == InterfaceState.UP:
                route_parts.extend(['nexthop', 'via', iface.gateway, 'dev', iface.name, 'weight', str(iface.weight)])
        
        if route_parts:
            command = ['ip', 'route', 'add', 'default'] + route_parts
            self._run_command(command)
            self.logger.info(f"Configured multipath routing: {' '.join(command)}")
        else:
            self.logger.warning("No active interfaces available for multipath routing")
    
    def _setup_packet_marking(self):
        """Configure nftables for packet marking and connection tracking"""
        try:
            # Create nftables rules for packet marking
            rules = [
                # Create table and chain
                "add table inet routeros",
                "add chain inet routeros prerouting { type filter hook prerouting priority -150; }",
                "add chain inet routeros postrouting { type filter hook postrouting priority 150; }",
                
                # Mark packets based on connection tracking
                "add rule inet routeros prerouting ct state new ct mark set 0x1 random mod 100",
                "add rule inet routeros prerouting ct state established,related ct mark set ct mark",
                
                # Mark high-priority traffic (VoIP, gaming)
                "add rule inet routeros prerouting ip dport { 5060, 5061 } ct mark set 0x10",  # SIP
                "add rule inet routeros prerouting ip dport { 27015, 27016 } ct mark set 0x20",  # Steam games
                "add rule inet routeros prerouting ip sport { 27015, 27016 } ct mark set 0x20",
                
                # Apply marks to packets for routing decisions
                "add rule inet routeros prerouting ct mark 0x10 meta mark set 0x10",
                "add rule inet routeros prerouting ct mark 0x20 meta mark set 0x20",
            ]
            
            for rule in rules:
                self._run_command(['nft', '-c', rule], check=False)
                
            self.logger.info("Packet marking configuration applied")
            
        except Exception as e:
            self.logger.error(f"Failed to setup packet marking: {e}")
    
    def update_interface_state(self, interface_name: str, state: InterfaceState, latency: float = 0.0, packet_loss: float = 0.0):
        """Update interface state and reconfigure routing if needed"""
        if interface_name in self.interfaces:
            old_state = self.interfaces[interface_name].state
            self.interfaces[interface_name].state = state
            self.interfaces[interface_name].latency = latency
            self.interfaces[interface_name].packet_loss = packet_loss
            self.interfaces[interface_name].last_check = time.time()
            
            if old_state != state:
                self.logger.info(f"Interface {interface_name} state changed: {old_state.value} -> {state.value}")
                self._reconfigure_routing()
    
    def _reconfigure_routing(self):
        """Reconfigure routing when interface states change"""
        self.logger.info("Reconfiguring routing due to interface state changes...")
        self._configure_multipath_routing()
        
        # Update routing tables for specific interfaces
        for iface_name, iface in self.interfaces.items():
            table_name = f"wan{list(self.interfaces.keys()).index(iface_name) + 1}"
            if iface.state == InterfaceState.UP:
                self._update_interface_routing(iface, table_name)
            else:
                self._remove_interface_routing(iface, table_name)
    
    def _update_interface_routing(self, iface: WANInterface, table_name: str):
        """Update routing table for specific interface"""
        try:
            table_id = self.routing_tables.get(table_name, 100)
            
            # Add route to interface-specific table
            self._run_command([
                'ip', 'route', 'add', 'default', 'via', iface.gateway, 'dev', iface.name,
                'table', str(table_id)
            ], check=False)
            
            # Add policy routing rule
            self._run_command([
                'ip', 'rule', 'add', 'from', 'all', 'iif', iface.name, 'table', str(table_id)
            ], check=False)
            
            self.logger.info(f"Updated routing for {iface.name} in table {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to update routing for {iface.name}: {e}")
    
    def _remove_interface_routing(self, iface: WANInterface, table_name: str):
        """Remove routing entries for failed interface"""
        try:
            table_id = self.routing_tables.get(table_name, 100)
            
            # Remove routes from interface-specific table
            self._run_command([
                'ip', 'route', 'flush', 'table', str(table_id)
            ], check=False)
            
            # Remove policy routing rules
            self._run_command([
                'ip', 'rule', 'del', 'from', 'all', 'iif', iface.name, 'table', str(table_id)
            ], check=False)
            
            # Flush connection tracking for this interface
            self._run_command([
                'conntrack', '-D', '-i', iface.name
            ], check=False)
            
            self.logger.info(f"Removed routing for {iface.name} from table {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to remove routing for {iface.name}: {e}")
    
    def get_interface_stats(self) -> Dict[str, Dict]:
        """Get current interface statistics"""
        stats = {}
        for iface_name, iface in self.interfaces.items():
            stats[iface_name] = {
                'state': iface.state.value,
                'gateway': iface.gateway,
                'weight': iface.weight,
                'latency': iface.latency,
                'packet_loss': iface.packet_loss,
                'last_check': iface.last_check
            }
        return stats
    
    def manual_interface_control(self, interface_name: str, action: str):
        """Manual control interface (for maintenance)"""
        if interface_name not in self.interfaces:
            self.logger.error(f"Interface {interface_name} not found")
            return False
        
        if action == "disable":
            self.update_interface_state(interface_name, InterfaceState.DOWN)
            self.logger.info(f"Manually disabled interface {interface_name}")
            return True
        elif action == "enable":
            self.update_interface_state(interface_name, InterfaceState.UP)
            self.logger.info(f"Manually enabled interface {interface_name}")
            return True
        else:
            self.logger.error(f"Unknown action: {action}")
            return False
    
    def get_routing_info(self) -> Dict:
        """Get current routing configuration information"""
        try:
            # Get main routing table
            result = self._run_command(['ip', 'route', 'show'])
            main_routes = result.stdout.strip()
            
            # Get multipath routes
            result = self._run_command(['ip', 'route', 'show', 'table', 'all'])
            all_routes = result.stdout.strip()
            
            # Get policy rules
            result = self._run_command(['ip', 'rule', 'show'])
            rules = result.stdout.strip()
            
            return {
                'main_routes': main_routes,
                'all_routes': all_routes,
                'policy_rules': rules,
                'interfaces': self.get_interface_stats()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get routing info: {e}")
            return {}

def main():
    """Main function for testing the route manager"""
    manager = RouteManager()
    
    # Test interface state updates
    print("Interface Statistics:")
    stats = manager.get_interface_stats()
    for iface, data in stats.items():
        print(f"  {iface}: {data}")
    
    # Test routing info
    print("\nRouting Information:")
    routing_info = manager.get_routing_info()
    print(f"Main routes: {routing_info.get('main_routes', 'N/A')}")
    
    # Test manual interface control
    print("\nTesting manual interface control...")
    manager.manual_interface_control('eth1', 'disable')
    time.sleep(2)
    manager.manual_interface_control('eth1', 'enable')

if __name__ == "__main__":
    main()