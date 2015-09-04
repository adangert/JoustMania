#!/bin/bash
set -eo pipefail

devices=$(hcitool dev | grep hci | awk '{print $1}')

for device in $devices
do
    scan_enable=$(hcitool -i ${device} cmd 0x3 0x19|grep -A1 'HCI Event'|tail -1|cut -d\  -f7)
    if [[ "$scan_enable" == '00' ]]; then
        echo "Scan disabled, enabling"
        # Could also use hciconfig hci0 pscan
        success=$(hcitool -i ${device} cmd 0x3 0x1a 0x2|grep -A1 'HCI Event'|tail -1|cut -d\  -f6)
        if [[ "$success" != '00' ]]; then
            echo "Scan enable failed"
            exit 1
        fi
        echo "Scan now enabled for ${device}"
    else
        echo "Scan already enabled on ${device}"
    fi
done
