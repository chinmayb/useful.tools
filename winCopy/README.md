# WinCopy

A tiny, install-free Windows tool to copy one folder to another on a schedule
(daily at a chosen time, or every 2 minutes).

## What's included

| File | Purpose |
|---|---|
| `launch.bat` | Double-click for a menu (Launch GUI / List task / Run / Delete / Open log) |
| `WinCopy-GUI.ps1` | Windows Forms UI: pick folders + schedule, save & schedule |
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
   - Choose a **Schedule**:
     - **Daily at** a specific time (e.g., `22:00`), or
     - **Every 2 minutes** (repeats indefinitely, starting ~1 minute after you save).
   - Click **Save & Schedule**. A Task Scheduler task named `WinCopyDailyJob` is created.
4. Click **Run Now** to copy immediately (also useful as a quick sanity check).
5. Click **Open Log** to view `winCopy.log`.

The GUI remembers your last choices.

## Behavior

- **Copy method:** native PowerShell `Copy-Item -Recurse -Force`. The directory structure under the source is preserved under the destination. Existing files are overwritten.
- **Schedule:** Windows Task Scheduler, either daily at the chosen time or every 2 minutes, task name `WinCopyDailyJob`. Re-saving overwrites the task.
- **Log:** appended to `winCopy.log` alongside the scripts. One compact summary line per run. The file is trimmed in place to the most recent 500 lines after every run, so it stays small even on the "every 2 minutes" schedule. Per-file errors are summarized in the count, with up to 5 error detail lines per run.

## Sample log

```
[2026-06-21 22:00:03] OK files=42 err=0 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:02:03] OK files=42 err=0 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:04:05]   err C:\Users\me\Docs\locked.xlsx: The process cannot access the file ...
[2026-06-21 22:04:05] FAIL files=41 err=1 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
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
