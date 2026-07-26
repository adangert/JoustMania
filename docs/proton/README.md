# PS Move support through Proton

This document records the PS Move and Proton investigation performed on an
Arch-based Linux system on July 26, 2026. It covers why the Windows PSMoveAPI
build does not see controllers directly through Proton, the exact cause of the
HID feature report failure, and the native compatibility path used instead.

## Investigation environment

The investigation used:

- Arch-based Linux
- Linux `6.16.12-valve24.5-1-neptune-616-gb2f7cfe85e45`
- Proton `10.0-4`
- A Sony PS Move ZCM1 controller with USB ID `054c:03d5`
- A Sony PS Move ZCM2 controller with USB ID `054c:0c5e`
- The Windows `psmove.exe` and `psmoveapi.dll` shipped with JoustMania
- The `windows-monitor` PSMoveAPI branch from pull request 519

The relevant persistent local checkouts were:

```text
/home/deck/JoustMania
/home/deck/psmoveapi-windows-monitor
/home/deck/wine-proton-10-hid
```

Do not put source checkouts or durable investigation notes in `/tmp`. Proton
logs may be written there when they are disposable.

## Summary

There are two separate blockers in the direct Windows controller path:

1. Proton receives a Linux-modified HID report descriptor instead of the
   controller's original USB report descriptor. This prevents Windows
   PSMoveAPI from seeing the three HID collections it expects and causes
   feature reports such as `0x04` and `0x05` to be rejected.
2. Proton's Windows Bluetooth API implementation is incomplete. In particular,
   `BluetoothGetRadioInfo` and several device, authentication, and service APIs
   are stubs. Windows PSMoveAPI pairing cannot complete even after fixing HID.

The controller, USB cable, Linux permissions, Linux `hidraw` access, and
Proton's low-level Linux feature report backend were all confirmed to work.

## Implemented compatibility path

JoustMania keeps its Windows process and Windows `psmoveapi.dll` under Proton,
but delegates controller access to PSMoveAPI's native Linux daemon:

```text
JoustMania.exe
  -> Windows psmoveapi.dll
  -> moved UDP protocol on 127.0.0.1:17778
  -> native Linux psmove daemon
  -> Linux HID and Bluetooth
```

The Windows package contains these additional files:

```text
proton/
  pair-psmove.sh
  psmoveapi/
    psmove
    libpsmoveapi.so
```

At startup, JoustMania detects Proton, writes the localhost moved
configuration inside the compatibility prefix, restores the Linux executable
bit on `psmove`, and starts the daemon as the named user service
`joustmania-psmove.service`. The existing controller manager then uses the
Windows DLL normally. JoustMania stops the service when it exits normally.

USB pairing stops controller access temporarily and launches the bundled
native `psmove pair` command through `pkexec`. A small result file communicates
success back to the Windows process before controller access is restarted.

Native Windows and native Linux runs keep their existing code paths.

## Build the Linux helper

A normal Windows compiler cannot produce the ELF executable and `.so`. Build
them separately on Linux, in a Linux container, in WSL, or in Linux CI. The
following container targets an older Linux userspace while producing the
x86-64 helper required by the Proton package:

```bash
podman run --rm \
  -v "$PWD/psmoveapi:/src" \
  -w /src \
  debian:11-slim \
  sh -lc '
    apt-get update
    apt-get install -y \
      build-essential cmake pkg-config \
      libbluetooth-dev libdbus-1-dev libudev-dev
    cmake -S . -B build-linux-joustmania \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_BUILD_RPATH=\$ORIGIN \
      -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON \
      -DCMAKE_INSTALL_RPATH=\$ORIGIN \
      -DCMAKE_SKIP_RPATH=NO \
      -DCMAKE_SKIP_INSTALL_RPATH=NO \
      -DPSMOVE_BUILD_EXAMPLES=OFF \
      -DPSMOVE_BUILD_NAVCON_TEST=OFF \
      -DPSMOVE_BUILD_TRACKER=OFF \
      -DPSMOVE_USE_PS3EYE_DRIVER=OFF \
      -DPSMOVE_USE_SIXPAIR=OFF
    cmake --build build-linux-joustmania --parallel
  '
```

Replace `$PWD/psmoveapi` with the real checkout path when necessary. Copy only
these outputs:

```text
build-linux-joustmania/psmove
build-linux-joustmania/libpsmoveapi.so
```

On the Windows build machine, place both files in:

```text
JoustMania\vendor\psmoveapi-linux
```

That directory is ignored by Git. `build_windows.ps1` detects it
automatically. A bundle stored elsewhere can be supplied explicitly:

```powershell
.\build_windows.ps1 `
  -PSMoveLinuxBundle 'C:\path\to\psmoveapi-linux'
