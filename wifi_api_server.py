#!/usr/bin/env python3
"""
Standalone WiFi API Server for WiFi Connect Frontend
Uses nmcli and iw commands to manage WiFi connections
"""

import json
import logging
import subprocess
import time
import os
import re
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from config import get_config

# Get configuration
config = get_config()

# Configure logging
log_level = getattr(logging, config.get("server.log_level", "INFO").upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global cached WiFi interface - initialized at startup for efficiency
_cached_wifi_interface: Optional[str] = None

# Create FastAPI app
app = FastAPI(
    title="WiFi Connect API",
    description="WiFi management API using nmcli and iw",
    version="1.0.0"
)

# Add CORS middleware
cors_config = config.get_cors_config()
if cors_config["enabled"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config["origins"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount static files
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

# Pydantic models
class WiFiDirectRequest(BaseModel):
    value: str

class ConnectRequest(BaseModel):
    ssid: str
    passphrase: Optional[str] = None

class ForgetNetworkRequest(BaseModel):
    ssid: str

class ForgetAllRequest(BaseModel):
    pass

class NetworkInfo(BaseModel):
    ssid: str
    security: str
    signal_strength: Optional[int] = None
    frequency: Optional[str] = None

class ConnectedNetwork(BaseModel):
    ssid: str
    interface: str
    security: str
    signal_strength: int
    ip_address: Optional[str] = None

class SavedNetwork(BaseModel):
    ssid: str
    security: str

class WiFiDirectResponse(BaseModel):
    value: bool

class NetworksResponse(BaseModel):
    networks: List[NetworkInfo]

class ConnectedResponse(BaseModel):
    connected: Optional[ConnectedNetwork]

class SavedNetworksResponse(BaseModel):
    saved_networks: List[SavedNetwork]

class SuccessResponse(BaseModel):
    success: bool
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    message: str

# Utility functions
def run_command(command: List[str], timeout: int = None) -> Dict[str, Any]:
    """Run a command and return the result"""
    if timeout is None:
        timeout = config.get("wifi.scan_timeout", 30)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Command failed: {' '.join(command)}")
            logger.error(f"Error: {result.stderr}")
            return {
                "success": False,
                "error": result.stderr.strip(),
                "output": result.stdout.strip()
            }
        
        return {
            "success": True,
            "output": result.stdout.strip(),
            "error": result.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {' '.join(command)}")
        return {
            "success": False,
            "error": "Command timed out",
            "output": ""
        }
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return {
            "success": False,
            "error": str(e),
            "output": ""
        }

def _detect_wifi_interface() -> Optional[str]:
    """Detect the primary WiFi interface name"""
    try:
        # Get network interfaces
        result = run_command(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "show"])
        if not result["success"]:
            return None
        
        # Parse interfaces to find WiFi
        for line in result["output"].split('\n'):
            if line and '\n' not in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    device = parts[0]
                    device_type = parts[1]
                    if device_type == 'wifi':
                        return device
        
        return None
    except Exception as e:
        logger.error(f"Error detecting WiFi interface: {e}")
        return None

def initialize_wifi_interface():
    """Initialize the cached WiFi interface at startup"""
    global _cached_wifi_interface
    logger.info("Detecting WiFi interface...")
    _cached_wifi_interface = _detect_wifi_interface()
    if _cached_wifi_interface:
        logger.info(f"WiFi interface detected: {_cached_wifi_interface}")
    else:
        logger.warning("No WiFi interface detected")

def get_wifi_interface() -> Optional[str]:
    """Get the cached WiFi interface name with fallback to re-detection"""
    global _cached_wifi_interface
    
    # Return cached interface if available
    if _cached_wifi_interface:
        return _cached_wifi_interface
    
    # Fallback: re-detect interface if cache is empty
    logger.warning("WiFi interface cache is empty, re-detecting...")
    _cached_wifi_interface = _detect_wifi_interface()
    return _cached_wifi_interface

def parse_network_security(security_info: str) -> str:
    """Parse security information from nmcli output"""
    if not security_info:
        return "open"
    
    security_info = security_info.lower()
    
    if "wpa3" in security_info:
        return "wpa3"
    elif "wpa2" in security_info:
        return "wpa2"
    elif "wpa" in security_info:
        return "wpa"
    elif "wep" in security_info:
        return "wep"
    else:
        return "open"

def parse_signal_strength(signal_str: str) -> int:
    """Parse signal strength from dBm to percentage"""
    try:
        if not signal_str or signal_str == "N/A":
            return 0
        
        # Remove dBm suffix and convert to int
        signal_dbm = int(signal_str.replace(" dBm", ""))
        
        # Convert dBm to percentage (rough approximation)
        # -100 dBm = 0%, -50 dBm = 100%
        if signal_dbm <= -100:
            return 0
        elif signal_dbm >= -50:
            return 100
        else:
            return int(((signal_dbm + 100) / 50) * 100)
    except (ValueError, AttributeError):
        return 0

# API Endpoints

@app.get("/")
async def serve_index():
    """Serve the main index.html file"""
    return FileResponse("index.html")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if nmcli is available
        result = run_command(["nmcli", "--version"])
        if not result["success"]:
            raise HTTPException(status_code=503, detail="NetworkManager not available")
        
        return {"status": "healthy", "message": "WiFi API is running"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

@app.get("/get-wifi-direct")
async def get_wifi_direct() -> WiFiDirectResponse:
    """Get WiFi Direct status"""
    try:
        # Check if WiFi Direct is enabled by looking for hotspot mode
        result = run_command(["nmcli", "radio", "wifi"])
        if not result["success"]:
            raise HTTPException(status_code=500, detail="Failed to check WiFi status")
        
        # Check if there's an active hotspot connection
        hotspot_result = run_command(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
        if hotspot_result["success"]:
            for line in hotspot_result["output"].split('\n'):
                if line and 'hotspot' in line.lower():
                    return WiFiDirectResponse(value=True)
        
        return WiFiDirectResponse(value=False)
    except Exception as e:
        logger.error(f"Error getting WiFi Direct status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get WiFi Direct status")

@app.post("/set-wifi-direct")
async def set_wifi_direct(request: WiFiDirectRequest):
    """Toggle WiFi Direct mode"""
    try:
        value = request.value.lower() == "true"
        wifi_config = config.get_wifi_config()
        hotspot_name = wifi_config["hotspot_name_prefix"]
        connection_name = config.get_connection_name()
        
        if value:
            # Enable WiFi Direct (create hotspot)
            wifi_interface = get_wifi_interface()
            if not wifi_interface:
                raise HTTPException(status_code=500, detail="No WiFi interface found")
            # Check if hotspot connection already exists
            check_result = run_command(["nmcli", "connection", "show", hotspot_name])
            
            if not check_result["success"]:
                # Connection doesn't exist, create it
                result = run_command([
                    "nmcli", 
                    "connection", "add", 
                    "type", "wifi",
                    "mode", "ap",
                    "ifname", wifi_interface,
                    "con-name", connection_name,
                    "ssid", hotspot_name,
                    "802-11-wireless-security.key-mgmt", "wpa-psk",
                    "802-11-wireless-security.psk", wifi_config["hotspot_password"],
                    "802-11-wireless.mode", "ap",
                    "802-11-wireless.band", "bg",
                    "802-11-wireless.channel", "6",
                    "ipv4.method", "shared",
                    "ipv4.addresses", "192.168.42.1/24",
                    "ipv6.method", "ignore",
                ])
                
                if not result["success"]:
                    raise HTTPException(status_code=500, detail="Failed to create WiFi Direct hotspot")
            
            # Start/activate the hotspot connection and enable autoconnect
            # Enable autoconnect when turning on
            run_command(["nmcli", "connection", "modify", connection_name, "connection.autoconnect", "yes"])
            start_result = run_command(["nmcli", "connection", "up", connection_name])
            if not start_result["success"]:
                raise HTTPException(status_code=500, detail="Failed to start WiFi Direct hotspot")
        else:
            # Disable WiFi Direct (stop hotspot)
            hotspot_name = f"{wifi_config['hotspot_name_prefix']}-hotspot"
            
            run_command(["nmcli", "connection", "modify", hotspot_name, "connection.autoconnect", "no"])
            down_result = run_command(["nmcli", "connection", "down", hotspot_name])
            
        return WiFiDirectResponse(value=value)
    except Exception as e:
        logger.error(f"Error setting WiFi Direct: {e}")
        raise HTTPException(status_code=500, detail="Failed to set WiFi Direct mode"))

async def list_networks(use_cache: bool = True):
    """List available WiFi networks"""
    try:
        # Scan for networks if not using cache
        if not use_cache:
            scan_result = run_command(["nmcli", "device", "wifi", "rescan"])
            if not scan_result["success"]:
                return ErrorResponse(
                    error="scan_failed",
                    message="Failed to scan networks"
                )
            # Wait a bit for scan to complete
            time.sleep(config.get("wifi.rescan_delay", 2))
        
        # Get available networks
        result = run_command([
            "nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL,FREQ", 
            "device", "wifi", "list"
        ])
        
        if not result["success"]:
            return ErrorResponse(
                error="scan_failed",
                message="Failed to get network list"
            )
        
        networks = []
        for line in result["output"].split('\n'):
            if line and '\n' not in line:
                parts = line.split(':')
                if len(parts) >= 4:
                    ssid = parts[0]
                    security = parse_network_security(parts[1])
                    signal = parse_signal_strength(parts[2])
                    freq = parts[3] if len(parts) > 3 else None
                    
                    # Skip empty SSIDs and special networks
                    if ssid and not ssid.startswith('*') and ssid != "--":
                        networks.append(NetworkInfo(
                            ssid=ssid,
                            security=security,
                            signal_strength=signal,
                            frequency=freq
                        ))
        
        return NetworksResponse(networks=networks)
    except Exception as e:
        logger.error(f"Error listing networks: {e}")
        return ErrorResponse(
            error="scan_failed",
            message="Failed to scan networks"
        )

@app.get("/list-connected")
async def list_connected():
    """Get currently connected network information"""
    try:
        # Get active connections
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE,DEVICE", 
            "connection", "show", "--active"
        ])
        
        if not result["success"]:
            return ConnectedResponse(connected=None)
        
        wifi_interface = None
        connection_name = None
        
        for line in result["output"].split('\n'):
            if line and '\n' not in line:
                parts = line.split(':')
                if len(parts) >= 3:
                    name = parts[0]
                    conn_type = parts[1]
                    device = parts[2]
                    
                    if conn_type == "wifi":
                        wifi_interface = device
                        connection_name = name
                        break
        
        if not wifi_interface or not connection_name:
            return ConnectedResponse(connected=None)
        
        # Get detailed connection info
        detail_result = run_command([
            "nmcli", "-t", "-f", "GENERAL.CONNECTION,GENERAL.DEVICES,802-11-WIRELESS.SSID,802-11-WIRELESS.SECURITY,802-11-WIRELESS.SIGNAL,IP4.ADDRESS",
            "connection", "show", connection_name
        ])
        
        if not detail_result["success"]:
            return ConnectedResponse(connected=None)
        
        # Parse connection details
        details = {}
        for line in detail_result["output"].split('\n'):
            if line and ':' in line:
                key, value = line.split(':', 1)
                details[key] = value
        
        # Get signal strength using iw
        signal_strength = 0
        if wifi_interface:
            iw_result = run_command(["iw", "dev", wifi_interface, "link"])
            if iw_result["success"]:
                signal_match = re.search(r'signal: (-\d+) dBm', iw_result["output"])
                if signal_match:
                    signal_strength = parse_signal_strength(signal_match.group(1) + " dBm")
        
        # Extract IP address
        ip_address = None
        if "IP4.ADDRESS" in details:
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', details["IP4.ADDRESS"])
            if ip_match:
                ip_address = ip_match.group(1)
        
        connected_network = ConnectedNetwork(
            ssid=details.get("802-11-WIRELESS.SSID", ""),
            interface=wifi_interface,
            security=parse_network_security(details.get("802-11-WIRELESS.SECURITY", "")),
            signal_strength=signal_strength,
            ip_address=ip_address
        )
        
        return ConnectedResponse(connected=connected_network)
    except Exception as e:
        logger.error(f"Error getting connected network: {e}")
        return ConnectedResponse(connected=None)

@app.get("/list-saved")
async def list_saved():
    """Get list of saved networks"""
    try:
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE,802-11-WIRELESS.SECURITY", 
            "connection", "show"
        ])
        
        if not result["success"]:
            return SavedNetworksResponse(saved_networks=[])
        
        saved_networks = []
        for line in result["output"].split('\n'):
            if line and '\n' not in line:
                parts = line.split(':')
                if len(parts) >= 3:
                    name = parts[0]
                    conn_type = parts[1]
                    security = parts[2] if len(parts) > 2 else ""
                    
                    if conn_type == "802-11-wireless":
                        saved_networks.append(SavedNetwork(
                            ssid=name,
                            security=parse_network_security(security)
                        ))
        
        return SavedNetworksResponse(saved_networks=saved_networks)
    except Exception as e:
        logger.error(f"Error listing saved networks: {e}")
        return SavedNetworksResponse(saved_networks=[])

