@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo       GitHub Publish Helper
echo ==========================================
echo.

:: Check if remote 'origin' exists
git remote get-url origin >nul 2>&1
if %errorlevel% equ 0 (
    echo Remote 'origin' is already configured:
    git remote get-url origin
    echo.
    set /p CHOICE="Is this the correct repository URL? (Y/N): "
    if /i "!CHOICE!"=="N" (
        set /p NEW_URL="Enter the new GitHub Repository URL: "
        git remote set-url origin !NEW_URL!
        echo Remote URL updated.
    )
) else (
    echo Remote 'origin' is NOT configured.
    echo Please create a repository on GitHub first.
    echo.
    set /p NEW_URL="Enter the GitHub Repository URL (e.g., https://github.com/user/repo.git): "
    git remote add origin !NEW_URL!
    echo Remote 'origin' added.
)

echo.
echo Pushing to GitHub...
echo.
git branch -M main
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo    Successfully pushed to GitHub!
    echo ==========================================
) else (
    echo.
    echo ==========================================
    echo    Push failed.
    echo    Please check your URL and internet connection.
    echo    You may need to sign in to GitHub in the popup.
    echo ==========================================
)
pause
