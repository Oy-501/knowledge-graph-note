@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 知识图谱系统 - 一键启动

echo ========================================
echo   知识图谱系统 - 一键启动
echo ========================================
echo.

set ROOT=%~dp0

:: ---- 1. 检查 Python ----
:: 注意：Windows 商店版的 python.exe 可能是「应用执行别名」空壳（退出码 9009），
:: 所以优先用 py 启动器，找不到再退回 python。
echo [1/5] 检查 Python...
set PYCMD=
where py >nul 2>&1
if not errorlevel 1 set PYCMD=py
if not defined PYCMD (
    where python >nul 2>&1
    if not errorlevel 1 set PYCMD=python
)
if not defined PYCMD (
    echo   [X] 未找到 Python，请先安装 Python 3.10+
    pause & exit /b 1
)
!PYCMD! --version
echo   [OK] !PYCMD!

:: ---- 2. 检查 Node ----
echo [2/5] 检查 Node...
where npm >nul 2>&1
if errorlevel 1 (
    echo   [X] 未找到 Node.js，请先安装 Node 18+
    pause & exit /b 1
)
echo   [OK] npm

:: ---- 3. 后端 .env 兜底（不存在才生成，不覆盖用户配置）----
echo [3/5] 检查后端配置...
if not exist "%ROOT%backend\.env" (
    echo   [!] 未找到 backend\.env，自动生成 SQLite 配置（免装 PostgreSQL）
    > "%ROOT%backend\.env" echo DB_MODE=sqlite
    >> "%ROOT%backend\.env" echo SQLITE_PATH=./kg.db
    >> "%ROOT%backend\.env" echo HOST=127.0.0.1
    >> "%ROOT%backend\.env" echo PORT=8080
    >> "%ROOT%backend\.env" echo DEBUG=true
    >> "%ROOT%backend\.env" echo CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
    >> "%ROOT%backend\.env" echo VECTOR_BACKEND=tfidf
) else (
    echo   [OK] .env 已存在，保留用户配置
)

:: ---- 4. 后端依赖兜底（用真实导入判断，不再用 __pycache__ 猜测）----
echo [4/5] 检查后端依赖...
cd /d "%ROOT%backend"
!PYCMD! -c "import fastapi, uvicorn, sqlalchemy, pydantic, pydantic_settings, docx, pptx, bcrypt, loguru, multipart" >nul 2>&1
if errorlevel 1 (
    echo   [!] 缺少后端依赖，安装轻量依赖（跳过 torch，语义向量自动降级为 tfidf）...
    !PYCMD! -m pip install fastapi==0.104.1 "uvicorn[standard]==0.24.0" sqlalchemy==2.0.23 psycopg2-binary==2.9.9 python-multipart==0.0.6 python-dotenv==1.0.0 loguru==0.7.2 pydantic==2.5.2 pydantic-settings==2.1.0 python-pptx==1.0.2 python-docx==1.2.0 bcrypt==4.1.2
    if errorlevel 1 (
        echo   [X] 依赖安装失败，请检查网络或手动执行：
        echo       cd backend ^&^& !PYCMD! -m pip install -r requirements.txt
        pause & exit /b 1
    )
) else (
    echo   [OK] 依赖已就绪
)

:: ---- 5. 前端依赖兜底 ----
echo [5/5] 检查前端依赖...
if not exist "%ROOT%kg-vue3\node_modules" (
    echo   [!] 首次运行，安装前端依赖（可能要 1-2 分钟）...
    cd /d "%ROOT%kg-vue3"
    call npm install --no-audit --no-fund --ignore-scripts
    if errorlevel 1 (
        echo   [X] 前端依赖安装失败，请检查网络后重试
        pause & exit /b 1
    )
) else (
    echo   [OK] node_modules 已就绪
)

:: ---- 统一交给 scripts\dev.py ----
:: 端口读取、占用检测、重复实例复用、前后端就绪等待都在这里，避免两套逻辑打架。
cd /d "%ROOT%"
echo.
echo 启动中（首次加载语义模型可能稍慢）...
echo 关闭本窗口即停止前后端。
echo.
!PYCMD! scripts\dev.py --open

echo.
echo 服务已停止。
pause
