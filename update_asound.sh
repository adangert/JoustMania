#!/bin/bash

# Prevent apt from prompting us about restarting services.
export DEBIAN_FRONTEND=noninteractive
HOMENAME=`logname`
HOMEDIR=/home/$HOMENAME
cd $HOMEDIR

#This is needed to hear espeak with sudo (adjusting asound.conf)
#adds asound.conf to /etc/ This is important for audio to play
#out of the headphone jack, sudo aplay <wav file> does weird things
#and setting it to the correct device(headphones) (hw:<HEADPHONE NUMBER>,0) 
#Allows multiple streams to play at the same time


#The pi 4 headphones do not like the dmixer and give a
#ALSA: Couldn't open audio device: Invalid argument
#However the USB input needs a dmixer for multiple streams to work
#This is why we are splitting up the below logic for both
#the pi4 and pi5 (which requires a usb audio jack).
echo "Now trying to get the audio card"
#Get the sudo aplay -l line corresponding to the headphones
headphones_info=$(sudo aplay -l | grep -Ei 'Headphones')
echo "headphones_info is $headphones_info"
if [ ! -z "$headphones_info" ]; then
	echo "Headphones found, likely a pi 4, updating asound.conf"
	#Get the card number from the headphones_info(tested 0 on bullseye, 2 on bookworm)
	card_number=$(echo "$headphones_info" | sed -n 's/^card \([0-9]*\):.*$/\1/p' | head -n 1) || exit -1
	echo "headphones card_number is $card_number"
	#update the asound.conf to have the correct card to play from, copy to /etc
	sed -i "s/pcm \"hw:[0-9]*,/pcm \"hw:$card_number,/g" $HOMEDIR/JoustMania/conf/asound_pi_4.conf || exit -1
	sed -i "s/card [0-9]*/card $card_number/g" $HOMEDIR/JoustMania/conf/asound_pi_4.conf || exit -1
	sudo cp $HOMEDIR/JoustMania/conf/asound_pi_4.conf /etc/asound.conf || exit -1
else
	echo "Headphones not found, likely a pi 5"
fi
	
USB_info=$(sudo aplay -l | grep -Ei 'USB')
if [ ! -z "$USB_info" ]; then
	echo "USB audio jack found, likely a pi 5, updating asound.conf"
	#Get the card number from the headphones_info(tested 0 on bullseye, 2 on bookworm)
	card_number=$(echo "$USB_info" | sed -n 's/^card \([0-9]*\):.*$/\1/p' | head -n 1) || exit -1
	echo "USB card_number is $card_number"
	#update the asound.conf to have the correct card to play from, copy to /etc
	sed -i "s/pcm \"hw:[0-9]*,/pcm \"hw:$card_number,/g" $HOMEDIR/JoustMania/conf/asound.conf || exit -1
	sed -i "s/card [0-9]*/card $card_number/g" $HOMEDIR/JoustMania/conf/asound.conf || exit -1
	sudo cp $HOMEDIR/JoustMania/conf/asound.conf /etc/ || exit -1
else
	echo "No USB audio jack found, likely a pi 4"
fi
exit -1
