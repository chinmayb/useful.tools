# WinCopy

A tiny, install-free Windows tool to copy one folder to another on a schedule
(daily at a chosen time, or at a repeating interval up to every 60 minutes /
24 hours).

Ships as a **single `WinCopy.exe`** — no batch files, no VBS shims, no
companion scripts.

## What's included

| File | Purpose |
|---|---|
| `WinCopy.exe` | The whole app. Double-click to open the GUI. `WinCopy.exe -Run` performs a headless copy (invoked by Task Scheduler). |
| `WinCopy.ps1` | Source script. Same code as the exe; can also be run directly during development. |
| `Build-WinCopy.ps1` | Build script that compiles `WinCopy.ps1` into `WinCopy.exe` via [PS2EXE](https://github.com/MScholtes/PS2EXE). |
| `wincopy.ico` | App icon embedded in the exe. Automatically used by `Build-WinCopy.ps1` when present. |

Runtime state (config + log) lives under **`%LOCALAPPDATA%\WinCopy\`**, not
next to the exe — see [Where files live](#where-files-live) for details.

No installs, no admin rights needed (uses current user's Task Scheduler).

## Usage

1. Copy `WinCopy.exe` onto the Windows machine. That's the only file you need
   to ship — config and log are kept in `%LOCALAPPDATA%\WinCopy\`, not next
   to the exe (see [Where files live](#where-files-live) below).
2. Double-click `WinCopy.exe` to open the GUI.
3. In the GUI:
   - **Browse...** to pick the source folder.
   - **Browse...** to pick the destination folder.
   - Choose a **Schedule**:
     - **Daily at** a specific time (e.g., `22:00`), or
     - **Every `<N>` `<Minutes|Hours>`** — pick the interval from the two
       dropdowns (e.g. `Every 60 Minutes`, `Every 1 Hours`, `Every 2 Minutes`).
       Allowed values: 1, 2, 5, 10, 15, 20, 30, 45, 60.
   - Click **Save & Schedule**. A Task Scheduler task named `WinCopyDailyJob`
     is created (re-saving overwrites it). The task action is simply
     `WinCopy.exe -Run`.
4. Click **Run Now** to copy immediately (runs in-process; useful as a quick
   sanity check).
5. Click **View Task** to see the scheduled task's state, last run, last
   result and next run time in a pop-up.
6. Click **Delete Task** to remove the scheduled task (asks for confirmation;
   your source/destination files are untouched).
7. Click **Open Log** to view `%LOCALAPPDATA%\WinCopy\winCopy.log`.

The GUI remembers your last choices (including the chosen interval).

## Where files live

`WinCopy.exe` itself is fully portable — you can drop it anywhere and it
never tries to write into its own folder. All persistent state lives under
**`%LOCALAPPDATA%\WinCopy\`** (typically
`C:\Users\<you>\AppData\Local\WinCopy\`), which is always writable for the
current user:

| Path | What |
|---|---|
| `%LOCALAPPDATA%\WinCopy\winCopy-config.json` | The settings you saved via **Save & Schedule** (source, destination, schedule). |
| `%LOCALAPPDATA%\WinCopy\winCopy.log` | Append-only run log, capped at 500 lines. |

### Why this matters

You can put `WinCopy.exe` in **any** folder — including UAC-protected ones
like `C:\`, `C:\Program Files\WinCopy\`, or even a read-only network share —
and it will still run **without prompting for administrator rights**. Earlier
builds stored config/log next to the exe, which is why placing the exe in
`C:\` previously triggered a UAC elevation prompt.

> **Per-user, not per-machine.** `%LOCALAPPDATA%` is specific to the logged-in
> Windows user. If you want a second Windows user on the same PC to have
> their own schedule, they just launch `WinCopy.exe` once and configure it
> for their own account. Likewise, the scheduled task is created under the
> current user's account, not system-wide.

### Legacy migration

If you used an earlier build that wrote `winCopy-config.json` /
`winCopy.log` next to the exe, those files are **moved** into
`%LOCALAPPDATA%\WinCopy\` automatically the first time the new build runs,
so your saved schedule and log history carry over. No manual action needed.

### Nuking everything

If you want to start fresh, close the GUI, click **Delete Task** (or run
`Unregister-ScheduledTask -TaskName WinCopyDailyJob -Confirm:$false`), then
delete the `%LOCALAPPDATA%\WinCopy\` folder. The exe can stay where it is.

## Behavior

- **Copy method:** Windows built-in **`robocopy`** (`/MIR`, with default
  incremental compare). On each run only files that are new or modified
  relative to the destination (by size + last-write time) are copied;
  unchanged files are skipped. Subdirectories — including empty ones — are
  preserved. **Mirror mode:** files and folders that no longer exist in the
  source are deleted from the destination, keeping it an exact mirror.
- **Schedule:** Windows Task Scheduler, either daily at the chosen time or at
  the chosen repeating interval (1–60 Minutes or 1–60 Hours), task name
  `WinCopyDailyJob`. Re-saving overwrites the task. The task action is
  `WinCopy.exe -Run`; because the exe is compiled with `-noConsole`, no
  console window flashes up on each scheduled run.
- **Log:** appended to `%LOCALAPPDATA%\WinCopy\winCopy.log`. One compact summary
  line per run, with `files=` (copied this run), `skipped=` (already in
  sync), `err=` (failed copies), `dur=` (seconds), and `exit=` (raw
  robocopy exit code). The file is trimmed in place to the most recent 500
  lines after every run, so it stays small even on short intervals. Up to 5
  per-file error detail lines are emitted per run.

## Sample log

```
[2026-06-21 22:00:03] OK files=42 skipped=0 err=0 dur=2s exit=1 src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:02:03] OK files=0 skipped=42 err=0 dur=0s exit=0 src=C:\Users\me\Docs dst=D:\Backup\Docs
[2026-06-21 22:04:05]   err 2026/06/21 22:04:05 ERROR 32 (0x00000020) Copying File C:\Users\me\Docs\locked.xlsx
[2026-06-21 22:04:05] FAIL files=41 skipped=0 err=1 dur=2s exit=8 src=C:\Users\me\Docs dst=D:\Backup\Docs
```

## Building `WinCopy.exe`

You only need to do this if you've changed `WinCopy.ps1`. End users just get
the pre-built `WinCopy.exe`.

From PowerShell, on a Windows machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\Build-WinCopy.ps1
```

