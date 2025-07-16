use std::thread;
use std::time::Duration;

use network_manager::{Device, NetworkManager};

use config::Config;
use dnsmasq::start_dnsmasq;
use errors::*;
use network::find_device;

#[derive(Debug)]
pub struct HotspotStatus {
    pub is_running: bool,
    pub ssid: Option<String>,
    pub gateway: Option<String>,
    pub interface: Option<String>,
    pub password_protected: bool,
    pub uptime: Option<String>,
}

impl HotspotStatus {
    pub fn print_status(&self) {
        if self.is_running {
            println!("Hotspot Status: RUNNING");
            if let Some(ref ssid) = self.ssid {
                println!("SSID: {}", ssid);
            }
            if let Some(ref gateway) = self.gateway {
                println!("Gateway: {}", gateway);
            }
            if let Some(ref interface) = self.interface {
                println!("Interface: {}", interface);
            }
            println!("Password Protected: {}", self.password_protected);
            if let Some(ref uptime) = self.uptime {
                println!("Uptime: {}", uptime);
            }
        } else {
            println!("Hotspot Status: STOPPED");
        }
    }
}

pub struct HotspotManager {
    config: Config,
    manager: NetworkManager,
    device: Device,
    dnsmasq_process: Option<std::process::Child>,
}

impl HotspotManager {
    pub fn new(config: Config) -> Result<Self> {
        let manager = NetworkManager::new();
        let device = find_device(&manager, &config.interface)?;

        Ok(HotspotManager {
            config,
            manager,
            device,
            dnsmasq_process: None,
        })
    }

    pub fn start_hotspot(&mut self) -> Result<()> {
        info!("Starting hotspot '{}'...", self.config.ssid);

        // Stop any existing hotspot first
        if self.is_hotspot_running() {
            self.stop_hotspot()?;
            thread::sleep(Duration::from_secs(2));
        }

        // Create the access point using NetworkManager
        let wifi_device = self.device.as_wifi_device().unwrap();
        let passphrase = self.config.passphrase.as_ref().map(|p| p.as_str());
        
        let (_connection, _state) = wifi_device.create_hotspot(
            self.config.ssid.as_str(),
            passphrase,
            Some(self.config.gateway),
        )?;

        // Start dnsmasq for DHCP
        let dnsmasq = start_dnsmasq(&self.config, &self.device)?;
        self.dnsmasq_process = Some(dnsmasq);

        info!("Hotspot '{}' started successfully", self.config.ssid);
        Ok(())
    }

    pub fn stop_hotspot(&mut self) -> Result<()> {
        info!("Stopping hotspot...");

        // Stop dnsmasq if running
        if let Some(mut dnsmasq) = self.dnsmasq_process.take() {
            let _ = dnsmasq.kill();
            let _ = dnsmasq.wait();
        }

        // Find and deactivate any active hotspot connections
        let connections = self.manager.get_connections()?;
        for connection in connections {
            let settings = connection.settings();
            if settings.kind == "802-11-wireless" 
                && settings.mode == "ap" 
                && settings.ssid.as_str().unwrap_or("") == self.config.ssid {
                info!("Deactivating hotspot connection");
                let _ = connection.deactivate();
                let _ = connection.delete();
            }
        }

        info!("Hotspot stopped");
        Ok(())
    }

    pub fn restart_hotspot(&mut self) -> Result<()> {
        info!("Restarting hotspot...");
        self.stop_hotspot()?;
        thread::sleep(Duration::from_secs(2));
        self.start_hotspot()?;
        info!("Hotspot restarted");
        Ok(())
    }

    pub fn is_hotspot_running(&self) -> bool {
        // Check if there's an active access point connection with our SSID
        if let Ok(connections) = self.manager.get_connections() {
            for connection in connections {
                let settings = connection.settings();
                if settings.kind == "802-11-wireless" 
                    && settings.mode == "ap" 
                    && settings.ssid.as_str().unwrap_or("") == self.config.ssid {
                    if let Ok(state) = connection.get_state() {
                        return state == network_manager::ConnectionState::Activated;
                    }
                }
            }
        }
        false
    }

    pub fn get_hotspot_status(&self) -> HotspotStatus {
        let is_running = self.is_hotspot_running();
        
        if is_running {
            HotspotStatus {
                is_running: true,
                ssid: Some(self.config.ssid.clone()),
                gateway: Some(self.config.gateway.to_string()),
                interface: Some(self.device.interface().to_string()),
                password_protected: self.config.passphrase.is_some(),
                uptime: None, // Could be implemented by tracking start time
            }
        } else {
            HotspotStatus {
                is_running: false,
                ssid: None,
                gateway: None,
                interface: None,
                password_protected: false,
                uptime: None,
            }
        }
    }
}

impl Drop for HotspotManager {
    fn drop(&mut self) {
        // Ensure cleanup when the manager is dropped
        if let Some(mut dnsmasq) = self.dnsmasq_process.take() {
            let _ = dnsmasq.kill();
            let _ = dnsmasq.wait();
        }
    }
}