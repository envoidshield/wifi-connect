use std::fs;
use std::io::Write;
use std::net::Ipv4Addr;
use std::path::{Path, PathBuf};
use std::process::{self, Command};
use std::thread;
use std::time::Duration;

use network_manager::{Connection, Device, NetworkManager};

use config::Config;
use dnsmasq::{start_dnsmasq, stop_dnsmasq};
use errors::*;
use network::{find_device, start_network_manager_service};

const STATE_FILE_PATH: &str = "/tmp/wificonnect_hotspot.state";
const DNSMASQ_PID_FILE: &str = "/tmp/wificonnect_dnsmasq.pid";

// Simple state representation using a text format instead of JSON
// Format: "running|ssid|gateway|interface|has_password|dnsmasq_pid|started_at"
pub struct HotspotState {
    pub is_running: bool,
    pub ssid: String,
    pub gateway: Ipv4Addr,
    pub interface: String,
    pub has_password: bool,
    pub dnsmasq_pid: Option<u32>,
    pub started_at: u64, // Unix timestamp
}

impl HotspotState {
    fn to_string(&self) -> String {
        format!(
            "{}|{}|{}|{}|{}|{}|{}",
            if self.is_running { "1" } else { "0" },
            self.ssid,
            self.gateway,
            self.interface,
            if self.has_password { "1" } else { "0" },
            self.dnsmasq_pid.map_or("0".to_string(), |p| p.to_string()),
            self.started_at
        )
    }

    fn from_string(s: &str) -> Result<Self> {
        let parts: Vec<&str> = s.trim().split('|').collect();
        if parts.len() != 7 {
            return Err("Invalid state format".into());
        }

        let gateway = parts[2].parse::<Ipv4Addr>()
            .chain_err(|| "Invalid gateway IP")?;
        
        let dnsmasq_pid = if parts[5] == "0" {
            None
        } else {
            Some(parts[5].parse::<u32>().chain_err(|| "Invalid dnsmasq PID")?)
        };

        let started_at = parts[6].parse::<u64>()
            .chain_err(|| "Invalid timestamp")?;

        Ok(HotspotState {
            is_running: parts[0] == "1",
            ssid: parts[1].to_string(),
            gateway,
            interface: parts[3].to_string(),
            has_password: parts[4] == "1",
            dnsmasq_pid,
            started_at,
        })
    }
}

