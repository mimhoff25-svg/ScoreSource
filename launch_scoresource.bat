@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if defined LOCALAPPDATA (
    set "LOG_DIR=%LOCALAPPDATA%\ScoreSource\Logs"
) else (
    set "LOG_DIR=%USERPROFILE%\AppData\Local\ScoreSource\Logs"
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\scoreboard.log"

if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    echo ===== ScoreSource launch %date% %time% =====>>"%LOG_FILE%"
    echo Using Python: %SCRIPT_DIR%\.venv\Scripts\python.exe>>"%LOG_FILE%"
    call "%SCRIPT_DIR%\.venv\Scripts\python.exe" -m scoresource.main >>"%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

where py >nul 2>&1
if %errorlevel%==0 (
    echo ===== ScoreSource launch %date% %time% =====>>"%LOG_FILE%"
    echo Using Python: py -3>>"%LOG_FILE%"
    call py -3 -m scoresource.main >>"%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
    echo ===== ScoreSource launch %date% %time% =====>>"%LOG_FILE%"
    echo Using Python: python>>"%LOG_FILE%"
    call python -m scoresource.main >>"%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

echo Python 3 was not found. Install Python 3.10 or 3.11 first.
exit /b %errorlevel%
