#!/bin/bash
# Disable onboard Bluetooth at boot without deleting controller pairings.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sudo /usr/bin/python3 "$script_dir/internal_bluetooth.py" disable || exit 1
sudo reboot
