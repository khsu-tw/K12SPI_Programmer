@echo off
REM Program a Curiosity Nano with MPLAB IPE (ipecmd, on-board nEDBG debugger), then verify by read-back.
REM Usage: firmware\flash_nano.bat [18f16q20|hexfile] [--dragdrop]      (default: 18f16q20)
REM
REM Drag-and-drop (copy HEX to the CURIOSITY drive) is NOT the default any more: on the PIC18F16Q20-CNANO
REM (debugger fw 01.22.0059) it silently stopped writing at file offset 18402 of a 19983-byte HEX
REM (program memory from 0x1998 up and all config bits left blank) while STATUS.TXT still said "Ready".
REM Override the IPE location with IPECMD if your MPLAB X is installed elsewhere.
setlocal
set "ARG=%~1"
if not defined ARG set "ARG=18f16q20"
set "PART="
if /i "%ARG%"=="18f16q20" (set "HEX=%~dp0prebuilt\K1V2SPI_FW_PIC18F16Q20.hex" & set "PART=18F16Q20")
if not defined HEX set "HEX=%ARG%"
if not exist "%HEX%" (echo [ERROR] HEX not found: %HEX% & exit /b 1)
if /i "%~2"=="--dragdrop" goto :dragdrop
if not defined PART (echo [ERROR] give 18f16q20 so IPE knows the part, or add --dragdrop & exit /b 1)
if not defined IPECMD set "IPECMD=C:\Program Files\Microchip\MPLABX\v6.30\mplab_platform\mplab_ipe\ipecmd.exe"
if not exist "%IPECMD%" (echo [WARN] ipecmd not found: %IPECMD% - falling back to drag-and-drop & goto :dragdrop)

set "RB=%TEMP%\mx25_readback_%PART%.hex"
if exist "%RB%" del "%RB%"
pushd "%TEMP%"
"%IPECMD%" -TPnEDBG -P%PART% -M -F"%HEX%" -OL
if errorlevel 1 (popd & echo [ERROR] IPE programming failed. & exit /b 3)
REM -OL on every call: IPE otherwise leaves the MCU held in reset and the bridge looks dead
"%IPECMD%" -TPnEDBG -P%PART% -GF"%RB%" -OL
popd
if not exist "%RB%" (echo [ERROR] read-back failed, cannot verify. & exit /b 4)
call "%~dp0..\Private\tools\py.cmd" -I "%~dp0verify_hex.py" "%HEX%" "%RB%"
if errorlevel 1 (echo [ERROR] VERIFY FAILED: the Nano does not contain this HEX. & exit /b 5)
echo Programmed and verified %HEX% (%PART%).
exit /b 0

:dragdrop
set "DRV="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "(Get-Volume | Where-Object FileSystemLabel -eq 'CURIOSITY' | Select-Object -First 1).DriveLetter"`) do set "DRV=%%D"
if not defined DRV (echo [ERROR] Drive "CURIOSITY" not found. Plug in the Curiosity Nano USB-C port. & exit /b 2)
copy /y "%HEX%" "%DRV%:\" >nul
if errorlevel 1 (echo [ERROR] Copy failed. & exit /b 3)
echo Copied %HEX% to %DRV%:\  - NOT verified. Drag-and-drop can truncate large HEX files; check INFO in the GUI.
