#!/usr/bin/env python3
import argparse
import subprocess
import sys
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class WiFiConnectWrapper:
    def __init__(self, binary_path="wifi-connect"):
        """Initialize with path to the wifi-connect binary"""
        self.binary_path = binary_path
    
    def list_networks(self):
        """List available WiFi networks using the binary"""
        try:
            result = subprocess.run(
                [self.binary_path, "--list-networks"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output based on the actual format
            networks = []
            # Look for the part after "Available WiFi Networks:"
            output = result.stdout
            
            # Check if the expected section exists
            if "Available WiFi Networks:" in output:
                # Extract the networks section
                networks_section = output.split("Available WiFi Networks:")[1]
                
                # Parse each network entry
                # The pattern is "SSID: <name>, Security: <type>"
                network_pattern = re.compile(r'SSID: (.*?), Security: (.*?)$', re.MULTILINE)
                matches = network_pattern.findall(networks_section)
                
                for ssid, security in matches:
                    networks.append({
                        "ssid": ssid.strip(),
                        "security": security.strip(),
                    })
            
            return networks
        except subprocess.CalledProcessError as e:
            print(f"Error listing networks: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr}", file=sys.stderr)
            return []
    
    def forget_all(self):
        """Forget all saved WiFi networks using the binary"""
        try:
            subprocess.run(
                [self.binary_path, "--forget-all"],
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error forgetting networks: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr if hasattr(e, 'stderr') else ''}", file=sys.stderr)
            return False
    
    def connect(self, ssid, passphrase=None):
        """Connect to a WiFi network using the binary"""
        try:
            cmd = [self.binary_path, "--connect", ssid]
            if passphrase:
                cmd.extend(["--passphrase", passphrase])
            
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error connecting to network: {e}", file=sys.stderr)
            print(f"Error output: {e.stderr if hasattr(e, 'stderr') else ''}", file=sys.stderr)
            return False

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
                with open('index.html', 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "index.html not found"}).encode())
        elif self.path == '/list-networks':
            networks = self.wifi_manager.list_networks()
            self._set_headers()
            self.wfile.write(json.dumps({"networks": networks}).encode())
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
                self.wfile.write(json.dumps({"success": success}).encode())
            
            elif self.path == '/connect':
                if 'ssid' not in data:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "SSID is required"}).encode())
                    return
                
                ssid = data['ssid']
                passphrase = data.get('passphrase')
                
                success = self.wifi_manager.connect(ssid, passphrase)
                self._set_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
            
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
    parser = argparse.ArgumentParser(description='WiFi Connection Manager')
    parser.add_argument('--binary', default='wifi-connect', help='Path to the wifi-connect binary (default: wifi-connect)')
    parser.add_argument('--forget-all', action='store_true', help='Forget all saved WiFi networks and exit')
    parser.add_argument('--list-networks', action='store_true', help='List all available WiFi networks and exit')
    parser.add_argument('--connect', metavar='ssid', help='Connect to a specific WiFi network')
    parser.add_argument('--passphrase', metavar='passphrase', help='Passphrase for the WiFi network to connect to')
    parser.add_argument('--serve', action='store_true', help='Run as a microserver')
    parser.add_argument('--port', type=int, default=8000, help='Port for the server to listen on (default: 8000)')
    
    args = parser.parse_args()
    
    wifi_manager = WiFiConnectWrapper(binary_path=args.binary)
    
    # Command-line operations
    if args.list_networks:
        networks = wifi_manager.list_networks()
        print("Available WiFi networks:")
        for idx, network in enumerate(networks, 1):
            print(f"{idx}. {network['ssid']} (Security: {network['security']})")
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
    
    # Run as a server if no other operations are specified or --serve is used
    if args.serve or (not args.list_networks and not args.forget_all and not args.connect):
        try:
            run_server(port=args.port, wifi_manager=wifi_manager)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            sys.exit(0)

if __name__ == "__main__":
    main()
