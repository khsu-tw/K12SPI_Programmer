@echo off
REM Build the GUI into a standalone Windows EXE.   Usage: build_exe.bat [--no-pause]
REM PyInstaller work files go to %TEMP% so OneDrive cannot lock them; only the EXE goes to gui\dist.
setlocal
cd /d "%~dp0.."
call tools\py.cmd -m PyInstaller --noconfirm --onefile --windowed --name PIC16F_MX25S1633F_Programmer --distpath gui\dist --workpath "%TEMP%\mx25_pyi\build" --specpath "%TEMP%\mx25_pyi" gui\mx25s1633_gui.py
if errorlevel 1 goto :fail
echo.
echo Done:  %CD%\gui\dist\PIC16F_MX25S1633F_Programmer.exe
goto :end
:fail
echo [FAILED] If PyInstaller is missing, run setup_env.bat first.
if /i not "%~1"=="--no-pause" pause
exit /b 1
:end
if /i not "%~1"=="--no-pause" pause
exit /b 0
