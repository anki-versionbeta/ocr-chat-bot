@echo off
echo OCR Chatbot Starter
echo =================
echo.

echo This script will start both the backend and frontend servers in separate windows.
echo Please ensure you have Python 3.7+ and Node.js 14+ installed.
echo.

echo Starting the backend server...
start cmd /k "cd %~dp0 && start_backend.bat"

echo Waiting for backend to initialize (5 seconds)...
timeout /t 5 /nobreak >nul

echo Starting the frontend server...
start cmd /k "cd %~dp0 && start_frontend.bat"

echo.
echo Servers are starting in separate windows.
echo - Backend: http://localhost:5000
echo - Frontend: http://localhost:3000
echo.
echo You can now use the application by opening http://localhost:3000 in your browser.
echo. 