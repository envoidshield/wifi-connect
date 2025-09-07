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

class SavedNetwork(BaseModel):
    ssid: str
    security: str

class WiFiDirectResponse(BaseModel):
    value: bool

class WiFiConnectRequest(BaseModel):
    value: str

class WiFiConnectResponse(BaseModel):
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
        result = run_command(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
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

async def manage_wifi_connection(connection_type: str, enable: bool) -> dict:
    """
    General function to manage WiFi connections (direct/connect mode)
    
    Args:
        connection_type: "direct" or "connect"
        enable: True to enable, False to disable
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # Get appropriate config based on connection type
        if connection_type == "direct":
            wifi_config = config.get_direct_config()
            mode_name = "WiFi Direct"
        elif connection_type == "connect":
            wifi_config = config.get_connect_config()
            mode_name = "WiFi Connect"
        else:
            return {
                "success": False,
                "message": f"Invalid connection type: {connection_type}"
            }
        
        hotspot_name = wifi_config["hotspot_name"]
        connection_name = wifi_config["connection_name"]
        wifi_interface = get_wifi_interface()
        
        if not wifi_interface:
            return {
                "success": False,
                "message": "No WiFi interface found"
            }
        
        if enable:
            # Enable the connection (create hotspot)
            logger.info(f"Enabling {mode_name} mode")
            
            # Check if hotspot connection already exists
            check_result = run_command(["nmcli", "connection", "show", connection_name])
            
            if not check_result["success"]:
                # Connection doesn't exist, create it
                logger.info(f"Creating new {mode_name} connection: {connection_name}")
                
                create_cmd = [
                    "nmcli", 
                    "connection", "add", 
                    "type", "wifi",
                    "mode", "ap",
                    "ifname", wifi_interface,
                    "con-name", connection_name,
                    "ssid", hotspot_name,
                    "802-11-wireless.mode", "ap",
                    "802-11-wireless.band", "bg",
                    "802-11-wireless.channel", "6",
                    "ipv4.method", "shared",
                    "ipv4.addresses", "192.168.42.1/24",
                    "ipv6.method", "ignore",
                ]
                
                result = run_command(create_cmd)
                if not result["success"]:
                    return {
                        "success": False,
                        "message": f"Failed to create {mode_name} hotspot: {result.get('error', 'Unknown error')}"
                    }
            
            # Enable autoconnect and start the hotspot connection
            autoconnect_result = run_command([
                "nmcli", "connection", "modify", connection_name, 
                "connection.autoconnect", "yes"
            ])
            
            start_result = run_command(["nmcli", "connection", "up", connection_name])
            if not start_result["success"]:
                return {
                    "success": False,
                    "message": f"Failed to start {mode_name} hotspot: {start_result.get('error', 'Unknown error')}"
                }
            
            logger.info(f"{mode_name} mode enabled successfully")
            return {
                "success": True,
                "message": f"{mode_name} mode enabled successfully"
            }
            
        else:
            # Disable the connection
            logger.info(f"Disabling {mode_name} mode")
            
            # Disable autoconnect
            run_command([
                "nmcli", "connection", "modify", connection_name, 
                "connection.autoconnect", "no"
            ])
            
            # Stop the connection
            down_result = run_command(["nmcli", "connection", "down", connection_name])
            if not down_result["success"]:
                return {
                    "success": False,
                    "message": f"Failed to stop {mode_name} hotspot: {down_result.get('error', 'Unknown error')}"
                }
            
            logger.info(f"{mode_name} mode disabled successfully")
            return {
                "success": True,
                "message": f"{mode_name} mode disabled successfully"
            }
            
    except Exception as e:
        logger.error(f"Error managing {connection_type} connection: {e}")
        return {
            "success": False,
            "message": f"Failed to manage {connection_type} connection: {str(e)}"
        }


@app.post("/set-wifi-direct")
async def set_wifi_direct(request: WiFiDirectRequest):
    """Toggle WiFi Direct mode"""
    try:
        value = request.value.lower() == "true"
        result = await manage_wifi_connection("direct", value)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return WiFiDirectResponse(value=value)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting WiFi Direct: {e}")
        raise HTTPException(status_code=500, detail="Failed to set WiFi Direct mode")


@app.post("/set-wifi-connect")
async def set_wifi_connect(request: WiFiConnectRequest):
    """Toggle WiFi Connect mode"""
    try:
        value = request.value.lower() == "true"
        result = await manage_wifi_connection("connect", value)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return WiFiConnectResponse(value=value)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting WiFi Connect: {e}")
        raise HTTPException(status_code=500, detail="Failed to set WiFi Connect mode")


# Alternative approach - if you want separate functions for each mode
async def enable_wifi_direct() -> dict:
    """Enable WiFi Direct mode"""
    return await manage_wifi_connection("direct", True)


async def disable_wifi_direct() -> dict:
    """Disable WiFi Direct mode"""
    return await manage_wifi_connection("direct", False)


async def enable_wifi_connect() -> dict:
    """Enable WiFi Connect mode"""
    return await manage_wifi_connection("connect", True)


async def disable_wifi_connect() -> dict:
    """Disable WiFi Connect mode"""
    return await manage_wifi_connection("connect", False)


# Utility function to get current connection status
async def get_connection_status(connection_type: str) -> dict:
    """
    Get the current status of a WiFi connection
    
    Args:
        connection_type: "direct" or "connect"
    
    Returns:
        dict: {"active": bool, "connection_name": str, "message": str}
    """
    try:
        if connection_type == "direct":
            wifi_config = config.get_direct_config()
        elif connection_type == "connect":
            wifi_config = config.get_connect_config()
        else:
            return {"active": False, "connection_name": "", "message": "Invalid connection type"}
        
        connection_name = wifi_config["connection_name"]
        
        # Check if connection is active
        result = run_command([
            "nmcli", "-t", "-f", "NAME,STATE", "connection", "show", "--active"
        ])
        
        if result["success"]:
            active_connections = result["output"].split('\n')
            for conn in active_connections:
                if conn.startswith(f"{connection_name}:"):
                    return {
                        "active": True, 
                        "connection_name": connection_name,
                        "message": f"{connection_type} mode is active"
                    }
        
        return {
            "active": False, 
            "connection_name": connection_name,
            "message": f"{connection_type} mode is inactive"
        }
        
    except Exception as e:
        logger.error(f"Error getting {connection_type} status: {e}")
        return {
            "active": False, 
            "connection_name": "",
            "message": f"Error checking {connection_type} status"
        }

app.get("/list-networks")
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
    """Get currently connected Wi-Fi network info (ssid/interface/security)."""
    try:
        # 1) Find the active Wi-Fi connection + interface
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE,DEVICE",
            "connection", "show", "--active"
        ])
        if not result["success"] or not result["output"]:
            return ConnectedResponse(connected=None)

        wifi_interface = None
        connection_name = None

        for line in result["output"].splitlines():
            line = line.strip()
            if not line or line.startswith("Warning:"):
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                name, conn_type, device = parts[0], parts[1], parts[2]
                if conn_type in ("wifi", "802-11-wireless"):
                    wifi_interface = device
                    connection_name = name
                    break

        if not wifi_interface or not connection_name:
            return ConnectedResponse(connected=None)

        # 2) Read details from the profile itself (valid sections only)
        detail_result = run_command([
            "nmcli", "-t",
            "-f", "GENERAL,802-11-wireless,802-11-wireless-security",
            "connection", "show", connection_name
        ])
        if not detail_result["success"] or not detail_result["output"]:
            return ConnectedResponse(connected=None)

        ssid = ""
        interface = ""
        security = "open"

        for line in detail_result["output"].splitlines():
            line = line.strip()
            if not line or line.startswith("Warning:") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "802-11-wireless.ssid":
                ssid = value
            elif key == "general.devices" and value:
                interface = value  # prefer DEVICES
            elif key == "general.ip-iface" and value and not interface:
                interface = value  # fallback if DEVICES empty
            elif key == "802-11-wireless-security.key-mgmt":
                security = parse_network_security(value)

        if not ssid or not interface:
            return ConnectedResponse(connected=None)

        connected_network = ConnectedNetwork(
            ssid=ssid,
            interface=interface,
            security=parse_network_security(security)
        )
        return ConnectedResponse(connected=connected_network)

    except Exception as e:
        logger.error(f"Error getting connected network: {e}")
        return ConnectedResponse(connected=None)

@app.get("/list-saved")
async def list_saved():
    """Get list of saved networks"""
    try:
        # First, get all wireless connections
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE", 
            "connection", "show"
        ])
        
        if not result["success"]:
            return SavedNetworksResponse(saved_networks=[])
        
        saved_networks = []
        for line in result["output"].split('\n'):
            if line and line.strip():
                parts = line.split(':')
                if len(parts) >= 2:
                    name = parts[0]
                    conn_type = parts[1]
                    
                    if conn_type == "802-11-wireless":
                        # Get security info for this specific connection
                        security_result = run_command([
                            "nmcli", "-t", "-f", "802-11-wireless-security.key-mgmt",
                            "connection", "show", name
                        ])
                        
                        security = ""
                        if security_result["success"] and security_result["output"].strip():
                            # Extract the security value after the colon
                            security_line = security_result["output"].strip()
                            if ':' in security_line:
                                security = security_line.split(':', 1)[1]
                        
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

async def forget_network(network_name: str) -> dict:
    """Remove a specific saved network"""
    try:
        # First check if the network exists
        check_result = run_command([
            "nmcli", "-t", "-f", "NAME", "connection", "show", network_name
        ])
        
        if not check_result["success"]:
            return {
                "success": False, 
                "message": f"Network '{network_name}' not found"
            }
        
        # Delete the network connection
        delete_result = run_command([
            "nmcli", "connection", "delete", network_name
        ])
        
        if delete_result["success"]:
            logger.info(f"Successfully forgot network: {network_name}")
            return {
                "success": True, 
                "message": f"Successfully forgot network '{network_name}'"
            }
        else:
            logger.error(f"Failed to delete network {network_name}: {delete_result['error']}")
            return {
                "success": False, 
                "message": f"Failed to forget network '{network_name}': {delete_result['error']}"
            }
            
    except Exception as e:
        logger.error(f"Error forgetting network {network_name}: {e}")
        return {
            "success": False, 
            "message": f"Error forgetting network '{network_name}': {str(e)}"
        }



@app.post("/forget")
async def forget_network_endpoint(request: ForgetNetworkRequest):
    """Remove a specific saved network"""
    result = await forget_network(request.network_name)
    return SuccessResponse(
        success=result["success"],
        message=result["message"]
    )


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
        failed_networks = []
        
        for line in result["output"].split('\n'):
            if line.strip():  # Only process non-empty lines
                parts = line.split(':')
                if len(parts) >= 2:
                    name = parts[0]
                    conn_type = parts[1]
                    
                    # Only process WiFi connections
                    if conn_type == "802-11-wireless":
                        forget_result = await forget_network(name)
                        if forget_result["success"]:
                            deleted_count += 1
                        else:
                            failed_networks.append(name)
        
        # Prepare response message
        if failed_networks:
            message = f"Forgot {deleted_count} networks. Failed to forget: {', '.join(failed_networks)}"
        else:
            message = f"Successfully forgot {deleted_count} networks"
        
        return SuccessResponse(
            success=len(failed_networks) == 0,  # Success only if no failures
            message=message
        )
        
    except Exception as e:
        logger.error(f"Error forgetting all networks: {e}")
        return SuccessResponse(success=False, message="Failed to forget all networks")

if __name__ == "__main__":
    # Initialize WiFi interface at startup
    initialize_wifi_interface()
    
    # Run the server
    uvicorn.run(
        app, 
        host=config.get_server_config()["host"],  # Allow external connections
        port=config.get_server_config()["port"],       # Default port
        log_level="info"
    )

