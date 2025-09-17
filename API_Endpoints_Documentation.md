# WiFi Connect API Endpoints Documentation

This document provides a comprehensive list of all available POST and GET requests in the WiFi Connect API server.

## Base URL
The API server runs on the configured host and port (default: localhost:8000)

## GET Endpoints

### 1. Root Endpoint
- **URL**: `/`
- **Method**: GET
- **Description**: Serves the main index.html file with optional touchscreen support
- **Features**: 
  - Dynamically injects keyboard scripts if `ENABLE_SURFACE_SUPPORT=1` environment variable is set
  - Replaces `<!-- kioskboard -->` and `<!-- keyboard -->` placeholders with actual script tags so it eble the keyboard
- **Response**: HTML content of the main interface

### 2. Health Check
- **URL**: `/health`
- **Method**: GET
- **Description**: Health check endpoint to verify API server status
- **Response**: 
  ```json
  {
    "status": "healthy",
    "message": "WiFi API is running"
  }
  ```
- **Error Response**: HTTP 503 if NetworkManager is not available

### 3. List Available Networks
- **URL**: `/list-networks`
- **Method**: GET
- **Description**: Lists all available WiFi networks
- **Query Parameters**:
  - `use_cache` (bool, optional): Whether to use cached network data (default: true)
- **Response**:
  ```json
  {
    "networks": [
      {
        "ssid": "NetworkName",
        "security": "wpa2",
        "signal_strength": 85,
        "frequency": "2.4 GHz"
      }
    ]
  }
  ```
- **Features**:
  - Temporarily disables active hotspots to perform scans
  - Implements retry logic for reliable scanning
  - Caches results for performance

### 4. List Connected Network
- **URL**: `/list-connected`
- **Method**: GET
- **Description**: Get information about the currently connected WiFi network
- **Response**:
  ```json
  {
    "connected": {
      "ssid": "ConnectedNetwork",
      "interface": "wlan0",
      "security": "wpa2",
      "connection_name": "ConnectedNetwork"
    }
  }
  ```
- **Response when not connected**:
  ```json
  {
    "connected": null
  }
  ```

### 5. List Saved Networks
- **URL**: `/list-saved`
- **Method**: GET
- **Description**: Get list of all saved WiFi networks
- **Response**:
  ```json
  {
    "saved_networks": [
      {
        "ssid": "SavedNetwork1",
        "interface": "wlan0",
        "security": "wpa2",
        "connection_name": "SavedNetwork1"
      }
    ]
  }
  ```

### 6. Get WiFi Direct Status
- **URL**: `/get-wifi-direct`
- **Method**: GET
- **Description**: Get current WiFi Direct mode status
- **Response**:
  ```json
  {
    "value": true
  }
  ```

### 7. Get WiFi Connect Status
- **URL**: `/get-wifi-connect`
- **Method**: GET
- **Description**: Get current WiFi Connect mode status
- **Response**:
  ```json
  {
    "value": true
  }
  ```

### 8. Get Scan Status
- **URL**: `/scan-status`
- **Method**: GET
- **Description**: Get information about network scanning capabilities and warnings
- **Response**:
  ```json
  {
    "hotspot_active": true,
    "hotspot_type": "connect",
    "can_scan": true,
    "warning_message": "Scanning will temporarily disconnect clients from WiFi Connect hotspot"
  }
  ```

## POST Endpoints

### 1. Set WiFi Direct Mode
- **URL**: `/set-wifi-direct`
- **Method**: POST
- **Description**: Toggle WiFi Direct mode on/off
- **Request Body**:
  ```json
  {
    "value": "true"
  }
  ```
- **Response**:
  ```json
  {
    "value": true
  }
  ```
- **Features**:
  - Creates WiFi Direct hotspot when enabled
  - Manages dnsmasq for DHCP services
  - Cleans up connections when disabled

### 2. Set WiFi Connect Mode
- **URL**: `/set-wifi-connect`
- **Method**: POST
- **Description**: Toggle WiFi Connect mode on/off
- **Request Body**:
  ```json
  {
    "value": "true"
  }
  ```
- **Response**:
  ```json
  {
    "value": true
  }
  ```
- **Features**:
  - Creates WiFi Connect hotspot when enabled
  - Manages dnsmasq for DHCP services
  - Cleans up connections when disabled

### 3. Connect to Network
- **URL**: `/connect`
- **Method**: POST
- **Description**: Connect to a WiFi network
- **Request Body**:
  ```json
  {
    "ssid": "NetworkName",
    "passphrase": "password123"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Connected to NetworkName"
  }
  ```
- **Features**:
  - Automatically stops active hotspots before connecting
  - Supports both saved and new networks
  - Handles open networks (no passphrase required)
  - Restarts hotspot if connection fails

### 4. Forget Network (Alternative Endpoint)
- **URL**: `/forget-network`
- **Method**: POST
- **Description**: Alternative endpoint to remove a specific saved network
- **Request Body**:
  ```json
  {
    "ssid": "NetworkName"
  }
  ```
  OR
  ```json
  {
    "network_name": "NetworkName"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Successfully deleted 1 network(s) with SSID 'NetworkName'"
  }
  ```

### 5. Forget All Networks
- **URL**: `/forget-all`
- **Method**: POST
- **Description**: Remove all saved networks
- **Request Body**:
  ```json
  {}
  ```
- **Response**:
  ```json
  {
    "success": true,
    "message": "Successfully forgot 3 networks"
  }
  ```
- **Features**:
  - Automatically starts WiFi Connect mode after forgetting all networks
  - Reports count of successfully forgotten networks

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "error": "error_code",
  "message": "Human readable error message"
}
```

Common HTTP status codes:
- **200**: Success
- **500**: Internal server error
- **503**: Service unavailable (e.g., NetworkManager not available)

## Special Features

### Touchscreen Support
The root endpoint (`/`) supports dynamic script injection for touchscreen devices:
- Set environment variable `ENABLE_SURFACE_SUPPORT=1` to enable
- Automatically injects kioskboard and keyboard scripts
- Replaces HTML comment placeholders with actual script tags

### Network Caching
- Network scan results are cached for performance
- Cache is automatically cleared when hotspots are started/stopped
- Force refresh available via query parameters

### Hotspot Management
- WiFi Connect and WiFi Direct modes are mutually exclusive
- Automatic cleanup of existing connections at startup
- dnsmasq integration for DHCP services
- Graceful handling of connection failures

### Retry Logic
- Network scanning includes retry logic for reliability
- Automatic hotspot restart on connection failures
- Configurable retry counts and delays

## Configuration

The API behavior can be configured through the `config.py` file and environment variables:
- Server host/port settings
- WiFi interface detection
- DHCP and gateway configuration
- Logging levels
- CORS settings
- Scan timeouts and retry counts
