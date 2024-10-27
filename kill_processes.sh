#!/bin/bash

#this is for development purposes only, to stop the automattically
#running piparty scripts
sudo supervisorctl stop joustmania
sudo kill -9 $(ps aux | grep 'JoustMania-' | awk '{print $2}')
