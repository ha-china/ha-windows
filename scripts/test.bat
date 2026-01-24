@echo off
REM Run test suite

echo Running tests...
python -m pytest tests/ -v --tb=short

echo.
echo Tests complete!