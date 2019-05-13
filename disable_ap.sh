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

update-rc.d hostapd disable
update-rc.d dnsmasq disable

mv /etc/dhcpcd.conf.bak /etc/dhcpcd.conf
chown :pi /etc/dhcpcd.conf

mv /etc/network/interfaces.bak /etc/network/interfaces

mv /etc/hostapd/hostapd.conf.bak /etc/hostapd/hostapd.conf

mv /etc/default/hostapd.bak /etc/default/hostapd

mv /etc/dnsmasq.conf.bak /etc/dnsmasq.conf

mv /etc/sysctl.conf.bak /etc/sysctl.conf

mv /etc/rc.local.bak /etc/rc.local

rm /etc/network/interfaces.d/ap

rm /etc/udev/rules.d/90-wireless.rules

mv /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant.bak /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant 

reboot
