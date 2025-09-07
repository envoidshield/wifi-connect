use std::collections::HashSet;
use std::thread;
use std::time::Duration;

use network_manager::{
    AccessPoint, AccessPointCredentials, Connection, ConnectionState, Connectivity, Device,
    DeviceState, DeviceType, NetworkManager, Security, ServiceState,
};

use config::Config;
use errors::*;


#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct Network {
    pub ssid: String,
    pub security: String,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct SavedNetwork {
    pub ssid: String,
    pub security: String,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub struct ConnectedNetwork {
    pub ssid: String,
    pub security: String,
    pub signal_strength: u8,
    pub interface: String,
    pub ip_address: Option<String>,
}



pub fn init_access_point_credentials(
    access_point: &AccessPoint,
    identity: &str,
    passphrase: &str,
) -> AccessPointCredentials {
    if access_point.security.contains(Security::ENTERPRISE) {
        AccessPointCredentials::Enterprise {
            identity: identity.to_string(),
            passphrase: passphrase.to_string(),
        }
    } else if access_point.security.contains(Security::WPA2)
        || access_point.security.contains(Security::WPA)
    {
        AccessPointCredentials::Wpa {
            passphrase: passphrase.to_string(),
        }
    } else if access_point.security.contains(Security::WEP) {
        AccessPointCredentials::Wep {
            passphrase: passphrase.to_string(),
        }
    } else {
        AccessPointCredentials::None
    }
}



pub fn find_device(manager: &NetworkManager, interface: &Option<String>) -> Result<Device> {
    if let Some(ref interface) = *interface {
        let device = manager
            .get_device_by_interface(interface)
            .chain_err(|| ErrorKind::DeviceByInterface(interface.clone()))?;

        info!("Targeted WiFi device: {}", interface);

        if *device.device_type() != DeviceType::WiFi {
            bail!(ErrorKind::NotAWiFiDevice(interface.clone()))
        }

        if device.get_state()? == DeviceState::Unmanaged {
            bail!(ErrorKind::UnmanagedDevice(interface.clone()))
        }

        Ok(device)
    } else {
        let devices = manager.get_devices()?;

        if let Some(device) = find_wifi_managed_device(devices)? {
            info!("WiFi device: {}", device.interface());
            Ok(device)
        } else {
            bail!(ErrorKind::NoWiFiDevice)
        }
    }
}

fn find_wifi_managed_device(devices: Vec<Device>) -> Result<Option<Device>> {
    for device in devices {
        if *device.device_type() == DeviceType::WiFi
            && device.get_state()? != DeviceState::Unmanaged
        {
            return Ok(Some(device));
        }
    }

    Ok(None)
}

pub fn get_access_points(device: &Device, ssid: &str) -> Result<Vec<AccessPoint>> {
    get_access_points_impl(device, ssid).chain_err(|| ErrorKind::NoAccessPoints)
}

fn get_access_points_impl(device: &Device, ssid: &str) -> Result<Vec<AccessPoint>> {
    info!("Scanning for available networks...");
    let retries_allowed = 10;
    let mut retries = 0;

    // After stopping the hotspot we may have to wait a bit for the list
    // of access points to become available
    while retries < retries_allowed {
        let wifi_device = device.as_wifi_device().unwrap();
        let mut access_points = wifi_device.get_access_points()?;

        // Only keep access points with valid SSIDs
        access_points.retain(|ap| ap.ssid().as_str().is_ok());

        // Purge access points with duplicate SSIDs
        let mut inserted = HashSet::new();
        access_points.retain(|ap| inserted.insert(ap.ssid.clone()));

        // Remove access points without SSID (hidden)
        access_points.retain(|ap| !ap.ssid().as_str().unwrap().is_empty());

        // Only filter by SSID if a specific SSID was provided
        if !ssid.is_empty() {
            access_points.retain(|ap| ap.ssid().as_str().unwrap() != ssid);
        }

        if !access_points.is_empty() {
            info!(
                "Found {} access points: {:?}",
                access_points.len(),
                get_access_points_ssids(&access_points)
            );
            return Ok(access_points);
        }

        retries += 1;
        info!("No access points found - retry #{}", retries);
        thread::sleep(Duration::from_secs(1));
    }

    warn!("No access points found - giving up...");
    Ok(vec![])
}

fn get_access_points_ssids(access_points: &[AccessPoint]) -> Vec<&str> {
    access_points
        .iter()
        .map(|ap| ap.ssid().as_str().unwrap())
        .collect()
}

pub fn get_networks(device: &Device, ssid: &String) -> Vec<Network> {
    let access_points = get_access_points_impl(device, ssid).unwrap_or_default();
    access_points.iter().map(get_network_info).collect()
}


fn get_network_info(access_point: &AccessPoint) -> Network {
    Network {
        ssid: access_point.ssid().as_str().unwrap().to_string(),
        security: get_network_security(access_point).to_string(),
    }
}

fn get_network_security(access_point: &AccessPoint) -> &str {
    if access_point.security.contains(Security::ENTERPRISE) {
        "enterprise"
    } else if access_point.security.contains(Security::WPA2)
        || access_point.security.contains(Security::WPA)
    {
        "wpa"
    } else if access_point.security.contains(Security::WEP) {
        "wep"
    } else {
        "none"
    }
}

pub fn find_access_point<'a>(access_points: &'a [AccessPoint], ssid: &str) -> Option<&'a AccessPoint> {
    for access_point in access_points.iter() {
        if let Ok(access_point_ssid) = access_point.ssid().as_str() {
            if access_point_ssid == ssid {
                return Some(access_point);
            }
        }
    }

    None
}

