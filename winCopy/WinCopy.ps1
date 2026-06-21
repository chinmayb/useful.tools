<#
.SYNOPSIS
    WinCopy - single-file folder copy scheduler.

    Run with no arguments to launch the Windows Forms GUI for picking
    source/destination folders and a schedule. The GUI registers a Windows
    Task Scheduler job (WinCopyDailyJob) that re-invokes this same
    binary/script with -Run to perform the headless copy.

    Run with -Run to execute the headless copy using settings stored in
    winCopy-config.json (used by Task Scheduler and the "Run Now" button).

.NOTES
    Dev mode (raw .ps1):
        powershell -ExecutionPolicy Bypass -File WinCopy.ps1
        powershell -ExecutionPolicy Bypass -File WinCopy.ps1 -Run

    Compiled (PS2EXE):
        WinCopy.exe
        WinCopy.exe -Run
#>

param(
    [switch]$Run
)

# ---------------------------------------------------------------------------
# Host / path detection
# ---------------------------------------------------------------------------
# When executed as a .ps1, $PSCommandPath / $MyInvocation give us the script
# path. When compiled with PS2EXE the script runs inside an .exe host, so we
# fall back to the process's main module path.
$IsCompiledExe = $false
$HostExePath   = $null
try {
    $HostExePath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
} catch { }

if ($PSCommandPath) {
    $SelfPath = $PSCommandPath
} elseif ($MyInvocation.MyCommand.Path) {
    $SelfPath = $MyInvocation.MyCommand.Path
} else {
    $SelfPath = $HostExePath
    $IsCompiledExe = $true
}

if ($HostExePath -and ([System.IO.Path]::GetFileName($HostExePath) -notmatch '^(powershell|pwsh)\.exe$')) {
    $IsCompiledExe = $true
    $SelfPath = $HostExePath
}

$ScriptDir  = Split-Path -Parent $SelfPath
$TaskName   = 'WinCopyDailyJob'

# Store config + log under %LOCALAPPDATA%\WinCopy\ so the exe itself can live
# anywhere - including UAC-protected folders like C:\ or C:\Program Files -
# without needing administrator rights to write its own state next to it.
$DataDir = $null
if ($env:LOCALAPPDATA) {
    $DataDir = Join-Path $env:LOCALAPPDATA 'WinCopy'
} else {
    # Fallback for the (unusual) case where LOCALAPPDATA isn't set.
    $DataDir = $ScriptDir
}
try {
    if (-not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    }
} catch {
    # If we can't create LOCALAPPDATA\WinCopy for any reason, fall back to
    # the exe's own directory. Writes there may still fail in protected
    # locations, but the rest of the code already handles that gracefully.
    $DataDir = $ScriptDir
}

$ConfigPath = Join-Path $DataDir 'winCopy-config.json'
$LogPath    = Join-Path $DataDir 'winCopy.log'

# One-time migration: if an older config/log exists next to the exe (from
# pre-LOCALAPPDATA builds), move it into the new data dir so the user
# doesn't lose their schedule.
$legacyConfig = Join-Path $ScriptDir 'winCopy-config.json'
$legacyLog    = Join-Path $ScriptDir 'winCopy.log'
if ((Test-Path $legacyConfig) -and -not (Test-Path $ConfigPath)) {
    try { Move-Item -Path $legacyConfig -Destination $ConfigPath -Force } catch { }
}
if ((Test-Path $legacyLog) -and -not (Test-Path $LogPath)) {
    try { Move-Item -Path $legacyLog -Destination $LogPath -Force } catch { }
}

# ===========================================================================
# RUN MODE - headless copy (invoked by Task Scheduler or "Run Now")
# ===========================================================================
$MaxLogLines       = 500   # cap the log at the last N lines
$MaxErrorLogPerRun = 5     # cap per-file error detail lines per run

$script:LogBuffer = New-Object System.Collections.Generic.List[string]

function Add-LogLine {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] $Message"
    [void]$script:LogBuffer.Add($line)
    # When compiled with PS2EXE -noConsole, Write-Host output is displayed in
    # a MessageBox popup at the end of the run. Avoid that by only echoing
    # to the host when running the raw .ps1 (i.e. there is a real console).
    if (-not $IsCompiledExe) {
        Write-Host $line
    }
}

