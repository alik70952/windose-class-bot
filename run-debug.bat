@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo Virtual environment was not found.
    echo First run install.bat.
    pause
    exit /b 1
)
if not exist "main.py" (
    echo main.py was not found in this repository folder.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%VENV_PY%" -u "main.py" %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Application exited with code %APP_EXIT_CODE%.
pause
exit /b %APP_EXIT_CODE%
