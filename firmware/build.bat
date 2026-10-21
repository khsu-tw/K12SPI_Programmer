@echo off
REM Build the bridge firmware with MPLAB XC8 (no MPLAB X project needed).
REM Usage: firmware\build.bat [16f13145|18f16q20|all]     (default: all)
REM   16f13145 -> firmware\prebuilt\mx25_bridge_pic16f13145.hex   (PIC16F13145-CNANO)
REM   18f16q20 -> firmware\prebuilt\mx25_bridge_pic18f16q20.hex   (PIC18F16Q20-CNANO)
REM Override tool locations with XC8_BIN / DFP_16F1 / DFP_18FQ if your install differs.
setlocal
set "WHICH=%~1"
if not defined WHICH set "WHICH=all"
if not defined XC8_BIN set "XC8_BIN=C:\Program Files\Microchip\xc8\v3.10\bin\xc8-cc.exe"
if not defined DFP_16F1 set "DFP_16F1=%USERPROFILE%\.mchp_packs\Microchip\PIC16F1xxxx_DFP\1.31.465\xc8"
if not defined DFP_18FQ set "DFP_18FQ=C:\Program Files\Microchip\MPLABX\v6.30\packs\Microchip\PIC18F-Q_DFP\1.28.451\xc8"
if not exist "%XC8_BIN%" (echo [ERROR] XC8 not found: %XC8_BIN% & exit /b 9009)
if not exist "%~dp0prebuilt" mkdir "%~dp0prebuilt"
if /i "%WHICH%"=="16f13145" goto :b16
if /i "%WHICH%"=="18f16q20" goto :b18
if /i "%WHICH%"=="all" goto :b16
echo [ERROR] unknown target "%WHICH%" (use 16f13145, 18f16q20 or all) & exit /b 2

:b16
if not exist "%DFP_16F1%" (echo [ERROR] PIC16F1xxxx_DFP not found: %DFP_16F1% & exit /b 9009)
set "OUT=%TEMP%\mx25_xc8_16f13145"
if not exist "%OUT%" mkdir "%OUT%"
"%XC8_BIN%" -mcpu=16F13145 -mdfp="%DFP_16F1%" -O2 -Wall -o "%OUT%\mx25_bridge.elf" "%~dp0src\main.c"
if errorlevel 1 exit /b 1
copy /y "%OUT%\mx25_bridge.hex" "%~dp0prebuilt\mx25_bridge_pic16f13145.hex" >nul
echo Done: %~dp0prebuilt\mx25_bridge_pic16f13145.hex
if /i "%WHICH%"=="16f13145" exit /b 0

:b18
if not exist "%DFP_18FQ%" (echo [ERROR] PIC18F-Q_DFP not found: %DFP_18FQ% & exit /b 9009)
set "OUT=%TEMP%\mx25_xc8_18f16q20"
if not exist "%OUT%" mkdir "%OUT%"
"%XC8_BIN%" -mcpu=18F16Q20 -mdfp="%DFP_18FQ%" -O2 -Wall -Wno-2019 -o "%OUT%\mx25_bridge.elf" "%~dp0src\main.c"
if errorlevel 1 exit /b 1
copy /y "%OUT%\mx25_bridge.hex" "%~dp0prebuilt\mx25_bridge_pic18f16q20.hex" >nul
echo Done: %~dp0prebuilt\mx25_bridge_pic18f16q20.hex
exit /b 0
