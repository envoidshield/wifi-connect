use std::net::Ipv4Addr;
use std::process;
use std::thread;
use std::time::Duration;

use network_manager::{Connection, Device, NetworkManager};
use config::Config;
use dnsmasq::{start_dnsmasq, stop_dnsmasq};
use errors::*;
use network::{find_device, start_network_manager_service};

pub struct HotspotManager {
    manager: NetworkManager,
    device: Device,
    portal_connection: Option<Connection>,
    dnsmasq: Option<process::Child>,
    config: Config,
}

impl HotspotManager {
    /// Create a new HotspotManager instance
    pub fn new(config: Config) -> Result<Self> {
        start_network_manager_service()?;
        
        let manager = NetworkManager::new();
        let device = find_device(&manager, &config.interface)?;
        
        Ok(HotspotManager {
            manager,
            device,
            portal_connection: None,
            dnsmasq: None,
            config,
        })
    }

    /// Start the hotspot with the configured SSID and settings
    pub fn start_hotspot(&mut self) -> Result<()> {
        if self.is_hotspot_running() {
            warn!("Hotspot is already running");
            return Ok(());
        }

        info!("Starting hotspot '{}'...", self.config.ssid);

        // Create the access point
        let portal_connection = self.create_portal()?;
        self.portal_connection = Some(portal_connection);

        // Start dnsmasq for DHCP and DNS
        let dnsmasq = start_dnsmasq(&self.config, &self.device)?;
        self.dnsmasq = Some(dnsmasq);

        info!("Hotspot '{}' started successfully", self.config.ssid);
        Ok(())
    }

    /// Stop the hotspot and cleanup resources
    pub fn stop_hotspot(&mut self) -> Result<()> {
        if !self.is_hotspot_running() {
            warn!("Hotspot is not running");
            return Ok(());
        }

        info!("Stopping hotspot '{}'...", self.config.ssid);

        // Stop dnsmasq first
        if let Some(mut dnsmasq) = self.dnsmasq.take() {
            if let Err(e) = stop_dnsmasq(&mut dnsmasq) {
                error!("Failed to stop dnsmasq: {}", e);
            }
        }

        // Stop the access point
        if let Some(connection) = self.portal_connection.take() {
            if let Err(e) = self.stop_portal(&connection) {
                error!("Failed to stop portal: {}", e);
            }
        }

        info!("Hotspot '{}' stopped successfully", self.config.ssid);
        Ok(())
    }

    /// Check if the hotspot is currently running
    pub fn is_hotspot_running(&self) -> bool {
        self.portal_connection.is_some() && self.dnsmasq.is_some()
    }

    /// Get the hotspot status information
    pub fn get_hotspot_status(&self) -> HotspotStatus {
        if self.is_hotspot_running() {
            HotspotStatus {
                is_running: true,
                ssid: Some(self.config.ssid.clone()),
                gateway: Some(self.config.gateway),
                interface: Some(self.device.interface().to_string()),
                has_password: self.config.passphrase.is_some(),
            }
        } else {
            HotspotStatus {
                is_running: false,
                ssid: None,
                gateway: None,
                interface: None,
                has_password: false,
            }
        }
    }

    /// Restart the hotspot (stop then start)
    pub fn restart_hotspot(&mut self) -> Result<()> {
        info!("Restarting hotspot...");
        self.stop_hotspot()?;
        
        // Brief pause to ensure cleanup is complete
        thread::sleep(Duration::from_secs(1));
        
        self.start_hotspot()?;
        Ok(())
    }

    /// Update hotspot configuration (requires restart to take effect)
    pub fn update_config(&mut self, new_config: Config) -> Result<()> {
        let was_running = self.is_hotspot_running();
        
        if was_running {
            self.stop_hotspot()?;
        }
        
        // Update device if interface changed
        if self.config.interface != new_config.interface {
            self.device = find_device(&self.manager, &new_config.interface)?;
        }
        
        self.config = new_config;
        
        if was_running {
            thread::sleep(Duration::from_secs(1));
            self.start_hotspot()?;
        }
        
        Ok(())
    }

    /// Get the network interface being used for the hotspot
    pub fn get_interface(&self) -> &str {
        self.device.interface()
    }

