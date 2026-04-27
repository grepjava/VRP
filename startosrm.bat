@echo off
setlocal

set DATA_DIR=%~dp0osrm-data
set MAP_FILE=malaysia-singapore-brunei-latest.osm.pbf
set OSRM_FILE=malaysia-singapore-brunei-latest.osrm
set CONTAINER_NAME=osrm-malaysia
set MAP_URL=https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf

echo === OSRM Malaysia ===
echo.

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running. Please start Docker Desktop first.
    exit /b 1
)
echo [OK] Docker is running

REM Check if container is already running
docker ps --filter "name=%CONTAINER_NAME%" --filter "status=running" --format "{{.Names}}" | findstr /x "%CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo [OK] OSRM is already running at http://localhost:5000
    exit /b 0
)

REM Remove stopped container with the same name if it exists
docker ps -a --filter "name=%CONTAINER_NAME%" --format "{{.Names}}" | findstr /x "%CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Removing stopped OSRM container...
    docker rm %CONTAINER_NAME% >nul 2>&1
)

REM Create data directory
if not exist "%DATA_DIR%" (
    echo Creating data directory...
    mkdir "%DATA_DIR%"
)

REM Download map if not present
if not exist "%DATA_DIR%\%MAP_FILE%" (
    echo Downloading Malaysia map data ~300MB, please wait...
    powershell -Command "Invoke-WebRequest -Uri '%MAP_URL%' -OutFile '%DATA_DIR%\%MAP_FILE%' -UseBasicParsing"
    if errorlevel 1 (
        echo ERROR: Failed to download map data.
        exit /b 1
    )
    echo [OK] Map downloaded
) else (
    echo [OK] Map data found
)

REM Pre-process if .osrm not present (one-time, takes a few minutes)
if not exist "%DATA_DIR%\%OSRM_FILE%" (
    echo Pre-processing map data, this runs once and may take several minutes...
    echo.

    echo Step 1/3: Extracting...
    docker run --rm -v "%DATA_DIR%:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/%MAP_FILE%
    if errorlevel 1 (
        echo ERROR: osrm-extract failed.
        exit /b 1
    )

    echo Step 2/3: Partitioning...
    docker run --rm -v "%DATA_DIR%:/data" osrm/osrm-backend osrm-partition /data/%OSRM_FILE%
    if errorlevel 1 (
        echo ERROR: osrm-partition failed.
        exit /b 1
    )

    echo Step 3/3: Customizing...
    docker run --rm -v "%DATA_DIR%:/data" osrm/osrm-backend osrm-customize /data/%OSRM_FILE%
    if errorlevel 1 (
        echo ERROR: osrm-customize failed.
        exit /b 1
    )

    echo [OK] Pre-processing complete
) else (
    echo [OK] Pre-processed data found
)

REM Start OSRM server
echo Starting OSRM server...
docker run -d --name %CONTAINER_NAME% -p 5000:5000 -v "%DATA_DIR%:/data" osrm/osrm-backend ^
    osrm-routed --algorithm mld --max-table-size 10000 /data/%OSRM_FILE%
if errorlevel 1 (
    echo ERROR: Failed to start OSRM container.
    exit /b 1
)

echo.
echo [OK] OSRM is running at http://localhost:5000
echo     Set OSRM_HOST=localhost when starting the API
echo     Run stoposrm.bat to stop

endlocal
