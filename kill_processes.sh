#!/bin/bash

kill $(ps aux | grep 'supervisor' | awk '{print $2}')
kill $(ps aux | grep 'oust' | awk '{print $2}')
