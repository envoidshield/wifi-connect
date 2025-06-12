#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import json
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import mimetypes
from datetime import datetime, timedelta

touchscreen = os.getenv('ENABLE_SURFACE_SUPPORT')

class WiFiConnectWrapper:
    def __init__(self, binary_path="wifi-connect", cache_duration=300):  # 5 minutes default cache
        """Initialize with path to the wifi-connect binary and cache duration in seconds"""
        self.binary_path = binary_path
        self.cache_duration = cache_duration
        self._network_cache = None
        self._cache_timestamp = None
        self._cache_lock = threading.Lock()
    
    def check_hotspot_status(self):
        """Check if hotspot is currently running"""
        try:
            result = subprocess.run(
                [self.binary_path, "--check-hotspot"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output to determine if hotspot is running
            output = result.stdout
            if "Hotspot Status: RUNNING" in output:
                # Extract hotspot details
                ssid_match = re.search(r'SSID: (.*?)(?:\n|$)', output)
                gateway_match = re.search(r'Gateway: (.*?)(?:\n|$)', output)
                interface_match = re.search(r'Interface: (.*?)(?:\n|$)', output)
                password_match = re.search(r'Password Protected: (.*?)(?:\n|$)', output)
                uptime_match = re.search(r'Uptime: (.*?)(?:\n|$)', output)
                
                return {
                    "running": True,
                    "ssid": ssid_match.group(1).strip() if ssid_match else None,
                    "gateway": gateway_match.group(1).strip() if gateway_match else None,
                    "interface": interface_match.group(1).strip() if interface_match else None,
                    "password_protected": password_match.group(1).strip() == "true" if password_match else False,
                    "uptime": uptime_match.group(1).strip() if uptime_match else None
                }
            else:
                return {"running": False}
                
        except subprocess.CalledProcessError as e:
            print(f"Error checking hotspot status: {e}", file=sys.stderr)
            return {"running": False}
    
    def _is_cache_valid(self):
        """Check if the network cache is still valid"""
        if self._network_cache is None or self._cache_timestamp is None:
            return False
        
        return datetime.now() - self._cache_timestamp < timedelta(seconds=self.cache_duration)
    
    def _scan_networks_internal(self):
        """Internal method to actually scan for networks"""
        try:
            # Scan for networks
            result = subprocess.run(
                [self.binary_path, "--list-networks"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output based on the actual format
            networks = []
            output = result.stdout
            
            # Check if the expected section exists
            if "Available WiFi Networks:" in output:
                # Extract the networks section
                networks_section = output.split("Available WiFi Networks:")[1]
                
                # Parse each network entry
                # The pattern is "SSID: <name>, Security: <type>"
                network_pattern = re.compile(r'SSID: (.*?), Security: (.*?)(?:,|$)', re.MULTILINE)
                matches = network_pattern.findall(networks_section)
                
                for ssid, security in matches:
                    # Skip empty lines and connected status indicators
                    ssid_clean = ssid.strip()
                    security_clean = security.strip()
                    if ssid_clean and not ssid_clean.startswith('('):
                        networks.append({
                            "ssid": ssid_clean,
                            "security": security_clean,
                        })
            
            return networks
            
        except subprocess.CalledProcessError as e:
            print(f"Error scanning networks: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr}", file=sys.stderr)
            return []
    
    def _refresh_network_cache(self, force_rescan=False):
        """Refresh the network cache by temporarily stopping hotspot if needed"""
        with self._cache_lock:
            # If cache is valid and we're not forcing a rescan, return cached data
            if not force_rescan and self._is_cache_valid():
                return self._network_cache
            
            print("Refreshing network cache...", file=sys.stderr)
            
            hotspot_was_running = False
            hotspot_info = None
            
            try:
                # Check if hotspot is running
                hotspot_status = self.check_hotspot_status()
                if hotspot_status.get("running", False):
                    hotspot_was_running = True
                    hotspot_info = hotspot_status
                    print("Hotspot is running, temporarily stopping to scan networks...", file=sys.stderr)
                    
                    # Stop hotspot to allow scanning
                    if not self.stop_hotspot():
                        print("Failed to stop hotspot for scanning", file=sys.stderr)
                        return self._network_cache or []
                    
                    # Wait a moment for the interface to be available
                    time.sleep(3)
                
                # Now scan for networks
                networks = self._scan_networks_internal()
                
                # Update cache
                self._network_cache = networks
                self._cache_timestamp = datetime.now()
                
                print(f"Network cache updated with {len(networks)} networks", file=sys.stderr)
                
                return networks
                
            finally:
                # Restart hotspot if it was running before
                if hotspot_was_running:
                    print("Restarting hotspot...", file=sys.stderr)
                    if not self.start_hotspot():
                        print("Failed to restart hotspot after scanning", file=sys.stderr)
                    else:
                        print("Hotspot restarted successfully", file=sys.stderr)
    
    def list_networks(self, use_cache=False):
        """List available WiFi networks, using cache when hotspot is running"""
        networks = self._scan_networks_internal()
        if use_cache and self._network_cache is not None:
            # Use cached networks if available
            return self._network_cache
        
        # Update cache even when hotspot is not running
        with self._cache_lock:
            self._network_cache = networks
            self._cache_timestamp = datetime.now()
        
        return networks
    
    def get_cache_info(self):
        """Get information about the network cache"""
        with self._cache_lock:
            if self._cache_timestamp is None:
                return {
                    "cached": False,
                    "cache_age": None,
                    "cache_valid": False,
                    "networks_count": 0
                }
            
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            return {
                "cached": True,
                "cache_age": cache_age,
                "cache_valid": self._is_cache_valid(),
                "networks_count": len(self._network_cache or []),
                "cache_timestamp": self._cache_timestamp.isoformat()
            }
    
    def clear_cache(self):
        """Clear the network cache"""
        with self._cache_lock:
            self._network_cache = None
            self._cache_timestamp = None
        print("Network cache cleared", file=sys.stderr)
    
    def start_hotspot(self):
        """Start the hotspot"""
        try:
            # Start hotspot in background (non-blocking)
            process = subprocess.Popen(
                [self.binary_path, "--start-hotspot"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Check if it started successfully
            status = self.check_hotspot_status()
            return status.get("running", False)
            
        except Exception as e:
            print(f"Error starting hotspot: {e}", file=sys.stderr)
            return False
    
    def stop_hotspot(self):
        """Stop the hotspot"""
        try:
            subprocess.run(
                [self.binary_path, "--stop-hotspot"],
                check=True,
                capture_output=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error stopping hotspot: {e}", file=sys.stderr)
            return False
    
    def restart_hotspot(self):
        """Restart the hotspot"""
        try:
            subprocess.run(
                [self.binary_path, "--restart-hotspot"],
                check=True,
                capture_output=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error restarting hotspot: {e}", file=sys.stderr)
            return False
    
    def list_connected(self):
        """List currently connected WiFi network using the binary"""
        try:
            result = subprocess.run(
                [self.binary_path, "--list-connected"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output to extract connected network info
            output = result.stdout
            
            if "Connected Network:" in output or "Connected:" in output:
                # Extract the connected network section
                if "Connected Network:" in output:
                    connected_section = output.split("Connected Network:")[1]
                else:
                    connected_section = output.split("Connected:")[1]
                
                # Parse the connected network information
                # Expected format: SSID: <name>, Security: <type>, Signal: <strength>%, Interface: <interface>, IP: <ip_address>
                ssid_match = re.search(r'SSID: (.*?)(?:,|$)', connected_section, re.MULTILINE)
                security_match = re.search(r'Security: (.*?)(?:,|$)', connected_section, re.MULTILINE)
                signal_match = re.search(r'Signal: (\d+)%', connected_section)
                interface_match = re.search(r'Interface: (.*?)(?:,|$)', connected_section, re.MULTILINE)
                ip_match = re.search(r'IP: (.*?)(?:,|\n|$)', connected_section, re.MULTILINE)
                
                if ssid_match:
                    connected_network = {
                        "ssid": ssid_match.group(1).strip(),
                        "security": security_match.group(1).strip() if security_match else "unknown",
                        "signal_strength": int(signal_match.group(1)) if signal_match else 0,
                        "interface": interface_match.group(1).strip() if interface_match else "unknown",
                        "ip_address": ip_match.group(1).strip() if ip_match else None
                    }
                    return connected_network
                    
            elif "No network connected" in output or "Not connected" in output or output.strip() == "":
                return None
            
            return None
        except subprocess.CalledProcessError as e:
            print(f"Error listing connected network: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr}", file=sys.stderr)
            return None
    
    def list_saved(self):
        """List all saved WiFi networks using the binary"""
        try:
            result = subprocess.run(
                [self.binary_path, "--list-saved"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output based on the actual format
            networks = []
            output = result.stdout
            
            # Check if the expected section exists
            if "Saved WiFi Networks:" in output:
                # Extract the saved networks section
                networks_section = output.split("Saved WiFi Networks:")[1]
                
                # Parse each saved network entry
                # Expected format: "SSID: <name>, Security: <type>"
                network_pattern = re.compile(r'SSID: (.*?), Security: (.*?)(?:,|$)', re.MULTILINE)
                matches = network_pattern.findall(networks_section)
                
                for ssid, security in matches:
                    ssid_clean = ssid.strip()
                    security_clean = security.strip()
                    if ssid_clean:
                        networks.append({
                            "ssid": ssid_clean,
                            "security": security_clean,
                        })
            elif "No saved networks found" in output:
                return []
            
            return networks
        except subprocess.CalledProcessError as e:
            print(f"Error listing saved networks: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr}", file=sys.stderr)
            return []
    
    def check_internet_connectivity(self, interface=None, timeout=5):
        """Check if we have actual internet connectivity by pinging reliable servers"""
        test_hosts = [
            "8.8.8.8",      # Google DNS
            "1.1.1.1",      # Cloudflare DNS  
            "208.67.222.222" # OpenDNS
        ]
        
        for host in test_hosts:
            try:
                # Build ping command
                cmd = ["ping", "-c", "1", "-W", str(timeout)]
                
                # If interface is specified, bind to that interface
                if interface:
                    cmd.extend(["-I", interface])
                
                cmd.append(host)
                
                # Run ping command
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 2
                )
                
                if result.returncode == 0:
                    print(f"Internet connectivity confirmed via {host}", file=sys.stderr)
                    return True
                    
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                print(f"Failed to ping {host}: {e}", file=sys.stderr)
                continue
        
        print("No internet connectivity detected", file=sys.stderr)
        return False

    def _ensure_connectivity(self):
        """Helper method to start hotspot if no real internet connection exists"""
        connected = self.list_connected()
        
        if not connected:
            print("No WiFi network connected, starting hotspot...", file=sys.stderr)
            if self.start_hotspot():
                print("Hotspot started successfully.", file=sys.stderr)
            else:
                print("Failed to start hotspot.", file=sys.stderr)
            return
        
        # We have a WiFi connection, but check if it has internet access
        interface = connected.get('interface')
        if not self.check_internet_connectivity(interface):
            print(f"Connected to '{connected['ssid']}' but no internet access, starting hotspot...", file=sys.stderr)
            if self.start_hotspot():
                print("Hotspot started successfully.", file=sys.stderr)
            else:
                print("Failed to start hotspot.", file=sys.stderr)
        else:
            print(f"Connected to '{connected['ssid']}' with internet access.", file=sys.stderr)

    def forget_network(self, ssid):
        """Forget a specific WiFi network using the binary"""
        try:
            subprocess.run(
                [self.binary_path, "--forget-network", ssid],
                check=True
            )
            
            # Check connectivity and start hotspot if needed
            self._ensure_connectivity()
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error forgetting network '{ssid}': {e}", file=sys.stderr)
            print(f"Error output: {e.stderr if hasattr(e, 'stderr') else ''}", file=sys.stderr)
            return False

    def forget_all(self):
        """Forget all saved WiFi networks using the binary"""
        try:
            subprocess.run(
                [self.binary_path, "--forget-all"],
                check=True
            )
            
            # After forgetting all networks, start hotspot immediately
            print("All networks forgotten, starting hotspot...", file=sys.stderr)
            if self.start_hotspot():
                print("Hotspot started successfully.", file=sys.stderr)
            else:
                print("Failed to start hotspot.", file=sys.stderr)
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error forgetting networks: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr if hasattr(e, 'stderr') else ''}", file=sys.stderr)
            return False

    
    def connect(self, ssid, passphrase=None):
        """Connect to a WiFi network using the binary with proper hotspot management"""
        hotspot_was_running = False
        hotspot_info = None
        
        try:
            # Step 1: Check if hotspot is running and stop it if needed
            print(f"Attempting to connect to '{ssid}'...", file=sys.stderr)
            hotspot_status = self.check_hotspot_status()
            if hotspot_status.get("running", False):
                hotspot_was_running = True
                hotspot_info = hotspot_status
                print("Hotspot is running, stopping it for connection attempt...", file=sys.stderr)
                
                if not self.stop_hotspot():
                    print("Failed to stop hotspot for connection", file=sys.stderr)
                    return False
                
                # Wait for the interface to be available and verify hotspot is stopped
                time.sleep(3)
                
                # Double-check that hotspot is actually stopped
                verify_status = self.check_hotspot_status()
                if verify_status.get("running", False):
                    print("Hotspot still running after stop command, trying again...", file=sys.stderr)
                    self.stop_hotspot()
                    time.sleep(3)
                    
                    final_verify = self.check_hotspot_status()
                    if final_verify.get("running", False):
                        print("Failed to stop hotspot completely", file=sys.stderr)
                        return False
                
                print("Hotspot successfully stopped", file=sys.stderr)
            
            # Step 2: Scan networks to ensure the target network is available
            print("Scanning for available networks...", file=sys.stderr)
            available_networks = self._scan_networks_internal()
            
            # Check if the target network is available
            target_network = None
            for network in available_networks:
                if network['ssid'] == ssid:
                    target_network = network
                    break
            
            if not target_network:
                print(f"Warning: Network '{ssid}' not found in scan results", file=sys.stderr)
                # Continue anyway as the network might be hidden or intermittent
            else:
                print(f"Found target network: {target_network['ssid']} (Security: {target_network['security']})", file=sys.stderr)
            
            # Step 3: Attempt to connect
            print(f"Connecting to '{ssid}'...", file=sys.stderr)
            cmd = [self.binary_path, "--connect", ssid]
            if passphrase:
                cmd.extend(["--passphrase", passphrase])
            
            # Run the connection command
            result = subprocess.run(
                cmd, 
                check=True,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout for connection attempts
            )
            
            # Wait a moment for the connection to establish
            time.sleep(5)
            
            # Step 4: Verify the connection was successful
            connected_network = self.list_connected()
            if connected_network and connected_network['ssid'] == ssid:
                print(f"Successfully connected to '{ssid}'", file=sys.stderr)
                if connected_network.get('ip_address'):
                    print(f"IP Address: {connected_network['ip_address']}", file=sys.stderr)
                
                # Clear the network cache since we're now connected to a different network
                self.clear_cache()
                return True
            else:
                print(f"Connection attempt completed but not connected to '{ssid}'", file=sys.stderr)
                raise Exception("Connection verification failed")
                
        except subprocess.TimeoutExpired:
            print(f"Connection attempt to '{ssid}' timed out", file=sys.stderr)
            return False
        except subprocess.CalledProcessError as e:
            print(f"Error connecting to network '{ssid}': {e}", file=sys.stderr)
            if hasattr(e, 'stderr') and e.stderr:
                print(f"Error output: {e.stderr}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Unexpected error during connection to '{ssid}': {e}", file=sys.stderr)
            return False
        
        finally:
            # Step 5: Restart hotspot if connection failed and hotspot was running before
            final_connected = self.list_connected()
            connection_successful = final_connected and final_connected['ssid'] == ssid
            
            if not connection_successful and hotspot_was_running:
                print("Connection failed, restarting hotspot...", file=sys.stderr)
                if self.start_hotspot():
                    print("Hotspot restarted successfully after failed connection", file=sys.stderr)
                    # Verify hotspot actually started
                    time.sleep(3)
                    verify_hotspot = self.check_hotspot_status()
                    if verify_hotspot.get("running", False):
                        print("Hotspot restart verified", file=sys.stderr)
                    else:
                        print("Hotspot restart verification failed", file=sys.stderr)
                else:
                    print("Failed to restart hotspot after connection failure", file=sys.stderr)
            elif connection_successful:
                print(f"Connected successfully to '{ssid}', hotspot remains off", file=sys.stderr)
            
            return connection_successful

class WiFiHandler(BaseHTTPRequestHandler):
    wifi_manager = None  
    def _set_headers(self, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
    
    def do_GET(self):
        if self.path == '/':
            # Serve the main HTML file
            try:
                with open('index.html', 'r') as f:
                    content = f.read()
                if touchscreen == '1':
                    content = content.replace('<!-- kioskboard -->', '<script src="./ui/public/static/js/kioskboard-aio-2.3.0.min.js"></script>')
                    content = content.replace('<!-- keyboard -->', '<script src="./ui/public/static/js/keyboard.js"></script>')
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "index.html not found"}).encode())
        
        elif self.path.startswith('/list-networks'):
            print("Getting network list...", file=sys.stderr)
            use_cache = 'use_cache=true' in self.path

            # Check if hotspot is running
            hotspot_status = self.wifi_manager.check_hotspot_status()
            is_running = hotspot_status.get('running', False)

            networks = []
            cache_info = {}

            if use_cache: 
                networks = self.wifi_manager.list_networks(use_cache=True)
                cache_info = self.wifi_manager.get_cache_info()
            elif not is_running:
                # If the hotspot is not running, simply list networks (new logic)
                networks = self.wifi_manager.list_networks(use_cache=use_cache)
                cache_info = self.wifi_manager.get_cache_info()
            else:
                self.wifi_manager.stop_hotspot()
                time.sleep(2)
                networks = self.wifi_manager._scan_networks_internal()  # Force rescan
                time.sleep(2)
                self.wifi_manager.start_hotspot()

            self._set_headers()
            self.wfile.write(json.dumps({
                "networks": networks,
                "cache_info": cache_info
            }).encode())
            
        elif self.path == '/list-networks?refresh=true' or self.path == '/list-networks?force=true':
            print("Force refreshing network list...", file=sys.stderr)
            networks = self.wifi_manager.list_networks(force_refresh=True)
            cache_info = self.wifi_manager.get_cache_info()
            self._set_headers()
            self.wfile.write(json.dumps({
                "networks": networks,
                "cache_info": cache_info
            }).encode())
        
        elif self.path == '/cache-info':
            cache_info = self.wifi_manager.get_cache_info()
            self._set_headers()
            self.wfile.write(json.dumps({"cache_info": cache_info}).encode())
        
        elif self.path == '/list-connected':
            connected = self.wifi_manager.list_connected()
            self._set_headers()
            self.wfile.write(json.dumps({"connected": connected}).encode())
        
        elif self.path == '/list-saved':
            saved_networks = self.wifi_manager.list_saved()
            self._set_headers()
            self.wfile.write(json.dumps({"saved_networks": saved_networks}).encode())
        
        elif self.path == '/hotspot-status':
            status = self.wifi_manager.check_hotspot_status()
            self._set_headers()
            self.wfile.write(json.dumps({"hotspot": status}).encode())
        
        elif self.path == '/connection-status':
            # Get both connection and hotspot status
            connected = self.wifi_manager.list_connected()
            hotspot_status = self.wifi_manager.check_hotspot_status()
            self._set_headers()
            self.wfile.write(json.dumps({
                "connected": connected,
                "hotspot": hotspot_status
            }).encode())
        
        elif self.path.startswith('/ui/public/static'):
            rel_path = self.path.removeprefix('/ui/public/static/')
            fs_path = os.path.join('ui', 'public', 'static', rel_path)

            if os.path.exists(fs_path) and os.path.isfile(fs_path):
                mime_type, _ = mimetypes.guess_type(fs_path)
                self.send_response(200)
                self.send_header('Content-type', mime_type or 'application/octet-stream')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(fs_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "File not found"}).encode())

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())

    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            
            if self.path == '/forget-all':
                success = self.wifi_manager.forget_all()
                self._set_headers()
                if success:
                    time.sleep(2)
                    self.wifi_manager.start_hotspot()
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/forget-network':
                if 'ssid' not in data:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "SSID is required"}).encode())
                    return
                
                ssid = data['ssid']
                success = self.wifi_manager.forget_network(ssid)
                self._set_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/connect':
                if 'ssid' not in data:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "SSID is required"}).encode())
                    return
                
                ssid = data['ssid']
                passphrase = data.get('passphrase')
                
                print(f"Received connection request for '{ssid}'", file=sys.stderr)
                
                # Check hotspot status before connection attempt
                initial_hotspot_status = self.wifi_manager.check_hotspot_status()
                was_hotspot_running = initial_hotspot_status.get("running", False)
                
                if was_hotspot_running:
                    print("Hotspot is running, will be stopped for connection attempt", file=sys.stderr)
                
                # Attempt connection (this handles hotspot stopping/restarting internally)
                success = self.wifi_manager.connect(ssid, passphrase)
                
                # Wait a moment for status to stabilize
                time.sleep(2)
                
                # Get the current connection status after attempt
                connected = self.wifi_manager.list_connected()
                hotspot_status = self.wifi_manager.check_hotspot_status()
                
                response_data = {
                    "success": success,
                    "connected": connected,
                    "hotspot": hotspot_status,
                    "was_hotspot_running": was_hotspot_running
                }
                
                if success and connected:
                    response_data["message"] = f"Successfully connected to '{ssid}'"
                    if was_hotspot_running:
                        response_data["message"] += " - Hotspot stopped"
                elif not success:
                    response_data["message"] = f"Failed to connect to '{ssid}'"
                    if was_hotspot_running and hotspot_status.get("running", False):
                        response_data["message"] += " - Hotspot has been restarted"
                    elif was_hotspot_running and not hotspot_status.get("running", False):
                        response_data["message"] += " - Hotspot failed to restart"
                
                self._set_headers()
                self.wfile.write(json.dumps(response_data).encode())
            
            elif self.path == '/start-hotspot':
                success = self.wifi_manager.start_hotspot()
                self._set_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/stop-hotspot':
                success = self.wifi_manager.stop_hotspot()
                self._set_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/restart-hotspot':
                success = self.wifi_manager.restart_hotspot()
                self._set_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/refresh-networks':
                # Force refresh the network cache
                networks = self.wifi_manager.list_networks(force_refresh=True)
                cache_info = self.wifi_manager.get_cache_info()
                self._set_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "networks": networks,
                    "cache_info": cache_info
                }).encode())
            
            elif self.path == '/clear-cache':
                # Clear the network cache
                self.wifi_manager.clear_cache()
                self._set_headers()
                self.wfile.write(json.dumps({"success": True}).encode())
            
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode())
        
        except json.JSONDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(server_class=HTTPServer, port=8000, wifi_manager=None):
    """Start the HTTP server"""
    server_address = ('', port)
    
    # Set the wifi_manager in the handler class
    WiFiHandler.wifi_manager = wifi_manager
    
    httpd = server_class(server_address, WiFiHandler)
    print(f"Starting server on port {port}...")
    httpd.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='WiFi Connection Manager with Network Caching')
    parser.add_argument('--binary', default='wifi-connect', help='Path to the wifi-connect binary (default: wifi-connect)')
    parser.add_argument('--cache-duration', type=int, default=300, help='Network cache duration in seconds (default: 300)')
    parser.add_argument('--forget-all', action='store_true', help='Forget all saved WiFi networks and exit')
    parser.add_argument('--list-networks', action='store_true', help='List all available WiFi networks and exit')
    parser.add_argument('--list-connected', action='store_true', help='List currently connected WiFi network and exit')
    parser.add_argument('--list-saved', action='store_true', help='List all saved WiFi networks and exit')
    parser.add_argument('--forget-network', metavar='ssid', help='Forget a specific WiFi network by SSID and exit')
    parser.add_argument('--connect', metavar='ssid', help='Connect to a specific WiFi network')
    parser.add_argument('--passphrase', metavar='passphrase', help='Passphrase for the WiFi network to connect to')
    parser.add_argument('--start-hotspot', action='store_true', help='Start the hotspot and exit')
    parser.add_argument('--stop-hotspot', action='store_true', help='Stop the hotspot and exit')
    parser.add_argument('--restart-hotspot', action='store_true', help='Restart the hotspot and exit')
    parser.add_argument('--check-hotspot', action='store_true', help='Check hotspot status and exit')
    parser.add_argument('--serve', action='store_true', help='Run as a microserver')
    parser.add_argument('--port', type=int, default=8000, help='Port for the server to listen on (default: 8000)')
    parser.add_argument('--clear-cache', action='store_true', help='Clear the network cache and exit')
    parser.add_argument('--cache-info', action='store_true', help='Show cache information and exit')
    
    args = parser.parse_args()
    
    wifi_manager = WiFiConnectWrapper(binary_path=args.binary, cache_duration=args.cache_duration)
    
    # Command-line operations
    if args.cache_info:
        cache_info = wifi_manager.get_cache_info()
        print("Network Cache Information:")
        print(f"Cached: {cache_info['cached']}")
        if cache_info['cached']:
            print(f"Cache Age: {cache_info['cache_age']:.1f} seconds")
            print(f"Cache Valid: {cache_info['cache_valid']}")
            print(f"Networks Count: {cache_info['networks_count']}")
            print(f"Cache Timestamp: {cache_info['cache_timestamp']}")
        sys.exit(0)
    
    if args.clear_cache:
        wifi_manager.clear_cache()
        print("Network cache cleared.")
        sys.exit(0)
    
    if args.list_networks:
        networks = wifi_manager.list_networks()
        cache_info = wifi_manager.get_cache_info()
        print("Available WiFi networks:")
        if networks:
            for idx, network in enumerate(networks, 1):
                print(f"{idx}. {network['ssid']} (Security: {network['security']})")
        else:
            print("No networks found.")
        
        if cache_info['cached']:
            print(f"\n(Using cached data, age: {cache_info['cache_age']:.1f}s)")
        sys.exit(0)
    
    if args.list_connected:
        connected = wifi_manager.list_connected()
        if connected:
            print("Currently connected network:")
            print(f"SSID: {connected['ssid']}")
            print(f"Security: {connected['security']}")
            print(f"Signal Strength: {connected['signal_strength']}%")
            print(f"Interface: {connected['interface']}")
            if connected['ip_address']:
                print(f"IP Address: {connected['ip_address']}")
        else:
            print("No network currently connected.")
        sys.exit(0)
    
    if args.list_saved:
        saved_networks = wifi_manager.list_saved()
        print("Saved WiFi networks:")
        if saved_networks:
            for idx, network in enumerate(saved_networks, 1):
                print(f"{idx}. {network['ssid']} (Security: {network['security']})")
        else:
            print("No saved networks found.")
        sys.exit(0)
    
    if args.forget_network:
        if wifi_manager.forget_network(args.forget_network):
            print(f"Successfully forgot network '{args.forget_network}'.")
        else:
            print(f"Failed to forget network '{args.forget_network}'.")
        sys.exit(0)
    
    if args.forget_all:
        if wifi_manager.forget_all():
            print("All saved WiFi networks have been forgotten.")
        else:
            print("Failed to forget WiFi networks.")
        sys.exit(0)
    
    if args.connect:
        if wifi_manager.connect(args.connect, args.passphrase):
            print(f"Connected to {args.connect}.")
        else:
            print(f"Failed to connect to {args.connect}.")
        sys.exit(0)
    
    if args.start_hotspot:
        if wifi_manager.start_hotspot():
            print("Hotspot started successfully.")
        else:
            print("Failed to start hotspot.")
        sys.exit(0)
    
    if args.stop_hotspot:
        if wifi_manager.stop_hotspot():
            print("Hotspot stopped successfully.")
        else:
            print("Failed to stop hotspot.")
        sys.exit(0)
    
    if args.restart_hotspot:
        if wifi_manager.restart_hotspot():
            print("Hotspot restarted successfully.")
        else:
            print("Failed to restart hotspot.")
        sys.exit(0)
    
    if args.check_hotspot:
        status = wifi_manager.check_hotspot_status()
        if status.get("running", False):
            print("Hotspot Status: RUNNING")
            if status.get("ssid"):
                print(f"SSID: {status['ssid']}")
            if status.get("gateway"):
                print(f"Gateway: {status['gateway']}")
            if status.get("interface"):
                print(f"Interface: {status['interface']}")
            print(f"Password Protected: {status.get('password_protected', False)}")
            if status.get("uptime"):
                print(f"Uptime: {status['uptime']}")
        else:
            print("Hotspot Status: STOPPED")
        sys.exit(0)
    
    # Run as a server if no other operations are specified or --serve is used
    if args.serve or (not any([args.list_networks, args.list_connected, args.list_saved, 
                              args.forget_all, args.forget_network, args.connect,
                              args.start_hotspot, args.stop_hotspot, args.restart_hotspot,
                              args.check_hotspot, args.clear_cache, args.cache_info])):
        try:
            run_server(port=args.port, wifi_manager=wifi_manager)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            sys.exit(0)

if __name__ == "__main__":
    main()

