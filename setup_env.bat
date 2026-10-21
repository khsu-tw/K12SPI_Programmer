@echo off
REM Create the Python environment used by all tasks.  Usage: setup_env.bat [--no-pause]
REM In OneDrive the venv is created under %LOCALAPPDATA% (OneDrive locks files); override with MX25_VENV.
setlocal
cd /d "%~dp0"
set "VENV=%MX25_VENV%"
if not defined VENV set "VENV=%LOCALAPPDATA%\MX25S1633F_Programmer\venv"
where python >nul 2>nul
if errorlevel 1 (echo [ERROR] Python not found. Install Python 3.9+ and tick "Add python.exe to PATH". & goto :fail)
if exist "%VENV%\Scripts\python.exe" goto :install
echo Creating %VENV% ...
python -m venv "%VENV%"
if errorlevel 1 goto :fail
:install
set TRY=0
:retry
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto :ok
set /a TRY+=1
if %TRY% lss 3 (timeout /t 3 >nul & goto :retry)
goto :fail
:ok
echo.
echo Done. Python interpreter: %VENV%\Scripts\python.exe
if /i not "%~1"=="--no-pause" pause
exit /b 0
:fail
echo [FAILED] See messages above.
if /i not "%~1"=="--no-pause" pause
exit /b 1
