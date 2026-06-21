@echo off
REM WinCopy launcher. Double-click this file on Windows to open the GUI.
REM All configuration, scheduling, viewing and deletion is done from the GUI.
setlocal
set "SCRIPT_DIR=%~dp0"
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%WinCopy-GUI.ps1"
endlocal
