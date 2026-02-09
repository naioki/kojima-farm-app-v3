@echo off
echo Updating Git repository...
git add .
git commit -m "Update all files to ensure everything is synced"
git push origin main
echo Done.
pause
