#!/bin/bash


if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

if [ -f ./apfiles/ap_active ]
	then echo "Script already run"
	exit
fi

touch ./apfiles/ap_active

#Copy over dnsmasq file so that http://joust.mania redirects to the webUI
echo "Copying dnsmasq configuration"
cp ./apfiles/joustmania.conf /etc/NetworkManager/dnsmasq-shared.d/joustmania.conf

echo "Create and enable wifi ad-hoc network"
#(note lowercase joustmania ssid does not work for some reason)
nmcli device wifi hotspot ifname wlan0 con-name Hotspot ssid JoustMania password "joustpass"

echo "Enable ad-hoc network as default on boot... "
nmcli connection modify Hotspot connection.autoconnect true

echo "Disable power save feature on wifi..."
nmcli connection modify Hotspot 802-11-wireless.powersave 2

echo "Enable wake-on-wlan..."
nmcli connection modify Hotspot 802-11-wireless.wake-on-wlan 2

echo "You should now be able to see and connect to JoustMania ssid on mobile (password: joustpass), and browse to the webui at http://joust.mania"

echo ">>> DONE <<<"





