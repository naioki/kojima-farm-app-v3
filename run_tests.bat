@echo off
echo Running tests...
python -m pytest tests/
if %errorlevel% neq 0 (
    echo Tests failed!
    pause
    exit /b %errorlevel%
)
echo Tests passed!
pause
