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

use std::io::Write;
use std::path;
use std::process;
use std::sync::mpsc::channel;
use std::thread;
use std::time::Duration;

use config::get_config;
use errors::*;
use exit::block_exit_signals;
use network::{init_networking, process_network_commands};
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
        
        match network::get_connected_network(&manager, &config.interface)? {
            Some(connected) => {
                println!("\nConnected Network:");
                println!("-----------------");
                println!("SSID: {}", connected.ssid);
                println!("Security: {}", connected.security);
                println!("Signal: {}%", connected.signal_strength);
                println!("Interface: {}", connected.interface);
                if let Some(ip) = connected.ip_address {
                    println!("IP: {}", ip);
                } else {
                    println!("IP: Not available");
                }
            }
            None => {
                println!("\nNo network connected");
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
                let auto_connect_str = if network.auto_connect { "Yes" } else { "No" };
                println!("SSID: {}, Security: {}, Auto-connect: {}", 
                         network.ssid, network.security, auto_connect_str);
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
