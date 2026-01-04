#!/usr/bin/env python3
"""
Smart Multi-WAN Router OS - Kill Switch Management Tool
Provides command-line interface for manual interface control and maintenance operations
"""

import sys
import os
import time
import json
import logging
import argparse
import subprocess
from typing import Dict, List, Optional

class KillSwitchManager:
    """Manages manual interface control and kill-switch operations"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.watchdog_script = '/opt/routeros/watchdog/watchdog_service.py'
        self.status_file = '/opt/routeros/web/status.json'
        self.config_file = '/opt/routeros/config/interfaces.json'
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for kill-switch operations"""
        logger = logging.getLogger('kill-switch')
        logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        return logger
    
    def get_interface_list(self) -> List[str]:
        """Get list of configured interfaces"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return [iface['name'] for iface in config.get('wan_interfaces', [])]
            else:
                # Fallback to common interface names
                return ['eth0', 'eth1', 'eth2', 'wlan0']
        except Exception as e:
            self.logger.error(f"Failed to read interface config: {e}")
            return ['eth0', 'eth1']
    
    def get_interface_status(self, interface: str) -> Optional[Dict]:
        """Get current status of an interface"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r') as f:
                    status = json.load(f)
                    interfaces = status.get('components', {}).get('health_monitor', {}).get('interfaces', {})
                    return interfaces.get(interface)
            return None
        except Exception as e:
            self.logger.error(f"Failed to read status file: {e}")
            return None
    
    def disable_interface(self, interface: str, force: bool = False) -> bool:
        """Disable an interface (kill-switch)"""
        self.logger.info(f"Attempting to disable interface {interface}")
        
        # Check current status
        current_status = self.get_interface_status(interface)
        if current_status and current_status.get('current_status') == 'failed':
            self.logger.warning(f"Interface {interface} is already disabled")
            return True
        
        if not force and current_status and current_status.get('current_status') == 'healthy':
            response = input(f"Interface {interface} is currently healthy. Are you sure you want to disable it? (y/N): ")
            if response.lower() != 'y':
                self.logger.info("Operation cancelled by user")
                return False
        
        try:
            # Call watchdog service to disable interface
            result = subprocess.run([
                'python3', self.watchdog_script,
                '--interface-control', interface, 'disable'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"✓ Interface {interface} disabled successfully")
                self.logger.info("The interface has been removed from the load balancing pool")
                return True
            else:
                self.logger.error(f"✗ Failed to disable interface {interface}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"✗ Timeout while disabling interface {interface}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Error disabling interface {interface}: {e}")
            return False
    
    def enable_interface(self, interface: str) -> bool:
        """Enable an interface"""
        self.logger.info(f"Attempting to enable interface {interface}")
        
        # Check current status
        current_status = self.get_interface_status(interface)
        if current_status and current_status.get('current_status') == 'healthy':
            self.logger.warning(f"Interface {interface} is already enabled")
            return True
        
        try:
            # Call watchdog service to enable interface
            result = subprocess.run([
                'python3', self.watchdog_script,
                '--interface-control', interface, 'enable'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"✓ Interface {interface} enabled successfully")
                self.logger.info("The interface has been added back to the load balancing pool")
                return True
            else:
                self.logger.error(f"✗ Failed to enable interface {interface}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"✗ Timeout while enabling interface {interface}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Error enabling interface {interface}: {e}")
            return False
    
    def show_status(self):
        """Show current interface status"""
        interfaces = self.get_interface_list()
        
        print("\n" + "="*60)
        print("RouterOS Kill-Switch Manager - Interface Status")
        print("="*60)
        
        for interface in interfaces:
            status = self.get_interface_status(interface)
            if status:
                current_status = status.get('current_status', 'unknown')
                latency = status.get('current_latency', 'N/A')
                packet_loss = status.get('current_packet_loss', 'N/A')
                uptime = status.get('uptime_percentage', 'N/A')
                
                status_symbol = {
                    'healthy': '✅',
                    'degraded': '⚠️',
                    'failed': '❌',
                    'unknown': '❓'
                }.get(current_status, '❓')
                
                print(f"\n{status_symbol} {interface}")
                print(f"   Status: {current_status.title()}")
                print(f"   Latency: {latency}ms")
                print(f"   Packet Loss: {packet_loss}%")
                print(f"   Uptime: {uptime}%")
            else:
                print(f"\n❓ {interface}: No status available")
        
        print("\n" + "="*60)
    
    def maintenance_mode(self, duration_minutes: int = 30):
        """Enter maintenance mode - disable all interfaces except one"""
        interfaces = self.get_interface_list()
        
        if len(interfaces) <= 1:
            self.logger.error("Maintenance mode requires at least 2 interfaces")
            return False
        
        self.logger.info(f"Entering maintenance mode for {duration_minutes} minutes")
        
        # Keep the first interface enabled, disable others
        keep_interface = interfaces[0]
        disable_interfaces = interfaces[1:]
        
        print(f"\n🛠️  Maintenance Mode Configuration:")
        print(f"   Keeping interface: {keep_interface}")
        print(f"   Disabling interfaces: {', '.join(disable_interfaces)}")
        print(f"   Duration: {duration_minutes} minutes")
        
        response = input(f"\nProceed with maintenance mode? (y/N): ")
        if response.lower() != 'y':
            self.logger.info("Maintenance mode cancelled by user")
            return False
        
        success_count = 0
        
        # Ensure keep_interface is enabled
        if self.enable_interface(keep_interface):
            success_count += 1
        
        # Disable other interfaces
        for interface in disable_interfaces:
            if self.disable_interface(interface, force=True):
                success_count += 1
        
        self.logger.info(f"✓ Maintenance mode activated. {success_count}/{len(interfaces)} interfaces configured")
        self.logger.info(f"⏰ Will automatically re-enable disabled interfaces in {duration_minutes} minutes")
        
        if duration_minutes > 0:
            try:
                time.sleep(duration_minutes * 60)
                self.logger.info("Maintenance mode duration completed, re-enabling interfaces...")
                
                # Re-enable disabled interfaces
                for interface in disable_interfaces:
                    self.enable_interface(interface)
                
                self.logger.info("✓ All interfaces re-enabled, maintenance mode completed")
                return True
                
            except KeyboardInterrupt:
                self.logger.info("\n⚠️  Maintenance mode interrupted by user")
                response = input("Re-enable disabled interfaces? (Y/n): ")
                if response.lower() != 'n':
                    for interface in disable_interfaces:
                        self.enable_interface(interface)
                return False
        
        return True

def main():
    """Main entry point for kill-switch management tool"""
    parser = argparse.ArgumentParser(
        description='RouterOS Kill-Switch Manager - Manual interface control tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --status                    Show current interface status
  %(prog)s --disable eth1              Disable interface eth1
  %(prog)s --enable eth1               Enable interface eth1
  %(prog)s --maintenance 30            Enter maintenance mode for 30 minutes
  %(prog)s --list                      List all configured interfaces
        """
    )
    
    parser.add_argument('--status', action='store_true', 
                       help='Show current interface status')
    parser.add_argument('--list', action='store_true', 
                       help='List all configured interfaces')
    parser.add_argument('--disable', metavar='INTERFACE', 
                       help='Disable specified interface (kill-switch)')
    parser.add_argument('--enable', metavar='INTERFACE', 
                       help='Enable specified interface')
    parser.add_argument('--maintenance', type=int, metavar='MINUTES', 
                       help='Enter maintenance mode for specified duration (0 = indefinite)')
    parser.add_argument('--force', action='store_true', 
                       help='Force operation without confirmation')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Initialize kill-switch manager
    manager = KillSwitchManager()
    
    # Set verbose logging if requested
    if args.verbose:
        manager.logger.setLevel(logging.DEBUG)
    
    # Handle commands
    if args.status:
        manager.show_status()
        return 0
    
    if args.list:
        interfaces = manager.get_interface_list()
        print("\nConfigured Interfaces:")
        for i, interface in enumerate(interfaces, 1):
            print(f"  {i}. {interface}")
        return 0
    
    if args.disable:
        success = manager.disable_interface(args.disable, force=args.force)
        return 0 if success else 1
    
    if args.enable:
        success = manager.enable_interface(args.enable)
        return 0 if success else 1
    
    if args.maintenance is not None:
        success = manager.maintenance_mode(args.maintenance)
        return 0 if success else 1
    
    # No arguments provided, show status by default
    manager.show_status()
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)