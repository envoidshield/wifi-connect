#![recursion_limit = "1024"]

#[macro_use]
extern crate log;

#[macro_use]
extern crate error_chain;

#[macro_use]
extern crate serde_derive;

#[macro_use]
extern crate clap;

extern crate env_logger;
extern crate iron;
extern crate iron_cors;
extern crate mount;
extern crate network_manager;
extern crate nix;
extern crate params;
extern crate persistent;
extern crate router;
extern crate serde_json;
extern crate staticfile;

mod config;
mod dnsmasq;
mod errors;
mod exit;
mod logger;
mod network;
mod privileges;
mod server;
mod hotspot_manager;

use std::io::Write;
use std::path;
use std::process;
use std::sync::mpsc::channel;
use std::thread;
use std::time::Duration;

use config::get_config;
use errors::*;
use exit::block_exit_signals;
use hotspot_manager::HotspotManager; // Import the HotspotManager
use network::{init_networking, process_network_commands, forget_all_wifi_connections, 
              forget_specific_network, find_device, get_access_points, get_networks, 
              get_connected_network, get_saved_networks, find_access_point, 
              init_access_point_credentials, wait_for_connectivity};
use privileges::require_root;

fn main() {
    if let Err(ref e) = run() {
        let stderr = &mut ::std::io::stderr();
        let errmsg = "Error writing to stderr";

        writeln!(stderr, "\x1B[1;31mError: {}\x1B[0m", e).expect(errmsg);

        for inner in e.iter().skip(1) {
            writeln!(stderr, "  caused by: {}", inner).expect(errmsg);
        }

        process::exit(errors::exit_code(e));
    }
}

fn run() -> Result<()> {
    block_exit_signals()?;

    logger::init();

    let config = get_config();

    require_root()?;

    // Handle hotspot management commands first
    if config.start_hotspot {
        return handle_start_hotspot(config);
        return Ok(());
    }

    if config.stop_hotspot {
        return handle_stop_hotspot(config);
        return Ok(());
    }

    if config.check_hotspot {
        return handle_check_hotspot(config);
        return Ok(());
    }

    if config.restart_hotspot {
        return handle_restart_hotspot(config);
        return Ok(());
    }

    // Handle existing WiFi management commands
    if config.forget_all {
        let manager = network_manager::NetworkManager::new();
        network::forget_all_wifi_connections(&manager)?;
        info!("All WiFi networks have been forgotten");
        return Ok(());
    }

    if let Some(ref ssid) = config.forget_network {
        let manager = network_manager::NetworkManager::new();
        let found = network::forget_specific_network(&manager, ssid)?;
        if found {
            info!("WiFi network '{}' has been forgotten", ssid);
        } else {
            info!("WiFi network '{}' was not found in saved connections", ssid);
        }
        return Ok(());
    }

    if config.list_networks {
        let manager = network_manager::NetworkManager::new();
        let device = network::find_device(&manager, &config.interface)?;
        
        // Force a scan for networks
        if let Some(wifi_device) = device.as_wifi_device() {
            info!("Scanning for WiFi networks...");
            if let Err(e) = wifi_device.request_scan() {
                warn!("Failed to request scan: {}", e);
            }
            // Wait a bit for the scan to complete
            thread::sleep(Duration::from_secs(2));
        }
        
        let access_points = network::get_access_points(&device, "")?;
        let networks = network::get_networks(&access_points);
        
        println!("\nAvailable WiFi Networks:");
        println!("----------------------");
        if networks.is_empty() {
            println!("No networks found. Please try again.");
        } else {
            for network in networks {
                println!("SSID: {}, Security: {}", network.ssid, network.security);
            }
        }
        return Ok(());
    }

    if config.list_connected {
        let manager = network_manager::NetworkManager::new();
        match network::get_connected_network(&manager, &config.interface) {
            Ok(Some(connected)) => {
                println!("Connected Network:");
                println!("SSID: {}, Security: {}, Signal: {}%, Interface: {}, IP: {}", 
                         connected.ssid, 
                         connected.security, 
                         connected.signal_strength,
                         connected.interface,
                         connected.ip_address.unwrap_or_else(|| "N/A".to_string()));
            }
            Ok(None) => {
                println!("No network connected");
            }
            Err(e) => {
                error!("Failed to get connected network: {}", e);
                return Err(e);
            }
        }
        return Ok(());
    }

    if config.list_saved {
        let manager = network_manager::NetworkManager::new();
        let saved_networks = network::get_saved_networks(&manager)?;
        
        println!("\nSaved WiFi Networks:");
        println!("-------------------");
        if saved_networks.is_empty() {
            println!("No saved networks found.");
        } else {
            for network in saved_networks {
                println!("SSID: {}, Security: {}", 
                         network.ssid, network.security);
            }
        }
        return Ok(());
    }

    if let Some((ssid, passphrase)) = config.connect {
        let manager = network_manager::NetworkManager::new();
        let device = network::find_device(&manager, &config.interface)?;
        let access_points = network::get_access_points(&device, "")?;
        
        if let Some(access_point) = network::find_access_point(&access_points, &ssid) {
            let wifi_device = device.as_wifi_device().unwrap();
            let credentials = network::init_access_point_credentials(access_point, "", &passphrase);
            
            info!("Connecting to '{}'...", ssid);
            match wifi_device.connect(access_point, &credentials) {
                Ok((connection, state)) => {
                    if state == network_manager::ConnectionState::Activated {
                        match network::wait_for_connectivity(&manager, 20) {
                            Ok(has_connectivity) => {
                                if has_connectivity {
                                    info!("Successfully connected to '{}'", ssid);
                                } else {
                                    warn!("Connected to '{}' but no internet connectivity", ssid);
                                }
                            }
                            Err(err) => error!("Getting Internet connectivity failed: {}", err),
                        }
                    } else {
                        warn!("Failed to connect to '{}': {:?}", ssid, state);
                    }
                }
                Err(e) => error!("Error connecting to '{}': {}", ssid, e),
            }
        } else {
            error!("Network '{}' not found", ssid);
        }
        return Ok(());
    }

    // If no specific commands, fall back to original captive portal mode
    init_networking(&config)?;

    let (exit_tx, exit_rx) = channel();

    thread::spawn(move || {
        process_network_commands(&config, &exit_tx);
    });

    match exit_rx.recv() {
        Ok(result) => result?,
        Err(e) => {
            return Err(e.into());
        }
    }

    Ok(())
}

