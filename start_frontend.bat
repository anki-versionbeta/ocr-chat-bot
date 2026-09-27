@echo off
echo OCR Chatbot Frontend Starter
echo ===========================
echo.

cd frontend

echo Checking for Node.js...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js not found! Please install Node.js 14+ and try again.
    exit /b 1
)

echo Checking for npm...
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo npm not found! Please install Node.js with npm and try again.
    exit /b 1
)

echo Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    exit /b 1
)

echo.
echo Starting frontend development server...
echo The server will run on http://localhost:3000
echo Press Ctrl+C to stop the server
echo.

call npm run dev 