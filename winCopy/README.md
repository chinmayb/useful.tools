# WinCopy

A tiny, install-free Windows tool to copy one folder to another on a schedule
(daily at a chosen time, or at a repeating interval up to every 60 minutes /
24 hours).

## What's included

| File | Purpose |
|---|---|
| `launch.bat` | Double-click to open the GUI (delegates to `WinCopy-Launch.vbs` to avoid a PowerShell console flash) |
| `WinCopy-Launch.vbs` | Tiny VBS shim that starts `WinCopy-GUI.ps1` with a hidden PowerShell host. Can be double-clicked directly |
| `WinCopy-GUI.ps1` | Windows Forms UI: pick folders + schedule, save & schedule, view, delete |
| `WinCopy-Run.ps1` | Headless copy script (Copy-Item + logging). Invoked by Task Scheduler |
| `WinCopy-Hidden.vbs` | Auto-generated tiny VBS launcher used by the scheduled task to run `WinCopy-Run.ps1` with no console window |
| `winCopy-config.json` | Auto-generated when you click **Save & Schedule** |
| `winCopy.log` | Auto-generated; one entry per run |

No installs, no admin rights needed (uses current user's Task Scheduler).

## Usage

1. Copy this folder onto the Windows machine.
2. Double-click **`launch.bat`** (or run `WinCopy-GUI.ps1` directly).
3. In the GUI:
   - **Browse...** to pick the source folder.
   - **Browse...** to pick the destination folder.
   - Choose a **Schedule**:
     - **Daily at** a specific time (e.g., `22:00`), or
     - **Every `<N>` `<Minutes|Hours>`** — pick the interval from the two
       dropdowns (e.g. `Every 60 Minutes`, `Every 1 Hours`, `Every 2 Minutes`).
       Allowed values: 1, 2, 5, 10, 15, 20, 30, 45, 60.
   - Click **Save & Schedule**. A Task Scheduler task named `WinCopyDailyJob`
     is created (re-saving overwrites it).
4. Click **Run Now** to copy immediately (also useful as a quick sanity check).
5. Click **View Task** to see the scheduled task's state, last run, last
   result and next run time in a pop-up.
6. Click **Delete Task** to remove the scheduled task (asks for confirmation;
   your source/destination files are untouched).
7. Click **Open Log** to view `winCopy.log`.

The GUI remembers your last choices (including the chosen interval).

## Behavior

- **Copy method:** native PowerShell `Copy-Item -Recurse -Force`. The directory structure under the source is preserved under the destination. Existing files are overwritten.
- **Schedule:** Windows Task Scheduler, either daily at the chosen time or at the chosen repeating interval (1–60 Minutes or 1–60 Hours), task name `WinCopyDailyJob`. Re-saving overwrites the task. The task launches via `wscript.exe WinCopy-Hidden.vbs`, which starts PowerShell with a hidden window so no console pops up on each scheduled run.
- **Log:** appended to `winCopy.log` alongside the scripts. One compact summary line per run. The file is trimmed in place to the most recent 500 lines after every run, so it stays small even on short intervals. Per-file errors are summarized in the count, with up to 5 error detail lines per run.

## Sample log

```
[2026-06-21 22:00:03] OK files=42 err=0 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:02:03] OK files=42 err=0 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:04:05]   err C:\Users\me\Docs\locked.xlsx: The process cannot access the file ...
[2026-06-21 22:04:05] FAIL files=41 err=1 dur=2s src=C:\Users\me\Docs dst=D:\Backup\Docs
```

## Removing the schedule

Easiest: open the GUI and click **Delete Task**.

Alternatively, in PowerShell:
```powershell
Unregister-ScheduledTask -TaskName WinCopyDailyJob -Confirm:$false
```
Or open Task Scheduler GUI and delete `WinCopyDailyJob`.

## Notes / limits

- Source and destination must be accessible to the user that scheduled the task (mapped network drives only work if mounted at task run time).
- For very large folders, consider switching `Copy-Item` to `robocopy` inside `WinCopy-Run.ps1` for delta copies. The current build copies all files every run as requested.
