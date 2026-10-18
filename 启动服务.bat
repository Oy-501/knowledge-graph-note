@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 知识图谱系统 - 一键启动

echo ========================================
echo   知识图谱系统 - 一键启动
echo ========================================
echo.

set ROOT=%~dp0
set BACKEND_PORT=8088
set FRONTEND_PORT=5173

:: ---- 1. 检查 Python ----
echo [1/6] 检查 Python...
where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo   [X] 未找到 Python，请先安装 Python 3.10+
        pause ^& exit /b 1
    ) else (
        set PYCMD=python
    )
) else (
    set PYCMD=py
)
echo   [OK] !PYCMD!

:: ---- 2. 检查 Node ----
echo [2/6] 检查 Node...
where npm >nul 2>&1
if errorlevel 1 (
    echo   [X] 未找到 Node.js，请先安装 Node 18+
    pause ^& exit /b 1
)
echo   [OK] npm

:: ---- 3. 后端 .env 兜底（不存在才生成，不覆盖用户配置）----
echo [3/6] 检查后端配置...
if not exist "%ROOT%backend\.env" (
    echo   [!] 未找到 backend\.env，自动生成 SQLite 降级配置（免装 torch）
    > "%ROOT%backend\.env" echo DB_MODE=sqlite
    >> "%ROOT%backend\.env" echo SQLITE_PATH=./kg.db
    >> "%ROOT%backend\.env" echo HOST=127.0.0.1
    >> "%ROOT%backend\.env" echo PORT=!BACKEND_PORT!
    >> "%ROOT%backend\.env" echo DEBUG=true
    >> "%ROOT%backend\.env" echo CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
    >> "%ROOT%backend\.env" echo VECTOR_BACKEND=tfidf
) else (
    echo   [OK] .env 已存在，保留用户配置
)

:: ---- 4. 后端依赖兜底 ----
echo [4/6] 检查后端依赖...
if not exist "%ROOT%backend\app\__pycache__" (
    echo   [!] 首次运行，安装后端轻量依赖（跳过 torch/sentence-transformers，用 tfidf 降级）...
    cd /d "%ROOT%backend"
    !PYCMD! -m pip install fastapi==0.104.1 "uvicorn[standard]==0.24.0" sqlalchemy==2.0.23 python-multipart==0.0.6 python-dotenv==1.0.0 loguru==0.7.2 pydantic==2.5.2 pydantic-settings==2.1.0 python-pptx==1.0.2 python-docx==1.2.0 bcrypt==4.1.2
)

:: ---- 5. 前端依赖兜底 ----
echo [5/6] 检查前端依赖...
if not exist "%ROOT%kg-vue3\node_modules" (
    echo   [!] 首次运行，安装前端依赖（可能要 1-2 分钟）...
    cd /d "%ROOT%kg-vue3"
    call npm install --no-audit --no-fund --ignore-scripts
)

:: ---- 6. 端口占用检测 ----
echo [6/6] 检测端口...
netstat -ano | findstr ":!BACKEND_PORT! " | findstr LISTENING >nul
if not errorlevel 1 (
    echo   [!] 端口 !BACKEND_PORT! 已被占用，自动切换到 8089...
    set BACKEND_PORT=8089
)

:: 同步前端指向
> "%ROOT%kg-vue3\.env.development" echo VITE_API_BASE=http://127.0.0.1:!BACKEND_PORT!/api

echo.
echo   后端端口: !BACKEND_PORT!
echo   前端端口: !FRONTEND_PORT!
echo.

:: ---- 启动后端 ----
echo 启动后端 FastAPI...
start "后端 - FastAPI" cmd /k "cd /d %ROOT%backend ^&^& %PYCMD% -m uvicorn app.main:app --host 127.0.0.1 --port !BACKEND_PORT!"

timeout /t 3 /nobreak >nul

:: ---- 启动前端 ----
echo 启动前端 Vite...
start "前端 - Vue3" cmd /k "cd /d %ROOT%kg-vue3 ^&^& npm run dev"

timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   启动完成
echo   后端 API: http://127.0.0.1:!BACKEND_PORT!
echo   前端页面: http://127.0.0.1:!FRONTEND_PORT!
echo ========================================
echo.

start http://127.0.0.1:!FRONTEND_PORT!

pause
