#!/usr/bin/env bash

export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

log_with_timestamp() {
    while IFS= read -r line; do
        echo "$(date +"[%d-%m-%Y %H:%M:%S]") $line"
    done
}

LOG_FILE=/logs/start.log
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(log_with_timestamp | tee -a ${LOG_FILE}) 2>&1

echo "Starting WiFi API Server..."

./block-peers.sh

python3 wifi_api_server.py
