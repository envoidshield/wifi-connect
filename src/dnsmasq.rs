use std::process::{Child, Command};

use network_manager::Device;

use config::Config;
use errors::*;

pub fn start_dnsmasq(config: &Config, device: &Device) -> Result<Child> {
    // Dynamically build dnsmasq arguments so that we can optionally omit the
    // router (gateway) and DNS advertisement when requested by the user
    let mut args: Vec<String> = Vec::new();

    if !config.no_dhcp_dns {
        args.push(format!("--address=/#/{}", config.gateway));
    }

    args.push(format!("--dhcp-range={}", config.dhcp_range));

    if !config.no_dhcp_gateway {
        args.push(format!("--dhcp-option=option:router,{}", config.gateway));
    } else if config.no_dhcp_router_option {
        // Explicitly set empty router option to prevent auto-detection
        args.push("--dhcp-option=option:router".to_string());
    }

    args.push(format!("--interface={}", device.interface()));

    // Static arguments that are always required
    args.push("--keep-in-foreground".to_string());
    args.push("--bind-interfaces".to_string());
    args.push("--except-interface=lo".to_string());
    args.push("--conf-file".to_string());
    args.push("--no-hosts".to_string());

    Command::new("dnsmasq")
        .args(&args)
        .spawn()
        .chain_err(|| ErrorKind::Dnsmasq)
}

