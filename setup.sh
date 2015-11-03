#!/bin/bash
pwd
sudo apt-get update -y
sudo apt-get dist-upgrade -y
pwd
cd ..
pwd
git clone https://github.com/thp/psmoveapi.git

cd psmoveapi
pwd
git remote add jmacarthur https://github.com/jmacarthur/psmoveapi.git
git fetch jmacarthur
git cherry-pick -n e3838a5c49313b8865ff493573aa417e8e4a391b

sudo apt-get install -y swig python-dev bluez python-pyaudio python-pip python-numpy python-setuptools libsamplerate0-dev

sudo pip install scikits.samplerate psutil

git submodule init
git submodule update

sudo apt-get install -y build-essential cmake libudev-dev libbluetooth-dev libv4l-dev libopencv-dev
pwd
mkdir build
cd build
pwd
cmake ..
make -j4

OLD='options snd-usb-audio index=-2'
NEW='options snd-usb-audio index=0\noptions snd_bcm2835 index=-2'

sudo sed -i -e "s/$OLD/$NEW/g" /etc/modprobe.d/alsa-base.conf

OLD='env_reset'
NEW='env_keep += "PYTHONPATH"'

sudo sed -i -e "s/$OLD/$NEW/g" /etc/sudoers

sudo apt-get install -y supervisor

sudo cp -r /home/pi/PiParty/supervisor/ /etc/

sudo reboot
