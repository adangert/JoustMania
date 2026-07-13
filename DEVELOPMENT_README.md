In order to develop for Joustmania there are two scripts that help

first cd into the Joustmania directory

next run:
`sudo ./stop_joustmania.sh`

this will stop all running Joust mania processes in the background and stop supervisor from restarting them

then run:
`sudo ./joust.sh`

and the game should be running locally in your terminal!

To return JoustMania to Supervisor after development, run:
`sudo ./start_joustmania.sh`

You can run unit tests with the provided shell script:
`./tests`

Happy development!
