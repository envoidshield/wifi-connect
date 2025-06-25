#!/usr/bin/env bash

export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

# Optional step - it takes couple of seconds (or longer) to establish a WiFi connection
# sometimes. In this case, following checks will fail and wifi-connect
# will be launched even if the device will be able to connect to a WiFi network.
# If this is your case, you can wait for a while and then check for the connection.
log_with_timestamp() {
    while IFS= read -r line; do
        echo "$(date +"[%d-%m-%Y %H:%M:%S]") $line"
    done
}

LOG_FILE=/logs/start.log
exec > >(log_with_timestamp | tee -a ${LOG_FILE}) 2>&1

# Check if the file exists
if [ ! -f "$LOG_FILE" ]; then
    # If the file doesn't exist, create it
    touch "$LOG_FILE"
    echo "File '$LOG_FILE' created."
else
    echo "File '$LOG_FILE' already exists."
fi 

check_api_ping() {
    local API_ENDPOINT='api.balena-cloud.com'
    local ATTEMPTS=3

    # Loop through the attempts
    for i in $(seq 1 $ATTEMPTS); do
        # Ping the API endpoint
        if ping -c 1 $API_ENDPOINT &> /dev/null; then
            # If ping is successful, return true (exit 0)
            echo "Ping to $API_ENDPOINT successful."
            return 0
        fi
        # If ping fails, wait a moment before retrying
        sleep 3
    done

    # If all attempts fail, return false (exit 1)
    echo "Ping to $API_ENDPOINT failed after $ATTEMPTS attempts."
    return 1
}


echo "starting start script..."
sleep 10

# Set SSID based on mode
if [[ -n "${WIFI_DIRECT+x}" && "${WIFI_DIRECT,,}" == "true" ]]; then
    export PORTAL_SSID="EnVoid-Direct-${RESIN_DEVICE_UUID:0:5}" >> ~/.bashrc && source ~/.bashrc

    echo "WIFI_DIRECT mode: SSID set to $PORTAL_SSID" >> ~/.bashrc && source ~/.bashrc

else
    export PORTAL_SSID="EnVoid-Connect-${RESIN_DEVICE_UUID:0:5}" >> ~/.bashrc && source ~/.bashrc

    echo "Standard mode: SSID set to $PORTAL_SSID" >> ~/.bashrc && source ~/.bashrc

fi

# Choose a condition for running WiFi Connect according to your use case:

# 1. Is there a default gateway?
# ip route | grep default

# 2. Is there Internet connectivity?
#nmcli -t g | grep full

# 3. Is there Internet connectivity via a google ping?
# wget --spider http://google.com 2>&1

# 4. Is there an active WiFi connection?

check_connection() {
    # Get the SSID of the connected WiFi network
    SSID=$(iwgetid -r)
    
    if [ -n "$SSID" ]; then
        echo "Connected to WiFi network: $SSID."
        
        # WIFI_DIRECT mode overrides connectivity check
        if [[ -n "${WIFI_DIRECT+x}" && "${WIFI_DIRECT,,}" == "true" ]]; then
            echo "WIFI_DIRECT mode enabled - skipping connectivity check"
            return 0;
        fi
        
        # Check if connected to Balena Cloud
        if [[ -n "${CHECK_CONNECTIVITY+x}" && "${CHECK_CONNECTIVITY,,}" == "false" ]]; then
            echo "skipping ping"
            return 0;
        fi

        if check_api_ping $API_ENDPOINT; then
            echo "Connected to Balena Cloud."
            return 0
        else
            echo "Connected to WiFi network: $SSID, but failed to connect to Balena Cloud."
        fi
    else
        echo "Not connected to any WiFi network."
    fi
    
    return 1
}

check_connection
connection=$? 


if [ "$connection" -eq 0 ]; then
    printf 'Starting API\n'
else
    printf 'Starting WiFi Connect\n'

    WIFI_CONNECT_ARGS=""

    # WIFI_DIRECT mode enables all direct connection options
    if [[ -n "${WIFI_DIRECT+x}" && "${WIFI_DIRECT,,}" == "true" ]]; then
        echo "WIFI_DIRECT mode enabled - activating CarPlay-style direct connection"
        WIFI_CONNECT_ARGS+=" --no-dhcp-gateway"
        WIFI_CONNECT_ARGS+=" --no-dhcp-router-option"
        WIFI_CONNECT_ARGS+=" --activity-timeout 0"
    else
        # Honour individual env vars for suppressing DHCP options
        if [[ -n "${NO_DHCP_GATEWAY+x}" && "${NO_DHCP_GATEWAY,,}" == "true" ]]; then
            WIFI_CONNECT_ARGS+=" --no-dhcp-gateway"
        fi

        if [[ -n "${NO_DHCP_DNS+x}" && "${NO_DHCP_DNS,,}" == "true" ]]; then
            WIFI_CONNECT_ARGS+=" --no-dhcp-dns"
        fi
        
        if [[ -n "${NO_DHCP_ROUTER_OPTION+x}" && "${NO_DHCP_ROUTER_OPTION,,}" == "true" ]]; then
            WIFI_CONNECT_ARGS+=" --no-dhcp-router-option"
        fi
    fi

    ./wifi-connect ${WIFI_CONNECT_ARGS} --start-hotspot
    sleep 1
fi

python3 api.py --binary "./wifi-connect" --serve --port 8080
