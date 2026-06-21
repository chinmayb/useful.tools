# WinCopy

A tiny, install-free Windows tool to copy one folder to another on a daily schedule.

## What's included

| File | Purpose |
|---|---|
| `launch.bat` | Double-click to open the GUI |
| `WinCopy-GUI.ps1` | Windows Forms UI: pick folders + time, save & schedule |
| `WinCopy-Run.ps1` | Headless copy script (Copy-Item + logging). Invoked by Task Scheduler |
| `winCopy-config.json` | Auto-generated when you click **Save & Schedule** |
| `winCopy.log` | Auto-generated; one entry per run |

No installs, no admin rights needed (uses current user's Task Scheduler).

## Usage

1. Copy this folder onto the Windows machine.
2. Double-click **`launch.bat`**.
3. In the GUI:
   - **Browse...** to pick the source folder.
   - **Browse...** to pick the destination folder.
   - Set the **daily run time** (e.g., `22:00`).
   - Click **Save & Schedule**. A Task Scheduler task named `WinCopyDailyJob` is created.
4. Click **Run Now** to copy immediately (also useful as a quick sanity check).
5. Click **Open Log** to view `winCopy.log`.

The GUI remembers your last choices.

## Behavior

- **Copy method:** native PowerShell `Copy-Item -Recurse -Force`. The directory structure under the source is preserved under the destination. Existing files are overwritten.
- **Schedule:** Windows Task Scheduler, daily at the chosen time, task name `WinCopyDailyJob`. Re-saving overwrites the task.
- **Log:** appended to `winCopy.log` alongside the scripts. Each run records start time, source, destination, file count, errors, and duration.

## Sample log

```
[2026-06-21 22:00:01] === WinCopy Run Start ===
[2026-06-21 22:00:01] Source: C:\Users\me\Docs
[2026-06-21 22:00:01] Destination: D:\Backup\Docs
[2026-06-21 22:00:03] Files copied: 42
[2026-06-21 22:00:03] Errors: 0
[2026-06-21 22:00:03] Run complete. Duration: 2s
```

## Removing the schedule

In PowerShell:
```powershell
Unregister-ScheduledTask -TaskName WinCopyDailyJob -Confirm:$false
```
Or open Task Scheduler GUI and delete `WinCopyDailyJob`.

## Notes / limits

- Source and destination must be accessible to the user that scheduled the task (mapped network drives only work if mounted at task run time).
- For very large folders, consider switching `Copy-Item` to `robocopy` inside `WinCopy-Run.ps1` for delta copies. The current build copies all files every run as requested.
