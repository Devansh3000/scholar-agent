@echo off
REM Setup script for the literature-review-web-app backend virtual environment (Windows)

SET SCRIPT_DIR=%~dp0
SET VENV_DIR=%SCRIPT_DIR%venv

echo Creating Python virtual environment at %VENV_DIR% ...
python -m venv "%VENV_DIR%"

echo Activating virtual environment ...
call "%VENV_DIR%\Scripts\activate.bat"

echo Upgrading pip ...
python -m pip install --upgrade pip

echo Installing dependencies from requirements.txt ...
pip install -r "%SCRIPT_DIR%requirements.txt"

echo.
echo Setup complete. Activate the virtual environment with:
echo   %VENV_DIR%\Scripts\activate.bat
