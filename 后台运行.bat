@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo 正在后台启动（关闭本窗口不会停止服务）...
powershell -NoProfile -Command "Start-Process -FilePath (Get-Command py).Source -ArgumentList 'scripts/serve.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
timeout /t 6 >nul
py scripts\serve.py --status
echo.
echo 前端 http://127.0.0.1:5173   后端 http://127.0.0.1:8080
echo 日志目录 logs\（serve.log / backend.log / frontend.log）
pause
