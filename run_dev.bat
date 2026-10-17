@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment in .venv...
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python launcher ^(py.exe^) was not found.
        echo Install Python 3.10 or newer and try again.
        exit /b 1
    )

    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
)

"%PYTHON_EXE%" -c "import PySide6, dissect.xfs, pyewf" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing development dependencies...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    if errorlevel 1 goto :error
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 goto :error
)

echo [INFO] Starting CCTV Log Analyzer (PySide6) in development mode...
"%PYTHON_EXE%" "%~dp0cctv_log_analyzer.py"
exit /b %errorlevel%

:error
echo [ERROR] Development environment setup failed.
exit /b 1
