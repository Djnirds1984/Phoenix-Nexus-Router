#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Dynamic Interface Detection and Auto-Configuration
Automatically detects network interfaces and configures primary WAN for initial access
"""

import os
import json
import subprocess
import logging
import ipaddress
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class NetworkInterface:
    """Represents a network interface"""
    name: str
    mac_address: str
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: List[str] = None
    interface_type: str = "unknown"  # wan, lan, or unknown
    status: str = "down"
    speed: Optional[str] = None
    carrier: bool = False
    
    def __post_init__(self):
        if self.dns_servers is None:
            self.dns_servers = []

class DynamicInterfaceDetector:
    """Automatically detects and configures network interfaces"""
    
    def __init__(self, config_dir: str = "/opt/routeros/config"):
        self.config_dir = config_dir
        self.interfaces_file = os.path.join(config_dir, "interfaces.json")
        self.auto_detect_file = os.path.join(config_dir, "auto_detected.json")
        self.logger = self._setup_logging()
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for interface detection"""
        logger = logging.getLogger('interface-detector')
        logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        os.makedirs('/var/log', exist_ok=True)
        
        # File handler
        file_handler = logging.FileHandler('/var/log/routeros-interface-detector.log')
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
    
    def detect_all_interfaces(self) -> List[NetworkInterface]:
        """Detect all network interfaces on the system"""
        interfaces = []
        
        try:
            # Get interface list from ip command
            result = subprocess.run(['ip', '-j', 'link', 'show'], 
                                  capture_output=True, text=True, check=True)
            
            link_data = json.loads(result.stdout)
            
            for link in link_data:
                if link.get('ifname') == 'lo':  # Skip loopback
                    continue
                    
                interface = NetworkInterface(
                    name=link.get('ifname', 'unknown'),
                    mac_address=link.get('address', 'unknown'),
                    status=link.get('operstate', 'down'),
                    carrier=link.get('link_type') == 'ether'
                )
                
                # Get IP address information
                self._update_interface_ip_info(interface)
                
                # Detect interface type
                interface.interface_type = self._detect_interface_type(interface)
                
                # Get speed information if available
                interface.speed = self._get_interface_speed(interface.name)
                
                interfaces.append(interface)
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to detect interfaces: {e}")
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse interface data: {e}")
            
        return interfaces
    
    def _update_interface_ip_info(self, interface: NetworkInterface):
        """Update IP address information for an interface"""
        try:
            result = subprocess.run(['ip', '-j', 'addr', 'show', interface.name], 
                                  capture_output=True, text=True, check=True)
            
            addr_data = json.loads(result.stdout)
            
            for addr_info in addr_data:
                for addr in addr_info.get('addr_info', []):
                    if addr.get('family') == 'inet':  # IPv4
                        interface.ip_address = f"{addr['local']}/{addr['prefixlen']}"
                        break
                        
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            self.logger.warning(f"Failed to get IP info for {interface.name}: {e}")
    
    def _detect_interface_type(self, interface: NetworkInterface) -> str:
        """Intelligently detect if interface is WAN or LAN based on various factors"""
        
        # Check if interface has internet connectivity
        if self._test_internet_connectivity(interface.name):
            return "wan"
        
        # Check interface naming conventions
        if interface.name.startswith(('eth', 'en', 'ens')):
            # For typical setups, first interface might be WAN
            if interface.name in ['eth0', 'enp0s3', 'ens3']:
                return "wan"
        
        # Check if interface has a gateway (indicates WAN)
        if self._get_interface_gateway(interface.name):
            return "wan"
        
        # Check if interface is on common LAN subnet
        if interface.ip_address:
            try:
                network = ipaddress.ip_network(interface.ip_address, strict=False)
                # Common LAN subnets
                if network.subnet_of(ipaddress.ip_network('192.168.0.0/16')):
                    return "lan"
                elif network.subnet_of(ipaddress.ip_network('10.0.0.0/8')):
                    return "lan"
                elif network.subnet_of(ipaddress.ip_network('172.16.0.0/12')):
                    return "lan"
            except ValueError:
                pass
        
        return "unknown"
    
    def _test_internet_connectivity(self, interface_name: str) -> bool:
        """Test if interface has internet connectivity"""
        try:
            # Try to ping a well-known host through this interface
            result = subprocess.run([
                'ping', '-I', interface_name, '-c', '1', '-W', '2', '8.8.8.8'
            ], capture_output=True, text=True, timeout=5)
            
            return result.returncode == 0
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False
    
    def _get_interface_gateway(self, interface_name: str) -> Optional[str]:
        """Get the default gateway for an interface"""
        try:
            result = subprocess.run(['ip', 'route', 'show', 'dev', interface_name], 
                                  capture_output=True, text=True, check=True)
            
            for line in result.stdout.split('\n'):
                if 'default' in line:
                    parts = line.split()
                    if 'via' in parts:
                        via_index = parts.index('via')
                        if via_index + 1 < len(parts):
                            return parts[via_index + 1]
                            
        except subprocess.CalledProcessError:
            pass
            
        return None
    
    def _get_interface_speed(self, interface_name: str) -> Optional[str]:
        """Get interface speed information"""
        try:
            # Try ethtool first
            result = subprocess.run(['ethtool', interface_name], 
                                  capture_output=True, text=True, check=True)
            
            for line in result.stdout.split('\n'):
                if 'Speed:' in line:
                    return line.split('Speed:')[1].strip()
                    
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to /sys filesystem
            try:
                speed_file = f"/sys/class/net/{interface_name}/speed"
                if os.path.exists(speed_file):
                    with open(speed_file, 'r') as f:
                        speed_mbps = int(f.read().strip())
                        if speed_mbps > 0:
                            return f"{speed_mbps}Mb/s"
            except (ValueError, IOError):
                pass
                
        return None
    
    def detect_primary_wan(self) -> Optional[NetworkInterface]:
        """Detect the primary WAN interface (the one with internet access)"""
        interfaces = self.detect_all_interfaces()
        
        # First, look for interfaces with internet connectivity
        for interface in interfaces:
            if interface.interface_type == "wan" and self._test_internet_connectivity(interface.name):
                return interface
        
        # Second, look for interfaces with default gateways
        for interface in interfaces:
            if self._get_interface_gateway(interface.name):
                return interface
        
        # Third, prefer first ethernet interface
        for interface in interfaces:
            if interface.name.startswith(('eth', 'en', 'ens')):
                return interface
        
        # Last resort: return first available interface
        return interfaces[0] if interfaces else None
    
    def auto_configure_primary_wan(self) -> Dict:
        """Auto-configure the primary WAN interface for initial access"""
        primary_wan = self.detect_primary_wan()
        
        if not primary_wan:
            self.logger.error("No suitable WAN interface detected")
            return {"error": "No WAN interface detected"}
        
        self.logger.info(f"Detected primary WAN interface: {primary_wan.name}")
        
        # Detect gateway and DNS for this interface
        gateway = self._get_interface_gateway(primary_wan.name)
        dns_servers = self._detect_dns_servers(primary_wan.name)
        
        # Create auto-detected configuration
        auto_config = {
            "primary_wan": {
                "name": primary_wan.name,
                "mac_address": primary_wan.mac_address,
                "ip_address": primary_wan.ip_address,
                "gateway": gateway,
                "dns_servers": dns_servers or ["8.8.8.8", "1.1.1.1"],
                "speed": primary_wan.speed,
                "status": primary_wan.status
            },
            "detected_at": self._get_timestamp(),
            "detection_method": "automatic"
        }
        
        # Save auto-detected configuration
        self._save_auto_detected_config(auto_config)
        
        # Create initial interfaces configuration with just primary WAN
        initial_config = self._create_initial_config(primary_wan, gateway, dns_servers)
        self._save_interfaces_config(initial_config)
        
        self.logger.info(f"Auto-configuration completed for {primary_wan.name}")
        return auto_config
    
    def _detect_dns_servers(self, interface_name: str) -> List[str]:
        """Detect DNS servers for an interface"""
        dns_servers = []
        
        try:
            # Check /etc/resolv.conf for current DNS
            if os.path.exists('/etc/resolv.conf'):
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            dns = line.split()[1]
                            if self._is_valid_dns(dns):
                                dns_servers.append(dns)
        except IOError:
            pass
        
        # Fallback to common DNS servers
        if not dns_servers:
            dns_servers = ["8.8.8.8", "1.1.1.1"]
        
        return dns_servers[:2]  # Limit to 2 DNS servers
    
    def _is_valid_dns(self, dns_server: str) -> bool:
        """Check if DNS server is valid"""
        try:
            ipaddress.ip_address(dns_server)
            return not dns_server.startswith('127.') and not dns_server.startswith('169.254.')
        except ValueError:
            return False
    
    def _create_initial_config(self, primary_wan: NetworkInterface, gateway: Optional[str], 
                              dns_servers: List[str]) -> Dict:
        """Create initial interfaces configuration with primary WAN"""
        
        return {
            "wan_interfaces": [
                {
                    "name": primary_wan.name,
                    "gateway": gateway or "192.168.1.1",
                    "weight": 2,
                    "dns": dns_servers or ["8.8.8.8", "8.8.4.4"],
                    "description": f"Primary WAN - {primary_wan.name} (Auto-detected)",
                    "auto_detected": True,
                    "mac_address": primary_wan.mac_address,
                    "speed": primary_wan.speed
                }
            ],
            "lan_interface": {
                "name": "eth2",  # Default LAN interface
                "ip": "192.168.1.1",
                "netmask": "255.255.255.0",
                "dhcp_range": "192.168.1.100-192.168.1.200",
                "description": "Default LAN interface"
            },
            "management": {
                "web_port": 8080,
                "api_port": 8081,
                "enable_ssh": True,
                "enable_web": True,
                "auto_detected": True
            },
            "auto_detection": {
                "enabled": True,
                "primary_wan_detected": True,
                "detection_date": self._get_timestamp()
            }
        }
    
    def _save_auto_detected_config(self, config: Dict):
        """Save auto-detected configuration"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.auto_detect_file, 'w') as f:
                json.dump(config, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save auto-detected config: {e}")
    
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
    
    def get_available_wan_interfaces(self) -> List[NetworkInterface]:
        """Get list of interfaces that could be used as WAN"""
        all_interfaces = self.detect_all_interfaces()
        available = []
        
        # Load current configuration to avoid duplicates
        current_config = self._load_current_config()
        current_wans = [wan['name'] for wan in current_config.get('wan_interfaces', [])]
        
        for interface in all_interfaces:
            # Skip if already configured as WAN
            if interface.name in current_wans:
                continue
                
            # Skip loopback and virtual interfaces
            if interface.name in ['lo', 'virbr', 'docker', 'veth']:
                continue
            
            # Prefer ethernet interfaces
            if interface.name.startswith(('eth', 'en', 'ens', 'wlan')):
                available.append(interface)
        
        return available
    
    def _load_current_config(self) -> Dict:
        """Load current interfaces configuration"""
        try:
            if os.path.exists(self.interfaces_file):
                with open(self.interfaces_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load current config: {e}")
        
        return {}
    
    def suggest_wan_configuration(self, interface_name: str) -> Dict:
        """Suggest WAN configuration for a new interface"""
        interfaces = self.detect_all_interfaces()
        target_interface = None
        
        for interface in interfaces:
            if interface.name == interface_name:
                target_interface = interface
                break
        
        if not target_interface:
            return {"error": f"Interface {interface_name} not found"}
        
        # Detect gateway (this might require temporary DHCP)
        gateway = self._detect_interface_gateway_suggestion(interface_name)
        
        # Use common DNS servers
        dns_servers = ["8.8.8.8", "1.1.1.1"]
        
        # Suggest weight based on interface speed
        weight = self._suggest_weight_based_on_speed(target_interface.speed)
        
        return {
            "name": interface_name,
            "gateway": gateway or "192.168.1.1",
            "weight": weight,
            "dns": dns_servers,
            "description": f"WAN Interface - {interface_name} (Added dynamically)",
            "mac_address": target_interface.mac_address,
            "speed": target_interface.speed,
            "suggested_config": True
        }
    
    def _detect_interface_gateway_suggestion(self, interface_name: str) -> Optional[str]:
        """Try to detect gateway for interface suggestion"""
        try:
            # Try DHCP first
            self.logger.info(f"Attempting DHCP on {interface_name} to detect gateway...")
            
            # Bring interface up
            subprocess.run(['ip', 'link', 'set', interface_name, 'up'], 
                         capture_output=True, check=True)
            
            # Try DHCP for a short period
            result = subprocess.run(['dhclient', '-v', '-1', '-timeout', '10', interface_name], 
                                  capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                # Successfully got DHCP, now check for gateway
                gateway = self._get_interface_gateway(interface_name)
                if gateway:
                    self.logger.info(f"Detected gateway via DHCP: {gateway}")
                    return gateway
            
            # Release DHCP lease
            subprocess.run(['dhclient', '-r', interface_name], 
                         capture_output=True, check=True)
                           
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.warning(f"DHCP detection failed for {interface_name}: {e}")
        
        return None
    
    def _suggest_weight_based_on_speed(self, speed: Optional[str]) -> int:
        """Suggest weight based on interface speed"""
        if not speed:
            return 1
        
        # Extract numeric speed value
        import re
        speed_match = re.search(r'(\d+)', speed)
        if speed_match:
            speed_mbps = int(speed_match.group(1))
            
            if speed_mbps >= 1000:  # Gigabit or higher
                return 3
            elif speed_mbps >= 100:  # Fast Ethernet
                return 2
        
        return 1

def main():
    """Main function for interface detection"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Dynamic Interface Detection Tool')
    parser.add_argument('--detect-all', action='store_true', 
                       help='Detect all network interfaces')
    parser.add_argument('--detect-primary', action='store_true', 
                       help='Detect primary WAN interface')
    parser.add_argument('--auto-configure', action='store_true', 
                       help='Auto-configure primary WAN interface')
    parser.add_argument('--available-wan', action='store_true', 
                       help='List available WAN interfaces')
    parser.add_argument('--suggest-config', metavar='INTERFACE', 
                       help='Suggest configuration for interface')
    parser.add_argument('--test-connectivity', metavar='INTERFACE', 
                       help='Test internet connectivity on interface')
    
    args = parser.parse_args()
    
    detector = DynamicInterfaceDetector()
    
    if args.detect_all:
        interfaces = detector.detect_all_interfaces()
        print("Detected Interfaces:")
        for interface in interfaces:
            print(f"  {interface.name}: {interface.interface_type} "
                  f"({interface.status}, {interface.ip_address or 'no IP'})")
    
    elif args.detect_primary:
        primary = detector.detect_primary_wan()
        if primary:
            print(f"Primary WAN Interface: {primary.name}")
            print(f"  MAC: {primary.mac_address}")
            print(f"  IP: {primary.ip_address or 'No IP'}")
            print(f"  Status: {primary.status}")
            print(f"  Speed: {primary.speed or 'Unknown'}")
        else:
            print("No primary WAN interface detected")
    
    elif args.auto_configure:
        result = detector.auto_configure_primary_wan()
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print("Auto-configuration completed successfully")
            print(f"Primary WAN: {result['primary_wan']['name']}")
            print(f"Gateway: {result['primary_wan']['gateway']}")
            print(f"DNS: {', '.join(result['primary_wan']['dns_servers'])}")
    
    elif args.available_wan:
        available = detector.get_available_wan_interfaces()
        print("Available WAN Interfaces:")
        for interface in available:
            print(f"  {interface.name}: {interface.mac_address} "
                  f"({interface.speed or 'Unknown speed'})")
    
    elif args.suggest_config:
        suggestion = detector.suggest_wan_configuration(args.suggest_config)
        if "error" in suggestion:
            print(f"Error: {suggestion['error']}")
        else:
            print(f"Suggested configuration for {args.suggest_config}:")
            print(json.dumps(suggestion, indent=2))
    
    elif args.test_connectivity:
        success = detector._test_internet_connectivity(args.test_connectivity)
        print(f"Connectivity test for {args.test_connectivity}: "
              f"{'SUCCESS' if success else 'FAILED'}")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()