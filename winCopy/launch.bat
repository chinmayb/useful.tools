@echo off
REM Launches the WinCopy GUI. Double-click this file on Windows.
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%WinCopy-GUI.ps1"
endlocal
