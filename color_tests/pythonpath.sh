#sets the username of the system, supervisord does not have a login
#so we need to use the who command. 
HOMENAME=`who | head -n1 | cut -d " " -f1`

export PSMOVEAPI_LIBRARY_PATH=/home/$HOMENAME/psmoveapi/build
export PYTHONPATH=/home/$HOMENAME/psmoveapi/bindings/python
