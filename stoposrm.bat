@echo off
set CONTAINER_NAME=osrm-malaysia

echo Stopping OSRM...

docker stop %CONTAINER_NAME% >nul 2>&1
docker rm %CONTAINER_NAME% >nul 2>&1

echo [OK] OSRM stopped