function Flush-Log {
    if ($script:LogBuffer.Count -eq 0) { return }
    Add-Content -Path $LogPath -Value $script:LogBuffer
    try {
        $all = Get-Content -Path $LogPath -ErrorAction Stop
        if ($all.Count -gt $MaxLogLines) {
            $tail = $all | Select-Object -Last $MaxLogLines
            Set-Content -Path $LogPath -Value $tail -Encoding UTF8
        }
    } catch { }
    $script:LogBuffer.Clear()
}

function Invoke-WinCopyRun {
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = 'Stop'
    try {
        if (-not (Test-Path $ConfigPath)) {
            # No config means nothing has been scheduled yet (e.g. the exe
            # was just copied to a new location). Don't treat that as a
            # failure - just record a one-line note and exit cleanly so the
            # scheduled task doesn't show repeated red errors.
            Add-LogLine "skip no-config path=$ConfigPath"
            Flush-Log
            return 0
        }

        $config      = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
        $source      = $config.source
        $destination = $config.destination

        if (-not (Test-Path $source)) {
            Add-LogLine "FAIL src-missing src=$source"
            Flush-Log
            return 1
        }

        if (-not (Test-Path $destination)) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
        }

        $startTime = Get-Date

        $sourceFull = (Resolve-Path $source).Path.TrimEnd('\')
        $destFull   = (Resolve-Path $destination).Path.TrimEnd('\')

        # robocopy is shipped with Windows (Vista+). By default it copies only
        # files that are new or modified relative to the destination (compares
        # size + last-write time), which is exactly the incremental behavior
        # we want. /MIR mirrors the source exactly: new/modified files are
        # copied and files no longer in the source are deleted from the
        # destination (orphan cleanup).
        #
        # Flags:
        #   /MIR  - mirror source to destination (includes /E + purges orphans)
        #   /R:2  - retry 2 times on a failed file (default is 1 million)
        #   /W:2  - wait 2 seconds between retries
        #   /NFL  - suppress the per-file list (we only want the summary)
        #   /NDL  - suppress the per-directory list
        #   /NC   - suppress class column
        #   /NP   - no progress percentages
        #   /NJH  - suppress job header (keep job summary for parsing)
        $roboArgs = @(
            $sourceFull, $destFull,
            '/MIR', '/R:2', '/W:2',
            '/NFL', '/NDL', '/NC', '/NP', '/NJH'
        )

        # Quote each argument that contains whitespace before joining.
        $quotedArgs = $roboArgs | ForEach-Object {
            if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
        }
        $argString = [string]::Join(' ', $quotedArgs)

        # Launch robocopy through System.Diagnostics.Process so we can pin
        # CreateNoWindow=$true. Calling `& robocopy` from a PS2EXE -noConsole
        # exe can briefly flash a console window; this approach never does.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = 'robocopy.exe'
        $psi.Arguments              = $argString
        $psi.UseShellExecute        = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.CreateNoWindow         = $true
        $psi.WindowStyle            = [System.Diagnostics.ProcessWindowStyle]::Hidden

        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        $roboExit   = $proc.ExitCode
        $roboOutput = @()
        if ($stdout) { $roboOutput += $stdout -split "`r?`n" }
        if ($stderr) { $roboOutput += $stderr -split "`r?`n" }

        # Parse robocopy's summary block. The "Files :" line looks like:
        #   Files :   Total   Copied   Skipped  Mismatch  FAILED   Extras
        $copied = 0
        $failed = 0
        $skipped = 0
        $filesLine = $roboOutput |
            Where-Object { $_ -match '^\s*Files\s*:\s*\d' } |
            Select-Object -First 1
        if ($filesLine -and ($filesLine -match 'Files\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)')) {
            $copied  = [int]$Matches[2]
            $skipped = [int]$Matches[3]
            $failed  = [int]$Matches[5]
        }

        # Capture up to N error detail lines from robocopy output. Errors
        # start with a timestamp and the word ERROR.
        $errorLines = @($roboOutput | Where-Object { $_ -match 'ERROR\s+\d+' })
        $errorsLogged = 0
        foreach ($el in $errorLines) {
            if ($errorsLogged -ge $MaxErrorLogPerRun) { break }
            Add-LogLine "  err $el"
            $errorsLogged++
        }

        # Robocopy exit codes are bit flags. 0-7 are success-ish, 8+ are
        # failures. Treat 8+ or any FAILED file count as a run failure.
        $duration = [int]((Get-Date) - $startTime).TotalSeconds
        $status   = if ($roboExit -ge 8 -or $failed -gt 0) { 'FAIL' } else { 'OK' }
        Add-LogLine "$status files=$copied skipped=$skipped err=$failed dur=${duration}s exit=$roboExit src=$sourceFull dst=$destFull"
        Flush-Log

        if ($status -eq 'FAIL') { return 1 } else { return 0 }
    } catch {
        Add-LogLine "FATAL $($_.Exception.Message)"
        Flush-Log
        return 1
    } finally {
        $ErrorActionPreference = $prevPref
    }
}

if ($Run) {
    exit (Invoke-WinCopyRun)
}

# ===========================================================================
# GUI MODE
# ===========================================================================
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Allowed interval choices for the two dropdowns
$IntervalValues = @(1, 2, 5, 10, 15, 20, 30, 45, 60)
$IntervalUnits  = @('Minutes', 'Hours')

# ----- Load existing config if present -----
$initialSource        = ''
$initialDest          = ''
$initialTime          = [DateTime]::Today.AddHours(22)  # default 22:00
$initialMode          = 'Daily'                          # 'Daily' or 'Interval'
$initialIntervalValue = 2
$initialIntervalUnit  = 'Minutes'
$configLoaded         = $false
if (Test-Path $ConfigPath) {
    try {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($cfg.source)      { $initialSource = $cfg.source }
        if ($cfg.destination) { $initialDest   = $cfg.destination }
        if ($cfg.runTime) {
            $parsed = [DateTime]::MinValue
            if ([DateTime]::TryParse("$(Get-Date -Format yyyy-MM-dd) $($cfg.runTime)", [ref]$parsed)) {
                $initialTime = $parsed
            }
        }
        if ($cfg.scheduleMode) {
            if ($cfg.scheduleMode -eq 'Every2Minutes') {
                $initialMode          = 'Interval'
                $initialIntervalValue = 2
                $initialIntervalUnit  = 'Minutes'
            } else {
                $initialMode = $cfg.scheduleMode
            }
        }
        if ($cfg.intervalValue) {
            try { $initialIntervalValue = [int]$cfg.intervalValue } catch { }
        }
        if ($cfg.intervalUnit -and ($IntervalUnits -contains $cfg.intervalUnit)) {
            $initialIntervalUnit = $cfg.intervalUnit
        }
        $configLoaded = $true
    } catch { }
}
if (-not ($IntervalValues -contains $initialIntervalValue)) {
    $initialIntervalValue = 2
}

# ----- Form -----
$form               = New-Object System.Windows.Forms.Form
$form.Text          = 'WinCopy - Schedule Folder Copy'
$form.Size          = New-Object System.Drawing.Size(620, 420)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox   = $false

# Source row
$lblSource = New-Object System.Windows.Forms.Label
$lblSource.Text = 'Source folder:'
$lblSource.Location = New-Object System.Drawing.Point(15, 20)
$lblSource.Size = New-Object System.Drawing.Size(100, 22)
$form.Controls.Add($lblSource)

$txtSource = New-Object System.Windows.Forms.TextBox
$txtSource.Location = New-Object System.Drawing.Point(120, 18)
$txtSource.Size = New-Object System.Drawing.Size(330, 22)
$txtSource.Text = $initialSource
$form.Controls.Add($txtSource)

$btnSource = New-Object System.Windows.Forms.Button
$btnSource.Text = 'Browse...'
$btnSource.Location = New-Object System.Drawing.Point(460, 17)
$btnSource.Size = New-Object System.Drawing.Size(75, 24)
$btnSource.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    if ($txtSource.Text) { $dlg.SelectedPath = $txtSource.Text }
    if ($dlg.ShowDialog() -eq 'OK') { $txtSource.Text = $dlg.SelectedPath }
})
$form.Controls.Add($btnSource)

