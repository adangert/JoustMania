#!/bin/bash

setup() {
    # Prevent apt from prompting us about restarting services.
    export DEBIAN_FRONTEND=noninteractive
    HOMENAME=`logname`
    HOMEDIR=/home/$HOMENAME
    cd $HOMEDIR
    sudo apt-get install -y espeak
    
    #This is needed to hear espeak with sudo (adjusting asound.conf)
    #adds asound.conf to /etc/ This is important for audio to play
    #out of the headphone jack, sudo aplay <wav file> does weird things
    #and setting it to the correct device(headphones) (hw:<HEADPHONE NUMBER>,0) 
    #Allows multiple streams to play at the same time
    
    #Get the sudo aplay -l line corresponding to the headphones
    headphones_info=$(sudo aplay -l | grep -i 'Headphones') || exit -1
    
    #Get the card number from the headphones_info(tested 0 on bullseye, 2 on bookworm)
    card_number=$(echo "$headphones_info" | sed -n 's/^card \([0-9]*\):.*$/\1/p' | head -n 1) || exit -1
    
    #update the asound.conf to have the correct card to play from, copy to /etc
    sed -i "s/pcm \"hw:[0-9]*,/pcm \"hw:$card_number,/g" $HOMEDIR/JoustMania/conf/asound.conf || exit -1
    sudo cp $HOMEDIR/JoustMania/conf/asound.conf /etc/ || exit -1

    espeak "starting software upgrade"
    sudo apt-get update -y || exit -1
    sudo apt-get upgrade -y || exit -1

    espeak "Installing required software dependencies"
    #TODO: remove pyaudio and dependencies
    #install components
    sudo apt-get install -y  \
        python3 python3-dev python3-pip \
        python3-pkg-resources python3-setuptools libdpkg-perl \
        libsdl1.2-dev libsdl-mixer1.2-dev libsdl-sound1.2-dev \
        libportmidi-dev portaudio19-dev \
        libsdl-image1.2-dev libsdl-ttf2.0-dev \
        libblas-dev liblapack-dev \
        iptables rfkill supervisor cmake ffmpeg \
        libudev-dev swig libbluetooth-dev \
        alsa-utils alsa-tools libasound2-dev libsdl2-mixer-2.0-0 \
        python-dbus-dev python3-dbus libdbus-glib-1-dev usbutils espeak libatlas-base-dev \
        python3-pyaudio python3-psutil || exit -1

    espeak "Installing PS move A.P.I. software updates"
    #install components for psmoveapi
    sudo apt-get install -y \
        build-essential \
        libv4l-dev libopencv-dev \
        libudev-dev libbluetooth-dev \
        libusb-dev || exit -1

    espeak "Installing software libraries"
    VENV=$HOMEDIR/JoustMania/venv
    # We install nearly all python deps in the virtualenv to avoid concflicts with system, except
    # numpy and scipy because they take forever to build.
    sudo apt-get install -y libasound2-dev libasound2 python3-scipy cmake || exit -1

    #install the python3 dev environment
    echo "about to install python3-dev and virtualenv"
    sudo apt-get install -y python3-dev || exit -1
    sudo apt-get install -y python3-virtualenv || exit -1
    
    espeak "installing virtual environment"
    # Rebuilding this is pretty cheap, so just do it every time.
    rm -rf $VENV
    /usr/bin/python3 -m virtualenv --system-site-packages $VENV || exit -1
    PYTHON=$VENV/bin/python3
    espeak "installing virtual environment dependencies"
    $PYTHON -m pip install --ignore-installed flask Flask-WTF pyalsaaudio pydub pyyaml dbus-python || exit -1
    #Sometimes pygame tries to install without a whl, and fails (like 2.4.0) this
    #checks that only correct versions will install
    $PYTHON -m pip install --ignore-installed --only-binary ":all:" pygame || exit -1

    espeak "downloading PS move API"
    #install psmoveapi (currently adangert's for opencv 3 support)
    rm -rf psmoveapi
    git clone --recursive https://github.com/thp/psmoveapi.git || exit -1
    cd psmoveapi || exit -1
    git checkout 8a1f8d035e9c82c5c134d848d9fbb4dd37a34b58 || exit -1

    espeak "compiling PS move API components"
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
    
    #change the supervisord directory to our own homename
    #this replaces pi default username in joust.conf,
    sed -i -e "s/pi/$HOMENAME/g" $HOMEDIR/JoustMania/conf/supervisor/conf.d/joust.conf || exit -1
    
    
    #installs custom supervisor script for running joustmania on startup
    sudo cp -r $HOMEDIR/JoustMania/conf/supervisor/ /etc/ || exit -1
    

    
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
        espeak "permisions updated, please wait after reboot for Joustmania to start"
    else
        echo "no permissions to update"
    fi
    
    #gets just the version of bluetooth
    BT_VERSION=$(bluetoothctl -v | cut -d' ' -f2)
    
    if [ "$1" != "--ps4_only" ] && [ "$2" != "--ps4_only" ] && [ "${BT_VERSION}" != "5.65" ]  ; then
        
        #Installing Bluez v 5.65 (version 5.66 is broken, and will not pair PS3 controllers, issue #316)
        #To uninstall this bluez version, go into this folder /joustmania/bluez-5.65 and run, sudo make uninstall
        echo "installing bluez version 5.65"
        espeak "Installing bluetooth version 5.65"
        
        sudo apt-get remove bluez -y || exit -1
        
        #Install Bluez dependencies for building:
        sudo apt-get install libdbus-1-dev libglib2.0-dev libudev-dev libical-dev libreadline-dev -y || exit -1
        
        #download bluez version 5.65
        wget www.kernel.org/pub/linux/bluetooth/bluez-5.65.tar.xz || exit -1
        
        #Uncompress the downloaded file.
        tar xvf bluez-5.65.tar.xz && cd bluez-5.65 || exit -1
        
        #Configure, compile, and install bluez
        ./configure --prefix=/usr --mandir=/usr/share/man --sysconfdir=/etc --localstatedir=/var --enable-experimental || exit -1
        make -j4 || exit -1
        sudo make install || exit -1
        
        #check new bluetooth version:
        bluetoothctl -v || exit -1
    else
        echo "bluez version already at 5.65, nothing to do"
    fi
    
    echo "joustmania successfully updated, now rebooting"
    espeak "Joustmania successfully updated, now rebooting"
    # Pause a second before rebooting so we can see all the output from this script.
    (sleep 2; sudo reboot) &
}

setup $1 2>&1 | tee setup.log
