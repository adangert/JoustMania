#!/bin/bash

#update OS
sudo apt-get dist-upgrade -y
sudo apt-get update -y
cd /home/pi

#install components
sudo apt-get install -y python-dev bluez python3-pyaudio python-pip python3-numpy supervisor python3-scipy python3-pygame cmake libudev-dev swig libbluetooth-dev alsa-utils alsa-tools
sudo pip3 install psutil


#install components for psmoveapi
sudo apt-get install -y \
    build-essential cmake \
    libudev-dev libbluetooth-dev libv4l-dev libopencv-dev \
    openjdk-7-jdk ant liblwjgl-java \
    python-dev \
    mono-mcs \
    swig3.0 \
    libsdl2-dev freeglut3-dev

#install psmoveapi
git clone --recursive git://github.com/thp/psmoveapi.git
cd psmoveapi
#git remote add jmacarthur https://github.com/jmacarthur/psmoveapi.git
#git fetch jmacarthur


#git cherry-pick -n e3838a5c49313b8865ff493573aa417e8e4a391b
#git submodule init
#git submodule update
mkdir build
cd build
JAVA_HOME=/usr/lib/jvm/java-7-openjdk-armhf/ cmake ..
make -j4

#installs custom supervisor script for running joustmania on startup
sudo cp -r /home/pi/JoustMania/supervisor/ /etc/

#sets up sound card as primary sound device
OLD='options snd-usb-audio index=-2'
NEW='options snd-usb-audio index=0\noptions snd_bcm2835 index=-2'
sudo sed -i -e "s/$OLD/$NEW/g" /lib/modprobe.d/aliases.conf

#allows python path to be kept after sudo command
OLD='env_reset'
NEW='env_keep += "PYTHONPATH"'
sudo sed -i -e "s/$OLD/$NEW/g" /etc/sudoers

# this will disable on-board bluetooth for the class one blue-tooth
sudo echo "dtoverlay=pi3-disable-bt" | sudo tee -a /boot/config.txt
sudo systemctl disable hciuart

#remove onboard bluetooth folders
sudo rm -rf /var/lib/bluetooth/*

sudo reboot