# Destination row
$lblDest = New-Object System.Windows.Forms.Label
$lblDest.Text = 'Destination folder:'
$lblDest.Location = New-Object System.Drawing.Point(15, 60)
$lblDest.Size = New-Object System.Drawing.Size(110, 22)
$form.Controls.Add($lblDest)

$txtDest = New-Object System.Windows.Forms.TextBox
$txtDest.Location = New-Object System.Drawing.Point(120, 58)
$txtDest.Size = New-Object System.Drawing.Size(330, 22)
$txtDest.Text = $initialDest
$form.Controls.Add($txtDest)

$btnDest = New-Object System.Windows.Forms.Button
$btnDest.Text = 'Browse...'
$btnDest.Location = New-Object System.Drawing.Point(460, 57)
$btnDest.Size = New-Object System.Drawing.Size(75, 24)
$btnDest.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    if ($txtDest.Text) { $dlg.SelectedPath = $txtDest.Text }
    if ($dlg.ShowDialog() -eq 'OK') { $txtDest.Text = $dlg.SelectedPath }
})
$form.Controls.Add($btnDest)

# Schedule mode row
$lblMode = New-Object System.Windows.Forms.Label
$lblMode.Text = 'Schedule:'
$lblMode.Location = New-Object System.Drawing.Point(15, 100)
$lblMode.Size = New-Object System.Drawing.Size(100, 22)
$form.Controls.Add($lblMode)

