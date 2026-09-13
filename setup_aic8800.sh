#!/bin/bash
# Optional AICSemi firmware-loader setup, called by setup.sh when detected.
set -euo pipefail
if [[ "${1:-}" != "--install" ]]; then
    if ! lsusb | grep -Eiq 'a69c:(5732|8d80)|368b:8d81'; then
        echo "No tested AIC8800 combo adapter detected; skipping its driver."
        exit 0
    fi
fi
if [[ $EUID -ne 0 ]]; then
    exec sudo bash "$0" --install
fi
# Pin the vendor package we built and tested; never execute a remote installer.
package_sha=5abe730ee9edec292a894f5cdf407c205491b8c57fd39b87886aae3785cd5fac
package_dir=$(mktemp -d)
trap 'rm -rf "$package_dir"' EXIT
apt-get install -y ca-certificates curl build-essential dkms eject usb-modeswitch
if [[ ! -f "/lib/modules/$(uname -r)/build/Makefile" ]]; then
    apt-get install -y "linux-headers-$(uname -r)"
fi
curl --fail --location --proto '=https' --tlsv1.2 \
    https://linux.brostrend.com/aic8800-dkms.deb -o "$package_dir/aic8800-dkms.deb"
printf '%s  %s\n' "$package_sha" "$package_dir/aic8800-dkms.deb" | sha256sum --check -
chmod 755 "$package_dir"
chmod 644 "$package_dir/aic8800-dkms.deb"
apt-get install -y "$package_dir/aic8800-dkms.deb"
udevadm control --reload-rules
# The package's udev rules handle future insertions. Switch a currently
# inserted storage-mode device as well, then load the firmware loader.
if lsusb | grep -qi 'a69c:5732'; then
    usb_modeswitch -KQ -v a69c -p 5732
fi
modprobe aic_load_fw
echo "AIC8800 firmware loader installed. Reinsert the adapter if needed."
