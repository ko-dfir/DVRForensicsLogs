@echo off
if /I "%~1"=="--internal-build" goto :build

setlocal
cd /d "%~dp0"
set "CCTV_BUILD_EXE_ONLY=0"
if /I "%~1"=="--exe-only" set "CCTV_BUILD_EXE_ONLY=1"
if not "%~1"=="" if /I not "%~1"=="--exe-only" (
    echo Usage: build.bat [--exe-only]
    pause
    exit /b 1
)
set "CCTV_BUILD_SELF=%~f0"
set "CCTV_BUILD_LOG_DIR=%~dp0build-logs"
if not exist "%CCTV_BUILD_LOG_DIR%" (
    mkdir "%CCTV_BUILD_LOG_DIR%"
    if errorlevel 1 (
        echo [ERROR] Could not create build log directory: %CCTV_BUILD_LOG_DIR%
        pause
        exit /b 1
    )
)
set "CCTV_BUILD_STAMP="
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss-fff"`) do set "CCTV_BUILD_STAMP=%%T"
if not defined CCTV_BUILD_STAMP set "CCTV_BUILD_STAMP=undated"
set "CCTV_BUILD_LOG=%CCTV_BUILD_LOG_DIR%\build-%CCTV_BUILD_STAMP%.log"

echo [INFO] Build log: %CCTV_BUILD_LOG%
powershell -NoProfile -Command "$q=[char]34; $line=$q+$q+$env:CCTV_BUILD_SELF+$q+' --internal-build 2>&1'+$q; & $env:ComSpec /d /s /c $line | Tee-Object -FilePath $env:CCTV_BUILD_LOG; exit $LASTEXITCODE"
set "CCTV_BUILD_RESULT=%ERRORLEVEL%"
echo.
if "%CCTV_BUILD_RESULT%"=="0" (
    echo [SUCCESS] Build finished. Full log: %CCTV_BUILD_LOG%
) else (
    echo [ERROR] Build failed with exit code %CCTV_BUILD_RESULT%. Full log: %CCTV_BUILD_LOG%
)
echo Press any key to close this window.
pause >nul
exit /b %CCTV_BUILD_RESULT%

:build
setlocal

cd /d "%~dp0"
echo [BUILD START] %DATE% %TIME%

rem Keep PySide6's deep package paths outside a long extracted project path.
set "VENV_DIR=%CCTV_BUILD_VENV%"
if not defined VENV_DIR set "VENV_DIR=%LOCALAPPDATA%\CCTVBuild\venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
echo [INFO] Build venv: %VENV_DIR%
echo [INFO] Project: %~dp0
if "%CCTV_BUILD_EXE_ONLY%"=="1" goto :environment

rem Check installer prerequisites before spending time on compilation.
if not defined ISCC_EXE set "ISCC_EXE=%LocalAppData%\Programs\Inno Setup 7\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" (
    echo [ERROR] Inno Setup was not found. No compilation has been started.
    echo Install Inno Setup, set ISCC_EXE to its compiler, or use build.bat --exe-only.
    goto :error
)

:environment

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating short-path build virtual environment...
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python launcher ^(py.exe^) was not found.
        echo Install 64-bit CPython 3.13 or set CCTV_BUILD_VENV to an existing environment.
        exit /b 1
    )

    py -3.13 -m venv "%VENV_DIR%"
    if errorlevel 1 goto :error
)

echo [INFO] Synchronizing pinned build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade -r "%~dp0requirements-build.txt"
if errorlevel 1 goto :error
"%PYTHON_EXE%" -m pip check
if errorlevel 1 goto :error
"%PYTHON_EXE%" -m pip freeze
"%PYTHON_EXE%" -c "import sys, struct; print(sys.version); assert struct.calcsize('P') == 8, '64-bit Python is required'"
if errorlevel 1 goto :error

set "APP_VERSION="
set "WINDOWS_VERSION="
set "CCTV_BUILD_CONFIG=%~dp0tools\build_config.py"
for /f "usebackq tokens=1,* delims==" %%A in (`powershell -NoProfile -Command "& $env:PYTHON_EXE $env:CCTV_BUILD_CONFIG"`) do set "%%A=%%B"
if not defined APP_VERSION (
    echo [ERROR] Could not read version from version.json.
    goto :error
)
if not defined WINDOWS_VERSION goto :error
echo [INFO] Application version: %APP_VERSION% - Windows numeric version: %WINDOWS_VERSION%
set "CCTV_CONSOLE_MODE=disable"
if "%CCTV_BUILD_DIAGNOSTIC%"=="1" set "CCTV_CONSOLE_MODE=force"

echo [INFO] Building Windows executable with Nuitka...
"%PYTHON_EXE%" -m nuitka ^
    --mode=standalone ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=%CCTV_CONSOLE_MODE% ^
    --report="%~dp0build-logs\nuitka-report.xml" ^
    --windows-icon-from-ico="%~dp0assets\cctv-log-analyzer.ico" ^
    --company-name="CCTV Log Analyzer" ^
    --product-name="CCTV Log Analyzer" ^
    --file-description="Multi-vendor CCTV recorder forensic log analysis" ^
    --file-version=%WINDOWS_VERSION% ^
    --product-version=%WINDOWS_VERSION% ^
    --output-dir="%~dp0dist" ^
    --output-filename=CCTVLogAnalyzer.exe ^
    --include-data-files="%~dp0version.json"=version.json ^
    --include-data-files="%~dp0assets\cctv-log-analyzer.ico"=assets/cctv-log-analyzer.ico ^
    --include-data-files="%~dp0assets\arrow-down-dark.svg"=assets/arrow-down-dark.svg ^
    --include-data-files="%~dp0assets\arrow-up-dark.svg"=assets/arrow-up-dark.svg ^
    --include-data-files="%~dp0assets\arrow-down-light.svg"=assets/arrow-down-light.svg ^
    --include-data-files="%~dp0assets\arrow-up-light.svg"=assets/arrow-up-light.svg ^
    --include-data-files="%~dp0assets\check.svg"=assets/check.svg ^
    --include-data-files="%~dp0scripts\hikvision_log_types.json"=scripts/hikvision_log_types.json ^
    "%~dp0cctv_log_analyzer.py"

if errorlevel 1 goto :error
if not exist "%~dp0dist\cctv_log_analyzer.dist\CCTVLogAnalyzer.exe" (
    echo [ERROR] Nuitka output executable was not found.
    goto :error
)

if "%CCTV_BUILD_EXE_ONLY%"=="1" (
    echo [SUCCESS] Executable build completed. Installer was not requested.
    echo %~dp0dist\cctv_log_analyzer.dist\CCTVLogAnalyzer.exe
    echo [INFO] Startup validation must be performed separately; compilation success is not runtime validation.
    echo [BUILD END] %DATE% %TIME% - SUCCESS
    exit /b 0
)

echo [INFO] Building installer v%APP_VERSION%...
"%ISCC_EXE%" /DMyAppVersion=%APP_VERSION% /DMyWindowsVersion=%WINDOWS_VERSION% "%~dp0installer\CCTVLogAnalyzer.iss"
if errorlevel 1 goto :error

echo.
echo [SUCCESS] Build completed:
echo %~dp0dist\cctv_log_analyzer.dist\CCTVLogAnalyzer.exe
echo %~dp0installer-output\CCTVLogAnalyzer-%APP_VERSION%-Setup.exe
echo [BUILD END] %DATE% %TIME% - SUCCESS
exit /b 0

:error
echo [ERROR] Build failed.
echo [BUILD END] %DATE% %TIME% - FAILURE
exit /b 1
