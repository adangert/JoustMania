#!/bin/bash

#this is for development purposes only, to stop the automattically
#running piparty scripts
sudo supervisorctl stop joustmania
sudo kill -9 $(ps aux | grep '[p]iparty' | awk '{print $2}')
