@echo off
REM Install development dependencies

echo Installing development dependencies...
pip install -e ".[dev]"

echo.
echo Development dependencies installed!
echo.
echo Available commands:
echo   - scripts\format.bat  : Format code
echo   - scripts\lint.bat    : Run code quality checks
echo   - scripts\test.bat    : Run tests
echo   - scripts\run.bat     : Run the application