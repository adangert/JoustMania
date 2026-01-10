#!/bin/bash

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi


if [ ! -f ./apfiles/ap_active ]
	then echo "AP not active... ending"
	exit
fi

rm ./apfiles/ap_active

echo "Deleting ad-hoc network, This pi should now reconnect back to the internet"
nmcli con delete Hotspot

#removing dnsmasq (for http://joust.mania access)
rm /etc/NetworkManager/dnsmasq-shared.d/joustmania.conf


echo ">>> DONE <<<"


