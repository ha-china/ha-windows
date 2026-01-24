@echo off
REM Format Python code with Black and isort

echo Formatting code with Black...
python -m black src/ tests/

echo.
echo Sorting imports with isort...
python -m isort src/ tests/

echo.
echo Code formatting complete!