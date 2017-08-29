#!/bin/bash

#update OS
sudo apt-get dist-upgrade -y
sudo apt-get update -y
cd /home/pi

#TODO: remove pyaudio and dependencies
#install components
sudo apt-get install -y \
    python-dev bluez python3-pyaudio \
    python-pip python3-numpy supervisor \
    python3-scipy python3-pygame cmake \
    libudev-dev swig libbluetooth-dev \
    alsa-utils alsa-tools libasound2-dev
sudo pip3 install psutil flask Flask-WTF pyalsaaudio

#install components for psmoveapi
sudo apt-get install -y \
    build-essential \
    libv4l-dev libopencv-dev \
    libudev-dev libbluetooth-dev \
    python-dev swig3.0

#install psmoveapi
git clone --recursive git://github.com/thp/psmoveapi.git
cd psmoveapi

mkdir build
cd build
# we definitely don't need java, opengj, csharp, etc
cmake .. \
    -DPSMOVE_BUILD_CSHARP_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_JAVA_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_OPENGL_EXAMPLES:BOOL=OFF \
    -DPSMOVE_BUILD_PROCESSING_BINDINGS:BOOL=OFF \
    -DPSMOVE_BUILD_TESTS:BOOL=OFF \
    -DPSMOVE_BUILD_TRACKER:BOOL=ON \
    -DPSMOVE_USE_PSEYE:BOOL=OFF
make -j4

#installs custom supervisor script for running joustmania on startup
sudo cp -r /home/pi/JoustMania/supervisor/ /etc/

#sound card is not required anymore TODO: eventually delete
#makes sound card 1(usb audio) to be default output
#use aplay -l to check sound card number
#sudo cp /home/pi/JoustMania/asound.conf /etc/


#allows python path to be kept after sudo command
OLD='env_reset'
NEW='env_keep += "PYTHONPATH"'
sudo sed -i -e "s/$OLD/$NEW/g" /etc/sudoers

sudo reboot
