@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo 正在停止守护与前后端...
py scripts\serve.py --stop
timeout /t 2 >nul
py scripts\serve.py --status
pause