pub struct HotspotManager {
    manager: NetworkManager,
    device: Device,
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
            config,
        })
    }

    /// Start the hotspot with the configured SSID and settings
    pub fn start_hotspot(&mut self) -> Result<()> {
        // Check if hotspot is already running
        if let Ok(state) = self.load_state() {
            if state.is_running && self.verify_hotspot_running(&state) {
                warn!("Hotspot '{}' is already running", state.ssid);
                return Ok(());
            }
        }

        info!("Starting hotspot '{}'...", self.config.ssid);

        // Stop any existing hotspot first
        let _ = self.stop_hotspot_internal();

        // Create the access point
        let _portal_connection = self.create_portal()?;

        // Start dnsmasq for DHCP and DNS
        let dnsmasq = start_dnsmasq(&self.config, &self.device)?;
        let dnsmasq_pid = dnsmasq.id();

        // Save dnsmasq PID to file for later cleanup
        self.save_dnsmasq_pid(dnsmasq_pid)?;

        // Create and save state
        let state = HotspotState {
            is_running: true,
            ssid: self.config.ssid.clone(),
            gateway: self.config.gateway,
            interface: self.device.interface().to_string(),
            has_password: self.config.passphrase.is_some(),
            dnsmasq_pid: Some(dnsmasq_pid),
            started_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        };

        self.save_state(&state)?;

        // Detach dnsmasq process - let it run in background
        std::mem::forget(dnsmasq);

        info!("Hotspot '{}' started successfully", self.config.ssid);
        Ok(())
    }

    /// Stop the hotspot and cleanup resources
    pub fn stop_hotspot(&mut self) -> Result<()> {
        self.stop_hotspot_internal()
    }

    fn stop_hotspot_internal(&mut self) -> Result<()> {
        let state = match self.load_state() {
            Ok(state) if state.is_running => state,
            Ok(_) => {
                info!("Hotspot is not running according to state file");
                return Ok(());
            }
            Err(_) => {
                info!("No hotspot state found");
                return Ok(());
            }
        };

        info!("Stopping hotspot '{}'...", state.ssid);

        // Stop dnsmasq first
        if let Some(pid) = state.dnsmasq_pid {
            self.stop_dnsmasq_by_pid(pid)?;
        }

        // Stop the access point connection by finding and deleting hotspot connections
        self.stop_all_hotspot_connections(&state.ssid)?;

        // Clean up state files
        self.cleanup_state_files();

        info!("Hotspot '{}' stopped successfully", state.ssid);
        Ok(())
    }

    /// Check if the hotspot is currently running
    pub fn is_hotspot_running(&self) -> bool {
        match self.load_state() {
            Ok(state) => state.is_running && self.verify_hotspot_running(&state),
            Err(_) => false,
        }
    }

    /// Get the hotspot status information
    pub fn get_hotspot_status(&self) -> HotspotStatus {
        match self.load_state() {
            Ok(state) if state.is_running => {
                let actually_running = self.verify_hotspot_running(&state);
                
                if !actually_running {
                    // Clean up stale state
                    let _ = self.cleanup_state_files();
                    return HotspotStatus {
                        is_running: false,
                        ssid: None,
                        gateway: None,
                        interface: None,
                        has_password: false,
                        uptime_seconds: None,
                    };
                }

                let uptime = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs() - state.started_at;

                HotspotStatus {
                    is_running: true,
                    ssid: Some(state.ssid),
                    gateway: Some(state.gateway),
                    interface: Some(state.interface),
                    has_password: state.has_password,
                    uptime_seconds: Some(uptime),
                }
            }
            _ => HotspotStatus {
                is_running: false,
                ssid: None,
                gateway: None,
                interface: None,
                has_password: false,
                uptime_seconds: None,
            },
        }
    }

    /// Restart the hotspot (stop then start)
    pub fn restart_hotspot(&mut self) -> Result<()> {
        info!("Restarting hotspot...");
        self.stop_hotspot_internal()?;
        
        // Brief pause to ensure cleanup is complete
        thread::sleep(Duration::from_secs(2));
        
        self.start_hotspot()?;
        Ok(())
    }

    // Private helper methods
    fn create_portal(&self) -> Result<Connection> {
        let portal_passphrase = self.config.passphrase.as_ref().map(|p| p as &str);

        info!("Creating access point '{}'...", self.config.ssid);
        let wifi_device = self.device.as_wifi_device().unwrap();
        let (portal_connection, _) = wifi_device
            .create_hotspot(self.config.ssid.as_str(), portal_passphrase, Some(self.config.gateway))
            .chain_err(|| ErrorKind::CreateCaptivePortal)?;
        
        info!("Access point '{}' created", self.config.ssid);
        Ok(portal_connection)
    }

    fn stop_all_hotspot_connections(&self, ssid: &str) -> Result<()> {
        info!("Stopping all hotspot connections for SSID '{}'...", ssid);
        
        // Get all connections and find hotspot/AP connections with matching SSID
        let connections = self.manager.get_connections()?;
        let mut found_any = false;
        
        for connection in connections {
            let settings = connection.settings();
            
            // Check if this is an access point connection with our SSID
            if settings.kind == "802-11-wireless" && settings.mode == "ap" {
                if let Ok(conn_ssid) = settings.ssid.as_str() {
                    if conn_ssid == ssid {
                        info!("Stopping access point connection: {}", conn_ssid);
                        
                        // Try to deactivate first, then delete
                        if let Err(e) = connection.deactivate() {
                            warn!("Failed to deactivate connection: {}", e);
                        }
                        
                        if let Err(e) = connection.delete() {
                            warn!("Failed to delete connection: {}", e);
                        } else {
                            found_any = true;
                        }
                    }
                }
            }
        }
        
        if !found_any {
            warn!("No active hotspot connections found for SSID '{}'", ssid);
        }
        
        Ok(())
    }

    fn stop_dnsmasq_by_pid(&self, pid: u32) -> Result<()> {
        info!("Stopping dnsmasq with PID {}...", pid);
        
        // Try to kill the process gracefully first
        let output = Command::new("kill")
            .arg(pid.to_string())
            .output();
            
        match output {
            Ok(output) if output.status.success() => {
                info!("Dnsmasq stopped gracefully");
            }
            _ => {
                warn!("Failed to stop dnsmasq gracefully, trying force kill");
                let _ = Command::new("kill")
                    .arg("-9")
                    .arg(pid.to_string())
                    .output();
            }
        }
        
        // Clean up PID file
        let _ = fs::remove_file(DNSMASQ_PID_FILE);
        
        Ok(())
    }

    fn save_state(&self, state: &HotspotState) -> Result<()> {
        let state_string = state.to_string();
        
        fs::write(STATE_FILE_PATH, state_string)
            .chain_err(|| "Failed to write hotspot state file")?;
        
        debug!("Hotspot state saved to {}", STATE_FILE_PATH);
        Ok(())
    }

    fn load_state(&self) -> Result<HotspotState> {
        let content = fs::read_to_string(STATE_FILE_PATH)
            .chain_err(|| "Failed to read hotspot state file")?;
        
        HotspotState::from_string(&content)
    }

    fn save_dnsmasq_pid(&self, pid: u32) -> Result<()> {
        fs::write(DNSMASQ_PID_FILE, pid.to_string())
            .chain_err(|| "Failed to write dnsmasq PID file")?;
        Ok(())
    }

    fn cleanup_state_files(&self) {
        let _ = fs::remove_file(STATE_FILE_PATH);
        let _ = fs::remove_file(DNSMASQ_PID_FILE);
        debug!("Cleaned up state files");
    }

    fn verify_hotspot_running(&self, state: &HotspotState) -> bool {
        // Check if dnsmasq process is still running
        if let Some(pid) = state.dnsmasq_pid {
            let output = Command::new("kill")
                .arg("-0") // Check if process exists without killing it
                .arg(pid.to_string())
                .output();
                
            match output {
                Ok(output) if !output.status.success() => {
                    debug!("Dnsmasq process {} is not running", pid);
                    return false;
                }
                Err(_) => {
                    debug!("Failed to check dnsmasq process {}", pid);
                    return false;
                }
                _ => {} // Process is running
            }
        }

        // Check if any hotspot connections exist for our SSID
        match self.manager.get_connections() {
            Ok(connections) => {
                let hotspot_exists = connections.iter().any(|conn| {
                    let settings = conn.settings();
                    settings.kind == "802-11-wireless" 
                        && settings.mode == "ap"
                        && settings.ssid.as_str().map_or(false, |ssid| ssid == state.ssid)
                });
                
                if !hotspot_exists {
                    debug!("No hotspot connection found for SSID '{}'", state.ssid);
                    return false;
                }
            }
            Err(_) => {
                debug!("Failed to check connections");
                return false;
            }
        }

        true
    }
}


