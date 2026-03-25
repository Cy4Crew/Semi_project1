@echo off
echo [*] Restarting Docker Desktop...

echo [1] Killing Docker processes...
taskkill /F /IM "Docker Desktop.exe" >nul 2>&1
taskkill /F /IM "com.docker.backend.exe" >nul 2>&1
taskkill /F /IM "vpnkit.exe" >nul 2>&1

echo [2] Shutting down WSL...
wsl --shutdown

timeout /t 3 >nul

echo [3] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo [4] Waiting for Docker to be ready...
:waitloop
timeout /t 3 >nul
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Waiting...
    goto waitloop
)

echo [✔] Docker is ready.
pause