$rbDaily = New-Object System.Windows.Forms.RadioButton
$rbDaily.Text = 'Daily at'
$rbDaily.Location = New-Object System.Drawing.Point(120, 98)
$rbDaily.Size = New-Object System.Drawing.Size(80, 24)
$rbDaily.Checked = ($initialMode -ne 'Interval')
$form.Controls.Add($rbDaily)

$dtpTime = New-Object System.Windows.Forms.DateTimePicker
$dtpTime.Format = [System.Windows.Forms.DateTimePickerFormat]::Custom
$dtpTime.CustomFormat = 'hh:mm tt'
$dtpTime.ShowUpDown = $true
$dtpTime.Location = New-Object System.Drawing.Point(205, 98)
$dtpTime.Size = New-Object System.Drawing.Size(95, 22)
$dtpTime.Value = $initialTime
$form.Controls.Add($dtpTime)

# Interval row: "Every <N> <unit>"
$rbInterval = New-Object System.Windows.Forms.RadioButton
$rbInterval.Text = 'Every'
$rbInterval.Location = New-Object System.Drawing.Point(120, 132)
$rbInterval.Size = New-Object System.Drawing.Size(65, 24)
$rbInterval.Checked = ($initialMode -eq 'Interval')
$form.Controls.Add($rbInterval)

$cmbIntervalValue = New-Object System.Windows.Forms.ComboBox
$cmbIntervalValue.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbIntervalValue.Location = New-Object System.Drawing.Point(190, 132)
$cmbIntervalValue.Size = New-Object System.Drawing.Size(60, 22)
foreach ($v in $IntervalValues) { [void]$cmbIntervalValue.Items.Add($v) }
$cmbIntervalValue.SelectedItem = $initialIntervalValue
$form.Controls.Add($cmbIntervalValue)

$cmbIntervalUnit = New-Object System.Windows.Forms.ComboBox
$cmbIntervalUnit.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbIntervalUnit.Location = New-Object System.Drawing.Point(255, 132)
$cmbIntervalUnit.Size = New-Object System.Drawing.Size(90, 22)
foreach ($u in $IntervalUnits) { [void]$cmbIntervalUnit.Items.Add($u) }
$cmbIntervalUnit.SelectedItem = $initialIntervalUnit
$form.Controls.Add($cmbIntervalUnit)

