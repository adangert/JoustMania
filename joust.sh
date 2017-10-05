#!/bin/bash

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

export HOME="/home/pi/JoustMania"
exec /home/pi/JoustMania/venv/bin/python3.6 /home/pi/JoustMania/piparty.py
