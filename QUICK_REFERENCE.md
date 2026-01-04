# Smart Multi-WAN Router OS - Quick Reference Card

## 🚀 Quick Start Commands

### Installation (Fresh Ubuntu 24.04)
```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Clone and install
cd /opt && sudo git clone https://github.com/Djnirds1984/Phoenix-Nexus-Router.git routeros
cd routeros && sudo chmod +x setup.sh

# 3. Run setup (customize for your network)
sudo ./setup.sh --wan1-interface eth0 --wan1-gateway 192.168.100.1 \
  --wan2-interface eth1 --wan2-gateway 192.168.200.1 \
  --lan-interface eth2 --lan-network 192.168.1.0/24

# 4. Start services
sudo systemctl start routeros-watchdog routeros-web
sudo systemctl enable routeros-watchdog routeros-web
```

## 📊 System Status & Monitoring

### Check System Status
```bash
# Quick status check
/opt/routeros/scripts/status.sh

# Service status
sudo systemctl status routeros-watchdog routeros-web

# Interface status
routeros-kill-switch --status

# Network statistics
ip -s link
ip route show
```

### View Logs
```bash
# Watch real-time logs
sudo journalctl -u routeros-watchdog -f
sudo journalctl -u routeros-web -f

# View recent logs
sudo journalctl -u routeros-watchdog -n 50
sudo journalctl -u routeros-web -n 50

# Check all RouterOS logs
tail -f /var/log/routeros-*.log
```

## 🔧 Interface Management

### Kill-Switch Operations
```bash
# Show interface status
routeros-kill-switch --status

# Disable interface (kill-switch)
routeros-kill-switch --disable eth1

# Enable interface
routeros-kill-switch --enable eth1

# Maintenance mode (30 minutes)
routeros-kill-switch --maintenance 30

# Force operation (no confirmation)
routeros-kill-switch --disable eth1 --force
```

### Manual Interface Control
```bash
# Via watchdog service
sudo /opt/routeros/watchdog/watchdog_service.py --interface-control eth1 disable
sudo /opt/routeros/watchdog/watchdog_service.py --interface-control eth1 enable

# Check interface details
ip link show eth1
ethtool eth1  # If available
```

## 🌐 Network Configuration

### Interface Configuration
```bash
# Edit interface config
sudo nano /opt/routeros/config/interfaces.json

# Apply network changes
sudo netplan apply

# Test connectivity
ping -I eth0 8.8.8.8  # Test WAN1
ping -I eth1 8.8.8.8  # Test WAN2
```

### Routing Tables
```bash
# View all routing tables
ip route show table all

# View specific table
ip route show table wan1
ip route show table wan2

# Check multipath routing
ip route show | grep nexthop
```

## 🖥️ Web Interface

### Access Dashboard
- **URL**: http://192.168.1.1:8080
- **API**: http://192.168.1.1:8081

### Quick Web Operations
```bash
# Test web interface locally
curl http://localhost:8080/api/status

# Check if port is listening
sudo netstat -tlnp | grep 8080
sudo ss -tlnp | grep 8080
```

## 🔍 Troubleshooting

### Service Won't Start
```bash
# Check service logs
sudo journalctl -u routeros-watchdog --no-pager -l
sudo journalctl -u routeros-web --no-pager -l

# Check file permissions
ls -la /opt/routeros/
sudo chown -R root:root /opt/routeros
sudo chmod -R 755 /opt/routeros

# Test watchdog manually
sudo python3 /opt/routeros/watchdog/watchdog_service.py --test
```

### Interface Detection Issues
```bash
# List all interfaces
ip link show

# Check interface configuration
cat /opt/routeros/config/interfaces.json

# Restart network services
sudo systemctl restart systemd-networkd
sudo netplan apply
```

### Failover Not Working
```bash
# Test health monitoring
sudo python3 /opt/routeros/watchdog/health_monitor.py --test

# Check connection tracking
conntrack -L | head -20

# Test manual failover
routeros-kill-switch --disable eth0
# Wait 10 seconds
routeros-kill-switch --enable eth0
```

### Web Interface Issues
```bash
# Check firewall rules
sudo nft list ruleset

# Test local access
curl http://localhost:8080

# Check service binding
sudo netstat -tlnp | grep 8080

# Restart web service
sudo systemctl restart routeros-web
```

## 📈 Performance Monitoring

### Bandwidth Monitoring
```bash
# Real-time bandwidth per interface
iftop -i eth0  # If available
nload eth0 eth1  # If available

# Interface statistics
ip -s link show eth0
ip -s link show eth1
```

### Connection Tracking
```bash
# View connection count
conntrack -C

# View active connections
conntrack -L | wc -l

# Monitor connection changes
conntrack -E
```

### System Resources
```bash
# CPU and memory usage
top -p $(pgrep -f routeros)

# Disk usage
df -h /opt/routeros

# System load
uptime
```

## 🔒 Security & Firewall

### Firewall Rules
```bash
# View current rules
sudo nft list ruleset

# Check firewall status
sudo systemctl status nftables

# Reload firewall rules
sudo nft -f /etc/nftables.conf
```

### Connection Security
```bash
# Check for suspicious connections
netstat -tulnp | grep -v 127.0.0.1

# Monitor failed connections
grep "Failed\|DROP" /var/log/routeros-*.log
```

## ⚡ Emergency Commands

### Complete System Restart
```bash
# Restart all RouterOS services
sudo systemctl restart routeros-watchdog routeros-web

# Reset to defaults (backup first!)
sudo cp /opt/routeros/config/interfaces.json /opt/routeros/config/interfaces.json.backup
sudo /opt/routeros/scripts/configure_network.sh --reset
```

### Network Reset
```bash
# Reset network configuration
sudo netplan apply --debug
sudo systemctl restart systemd-networkd

# Flush routing tables
sudo ip route flush table all
sudo systemctl restart routeros-watchdog
```

### Service Recovery
```bash
# Force service restart
sudo systemctl stop routeros-watchdog routeros-web
sleep 5
sudo systemctl start routeros-watchdog routeros-web

# Check for zombie processes
ps aux | grep -i routeros | grep -v grep
```

## 📋 Configuration Files

### Key Configuration Files
```
/opt/routeros/config/interfaces.json          # Network interfaces
/opt/routeros/config/health_monitor.json       # Health check settings
/opt/routeros/config/connection_rules.json   # Traffic rules
/etc/nftables.conf                           # Firewall rules
/etc/netplan/*.yaml                          # Network configuration
```

### Log Files
```
/var/log/routeros-watchdog.log              # Watchdog service
/var/log/routeros-health.log                # Health monitoring
/var/log/routeros-routing.log               # Routing events
/var/log/routeros-web.log                   # Web interface
/var/log/routeros-latency.log               # Latency monitoring
```

## 🆘 Getting Help

### Check Documentation
```bash
# View installation summary
cat /opt/routeros/INSTALLATION_SUMMARY.md

# Check README
cat /opt/routeros/README.md
```

### System Information
```bash
# Get system info
lsb_release -a
uname -a
ip link show
```

### Support Commands
```bash
# Generate support bundle
/opt/routeros/scripts/status.sh > /tmp/routeros-support.txt
sudo journalctl -u routeros-* >> /tmp/routeros-support.txt

# Check for common issues
routeros-kill-switch --status
sudo systemctl is-active routeros-watchdog routeros-web
```

---

**Remember**: Always backup your configuration before making changes!
**Web Interface**: http://192.168.1.1:8080
**Support**: Check logs first, then documentation