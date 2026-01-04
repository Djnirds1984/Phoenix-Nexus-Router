#!/bin/bash

# Test script to manually start and debug RouterOS services

echo "=== Phoenix Nexus Router Service Test Script ==="
echo "Testing services individually to identify issues..."
echo ""

# Test routing manager
echo "1. Testing Routing Manager..."
cd /opt/routeros/routing
python3 routing_manager.py &
ROUTING_PID=$!
echo "Routing Manager PID: $ROUTING_PID"
sleep 3
if ps -p $ROUTING_PID > /dev/null; then
    echo "✓ Routing Manager is running"
    kill $ROUTING_PID
else
    echo "✗ Routing Manager failed to start"
    echo "Checking for errors..."
    python3 routing_manager.py 2>&1 | head -10
fi
echo ""

# Test watchdog service
echo "2. Testing Watchdog Service..."
cd /opt/routeros/watchdog
python3 watchdog_service.py &
WATCHDOG_PID=$!
echo "Watchdog Service PID: $WATCHDOG_PID"
sleep 3
if ps -p $WATCHDOG_PID > /dev/null; then
    echo "✓ Watchdog Service is running"
    kill $WATCHDOG_PID
else
    echo "✗ Watchdog Service failed to start"
    echo "Checking for errors..."
    python3 watchdog_service.py 2>&1 | head -10
fi
echo ""

# Test web interface
echo "3. Testing Web Interface..."
cd /opt/routeros/web
python3 enhanced_app.py --host 0.0.0.0 --port 8080 &
WEB_PID=$!
echo "Web Interface PID: $WEB_PID"
sleep 3
if ps -p $WEB_PID > /dev/null; then
    echo "✓ Web Interface is running"
    kill $WEB_PID
else
    echo "✗ Web Interface failed to start"
    echo "Checking for errors..."
    python3 enhanced_app.py --host 0.0.0.0 --port 8080 2>&1 | head -10
fi
echo ""

echo "=== Service Test Complete ==="
echo "Check the logs above for specific error messages."