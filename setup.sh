#!/bin/bash

setup() {
    # Prevent apt from prompting us about restarting services.
    export DEBIAN_FRONTEND=noninteractive
    HOMENAME=`logname`
    HOMEDIR=/home/$HOMENAME
    cd $HOMEDIR

    #This was causing some errors updating below (stuck on looking for font directory)
    sudo apt-get remove realvnc-vnc-server -y

    echo "starting software upgrade"
    sudo apt-get update -y || exit -1
    sudo apt-get upgrade -y || exit -1
    

    echo "Installing required software dependencies"
    #TODO: remove pyaudio and dependencies
    #install components
    sudo apt-get install -y \
        python3 python3-dev python3-pip \
        python3-pkg-resources python3-setuptools libdpkg-perl \
        libsdl1.2-dev libsdl-mixer1.2-dev libsdl-sound1.2-dev \
        libportmidi-dev portaudio19-dev \
        libsdl-image1.2-dev libsdl-ttf2.0-dev \
        libblas-dev liblapack-dev \
        bluez bluez-tools iptables rfkill supervisor cmake ffmpeg \
        libudev-dev swig libbluetooth-dev \
        alsa-utils alsa-tools libasound2-dev libsdl2-mixer-2.0-0 \
        python-dbus-dev python3-dbus libdbus-glib-1-dev usbutils libatlas-base-dev \
        python3-pyaudio python3-psutil || exit -1

    echo "Installing PS move A.P.I. software updates"
    #install components for psmoveapi
    sudo apt-get install -y \
        build-essential \
        libv4l-dev libopencv-dev \
        libudev-dev libbluetooth-dev \
        libusb-dev || exit -1

    echo "Installing software libraries"
    VENV=$HOMEDIR/JoustMania/venv
    # We install nearly all python deps in the virtualenv to avoid concflicts with system, except
    # numpy and scipy because they take forever to build.
    sudo apt-get install -y libasound2-dev libasound2 python3-scipy cmake || exit -1

    #install the python3 dev environment
    echo "about to install python3-dev and virtualenv"
    sudo apt-get install -y python3-dev || exit -1
    sudo python3 -m pip install -U uv || exit -1
    
    echo "installing virtual environment"
    uv venv --system-site-packages $VENV || exit -1
    PYTHON=$VENV/bin/python3

    echo "installing virtual environment dependencies"
    uv pip install -p $PYTHON flask Flask-WTF pyalsaaudio pydub pyyaml dbus-python python-dotenv || exit -1

    #Sometimes pygame tries to install without a whl, and fails (like 2.4.0) this
    #checks that only correct versions will install
    uv pip install -p $PYTHON --only-binary ":all:" pygame || exit -1

    echo "downloading PS move API"
    #install psmoveapi (currently adangert's for opencv 3 support)
    rm -rf psmoveapi
    git clone --recursive https://github.com/thp/psmoveapi.git || exit -1
    cd psmoveapi || exit -1
    git checkout 8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58 || exit -1

    echo "compiling PS move API components"
    mkdir build
    cd build
    cmake .. \
        -DPSMOVE_BUILD_CSHARP_BINDINGS:BOOL=OFF \
        -DPSMOVE_BUILD_EXAMPLES:BOOL=OFF \
        -DPSMOVE_BUILD_JAVA_BINDINGS:BOOL=OFF \
        -DPSMOVE_BUILD_OPENGL_EXAMPLES:BOOL=OFF \
        -DPSMOVE_BUILD_PROCESSING_BINDINGS:BOOL=OFF \
        -DPSMOVE_BUILD_TESTS:BOOL=OFF \
        -DPSMOVE_BUILD_TRACKER:BOOL=OFF \
        -DPSMOVE_USE_PSEYE:BOOL=OFF || exit -1
    make -j4 || exit -1
    
    CONFIG_DIR="/etc/supervisor/conf.d"
    CONFIG_FILE="$CONFIG_DIR/joust.conf"
    
    #installs custom supervisor script for running joustmania on startup
    sudo cp -r $HOMEDIR/JoustMania/conf/supervisor/ /etc/ || exit -1
    
    #change the supervisord directory to our own homename
    #this replaces pi default username in the supervisor joust.conf
    sudo sed -i -e "s|/home/[^/]*\/JoustMania|$HOMEDIR/JoustMania|g" $CONFIG_FILE || exit -1
    
    
    #Use amixer to set sound output to 100% (This looks somewhat broken, potentially remove it)
    #unable to find simple control 'PCM',0
    amixer sset PCM,0 100%
    sudo alsactl store
    
    DIST_REL=$(cut -f2 <<< $(lsb_release -r))
    if [ "$DIST_REL" -ge 12 ]; then
        echo "the distribution $DIST_REL is larger than 12" 
        config_loc=/boot/firmware/config.txt || exit -1
    else
        echo "the distribution is smaller than 12"
        config_loc=/boot/config.txt || exit -1
    fi
        
    
    
    #This will disable on-board bluetooth with the --disable_internal_bt command line option
    #This will allow only class one long range btdongles to connect to psmove controllers
    if [ "$1" = "--disable_internal_bt" ]; then
        echo "disabling internal bt"
        sudo grep -qxF 'dtoverlay=disable-bt' $config_loc || { echo "dtoverlay=disable-bt" | sudo tee -a $config_loc; sudo rm -rf /var/lib/bluetooth/*; } || exit -1
        sudo systemctl disable hciuart || exit -1
    fi

    uname2="$(stat --format '%U' $HOMEDIR'/JoustMania/setup.sh')"
    uname3="$(stat --format '%U' $HOMEDIR'/JoustMania/piparty.py')"
    if [ "${uname2}" = "root" ] || [ "${uname3}" = "root" ] ; then
        sudo chown -R $HOMENAME:$HOMENAME $HOMEDIR/JoustMania/ || exit -1
        echo "permisions updated, please wait after reboot for Joustmania to start"
    else
        echo "no permissions to update"
    fi
    
    
    #This will change ClassiBondedOnly to false in /etc/bluetooth/input.conf
    #needed for pairing the PS3 controllers: https://github.com/thp/psmoveapi/issues/489
    sudo sed -i '/^#\?ClassicBondedOnly=\(true\|false\)$/s/.*/ClassicBondedOnly=false/' '/etc/bluetooth/input.conf'
    
    
    echo "joustmania successfully updated, now rebooting"
    #es[eak "Joustmania successfully updated, now rebooting"
    # Pause a second before rebooting so we can see all the output from this script.
    (sleep 2; sudo reboot) &
}

setup $1 2>&1 | tee setup.log
