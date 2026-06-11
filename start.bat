@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting SQLark Web UI...
.venv\Scripts\python.exe app/main.py --web --port 8000
pause
