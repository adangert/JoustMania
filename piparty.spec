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
psmove_linux_bundle_value = os.environ.get("PSMOVEAPI_LINUX_BUNDLE_DIR")
psmove_linux_bundle = (
    Path(psmove_linux_bundle_value).resolve()
    if psmove_linux_bundle_value
    else None
)

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

if psmove_linux_bundle is not None:
    proton_inputs = [
        psmove_linux_bundle / "psmove",
        psmove_linux_bundle / "libpsmoveapi.so",
        project_dir / "proton" / "pair-psmove.sh",
    ]
    missing_proton_inputs = [
        str(path) for path in proton_inputs if not path.is_file()
    ]
    if missing_proton_inputs:
        raise FileNotFoundError(
            "The Proton PS Move bundle is incomplete. Missing:\n"
            + "\n".join(missing_proton_inputs)
        )

    # Treat ELF files as data so the Windows PyInstaller analysis does not try
    # to inspect them as PE binaries. JoustMania restores the executable bit
    # before launching the helper through Proton.
    datas.extend(
        [
            (str(psmove_linux_bundle / "psmove"), "proton/psmoveapi"),
            (
                str(psmove_linux_bundle / "libpsmoveapi.so"),
                "proton/psmoveapi",
            ),
            (str(project_dir / "proton" / "pair-psmove.sh"), "proton"),
        ]
    )

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
