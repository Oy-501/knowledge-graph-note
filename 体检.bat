@echo off
chcp 65001 >nul 2>&1
title 代码体检 - 启动前的防线

echo ========================================
echo   代码体检 - 在启动服务之前先排雷
echo ========================================
echo   检查项：语法 / 导入 / 路由冲突 / 表结构漂移
echo           静默吞异常 / 关键配置 / 前端工程
echo.

cd /d "%~dp0backend"

py scripts/check.py
if errorlevel 1 (
  echo.
  echo [结果] 存在必须修复的错误，请按上面的「--^> 建议」处理后重新体检。
  echo        带红色 ✕ 的项会让服务启动失败或接口报错，建议先修掉。
) else (
  echo.
  echo [结果] 通过。可以启动服务：启动服务.bat
)

echo.
echo 提示：加 --build 可顺带跑一次前端生产构建（较慢）：
echo       py backend\scripts\check.py --build
echo.
pause
