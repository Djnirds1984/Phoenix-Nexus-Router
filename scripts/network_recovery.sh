#!/bin/bash

# EMERGENCY NETWORK RECOVERY SCRIPT
# This script will restore your network connectivity if something goes wrong

echo "🚨 EMERGENCY NETWORK RECOVERY 🚨"
echo "This script will restore your network to working state"
echo ""

# Function to test connectivity
test_connectivity() {
    echo "🔍 Testing network connectivity..."
    if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
        echo "✅ Network is working!"
        return 0
    else
        echo "❌ Network is down - proceeding with recovery"
        return 1
    fi
}

# Function to restore NetworkManager
restore_networkmanager() {
    echo "🔄 Restoring NetworkManager..."
    systemctl enable NetworkManager 2>/dev/null
    systemctl start NetworkManager 2>/dev/null
    systemctl restart NetworkManager 2>/dev/null
    echo "✅ NetworkManager restored"
}

# Function to restore systemd-networkd
restore_systemd_networkd() {
    echo "🔄 Restoring systemd-networkd..."
    systemctl enable systemd-networkd 2>/dev/null
    systemctl start systemd-networkd 2>/dev/null
    systemctl restart systemd-networkd 2>/dev/null
    echo "✅ systemd-networkd restored"
}

# Function to restart network services
restart_network_services() {
    echo "🔄 Restarting network services..."
    
    # Try different methods to restart networking
    if command -v netplan > /dev/null; then
        echo "📋 Applying netplan configuration..."
        netplan apply 2>/dev/null || true
    fi
    
    if command -v nmcli > /dev/null; then
        echo "📋 Restarting NetworkManager connections..."
        nmcli networking off 2>/dev/null || true
        sleep 2
        nmcli networking on 2>/dev/null || true
    fi
    
    # Restart dhclient for DHCP
    pkill dhclient 2>/dev/null || true
    sleep 1
    dhclient -r 2>/dev/null || true
    dhclient 2>/dev/null || true
    
    echo "✅ Network services restarted"
}

