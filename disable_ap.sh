#!/bin/bash
set -e

if [ "$UID" -ne 0 ]; then
    exec sudo -n /bin/bash "$0" "$@"
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Query NetworkManager rather than relying on a potentially stale marker.
profiles=$(nmcli -t -f NAME connection show)
if grep -Fxq Hotspot <<< "$profiles"; then
    nmcli -w 20 connection delete Hotspot
fi
rm -f /etc/NetworkManager/dnsmasq-shared.d/joustmania.conf ./apfiles/ap_active
echo "Hotspot disabled. The Pi can reconnect to its saved Wi-Fi network."
