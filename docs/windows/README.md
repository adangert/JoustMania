# JoustMania Windows Development and Build Guide

This guide records the complete Windows workflow used on July 16, 2026. It
covers development setup, the current PSMoveAPI integration, running from
source, controller pairing, packaging, and testing.

## Current repository state

The working checkouts are sibling directories:

```text
<repository parent>\
|-- JoustMania\
`-- psmoveapi\
```

Choose any repository parent directory. Set these PowerShell variables to the
locations on the current machine before using the commands in this guide:

```powershell
$reposRoot = 'C:\path\to\your\repositories'
$joustRoot = Join-Path $reposRoot 'JoustMania'
$psmoveRoot = Join-Path $reposRoot 'psmoveapi'
```

The variables last for the current PowerShell window. Set them again after
opening a new window.

The active branches used for the Windows build are:

```text
JoustMania: windows-modernization
psmoveapi:  windows-hotplug
```

Both repositories currently contain important local Windows changes. Before
pulling, switching branches, cleaning, or deleting build directories, inspect
both repositories:

```powershell
git -C $joustRoot status
git -C $psmoveRoot status
```

Do not use `git reset --hard`, `git clean`, or delete either checkout until the
Windows changes have been committed or otherwise backed up.

The repository remotes are:

```text
JoustMania origin: https://github.com/adangert/JoustMania.git
psmoveapi origin:  https://github.com/adangert/psmoveapi.git
psmoveapi upstream: https://github.com/thp/psmoveapi.git
```

## Required software

Install the following on a 64-bit Windows 10 or Windows 11 machine:

1. Git for Windows.
2. Python 3.13, 64-bit, including the Python launcher.
3. Visual Studio 2022 Community.
4. The Visual Studio workload named **Desktop development with C++**.
5. MSVC v143, a current Windows 10 or Windows 11 SDK, and CMake tools for
   Windows from the Visual Studio Installer.
6. PowerShell 7, recommended for the build command.
7. A Bluetooth adapter supported by Windows and a data-capable USB cable for
   each PlayStation Move controller.

Confirm Python:

```powershell
py -3.13 --version
```

The successful setup used Python 3.13.14. The Windows package is intentionally
pinned to Python 3.13 because the build script checks that version.

## Visual Studio and CMake

The current PSMoveAPI build uses the Visual Studio 2022 generator. The CMake
executable bundled with Visual Studio is a reliable choice:

```powershell
$psmoveCmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $psmoveCmake --version
```

An older standalone CMake installation may not know the `Visual Studio 17
2022` generator. It does not have to be uninstalled. Use the full Visual
Studio CMake path shown above.

If MSBuild reports that `Microsoft.TeamTest.targets` is malformed or has a
missing root element, repair Visual Studio 2022 in Visual Studio Installer,
then apply available updates.

## Build the current PSMoveAPI

Open an ordinary PowerShell for compilation. Administrator access is not
needed to configure or build.

```powershell
Set-Location $psmoveRoot

$psmoveCmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'

& $psmoveCmake --fresh -S . -B build-hotplug -G 'Visual Studio 17 2022' -A x64 `
  -DPSMOVE_BUILD_TRACKER=OFF `
  -DPSMOVE_BUILD_EXAMPLES=OFF `
  -DPSMOVE_BUILD_NAVCON_TEST=OFF `
  -DPSMOVE_USE_SIXPAIR=OFF

& $psmoveCmake --build build-hotplug --config Release --parallel
```

The Windows packaging workflow requires these outputs:

```text
psmoveapi\build-hotplug\psmove.exe
psmoveapi\build-hotplug\psmoveapi.dll
psmoveapi\bindings\python\psmoveapi.py
```

The `windows-hotplug` branch also contains the local Windows device-monitoring
implementation. That code is what lets JoustMania notice USB and Bluetooth
connection changes while the game is already running.

## Pair and inspect controllers with PSMoveAPI

Pairing changes Windows Bluetooth state, so pairing must run from an
Administrator PowerShell.

1. Connect the Move controller with a data-capable USB cable.
2. Open PowerShell as Administrator.
3. Run:

```powershell
Set-Location (Join-Path $psmoveRoot 'build-hotplug')
.\psmove.exe pair
```

4. Follow the prompt to unplug the controller.
5. Press the PS button until the status light remains on.
6. Inspect connected controllers:

```powershell
.\psmove.exe list
```

A successful Bluetooth connection is reported as `Bluetooth` with a battery
percentage. A magnetometer calibration warning does not prevent JoustMania
from using the controller.

JoustMania can also pair automatically. Start JoustMania as Administrator,
then connect a Move controller by USB while it is running.

## Create the Python environment

Use the repository-local virtual environment. This avoids conflicts with
unrelated global Python packages.

```powershell
Set-Location $joustRoot
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe -m pip check
```

Activation is optional because every command in this guide calls the virtual
environment's Python directly.

If PowerShell blocks activation or another local script, allow scripts only
for the current PowerShell process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Run JoustMania from source

Open PowerShell as Administrator. Administrator access is recommended because
JoustMania listens on port 80 and can pair Bluetooth controllers.

```powershell
Set-Location $joustRoot

$env:PYTHONPATH = Join-Path $psmoveRoot 'bindings\python'
$env:PSMOVEAPI_LIBRARY_PATH = Join-Path $psmoveRoot 'build-hotplug'

