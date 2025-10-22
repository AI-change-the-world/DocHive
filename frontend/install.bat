@echo off
echo ========================================
echo DocHive Frontend - Installing Dependencies
echo ========================================
echo.

echo Checking pnpm...
where pnpm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo pnpm not found. Installing pnpm...
    npm install -g pnpm
)

echo.
echo Installing project dependencies...
pnpm install

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo To start development server, run:
echo   pnpm dev
echo.
echo To build for production, run:
echo   pnpm build
echo.
pause
