@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem One-click entry point: install once when needed, then launch normally.
if not exist ".venv\Scripts\python.exe" (
    echo First launch: preparing Windows Class Bot...
    call install.bat --no-pause
    if errorlevel 1 (
        echo Installation failed. See the message above, then run start.bat again.
        pause
        exit /b 1
    )
)

call run.bat %*
exit /b %ERRORLEVEL%