// New hotspot management functions
fn handle_start_hotspot(config: config::Config) -> Result<()> {
    info!("Starting hotspot '{}'...", config.ssid);
    
    let mut hotspot = HotspotManager::new(config)?;
    hotspot.start_hotspot()?;
    
    let status = hotspot.get_hotspot_status();
    status.print_status();
    
    info!("Hotspot started successfully. Press Ctrl+C to stop.");
    
    // Set up signal handling for graceful shutdown
    let (exit_tx, exit_rx) = channel();
    
    thread::spawn(move || {
        if let Err(e) = exit::trap_exit_signals() {
            error!("Signal handling failed: {}", e);
            return;
        }
        
        info!("Received shutdown signal");
        let _ = exit_tx.send(());
    });
    
    // Wait for shutdown signal
    match exit_rx.recv() {
        Ok(_) => {
            info!("Shutting down hotspot...");
            hotspot.stop_hotspot()?;
            info!("Hotspot stopped");
        }
        Err(e) => {
            error!("Error waiting for exit signal: {}", e);
            hotspot.stop_hotspot()?;
        }
    }
    
    Ok(())
}

fn handle_stop_hotspot(config: config::Config) -> Result<()> {
    info!("Stopping hotspot...");
    
    let mut hotspot = HotspotManager::new(config)?;
    
    if !hotspot.is_hotspot_running() {
        info!("Hotspot is not currently running");
        return Ok(());
    }
    
    hotspot.stop_hotspot()?;
    info!("Hotspot stopped successfully");
    Ok(())
}

fn handle_check_hotspot(config: config::Config) -> Result<()> {
    let hotspot = HotspotManager::new(config)?;
    let status = hotspot.get_hotspot_status();
    
    println!("\n=== Hotspot Status ===");
    status.print_status();
    
    if status.is_running {
        println!("\nTo stop the hotspot, run: {} --stop-hotspot", env!("CARGO_PKG_NAME"));
    } else {
        println!("\nTo start the hotspot, run: {} --start-hotspot", env!("CARGO_PKG_NAME"));
    }
    
    Ok(())
}

fn handle_restart_hotspot(config: config::Config) -> Result<()> {
    info!("Restarting hotspot '{}'...", config.ssid);
    
    let mut hotspot = HotspotManager::new(config)?;
    hotspot.restart_hotspot()?;
    
    let status = hotspot.get_hotspot_status();
    status.print_status();
    
    info!("Hotspot restarted successfully");
    Ok(())
}

// Helper function to create a persistent hotspot that stays running
pub fn run_persistent_hotspot(config: config::Config) -> Result<()> {
    info!("Starting persistent hotspot '{}'...", config.ssid);
    
    let mut hotspot = HotspotManager::new(config.clone())?;
    hotspot.start_hotspot()?;
    
    let status = hotspot.get_hotspot_status();
    status.print_status();
    
    info!("Hotspot running persistently. Press Ctrl+C to stop.");
    
    // Set up signal handling for graceful shutdown
    let (exit_tx, exit_rx) = channel();
    
    thread::spawn(move || {
        if let Err(e) = exit::trap_exit_signals() {
            error!("Signal handling failed: {}", e);
            return;
        }
        
        info!("Received shutdown signal");
        let _ = exit_tx.send(());
    });
    
    // Wait for shutdown signal
    match exit_rx.recv() {
        Ok(_) => {
            info!("Shutting down hotspot...");
            hotspot.stop_hotspot()?;
            info!("Hotspot stopped");
        }
        Err(e) => {
            error!("Error waiting for exit signal: {}", e);
            hotspot.stop_hotspot()?;
        }
    }
    
    Ok(())
}
