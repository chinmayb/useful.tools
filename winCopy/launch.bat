@echo off
REM WinCopy launcher. Double-click this file on Windows to open the GUI.
REM All configuration, scheduling, viewing and deletion is done from the GUI.
REM
REM We invoke the GUI via WinCopy-Launch.vbs + wscript.exe so that the
REM PowerShell host window does not flash up before the Forms GUI appears.
setlocal
set "SCRIPT_DIR=%~dp0"
start "" wscript.exe "%SCRIPT_DIR%WinCopy-Launch.vbs"
endlocal