#[derive(Debug, Clone)]
pub struct HotspotStatus {
    pub is_running: bool,
    pub ssid: Option<String>,
    pub gateway: Option<Ipv4Addr>,
    pub interface: Option<String>,
    pub has_password: bool,
    pub uptime_seconds: Option<u64>,
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
            if let Some(uptime) = self.uptime_seconds {
                let hours = uptime / 3600;
                let minutes = (uptime % 3600) / 60;
                let seconds = uptime % 60;
                println!("Uptime: {:02}:{:02}:{:02}", hours, minutes, seconds);
            }
        } else {
            println!("Hotspot Status: STOPPED");
        }
    }
}

// Utility functions for external use
pub fn is_any_hotspot_running() -> bool {
    match fs::read_to_string(STATE_FILE_PATH) {
        Ok(content) => {
            match HotspotState::from_string(&content) {
                Ok(state) if state.is_running => {
                    // Quick verification without full manager
                    verify_processes_running(&state)
                }
                _ => false,
            }
        }
        Err(_) => false,
    }
}

pub fn get_hotspot_status_quick() -> Option<HotspotStatus> {
    match fs::read_to_string(STATE_FILE_PATH) {
        Ok(content) => {
            match HotspotState::from_string(&content) {
                Ok(state) if state.is_running => {
                    let actually_running = verify_processes_running(&state);
                    
                    if !actually_running {
                        // Clean up stale state
                        let _ = fs::remove_file(STATE_FILE_PATH);
                        return Some(HotspotStatus {
                            is_running: false,
                            ssid: None,
                            gateway: None,
                            interface: None,
                            has_password: false,
                            uptime_seconds: None,
                        });
                    }

                    let uptime = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap()
                        .as_secs() - state.started_at;

                    Some(HotspotStatus {
                        is_running: true,
                        ssid: Some(state.ssid),
                        gateway: Some(state.gateway),
                        interface: Some(state.interface),
                        has_password: state.has_password,
                        uptime_seconds: Some(uptime),
                    })
                }
                _ => Some(HotspotStatus {
                    is_running: false,
                    ssid: None,
                    gateway: None,
                    interface: None,
                    has_password: false,
                    uptime_seconds: None,
                }),
            }
        }
        Err(_) => Some(HotspotStatus {
            is_running: false,
            ssid: None,
            gateway: None,
            interface: None,
            has_password: false,
            uptime_seconds: None,
        }),
    }
}

