#!/bin/bash

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

#sets the username, supervisord does not have a login when running joustmania
HOMENAME=`who | head -n1 | cut -d " " -f1`
export HOME="/home/$HOMENAME/JoustMania"
export PYTHONPATH="/home/$HOMENAME/psmoveapi/build/"
exec /home/$HOMENAME/JoustMania/venv/bin/python3 /home/$HOMENAME/JoustMania/controller_util.py
