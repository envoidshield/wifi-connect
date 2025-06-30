#!/bin/bash

echo "Starting WiFi AP Isolation..."

for iface in $(ip route | grep -E "dev (wl)" | awk '{print $3}' | sort -u); do
    gateway=$(ip route | grep "dev $iface" | grep "src" | sed 's/.*src \([0-9.]*\).*/\1/' | head -n1)
    
    if [[ -n "$gateway" ]]; then
        echo "Found interface: $iface with gateway: $gateway"
        
        echo "Applying isolation rules for $iface..."
        sudo iptables -I FORWARD -i "$iface" -o "$iface" -j DROP
        sudo iptables -I FORWARD -i "$iface" -d "$gateway" -j ACCEPT
        sudo iptables -I FORWARD -o "$iface" -s "$gateway" -j ACCEPT
        
        echo "✓ Isolation applied for $iface"
    else
        echo "No gateway found for $iface, skipping..."
    fi
done

echo "WiFi AP Isolation completed."
