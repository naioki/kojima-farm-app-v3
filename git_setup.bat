@echo off
echo Initializing Git repository...
git init
if %errorlevel% neq 0 (
    echo Failed to initialize git. Is git installed?
    pause
    exit /b
)

echo Adding files...
git add .

echo Committing files...
git commit -m "Initial commit for Kojima Farm DX App"

echo.
echo ==========================================
echo  Git repository initialized successfully!
echo ==========================================
echo.
echo Next steps:
echo 1. Create a new repository on GitHub.
echo 2. Run the following commands (replace URL with yours):
echo    git branch -M main
echo    git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
echo    git push -u origin main
echo.
pause
