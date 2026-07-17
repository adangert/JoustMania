# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


project_dir = Path(SPECPATH).resolve()
psmove_root = Path(
    os.environ.get("PSMOVEAPI_ROOT", project_dir.parent / "psmoveapi")
).resolve()
psmove_build = Path(
    os.environ.get("PSMOVEAPI_BUILD_DIR", psmove_root / "build-hotplug")
).resolve()
psmove_bindings = psmove_root / "bindings" / "python"
reset_executable = project_dir / "build" / "windows-tools" / "reset_psmove_connections.exe"

required_inputs = [
    psmove_bindings / "psmoveapi.py",
    psmove_build / "psmoveapi.dll",
    psmove_build / "psmove.exe",
    reset_executable,
]
missing_inputs = [str(path) for path in required_inputs if not path.is_file()]
if missing_inputs:
    raise FileNotFoundError(
        "Build the current PSMoveAPI and reset tool first. Missing:\n"
        + "\n".join(missing_inputs)
    )

datas = [
    (str(project_dir / "audio"), "audio"),
    (str(project_dir / "conf"), "conf"),
    (str(project_dir / "static"), "static"),
    (str(project_dir / "templates"), "templates"),
    (str(project_dir / "README.md"), "."),
    (str(project_dir / "LICENSE"), "."),
    (str(project_dir / "audio-license"), "."),
    (str(project_dir / "clear_devices.py"), "."),
    (str(project_dir / "reset_psmove_connections.ps1"), "."),
]

binaries = [
    (str(psmove_build / "psmoveapi.dll"), "."),
    (str(psmove_build / "psmove.exe"), "."),
    (str(reset_executable), "."),
]

a = Analysis(
    [str(project_dir / "piparty.py")],
    pathex=[str(project_dir), str(psmove_bindings)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["psmoveapi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="piparty",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    uac_admin=True,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="piparty",
)
