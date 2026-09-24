@echo off
chcp 65001 >nul 2>&1
title 知识图谱系统

echo ========================================
echo   知识图谱系统 - 一键启动
echo ========================================
echo.

:: 启动后端（app.main，端口 8080）
echo [1/2] 启动后端 FastAPI (端口 8080)...
start "后端 - FastAPI" cmd /k "cd /d c:\Users\yr200\Documents\trae_projects\YR\backend && py -m uvicorn app.main:app --host 127.0.0.1 --port 8080"

timeout /t 3 /nobreak >nul

:: 启动前端
echo [2/2] 启动前端 Vue3 Dev Server (端口 5173)...
start "前端 - Vue3" cmd /k "cd /d c:\Users\yr200\Documents\trae_projects\YR\kg-vue3 && npm run dev"

timeout /t 3 /nobreak >nul

echo.
echo   后端 API: http://127.0.0.1:8080
echo   前端页面: http://127.0.0.1:5173
echo ========================================
echo.
echo 请在浏览器打开 http://127.0.0.1:5173
echo.
pause
