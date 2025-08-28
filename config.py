#!/usr/bin/env python3
"""
Minimal configuration system for WiFi Connect API Server
Supports environment variables and config file
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

class Config:
    """Minimal configuration class for WiFi API Server"""
    
    def __init__(self, config_file: str = "wifi_config.json"):
        self.config_file = Path(config_file)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file and environment variables"""
        # Default configuration
        default_config = {
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
                "enabled": True,
                "origins": ["*"]
            }
        }
        
        # Load from config file if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    # Merge with defaults
                    self._merge_config(default_config, file_config)
            except Exception as e:
                print(f"Warning: Could not load config file {self.config_file}: {e}")
        
        # Override with environment variables
        self._load_env_vars(default_config)
        
        return default_config
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]):
        """Recursively merge configuration dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _load_env_vars(self, config: Dict[str, Any]):
        """Load configuration from environment variables"""
        env_mappings = {
            "WIFI_SERVER_HOST": ("server", "host"),
            "WIFI_SERVER_PORT": ("server", "port"),
            "WIFI_SERVER_LOG_LEVEL": ("server", "log_level"),
            "WIFI_HOTSPOT_NAME_PREFIX": ("wifi", "hotspot_name_prefix"),
            "WIFI_HOTSPOT_PASSWORD": ("wifi", "hotspot_password"),
            "WIFI_SCAN_TIMEOUT": ("wifi", "scan_timeout"),
            "WIFI_RESCAN_DELAY": ("wifi", "rescan_delay"),
            "WIFI_CORS_ENABLED": ("cors", "enabled"),
            "WIFI_CORS_ORIGINS": ("cors", "origins")
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Navigate to the nested config location
                current = config
                for key in config_path[:-1]:
                    current = current[key]
                
                # Convert value based on expected type
                key = config_path[-1]
                if key in ["port", "scan_timeout", "rescan_delay"]:
                    try:
                        current[key] = int(value)
                    except ValueError:
                        print(f"Warning: Invalid integer value for {env_var}: {value}")
                elif key == "enabled":
                    current[key] = value.lower() in ["true", "1", "yes", "on"]
                elif key == "origins":
                    current[key] = [origin.strip() for origin in value.split(",")]
                else:
                    current[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self._config["server"]
    
    def get_wifi_config(self) -> Dict[str, Any]:
        """Get WiFi configuration"""
        return self._config["wifi"]
    
    def get_cors_config(self) -> Dict[str, Any]:
        """Get CORS configuration"""
        return self._config["cors"]
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def print_config(self):
        """Print current configuration"""
        print("Current Configuration:")
        print(json.dumps(self._config, indent=2))

# Global config instance
_config_instance: Optional[Config] = None

def get_config(config_file: str = "wifi_config.json") -> Config:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_file)
    return _config_instance

def create_default_config(config_file: str = "wifi_config.json") -> bool:
    """Create a default configuration file"""
    config = Config(config_file)
    return config.save_config()

if __name__ == "__main__":
    # Create default config file
    if create_default_config():
        print("Default configuration file created: wifi_config.json")
        config = get_config()
        config.print_config()
    else:
        print("Failed to create configuration file")
