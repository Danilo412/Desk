@echo off
setlocal
set "REPO_ROOT=%~dp0.."
set "DEFAULT_VENV=C:\Users\danil\Documents\Codex\2026-10-28\in\work\novoacesso-build\venv\Scripts\python.exe"
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PY=%REPO_ROOT%\.venv\Scripts\python.exe"
) else if exist "%DEFAULT_VENV%" (
    set "PY=%DEFAULT_VENV%"
) else (
    set "PY=python"
)

set "TASK=%~1"
if "%TASK%"=="" set "TASK=run"

pushd "%REPO_ROOT%"
if /I "%TASK%"=="run" (
    set "PYTHONPATH=%REPO_ROOT%\src"
    "%PY%" "%REPO_ROOT%\iniciar.py"
) else if /I "%TASK%"=="test" (
    set "QT_QPA_PLATFORM=offscreen"
    set "NOVOACESSO_OFFLINE=1"
    set "DESK_AUTOREADY=0"
    set "PYTHONPATH=%REPO_ROOT%\src"
    "%PY%" -m pytest tests -q --disable-warnings
) else if /I "%TASK%"=="build" (
    "%PY%" "%REPO_ROOT%\scripts\publish_release.py" --skip-tests --dry-run
) else if /I "%TASK%"=="store" (
    "%PY%" "%REPO_ROOT%\scripts\build_store_msix.py" --build
) else if /I "%TASK%"=="publish" (
    "%PY%" "%REPO_ROOT%\scripts\publish_release.py" --publish
) else (
    echo Uso: scripts\dev.cmd [run^|test^|build^|store^|publish]
    popd
    exit /b 1
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
