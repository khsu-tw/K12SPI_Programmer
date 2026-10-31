@echo off
REM Build the Ubuntu executable from Windows using Docker Desktop (Ubuntu 22.04 container: runs on Ubuntu 22.04 and newer).
REM Usage: build_linux_docker.bat [--no-pause]       Output: gui\Linux\dist\K1V2SPI_Programmer, gui\Linux\build
setlocal
cd /d "%~dp0..\.."
docker run --rm -v "%CD%:/src" -w /src ubuntu:22.04 bash -c "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip python3-tk binutils >/dev/null && bash gui/Linux/build_linux.sh"
if errorlevel 1 goto :fail
echo.
echo Done:  %CD%\gui\Linux\dist\K1V2SPI_Programmer
goto :end
:fail
echo [FAILED] Is Docker Desktop running?
if /i not "%~1"=="--no-pause" pause
exit /b 1
:end
if /i not "%~1"=="--no-pause" pause
exit /b 0
