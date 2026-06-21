<#
.SYNOPSIS
    Headless copy script for WinCopy. Reads winCopy-config.json and copies
    source -> destination using Copy-Item, logging to winCopy.log.

    The log is appended to on every run, and trimmed in place to the most
    recent $MaxLogLines lines so it stays small even under short repeating
    schedules (e.g. every 2 minutes).

.NOTES
    Invoked by Windows Task Scheduler or by the GUI "Run Now" button.
#>

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath  = Join-Path $ScriptDir 'winCopy-config.json'
$LogPath     = Join-Path $ScriptDir 'winCopy.log'
$MaxLogLines = 500    # cap the log at the last N lines
$MaxErrorLogPerRun = 5  # cap per-file error detail lines per run

# Buffer log lines for this run; we write them in one shot and then trim.
$script:LogBuffer = New-Object System.Collections.Generic.List[string]

function Add-LogLine {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] $Message"
    [void]$script:LogBuffer.Add($line)
    Write-Host $line
}

function Flush-Log {
    if ($script:LogBuffer.Count -eq 0) { return }

    # Append this run's lines.
    Add-Content -Path $LogPath -Value $script:LogBuffer

    # In-place rotation: keep only the last $MaxLogLines lines.
    try {
        $all = Get-Content -Path $LogPath -ErrorAction Stop
        if ($all.Count -gt $MaxLogLines) {
            $tail = $all | Select-Object -Last $MaxLogLines
            Set-Content -Path $LogPath -Value $tail -Encoding UTF8
        }
    } catch {
        # Trimming is best-effort; don't fail the run because of log rotation.
    }

    $script:LogBuffer.Clear()
}

try {
    if (-not (Test-Path $ConfigPath)) {
        Add-LogLine "FAIL no-config path=$ConfigPath"
        Flush-Log
        exit 1
    }

    $config      = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
    $source      = $config.source
    $destination = $config.destination

    if (-not (Test-Path $source)) {
        Add-LogLine "FAIL src-missing src=$source"
        Flush-Log
        exit 1
    }

    if (-not (Test-Path $destination)) {
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
    }

    $startTime  = Get-Date
    $fileCount  = 0
    $errorCount = 0
    $errorsLogged = 0

    $sourceFull = (Resolve-Path $source).Path.TrimEnd('\')
    $destFull   = (Resolve-Path $destination).Path.TrimEnd('\')

    $items = Get-ChildItem -Path $sourceFull -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($item in $items) {
        $relative   = $item.FullName.Substring($sourceFull.Length).TrimStart('\')
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
            if ($errorsLogged -lt $MaxErrorLogPerRun) {
                Add-LogLine "  err $($item.FullName): $($_.Exception.Message)"
                $errorsLogged++
            }
        }
    }

    $duration = [int]((Get-Date) - $startTime).TotalSeconds
    $status   = if ($errorCount -gt 0) { 'FAIL' } else { 'OK' }
    Add-LogLine "$status files=$fileCount err=$errorCount dur=${duration}s src=$sourceFull dst=$destFull"

    Flush-Log

    if ($errorCount -gt 0) { exit 1 } else { exit 0 }

} catch {
    Add-LogLine "FATAL $($_.Exception.Message)"
    Flush-Log
    exit 1
}