@app.post("/connect")
async def connect_to_network(request: ConnectRequest):
    """Connect to a WiFi network"""
    try:
        ssid = request.ssid
        passphrase = request.passphrase
        
        # Check if network is already saved
        check_result = run_command(["nmcli", "connection", "show", ssid])
        
        if check_result["success"]:
            # Network is saved, just connect
            result = run_command(["nmcli", "connection", "up", ssid])
        else:
            # New network, create connection
            if passphrase:
                result = run_command([
                    "nmcli", "device", "wifi", "connect", ssid, 
                    "password", passphrase
                ])
            else:
                result = run_command([
                    "nmcli", "device", "wifi", "connect", ssid
                ])
        
        if not result["success"]:
            return SuccessResponse(success=False, message="Failed to connect to network")
        
        return SuccessResponse(success=True, message=f"Connected to {ssid}")
    except Exception as e:
        logger.error(f"Error connecting to network: {e}")
        return SuccessResponse(success=False, message="Connection failed")

@app.post("/forget-network")
async def forget_network(request: ForgetNetworkRequest):
    """Remove a saved network"""
    try:
        ssid = request.ssid
        
        # Delete the connection
        result = run_command(["nmcli", "connection", "delete", ssid])
        
        if not result["success"]:
            return SuccessResponse(success=False, message="Failed to forget network")
        
        return SuccessResponse(success=True, message=f"Forgot network {ssid}")
    except Exception as e:
        logger.error(f"Error forgetting network: {e}")
        return SuccessResponse(success=False, message="Failed to forget network")

