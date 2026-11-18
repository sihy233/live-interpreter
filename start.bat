@echo off
chcp 65001 >nul
title Live Interpreter
cd /d "%~dp0"
set PYTHONUTF8=1
set HF_ENDPOINT=https://hf-mirror.com

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found. Install it from https://docs.astral.sh/uv/
    pause
    exit /b 1
)

if not exist "tools\.ready" (
    uv run python setup.py
    if errorlevel 1 (
        echo.
        echo Setup failed. See the error above.
        pause
        exit /b 1
    )
)

uv run python main.py %*
if errorlevel 1 pause