# Enable/disable inputs based on selected mode
$updateModeEnabled = {
    $dtpTime.Enabled          = $rbDaily.Checked
    $cmbIntervalValue.Enabled = $rbInterval.Checked
    $cmbIntervalUnit.Enabled  = $rbInterval.Checked
}
$rbDaily.Add_CheckedChanged($updateModeEnabled)
$rbInterval.Add_CheckedChanged($updateModeEnabled)
& $updateModeEnabled

# Status label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(15, 280)
$lblStatus.Size = New-Object System.Drawing.Size(580, 60)
$lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
if ($configLoaded) {
    $lblStatus.Text = "Loaded settings from $ConfigPath"
} else {
    $lblStatus.Text = "No config yet. Fill in folders + schedule and click 'Save & Schedule' to start. Settings will be saved to: $ConfigPath"
}
$form.Controls.Add($lblStatus)

# Helpers
function Validate-Inputs {
    if (-not $txtSource.Text -or -not (Test-Path $txtSource.Text)) {
        [System.Windows.Forms.MessageBox]::Show('Source folder does not exist.', 'WinCopy', 'OK', 'Error') | Out-Null
        return $false
    }
    if (-not $txtDest.Text) {
        [System.Windows.Forms.MessageBox]::Show('Destination folder is required.', 'WinCopy', 'OK', 'Error') | Out-Null
        return $false
    }
    return $true
}

function Save-Config {
    $runTime    = $dtpTime.Value.ToString('HH:mm')
    $runDisplay = $dtpTime.Value.ToString('hh:mm tt')
    $mode       = if ($rbInterval.Checked) { 'Interval' } else { 'Daily' }
    $intervalValue = [int]$cmbIntervalValue.SelectedItem
    $intervalUnit  = [string]$cmbIntervalUnit.SelectedItem
    $cfg = [PSCustomObject]@{
        source        = $txtSource.Text
        destination   = $txtDest.Text
        runTime       = $runTime
        scheduleMode  = $mode
        intervalValue = $intervalValue
        intervalUnit  = $intervalUnit
    }
    $cfg | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
    return [PSCustomObject]@{
        RunTime       = $runTime
        RunDisplay    = $runDisplay
        Mode          = $mode
        IntervalValue = $intervalValue
        IntervalUnit  = $intervalUnit
    }
}

