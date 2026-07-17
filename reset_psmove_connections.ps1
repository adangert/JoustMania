[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$clearDevices = Join-Path $scriptDirectory 'clear_devices.py'
$resetExecutable = Join-Path $scriptDirectory 'reset_psmove_connections.exe'

$joustProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @('python.exe', 'pythonw.exe') -and
        $_.CommandLine -match '(?i)(^|[\\/])piparty\.py(?:\s|$)') -or
    $_.Name -eq 'piparty.exe'
}

if (-not $DryRun -and $joustProcesses) {
    $processIds = ($joustProcesses.ProcessId -join ', ')
    throw "Stop JoustMania before resetting controllers (running process IDs: $processIds)."
}

if (-not $DryRun) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdministrator = $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdministrator) {
        throw 'Run this script from an Administrator PowerShell window.'
    }
}

$arguments = @()
if ($DryRun) {
    $arguments += '--dry-run'
}

if (Test-Path -LiteralPath $resetExecutable) {
    & $resetExecutable @arguments
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
    & $python $clearDevices @arguments
}
if ($LASTEXITCODE -ne 0) {
    throw "PS Move reset failed with exit code $LASTEXITCODE."
}

if (-not $DryRun) {
    Write-Host 'Reset complete. Start JoustMania and pair each controller again by USB.'
}
