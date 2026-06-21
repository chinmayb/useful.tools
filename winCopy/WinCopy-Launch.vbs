' WinCopy-Launch.vbs - opens the WinCopy GUI without flashing a PowerShell console.
' Used by launch.bat and safe to double-click directly.
Option Explicit
Dim shell, scriptDir, ps1, cmd
Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ps1       = scriptDir & "\WinCopy-GUI.ps1"
cmd       = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & ps1 & """"
' Run hidden (0); do not wait so the launcher exits immediately.
shell.Run cmd, 0, False
