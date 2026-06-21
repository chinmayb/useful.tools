<#
.SYNOPSIS
    Headless copy script for WinCopy. Reads winCopy-config.json and copies
    source -> destination using Copy-Item, logging to winCopy.log.

.NOTES
    Invoked by Windows Task Scheduler or by the GUI "Run Now" button.
#>

$ErrorActionPreference = 'Stop'

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptDir 'winCopy-config.json'
$LogPath    = Join-Path $ScriptDir 'winCopy.log'

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] $Message"
    Add-Content -Path $LogPath -Value $line
    Write-Host $line
}

try {
    if (-not (Test-Path $ConfigPath)) {
        Write-Log "ERROR: Config file not found at $ConfigPath"
        exit 1
    }

    $config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
    $source = $config.source
    $destination = $config.destination

    Write-Log "=== WinCopy Run Start ==="
    Write-Log "Source: $source"
    Write-Log "Destination: $destination"

    if (-not (Test-Path $source)) {
        Write-Log "ERROR: Source directory does not exist: $source"
        exit 1
    }

    if (-not (Test-Path $destination)) {
        Write-Log "Destination does not exist. Creating: $destination"
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
    }

    $startTime = Get-Date
    $fileCount = 0
    $errorCount = 0

    # Enumerate all files under source, preserve directory structure under destination.
    $sourceFull = (Resolve-Path $source).Path.TrimEnd('\')
    $destFull   = (Resolve-Path $destination).Path.TrimEnd('\')

    # Use foreach (not ForEach-Object) so $fileCount/$errorCount updates
    # are visible outside the loop without needing $script: scoping.
    $items = Get-ChildItem -Path $sourceFull -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($item in $items) {
        $relative = $item.FullName.Substring($sourceFull.Length).TrimStart('\')
        $targetPath = Join-Path $destFull $relative

        try {
            if ($item.PSIsContainer) {
                if (-not (Test-Path $targetPath)) {
                    New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
                }
            } else {
                $targetDir = Split-Path -Parent $targetPath
                if (-not (Test-Path $targetDir)) {
                    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                }
                Copy-Item -Path $item.FullName -Destination $targetPath -Force
                $fileCount++
            }
        } catch {
            $errorCount++
            Write-Log "ERROR copying $($item.FullName): $($_.Exception.Message)"
        }
    }

    $duration = [int]((Get-Date) - $startTime).TotalSeconds
    Write-Log "Files copied: $fileCount"
    Write-Log "Errors: $errorCount"
    Write-Log "Run complete. Duration: ${duration}s"
    Write-Log ""

    if ($errorCount -gt 0) { exit 1 } else { exit 0 }

} catch {
    Write-Log "FATAL: $($_.Exception.Message)"
    Write-Log ""
    exit 1
}
