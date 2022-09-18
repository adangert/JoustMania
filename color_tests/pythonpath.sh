#sets the username of the system, supervisord does not have a login
#so we need to use the who command. 
HOMENAME=`who | head -n1 | cut -d " " -f1`

export PYTHONPATH=/home/$HOMENAME/psmoveapi/build/
