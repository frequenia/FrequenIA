@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%tools\start_local.ps1" %*
exit /b %ERRORLEVEL%
