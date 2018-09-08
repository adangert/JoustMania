#!/bin/bash

#for debugging the webui without starting the whole app

#root needed since psmove still gets imported
if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

export HOME="/home/pi/JoustMania"
export PYTHONPATH="/home/pi/psmoveapi/build/"
/home/pi/JoustMania/venv/bin/python3.6 /home/pi/JoustMania/webui.py