```

If no Linux bundle is supplied, the script warns and creates a Windows-only
package.

## Controller descriptors

### Original USB descriptor

The controller reports a 178-byte descriptor directly over USB. It contains
three top-level collections, which Windows normally exposes as `col01`,
`col02`, and `col03`.

The reports relevant to PSMoveAPI are:

| Collection | Report ID | Type | Total length |
| --- | ---: | --- | ---: |
| `col01` | `0x01` | Input | 49 bytes |
| `col01` | `0x02` | Output | 49 bytes |
| `col01` | `0x06` | Output | 9 bytes |
| `col01` | `0x03` | Feature | 9 bytes |
| `col01` | `0x10` | Feature | 49 bytes |
| `col01` | `0xE0` | Feature | 49 bytes |
| `col01` | `0x11` | Feature | 49 bytes |
| `col02` | `0x04` | Feature | 16 bytes |
| `col02` | `0x05` | Feature | 23 bytes |
| `col03` | `0xA0` | Feature | 35 bytes |
| `col03` | `0xA1` | Feature | 23 bytes |

Report `0x04` reads the controller and current host Bluetooth addresses.
Report `0x05` changes the host Bluetooth address stored by the controller.

The original descriptor was captured with `usbhid-dump`. That utility
temporarily detaches and then reattaches the Linux HID driver. The associated
`/dev/hidrawN` node can briefly disappear and be recreated, so do not assume
the numeric node remains stable.

### Linux replacement descriptor

The Linux `hid-sony` driver applies `motion_fixup()` to PS Move controllers.
It replaces the original descriptor with a 194-byte descriptor containing
only one top-level collection.

That replacement describes report IDs `0x01`, `0x02`, `0xEE`, and `0xEF`, but
it omits several reports used by PSMoveAPI, including pairing reports `0x04`
and `0x05`. Wine reads this replacement descriptor through
`HIDIOCGRDESCSIZE` and `HIDIOCGRDESC`.

Linux `hidraw` still permits direct raw feature requests that are not present
in the replacement descriptor. Wine does not currently take advantage of
that behavior because its HID class layer validates requests against the
replacement descriptor first.

## Why `psmove.exe list` returns zero

The Windows code in PSMoveAPI deliberately counts only device paths containing
`&col01#`. It later changes that path to `&col02#` to open a second handle for
Bluetooth address reports.

With the Linux replacement descriptor, Proton exposes only one collection.
The observed path contained `&mi_00#`, not `&col01#`. PSMoveAPI therefore
subtracts the device from its count and reports zero controllers.

A temporary PSMoveAPI experiment accepted the `mi_00` path and used the same
handle for normal and address operations. That changed enumeration from zero
to one and successfully opened the HID handle, but feature report `0x04`
still failed with `ERROR_INVALID_PARAMETER`.

This proves that enumeration and feature report handling are distinct parts
of the same descriptor problem.

## Exact `HidD_GetFeature` failure

The bundled Windows HIDAPI implementation normally calls
`DeviceIoControl(IOCTL_HID_GET_FEATURE)` directly. An experiment changed it to
call `HidD_GetFeature`, but the result was identical.

Wine implements `HidD_GetFeature` as a synchronous wrapper around the same
`IOCTL_HID_GET_FEATURE` request. Wine's HID class driver then:

1. Reads the requested report ID from byte zero of the caller's buffer.
2. Searches the parsed descriptor for a feature report with that ID in the
   selected collection.
3. Returns `STATUS_INVALID_PARAMETER` if no matching report is described.

Because report `0x04` is absent from the Linux replacement descriptor, Wine
rejects the request before its Linux backend is called. This becomes Windows
error `ERROR_INVALID_PARAMETER`.

The Proton 10 implementation and upstream Wine 11.14 both contain this same
validation behavior.

## Direct Linux proof

A direct `HIDIOCGFEATURE` request was issued against the controller's current
`/dev/hidrawN` node:

```text
requested report ID: 0x04
caller buffer size:  20 bytes
ioctl return value:  16 bytes
```

The returned report contained valid controller and current host Bluetooth
addresses. The unique address bytes are intentionally not recorded here.

This confirms:

- The controller supports report `0x04`.
- The USB connection works.
- The `deck` user has suitable `hidraw` access.
- Linux accepts a buffer larger than the actual report and returns the actual
  16-byte length.
- Wine's existing `hidraw_device_get_feature_report()` backend should work if
  the descriptor validation layer allows the request to reach it.

Report `0x05` was not tested directly because it changes the controller's
stored Bluetooth host and therefore changes pairing state.

## The unrelated HID parser error

The Proton trace also contained:

```text
err:hid:parse_new_value_caps HID parser values overflow!
```

This message did not come from the PS Move. Trace correlation showed it came
from a SONiX USB keyboard with USB ID `0c45:7691`.

