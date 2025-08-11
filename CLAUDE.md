# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WiFi Connect is a Rust-based utility for dynamically setting WiFi configuration on Linux devices via a captive portal. The project consists of:
- Core Rust application that manages NetworkManager for WiFi connectivity
- React-based UI for the captive portal (in `ui/` directory)
- Python API server (`scripts/api.py`) for external control
- Shell scripts for deployment and management

## Development Commands

### Building the Rust Application
```bash
# Build release version
cargo build --release

# Check compilation without building
cargo check

# Run the application (requires root)
sudo ./target/release/wifi-connect
```

### UI Development (React)
```bash
# Navigate to UI directory
cd ui/

# Install dependencies
npm install

# Development server
npm start

# Build production UI
npm run build

# Lint the UI code
npm run lint
```

### Cross-compilation for ARM/Other Architectures
```bash
# Use the local build script with target architecture
./scripts/local-build.sh <target> <arch>
# Example: ./scripts/local-build.sh armv7-unknown-linux-gnueabihf armv7
```

## Architecture

### Core Components

1. **main.rs**: Entry point handling command-line arguments and orchestrating the main workflow
   - Manages hotspot lifecycle (start/stop/check/restart)
   - Handles network connection management
   - Routes between different operational modes

2. **config.rs**: Configuration management via CLI arguments and environment variables
   - Default gateway: 192.168.42.1
   - Default DHCP range: 192.168.42.2-254
   - Default SSID: "WiFi Connect"
   - Supports hotspot management flags and DHCP configuration options

3. **hotspot_manager.rs**: Manages the WiFi access point creation and lifecycle
   - Creates and manages the captive portal hotspot
   - Handles AP isolation and DHCP configuration

4. **network.rs**: NetworkManager integration for WiFi operations
   - Scanning for available networks
   - Managing WiFi connections
   - Forgetting saved networks

5. **server.rs**: Iron-based HTTP server for the captive portal
   - Serves the React UI from `ui/build/`
   - Handles API endpoints for network operations
   - CORS enabled for cross-origin requests

6. **dnsmasq.rs**: DNS and DHCP server configuration for the captive portal
   - Configures DHCP options based on mode (standard vs WiFi Direct)
   - Manages DNS redirection for captive portal

### UI Architecture

The UI is a React application using:
- TypeScript for type safety
- Rendition component library (Balena's UI framework)
- Static build served by the Rust server

### Operational Modes

1. **Standard Mode**: Traditional captive portal for WiFi configuration
2. **WiFi Direct Mode**: CarPlay/Android Auto style direct connection
   - Bypasses certain DHCP options for compatibility
   - Maintains persistent connection without internet gateway

### Key Scripts

- **start.sh**: Main entry script for balenaOS deployments
  - Checks connectivity before starting WiFi Connect
  - Manages WiFi Direct mode configuration
  - Launches Python API server alongside main application

- **api.py**: REST API server for external control
  - Runs on port 8080
  - Provides programmatic control over WiFi Connect

## Important Notes

- The application requires root privileges to manage NetworkManager
- NetworkManager dependency is from a custom fork: `https://github.com/Moses3301/network-manager.git`
- The UI build output must be in `ui/build/` for the server to serve it correctly
- Environment variables can override all command-line arguments (prefix with `PORTAL_`)
- The application uses Iron web framework (0.6) which is older but stable
- DBUS system bus access is required for NetworkManager communication