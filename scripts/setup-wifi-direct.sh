#!/bin/bash

# WiFi Direct Setup Script for WiFi Connect
# This script helps configure your system for WiFi Direct (P2P) support

set -e

echo "WiFi Connect - WiFi Direct Setup Script"
echo "======================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Check if wpa_supplicant is installed
if ! command -v wpa_supplicant &> /dev/null; then
    echo "Error: wpa_supplicant is not installed"
    echo "Please install wpa_supplicant first:"
    echo "  Ubuntu/Debian: sudo apt-get install wpasupplicant"
    echo "  CentOS/RHEL: sudo yum install wpa_supplicant"
    exit 1
fi

# Check if wpa_cli is installed
if ! command -v wpa_cli &> /dev/null; then
    echo "Error: wpa_cli is not installed"
    echo "Please install wpa_supplicant package which includes wpa_cli"
    exit 1
fi

# Check if iw is installed
if ! command -v iw &> /dev/null; then
    echo "Error: iw is not installed"
    echo "Please install iw first:"
    echo "  Ubuntu/Debian: sudo apt-get install iw"
    echo "  CentOS/RHEL: sudo yum install iw"
    exit 1
fi

echo "✓ Required tools are installed"

# Check WiFi hardware capabilities
echo ""
echo "Checking WiFi hardware capabilities..."

# Get WiFi interfaces
WIFI_INTERFACES=$(iw dev | grep Interface | awk '{print $2}')

if [ -z "$WIFI_INTERFACES" ]; then
    echo "Error: No WiFi interfaces found"
    echo "Please ensure your WiFi hardware is properly installed and recognized"
    exit 1
fi

echo "Found WiFi interfaces: $WIFI_INTERFACES"

# Check P2P support
P2P_SUPPORT=$(iw list | grep -A 8 "Supported interface modes" | grep -E "(P2P-client|P2P-GO|P2P-device)" | wc -l)

if [ "$P2P_SUPPORT" -lt 2 ]; then
    echo "Warning: Your WiFi hardware may not fully support WiFi Direct (P2P)"
    echo "Found P2P modes: $(iw list | grep -A 8 'Supported interface modes' | grep -E '(P2P-client|P2P-GO|P2P-device)')"
    echo "You need at least P2P-GO and P2P-device support for WiFi Direct"
    echo ""
    echo "Continuing anyway - some features may not work..."
else
    echo "✓ WiFi hardware supports P2P modes"
fi

# Check if wpa_supplicant supports P2P
echo ""
echo "Checking wpa_supplicant P2P support..."

WPA_VERSION=$(wpa_supplicant -v 2>&1 | head -n 1)
echo "wpa_supplicant version: $WPA_VERSION"

# Create backup of existing wpa_supplicant.conf if it exists
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [ -f "$WPA_CONF" ]; then
    echo ""
    echo "Backing up existing wpa_supplicant.conf..."
    cp "$WPA_CONF" "${WPA_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "✓ Backup created: ${WPA_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Create wpa_supplicant directory if it doesn't exist
mkdir -p /etc/wpa_supplicant

# Create or update wpa_supplicant.conf with P2P support
echo ""
echo "Configuring wpa_supplicant for P2P support..."

cat > "$WPA_CONF" << 'EOF'
# WiFi Connect - wpa_supplicant configuration with P2P support
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

# P2P Device configuration
device_name=DIRECT-EnVoidConnect
device_type=6-0050F204-1
config_methods=keypad
p2p_go_intent=15
persistent_reconnect=1

# Set your country code for regulatory compliance
# Change this to your country code (e.g., US, GB, DE, etc.)
country=US

# Optional: Uncomment and set a fixed MAC address for persistent groups
# p2p_device_persistent_mac_addr=02:00:00:00:00:00
# p2p_device_random_mac_addr=0

EOF

echo "✓ wpa_supplicant.conf configured for P2P support"

# Set proper permissions
chmod 600 "$WPA_CONF"
echo "✓ Set secure permissions on wpa_supplicant.conf"

# Check if NetworkManager is running and might interfere
if systemctl is-active --quiet NetworkManager; then
    echo ""
    echo "Warning: NetworkManager is running"
    echo "NetworkManager may interfere with WiFi Direct functionality"
    echo "Consider stopping NetworkManager or configuring it to ignore your WiFi interface:"
    echo "  sudo systemctl stop NetworkManager"
    echo "  # or configure NetworkManager to ignore the interface"
fi

# Restart wpa_supplicant service
echo ""
echo "Restarting wpa_supplicant service..."

# Stop any running wpa_supplicant processes
pkill -f wpa_supplicant || true
sleep 2

# Start wpa_supplicant with P2P support
# Try different methods depending on the system
if systemctl list-unit-files | grep -q wpa_supplicant.service; then
    systemctl restart wpa_supplicant.service
    echo "✓ wpa_supplicant service restarted"
else
    # Manual start for systems without systemd service
    echo "Starting wpa_supplicant manually..."
    WIFI_INTERFACE=$(echo $WIFI_INTERFACES | awk '{print $1}')
    wpa_supplicant -B -i "$WIFI_INTERFACE" -c "$WPA_CONF" -D nl80211,wext
    echo "✓ wpa_supplicant started manually on interface $WIFI_INTERFACE"
fi

# Wait a moment for wpa_supplicant to initialize
sleep 3

# Check if P2P device was created
echo ""
echo "Checking P2P device creation..."

P2P_DEVICE=$(iw dev | grep -A 1 "type P2P-device" | grep Interface | awk '{print $2}' | head -n 1)

if [ -n "$P2P_DEVICE" ]; then
    echo "✓ P2P device created: $P2P_DEVICE"
    
    # Test basic P2P functionality
    echo ""
    echo "Testing P2P functionality..."
    
    if wpa_cli -i "$P2P_DEVICE" status &> /dev/null; then
        echo "✓ Can communicate with P2P device via wpa_cli"
    else
        echo "Warning: Cannot communicate with P2P device via wpa_cli"
        echo "Check wpa_supplicant logs: journalctl -u wpa_supplicant -f"
    fi
else
    echo "Warning: No P2P device found"
    echo "Available interfaces:"
    iw dev
    echo ""
    echo "Check wpa_supplicant logs: journalctl -u wpa_supplicant -f"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Test WiFi Direct mode: wifi-connect --wifi-direct"
echo "2. Check the WiFi Direct documentation: docs/wifi-direct.md"
echo "3. Monitor logs: journalctl -u wpa_supplicant -f"
echo ""
echo "If you encounter issues:"
echo "- Ensure your WiFi hardware supports P2P modes"
echo "- Check that wpa_supplicant has P2P support compiled in"
echo "- Verify no other network managers are interfering"
echo "- Review the troubleshooting section in docs/wifi-direct.md" 