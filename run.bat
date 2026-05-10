@echo off
title Retirement Planner - Dev
cd /d "%~dp0"

echo Stopping services on ports 8000 and 3000...
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; foreach ($port in @(8000,3000)) { $c = Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue; if ($c) { $p = $c.OwningProcess; $pp = (Get-CimInstance Win32_Process -Filter ('ProcessId='+$p) -EA 0).ParentProcessId; Stop-Process -Id $p -Force -EA SilentlyContinue; if ($pp -gt 4) { Stop-Process -Id $pp -Force -EA SilentlyContinue } } }; Start-Sleep 1"

echo.
echo   API  http://127.0.0.1:8000
echo   Web  http://127.0.0.1:3000
echo.
npm run dev
