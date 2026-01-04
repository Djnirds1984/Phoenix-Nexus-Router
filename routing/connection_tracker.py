#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Connection Tracker
Handles connection tracking, packet marking, and sticky sessions for session persistence
"""

import subprocess
import logging
import time
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum

class ConnectionState(Enum):
    NEW = "NEW"
    ESTABLISHED = "ESTABLISHED"
    RELATED = "RELATED"
    INVALID = "INVALID"

class TrafficType(Enum):
    GENERAL = "general"
    VOIP = "voip"
    GAMING = "gaming"
    STREAMING = "streaming"
    BANKING = "banking"

@dataclass
class Connection:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    state: ConnectionState
    interface: str
    mark: int = 0
    traffic_type: TrafficType = TrafficType.GENERAL
    created_at: float = 0.0
    last_seen: float = 0.0
    packets: int = 0
    bytes: int = 0

class ConnectionTracker:
    """Manages connection tracking and packet marking for session persistence"""
    
    def __init__(self, config_file: str = "/opt/routeros/config/connection_rules.json"):
        self.config_file = config_file
        self.connections: Dict[str, Connection] = {}
        self.sticky_sessions: Set[str] = set()
        self.logger = logging.getLogger(__name__)
        
        # Traffic classification rules
        self.traffic_rules = {
            TrafficType.VOIP: {
                'ports': [5060, 5061, 5062, 16384, 16385, 16386],  # SIP, RTP
                'protocols': ['udp', 'tcp']
            },
            TrafficType.GAMING: {
                'ports': [27015, 27016, 27017, 27018, 27019, 27020,  # Steam
                         80, 443, 8080, 8443],  # HTTP/HTTPS gaming
                'protocols': ['udp', 'tcp']
            },
            TrafficType.STREAMING: {
                'ports': [1935, 1936, 8080, 8081, 8082, 8083,  # RTMP, HLS
                         554, 8554, 8555],  # RTSP
                'protocols': ['tcp', 'udp']
            },
            TrafficType.BANKING: {
                'ports': [443, 8443, 9443],  # HTTPS banking
                'protocols': ['tcp']
            }
        }
        
        # Connection mark assignments
        self.interface_marks = {
            'eth0': 0x100,  # Primary WAN
            'eth1': 0x200,  # Secondary WAN
            'eth2': 0x300   # Tertiary WAN
        }
        
        self._setup_logging()
        self._setup_nftables()
        self._load_rules()
    
    def _setup_logging(self):
        """Configure logging for connection tracker"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/routeros-connections.log'),
                logging.StreamHandler()
            ]
        )
    
    def _setup_nftables(self):
        """Initialize nftables rules for connection tracking and marking"""
        try:
            # Create comprehensive nftables configuration
            nft_rules = [
                # Create routeros table
                "add table inet routeros",
                
                # Create chains for different hooks
                "add chain inet routeros prerouting { type filter hook prerouting priority -150; }",
                "add chain inet routeros postrouting { type filter hook postrouting priority 150; }",
                "add chain inet routeros forward { type filter hook forward priority 0; }",
                "add chain inet routeros output { type filter hook output priority -150; }",
                
                # Connection tracking rules
                "add rule inet routeros prerouting ct state invalid drop",
                "add rule inet routeros prerouting ct state established,related accept",
                
                # Mark new connections based on traffic type
                "add rule inet routeros prerouting ct state new ct mark set 0x1 random mod 100",
                
                # VoIP traffic marking (high priority)
                "add rule inet routeros prerouting ip dport { 5060, 5061, 5062 } ct mark set 0x10",
                "add rule inet routeros prerouting ip sport { 5060, 5061, 5062 } ct mark set 0x10",
                "add rule inet routeros prerouting udp dport { 16384-16387 } ct mark set 0x10",
                "add rule inet routeros prerouting udp sport { 16384-16387 } ct mark set 0x10",
                
                # Gaming traffic marking (medium-high priority)
                "add rule inet routeros prerouting ip dport { 27015-27020 } ct mark set 0x20",
                "add rule inet routeros prerouting ip sport { 27015-27020 } ct mark set 0x20",
                
                # Banking traffic marking (highest priority, sticky)
                "add rule inet routeros prerouting ip dport { 443, 8443, 9443 } ct mark set 0x30",
                "add rule inet routeros prerouting ip sport { 443, 8443, 9443 } ct mark set 0x30",
                
                # Streaming traffic marking
                "add rule inet routeros prerouting ip dport { 1935, 1936, 8080-8083 } ct mark set 0x40",
                "add rule inet routeros prerouting ip sport { 1935, 1936, 8080-8083 } ct mark set 0x40",
                
                # Apply connection marks to packet marks for routing decisions
                "add rule inet routeros prerouting ct mark 0x10 meta mark set 0x10",
                "add rule inet routeros prerouting ct mark 0x20 meta mark set 0x20",
                "add rule inet routeros prerouting ct mark 0x30 meta mark set 0x30",
                "add rule inet routeros prerouting ct mark 0x40 meta mark set 0x40",
                
                # Sticky session rules for banking connections
                "add rule inet routeros prerouting ct mark 0x30 ct mark set mark and 0x0f00 or ct mark",
                "add rule inet routeros postrouting ct mark 0x30 ct mark set mark and 0x0f00 or ct mark",
                
                # Log marked connections for debugging
                "add rule inet routeros prerouting ct mark 0x30 log prefix 'BANKING-STICKY: '",
                "add rule inet routeros prerouting ct mark 0x10 log prefix 'VOIP-PRIORITY: ' limit rate 10/second",
            ]
            
            # Apply rules
            for rule in nft_rules:
                try:
                    subprocess.run(['nft', rule], check=True, capture_output=True)
                    self.logger.debug(f"Applied nftables rule: {rule}")
                except subprocess.CalledProcessError as e:
                    # Rule might already exist, continue
                    self.logger.debug(f"Rule may already exist: {rule}")
            
            self.logger.info("Nftables connection tracking configuration applied")
            
        except Exception as e:
            self.logger.error(f"Failed to setup nftables: {e}")
    
    def _load_rules(self):
        """Load custom connection rules from configuration file"""
        try:
            with open(self.config_file, 'r') as f:
                custom_rules = json.load(f)
                
            # Merge custom rules with default rules
            for traffic_type, rules in custom_rules.get('traffic_rules', {}).items():
                try:
                    ttype = TrafficType(traffic_type)
                    if ttype in self.traffic_rules:
                        self.traffic_rules[ttype].update(rules)
                    else:
                        self.traffic_rules[ttype] = rules
                except ValueError:
                    self.logger.warning(f"Unknown traffic type: {traffic_type}")
                    
            self.logger.info(f"Loaded {len(custom_rules)} custom connection rules")
            
        except FileNotFoundError:
            self.logger.info("No custom connection rules file found, using defaults")
        except Exception as e:
            self.logger.error(f"Failed to load connection rules: {e}")
    
    def classify_traffic(self, src_port: int, dst_port: int, protocol: str) -> TrafficType:
        """Classify traffic based on port numbers and protocol"""
        for traffic_type, rules in self.traffic_rules.items():
            ports = rules.get('ports', [])
            protocols = rules.get('protocols', [])
            
            if protocol in protocols:
                if src_port in ports or dst_port in ports:
                    return traffic_type
        
        return TrafficType.GENERAL
    
    def get_connection_key(self, src_ip: str, dst_ip: str, src_port: int, dst_port: int, protocol: str) -> str:
        """Generate unique connection key"""
        # Normalize connection key (handle NAT and bidirectional flows)
        if src_port < dst_port:
            return f"{src_ip}:{src_port}-{dst_ip}:{dst_port}-{protocol}"
        else:
            return f"{dst_ip}:{dst_port}-{src_ip}:{src_port}-{protocol}"
    
    def track_connection(self, connection: Connection) -> bool:
        """Track a new connection and determine if it needs sticky session handling"""
        conn_key = self.get_connection_key(
            connection.src_ip, connection.dst_ip,
            connection.src_port, connection.dst_port,
            connection.protocol
        )
        
        # Classify traffic type
        connection.traffic_type = self.classify_traffic(
            connection.src_port, connection.dst_port, connection.protocol
        )
        
        # Check if this is a sticky session candidate
        if connection.traffic_type in [TrafficType.BANKING, TrafficType.VOIP]:
            self.sticky_sessions.add(conn_key)
            self.logger.info(f"Added sticky session: {conn_key} ({connection.traffic_type.value})")
        
        # Store connection
        self.connections[conn_key] = connection
        connection.created_at = time.time()
        connection.last_seen = time.time()
        
        return conn_key in self.sticky_sessions
    
    def update_connection(self, conn_key: str, packets: int = 0, bytes: int = 0, interface: str = None):
        """Update connection statistics"""
        if conn_key in self.connections:
            conn = self.connections[conn_key]
            conn.packets += packets
            conn.bytes += bytes
            conn.last_seen = time.time()
            
            if interface:
                conn.interface = interface
    
    def get_sticky_interface(self, conn_key: str) -> Optional[str]:
        """Get the interface assigned to a sticky session"""
        if conn_key in self.connections:
            return self.connections[conn_key].interface
        return None
    
    def cleanup_connections(self, max_age: int = 3600):
        """Clean up old connections"""
        current_time = time.time()
        expired_keys = []
        
        for conn_key, connection in self.connections.items():
            # Remove connections older than max_age
            if current_time - connection.last_seen > max_age:
                expired_keys.append(conn_key)
            
            # Remove completed connections (FIN/RST)
            if connection.state == ConnectionState.INVALID:
                expired_keys.append(conn_key)
        
        # Remove expired connections
        for conn_key in expired_keys:
            del self.connections[conn_key]
            self.sticky_sessions.discard(conn_key)
        
        if expired_keys:
            self.logger.info(f"Cleaned up {len(expired_keys)} expired connections")
    
    def get_connection_stats(self) -> Dict:
        """Get connection tracking statistics"""
        stats = {
            'total_connections': len(self.connections),
            'sticky_sessions': len(self.sticky_sessions),
            'traffic_breakdown': {},
            'interface_distribution': {}
        }
        
        # Traffic type breakdown
        for traffic_type in TrafficType:
            count = sum(1 for conn in self.connections.values() if conn.traffic_type == traffic_type)
            stats['traffic_breakdown'][traffic_type.value] = count
        
        # Interface distribution
        for conn in self.connections.values():
            iface = conn.interface or 'unknown'
            stats['interface_distribution'][iface] = stats['interface_distribution'].get(iface, 0) + 1
        
        return stats
    
    def get_active_connections(self, traffic_type: Optional[TrafficType] = None) -> List[Connection]:
        """Get list of active connections, optionally filtered by traffic type"""
        connections = list(self.connections.values())
        
        if traffic_type:
            connections = [conn for conn in connections if conn.traffic_type == traffic_type]
        
        # Sort by last seen (most recent first)
        connections.sort(key=lambda x: x.last_seen, reverse=True)
        
        return connections
    
    def export_connections(self, format: str = 'json') -> str:
        """Export connection tracking data"""
        data = {
            'timestamp': time.time(),
            'total_connections': len(self.connections),
            'sticky_sessions': list(self.sticky_sessions),
            'connections': [asdict(conn) for conn in self.connections.values()]
        }
        
        if format == 'json':
            return json.dumps(data, indent=2, default=str)
        else:
            # Simple text format
            output = f"Connection Tracking Report - {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            output += f"Total Connections: {data['total_connections']}\n"
            output += f"Sticky Sessions: {len(data['sticky_sessions'])}\n\n"
            
            for conn in data['connections'][:50]:  # Limit to first 50
                output += f"{conn['src_ip']}:{conn['src_port']} -> {conn['dst_ip']}:{conn['dst_port']} "
                output += f"({conn['protocol']}) [{conn['traffic_type']}] "
                output += f"via {conn['interface']} mark:{conn['mark']}\n"
            
            return output
    
    def apply_connection_mark(self, conn_key: str, mark: int):
        """Apply nftables mark to connection"""
        if conn_key not in self.connections:
            return False
        
        conn = self.connections[conn_key]
        
        try:
            # Build nftables command to mark connection
            mark_rule = (
                f"add rule inet routeros filter "
                f"ip saddr {conn.src_ip} ip daddr {conn.dst_ip} "
                f"{conn.protocol} sport {conn.src_port} dport {conn.dst_port} "
                f"ct mark set {mark}"
            )
            
            subprocess.run(['nft', mark_rule], check=True, capture_output=True)
            conn.mark = mark
            
            self.logger.info(f"Applied mark {mark} to connection {conn_key}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to apply connection mark: {e}")
            return False
    
    def get_nftables_rules(self) -> str:
        """Get current nftables rules"""
        try:
            result = subprocess.run(['nft', 'list', 'ruleset'], 
                                  capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get nftables rules: {e}")
            return ""
    
    def validate_connection_tracking(self) -> bool:
        """Validate that connection tracking is working properly"""
        try:
            # Check if conntrack module is loaded
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            if 'nf_conntrack' not in result.stdout:
                self.logger.error("Connection tracking module not loaded")
                return False
            
            # Check if nftables is working
            result = subprocess.run(['nft', 'list', 'tables'], 
                                  capture_output=True, check=True)
            if 'routeros' not in result.stdout.decode():
                self.logger.warning("RouterOS nftables table not found")
            
            # Test connection tracking
            result = subprocess.run(['conntrack', '-C'], 
                                  capture_output=True, text=True)
            connection_count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
            
            self.logger.info(f"Connection tracking validation passed. Active connections: {connection_count}")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection tracking validation failed: {e}")
            return False

def main():
    """Main function for testing connection tracker"""
    tracker = ConnectionTracker()
    
    # Test traffic classification
    print("Traffic Classification Test:")
    test_cases = [
        (5060, 12345, 'udp'),  # SIP
        (27015, 80, 'udp'),    # Gaming
        (12345, 443, 'tcp'),   # Banking
        (12345, 8080, 'tcp'),  # Streaming
    ]
    
    for src_port, dst_port, protocol in test_cases:
        traffic_type = tracker.classify_traffic(src_port, dst_port, protocol)
        print(f"  {src_port}->{dst_port} ({protocol}): {traffic_type.value}")
    
    # Test connection tracking
    print("\nConnection Tracking Test:")
    test_conn = Connection(
        src_ip="192.168.1.100",
        dst_ip="93.184.216.34",
        src_port=5060,
        dst_port=12345,
        protocol="udp",
        state=ConnectionState.NEW,
        interface="eth0"
    )
    
    is_sticky = tracker.track_connection(test_conn)
    print(f"Connection tracked (sticky: {is_sticky})")
    
    # Display stats
    print("\nConnection Statistics:")
    stats = tracker.get_connection_stats()
    print(json.dumps(stats, indent=2))
    
    # Test nftables validation
    print(f"\nConnection tracking validation: {tracker.validate_connection_tracking()}")

if __name__ == "__main__":
    main()