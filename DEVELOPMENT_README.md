in order to develop for Joustmania there are two scripts that help

first cd into the Joustmania directory

next run:
`sudo ./kill_processes.sh`

this will stop all running Joust mania processes in the background and stop supervisor from restarting them

then run:
`source pythonpath.sh`

this imports the psmove api so that python can find it's libraries

finally run:
`sudo python3 piparty.py`

and the game should be running locally in your terminal!

Happy development!
