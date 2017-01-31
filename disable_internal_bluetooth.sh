# this will disable on-board bluetooth
#this will allow only class one long range btdongles to connect to psmove controllers
sudo echo "dtoverlay=pi3-disable-bt" | sudo tee -a /boot/config.txt
sudo systemctl disable hciuart

#remove onboard bluetooth folders
sudo rm -rf /var/lib/bluetooth/*

sudo reboot
