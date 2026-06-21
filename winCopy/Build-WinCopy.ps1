<#
.SYNOPSIS
    Builds WinCopy.exe from WinCopy.ps1 using PS2EXE.

.DESCRIPTION
    Installs the ps2exe module for the current user if it's not already
    available, then compiles WinCopy.ps1 into a single GUI-mode WinCopy.exe.
    The resulting exe contains both the GUI and the headless -Run logic, so
    no other files (launcher VBS, batch, separate Run script) are needed.

.PARAMETER IconFile
    Optional .ico file to embed in the exe.

.PARAMETER Version
    Optional version string ("1.0.0.0") stamped into the exe metadata.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Build-WinCopy.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Build-WinCopy.ps1 -IconFile .\wincopy.ico -Version 1.0.0.0
#>

param(
    [string]$IconFile,
    [string]$Version
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source    = Join-Path $ScriptDir 'WinCopy.ps1'
$Output    = Join-Path $ScriptDir 'WinCopy.exe'

# Default to wincopy.ico next to this script when -IconFile is not supplied
if (-not $IconFile) {
    $defaultIco = Join-Path $ScriptDir 'wincopy.ico'
    if (Test-Path $defaultIco) { $IconFile = $defaultIco }
}

if (-not (Test-Path $Source)) {
    throw "Cannot find WinCopy.ps1 next to this build script ($Source)."
}

# Ensure ps2exe is available
if (-not (Get-Module -ListAvailable -Name ps2exe)) {
    Write-Host 'Installing ps2exe module for current user...'
    try {
        Install-Module -Name ps2exe -Scope CurrentUser -Force -AllowClobber
    } catch {
        throw "Failed to install ps2exe: $($_.Exception.Message). Run PowerShell as the same user and ensure PSGallery is reachable."
    }
}
Import-Module ps2exe -Force

# Build the ps2exe argument set. -noConsole hides the console window so the
# GUI launches cleanly with no flash; the headless -Run path writes to the
# log file rather than stdout, so losing the console is harmless.
$ps2exeArgs = @{
    InputFile  = $Source
    OutputFile = $Output
    NoConsole  = $true
    Title      = 'WinCopy'
    Product    = 'WinCopy'
    Description = 'Scheduled folder copy tool'
    Company    = 'WinCopy'
}
if ($Version)  { $ps2exeArgs.Version  = $Version }
if ($IconFile) {
    if (-not (Test-Path $IconFile)) { throw "Icon file not found: $IconFile" }
    $ps2exeArgs.IconFile = (Resolve-Path $IconFile).Path
}

Write-Host "Compiling $Source -> $Output ..."
Invoke-PS2EXE @ps2exeArgs

if (-not (Test-Path $Output)) {
    throw 'Build did not produce WinCopy.exe.'
}

$size = [int]((Get-Item $Output).Length / 1KB)
Write-Host "Built WinCopy.exe ($size KB)."
