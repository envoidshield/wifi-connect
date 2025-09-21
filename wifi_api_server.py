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

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize WiFi interface and check connectivity at startup"""
    # Initialize WiFi interface
    initialize_wifi_interface()
    
    # Perform startup WiFi check
    await startup_wifi_check()

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down WiFi API server...")
    
    # Stop dnsmasq if running
    stop_dnsmasq()
    
    # Save current state before shutdown
    try:
        # Check current connection status
        connected_response = await list_connected()
        if hasattr(connected_response, 'connected') and connected_response.connected:
            save_wifi_state("connected", connected_response.connected)
        else:
            # Check if any hotspot is active
            direct_status = await get_connection_status("direct")
            connect_status = await get_connection_status("connect")
            
            if direct_status["active"]:
                save_wifi_state("direct")
            elif connect_status["active"]:
                save_wifi_state("connect")
            else:
                save_wifi_state("disconnected")
    except Exception as e:
        logger.warning(f"Could not save final state on shutdown: {e}")
    
    logger.info("Shutdown complete")

# Pydantic models
class WiFiDirectRequest(BaseModel):
    value: str

class ConnectRequest(BaseModel):
    ssid: str
    passphrase: Optional[str] = None

class ForgetNetworkRequest(BaseModel):
    ssid: Optional[str] = None
    bssid: Optional[str] = None

class ForgetAllRequest(BaseModel):
    pass

class NetworkInfo(BaseModel):
    ssid: str
    security: str
    signal_strength: Optional[int] = None
    frequency_band: Optional[str] = None
    active: Optional[bool] = None
    bssid: Optional[str] = None

class ConnectedNetwork(BaseModel):
    ssid: str
    interface: str
    security: str
    connection_name: str

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
    saved_networks: List[ConnectedNetwork]

class SuccessResponse(BaseModel):
    success: bool
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    message: str

class ScanStatusResponse(BaseModel):
    hotspot_active: bool
    hotspot_type: Optional[str] = None
    can_scan: bool
    warning_message: Optional[str] = None

# Global cached WiFi interface - initialized at startup for efficiency
_cached_wifi_interface: Optional[str] = None

# Global dnsmasq process - managed when WiFi Connect is active
_dnsmasq_process: Optional[subprocess.Popen] = None

# Global cached networks - stores network list with timestamp
_cached_networks: Optional[List[NetworkInfo]] = None
_cached_networks_timestamp: Optional[float] = None

# State persistence file path - can be configured
def get_state_file_path() -> str:
    """Get the state file path from config or use default"""
    return config.get("wifi.state_file", "wifi_state.json")


# Utility functions
def run_command(command: List[str], timeout: int = None, input: str = None) -> Dict[str, Any]:
    """Run a command and return the result"""
    if timeout is None:
        timeout = config.get("wifi.scan_timeout", 30)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            input=input
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

async def cleanup_startup_connections():
    """Clean up existing connect and direct connections at startup"""
    try:
        logger.info("Starting cleanup of existing connect and direct connections...")
        
        # Get connection names from config
        connect_config = config.get_connect_config()
        direct_config = config.get_direct_config()
        
        connect_connection_name = connect_config.get("connection_name", "connectInterface")
        direct_connection_name = direct_config.get("connection_name", "directInterface")
        
        logger.info(f"Looking for connections: '{connect_connection_name}' and '{direct_connection_name}'")
        
        connections_to_cleanup = [connect_connection_name, direct_connection_name]
        cleaned_count = 0
        
        for connection_name in connections_to_cleanup:
            logger.debug(f"Checking connection: '{connection_name}'")
            
            # Check if connection exists
            check_result = run_command(["nmcli", "connection", "show", connection_name])
            
            if check_result["success"]:
                logger.info(f"Found existing connection '{connection_name}', removing it...")
                
                # Stop the connection if it's active
                logger.debug(f"Stopping connection '{connection_name}' if active...")
                down_result = run_command(["nmcli", "connection", "down", connection_name])
                if down_result["success"]:
                    logger.debug(f"Successfully stopped connection '{connection_name}'")
                else:
                    logger.debug(f"Connection '{connection_name}' was not active or already stopped")
                
                # Delete the connection
                logger.debug(f"Deleting connection '{connection_name}'...")
                delete_result = run_command(["nmcli", "connection", "delete", connection_name])
                
                if delete_result["success"]:
                    logger.info(f"Successfully removed connection '{connection_name}'")
                    cleaned_count += 1
                else:
                    logger.warning(f"Failed to remove connection '{connection_name}': {delete_result.get('error', 'Unknown error')}")
            else:
                logger.debug(f"Connection '{connection_name}' does not exist, skipping")
        
        # Also stop any running dnsmasq process
        logger.info("Stopping any running dnsmasq process...")
        dnsmasq_stopped = stop_dnsmasq()
        if dnsmasq_stopped:
            logger.info("dnsmasq process cleanup completed")
        else:
            logger.debug("No dnsmasq process was running")
        
        logger.info(f"Startup connection cleanup completed - removed {cleaned_count} connections")
        
    except Exception as e:
        logger.error(f"Error during startup connection cleanup: {e}")
        logger.error(f"Cleanup error details: {str(e)}", exc_info=True)

def initialize_wifi_interface():
    """Initialize the cached WiFi interface at startup"""
    global _cached_wifi_interface
    logger.info("Detecting WiFi interface...")
    _cached_wifi_interface = _detect_wifi_interface()
    if _cached_wifi_interface:
        logger.info(f"WiFi interface detected: {_cached_wifi_interface}")
    else:
        logger.warning("No WiFi interface detected")

async def startup_wifi_check():
    """Check WiFi connectivity at startup and restore previous state if available"""
    try:
        # Set startup flag to prevent cache clearing during startup
        startup_wifi_check._startup_in_progress = True
        await cleanup_startup_connections()
        
        # Check if startup check is enabled
        if not config.get("wifi.startup_check", True):
            logger.info("Startup WiFi check is disabled")
            return
            
        logger.info("Performing startup WiFi connectivity check...")
        
        # Check if WiFi interface is available
        wifi_interface = get_wifi_interface()
        if not wifi_interface:
            logger.warning("No WiFi interface available, skipping startup check")
            return
        
        # Try to restore previous state first
        saved_state = load_wifi_state()
        if saved_state:
            state = saved_state.get("state")
            connected_network_data = saved_state.get("connected_network")
            
            logger.info(f"Found saved state: {state}")
            
            if state == "connected" and connected_network_data:
                # Try to restore the connected network
                try:
                    logger.info(f"Attempting to restore connection to {connected_network_data['ssid']}")
                    result = run_command(["nmcli", "connection", "up", connected_network_data["connection_name"]])
                    
                    if result["success"]:
                        logger.info(f"Successfully restored connection to {connected_network_data['ssid']}")
                        # Save the restored state
                        connected_network = ConnectedNetwork(
                            ssid=connected_network_data["ssid"],
                            interface=connected_network_data["interface"],
                            security=connected_network_data["security"],
                            connection_name=connected_network_data["connection_name"]
                        )
                        save_wifi_state("connected", connected_network)
                        return
                    else:
                        logger.warning(f"Failed to restore connection to {connected_network_data['ssid']}: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    logger.warning(f"Error restoring connection: {e}")
            
            elif state == "direct":
                # Restore WiFi Direct mode
                logger.info("Restoring WiFi Direct mode")
                direct_result = await manage_wifi_connection("direct", True)
                if direct_result["success"]:
                    logger.info("WiFi Direct mode restored successfully")
                    save_wifi_state("direct")
                    return
                else:
                    logger.warning(f"Failed to restore WiFi Direct mode: {direct_result['message']}")
            
            elif state == "connect":
                # Restore WiFi Connect mode
                logger.info("Restoring WiFi Connect mode")
                connect_result = await manage_wifi_connection("connect", True)
                if connect_result["success"]:
                    logger.info("WiFi Connect mode restored successfully")
                    save_wifi_state("connect")
                    return
                else:
                    logger.warning(f"Failed to restore WiFi Connect mode: {connect_result['message']}")
        
        # If no saved state or restoration failed, check current connection status
        try:
            connected_response = await list_connected()
            if hasattr(connected_response, 'connected') and connected_response.connected:
                logger.info(f"WiFi network already connected to {connected_response.connected.ssid}")
                save_wifi_state("connected", connected_response.connected)
                return
            else:
                logger.info("No active WiFi connection found")
        except Exception as e:
            logger.warning(f"Could not check connected status: {e}")
            # Continue with startup check even if we can't determine connection status
        
        logger.info("No WiFi connection found, performing network scan...")
        
        # Use the list_networks endpoint to scan and cache networks
        try:
            networks_response = await list_networks(use_cache=False, force_scan=True)
            if hasattr(networks_response, 'networks'):
                networks = networks_response.networks
                if networks:
                    logger.info(f"Found {len(networks)} available networks, but none connected")
                    
                    # If 1 or fewer networks found, try rescanning up to 5 times
                    max_retries = 5
                    retry_count = 0
                    while len(networks) <= 1 and retry_count < max_retries:
                        retry_count += 1
                        logger.info(f"Only {len(networks)} network(s) found, performing rescan attempt {retry_count}/{max_retries}...")
                        time.sleep(2)  # Wait a bit before rescanning
                        networks_response = await list_networks(use_cache=False, force_scan=True)
                        if hasattr(networks_response, 'networks'):
                            networks = networks_response.networks
                            logger.info(f"After rescan attempt {retry_count}: Found {len(networks)} available networks")
                        else:
                            logger.warning(f"Failed to get networks on rescan attempt {retry_count}")
                            break
                    
                    if retry_count >= max_retries and len(networks) <= 1:
                        logger.warning(f"After {max_retries} rescan attempts, still only found {len(networks)} network(s)")
                else:
                    logger.info("No WiFi networks found in range")
            else:
                logger.warning("Failed to get network list from API")
        except Exception as e:
            logger.warning(f"Failed to scan networks via API: {e}")
        
        # Start WiFi Connect mode since no network is connected
        logger.info("Starting WiFi Connect mode for network configuration...")
        connect_result = await manage_wifi_connection("connect", True)
        
        if connect_result["success"]:
            logger.info("WiFi Connect mode started successfully")
            save_wifi_state("connect")
        else:
            logger.error(f"Failed to start WiFi Connect mode: {connect_result['message']}")
            
    except Exception as e:
        logger.error(f"Error during startup WiFi check: {e}")
    finally:
        # Clear startup flag
        if hasattr(startup_wifi_check, '_startup_in_progress'):
            delattr(startup_wifi_check, '_startup_in_progress')

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

def is_cache_valid() -> bool:
    """Check if the cached networks are still valid"""
    global _cached_networks, _cached_networks_timestamp
    
    if _cached_networks is None or _cached_networks_timestamp is None:
        return False
    
    return True

def get_cached_networks() -> Optional[List[NetworkInfo]]:
    """Get cached networks if they are still valid"""
    if is_cache_valid():
        logger.info(f"get_cached_networks: Returning {len(_cached_networks)} cached networks")
        return _cached_networks
    else:
        logger.info(f"get_cached_networks: No valid cache found (cache_valid={is_cache_valid()})")
    return None

def set_cached_networks(networks: List[NetworkInfo]) -> None:
    """Store networks in cache with current timestamp"""
    global _cached_networks, _cached_networks_timestamp
    
    _cached_networks = networks
    _cached_networks_timestamp = time.time()
    logger.info(f"set_cached_networks: Cached {len(networks)} networks at timestamp {_cached_networks_timestamp}")

def clear_network_cache() -> None:
    """Clear the network cache"""
    global _cached_networks, _cached_networks_timestamp
    return
    _cached_networks = None
    _cached_networks_timestamp = None
    logger.debug("Network cache cleared")

def save_wifi_state(state: str, connected_network: Optional[ConnectedNetwork] = None) -> None:
    """Save the current WiFi state to file"""
    try:
        state_file = get_state_file_path()
        state_data = {
            "state": state,  # "direct", "connect", "connected", or "disconnected"
            "timestamp": time.time(),
            "connected_network": None
        }
        
        if connected_network:
            state_data["connected_network"] = {
                "ssid": connected_network.ssid,
                "interface": connected_network.interface,
                "security": connected_network.security,
                "connection_name": connected_network.connection_name
            }
        
        # Create directory if it doesn't exist
        state_dir = os.path.dirname(state_file)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
        
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)
        
        logger.info(f"Saved WiFi state: {state} to {state_file}")
        
    except Exception as e:
        logger.error(f"Failed to save WiFi state: {e}")

def load_wifi_state() -> Optional[Dict[str, Any]]:
    """Load the WiFi state from file"""
    try:
        state_file = get_state_file_path()
        if not os.path.exists(state_file):
            logger.debug("No state file found")
            return None
        
        with open(state_file, 'r') as f:
            state_data = json.load(f)
        
        # Check if state is not too old (e.g., older than 24 hours)
        state_age = time.time() - state_data.get("timestamp", 0)
        max_age = config.get("wifi.state_max_age", 86400)  # 24 hours default
        
        if state_age > max_age:
            logger.info(f"State file is too old ({state_age:.0f}s), ignoring")
            # Clean up old state file
            try:
                os.remove(state_file)
                logger.info("Removed old state file")
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove old state file: {cleanup_error}")
            return None
        
        logger.info(f"Loaded WiFi state: {state_data.get('state', 'unknown')} from {state_file}")
        return state_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in state file: {e}")
        # Try to clean up corrupted state file
        try:
            state_file = get_state_file_path()
            if os.path.exists(state_file):
                os.remove(state_file)
                logger.info("Removed corrupted state file")
        except Exception as cleanup_error:
            logger.warning(f"Failed to remove corrupted state file: {cleanup_error}")
        return None
    except Exception as e:
        logger.error(f"Failed to load WiFi state: {e}")
        return None

def clear_wifi_state() -> None:
    """Clear the WiFi state file"""
    try:
        state_file = get_state_file_path()
        if os.path.exists(state_file):
            os.remove(state_file)
            logger.info("Cleared WiFi state file")
    except Exception as e:
        logger.error(f"Failed to clear WiFi state: {e}")

def create_dnsmasq_config() -> bool:
    """Create dnsmasq configuration file for WiFi Direct mode"""
    try:
        # Create the configuration content
        config_content = "dhcp-option=3\n"
        
        # Create the configuration file
        result = run_command([
            "sudo", "tee", "/etc/NetworkManager/dnsmasq-shared.d/no-router.conf"
        ], input=config_content)
        
        if result["success"]:
            logger.info("dnsmasq configuration file created successfully")
            return True
        else:
            logger.error(f"Failed to create dnsmasq configuration: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating dnsmasq configuration: {e}")
        return False

def remove_dnsmasq_config() -> bool:
    """Remove dnsmasq configuration file for WiFi Direct mode"""
    try:
        # Remove the configuration file
        result = run_command([
            "sudo", "rm", "-f", "/etc/NetworkManager/dnsmasq-shared.d/no-router.conf"
        ])
        
        if result["success"]:
            logger.info("dnsmasq configuration file removed successfully")
            return True
        else:
            logger.error(f"Failed to remove dnsmasq configuration: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error removing dnsmasq configuration: {e}")
        return False

def start_dnsmasq(wifi_interface: str, connection_type: str = "connect") -> bool:
    """Start dnsmasq for WiFi hotspot"""
    global _dnsmasq_process
    
    try:
        # Check if dnsmasq is already running
        if _dnsmasq_process and _dnsmasq_process.poll() is None:
            logger.info("dnsmasq is already running")
            return True
        
        # Get dnsmasq configuration
        gateway = config.get("wifi.gateway", "192.168.42.1")
        dhcp_range = config.get("wifi.dhcp_range", "192.168.42.2,192.168.42.20")
        log_file = config.get("wifi.log_file", "/var/log/dnsmasq.log")
        
        # Build base dnsmasq command
        dnsmasq_cmd = [
            "dnsmasq",
            f"--address=/#/{gateway}",
            f"--interface={wifi_interface}",
            "--keep-in-foreground",
            f"--dhcp-range={dhcp_range}",
            "--bind-interfaces",
            "--except-interface=lo",
            "--no-hosts",
            "--log-queries",
            "--log-dhcp",
            f"--log-facility={log_file}"
        ]
        
        # Add connection type specific options
        if connection_type == "connect":
            # WiFi Connect mode - normal DHCP and routing
            dnsmasq_cmd.extend([
                f"--dhcp-option=option:router,{gateway}",
                f"--dhcp-option=option:dns-server,{gateway}",
            ])
        elif connection_type == "direct":
            # WiFi Direct mode - isolated mode with special flags
            dnsmasq_cmd.extend([
                "--dhcp-option=3"
            ])
        
        logger.info(f"Starting dnsmasq with command: {' '.join(dnsmasq_cmd)}")
        
        # Start dnsmasq process
        _dnsmasq_process = subprocess.Popen(
            dnsmasq_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a moment to start
        time.sleep(1)
        
        # Check if it started successfully
        if _dnsmasq_process.poll() is None:
            logger.info("dnsmasq started successfully")
            return True
        else:
            stdout, stderr = _dnsmasq_process.communicate()
            logger.error(f"dnsmasq failed to start: {stderr}")
            _dnsmasq_process = None
            return False
            
    except Exception as e:
        logger.error(f"Error starting dnsmasq: {e}")
        _dnsmasq_process = None
        return False

def stop_dnsmasq() -> bool:
    """Stop dnsmasq process"""
    global _dnsmasq_process
    
    try:
        if _dnsmasq_process and _dnsmasq_process.poll() is None:
            logger.info("Stopping dnsmasq...")
            _dnsmasq_process.terminate()
            
            # Wait for graceful shutdown
            try:
                _dnsmasq_process.wait(timeout=5)
                logger.info("dnsmasq stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("dnsmasq did not stop gracefully, forcing kill")
                _dnsmasq_process.kill()
                _dnsmasq_process.wait()
                logger.info("dnsmasq force killed")
            
            _dnsmasq_process = None
            return True
        else:
            logger.info("dnsmasq is not running")
            return True
            
    except Exception as e:
        logger.error(f"Error stopping dnsmasq: {e}")
        _dnsmasq_process = None
        return False

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
    """Parse signal strength to percentage"""
    try:
        if not signal_str or signal_str == "N/A":
            return 0
        
        # Clean the signal string
        signal_clean = signal_str.strip().replace(" dBm", "")
        signal_value = int(signal_clean)
        
        # If the value is already in a reasonable percentage range (0-100), use it directly
        if 0 <= signal_value <= 100:
            return signal_value
        # If it's a negative value (dBm format), convert to percentage
        elif signal_value < 0:
            # Convert dBm to percentage (rough approximation)
            # -100 dBm = 0%, -50 dBm = 100%
            if signal_value <= -100:
                return 0
            elif signal_value >= -50:
                return 100
            else:
                return int(((signal_value + 100) / 50) * 100)
        else:
            # For positive values > 100, cap at 100
            return 100
            
    except (ValueError, AttributeError):
        return 0

def parse_frequency_band(channel_str: str) -> str:
    """Parse channel to frequency band"""
    try:
        if not channel_str or channel_str == "N/A":
            return "unknown"
        
        # Convert channel to int
        channel = int(channel_str)
        
        # Determine frequency band based on channel
        if 1 <= channel <= 14:
            return "2.4GHz"
        elif 36 <= channel <= 64 or 100 <= channel <= 165:
            return "5GHz"
        elif 1 <= channel <= 233:  # 6GHz channels (WiFi 6E)
            return "6GHz"
        else:
            return f"Channel {channel}"
    except (ValueError, AttributeError):
        return "unknown"

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
                    "nmcli", "connection", "add", "type", "wifi",
                    "ifname", wifi_interface,
                    "con-name", connection_name,
                    "ssid", hotspot_name
                ]
                
                result = run_command(create_cmd)
                if not result["success"]:
                    return {
                        "success": False,
                        "message": f"Failed to create {mode_name} hotspot: {result.get('error', 'Unknown error')}"
                    }
                
                # Configure the hotspot settings
                modify_cmd = [
                    "nmcli", "connection", "modify", connection_name,
                    "802-11-wireless.mode", "ap",
                    "802-11-wireless.band", "bg",
                    "ipv4.never-default", "yes",
                    "connection.autoconnect", "no",
                    "ipv4.method", "manual",
                    "ipv4.addresses", "192.168.42.1/24",
                ]

                if connection_type == "direct":
                    modify_cmd.extend([
                         "802-11-wireless.powersave", "0",
                    ])
                
                modify_result = run_command(modify_cmd)
                if not modify_result["success"]:
                    return {
                        "success": False,
                        "message": f"Failed to configure {mode_name} hotspot: {modify_result.get('error', 'Unknown error')}"
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
            logger.info(f"Stopping dnsmasq for {mode_name} mode...")
            stop_dnsmasq()
            time.sleep(1)
            logger.info(f"Starting dnsmasq for {mode_name} mode...")
            dnsmasq_started = start_dnsmasq(wifi_interface, connection_type)
            if not dnsmasq_started:
                logger.warning("Failed to start dnsmasq, but continuing with hotspot")
            
            # Clear network cache when starting hotspot (but not during startup)
            # During startup, we want to keep the cached networks for immediate frontend use
            if not hasattr(startup_wifi_check, '_startup_in_progress'):
                clear_network_cache()
            
            # Save the new state
            save_wifi_state(connection_type)
            
            logger.info(f"{mode_name} mode enabled successfully")
            return {
                "success": True,
                "message": f"{mode_name} mode enabled successfully"
            }
            
        else:
            # Disable the connection
            logger.info(f"Disabling {mode_name} mode")
            
            # Stop dnsmasq for both WiFi Connect and Direct modes
            logger.info(f"Stopping dnsmasq for {mode_name} mode...")
            stop_dnsmasq()
            
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
            
            # Clear network cache when stopping hotspot
            clear_network_cache()
            await list_networks(use_cache=False, force_scan=True)
            
            # Save the disconnected state
            save_wifi_state("disconnected")
            
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

@app.get("/list-networks")
async def list_networks(use_cache: bool = True, force_scan: bool = False):
    """List available WiFi networks"""
    try:
        # If use_cache is True and we have valid cached data, return it
        if use_cache and not force_scan:
            logger.debug(f"Cache requested: use_cache={use_cache}, force_scan={force_scan}")
            cached_networks = get_cached_networks()
            if cached_networks is not None:
                logger.info(f"Returning {len(cached_networks)} cached networks")
                return NetworksResponse(networks=cached_networks)
            else:
                logger.debug("No valid cached networks found, proceeding with scan")
        
        # Check if any hotspot is currently active
        direct_status = await get_connection_status("direct")
        connect_status = await get_connection_status("connect")
        hotspot_active = direct_status["active"] or connect_status["active"]
        
        # Determine which hotspot is active and get its details
        hotspot_type = ""
        hotspot_name = ""
        if direct_status["active"]:
            hotspot_type = "direct"
            hotspot_name = config.get_direct_config()["hotspot_name"]
        elif connect_status["active"]:
            hotspot_type = "connect"
            hotspot_name = config.get_connect_config()["hotspot_name"]
        
        # If hotspot is active and we need to scan, we need to temporarily disable it
        if hotspot_active and (not use_cache or force_scan):
            logger.info("Hotspot is active, temporarily disabling for network scan")
            
            # Temporarily disable the hotspot
            disable_result = await manage_wifi_connection(hotspot_type, False)
            if not disable_result["success"]:
                return ErrorResponse(
                    error="hotspot_disable_failed",
                    message=f"Failed to temporarily disable {hotspot_type} for scanning: {disable_result['message']}"
                )
            
            # Wait for the interface to be available
            time.sleep(config.get("wifi.hotspot_disable_delay", 3))
            
        try:
            # Retry logic for low output lines
            max_retries = config.get("wifi.scan_retries", 3)
            networks = []
            
            for retry_count in range(max_retries):
                scan_result = run_command(["nmcli", "device", "wifi", "rescan", "ifname", get_wifi_interface()])
                if not scan_result["success"]:
                    logger.warning(f"Scan failed: {scan_result.get('error', 'Unknown error')}")
                else:
                    # Wait a bit for scan to complete
                    time.sleep(config.get("wifi.rescan_delay", 2))
                
                # Get available networks
                result = run_command([
                    "nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,SECURITY,CHAN,SIGNAL", 
                    "device", "wifi", "list", "ifname", get_wifi_interface()
                ])
                
                if not result["success"]:
                    if retry_count == max_retries - 1:  # Last retry
                        return ErrorResponse(
                            error="scan_failed",
                            message="Failed to get network list"
                        )
                    continue
                
                # Check if we have enough output lines
                output_lines = result["output"].split('\n')
                if len(output_lines) <= 1 and retry_count < max_retries - 1:
                    logger.info(f"Only {len(output_lines)} line(s) in output, retrying scan ({retry_count + 1}/{max_retries})")
                    time.sleep(2)  # Wait before retry
                    continue
                
                networks = []
                seen_bssids = set()  # Track BSSIDs to avoid duplicates
                
                for line in output_lines:
                    if line and '\n' not in line:
                        logger.debug(f"Parsing line: '{line}'")
                        
                        # Handle escaped colons in BSSID by splitting more carefully
                        # The format is: ACTIVE:SSID:BSSID:SECURITY:CHAN:SIGNAL
                        # But BSSID contains escaped colons like "00\:B8\:C2\:01\:7B\:8C"
                        
                        # First split by unescaped colons only
                        parts = []
                        current_part = ""
                        i = 0
                        while i < len(line):
                            if line[i] == ':' and (i == 0 or line[i-1] != '\\'):
                                parts.append(current_part)
                                current_part = ""
                            else:
                                current_part += line[i]
                            i += 1
                        parts.append(current_part)  # Add the last part
                        
                        logger.debug(f"Split into {len(parts)} parts: {parts}")
                        
                        if len(parts) >= 6:
                            active = parts[0].strip() == "*"
                            ssid = parts[1]
                            bssid = parts[2].replace('\\:', ':')  # Convert escaped colons back to normal colons
                            security = parse_network_security(parts[3])
                            frequency_band = parse_frequency_band(parts[4]) if len(parts) > 4 else "unknown"
                            signal = parse_signal_strength(parts[5]) if len(parts) > 5 else 0
                            
                            logger.debug(f"Parsed: active={active}, ssid='{ssid}', bssid='{bssid}', security='{security}', freq='{frequency_band}', signal={signal}")
                            
                            # Skip empty SSIDs and special networks
                            if ssid and not ssid.startswith('*') and ssid != "--":
                                # Skip if we've already seen this BSSID
                                if bssid in seen_bssids:
                                    logger.debug(f"Skipping duplicate BSSID: {bssid}")
                                    continue
                                
                                seen_bssids.add(bssid)
                                networks.append(NetworkInfo(
                                    ssid=ssid,
                                    security=security,
                                    signal_strength=signal,
                                    frequency_band=frequency_band,
                                    active=active,
                                    bssid=bssid
                                ))
                
                # If we have more than 1 line in output, we're good
                if len(output_lines) > 1:
                    break
                else:
                    logger.warning(f"After {max_retries} attempts, only found {len(output_lines)} line(s) in output")
                    break
                        # Cache the networks
            set_cached_networks(networks)
            logger.info(f"list_networks (hotspot): Cached {len(networks)} networks")
            # Re-enable the hotspot
            if hotspot_active:
                logger.info(f"Re-enabling {hotspot_name} after scan")
                enable_result = await manage_wifi_connection(hotspot_type, True)
                if not enable_result["success"]:
                    logger.error(f"Failed to re-enable {hotspot_name}: {enable_result['message']}")
                    # Don't fail the request, just log the error
            return NetworksResponse(networks=networks)
               
        except Exception as scan_error:
            # Try to re-enable hotspot even if scan failed
            logger.error(f"Error during scan: {scan_error}")
            if hotspot_active and hotspot_type:
                try:
                    enable_result = await manage_wifi_connection(hotspot_type, True)
                    if not enable_result["success"]:
                        logger.error(f"Failed to re-enable {hotspot_name} after scan error: {enable_result['message']}")
                except Exception as enable_error:
                    logger.error(f"Error re-enabling hotspot: {enable_error}")
            
            return ErrorResponse(
                error="scan_failed",
                message=f"Failed to scan networks: {str(scan_error)}"
            )            
    except Exception as e:
        logger.error(f"Error listing networks: {e}")
        return ErrorResponse(
            error="scan_failed",
            message="Failed to scan networks"
        )

async def get_wifi_connections(active_only: bool = False):
    """Get WiFi connections (active or all) with AP mode filtering and full details"""
    try:
        # Build command with optional --active flag
        cmd = ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"]
        if active_only:
            cmd.append("--active")
        
        result = run_command(cmd)
        if not result["success"] or not result["output"]:
            logger.debug(f"No {'active ' if active_only else ''}connections found")
            return []
        
        logger.debug(f"{'Active ' if active_only else ''}connections: {result['output']}")
        
        connections = []
        for line in result["output"].splitlines():
            line = line.strip()
            if not line or line.startswith("Warning:"):
                continue
            parts = line.split(":")
            if len(parts) >= 3:
                name, conn_type, device = parts[0], parts[1], parts[2]
                if conn_type in ("wifi", "802-11-wireless"):
                    # For active connections, check if device is actually connected
                    if active_only and device and device != "--":
                        connections.append((name, device))
                    elif not active_only:
                        connections.append((name, device))
        
        # Get detailed information for each connection
        detailed_connections = []
        for connection_name, wifi_interface in connections:
            # Get connection details and check for AP mode
            detail_result = run_command([
                "nmcli", "-t", "-f", "802-11-wireless.ssid,802-11-wireless-security.key-mgmt,GENERAL.devices,802-11-wireless.seen-bssids,802-11-wireless.mode",
                "connection", "show", connection_name
            ])
            
            if not detail_result["success"] or not detail_result["output"]:
                continue
            
            # Parse the output
            ssid = ""
            security = "open"
            interface = ""
            seen_bssids = ""
            mode = ""
            
            for line in detail_result["output"].splitlines():
                line = line.strip()
                if not line or line.startswith("Warning:") or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == "802-11-wireless.ssid":
                    ssid = value
                elif key == "802-11-wireless-security.key-mgmt":
                    security = value
                elif key == "general.devices" and value:
                    interface = value
                elif key == "802-11-wireless.seen-bssids":
                    seen_bssids = value
                elif key == "802-11-wireless.mode":
                    mode = value.lower()
            
            # Skip AP mode connections
            if mode == "ap":
                logger.debug(f"Skipping AP mode connection: {connection_name}")
                continue
            
            # Use interface from connection or fallback to wifi_interface
            if not interface:
                interface = wifi_interface
            
            if ssid:  # Only add if we have a valid SSID
                detailed_connections.append(ConnectedNetwork(
                    ssid=ssid,
                    interface=interface,
                    security=parse_network_security(security),
                    connection_name=connection_name
                ))
        
        return detailed_connections
    except Exception as e:
        logger.error(f"Error getting {'active ' if active_only else ''}connections: {e}")
        return []

@app.get("/list-connected")
async def list_connected():
    """Get currently connected Wi-Fi network info (ssid/interface/security)."""
    try:
        # Get active WiFi connections
        connections = await get_wifi_connections(active_only=True)
        
        # Return the first connected network (if any)
        if connections:
            return ConnectedResponse(connected=connections[0])
        else:
            return ConnectedResponse(connected=None)
        
    except Exception as e:
        logger.error(f"Error getting connected network: {e}")
        return ConnectedResponse(connected=None)

@app.get("/list-saved")
async def list_saved():
    """Get list of saved networks"""
    try:
        # Get all WiFi connections (not just active)
        connections = await get_wifi_connections(active_only=False)
        
        return SavedNetworksResponse(saved_networks=connections)
    except Exception as e:
        logger.error(f"Error listing saved networks: {e}")
        return SavedNetworksResponse(saved_networks=[])

@app.post("/connect")
async def connect_to_network(request: ConnectRequest):
    """Connect to a WiFi network"""
    try:
        ssid = request.ssid
        passphrase = request.passphrase
        
        # Check if any hotspot is currently active using existing functions
        hotspot_active = False
        hotspot_type = None
        
        # Check for WiFi Connect hotspot
        connect_status = await get_connection_status("connect")
        if connect_status["active"]:
            hotspot_active = True
            hotspot_type = "connect"
            logger.info("WiFi Connect hotspot is active, stopping it before connecting")
            # Stop WiFi Connect hotspot using existing function
            await disable_wifi_connect()
        
        # Check for WiFi Direct hotspot
        direct_status = await get_connection_status("direct")
        if direct_status["active"]:
            hotspot_active = True
            hotspot_type = "direct"
            logger.info("WiFi Direct hotspot is active, stopping it before connecting")
            # Stop WiFi Direct hotspot using existing function
            await disable_wifi_direct()
        
        # Wait a moment for hotspot to fully stop
        if hotspot_active:
            time.sleep(2)
        await list_networks(use_cache=False, force_scan=True)
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
                    "password", passphrase, "ifname", get_wifi_interface()
                ])
            else:
                result = run_command([
                    "nmcli", "device", "wifi", "connect", ssid,
                    "ifname", get_wifi_interface()
                ])
        
        if not result["success"]:
            # If connection failed and we had a hotspot active, restart it using existing functions
            if hotspot_active and hotspot_type:
                logger.info(f"Connection failed, restarting {hotspot_type} hotspot")
                if hotspot_type == "connect":
                    await enable_wifi_connect()
                elif hotspot_type == "direct":
                    await enable_wifi_direct()
            return SuccessResponse(success=False, message="Failed to connect to network")
        
        # Connection successful - don't restart hotspot if it was WiFi Connect
        if hotspot_active and hotspot_type == "connect":
            logger.info("Connection successful, WiFi Connect hotspot will remain stopped")
        elif hotspot_active and hotspot_type == "direct":
            # For WiFi Direct, we might want to restart it, but for now we'll leave it stopped
            logger.info("Connection successful, WiFi Direct hotspot will remain stopped")
        
        # Clear network cache when connecting to a network
        clear_network_cache()
        
        # Get the connected network info and save state
        try:
            connected_response = await list_connected()
            if hasattr(connected_response, 'connected') and connected_response.connected:
                save_wifi_state("connected", connected_response.connected)
        except Exception as e:
            logger.warning(f"Could not save connected state: {e}")
        
        return SuccessResponse(success=True, message=f"Connected to {ssid}")
    except Exception as e:
        logger.error(f"Error connecting to network: {e}")
        return SuccessResponse(success=False, message="Connection failed")

async def forget_network(ssid: str = None, bssid: str = None) -> dict:
    """Remove all networks with the specified SSID or BSSID"""
    try:
        # Validate input parameters
        if not ssid and not bssid:
            return {
                "success": False,
                "message": "Either SSID or BSSID must be provided"
            }
        
        # Get all connections and find all with matching SSID or BSSID
        result = run_command([
            "nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"
        ])
        
        if not result["success"]:
            return {
                "success": False, 
                "message": "Failed to get connection list"
            }
        
        connections_to_delete = []
        
        # Find all connections with matching SSID or BSSID
        for line in result["output"].splitlines():
            line = line.strip()
            if line and ':' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    name, conn_type = parts[0], parts[1]
                    if conn_type == "802-11-wireless":
                        # Check if this connection has the matching SSID or BSSID
                        detail_result = run_command([
                            "nmcli", "-t", "-f", "802-11-wireless.ssid,802-11-wireless.mode,802-11-wireless.bssid",
                            "connection", "show", name
                        ])
                        
                        if detail_result["success"]:
                            connection_ssid = ""
                            connection_bssid = ""
                            mode = ""
                            for detail_line in detail_result["output"].splitlines():
                                if ':' in detail_line:
                                    key, value = detail_line.split(':', 1)
                                    if key == "802-11-wireless.ssid":
                                        connection_ssid = value.strip()
                                    elif key == "802-11-wireless.mode":
                                        mode = value.strip().lower()
                                    elif key == "802-11-wireless.bssid":
                                        connection_bssid = value.strip()
                            
                            # Skip AP mode connections
                            if mode == "ap":
                                continue
                            
                            # Match by SSID or BSSID
                            match_found = False
                            if ssid and connection_ssid == ssid:
                                match_found = True
                            elif bssid and connection_bssid == bssid:
                                match_found = True
                            
                            if match_found:
                                connections_to_delete.append(name)
        
        if not connections_to_delete:
            if bssid:
                return {
                    "success": False, 
                    "message": f"No networks with BSSID '{bssid}' found"
                }
            else:
                return {
                    "success": False, 
                    "message": f"No networks with SSID '{ssid}' found"
                }
        
        # Delete all connections with matching SSID
        deleted_count = 0
        failed_connections = []
        
        for connection_name in connections_to_delete:
            delete_result = run_command([
                "nmcli", "connection", "delete", connection_name
            ])
            
            if delete_result["success"]:
                deleted_count += 1
                logger.info(f"Successfully deleted connection: {connection_name}")
            else:
                failed_connections.append(connection_name)
                logger.error(f"Failed to delete connection {connection_name}: {delete_result['error']}")
        
        # Check if there are any networks left
        remaining_connections = await get_wifi_connections(active_only=False)
        
        if not remaining_connections:
            # No networks left, start WiFi Connect mode
            logger.info("No saved networks remaining, starting WiFi Connect mode")
            connect_result = await manage_wifi_connection("connect", True)
            if connect_result["success"]:
                logger.info("WiFi Connect mode started successfully")
                # State is already saved by manage_wifi_connection
            else:
                logger.warning(f"Failed to start WiFi Connect mode: {connect_result['message']}")
                # Save disconnected state if WiFi Connect failed
                save_wifi_state("disconnected")
        
        # Prepare response message
        if failed_connections:
            if bssid:
                message = f"Deleted {deleted_count} network(s) with BSSID '{bssid}'. Failed to delete: {', '.join(failed_connections)}"
            else:
                message = f"Deleted {deleted_count} network(s) with SSID '{ssid}'. Failed to delete: {', '.join(failed_connections)}"
        else:
            if bssid:
                message = f"Successfully deleted {deleted_count} network(s) with BSSID '{bssid}'"
            else:
                message = f"Successfully deleted {deleted_count} network(s) with SSID '{ssid}'"
        
        return {
            "success": len(failed_connections) == 0,
            "message": message
        }
            
    except Exception as e:
        identifier = bssid if bssid else ssid
        identifier_type = "BSSID" if bssid else "SSID"
        logger.error(f"Error forgetting network {identifier_type} {identifier}: {e}")
        return {
            "success": False, 
            "message": f"Error forgetting network '{identifier}': {str(e)}"
        }

@app.post("/forget")
async def forget_network_endpoint(request: ForgetNetworkRequest):
    """Remove a specific saved network"""
    if not request.ssid and not request.bssid:
        return SuccessResponse(
            success=False,
            message="Either SSID or BSSID is required"
        )
    
    result = await forget_network(ssid=request.ssid, bssid=request.bssid)
    return SuccessResponse(
        success=result["success"],
        message=result["message"]
    )

@app.post("/forget-network")
async def forget_network_endpoint_alt(request: dict):
    """Remove a specific saved network (alternative endpoint)"""
    # Handle both 'network_name', 'ssid', and 'bssid' fields for compatibility
    ssid = request.get("ssid") or request.get("network_name")
    bssid = request.get("bssid")
    
    if not ssid and not bssid:
        return SuccessResponse(
            success=False,
            message="Either SSID or BSSID is required"
        )
    
    result = await forget_network(ssid=ssid, bssid=bssid)
    return SuccessResponse(
        success=result["success"],
        message=result["message"]
    )

@app.post("/forget-all")
async def forget_all_networks(request: ForgetAllRequest):
    """Remove all saved networks"""
    try:
        # Get all saved networks using the existing list_saved endpoint
        saved_response = await list_saved()
        
        if not hasattr(saved_response, 'saved_networks'):
            return SuccessResponse(success=False, message="Failed to get saved networks")
        
        saved_networks = saved_response.saved_networks
        
        if not saved_networks:
            return SuccessResponse(success=True, message="No saved networks to forget")
        
        deleted_count = 0
        failed_networks = []
        
        # Forgot each network by SSID
        for network in saved_networks:
            forget_result = await forget_network(network.ssid)
            if forget_result["success"]:
                deleted_count += 1
            else:
                failed_networks.append(network.ssid)
        
        # Prepare response message
        if failed_networks:
            message = f"Forgot {deleted_count} networks. Failed to forget: {', '.join(failed_networks)}"
        else:
            message = f"Successfully forgot {deleted_count} networks"
        
        # Start WiFi Connect mode after forgetting all networks
        connect_result = await manage_wifi_connection("connect", True)
        if not connect_result["success"]:
            logger.warning(f"Failed to start WiFi Connect mode after forgetting all: {connect_result['message']}")
            # Save disconnected state if WiFi Connect failed
            save_wifi_state("disconnected")
        
        return SuccessResponse(
            success=len(failed_networks) == 0,  # Success only if no failures
            message=message
        )
    except Exception as e:
        logger.error(f"Error forgetting all networks: {e}")
        return SuccessResponse(success=False, message="Failed to forget all networks")

@app.get("/get-wifi-direct")
async def get_wifi_direct():
    """Get current WiFi Direct mode status"""
    try:
        result = await get_connection_status("direct")
        return WiFiDirectResponse(value=result["active"])
    except Exception as e:
        logger.error(f"Error getting WiFi Direct status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get WiFi Direct status")

@app.get("/get-wifi-connect")
async def get_wifi_connect():
    """Get current WiFi Connect mode status"""
    try:
        result = await get_connection_status("connect")
        return WiFiConnectResponse(value=result["active"])
    except Exception as e:
        logger.error(f"Error getting WiFi Connect status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get WiFi Connect status")

@app.get("/scan-status")
async def get_scan_status():
    """Get information about network scanning capabilities and warnings"""
    try:
        # Check if any hotspot is currently active
        direct_status = await get_connection_status("direct")
        connect_status = await get_connection_status("connect")
        hotspot_active = direct_status["active"] or connect_status["active"]
        
        if hotspot_active:
            hotspot_type = "direct" if direct_status["active"] else "connect"
            hotspot_name = "WiFi Direct" if direct_status["active"] else "WiFi Connect"
            
            return ScanStatusResponse(
                hotspot_active=True,
                hotspot_type=hotspot_type,
                can_scan=True,  # We can scan by temporarily disabling hotspot
                warning_message=f"Scanning will temporarily disconnect clients from {hotspot_name} hotspot"
            )
        else:
            return ScanStatusResponse(
                hotspot_active=False,
                hotspot_type=None,
                can_scan=True,
                warning_message=None
            )
            
    except Exception as e:
        logger.error(f"Error getting scan status: {e}")
        return ScanStatusResponse(
            hotspot_active=False,
            hotspot_type=None,
            can_scan=False,
            warning_message="Unable to determine scan status"
        )
        
if __name__ == "__main__":
    # Run the server (startup event will handle initialization)
    uvicorn.run(
        app, 
        host=config.get_server_config()["host"],  # Allow external connections
        port=config.get_server_config()["port"],       # Default port
        log_level="info"
    )

