@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Compile-P4-Variants.ps1" %*
set "P4_BUILD_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %P4_BUILD_RESULT%
