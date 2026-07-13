#!/bin/bash

#for debugging the webui without starting the whole app

#root needed since psmove still gets imported
if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

#sets the username of the system, supervisord does not have a login
#so we need to use the who command. 
HOMENAME=`who | head -n1 | cut -d " " -f1`

export HOME="/home/$HOMENAME/JoustMania"
export PSMOVEAPI_LIBRARY_PATH="/home/$HOMENAME/psmoveapi/build"
export PYTHONPATH="/home/$HOMENAME/psmoveapi/bindings/python"
/home/$HOMENAME/JoustMania/venv/bin/python3 /home/$HOMENAME/JoustMania/webui.py