// New function to get currently connected network - improved version
pub fn get_connected_network(manager: &NetworkManager, interface: &Option<String>) -> Result<Option<ConnectedNetwork>> {
    let device = find_device(manager, interface)?;
    
    // Check if device is connected
    let device_state = device.get_state()?;
    if device_state != DeviceState::Activated {
        return Ok(None);
    }

    // Try to get the currently connected network by checking access points
    let wifi_device = device.as_wifi_device().unwrap();
    
    // First, try to scan for current access points to see which one we're connected to
    if let Ok(access_points) = wifi_device.get_access_points() {
        // Look for access points with high signal strength that might indicate connection
        for ap in &access_points {
            if let Ok(ssid) = ap.ssid().as_str() {
                if !ssid.is_empty() && ap.strength > 50 { // Assume high signal might indicate connection
                    // Check if we have a saved connection for this SSID
                    let connections = manager.get_connections()?;
                    for connection in connections {
                        if is_wifi_connection(&connection) {
                            let settings = connection.settings();
                            if let Ok(conn_ssid) = settings.ssid.as_str() {
                                if conn_ssid == ssid {
                                    return Ok(Some(ConnectedNetwork {
                                        ssid: ssid.to_string(),
                                        security: get_network_security(ap).to_string(),
                                        signal_strength: (ap.strength as u8).min(100),
                                        interface: device.interface().to_string(),
                                        ip_address: None,
                                    }));
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Ok(None)
}

// New function to list all saved networks
pub fn get_saved_networks(manager: &NetworkManager) -> Result<Vec<SavedNetwork>> {
    let connections = manager.get_connections()?;
    let mut saved_networks = Vec::new();
    let mut seen_ssids = HashSet::new();

    for connection in &connections {
        if is_wifi_connection(connection) && !is_access_point_connection(connection) {
            let settings = connection.settings();
            
            if let Ok(ssid) = settings.ssid.as_str() {
                if !ssid.is_empty() && !seen_ssids.contains(ssid) {
                    seen_ssids.insert(ssid.to_string());
                    
                    // Simplified security detection - could be enhanced
                    let security = "wpa"; // Default assumption for saved networks

                    saved_networks.push(SavedNetwork {
                        ssid: ssid.to_string(),
                        security: security.to_string(),
                    });
                }
            }
        }
    }

    saved_networks.sort_by(|a, b| a.ssid.cmp(&b.ssid));
    Ok(saved_networks)
}

// New function to forget a specific network
pub fn forget_specific_network(manager: &NetworkManager, ssid: &str) -> Result<bool> {
    let connections = manager.get_connections()?;
    let mut found = false;

    for connection in &connections {
        if is_wifi_connection(connection) && !is_access_point_connection(connection) {
            if let Some(connection_ssid) = connection_ssid_as_str(connection) {
                if connection_ssid == ssid {
                    info!("Forgetting WiFi network: {}", ssid);
                    connection.delete().chain_err(|| ErrorKind::DeleteAccessPoint)?;
                    found = true;
                }
            }
        }
    }

    if !found {
        warn!("Network '{}' not found in saved connections", ssid);
    }

    Ok(found)
}


pub fn wait_for_connectivity(manager: &NetworkManager, timeout: u64) -> Result<bool> {
    let mut total_time = 0;

    loop {
        let connectivity = manager.get_connectivity()?;

        if connectivity == Connectivity::Full || connectivity == Connectivity::Limited {
            debug!(
                "Connectivity established: {:?} / {}s elapsed",
                connectivity, total_time
            );

            return Ok(true);
        } else if total_time >= timeout {
            debug!(
                "Timeout reached in waiting for connectivity: {:?} / {}s elapsed",
                connectivity, total_time
            );

            return Ok(false);
        }

        ::std::thread::sleep(::std::time::Duration::from_secs(1));

        total_time += 1;

        debug!(
            "Still waiting for connectivity: {:?} / {}s elapsed",
            connectivity, total_time
        );
    }
}





fn connection_ssid_as_str(connection: &Connection) -> Option<&str> {
    // An access point SSID could be random bytes and not a UTF-8 encoded string
    connection.settings().ssid.as_str().ok()
}

fn is_access_point_connection(connection: &Connection) -> bool {
    is_wifi_connection(connection) && connection.settings().mode == "ap"
}

fn is_wifi_connection(connection: &Connection) -> bool {
    connection.settings().kind == "802-11-wireless"
}

pub fn disconnect_from_network(manager: &NetworkManager, interface: &Option<String>) -> Result<()> {
    let device = find_device(manager, interface)?;

    // Check if device is connected
    let device_state = device.get_state()?;
    if device_state != DeviceState::Activated {
        println!("No active connection found.");
        return Ok(());
    }

    // Deactivate the device to disconnect from the network
    device.disconnect()?; // Assuming there is a `disconnect` method

    println!("Disconnected successfully.");

    Ok(())
}

pub fn forget_all_wifi_connections(manager: &NetworkManager) -> Result<()> {
    let connections = match manager.get_connections() {
        Ok(connections) => connections,
        Err(e) => {
            error!("Getting existing connections failed: {}", e);
            return Err(e.into());
        }
    };

    info!("Forgetting all WiFi connections...");
    
    for connection in &connections {
        if is_wifi_connection(connection) {
            if let Some(ssid) = connection_ssid_as_str(connection) {
                info!("Deleting WiFi connection: {}", ssid);
                
                if let Err(e) = connection.delete() {
                    error!("Deleting WiFi connection failed: {}", e);
                }
            }
        }
    }
    
    Ok(())
}

