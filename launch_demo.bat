@echo off
title OpenSwarm Live Demonstration Launcher
color 0A

set "ROOT=%~dp0"
set "PYTHON=python"
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
if errorlevel 1 python --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 is required. Install Python and try again.
    pause
    exit /b 1
)
set "PYTHONPATH=%ROOT%master"

echo ====================================================================
echo   OPENSWARM FLEET MASTER -- 3D DEMONSTRATION RECORDING SUITE
echo ====================================================================
echo.
echo Launching:
echo   1. Virtual ESP32 Node Terminal (tug_esp32 on UDP 4210)
echo   2. Virtual RP2040 Node Terminal (tug_rp2040 on UDP 4212)
echo   3. 3D Open-World Fleet Master (http://localhost:8080)
echo.

start "OpenSwarm Slave [ESP32]" cmd /k "%PYTHON% -m openswarm.virtual_slave --id tug_esp32 --board ESP32 --port 4210"

timeout /t 1 /nobreak >nul

start "OpenSwarm Slave [RP2040]" cmd /k "%PYTHON% -m openswarm.virtual_slave --id tug_rp2040 --board RP2040 --port 4212"

timeout /t 1 /nobreak >nul

echo Starting 3D Web Master... Opening http://localhost:8080
start "" http://localhost:8080
cd /d "%ROOT%"
%PYTHON% -m openswarm.web_server

pause
