![Magfest 2017](logo/magfest.jpg)
JoustMania at Magfest 2017!
![PiParty Logo](logo/PiPartyLogo2.png)

What is JoustMania????
--------------------------------------

* JoustMania is a collection of PlayStation Move enabled party games based off of the "Jostling" mechanic introduced in [Johann Sebastian Joust](http://www.jsjoust.com/)
* JoustMania includes FFA, Teams, Werewolves, Zombies, Commander modes, and lots of other goodies!
* The system is also designed to be easy to set up at conventions and is made to run itself with a large group of people. In convention mode, every game is started once everyone is ready, and announces the rules aloud for new players to learn.

Cool Stuffs!
--------------------------------------

* 16+ Player support
* Super easy setup
* Runs in Headless mode, no screen required
* Optional web interface, view status and change game settings with your phone
* Custom music support, play with your own music
* Convention mode, no manual instructions needed, the game plays itself and switches between game modes

Hardware
---------------------------
You will need the following to run JoustMania:

0. A Raspberry Pi 3 B with sd card
0. External USB sound card (https://goo.gl/S4vDXF)

Optional and **highly recommended**:

* Class 1, Bluetooth 4.0 USB adapters (https://goo.gl/q0j0Fu)

Note on Hardware: The internal bluetooth is short range and has a high latency, making gameplay laggy and slow, although still possible.
The class 1 adapters allow bluetooth connections up to 300+ feet and allow for the gameplay to be smooth, each adapter can connect to 6 to 7 controllers. I've tested this build with three adapters and 16 controllers successfully.

Optional:

* USB hub for charging controllers (https://www.amazon.com/dp/B00POYDAGS/)

This will allow you to charge 9 controllers at once through the pi

Installation
---------------------------

0. [Download](https://www.raspberrypi.org/downloads/raspbian/) and [Install](https://www.raspberrypi.org/documentation/installation/installing-images/README.md) Raspbian on the micro SD card
0. Connect the USB Soundcard and bluetooth adapters
0. Turn on the pi, open a Terminal and run these commands, the pi will reboot on a successful install
```
git clone https://github.com/adangert/JoustMania.git
cd JoustMania
sudo ./setup.sh
```
If you have the bluetooth adapters, disable the on-board bluetooth 
```
sudo ./disable_internal_bluetooth.sh
```
You can now disconnect the hdmi cable and run JoustMania in headless mode. JoustMania will automatically boot up on restart.

Update Joust Mania
---------------------------
You can update Joust Mania by doing a `git pull` in the main directory and rebooting the pi.


Pairing controllers
---------------------------

* Once you have installed JoustMania, in order to pair controllers, plug them into the Raspberry Pi via USB
* Once plugged in a controller should turn white indicating that it has been paired correctly
* After a controller has been synced via USB, press the PlayStation sync button (the circular one in the middle) to connect the controller to the Pi
* This process should only need to be done once, after this the controller should be permenently paired with the Pi and will only need to be turned on via the sync button for any future games
* All the controllers may restart when pairing, this is expected, just keep plugging in new ones until they are all paired. if you encounter problems restart the Pi, and continue pairing the remaining controllers, again once this process is finished you should not have to connect the controllers to the Pi again via USB

If pairing is not working for some reason, or you would like to resync all controllers run the following
```
sudo -i
cd /home/pi/JoustMania/
./reset_bluetooth_connections.sh
```

How to select a game mode
---------------------------------
* In order to change between games, on any controller press the select button (located on the left side of a controller)
* Changing game types will turn you into an Admin
* Press start (located on the right side) on any controller to launch the selected game
* In order to remove a controller from play press all four front buttons

Admin Mode (Sensitivity and convention mode settings)
---------------------------------
You can become an Admin by changing the game mode via the select button, this will allow you to modify the games settings from the four front buttons on the controller, After a game is played the Admin mode will be reset

* (Cross) Add or remove a game from Convention mode, your controller will be green if the game is added and Red if it is not, Custom Teams mode can not be added to the Convention mode
* (Circle) Change sensitivity of the game. There are three settings, slow, medium, and fast, you will hear a corresponding sound for each
* (Square) toggle the playback of instructions for each game
* (Triangle) show battery level on all controllers

Web Interface
---------------------------------
Joustmania can also be controlled via a web browser on your laptop or smartphone. If your Pi is on a network, use the IP address of your Pi (for example, http://192.168.1.xxx/). Alternatively, you can turn your Pi in to an access point and connect your device directly to it. To enable this,  run the command
```
sudo ./enable_ap.sh
```
Note that this disables normal Wi-Fi on the Pi, but a wired connection will still work. The default SSID is "JOUSTMANIA" and the default password is "joustmania"; both (and other) settings may be adjusted in the apfiles/hostapd.conf file before running enable_ap.sh. To connect to the game, go to http://joust.mania in your web browser. To disable the access point and restore Wi-Fi, run the command
```
sudo ./disable_ap.sh
```

The web interface is currently a WIP. Known issues are:
* The settings menu does not update if modified from a Move controller or another device via web browser
* Newer game modes may not properly dispaly game status

Custom Music
---------------------------------
* JoustMania comes with a single classical music piece
* Play your own music, by copying it into the respective folders: /audio/(Joust, Zombie, Commander)/music/
* WAV files currently supported
* All music and audio can be disabled by changing `audio = False` in joustconfig.ini, this will also disable tempo sensitivity changes for each game mode


# Game Rules and Variants 
* Keep your controller still while trying to jostle others.
* If your controller is jostled then you are out of the game
* The music is tied to the gameplay, the faster the music the faster you can move
* recommended player count is listed next to every game mode
* Extended rules can be found on the [Wiki](https://github.com/adangert/JoustMania/wiki/Extended-Rules)


 ### Convention/Random mode
 * This is the first mode that JoustMania boots to
 * This mode allows for multiple game types to be randomly rotated with instructions played before each game
 * Convention mode will only start with FFA in rotation, more game modes can be added as an Admin (see above)
 * All players press the A button (middle of controller) to signal they are ready to play, and the game will begin


 ### FFA
 * The most basic version of Joust; be the last one standing!


 ### Teams
 * This game is the same as Joust FFA however at the beginning players select their team color with the big button in the middle of their controller
 * There are six teams to select from


 ### Random Teams
 * Same as Joust Teams, however the teams are randomly assigned at start of play
 * There are three teams in this mode


 ### Traitor
 * Three teams face off against one another, however there is a traitor on every team
 * Traitors are on a secret fourth team
 * If you controller vibrates during the start countdown you are a traitor


 ### Werewolves
 * Hidden werewolves are selected at the beginning of the game.
 * When the countdown starts the werewolf will feel a vibration, letting that player know they are a werewolf
 * After a short period of time, werewolves will be revealed
 * Werewolves win only if they are the last remaining


 ### Zombies
 * Two players start out as zombies, and try to infect the humans
 * Humans can shoot random zombies with bullets
 * Bullets are randomly assigned as loot from killing zombies
 * Humans try to survive for a couple of minutes, otherwise zombies win!
 
 
 ### Commander
 * Teams are split into two sides
 * One commander is chosen for each side, if this commander dies, the other team wins
 * Commanders can activate special abilities that helps their team win


 ### Swapper
 * Players start on two teams
 * When you die, you switch to the other team
 * The last person remaining does not switch


 ### Tournament
 * Everyone is paired up 1v1 via controller colors
 * If your controller is white, wait to be assigned to a new player
 * The last person remaining wins!


 ### Ninja Bomb
 * Players stand in a circle each holding a controller
 * Players press A to join the game. 
 * A bomb is passed around by pressing the A button, if held too long it will explode
 * Players can try to pass a traps in order to fake out their opponents.
 * If a player presses A or trigger while holding a trap, they explode
 * Traps are passed by holding the trigger-button half way, too much or too little and you'll give yourself away
 * Traps can also be countered by pressing any of the four front buttons.
 * Players have two lives, the last player remaining wins!
