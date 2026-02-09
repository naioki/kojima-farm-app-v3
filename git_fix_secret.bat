@echo off
echo ==========================================
echo      Fixing Git Secrets Issue
echo ==========================================
echo.

echo Removing secret file from git tracking...
git rm --cached streamlit-sheets-486912-5dd20ca660e9.json

echo Updating .gitignore...
:: .gitignore is already updated by the agent tool, but ensuring it is added
git add .gitignore

echo rewriting the commit to remove the secret...
git commit --amend --no-edit

echo.
echo ==========================================
echo   Secret removed from history!
echo   Retrying push...
echo ==========================================
echo.

git push -u origin main -f

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS! Pushed to GitHub.
) else (
    echo.
    echo Push failed. Please check the error message.
)
pause
