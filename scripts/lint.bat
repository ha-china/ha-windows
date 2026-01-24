@echo off
REM Run all code quality checks

echo Running flake8...
python -m flake8 src/ --max-line-length=120 --ignore=E501,W503,E203,D202,W504,E266 --statistics
if %errorlevel% neq 0 (
    echo.
    echo Flake8 found issues!
    exit /b 1
)

echo.
echo Running mypy...
python -m mypy src/ --ignore-missing-imports
if %errorlevel% neq 0 (
    echo.
    echo MyPy found issues!
    exit /b 1
)

echo.
echo All checks passed!