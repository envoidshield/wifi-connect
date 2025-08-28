#!/bin/bash

# WiFi Connect API Server Startup Script
# Uses configuration from wifi_config.json and environment variables

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Change to script directory
cd "$(dirname "$0")"

# Check if config file exists, create if not
if [ ! -f "wifi_config.json" ]; then
    print_info "Creating default configuration file..."
    python3 config.py
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_warning "Not running as root - some WiFi features may be limited"
    print_warning "Consider running with: sudo $0"
fi

# Check dependencies
print_info "Checking dependencies..."
if ! command -v nmcli &> /dev/null; then
    echo "Error: nmcli not found. Please install NetworkManager"
    exit 1
fi

if ! command -v iw &> /dev/null; then
    echo "Error: iw not found. Please install wireless tools"
    exit 1
fi

# Install Python dependencies if needed
if ! python3 -c "import fastapi, uvicorn, pydantic" &> /dev/null; then
    print_info "Installing Python dependencies..."
    pip3 install -r requirements.txt
fi

print_success "Starting WiFi API Server..."
print_info "Configuration loaded from wifi_config.json and environment variables"
print_info "Press Ctrl+C to stop the server"

# Start the server
python3 wifi_api_server.py
