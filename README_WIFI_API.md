# WiFi Connect API Server

A standalone WiFi management API server that provides all the endpoints needed for the WiFi Connect frontend. This server uses `nmcli` and `iw` commands to manage WiFi connections on Linux systems.

## Features

- **Network Scanning**: Scan and list available WiFi networks
- **Connection Management**: Connect to WiFi networks with or without passwords
- **Saved Networks**: Manage saved/remembered networks
- **WiFi Direct**: Toggle WiFi Direct mode (hotspot functionality)
- **Signal Strength**: Get real-time signal strength information
- **Health Monitoring**: Server health checks and error handling

## Prerequisites

### Required Tools
- `nmcli` (NetworkManager command line interface)
- `iw` (wireless tools)

## Configuration

The WiFi API Server uses a minimal and elegant configuration system that supports both environment variables and a JSON configuration file.

### Configuration File (`wifi_config.json`)

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "info"
  },
  "wifi": {
    "hotspot_name_prefix": "WiFiDirect",
    "hotspot_password": "12345678",
    "scan_timeout": 30,
    "rescan_delay": 2
  },
  "cors": {
    "enabled": true,
    "origins": ["*"]
  }
}
```

### Environment Variables

You can override any configuration using environment variables:

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `WIFI_SERVER_HOST` | Server host address | `0.0.0.0` |
| `WIFI_SERVER_PORT` | Server port | `8000` |
| `WIFI_SERVER_LOG_LEVEL` | Log level (debug, info, warning, error) | `info` |
| `WIFI_HOTSPOT_NAME_PREFIX` | Hotspot name prefix | `WiFiDirect` |
| `WIFI_HOTSPOT_PASSWORD` | Hotspot password | `12345678` |
| `WIFI_SCAN_TIMEOUT` | Network scan timeout (seconds) | `30` |
| `WIFI_RESCAN_DELAY` | Delay between rescans (seconds) | `2` |
| `WIFI_CORS_ENABLED` | Enable CORS (true/false) | `true` |
| `WIFI_CORS_ORIGINS` | CORS origins (comma-separated) | `*` |

### Examples

**Using environment variables:**
```bash
export WIFI_SERVER_PORT=9000
export WIFI_HOTSPOT_NAME_PREFIX="MyHotspot"
export WIFI_HOTSPOT_PASSWORD="mypassword123"
python3 wifi_api_server.py
```

**Using configuration file:**
```bash
# Edit wifi_config.json
python3 wifi_api_server.py
```

**Create default configuration:**
```bash
python3 config.py
```

## Usage

### Quick Start

1. **Run with the startup script**:
   ```bash
   # With sudo (recommended for WiFi management)
   sudo ./start.sh
   
   # Or without sudo (may have limited functionality)
   ./start.sh
   ```

2. **Or run directly**:
   ```bash
   # With sudo (recommended for WiFi management)
   sudo python3 wifi_api_server.py
   
   # Or without sudo (may have limited functionality)
   python3 wifi_api_server.py
   ```

3. **Access the WiFi Connect interface**:
   - Open your browser and go to: `http://localhost:8000` (or configured port)
   - The server will serve the WiFi Connect frontend automatically

## API Endpoints

### Health Check
- **GET** `/health` - Check server status and NetworkManager availability

### WiFi Direct Management
- **GET** `/get-wifi-direct` - Get current WiFi Direct status
- **POST** `/set-wifi-direct` - Toggle WiFi Direct mode (hotspot)

### Network Management
- **GET** `/list-networks` - Scan and list available WiFi networks
- **GET** `/list-connected` - Get currently connected network information
- **GET** `/list-saved` - Get list of saved/remembered networks

### Connection Management
- **POST** `/connect` - Connect to a WiFi network
- **POST** `/forget-network` - Remove a specific saved network
- **POST** `/forget-all` - Remove all saved networks

## API Request/Response Examples

### List Available Networks
```bash
curl -X GET "http://localhost:8000/list-networks?use_cache=true"
```

**Response**:
```json
{
  "networks": [
    {
      "ssid": "Home WiFi",
      "security": "wpa2",
      "signal_strength": 85,
      "frequency": "2.4 GHz"
    },
    {
      "ssid": "Guest Network",
      "security": "open",
      "signal_strength": 60,
      "frequency": "5 GHz"
    }
  ]
}
```

### Connect to Network
```bash
curl -X POST "http://localhost:8000/connect" \
  -H "Content-Type: application/json" \
  -d '{"ssid": "Home WiFi", "passphrase": "mypassword"}'
```

**Response**:
```json
{
  "success": true,
  "message": "Connected to Home WiFi"
}
```

### Get Connected Network
```bash
curl -X GET "http://localhost:8000/list-connected"
```

**Response**:
```json
{
  "connected": {
    "ssid": "Home WiFi",
    "interface": "wlan0",
    "security": "wpa2",
    "signal_strength": 85,
    "ip_address": "192.168.1.100"
  }
}
```

### Toggle WiFi Direct
```bash
curl -X POST "http://localhost:8000/set-wifi-direct" \
  -H "Content-Type: application/json" \
  -d '{"value": "true"}'
```

**Response**:
```json
{
  "value": true
}
```

## Error Handling

The API includes comprehensive error handling:

### Error Response Format
```json
{
  "error": "error_type",
  "message": "Human readable error message"
}
```

### Common Error Types
- `battery_low` - Device battery is too low for scanning
- `scan_failed` - Failed to scan for networks
- `connection_failed` - Failed to connect to network
- `network_not_found` - Network not found or unavailable

## Security Considerations

1. **Root Privileges**: The server needs root privileges to manage WiFi connections
2. **Network Security**: WiFi passwords are handled securely through NetworkManager
3. **CORS**: CORS is enabled for all origins (configure as needed for production)
4. **Input Validation**: All inputs are validated using Pydantic models

## Troubleshooting

### Debug Mode

Enable debug logging by modifying the logging level in `wifi_api_server.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Development

### Adding New Endpoints

1. Add new Pydantic models for request/response
2. Create new endpoint function with appropriate decorator
3. Add error handling and logging
4. Test with the frontend

### Testing

Test individual endpoints:
```bash
# Test health check
curl http://localhost:8000/health

# Test network scanning
curl http://localhost:8000/list-networks

# Test connection (replace with real network)
curl -X POST http://localhost:8000/connect \
  -H "Content-Type: application/json" \
  -d '{"ssid": "test", "passphrase": "test123"}'
```

## License

This WiFi API server is part of the IronPort project and follows the same licensing terms.
