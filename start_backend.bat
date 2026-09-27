@echo off
echo OCR Chatbot Backend Starter
echo ==========================
echo.

cd backend

echo Checking for Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Please install Python 3.7+ and try again.
    exit /b 1
)

echo Installing dependencies...
python install_dependencies.py
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    exit /b 1
)

echo.
echo Starting backend server...
echo The server will run on http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python app.py 