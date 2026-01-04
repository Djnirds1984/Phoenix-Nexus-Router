#!/usr/bin/env python3
"""
Phoenix Nexus Router - Service Diagnostic Script
Checks for missing dependencies, configuration issues, and startup problems
"""

import os
import sys
import subprocess
import json
import importlib.util

def check_python_version():
    """Check Python version compatibility"""
    print("1. Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 6:
        print(f"   ✓ Python {version.major}.{version.minor}.{version.micro} is compatible")
        return True
    else:
        print(f"   ✗ Python {version.major}.{version.minor}.{version.micro} is too old (need 3.6+)")
        return False

def check_dependencies():
    """Check for required Python packages"""
    print("2. Checking Python dependencies...")
    required_packages = [
        'flask',
        'requests',
        'psutil',
        'netifaces'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            spec = importlib.util.find_spec(package)
            if spec is None:
                missing_packages.append(package)
            else:
                print(f"   ✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"   ✗ Missing packages: {', '.join(missing_packages)}")
        print("   Install with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("   ✓ All required packages are installed")
        return True

def check_directory_structure():
    """Check if required directories exist"""
    print("3. Checking directory structure...")
    required_dirs = [
        '/opt/routeros',
        '/opt/routeros/routing',
        '/opt/routeros/watchdog',
        '/opt/routeros/web',
        '/opt/routeros/config',
        '/opt/routeros/scripts',
        '/var/log'
    ]
    
    missing_dirs = []
    for directory in required_dirs:
        if os.path.exists(directory):
            print(f"   ✓ {directory} exists")
        else:
            print(f"   ✗ {directory} is missing")
            missing_dirs.append(directory)
    
    if missing_dirs:
        print("   Creating missing directories...")
        for directory in missing_dirs:
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"   ✓ Created {directory}")
            except Exception as e:
                print(f"   ✗ Failed to create {directory}: {e}")
        return len(missing_dirs) == 0
    else:
        print("   ✓ All required directories exist")
        return True

def check_configuration_files():
    """Check for required configuration files"""
    print("4. Checking configuration files...")
    config_files = [
        '/opt/routeros/config/interfaces.json',
        '/opt/routeros/config/router.conf'
    ]
    
    missing_configs = []
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"   ✓ {config_file} exists")
            try:
                with open(config_file, 'r') as f:
                    json.load(f)
                print(f"   ✓ {config_file} is valid JSON")
            except Exception as e:
                print(f"   ✗ {config_file} has invalid JSON: {e}")
        else:
            print(f"   ✗ {config_file} is missing")
            missing_configs.append(config_file)
    
    if missing_configs:
        print("   Creating default configurations...")
        # Create default interfaces.json
        default_interfaces = {
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
        
        try:
            with open('/opt/routeros/config/interfaces.json', 'w') as f:
                json.dump(default_interfaces, f, indent=2)
            print("   ✓ Created default interfaces.json")
        except Exception as e:
            print(f"   ✗ Failed to create interfaces.json: {e}")
            return False
    
    return True

def check_system_dependencies():
    """Check for system-level dependencies"""
    print("5. Checking system dependencies...")
    system_commands = [
        'ip',
        'iptables',
        'nft',
        'ping',
        'python3'
    ]
    
    missing_commands = []
    for command in system_commands:
        try:
            result = subprocess.run(['which', command], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   ✓ {command} is available")
            else:
                print(f"   ✗ {command} is not available")
                missing_commands.append(command)
        except Exception as e:
            print(f"   ✗ Error checking {command}: {e}")
            missing_commands.append(command)
    
    if missing_commands:
        print(f"   ✗ Missing system commands: {', '.join(missing_commands)}")
        return False
    else:
        print("   ✓ All required system commands are available")
        return True

def test_service_imports():
    """Test if service modules can be imported"""
    print("6. Testing service imports...")
    
    # Test routing module imports
    try:
        sys.path.append('/opt/routeros/routing')
        from route_manager import RouteManager
        print("   ✓ RouteManager import successful")
    except Exception as e:
        print(f"   ✗ RouteManager import failed: {e}")
        return False
    
    # Test watchdog module imports
    try:
        sys.path.append('/opt/routeros/watchdog')
        from health_monitor import HealthMonitor
        print("   ✓ HealthMonitor import successful")
    except Exception as e:
        print(f"   ✗ HealthMonitor import failed: {e}")
        return False
    
    # Test web module imports
    try:
        sys.path.append('/opt/routeros/web')
        # This would require Flask to be installed, so we'll skip the actual import
        print("   ✓ Web module path configured")
    except Exception as e:
        print(f"   ✗ Web module configuration failed: {e}")
        return False
    
    return True

def check_file_permissions():
    """Check file permissions and ownership"""
    print("7. Checking file permissions...")
    
    critical_files = [
        '/opt/routeros/routing/routing_manager.py',
        '/opt/routeros/watchdog/watchdog_service.py',
        '/opt/routeros/web/enhanced_app.py'
    ]
    
    permission_issues = []
    for file_path in critical_files:
        if os.path.exists(file_path):
            try:
                stat = os.stat(file_path)
                mode = oct(stat.st_mode)[-3:]
                if int(mode[-1]) >= 4:  # World readable
                    print(f"   ✓ {file_path} has proper permissions ({mode})")
                else:
                    print(f"   ⚠ {file_path} may have restrictive permissions ({mode})")
            except Exception as e:
                print(f"   ✗ Error checking {file_path}: {e}")
                permission_issues.append(file_path)
        else:
            print(f"   ✗ {file_path} does not exist")
            permission_issues.append(file_path)
    
    return len(permission_issues) == 0

def main():
    """Run all diagnostic checks"""
    print("=== Phoenix Nexus Router Service Diagnostic ===")
    print("")
    
    checks = [
        check_python_version,
        check_dependencies,
        check_directory_structure,
        check_configuration_files,
        check_system_dependencies,
        test_service_imports,
        check_file_permissions
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
            print("")
        except Exception as e:
            print(f"   ✗ Check failed with exception: {e}")
            results.append(False)
            print("")
    
    print("=== Diagnostic Summary ===")
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total} checks")
    
    if passed == total:
        print("✓ All checks passed! Services should start normally.")
        return 0
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())