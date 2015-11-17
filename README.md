PI PARTY!!
--------------------------------------

A collection of movement games designed for the raspberry pi

[Johann Sebastian Joust](http://www.jsjoust.com/) started the movement based party game genre, since that time there have been various implementations of this awesome game including [Jonty's oust](https://github.com/Jonty/Oust)

This collection of games attempts to expand upon the basic joust gameplay with new modes, as well as entirely new games. 

it has been currently tested on 12 move controllers successfully, with both FFA and Team modes, more modes and games coming soon!

Hardware
---------------------------
You will need the following to run PI party:

0. a raspberry pi 2 B+
0. micro SD card for the raspberry pi
0. up to 3, Class 1, Bluetooth 4.0 usb adapters (each adapter can handle 6-7 move controllers)
0. an external USB sound card
0. an external battery (the larger the better)
0. a speaker, preferably portable
0. as many playstation move controllers as you can handle

Installation
---------------------------

0. [Download](https://www.raspberrypi.org/downloads/raspbian/) and [Install](https://www.raspberrypi.org/documentation/installation/installing-images/README.md) Raspbian on the micro SD card (this has been tested with the Wheezy release)
0. connect your bluetooth adapters, external USB Soundcard, ethernet conneciton, and keyboard, mouse and hdmi to the pi.
0. plug in the power and wait for the boot menu on screen
0. select to expand the Filesystem (option 1) and Boot to Desktop as a pi user (option 3), then hit finish and reboot.
0. open a Terminal located at the top of the desktop (the black monitor icon) and run these commands:
```
git clone https://github.com/aangert/PiParty.git
cd PiParty
sudo ./setup.sh
```
0.wait until it's finished, and you're done!!

Pairing controllers
---------------------------

* once you have installed PiParty, in order to pair controllers, plug them into the raspberry pi via usb, and wait until the bulb turns white. 
* This process should only need to be done once, after this the controllers should be permenently paired and will only need to be turned on via the circular sync button on the front of the move controller for any future games
* if the controller does not turn white, this means that the process probably crashed due to a kernal bug with the psmoveapi, restart the the pi and then plug in an pair the remaining controllers, 
* The controller led should turn a solid red when it's paired successfully.

Games (More coming soon!!)
---------------------------------

* In order to change between games, someone needs to press the select button (left side of the controller)

Joust FFA
---------------------------------

0. All the controllers are dark. As the players press the squishy trigger their controller lights up white.
0. When someone presses start(right side of the controller), the controllers will vibrate, then flash red/yellow/green as a "get ready" signal.
0. Every controller turns a different colour and the game has begun.
0. The aim of the game is to force all the other players to move their controllers too fast, either by hitting the controller, making them flinch, or the other player doing something stupid.
0. The sensitivity of the controllers is tied to the music, when the music speeds up, you are able to move faster
0. If your controller is going too fast it'll flicker as a warning.
0. If you are knocked out, your controller goes dark and vibrates.
0. The last player standing has their controller flash a beautiful rainbow sequence, and all controllers vibrate to indicate the end of the game.
0. The game resets, people hand their controllers to other people to play. GOTO 1.

Joust Teams
---------------------------------

* This game is the same as Joust FFA however at the beginning players select their team color with the big button in the middle of their controller
* The last team standing wins!


Things You Should Know
----------------------
* The Playstation Move controllers need a computer to charge or a docking station, I would reccomend buying charging stations, just because they are cheap and make life much easier once you have a ton of controllers


Things to do
----------------------
* Create more games and modes!
* Test out 16+ move controllers
* add freeze mode for Joust, and music selection

