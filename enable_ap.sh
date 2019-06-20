#!/bin/bash

#following the guide here: https://github.com/peebles/rpi3-wifi-station-ap-stretch

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

if [ -f ./apfiles/ap_active ]
	then echo "Script already run"
	exit
fi

touch ./apfiles/ap_active

apt-get install -y hostapd dnsmasq

#cp ./apfiles/ap /etc/network/interfaces.d/ap

#cp ./apfiles/station /etc/network/interfaces.d/station

#cp ./apfiles/90-wireless.rules /etc/udev/rules.d/90-wireless.rules

#mv /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant.bak
#cp ./apfiles/10-wpa_supplicant /lib/dhcpcd/dhcpcd-hooks/10-wpa_supplicant


mv /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
cp ./apfiles/dnsmasq.conf /etc/dnsmasq.conf

mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
cp ./apfiles/hostapd.conf /etc/hostapd/hostapd.conf

mv /etc/default/hostapd /etc/default/hostapd.bak
cp ./apfiles/hostapd /etc/default/hostapd


#for testing
mv /etc/dhcpcd.conf /etc/dhcpcd.conf.bak
cp ./apfiles/dhcpcd.conf /etc/dhcpcd.conf
chown :pi /etc/dhcpcd.conf

#mv /etc/network/interfaces /etc/network/interfaces.bak
#cp ./apfiles/interfaces /etc/network/interfaces

#sudo service dhcpcd restart
#ifdown wlan0; ifup wlan0

mv /etc/sysctl.conf /etc/sysctl.conf.bak
cp ./apfiles/sysctl.conf /etc/sysctl.conf

#updates for allowing joustmania to work
#echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
#echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -A POSTROUTING -s 10.3.141.0/24 ! -d 10.3.141.0/24 -j MASQUERADE
#iptables-save > /etc/iptables/rules.v4
#sh -c "iptables-save > /etc/iptables.ipv4.nat"

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE  
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT  
#iptables -A FORWARD -i eth0 -o uap0 -m state --state RELATED,ESTABLISHED -j ACCEPT  


iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT 
#iptables -A FORWARD -i uap0 -o eth0 -j ACCEPT 
sh -c "iptables-save > /etc/iptables.ipv4.nat"

mv /etc/rc.local /etc/rc.local.bak
cp ./apfiles/rc.local /etc/rc.local

#update-rc.d hostapd enable
#update-rc.d dnsmasq enable

reboot
