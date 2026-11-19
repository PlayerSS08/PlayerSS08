@echo off
rem Double-click to open Invoice Extractor in your browser.
rem First start installs the libraries once; later starts open straight away.
title Invoice Extractor
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 launch.py
    goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
    python launch.py
    goto done
)
echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
echo and tick "Add Python to PATH", then double-click this file again.

:done
echo.
pause
