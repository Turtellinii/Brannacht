@echo off
cd /d "%~dp0"

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Download it from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: ── Check / prompt for API key ────────────────────────────────────────────────
if "%ANTHROPIC_API_KEY%"=="" (
    echo Your Anthropic API key is not set.
    echo You can get one at: https://console.anthropic.com
    echo.
    set /p ANTHROPIC_API_KEY="Paste your API key here: "
    if "!ANTHROPIC_API_KEY!"=="" (
        echo No key entered. Exiting.
        pause
        exit /b 1
    )
)

:: ── Install dependencies if missing ──────────────────────────────────────────
python -c "import anthropic" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install -q -r requirements.txt
)

:: ── Launch game ───────────────────────────────────────────────────────────────
python main.py %*

echo.
pause