# Build the Task Scheduler action so it runs *this* same artifact with -Run.
# - When packaged as WinCopy.exe (PS2EXE), Task Scheduler invokes the .exe
#   directly with the -Run argument. No console window, no VBS shim needed.
# - When running as the raw .ps1 (dev mode), fall back to invoking
#   powershell.exe -File <script> -Run with a hidden window.
function Get-TaskAction {
    if ($IsCompiledExe -and $HostExePath -and (Test-Path $HostExePath)) {
        return New-ScheduledTaskAction -Execute $HostExePath -Argument '-Run'
    }
    $psExe = (Get-Command powershell.exe).Source
    $arg   = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$SelfPath`" -Run"
    return New-ScheduledTaskAction -Execute $psExe -Argument $arg
}

function Register-WinCopyTask {
    param(
        [string]$RunTime,
        [string]$Mode,
        [int]$IntervalValue,
        [string]$IntervalUnit
    )

    if ($Mode -eq 'Interval') {
        $startAt = (Get-Date).AddMinutes(1)
        if ($IntervalUnit -eq 'Hours') {
            $interval = New-TimeSpan -Hours $IntervalValue
        } else {
            $interval = New-TimeSpan -Minutes $IntervalValue
        }
        $trigger = New-ScheduledTaskTrigger -Once -At $startAt `
                        -RepetitionInterval $interval `
                        -RepetitionDuration (New-TimeSpan -Days 3650)
        $description = "WinCopy: folder copy job, every $IntervalValue $($IntervalUnit.ToLower())"
    } else {
        $trigger     = New-ScheduledTaskTrigger -Daily -At $RunTime
        $description = 'WinCopy: daily folder copy job'
    }

    $action   = Get-TaskAction
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -Description $description `
        -RunLevel Limited `
        -Force | Out-Null
}

function Get-WinCopyTaskInfo {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop

        $triggerSummaries = @()
        foreach ($t in $task.Triggers) {
            $cls = $t.CimClass.CimClassName
            switch ($cls) {
                'MSFT_TaskDailyTrigger' {
                    $startBoundary = $null
                    try { $startBoundary = [DateTime]::Parse($t.StartBoundary) } catch { }
                    $when = if ($startBoundary) { $startBoundary.ToString('hh:mm tt') } else { $t.StartBoundary }
                    $triggerSummaries += "Daily at $when"
                }
                'MSFT_TaskTimeTrigger' {
                    $startBoundary = $null
                    try { $startBoundary = [DateTime]::Parse($t.StartBoundary) } catch { }
                    $startTxt = if ($startBoundary) { $startBoundary.ToString('yyyy-MM-dd hh:mm tt') } else { $t.StartBoundary }
                    if ($t.Repetition -and $t.Repetition.Interval) {
                        $iso = $t.Repetition.Interval
                        try {
                            $ts = [System.Xml.XmlConvert]::ToTimeSpan($iso)
                            if ($ts.TotalMinutes -lt 60) {
                                $every = "$([int]$ts.TotalMinutes) minute(s)"
                            } else {
                                $every = "$([int]$ts.TotalHours) hour(s)"
                            }
                            $triggerSummaries += "Every $every (started $startTxt)"
                        } catch {
                            $triggerSummaries += "Repeats every $iso (started $startTxt)"
                        }
                    } else {
                        $triggerSummaries += "Once at $startTxt"
                    }
                }
                default { $triggerSummaries += $cls }
            }
        }
        if (-not $triggerSummaries) { $triggerSummaries = @('(no triggers)') }

        return [PSCustomObject]@{
            Exists             = $true
            State              = $task.State
            Description        = $task.Description
            LastRunTime        = $info.LastRunTime
            LastResult         = $info.LastTaskResult
            NextRunTime        = $info.NextRunTime
            NumberOfMissedRuns = $info.NumberOfMissedRuns
            Triggers           = $triggerSummaries
        }
    } catch {
        return [PSCustomObject]@{ Exists = $false }
    }
}

function Format-TaskTime {
    param($value)
    if (-not $value) { return 'Never' }
    try {
        $dt = [DateTime]$value
        if ($dt.Year -lt 1900) { return 'Never' }
        return $dt.ToString('yyyy-MM-dd hh:mm:ss tt')
    } catch {
        return [string]$value
    }
}

# Save & Schedule button
$btnSave = New-Object System.Windows.Forms.Button
$btnSave.Text = 'Save && Schedule'
$btnSave.Location = New-Object System.Drawing.Point(15, 230)
$btnSave.Size = New-Object System.Drawing.Size(140, 32)
$btnSave.Add_Click({
    if (-not (Validate-Inputs)) { return }
    try {
        $saved = Save-Config
        Register-WinCopyTask -RunTime $saved.RunTime -Mode $saved.Mode `
            -IntervalValue $saved.IntervalValue -IntervalUnit $saved.IntervalUnit
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
        if ($saved.Mode -eq 'Interval') {
            $lblStatus.Text = "Scheduled to run every $($saved.IntervalValue) $($saved.IntervalUnit.ToLower()). Task name: $TaskName"
        } else {
            $lblStatus.Text = "Scheduled daily at $($saved.RunDisplay). Task name: $TaskName"
        }
    } catch {
        $lblStatus.ForeColor = [System.Drawing.Color]::Red
        $lblStatus.Text = "Failed to schedule: $($_.Exception.Message)"
    }
})
$form.Controls.Add($btnSave)

