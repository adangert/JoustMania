#!/usr/bin/env bash

set -e

if [ "$UID" -ne 0 ]; then
    exec sudo "$0" "$@"
fi

supervisorctl start joustmania
