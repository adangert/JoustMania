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

apt-get install dnsmasq hostapd

mv /etc/dhcpcd.conf /etc/dhcpcd.conf.bak
cp ./apfiles/dhcpcd.conf /etc/dhcpcd.conf
chown :pi /etc/dhcpcd.conf

mv /etc/network/interfaces /etc/network/interfaces.bak
cp ./apfiles/interfaces /etc/network/interfaces

sudo service dhcpcd restart
ifdown wlan0; ifup wlan0

mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
cp ./apfiles/hostapd.conf /etc/hostapd/hostapd.conf

mv /etc/default/hostapd /etc/default/hostapd.bak
cp ./apfiles/hostapd /etc/default/hostapd

mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
cp ./apfiles/dnsmasq.conf /etc/dnsmasq.conf

mv /etc/sysctl.conf /etc/sysctl.conf.bak
cp ./apfiles/sysctl.conf /etc/sysctl.conf

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE  
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT  
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT 
sh -c "iptables-save > /etc/iptables.ipv4.nat"

mv /etc/rc.local /etc/rc.local.bak
cp ./apfiles/rc.local /etc/rc.local

update-rc.d hostapd enable
update-rc.d dnsmasq enable

reboot
