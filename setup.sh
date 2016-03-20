#!/bin/bash

#update OS
sudo apt-get dist-upgrade -y
sudo apt-get update -y
cd /home/pi

#install components
sudo apt-get install -y python-dev bluez python-pyaudio python-pip python-numpy supervisor python-scipy python-pygame cmake libudev-dev swig libbluetooth-dev
sudo pip install psutil enum

#install psmoveapi
git clone https://github.com/thp/psmoveapi.git
cd psmoveapi
git remote add jmacarthur https://github.com/jmacarthur/psmoveapi.git
git fetch jmacarthur


git cherry-pick -n e3838a5c49313b8865ff493573aa417e8e4a391b
git submodule init
git submodule update
mkdir build
cd build
cmake ..
make -j4

#installs custom supervisor script for running piparty on startup
sudo cp -r /home/pi/PiParty/supervisor/ /etc/

#this may need to be in /lib/modprobe.d/aliases.conf instead for jessie release
#sets up sound card as primary sound device
OLD='options snd-usb-audio index=-2'
NEW='options snd-usb-audio index=0\noptions snd_bcm2835 index=-2'
sudo sed -i -e "s/$OLD/$NEW/g" /etc/modprobe.d/alsa-base.conf

#allows python path to be kept after sudo command
OLD='env_reset'
NEW='env_keep += "PYTHONPATH"'
sudo sed -i -e "s/$OLD/$NEW/g" /etc/sudoers

sudo reboot