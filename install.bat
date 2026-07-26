@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NO_PAUSE=0"
if /I "%CI%"=="1" set "NO_PAUSE=1"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto parse_args
:args_done

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo Python پیدا نشد. Python 3.11 یا جدیدتر را نصب کنید و گزینه Add Python to PATH را فعال کنید.
    call :fail 1 "Python detection" & exit /b 1
)

echo Using Python launcher: %PYTHON_CMD%
%PYTHON_CMD% --version
if errorlevel 1 (call :fail 1 "Python version check" & exit /b 1)
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Python 3.11 or newer is required.
    call :fail 1 "Python version requirement" & exit /b 1
)

if exist "%VENV_DIR%" if not exist "%VENV_PY%" (
    echo Virtual environment exists but is incomplete or broken: "%VENV_DIR%"
    echo Delete the "%VENV_DIR%" folder and run install.bat again to rebuild it.
    call :fail 1 "Virtual environment validation" & exit /b 1
)

if not exist "%VENV_PY%" (
    echo Creating virtual environment in "%VENV_DIR%"...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (call :fail 1 "Virtual environment creation" & exit /b 1)
)

"%VENV_PY%" --version
if errorlevel 1 (call :fail 1 "Virtual environment Python check" & exit /b 1)

"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (call :fail 1 "Upgrade pip setuptools wheel" & exit /b 1)

if not exist "requirements.txt" (call :fail 1 "requirements.txt check" & exit /b 1)
"%VENV_PY%" -m pip install -r "requirements.txt"
if errorlevel 1 (call :fail 1 "Install requirements" & exit /b 1)

rem Use the Google Chrome already installed on Windows. Do not download the
rem redundant Playwright Chromium browser during the first launch.
call :check_chrome
if errorlevel 1 (
    echo Google Chrome was not found in the standard Windows installation paths.
    echo Install Google Chrome, then run start.bat again. Chromium will not be downloaded.
    call :fail 1 "Google Chrome detection" & exit /b 1
)
echo Using the Google Chrome already installed on this computer.

"%VENV_PY%" -c "import customtkinter; import playwright; import keyring; import src.app"
if errorlevel 1 (call :fail 1 "Startup import check" & exit /b 1)

"%VENV_PY%" -m compileall "main.py" "src"
if errorlevel 1 (call :fail 1 "compileall" & exit /b 1)

rem The installer deliberately does not run the developer test suite.  Apart
rem from making installation much slower, UI/process tests can briefly open
rem extra Windows.  Developers can run ".venv\Scripts\python -m pytest -q"
rem explicitly when they need it.

echo Registering the persistent background scheduler worker...
for /f "tokens=1,* delims=," %%A in ('schtasks.exe /Query /FO CSV /V /NH 2^>nul') do (
    echo %%A %%B | findstr /I /C:"VadanaClassBot-" /C:"scheduled_runner.py" /C:"schedule_worker.py" /C:"cmd.exe" /C:"run.bat" /C:"main.py" >nul && schtasks.exe /Delete /F /TN %%~A >nul 2>nul
)
"%VENV_PY%" main.py --install-worker
if errorlevel 1 (
    echo.
    echo Windows denied the initial Task Scheduler registration.
    echo Requesting administrator approval for this step only...
    set "VADANA_WORKER_PY=%CD%\%VENV_PY%"
    set "VADANA_PROJECT_ROOT=%CD%"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$process = Start-Process -FilePath $env:VADANA_WORKER_PY -ArgumentList @('main.py','--install-worker') -WorkingDirectory $env:VADANA_PROJECT_ROOT -Verb RunAs -Wait -PassThru; exit $process.ExitCode"
    if errorlevel 1 (
        echo Worker registration still failed. Approve the Windows UAC prompt, or run install.bat as Administrator.
        call :fail 1 "Worker registration" & exit /b 1
    )
)

"%VENV_PY%" -c "import hashlib,pathlib; pathlib.Path(r'%VENV_DIR%\.install-complete').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='ascii')"
if errorlevel 1 (call :fail 1 "Installation completion marker" & exit /b 1)

echo Installation completed successfully.
echo Run run.bat to start the application.
if not "%NO_PAUSE%"=="1" pause
exit /b 0

:check_chrome
where chrome.exe >nul 2>nul && exit /b 0
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" exit /b 0
exit /b 1

:fail
echo.
echo ERROR: Step failed: %~2
echo Exit Code: %~1
call :finish %~1

:finish
if not "%NO_PAUSE%"=="1" pause
exit /b %~1