`wincopy.ico` (included in the repo) is picked up automatically — no extra
flags needed. Optional overrides:

```powershell
.\Build-WinCopy.ps1 -IconFile .\my-custom.ico -Version 1.0.0.0
```

> SmartScreen may warn the first time `WinCopy.exe` is run because the binary
> is unsigned. Click **More info → Run anyway**, or code-sign the exe to
> avoid the prompt entirely.

## Running from source (dev mode)

You can also run the unpackaged script directly — useful when iterating on
changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\WinCopy.ps1          # GUI
powershell -ExecutionPolicy Bypass -File .\WinCopy.ps1 -Run     # headless copy
```

The GUI detects whether it's running as the compiled exe or the raw script
and registers the matching Task Scheduler action automatically.

## Removing the schedule

Easiest: open the GUI and click **Delete Task**.

Alternatively, in PowerShell:
```powershell
Unregister-ScheduledTask -TaskName WinCopyDailyJob -Confirm:$false
```
Or open Task Scheduler GUI and delete `WinCopyDailyJob`.

## Notes / limits

- Source and destination must be accessible to the user that scheduled the
  task (mapped network drives only work if mounted at task run time).
- For very large folders, the current implementation already uses
  `robocopy` (built into Windows) so only changed files are copied each run.
  `/MIR` is used, so the destination is kept as an exact mirror of the
  source — files deleted from the source will also be removed from the
  destination on the next run.