.\.venv\Scripts\python.exe .\piparty.py
```

The current source also detects a sibling `psmoveapi` checkout automatically,
but setting the two environment variables makes the selected binding and DLL
explicit.

Expected behavior:

- The console reports that piparty is starting.
- Audio starts without requiring ffmpeg on Windows.
- Flask starts on port 80.
- The web interface is available at `http://localhost/`.
- A Bluetooth controller is added to the menu.
- A USB controller is detected and paired while the program is running.
- Disconnecting and reconnecting a paired controller does not require a full
  JoustMania restart.

Stop the source process with `Ctrl+C` after testing.

## Run the unit tests

The current non-hardware controller tests use the current PSMoveAPI paths:

```powershell
Set-Location $joustRoot

$env:PYTHONPATH = Join-Path $psmoveRoot 'bindings\python'
$env:PSMOVEAPI_LIBRARY_PATH = Join-Path $psmoveRoot 'build-hotplug'

.\.venv\Scripts\python.exe -m unittest -v test_controller test_game_controller_capacity
```

The verified result on July 16, 2026 was 8 passing tests.

## Reset saved Move controller connections

Stop JoustMania before resetting controllers.

From a source checkout, open an Administrator PowerShell and run:

```powershell
Set-Location $joustRoot
powershell -NoProfile -ExecutionPolicy Bypass -File .\reset_psmove_connections.ps1
```

From the packaged build, run this as Administrator:

```text
reset_psmove_connections.exe
```

The reset utility removes only Bluetooth devices named `Motion Controller`
and matching PS Move virtual-cable registry entries. Windows error 1168 means
a requested device registration was already absent and is treated as a safe
condition by the current utility.

After a reset, pair each controller again by USB.

## Build the Windows distribution

Make sure PSMoveAPI was built into `build-hotplug` and the Python virtual
environment is complete. Then run:

```powershell
Set-Location $joustRoot
pwsh -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The build script performs two PyInstaller builds:

1. `reset_psmove_connections.spec` builds the standalone administrator reset
   tool from `clear_devices.py`.
2. `piparty.spec` builds the main one-folder JoustMania distribution.

The output is:

```text
JoustMania\dist\piparty\
```

Important files and directories in the output include:

```text
piparty.exe
psmove.exe
psmoveapi.dll
reset_psmove_connections.exe
audio\
conf\logging.prod.ini
static\
templates\
```

`conf\logging.prod.ini` is required. The packaged executable selects it for
production logging. Do not remove it from the source or packaged output.

`joustsettings.yaml` is intentionally not packaged. A fresh default settings
file is generated on first launch. Local settings are not embedded into new
packages.

Runtime logs are written to the package's `logs` directory and are excluded
from build inputs.

## Smoke test the packaged build

Run the packaged executable as Administrator:

```powershell
Set-Location $joustRoot
Start-Process -FilePath '.\dist\piparty\piparty.exe' -Verb RunAs
```

Verify all of the following:

1. The administrator prompt appears.
2. The application reaches the controller menu.
3. `http://localhost/` returns the web interface.
4. Audio plays.
5. A controller can pair by USB after startup.
6. A paired controller can reconnect over Bluetooth.
7. Two or more controllers can be active at once.
8. A complete game round starts, ends, and returns to the menu.
9. The reset executable starts with an administrator prompt.

The PyInstaller analysis may report an optional SciPy hidden import named
`scipy.special._cdflib`. The July 16 build passed the application, audio, web,
and controller smoke tests despite that warning.

## Important developer files

- `build_windows.ps1`: validates Python and PSMoveAPI, then runs both
  PyInstaller builds.
- `requirements-windows.txt`: pinned Python 3.13 Windows dependencies.
- `piparty.spec`: main one-folder PyInstaller package definition.
- `reset_psmove_connections.spec`: standalone administrator reset-tool package
  definition.
- `reset_psmove_connections.ps1`: source checkout wrapper for the reset tool.
- `clear_devices.py`: cross-platform controller registration cleanup logic.
- `conf\logging.prod.ini`: required production logging configuration.
- `controller_manager.py`: shared controller state and PSMoveAPI process.

## Troubleshooting

### CMake cannot create the Visual Studio 17 2022 generator

An old CMake executable is first on `PATH`. Use the full Visual Studio 2022
CMake path documented above.

### MSBuild cannot load Microsoft.TeamTest.targets

Repair Visual Studio 2022 through Visual Studio Installer, then update it.

### ImportError while loading `_psmove`

The process is finding the old SWIG binding or a DLL with missing
dependencies. Use the current ctypes binding in `bindings\python`, point
`PSMOVEAPI_LIBRARY_PATH` to `build-hotplug`, and use the 64-bit Python 3.13
environment.

### ModuleNotFoundError for Flask, pygame, or another Python package

Install `requirements-windows.txt` into `.venv` and run `.venv`'s Python, not
a global Python installation.

### ModuleNotFoundError for dbus on Windows

Use the Windows modernization branch. The current Windows path does not import
Linux DBus support.

### PowerShell says running scripts is disabled

Use one of these forms:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell -NoProfile -ExecutionPolicy Bypass -File .\reset_psmove_connections.ps1
```

### A controller keeps blinking and never stays connected

1. Stop JoustMania.
2. Run the reset utility as Administrator.
3. Connect the controller by USB.
4. Pair it again as Administrator.
5. Unplug it and press the PS button.
6. Confirm it with `psmove.exe list`.

### PyAudio reports error -9999

Confirm Windows has a working default output device, close applications using
the device exclusively, and restart JoustMania. The current Windows build does
not require ffmpeg for its WAV playback path.

### The web interface does not load

Confirm JoustMania is still running, approve the administrator prompt, and open
`http://localhost/`. Check that `templates`, `static`, and
`conf\logging.prod.ini` exist beside the packaged executable.