fn verify_processes_running(state: &HotspotState) -> bool {
    if let Some(pid) = state.dnsmasq_pid {
        let output = Command::new("kill")
            .arg("-0")
            .arg(pid.to_string())
            .output();
            
        match output {
            Ok(output) if output.status.success() => true,
            _ => false,
        }
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;

    #[test]
    fn test_state_serialization() {
        let state = HotspotState {
            is_running: true,
            ssid: "TestAP".to_string(),
            gateway: Ipv4Addr::new(192, 168, 1, 1),
            interface: "wlan0".to_string(),
            has_password: true,
            dnsmasq_pid: Some(12345),
            started_at: 1234567890,
        };

        let state_string = state.to_string();
        let deserialized = HotspotState::from_string(&state_string).unwrap();
        
        assert_eq!(state.ssid, deserialized.ssid);
        assert_eq!(state.is_running, deserialized.is_running);
        assert_eq!(state.gateway, deserialized.gateway);
        assert_eq!(state.dnsmasq_pid, deserialized.dnsmasq_pid);
    }

    #[test]
    fn test_state_format() {
        let state = HotspotState {
            is_running: true,
            ssid: "TestNetwork".to_string(),
            gateway: Ipv4Addr::new(192, 168, 42, 1),
            interface: "wlan0".to_string(),
            has_password: false,
            dnsmasq_pid: None,
            started_at: 1640995200,
        };

        let expected = "1|TestNetwork|192.168.42.1|wlan0|0|0|1640995200";
        assert_eq!(state.to_string(), expected);
        
        let parsed = HotspotState::from_string(expected).unwrap();
        assert_eq!(parsed.is_running, true);
        assert_eq!(parsed.ssid, "TestNetwork");
        assert_eq!(parsed.has_password, false);
        assert_eq!(parsed.dnsmasq_pid, None);
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
    thread::sleep(Duration::from_secs(5));
    
    // Stop the hotspot
    hotspot.stop_hotspot()?;
    
    Ok(())
}
