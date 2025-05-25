# WiFi Connect Command Line Arguments

## Flags

*   **-h, --help**

    Prints help information

*   **-V, --version**

    Prints version information

## Options

Command line options have environment variable counterpart. If both a command line option and its environment variable counterpart are defined, the command line option will take higher precedence.

*   **-d, --portal-dhcp-range** dhcp_range, **$PORTAL_DHCP_RANGE**

    DHCP range of the captive portal WiFi network

    Default: _192.168.42.2,192.168.42.254_

*   **-g, --portal-gateway** gateway, **$PORTAL_GATEWAY**

    Gateway of the captive portal WiFi network

    Default: _192.168.42.1_

*   **-o, --portal-listening-port** listening_port, **$PORTAL_LISTENING_PORT**

    Listening port of the captive portal web server

    Default: _80_

*   **-i, --portal-interface** interface, **$PORTAL_INTERFACE**

    Wireless network interface to be used by WiFi Connect

*   **-p, --portal-passphrase** passphrase, **$PORTAL_PASSPHRASE**

    WPA2 Passphrase of the captive portal WiFi network

    Default: _no passphrase_

*   **-s, --portal-ssid** ssid, **$PORTAL_SSID**

    SSID of the captive portal WiFi network

    Default: _WiFi Connect_

*   **-a, --activity-timeout** timeout, **$ACTIVITY_TIMEOUT**

    Exit if no activity for the specified timeout (seconds)

    Default: _0 - no timeout_

*   **-u, --ui-directory** ui_directory, **$UI_DIRECTORY**

    Web UI directory location

    Default: _ui_

*   **--forget-all**

    Forget all saved WiFi networks and exit

*   **--wifi-direct**

    Enable WiFi Direct (P2P) mode instead of traditional access point. Provides better compatibility with mobile devices and allows them to maintain their cellular/WiFi connection while connecting to the setup portal.

## Environment Variables
