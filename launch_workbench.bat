@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================================
echo   SciFigStudio Interactive Workbench (v2.1.0)
echo   Origin-free Declarative Chemistry Figure Studio
echo ============================================================
echo.

set "PYCMD="
where python >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
    where py >nul 2>&1 && set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [ERROR] Python 3.10+ not found in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo or download the zero-install SciFigStudio-Workbench-win64.zip from GitHub Releases.
    pause
    exit /b 1
)

echo [1/2] Checking required Python packages...
%PYCMD% -X utf8 -c "import matplotlib, numpy, scipy, pandas, PIL, pymupdf, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Some scientific dependencies are missing. Installing from requirements.txt...
    %PYCMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Please check your network / pip environment.
        pause
        exit /b 1
    )
)

echo [2/2] Starting Interactive Workbench (http://127.0.0.1:8765/)...
echo       Keep this window open while using the browser UI. Press Ctrl+C to stop.
echo.
set "SCIFIG_ASSETS=%~dp0assets"
set "PYTHONUTF8=1"
%PYCMD% -X utf8 -m scifig workbench %*
if errorlevel 1 (
    echo.
    echo [ERROR] Workbench exited with an error.
    pause
)
endlocal
