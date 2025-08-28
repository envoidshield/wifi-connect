#!/usr/bin/env python3
"""
WiFi API Configuration Utility
Helps manage configuration settings
"""

import argparse
import sys
from config import get_config, create_default_config

def show_config():
    """Show current configuration"""
    config = get_config()
    config.print_config()

def set_config_value(key: str, value: str):
    """Set a configuration value"""
    config = get_config()
    
    # Parse the key (e.g., "server.port" -> ["server", "port"])
    keys = key.split('.')
    
    # Navigate to the nested location
    current = config._config
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    
    # Set the value with type conversion
    key_name = keys[-1]
    if key_name in ["port", "scan_timeout", "rescan_delay"]:
        try:
            current[key_name] = int(value)
        except ValueError:
            print(f"Error: {value} is not a valid integer for {key}")
            return False
    elif key_name == "enabled":
        current[key_name] = value.lower() in ["true", "1", "yes", "on"]
    elif key_name == "origins":
        current[key_name] = [origin.strip() for origin in value.split(",")]
    else:
        current[key_name] = value
    
    # Save the configuration
    if config.save_config():
        print(f"Configuration updated: {key} = {value}")
        return True
    else:
        print("Error: Failed to save configuration")
        return False

def main():
    parser = argparse.ArgumentParser(description="WiFi API Configuration Utility")
    parser.add_argument("action", choices=["show", "set", "create"], 
                       help="Action to perform")
    parser.add_argument("--key", help="Configuration key (for set action)")
    parser.add_argument("--value", help="Configuration value (for set action)")
    parser.add_argument("--config-file", default="wifi_config.json",
                       help="Configuration file path")
    
    args = parser.parse_args()
    
    if args.action == "show":
        show_config()
    elif args.action == "set":
        if not args.key or not args.value:
            print("Error: --key and --value are required for set action")
            sys.exit(1)
        if not set_config_value(args.key, args.value):
            sys.exit(1)
    elif args.action == "create":
        if create_default_config(args.config_file):
            print(f"Default configuration created: {args.config_file}")
        else:
            print("Error: Failed to create configuration file")
            sys.exit(1)

if __name__ == "__main__":
    main()