Wine's HID parser starts its values array with a capacity of 32 and has a
growth edge case when a single HID item contains 32 explicit usages. This is
unrelated noise and is not responsible for PSMoveAPI returning zero
controllers.

## Candidate Proton HID fix

A targeted Proton or Wine quirk for PS Move could substitute the controller's
original 178-byte descriptor when a `054c:03d5` hidraw device is created.

With the original descriptor, Wine's existing HID parser should create three
child devices and name them `Col01`, `Col02`, and `Col03`. That matches the
paths expected by the Windows PSMoveAPI implementation. The descriptor also
provides the correct report IDs and lengths for input, LEDs, calibration,
extensions, authentication, and pairing.

This is safer than globally allowing every unknown HID report ID. A global
bypass could change behavior for unrelated devices, while the descriptor
override can be limited to known PS Move vendor and product IDs.

ZCM2 support must be investigated separately. PSMoveAPI identifies ZCM2 as
USB ID `054c:0c5e`, and its descriptor and report behavior should be captured
from real hardware before adding a Proton quirk.

Even if this HID fix is successful, distributing it would require one of:

- Acceptance of the fix into Wine and Proton
- Shipping a custom Wine compatibility tool
- Keeping all controller I/O in a bundled native Linux process

A normal Windows game package cannot directly replace Proton's system HID
driver.

## Remaining Windows Bluetooth API blocker

Windows PSMoveAPI pairing calls:

1. `BluetoothFindFirstRadio`
2. `BluetoothGetRadioInfo`
3. Bluetooth device discovery and authentication functions
4. `BluetoothSetServiceState`
5. Windows registry updates for a virtually cabled HID device

Proton 10 can enumerate a Bluetooth radio interface, but
`BluetoothGetRadioInfo` returns `ERROR_CALL_NOT_IMPLEMENTED`. Several later
device, authentication, removal, and service functions are also unimplemented.

As a result, the Windows `psmove_pair()` path cannot currently:

- Obtain the Linux host Bluetooth adapter address
- Complete Windows-style discovery and authentication
- Register or enable the controller through the Windows Bluetooth stack

Implementing all of these Wine APIs would be substantially larger than the
PS Move HID descriptor fix.

## Compatibility architecture

The compatibility path uses one package layout:

1. Continue shipping the Windows JoustMania application and Windows
   `psmoveapi.dll`.
2. Include prebuilt Linux controller helper binaries in the same game package.
   Do not include the PSMoveAPI Git checkout.
3. Detect Proton at runtime.
4. On native Windows, continue using the existing Windows PSMoveAPI path.
5. Under Proton, launch the packaged native helper for Linux pairing and
   controller I/O.

A Windows process cannot load an ELF `.so` through normal `LoadLibrary`.
Crossing from the Windows build into native Linux therefore needs an
executable or daemon with an IPC protocol, or a specialized Wine builtin and
Unix library component.

PSMoveAPI's existing moved client and daemon provide controller I/O. The fixed
64-byte moved response now includes optional controller model metadata so a
new client can decode ZCM2 reports correctly while remaining compatible with
older daemons. Moved sends the fixed byte-array sizes rather than compiler
union sizes, keeping the 16-byte request and 64-byte response identical
between GCC and MSVC. Pairing runs separately through the native CLI.

The native Linux pairing implementation also modifies BlueZ state under
`/var/lib/bluetooth` and may stop or restart `bluetoothd`. Its BlueZ record
includes `CablePairing=true`, which prevents the PIN prompt for cable-paired
PS Move controllers when `ClassicBondedOnly=true`.

## Relevant source locations

At the time of this investigation:

```text
PSMoveAPI Windows enumeration:
  /home/deck/psmoveapi-windows-monitor/src/psmove.c

PSMoveAPI Windows HIDAPI feature calls:
  /home/deck/psmoveapi-windows-monitor/external/hidapi/windows/hid.c

PSMoveAPI Windows Bluetooth pairing:
  /home/deck/psmoveapi-windows-monitor/src/platform/psmove_port_windows.c

Wine HidD_GetFeature wrapper:
  /home/deck/wine-proton-10-hid/dlls/hid/hidd.c

Wine HID descriptor validation:
  /home/deck/wine-proton-10-hid/dlls/hidclass.sys/device.c

Wine HID child collection creation:
  /home/deck/wine-proton-10-hid/dlls/hidclass.sys/pnp.c

Wine Linux hidraw descriptor and feature backend:
  /home/deck/wine-proton-10-hid/dlls/winebus.sys/bus_udev.c

Wine Windows Bluetooth API implementation:
  /home/deck/wine-proton-10-hid/dlls/bluetoothapis/main.c
```

These paths are investigation checkouts, not JoustMania runtime dependencies.
