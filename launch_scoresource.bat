@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PY_CMD=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if exist "%PY_CMD%" goto have_python

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py -3"
    goto have_python
)

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=python"
    goto have_python
)

echo Python 3 was not found. Install Python 3.10 or 3.11 first.
exit /b 1

:have_python
if defined LOCALAPPDATA (
    set "LOG_DIR=%LOCALAPPDATA%\ScoreSource\Logs"
) else (
    set "LOG_DIR=%USERPROFILE%\AppData\Local\ScoreSource\Logs"
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\scoreboard.log"

echo ===== ScoreSource launch %date% %time% =====>>"%LOG_FILE%"
echo Using Python: %PY_CMD%>>"%LOG_FILE%"
call %PY_CMD% -m scoresource.main >>"%LOG_FILE%" 2>&1
exit /b %errorlevel%
