@echo off
TITLE EDI Accelerator Platform
echo =================================================
echo  EDI Accelerator Platform - Local Launch
echo =================================================
echo.

SET ROOT=%~dp0
SET PYTHON=C:\Users\ParagW4.MUMBAI1\AppData\Local\Programs\Python\Python314\python.exe
SET BACKEND=%ROOT%backend
SET FRONTEND=%ROOT%frontend

:: Check Python
if not exist "%PYTHON%" (
    echo [ERROR] Python not found at %PYTHON%
    echo Please install Python 3.11+ and update the PYTHON path in this script.
    pause
    exit /b 1
)

:: Check Node
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+.
    pause
    exit /b 1
)

echo [1/3] Starting Backend (FastAPI on http://127.0.0.1:8000) ...
start "EDI Backend" cmd /k "cd /d "%BACKEND%" && "%PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

:: Wait for backend to start
timeout /t 3 /nobreak >nul

echo [2/3] Starting Frontend (React on http://localhost:5173) ...
start "EDI Frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

echo.
echo [3/3] Platform Starting...
echo.
echo   Backend API:  http://127.0.0.1:8000
echo   Frontend UI:  http://localhost:5173
echo   API Docs:     http://127.0.0.1:8000/docs
echo   Health:       http://127.0.0.1:8000/health
echo.
echo Press any key to open the UI in your browser...
pause >nul

start http://localhost:5173
