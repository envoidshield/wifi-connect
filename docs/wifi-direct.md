# WiFi Direct Support in WiFi Connect

WiFi Connect now supports WiFi Direct (P2P) mode, which provides better compatibility with mobile devices and allows for direct peer-to-peer connections similar to Apple CarPlay and Android Auto.

## What is WiFi Direct?

WiFi Direct (also known as Wi-Fi P2P) allows devices to connect directly to each other without requiring a traditional wireless access point. This technology is used by:

- Apple CarPlay
- Android Auto
- Screen mirroring applications
- File sharing between devices
- IoT device setup

## Benefits of WiFi Direct Mode

1. **Better Mobile Compatibility**: Mobile devices can maintain their cellular/WiFi connection while connecting to your device
2. **No Routing Conflicts**: Unlike traditional AP mode, WiFi Direct doesn't interfere with the mobile device's internet connection
3. **Faster Discovery**: Devices appear more quickly in WiFi Direct scanning
4. **Industry Standard**: Used by major automotive and IoT manufacturers

## Enabling WiFi Direct Mode

### Command Line

To enable WiFi Direct mode, use the `--wifi-direct` flag:

```bash
wifi-connect --wifi-direct
```

You can combine it with other options:

```bash
wifi-connect --wifi-direct --portal-ssid "MyDevice-Setup" --portal-passphrase "12345678"
```

### Environment Variable

Set the `WIFI_DIRECT` environment variable:

```bash
export WIFI_DIRECT=true
wifi-connect
```

### Docker/Balena

In your `docker-compose.yml`:

```yaml
version: "2.1"

services:
    wifi-connect:
        build: ./wifi-connect
        network_mode: "host"
        labels:
            io.balena.features.dbus: '1'
        cap_add:
            - NET_ADMIN
        environment:
            DBUS_SYSTEM_BUS_ADDRESS: "unix:path=/host/run/dbus/system_bus_socket"
            WIFI_DIRECT: "true"
            PORTAL_SSID: "MyDevice-Setup"
```

## Requirements

### System Requirements

1. **wpa_supplicant with P2P support**: Ensure wpa_supplicant is compiled with P2P support
2. **P2P-capable WiFi hardware**: Check with `iw list | grep "P2P-GO"`
3. **Root privileges**: Required for P2P group creation

### Checking P2P Support

Verify your system supports WiFi Direct:

```bash
# Check if P2P-GO is supported
iw list | grep "Supported interface modes" -A 8

# Should show:
# * P2P-client
# * P2P-GO
# * P2P-device

# Check for P2P device
iw dev
# Should show a P2P-device interface like "p2p-dev-wlan0"
```

### wpa_supplicant Configuration

Ensure your `/etc/wpa_supplicant/wpa_supplicant.conf` includes P2P support:

```
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
device_name=DIRECT-MyDevice
device_type=6-0050F204-1
config_methods=keypad
p2p_go_intent=15
persistent_reconnect=1
country=US
```

## How It Works

1. **P2P Group Creation**: Creates a WiFi Direct group using wpa_supplicant
2. **Group Owner Role**: Your device becomes the Group Owner (GO)
3. **WPS Authentication**: Uses WPS PIN or Push Button for secure connection
4. **IP Configuration**: Configures the P2P interface with the specified gateway
5. **DHCP/DNS Services**: Runs dnsmasq on the P2P interface
6. **Captive Portal**: Serves the web interface for WiFi configuration

## Connection Process

### From Android Device

1. Go to **Settings** → **WiFi** → **Advanced** → **WiFi Direct**
2. Your device should appear as "DIRECT-[YourSSID]"
3. Tap to connect
4. Enter PIN if prompted (or use push button if no PIN configured)
5. Once connected, the captive portal should open automatically

### From iOS Device

iOS doesn't support WiFi Direct directly, but the P2P group also operates in AP mode:

1. Go to **Settings** → **WiFi**
2. Look for "DIRECT-[YourSSID]" in available networks
3. Connect using the configured passphrase
4. The captive portal should open automatically

## Troubleshooting

### P2P Device Not Found

```bash
# Check if wpa_supplicant is running with P2P support
ps aux | grep wpa_supplicant

# Restart wpa_supplicant with P2P support
sudo systemctl restart wpa_supplicant

# Check for P2P device creation
iw dev
```

### Group Creation Fails

```bash
# Check wpa_supplicant logs
journalctl -u wpa_supplicant -f

# Manually test P2P group creation
wpa_cli -i p2p-dev-wlan0 p2p_group_add freq=2412
```

### Interface Not Available

```bash
# Check if P2P interface was created
ip link show | grep p2p

# Check interface status
ip addr show p2p-wlan0-0
```

### Mobile Device Can't See the Group

1. Ensure 2.4GHz band is used (better compatibility)
2. Check country code in wpa_supplicant.conf
3. Verify P2P device name is set correctly
4. Try restarting WiFi Direct on the mobile device

## Advanced Configuration

### Custom P2P Interface Name

The P2P interface name is automatically determined by wpa_supplicant, typically `p2p-wlan0-0`.

### Frequency Selection

WiFi Direct uses 2.4GHz (channel 1, 2412 MHz) by default for better compatibility. This can be modified in the WiFi Direct implementation.

### WPS Configuration

- **PIN Mode**: Uses a fixed PIN (default: from passphrase)
- **PBC Mode**: Push Button Configuration (no PIN required)

## Compatibility

### Tested Devices

- **Android**: 6.0+ (WiFi Direct support)
- **iOS**: 9.0+ (AP mode compatibility)
- **Raspberry Pi**: 3B+, 4B with built-in WiFi
- **Linux**: Ubuntu 18.04+, Debian 10+

### Known Limitations

1. Some older Android devices may require manual reconnection
2. iOS devices connect via AP mode, not true WiFi Direct
3. Single P2P group limitation on most hardware
4. Requires compatible WiFi chipset

## Migration from Traditional AP Mode

WiFi Direct mode is backward compatible. If WiFi Direct fails to initialize, the system will fall back to traditional AP mode automatically.

To migrate existing deployments:

1. Add `--wifi-direct` flag to your startup command
2. Ensure wpa_supplicant P2P support is available
3. Test with your target mobile devices
4. Monitor logs for any P2P-specific errors

## Security Considerations

- WPS PIN should be at least 8 digits
- Consider using PBC mode for easier setup
- P2P groups use WPA2 security by default
- Monitor connected devices through wpa_cli

For more information, see the [WiFi Direct specification](https://www.wi-fi.org/discover-wi-fi/wi-fi-direct) and [wpa_supplicant P2P documentation](https://w1.fi/wpa_supplicant/devel/p2p.html). 