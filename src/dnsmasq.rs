use std::process::{Child, Command};

use network_manager::Device;

use config::Config;
use errors::*;

pub fn start_dnsmasq(config: &Config, device: &Device) -> Result<Child> {
    let interface_name = if config.wifi_direct {
        "p2p-wlan0-0".to_string()
    } else {
        device.interface().to_string()
    };

    let args = [
        &format!("--address=/#/{}", config.gateway),
        &format!("--dhcp-range={}", config.dhcp_range),
        &format!("--dhcp-option=option:router,{}", config.gateway),
        &format!("--interface={}", interface_name),
        "--keep-in-foreground",
        "--bind-interfaces",
        "--except-interface=lo",
        "--conf-file",
        "--no-hosts",
    ];

    Command::new("dnsmasq")
        .args(args)
        .spawn()
        .chain_err(|| ErrorKind::Dnsmasq)
}

pub fn stop_dnsmasq(dnsmasq: &mut Child) -> Result<()> {
    dnsmasq.kill()?;

    dnsmasq.wait()?;

    Ok(())
}
