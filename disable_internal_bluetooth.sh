#!/bin/bash
# this will disable on-board bluetooth
# this will allow only class one long range btdongles to connect to psmove controllers

DIST_REL=$(cut -f2 <<< $(lsb_release -r))
if [ "$DIST_REL" -ge 12 ]; then
	echo "the distribution $DIST_REL is larger than 12"
	config_loc=/boot/firmware/config.txt || exit -1
else
	echo "the distribution is smaller than 12"
	config_loc=/boot/config.txt || exit -1
fi

echo "dtoverlay=disable-bt" | sudo tee -a $config_loc
sudo rm -rf /var/lib/bluetooth/*
sudo systemctl disable hciuart

sudo reboot
