use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader, Write};
use std::thread;
use std::time::Duration;
use std::net::Ipv4Addr;

use config::Config;
use errors::*;

pub struct WiFiDirectManager {
    interface: String,
    ssid: String,
    passphrase: Option<String>,
    gateway: Ipv4Addr,
}

impl WiFiDirectManager {
    pub fn new(interface: String, config: &Config) -> Self {
        WiFiDirectManager {
            interface,
            ssid: config.ssid.clone(),
            passphrase: config.passphrase.clone(),
            gateway: config.gateway,
        }
    }

    pub fn start_wifi_direct_group(&self) -> Result<()> {
        info!("Starting WiFi Direct (P2P) group...");
        
        // First, ensure wpa_supplicant is running with P2P support
        self.ensure_wpa_supplicant_p2p()?;
        
        // Create P2P group
        self.create_p2p_group()?;
        
        // Configure IP address for the P2P interface
        self.configure_p2p_interface()?;
        
        info!("WiFi Direct group '{}' created successfully", self.ssid);
        Ok(())
    }

    pub fn stop_wifi_direct_group(&self) -> Result<()> {
        info!("Stopping WiFi Direct group...");
        
        // Remove P2P group
        let output = Command::new("wpa_cli")
            .args(&["-i", &self.interface, "p2p_group_remove", "p2p-wlan0-0"])
            .output()
            .chain_err(|| "Failed to execute wpa_cli p2p_group_remove")?;

        if !output.status.success() {
            warn!("Failed to remove P2P group: {}", String::from_utf8_lossy(&output.stderr));
        }

        info!("WiFi Direct group stopped");
        Ok(())
    }

    fn ensure_wpa_supplicant_p2p(&self) -> Result<()> {
        // Check if P2P device exists
        let output = Command::new("iw")
            .args(&["dev"])
            .output()
            .chain_err(|| "Failed to execute iw dev")?;

        let output_str = String::from_utf8_lossy(&output.stdout);
        if !output_str.contains("type P2P-device") {
            return Err("No P2P device found. Ensure wpa_supplicant is running with P2P support".into());
        }

        Ok(())
    }

    fn create_p2p_group(&self) -> Result<()> {
        // Set device name for P2P
        let device_name = format!("DIRECT-{}", &self.ssid);
        let mut cmd = Command::new("wpa_cli")
            .args(&["-i", &self.interface, "set", "device_name", &device_name])
            .spawn()
            .chain_err(|| "Failed to set P2P device name")?;
        cmd.wait().chain_err(|| "Failed to wait for wpa_cli")?;

        // Set P2P GO intent to maximum (15) to ensure we become Group Owner
        let mut cmd = Command::new("wpa_cli")
            .args(&["-i", &self.interface, "set", "p2p_go_intent", "15"])
            .spawn()
            .chain_err(|| "Failed to set P2P GO intent")?;
        cmd.wait().chain_err(|| "Failed to wait for wpa_cli")?;

        // Create autonomous P2P group
        let freq_arg = "freq=2412"; // Use 2.4GHz channel 1 for better compatibility
        let mut cmd = Command::new("wpa_cli")
            .args(&["-i", &self.interface, "p2p_group_add", freq_arg])
            .spawn()
            .chain_err(|| "Failed to create P2P group")?;
        cmd.wait().chain_err(|| "Failed to wait for wpa_cli")?;

        // Wait for group to be created
        thread::sleep(Duration::from_secs(3));

        // If we have a passphrase, set up WPS with PIN
        if let Some(ref passphrase) = self.passphrase {
            self.setup_wps_pin(passphrase)?;
        } else {
            // Enable WPS PBC (Push Button Configuration)
            self.setup_wps_pbc()?;
        }

        Ok(())
    }

    fn setup_wps_pin(&self, pin: &str) -> Result<()> {
        info!("Setting up WPS PIN authentication");
        
        // Set WPS PIN on the P2P group interface
        let mut cmd = Command::new("wpa_cli")
            .args(&["-i", "p2p-wlan0-0", "wps_pin", "any", pin])
            .spawn()
            .chain_err(|| "Failed to set WPS PIN")?;
        cmd.wait().chain_err(|| "Failed to wait for wpa_cli")?;

        Ok(())
    }

    fn setup_wps_pbc(&self) -> Result<()> {
        info!("Setting up WPS Push Button Configuration");
        
        // Enable WPS PBC on the P2P group interface
        let mut cmd = Command::new("wpa_cli")
            .args(&["-i", "p2p-wlan0-0", "wps_pbc"])
            .spawn()
            .chain_err(|| "Failed to enable WPS PBC")?;
        cmd.wait().chain_err(|| "Failed to wait for wpa_cli")?;

        Ok(())
    }

    fn configure_p2p_interface(&self) -> Result<()> {
        info!("Configuring P2P interface IP address");
        
        // Wait a bit more for the interface to be fully ready
        thread::sleep(Duration::from_secs(2));
        
        // Set IP address on the P2P group interface
        let ip_addr = format!("{}/24", self.gateway);
        let mut cmd = Command::new("ip")
            .args(&["addr", "add", &ip_addr, "dev", "p2p-wlan0-0"])
            .spawn()
            .chain_err(|| "Failed to set IP address on P2P interface")?;
        cmd.wait().chain_err(|| "Failed to wait for ip command")?;

        // Bring the interface up
        let mut cmd = Command::new("ip")
            .args(&["link", "set", "p2p-wlan0-0", "up"])
            .spawn()
            .chain_err(|| "Failed to bring up P2P interface")?;
        cmd.wait().chain_err(|| "Failed to wait for ip command")?;

        Ok(())
    }

    pub fn get_p2p_interface_name(&self) -> String {
        "p2p-wlan0-0".to_string()
    }
} 