@app.post("/forget-all")
async def forget_all_networks(request: ForgetAllRequest):
    """Remove all saved networks"""
    try:
        # Get all saved networks
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE", 
            "connection", "show"
        ])
        
        if not result["success"]:
            return SuccessResponse(success=False, message="Failed to get saved networks")
        
        deleted_count = 0
        for line in result["output"].split('\n'):
            if line and '\n' not in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    name = parts[0]
                    conn_type = parts[1]
                    
                    if conn_type == "802-11-wireless":
                        delete_result = run_command(["nmcli", "connection", "delete", name])
                        if delete_result["success"]:
                            deleted_count += 1
        
        return SuccessResponse(
            success=True, 
            message=f"Forgot {deleted_count} networks"
        )
    except Exception as e:
        logger.error(f"Error forgetting all networks: {e}")
        return SuccessResponse(success=False, message="Failed to forget all networks")

if __name__ == "__main__":
    logger.info("Starting WiFi API Server...")
    
    # Initialize WiFi interface cache at startup for efficiency
    initialize_wifi_interface()
    
    server_config = config.get_server_config()
    logger.info(f"Server will run on {server_config['host']}:{server_config['port']}")
    logger.info(f"Access the WiFi Connect interface at: http://{server_config['host']}:{server_config['port']}")
    
    uvicorn.run(
        app,
        host=server_config["host"],
        port=server_config["port"],
        log_level=server_config["log_level"]
    )
