if [ "$EUID" -ne 0 ]
  then echo "This script needs root... run with sudo"
  exit
fi

mv /etc/dhcpcd.conf.bak /etc/dhcpcd.conf

mv /etc/network/interfaces.bak /etc/network/interfaces

mv /etc/hostapd/hostapd.conf.bak /etc/hostapd/hostapd.conf

mv /etc/default/hostapd.bak /etc/default/hostapd

mv /etc/dnsmasq.conf.bak /etc/dnsmasq.conf

mv /etc/sysctl.conf.bak /etc/sysctl.conf

mv /etc/rc.local.bak /etc/rc.local

sudo service hostapd stop  
sudo service dnsmasq stop

reboot