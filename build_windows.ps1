[CmdletBinding()]
param(
    [string]$PSMoveRoot = '',
    [string]$PSMoveBuild = '',
    [string]$PSMoveLinuxBundle = ''
)

$ErrorActionPreference = 'Stop'
if (-not $PSMoveRoot) {
    $PSMoveRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'psmoveapi'
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the Python 3.13 virtual environment and install requirements-windows.txt first.'
}

$pythonVersion = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($pythonVersion -ne '3.13') {
    throw "The Windows build environment must use Python 3.13, not $pythonVersion."
}

if (-not $PSMoveBuild) {
    $PSMoveBuild = Join-Path $PSMoveRoot 'build-hotplug'
}

$requiredInputs = @(
    (Join-Path $PSMoveRoot 'bindings\python\psmoveapi.py'),
    (Join-Path $PSMoveBuild 'psmoveapi.dll'),
    (Join-Path $PSMoveBuild 'psmove.exe')
)
foreach ($requiredInput in $requiredInputs) {
    if (-not (Test-Path -LiteralPath $requiredInput)) {
        throw "Missing Windows build input: $requiredInput"
    }
}

if (-not $PSMoveLinuxBundle) {
    $defaultLinuxBundle = Join-Path $PSScriptRoot 'vendor\psmoveapi-linux'
    if (Test-Path -LiteralPath $defaultLinuxBundle -PathType Container) {
        $PSMoveLinuxBundle = $defaultLinuxBundle
    }
}

if ($PSMoveLinuxBundle) {
    $requiredLinuxInputs = @(
        (Join-Path $PSMoveLinuxBundle 'psmove'),
        (Join-Path $PSMoveLinuxBundle 'libpsmoveapi.so')
    )
    foreach ($requiredLinuxInput in $requiredLinuxInputs) {
        if (-not (Test-Path -LiteralPath $requiredLinuxInput -PathType Leaf)) {
            throw "Missing Proton build input: $requiredLinuxInput"
        }
    }
    $env:PSMOVEAPI_LINUX_BUNDLE_DIR = (
        Resolve-Path -LiteralPath $PSMoveLinuxBundle
    ).Path
} else {
    Remove-Item Env:PSMOVEAPI_LINUX_BUNDLE_DIR -ErrorAction SilentlyContinue
    Write-Warning (
        'No Linux PSMoveAPI bundle was supplied. ' +
        'This build will work on Windows but not through Proton.'
    )
}

$env:PSMOVEAPI_ROOT = (Resolve-Path -LiteralPath $PSMoveRoot).Path
$env:PSMOVEAPI_BUILD_DIR = (Resolve-Path -LiteralPath $PSMoveBuild).Path
$env:PYGAME_HIDE_SUPPORT_PROMPT = '1'

Push-Location $PSScriptRoot
try {
    & $python -m PyInstaller --clean --noconfirm `
        --distpath 'build\windows-tools' `
        --workpath 'build\reset-tool' `
        'reset_psmove_connections.spec'
    if ($LASTEXITCODE -ne 0) {
        throw "Reset tool build failed with exit code $LASTEXITCODE."
    }

    & $python -m PyInstaller --clean --noconfirm `
        --distpath 'dist' `
        --workpath 'build\piparty' `
        'piparty.spec'
    if ($LASTEXITCODE -ne 0) {
        throw "JoustMania build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

Write-Host "Windows build complete: $PSScriptRoot\dist\piparty"