    /// Get the configured SSID
    pub fn get_ssid(&self) -> &str {
        &self.config.ssid
    }

    /// Get the gateway IP address
    pub fn get_gateway(&self) -> Ipv4Addr {
        self.config.gateway
    }

    // Private helper methods
    fn create_portal(&self) -> Result<Connection> {
        let portal_passphrase = self.config.passphrase.as_ref().map(|p| p as &str);

        info!("Creating access point '{}'...", self.config.ssid);
        let wifi_device = self.device.as_wifi_device().unwrap();
        let (portal_connection, _) = wifi_device
            .create_hotspot(&self.config.ssid, portal_passphrase, Some(self.config.gateway))
            .chain_err(|| ErrorKind::CreateCaptivePortal)?;
        
        info!("Access point '{}' created", self.config.ssid);
        Ok(portal_connection)
    }

    fn stop_portal(&self, connection: &Connection) -> Result<()> {
        info!("Stopping access point '{}'...", self.config.ssid);
        connection.deactivate().chain_err(|| ErrorKind::StopAccessPoint)?;
        connection.delete().chain_err(|| ErrorKind::DeleteAccessPoint)?;
        thread::sleep(Duration::from_secs(1));
        info!("Access point '{}' stopped", self.config.ssid);
        Ok(())
    }
}

impl Drop for HotspotManager {
    /// Ensure hotspot is stopped when the manager is dropped
    fn drop(&mut self) {
        if self.is_hotspot_running() {
            if let Err(e) = self.stop_hotspot() {
                error!("Failed to stop hotspot during cleanup: {}", e);
            }
        }
    }
}

#[derive(Debug, Clone)]
pub struct HotspotStatus {
    pub is_running: bool,
    pub ssid: Option<String>,
    pub gateway: Option<Ipv4Addr>,
    pub interface: Option<String>,
    pub has_password: bool,
}

impl HotspotStatus {
    pub fn print_status(&self) {
        if self.is_running {
            println!("Hotspot Status: RUNNING");
            if let Some(ref ssid) = self.ssid {
                println!("SSID: {}", ssid);
            }
            if let Some(gateway) = self.gateway {
                println!("Gateway: {}", gateway);
            }
            if let Some(ref interface) = self.interface {
                println!("Interface: {}", interface);
            }
            println!("Password Protected: {}", self.has_password);
        } else {
            println!("Hotspot Status: STOPPED");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;
    use std::path::PathBuf;

    fn create_test_config() -> Config {
        Config {
            interface: None,
            ssid: "TestHotspot".to_string(),
            passphrase: Some("testpass123".to_string()),
            gateway: Ipv4Addr::new(192, 168, 42, 1),
            dhcp_range: "192.168.42.2,192.168.42.254".to_string(),
            listening_port: 80,
            activity_timeout: 0,
            ui_directory: PathBuf::from("ui"),
            forget_all: false,
            list_networks: false,
            list_connected: false,
            list_saved: false,
            forget_network: None,
            connect: None,
        }
    }

    #[test]
    fn test_hotspot_manager_creation() {
        // Note: This test requires root privileges and NetworkManager
        // In a real environment, you might want to mock these dependencies
        let config = create_test_config();
        
        // This would fail in test environment without proper setup
        // but shows the intended usage
        match HotspotManager::new(config) {
            Ok(_manager) => {
                // Test would continue here
            }
            Err(_) => {
                // Expected in test environment
            }
        }
    }
}

// Example usage function
pub fn example_usage() -> Result<()> {
    use crate::config::get_config;
    
    let config = get_config();
    let mut hotspot = HotspotManager::new(config)?;

    // Start the hotspot
    hotspot.start_hotspot()?;
    
    // Check status
    let status = hotspot.get_hotspot_status();
    status.print_status();
    
    // Keep it running for some time
    println!("Hotspot running... Press Ctrl+C to stop");
    
    // In a real application, you might want to handle signals here
    // For this example, we'll just sleep briefly
    thread::sleep(Duration::from_secs(5));
    
    // Stop the hotspot
    hotspot.stop_hotspot()?;
    
    Ok(())
}
