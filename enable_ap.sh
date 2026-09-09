#!/bin/bash
set -e

if [ "$UID" -ne 0 ]; then
    exec sudo -n /bin/bash "$0" "$@"
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Copy DNS settings before activating the hotspot.
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cp ./apfiles/joustmania.conf /etc/NetworkManager/dnsmasq-shared.d/joustmania.conf

profiles=$(nmcli -t -f NAME connection show)
if grep -Fxq Hotspot <<< "$profiles"; then
    nmcli -w 20 connection up Hotspot
else
    nmcli -w 20 device wifi hotspot ifname wlan0 con-name Hotspot ssid JoustMania password "joustpass"
fi
nmcli connection modify Hotspot connection.autoconnect true
nmcli connection modify Hotspot 802-11-wireless.powersave 2
nmcli connection modify Hotspot 802-11-wireless.wake-on-wlan 2

# Only record success after NetworkManager has completed the operation.
touch ./apfiles/ap_active
echo "Connect to JoustMania (password: joustpass), then open http://joust.mania"