# Run Now button - runs the copy in-process so it works identically in dev
# and compiled-exe modes (no need to spawn a child PowerShell or WinCopy.exe).
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = 'Run Now'
$btnRun.Location = New-Object System.Drawing.Point(165, 230)
$btnRun.Size = New-Object System.Drawing.Size(90, 32)
$btnRun.Add_Click({
    if (-not (Validate-Inputs)) { return }
    try {
        [void](Save-Config)
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = 'Running copy now...'
        $form.Refresh()
        $exitCode = Invoke-WinCopyRun
        if ($exitCode -eq 0) {
            $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
            $lblStatus.Text = 'Run Now completed successfully. See winCopy.log for details.'
        } else {
            $lblStatus.ForeColor = [System.Drawing.Color]::Red
            $lblStatus.Text = "Run Now finished with errors (exit $exitCode). See winCopy.log."
        }
    } catch {
        $lblStatus.ForeColor = [System.Drawing.Color]::Red
        $lblStatus.Text = "Run failed: $($_.Exception.Message)"
    }
})
$form.Controls.Add($btnRun)

# View Task button (shows task status in a popup)
$btnView = New-Object System.Windows.Forms.Button
$btnView.Text = 'View Task'
$btnView.Location = New-Object System.Drawing.Point(265, 230)
$btnView.Size = New-Object System.Drawing.Size(90, 32)
$btnView.Add_Click({
    $info = Get-WinCopyTaskInfo
    if (-not $info.Exists) {
        [System.Windows.Forms.MessageBox]::Show(
            "No scheduled task named '$TaskName' exists. Use Save & Schedule to create one.",
            'WinCopy - View Task', 'OK', 'Information') | Out-Null
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = "No scheduled task '$TaskName' exists yet."
        return
    }
    $lastResultHex = '0x{0:X}' -f [int]$info.LastResult
    $triggerText   = ($info.Triggers -join "`r`n              ")
    $lastRunText   = Format-TaskTime $info.LastRunTime
    $nextRunText   = Format-TaskTime $info.NextRunTime
    $msg = @"
Task name:    $TaskName
State:        $($info.State)
Description:  $($info.Description)
Schedule:     $triggerText

Last run:     $lastRunText
Last result:  $($info.LastResult) ($lastResultHex)
Next run:     $nextRunText
Missed runs:  $($info.NumberOfMissedRuns)
"@
    [System.Windows.Forms.MessageBox]::Show($msg, 'WinCopy - View Task', 'OK', 'Information') | Out-Null
    $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
    $lblStatus.Text = "Task '$TaskName' state: $($info.State); next run: $nextRunText."
})
$form.Controls.Add($btnView)

# Delete Task button (with confirmation)
$btnDelete = New-Object System.Windows.Forms.Button
$btnDelete.Text = 'Delete Task'
$btnDelete.Location = New-Object System.Drawing.Point(365, 230)
$btnDelete.Size = New-Object System.Drawing.Size(95, 32)
$btnDelete.Add_Click({
    $info = Get-WinCopyTaskInfo
    if (-not $info.Exists) {
        [System.Windows.Forms.MessageBox]::Show(
            "No scheduled task named '$TaskName' exists.",
            'WinCopy - Delete Task', 'OK', 'Information') | Out-Null
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = "No scheduled task '$TaskName' to delete."
        return
    }
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Delete scheduled task '$TaskName'?`r`n`r`nThis only removes the schedule; your files are untouched.",
        'WinCopy - Confirm Delete', 'YesNo', 'Warning')
    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
        $lblStatus.Text = "Scheduled task '$TaskName' deleted."
    } catch {
        $lblStatus.ForeColor = [System.Drawing.Color]::Red
        $lblStatus.Text = "Failed to delete task: $($_.Exception.Message)"
    }
})
$form.Controls.Add($btnDelete)

# Open Log button
$btnLog = New-Object System.Windows.Forms.Button
$btnLog.Text = 'Open Log'
$btnLog.Location = New-Object System.Drawing.Point(470, 230)
$btnLog.Size = New-Object System.Drawing.Size(90, 32)
$btnLog.Add_Click({
    if (Test-Path $LogPath) {
        Start-Process notepad.exe $LogPath
    } else {
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = 'No log file yet (winCopy.log will be created on first run).'
    }
})
$form.Controls.Add($btnLog)

# Close button
$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = 'Close'
$btnClose.Location = New-Object System.Drawing.Point(470, 350)
$btnClose.Size = New-Object System.Drawing.Size(90, 28)
$btnClose.Add_Click({ $form.Close() })
$form.Controls.Add($btnClose)

[void]$form.ShowDialog()
