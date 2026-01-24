# Development Scripts

This directory contains convenience scripts for development tasks.

## Setup

Install development dependencies:

```cmd
scripts\setup.bat
```

## Available Scripts

### Format Code

Format Python code with Black and isort:

```cmd
scripts\format.bat
```

### Lint Code

Run all code quality checks (flake8, mypy):

```cmd
scripts\lint.bat
```

### Run Tests

Run the test suite:

```cmd
scripts\test.bat
```

### Run Application

Run the Home Assistant Windows client:

```cmd
scripts\run.bat
```

## Manual Commands

If you prefer to run commands manually:

```cmd
# Format code
python -m black src/ tests/
python -m isort src/ tests/

# Lint code
python -m flake8 src/ --max-line-length=120 --ignore=E501,W503,E203,D202,W504,E266 --statistics
python -m mypy src/ --ignore-missing-imports

# Run tests
python -m pytest tests/ -v --tb=short

# Run application
python -m src
```