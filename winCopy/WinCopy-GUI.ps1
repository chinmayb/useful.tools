<#
.SYNOPSIS
    Windows Forms GUI for WinCopy. Lets the user pick a source folder,
    destination folder, and a schedule (either daily at a chosen time or
    every 2 minutes), then registers a Windows Task Scheduler job that
    invokes WinCopy-Run.ps1 on that schedule.

.NOTES
    Run with:  powershell -ExecutionPolicy Bypass -File WinCopy-GUI.ps1
#>

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptDir 'winCopy-config.json'
$RunScript  = Join-Path $ScriptDir 'WinCopy-Run.ps1'
$TaskName   = 'WinCopyDailyJob'

# ----- Load existing config if present -----
$initialSource = ''
$initialDest   = ''
$initialTime   = [DateTime]::Today.AddHours(22)  # default 22:00
$initialMode   = 'Daily'                          # 'Daily' or 'Every2Minutes'
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
        if ($cfg.scheduleMode) { $initialMode = $cfg.scheduleMode }
    } catch { }
}

# ----- Form -----
$form               = New-Object System.Windows.Forms.Form
$form.Text          = 'WinCopy - Schedule Folder Copy'
$form.Size          = New-Object System.Drawing.Size(560, 380)
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
$rbDaily.Checked = ($initialMode -ne 'Every2Minutes')
$form.Controls.Add($rbDaily)

$dtpTime = New-Object System.Windows.Forms.DateTimePicker
$dtpTime.Format = [System.Windows.Forms.DateTimePickerFormat]::Custom
$dtpTime.CustomFormat = 'hh:mm tt'
$dtpTime.ShowUpDown = $true
$dtpTime.Location = New-Object System.Drawing.Point(205, 98)
$dtpTime.Size = New-Object System.Drawing.Size(95, 22)
$dtpTime.Value = $initialTime
$form.Controls.Add($dtpTime)

$rbEvery2 = New-Object System.Windows.Forms.RadioButton
$rbEvery2.Text = 'Every 2 minutes'
$rbEvery2.Location = New-Object System.Drawing.Point(320, 98)
$rbEvery2.Size = New-Object System.Drawing.Size(140, 24)
$rbEvery2.Checked = ($initialMode -eq 'Every2Minutes')
$form.Controls.Add($rbEvery2)

# Enable/disable time picker based on selected mode
$updateTimeEnabled = {
    $dtpTime.Enabled = $rbDaily.Checked
}
$rbDaily.Add_CheckedChanged($updateTimeEnabled)
$rbEvery2.Add_CheckedChanged($updateTimeEnabled)
& $updateTimeEnabled

# Status label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(15, 250)
$lblStatus.Size = New-Object System.Drawing.Size(520, 60)
$lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
$lblStatus.Text = ''
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
    $mode       = if ($rbEvery2.Checked) { 'Every2Minutes' } else { 'Daily' }
    $cfg = [PSCustomObject]@{
        source       = $txtSource.Text
        destination  = $txtDest.Text
        runTime      = $runTime
        scheduleMode = $mode
    }
    $cfg | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
    return [PSCustomObject]@{ RunTime = $runTime; RunDisplay = $runDisplay; Mode = $mode }
}

function Register-WinCopyTask {
    param(
        [string]$RunTime,
        [string]$Mode
    )

    if ($Mode -eq 'Every2Minutes') {
        # Trigger: starts (about) now, repeats every 2 minutes "indefinitely".
        # Task Scheduler requires a finite RepetitionDuration, so use a long span.
        $startAt   = (Get-Date).AddMinutes(1)
        $trigger   = New-ScheduledTaskTrigger -Once -At $startAt `
                        -RepetitionInterval (New-TimeSpan -Minutes 2) `
                        -RepetitionDuration (New-TimeSpan -Days 3650)
        $description = 'WinCopy: folder copy job, every 2 minutes'
    } else {
        # Trigger: daily at the given HH:mm
        $trigger     = New-ScheduledTaskTrigger -Daily -At $RunTime
        $description = 'WinCopy: daily folder copy job'
    }

    # Action: run PowerShell with the run script
    $psExe = (Get-Command powershell.exe).Source
    $action = New-ScheduledTaskAction `
        -Execute $psExe `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""

    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    # Remove existing task first, ignore errors
    try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue } catch { }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Trigger $trigger `
        -Action $action `
        -Settings $settings `
        -Description $description `
        -RunLevel Limited | Out-Null
}

# Save & Schedule button
$btnSave = New-Object System.Windows.Forms.Button
$btnSave.Text = 'Save && Schedule'
$btnSave.Location = New-Object System.Drawing.Point(15, 200)
$btnSave.Size = New-Object System.Drawing.Size(160, 32)
$btnSave.Add_Click({
    if (-not (Validate-Inputs)) { return }
    try {
        $saved = Save-Config
        Register-WinCopyTask -RunTime $saved.RunTime -Mode $saved.Mode
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
        if ($saved.Mode -eq 'Every2Minutes') {
            $lblStatus.Text = "Scheduled to run every 2 minutes. Task name: $TaskName"
        } else {
            $lblStatus.Text = "Scheduled daily at $($saved.RunDisplay). Task name: $TaskName"
        }
    } catch {
        $lblStatus.ForeColor = [System.Drawing.Color]::Red
        $lblStatus.Text = "Failed to schedule: $($_.Exception.Message)"
    }
})
$form.Controls.Add($btnSave)

# Run Now button
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = 'Run Now'
$btnRun.Location = New-Object System.Drawing.Point(185, 200)
$btnRun.Size = New-Object System.Drawing.Size(100, 32)
$btnRun.Add_Click({
    if (-not (Validate-Inputs)) { return }
    try {
        [void](Save-Config)
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = 'Running copy now...'
        $form.Refresh()
        $psExe = (Get-Command powershell.exe).Source
        $p = Start-Process -FilePath $psExe `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $RunScript) `
            -WindowStyle Hidden -PassThru -Wait
        if ($p.ExitCode -eq 0) {
            $lblStatus.ForeColor = [System.Drawing.Color]::DarkGreen
            $lblStatus.Text = 'Run Now completed successfully. See winCopy.log for details.'
        } else {
            $lblStatus.ForeColor = [System.Drawing.Color]::Red
            $lblStatus.Text = "Run Now finished with errors (exit $($p.ExitCode)). See winCopy.log."
        }
    } catch {
        $lblStatus.ForeColor = [System.Drawing.Color]::Red
        $lblStatus.Text = "Run failed: $($_.Exception.Message)"
    }
})
$form.Controls.Add($btnRun)

# Open Log button
$btnLog = New-Object System.Windows.Forms.Button
$btnLog.Text = 'Open Log'
$btnLog.Location = New-Object System.Drawing.Point(295, 200)
$btnLog.Size = New-Object System.Drawing.Size(100, 32)
$btnLog.Add_Click({
    $logPath = Join-Path $ScriptDir 'winCopy.log'
    if (Test-Path $logPath) {
        Start-Process notepad.exe $logPath
    } else {
        $lblStatus.ForeColor = [System.Drawing.Color]::DarkBlue
        $lblStatus.Text = 'No log file yet (winCopy.log will be created on first run).'
    }
})
$form.Controls.Add($btnLog)

# Close button
$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = 'Close'
$btnClose.Location = New-Object System.Drawing.Point(435, 200)
$btnClose.Size = New-Object System.Drawing.Size(100, 32)
$btnClose.Add_Click({ $form.Close() })
$form.Controls.Add($btnClose)

[void]$form.ShowDialog()
