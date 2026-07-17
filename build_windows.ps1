[CmdletBinding()]
param(
    [string]$PSMoveRoot = '',
    [string]$PSMoveBuild = ''
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