# Function to restore default routes
restore_default_routes() {
    echo "🔄 Restoring default routes..."
    
    # Remove any custom routing tables first
    ip route flush table 100 2>/dev/null || true
    ip route flush table 200 2>/dev/null || true
    ip route flush table 300 2>/dev/null || true
    
    # Clear main routing table
    ip route flush all 2>/dev/null || true
    
    # Get the primary interface (usually the one with default route)
    PRIMARY_IFACE=$(ip route | grep default | head -1 | awk '{print $5}' | head -1)
    
    if [ -n "$PRIMARY_IFACE" ]; then
        echo "📋 Found primary interface: $PRIMARY_IFACE"
        
        # Get IP address of primary interface
        IP_ADDR=$(ip addr show "$PRIMARY_IFACE" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
        
        if [ -n "$IP_ADDR" ]; then
            echo "📋 Found IP address: $IP_ADDR"
            
            # Try to get gateway from DHCP
            echo "📋 Attempting to restore gateway via DHCP..."
            dhclient "$PRIMARY_IFACE" 2>/dev/null || true
            
            # If DHCP fails, try common gateway addresses
            GATEWAY=$(ip route | grep default | awk '{print $3}' | head -1)
            if [ -z "$GATEWAY" ]; then
                echo "📋 Trying common gateway addresses..."
                # Try common router IPs
                for gw in "192.168.1.1" "192.168.0.1" "10.0.0.1" "172.16.0.1"; do
                    if ping -c 1 -W 1 "$gw" > /dev/null 2>&1; then
                        ip route add default via "$gw" dev "$PRIMARY_IFACE" 2>/dev/null || true
                        echo "✅ Added default route via $gw"
                        break
                    fi
                done
            fi
        fi
    fi
    
    echo "✅ Default routes restored"
}

# Function to stop Phoenix Router services
stop_phoenix_services() {
    echo "🛑 Stopping Phoenix Router services..."
    
    # Stop all router services
    systemctl stop phoenix-safe-web.service 2>/dev/null || true
    systemctl stop routeros-web.service 2>/dev/null || true
    systemctl stop routeros-watchdog.service 2>/dev/null || true
    systemctl stop routeros-routing.service 2>/dev/null || true
    
    # Disable them so they don't restart
    systemctl disable phoenix-safe-web.service 2>/dev/null || true
    systemctl disable routeros-web.service 2>/dev/null || true
    systemctl disable routeros-watchdog.service 2>/dev/null || true
    systemctl disable routeros-routing.service 2>/dev/null || true
    
    # Kill any remaining processes
    pkill -f "python.*router" 2>/dev/null || true
    pkill -f "python.*phoenix" 2>/dev/null || true
    
    echo "✅ Phoenix Router services stopped"
}

# Function to reset iptables/nftables
reset_firewall() {
    echo "🔄 Resetting firewall rules..."
    
    # Reset iptables
    iptables -F 2>/dev/null || true
    iptables -t nat -F 2>/dev/null || true
    iptables -t mangle -F 2>/dev/null || true
    iptables -X 2>/dev/null || true
    
    # Reset nftables
    nft flush ruleset 2>/dev/null || true
    
    echo "✅ Firewall rules reset"
}

# Function to show network status
show_network_status() {
    echo "📊 Current Network Status:"
    echo "=========================="
    
    # Show interfaces
    echo "Network Interfaces:"
    ip addr show | grep -E "^[0-9]+:" | awk '{print $2}' | sed 's/://g' | while read iface; do
        if [ "$iface" != "lo" ]; then
            ip addr show "$iface" | grep 'inet ' | awk '{print "  " $2 " on " $NF}'
        fi
    done
    
    echo ""
    echo "Routing Table:"
    ip route show | head -5
    
    echo ""
    echo "DNS Configuration:"
    cat /etc/resolv.conf 2>/dev/null | grep nameserver | head -3
    
    echo ""
    echo "Service Status:"
    systemctl is-active NetworkManager systemd-networkd 2>/dev/null | while read status; do
        echo "  $status"
    done
}

# Main recovery process
main() {
    echo "Starting network recovery process..."
    echo ""
    
    # Test current connectivity
    if test_connectivity; then
        echo "Network appears to be working. Showing current status:"
        show_network_status
        echo ""
        read -p "Do you want to proceed with recovery anyway? (y/N): " proceed
        if [[ ! "$proceed" =~ ^[Yy]$ ]]; then
            echo "Recovery cancelled."
            exit 0
        fi
    fi
    
    echo ""
    echo "🔄 Starting network recovery..."
    echo ""
    
    # Step 1: Stop Phoenix services
    stop_phoenix_services
    echo ""
    
    # Step 2: Reset firewall
    reset_firewall
    echo ""
    
    # Step 3: Restore network management
    restore_networkmanager
    restore_systemd_networkd
    echo ""
    
    # Step 4: Restart network services
    restart_network_services
    echo ""
    
    # Step 5: Restore routing
    restore_default_routes
    echo ""
    
    # Step 6: Test connectivity
    echo "🔄 Testing connectivity after recovery..."
    sleep 5
    
    if test_connectivity; then
        echo ""
        echo "✅ NETWORK RECOVERY SUCCESSFUL!"
        echo ""
        show_network_status
        echo ""
        echo "🎉 Your network should now be working!"
        echo "If you still have issues, try rebooting the system."
    else
        echo ""
        echo "❌ Recovery incomplete - trying alternative methods..."
        echo ""
        echo "🔄 Attempting complete network reset..."
        
        # Last resort: reboot suggestion
        echo "💡 SUGGESTION: Try rebooting your system with:"
        echo "   sudo reboot"
        echo ""
        echo "If reboot doesn't help, you may need to:"
        echo "1. Check physical network connections"
        echo "2. Verify your router/modem is working"
        echo "3. Contact your ISP"
        echo "4. Check system logs: journalctl -xe"
    fi
}

# Handle command line arguments
case "${1:-}" in
    --status)
        show_network_status
        ;;
    --test)
        test_connectivity
        ;;
    *)
        main
        ;;
esac