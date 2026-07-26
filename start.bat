@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem One-click entry point: install once, repair incomplete installs, then launch.
set "VENV_PY=.venv\Scripts\python.exe"
set "INSTALL_MARKER=.venv\.install-complete"
set "NEEDS_INSTALL=0"

if not exist "%VENV_PY%" set "NEEDS_INSTALL=1"
if not exist "%INSTALL_MARKER%" set "NEEDS_INSTALL=1"

if "%NEEDS_INSTALL%"=="0" (
    "%VENV_PY%" -c "import hashlib,pathlib; marker=pathlib.Path(r'%INSTALL_MARKER%').read_text().strip(); expected=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); raise SystemExit(0 if marker == expected else 1)" >nul 2>nul
    if errorlevel 1 set "NEEDS_INSTALL=1"
)

if "%NEEDS_INSTALL%"=="1" (
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
