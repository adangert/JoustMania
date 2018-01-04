#!/bin/bash

setup() {
    # Prevent apt from prompting us about restarting services.
    export DEBIAN_FRONTEND=noninteractive

    #update OS
    sudo cp -v conf/sources.list /etc/apt/sources.list || exit -1
    sudo cp -v conf/apt.conf /etc/apt/apt.conf.d/10joustmania-conf || exit -1
    sudo apt-get update -y || exit -1
    sudo apt-get upgrade -y || exit -1
    sudo apt-get dist-upgrade -y || exit -1
    cd /home/pi

    #TODO: remove pyaudio and dependencies
    #install components
    sudo apt-get install -y  \
        python3 python3-dev python3-pip \
        python3-pkg-resources python3-setuptools libdpkg-perl \
        libsdl1.2-dev libsdl-mixer1.2-dev libsdl-sound1.2-dev \
        libportmidi-dev portaudio19-dev \
        libsdl-image1.2-dev libsdl-ttf2.0-dev \
        libblas-dev liblapack-dev \
        bluez bluez-tools rfkill supervisor cmake ffmpeg \
        libudev-dev swig libbluetooth-dev \
        alsa-utils alsa-tools libasound2-dev \
        python-dbus-dev libdbus-glib-1-dev espeak || exit -1

    #install components for psmoveapi
    sudo apt-get install -y \
        build-essential \
        libv4l-dev libopencv-dev \
        libudev-dev libbluetooth-dev \
        swig3.0 || exit -1



    VENV=/home/pi/JoustMania/venv
    # We install nearly all python deps in the virtualenv to avoid concflicts with system, except
    # numpy and scipy because they take forever to build.
    sudo apt-get install -y -t buster libasound2-dev libasound2 python3-scipy
    sudo python3.6 -m pip install --upgrade virtualenv || exit -1

    # Rebuilding this is pretty cheap, so just do it every time.
    rm -rf $VENV
    /usr/bin/python3.6 -m virtualenv --system-site-packages $VENV || exit -1
    PYTHON=$VENV/bin/python3.6
    $PYTHON -m pip install --ignore-installed psutil flask Flask-WTF pyalsaaudio pydub pygame pyaudio pyyaml dbus-python || exit -1

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
    cp /home/pi/psmoveapi/build/{psmove.py,_psmove.so} $VENV/lib/python3.6

    #installs custom supervisor script for running joustmania on startup
    sudo cp -r /home/pi/JoustMania/conf/supervisor/ /etc/

    #sound card is not required anymore TODO: eventually delete
    #makes sound card 1(usb audio) to be default output
    #use aplay -l to check sound card number
    #sudo cp /home/pi/JoustMania/asound.conf /etc/
    
    #Use amixer to set sound output to 100%
    amixer sset PCM,0 100%
    sudo alsactl store

    # Pause a second before rebooting so we can see all the output from this script.
    (sleep 1; sudo reboot) &
}

setup 2>&1 | tee setup.log
