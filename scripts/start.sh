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
export PORTAL_SSID="EnVoid-connect-${RESIN_DEVICE_UUID:0:5}"
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
    printf 'Skipping WiFi Connect\n'
    sleep infinity
else
    printf 'Starting WiFi Connect\n'
    ./wifi-connect
fi

