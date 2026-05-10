@echo off
title Retirement Planner - Tests
cd /d "%~dp0"

echo Running all tests...
echo.

python -m pytest tests\ -v --tb=short

echo.
if %ERRORLEVEL% EQU 0 (
    echo All tests passed.
) else (
    echo One or more tests failed. See output above.
)
echo.
pause
