@echo off
echo ========================================
echo DocHive Backend - Installing Dependencies
echo ========================================
echo.

echo Creating virtual environment...
python -m venv venv

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Creating .env file from template...
if not exist .env (
    copy .env.example .env
    echo .env file created. Please edit it with your configuration.
) else (
    echo .env file already exists.
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Edit .env file with your configuration
echo 2. Start PostgreSQL, Redis, and MinIO services
echo 3. Run: python main.py
echo.
pause
