#!/bin/bash

#update OS
sudo apt-get dist-upgrade -y
sudo apt-get update -y
cd /home/pi

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

#Pip installs
sudo pip install bluetooth
