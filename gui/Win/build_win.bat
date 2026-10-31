@echo off
REM Build the GUI into a standalone Windows EXE.   Usage: build_win.bat [--no-pause]
REM Output: gui\Win\dist\K1V2SPI_Programmer.exe   Work files: gui\Win\build   (Ubuntu version: gui\Linux)
setlocal
cd /d "%~dp0..\.."
call Private\tools\py.cmd -m PyInstaller --noconfirm --onefile --windowed --name K1V2SPI_Programmer --distpath gui\Win\dist --workpath gui\Win\build --specpath gui\Win\build gui\mx25s1633_gui.py
if errorlevel 1 goto :fail
echo.
echo Done:  %CD%\gui\Win\dist\K1V2SPI_Programmer.exe
goto :end
:fail
echo [FAILED] If PyInstaller is missing, run setup_env.bat first.
if /i not "%~1"=="--no-pause" pause
exit /b 1
:end
if /i not "%~1"=="--no-pause" pause
exit /b 0
