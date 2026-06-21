@echo off
REM WinCopy launcher menu. Double-click this file on Windows.
setlocal
set "SCRIPT_DIR=%~dp0"
set "TASK_NAME=WinCopyDailyJob"

:menu
cls
echo ==========================================
echo               WinCopy
echo ==========================================
echo  1. Launch GUI (configure / schedule)
echo  2. List scheduled task (status, last/next run)
echo  3. Run scheduled task now
echo  4. Delete scheduled task
echo  5. Open log file
echo  6. Exit
echo ==========================================
set /p choice="Choose an option [1-6]: "

if "%choice%"=="1" goto launch_gui
if "%choice%"=="2" goto list_task
if "%choice%"=="3" goto run_task
if "%choice%"=="4" goto delete_task
if "%choice%"=="5" goto open_log
if "%choice%"=="6" goto end
goto menu

:launch_gui
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%WinCopy-GUI.ps1"
goto menu

:list_task
echo.
schtasks /Query /TN "%TASK_NAME%" /V /FO LIST 2>nul
if errorlevel 1 echo No scheduled task named "%TASK_NAME%" exists. Use option 1 to create one.
echo.
pause
goto menu

:run_task
echo.
schtasks /Run /TN "%TASK_NAME%" 2>nul
if errorlevel 1 (echo Failed to run task. Does it exist?) else (echo Task triggered.)
echo.
pause
goto menu

:delete_task
echo.
set /p confirm="Delete scheduled task '%TASK_NAME%'? [y/N]: "
if /i not "%confirm%"=="y" goto menu
schtasks /Delete /TN "%TASK_NAME%" /F 2>nul
if errorlevel 1 (echo Failed to delete. Does it exist?) else (echo Task deleted.)
echo.
pause
goto menu

:open_log
if exist "%SCRIPT_DIR%winCopy.log" (
    start "" notepad.exe "%SCRIPT_DIR%winCopy.log"
) else (
    echo No log file yet ^(winCopy.log will be created on first run^).
    pause
)
goto menu

:end
endlocal
