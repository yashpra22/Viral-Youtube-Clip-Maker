@echo off
echo ========================================
echo   AutoClip Setup Script
echo ========================================
echo.

:: Check Python
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11 or 3.12 first.
    pause
    exit /b 1
)
echo Python found.

:: Create virtual environment
echo [2/6] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo Virtual environment created.

:: Install dependencies
echo [3/6] Installing Python dependencies (this may take several minutes)...
.venv\Scripts\pip install -e ".[dev]"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo Dependencies installed.

:: Install ffmpeg
echo [4/6] Checking ffmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo WARNING: ffmpeg not found on PATH.
    echo Please install ffmpeg manually:
    echo   Windows: winget install Gyan.FFmpeg
    echo   macOS:   brew install ffmpeg-full
    echo   Linux:   sudo apt install ffmpeg
    echo.
    echo Press any key to continue...
    pause >nul
) else (
    echo ffmpeg found.
)

:: Build frontend
echo [5/6] Building frontend UI...
cd frontend
npm install
if errorlevel 1 (
    echo ERROR: npm install failed.
    cd ..
    pause
    exit /b 1
)
npm run build
if errorlevel 1 (
    echo ERROR: npm run build failed.
    cd ..
    pause
    exit /b 1
)
cd ..
echo Frontend built.

:: Verify setup
echo [6/6] Running autoclip doctor...
.venv\Scripts\autoclip.exe doctor
if errorlevel 1 (
    echo WARNING: Doctor found issues. Please fix them before running AutoClip.
    echo.
    echo Press any key to continue...
    pause >nul
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo To start AutoClip:
echo   .venv\Scripts\autoclip.exe serve
echo   Then open: http://localhost:8000
echo.
echo To use automation:
echo   .venv\Scripts\python scripts\get_urls.py
echo   .venv\Scripts\python scripts\process_videos.py
echo.
pause