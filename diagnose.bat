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

set "PROBLEMS=0"
set "VENV_PY=.venv\Scripts\python.exe"

echo Repository: "%CD%"
call :exists_file "main.py" "main.py"
call :exists_file "requirements.txt" "requirements.txt"
call :exists_file ".venv" "virtual environment"
if exist "%VENV_PY%" (echo Venv Python: "%CD%\%VENV_PY%") else (echo Missing venv Python: "%CD%\%VENV_PY%" & set "PROBLEMS=1")

if exist "%VENV_PY%" (
    "%VENV_PY%" --version || set "PROBLEMS=1"
    "%VENV_PY%" -m pip --version || set "PROBLEMS=1"
    "%VENV_PY%" -m playwright --version || set "PROBLEMS=1"
    "%VENV_PY%" -c "import customtkinter; print('customtkinter import OK')" || set "PROBLEMS=1"
    "%VENV_PY%" -c "import keyring; print('keyring import OK')" || set "PROBLEMS=1"
    "%VENV_PY%" -c "import src.app; print('src.app import OK')" || set "PROBLEMS=1"
    "%VENV_PY%" -m compileall "main.py" "src" || set "PROBLEMS=1"
)

call :check_chrome
if errorlevel 1 (echo Google Chrome: not found in common Windows paths & set "PROBLEMS=1") else echo Google Chrome: found

echo Config path: "%CD%\config.json"
if exist "config.json" (echo Config file exists. Contents are not displayed.) else echo Config file not found; defaults will be used.
echo Startup logs: "%CD%\logs\startup-error.log"

if "%PROBLEMS%"=="0" (echo Diagnostics passed) else echo Diagnostics found one or more problems
if not "%NO_PAUSE%"=="1" pause
if "%PROBLEMS%"=="0" exit /b 0
exit /b 1

:exists_file
if exist "%~1" (echo Found %~2: "%CD%\%~1") else (echo Missing %~2: "%CD%\%~1" & set "PROBLEMS=1")
exit /b 0

:check_chrome
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" exit /b 0
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" exit /b 0
exit /b 1
