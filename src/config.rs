use clap::{App, Arg};

use std::env;
use std::net::Ipv4Addr;
use std::str::FromStr;

const DEFAULT_GATEWAY: &str = "192.168.42.1";
const DEFAULT_DHCP_RANGE: &str = "192.168.42.2,192.168.42.254";
const DEFAULT_SSID: &str = "WiFi Connect";

#[derive(Clone)]
pub struct Config {
    pub interface: Option<String>,
    pub ssid: String,
    pub passphrase: Option<String>,
    pub gateway: Ipv4Addr,
    pub dhcp_range: String,
    pub forget_all: bool,
    pub list_networks: bool,
    pub list_connected: bool,
    pub list_saved: bool,
    pub forget_network: Option<String>,
    pub connect: Option<(String, String)>, // (SSID, passphrase)
    // New hotspot management commands
    pub start_hotspot: bool,
    pub stop_hotspot: bool,
    pub check_hotspot: bool,
    pub restart_hotspot: bool,
    pub no_dhcp_gateway: bool,
    pub no_dhcp_dns: bool,
    pub no_dhcp_router_option: bool,
    pub disconnect: bool
}


pub fn get_config() -> Config {
    let matches = App::new(crate_name!())
        .version(crate_version!())
        .author(crate_authors!())
        .about(crate_description!())
        .arg(
            Arg::with_name("portal-interface")
                .short("i")
                .long("portal-interface")
                .value_name("interface")
                .help("Wireless network interface to be used by WiFi Connect")
                .takes_value(true),
        )
        .arg(
            Arg::with_name("portal-ssid")
                .short("s")
                .long("portal-ssid")
                .value_name("ssid")
                .help(&format!(
                    "SSID of the captive portal WiFi network (default: {})",
                    DEFAULT_SSID
                ))
                .takes_value(true),
        )
        .arg(
            Arg::with_name("portal-passphrase")
                .short("p")
                .long("portal-passphrase")
                .value_name("passphrase")
                .help("WPA2 Passphrase of the captive portal WiFi network (default: none)")
                .takes_value(true),
        )
        .arg(
            Arg::with_name("portal-gateway")
                .short("g")
                .long("portal-gateway")
                .value_name("gateway")
                .help(&format!(
                    "Gateway of the captive portal WiFi network (default: {})",
                    DEFAULT_GATEWAY
                ))
                .takes_value(true),
        )
        .arg(
            Arg::with_name("portal-dhcp-range")
                .short("d")
                .long("portal-dhcp-range")
                .value_name("dhcp_range")
                .help(&format!(
                    "DHCP range of the WiFi network (default: {})",
                    DEFAULT_DHCP_RANGE
                ))
                .takes_value(true),
        )
        .arg(
            Arg::with_name("forget-all")
                .long("forget-all")
                .help("Forget all saved WiFi networks and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("list-networks")
                .long("list-networks")
                .help("List all available WiFi networks and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("list-connected")
                .long("list-connected")
                .help("List currently connected WiFi network and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("list-saved")
                .long("list-saved")
                .help("List all saved WiFi networks and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("forget-network")
                .long("forget-network")
                .value_name("ssid")
                .help("Forget a specific WiFi network by SSID and exit")
                .takes_value(true),
        )
        .arg(
            Arg::with_name("connect")
                .long("connect")
                .value_name("ssid")
                .help("Connect to a specific WiFi network")
                .takes_value(true),
        )
        .arg(
            Arg::with_name("passphrase")
                .long("passphrase")
                .value_name("passphrase")
                .help("Passphrase for the WiFi network to connect to")
                .takes_value(true),
        )
        // New hotspot management arguments
        .arg(
            Arg::with_name("start-hotspot")
                .long("start-hotspot")
                .help("Start the WiFi hotspot and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("stop-hotspot")
                .long("stop-hotspot")
                .help("Stop the WiFi hotspot and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("check-hotspot")
                .long("check-hotspot")
                .help("Check hotspot status and exit")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("restart-hotspot")
                .long("restart-hotspot")
                .help("Restart the WiFi hotspot and exit")
                .takes_value(false),
            )
        .arg(
            Arg::with_name("no-dhcp-gateway")
                .long("no-dhcp-gateway")
                .help("Do not advertise a router (gateway) option via DHCP")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("no-dhcp-dns")
                .long("no-dhcp-dns")
                .help("Do not provide DNS server information via DHCP (disables wildcard DNS redirection)")
                .takes_value(false),
        )
        .arg(
            Arg::with_name("no-dhcp-router-option")
                .long("no-dhcp-router-option")
                .help("Explicitly set empty router option via DHCP (prevents auto-detection of gateway)")
                .takes_value(false),
        )
        .arg(
                Arg::with_name("disconnect")
                    .short("d")
                    .long("disconnect")
                    .help("Disconnects from the current WiFi network"),
        )
        .get_matches();

    let interface: Option<String> = matches.value_of("portal-interface").map_or_else(
        || env::var("PORTAL_INTERFACE").ok(),
        |v| Some(v.to_string()),
    );

    let ssid: String = matches.value_of("portal-ssid").map_or_else(
        || env::var("PORTAL_SSID").unwrap_or_else(|_| DEFAULT_SSID.to_string()),
        String::from,
    );

    let passphrase: Option<String> = matches.value_of("portal-passphrase").map_or_else(
        || env::var("PORTAL_PASSPHRASE").ok(),
        |v| Some(v.to_string()),
    );

    let gateway = Ipv4Addr::from_str(&matches.value_of("portal-gateway").map_or_else(
        || env::var("PORTAL_GATEWAY").unwrap_or_else(|_| DEFAULT_GATEWAY.to_string()),
        String::from,
    ))
    .expect("Cannot parse gateway address");

    let dhcp_range = matches.value_of("portal-dhcp-range").map_or_else(
        || env::var("PORTAL_DHCP_RANGE").unwrap_or_else(|_| DEFAULT_DHCP_RANGE.to_string()),
        String::from,
    );

    let forget_all = matches.is_present("forget-all");
    let list_networks = matches.is_present("list-networks");
    let list_connected = matches.is_present("list-connected");
    let list_saved = matches.is_present("list-saved");
    let forget_network = matches.value_of("forget-network").map(|s| s.to_string());
    let connect = if let Some(ssid) = matches.value_of("connect") {
        let passphrase = matches.value_of("passphrase").unwrap_or("").to_string();
        Some((ssid.to_string(), passphrase))
    } else {
        None
    };

    // New hotspot command flags
    let start_hotspot = matches.is_present("start-hotspot");
    let stop_hotspot = matches.is_present("stop-hotspot");
    let check_hotspot = matches.is_present("check-hotspot");
    let restart_hotspot = matches.is_present("restart-hotspot");
    let no_dhcp_gateway = matches.is_present("no-dhcp-gateway");
    let no_dhcp_dns = matches.is_present("no-dhcp-dns");
    let no_dhcp_router_option = matches.is_present("no-dhcp-router-option");

    Config {
        interface,
        ssid,
        passphrase,
        gateway,
        dhcp_range,
        forget_all,
        list_networks,
        list_connected,
        list_saved,
        forget_network,
        connect,
        start_hotspot,
        stop_hotspot,
        check_hotspot,
        restart_hotspot,
        no_dhcp_gateway,
        no_dhcp_dns,
        no_dhcp_router_option,
        disconnect: matches.is_present("disconnect"),
    }
}

