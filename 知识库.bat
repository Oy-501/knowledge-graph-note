@echo off
chcp 65001 >nul 2>&1
title 知识库构建工具

echo ========================================
echo   知识库构建 - 关系推导 / 锚定 / 知识关联
echo ========================================
echo.

cd /d "%~dp0backend"

echo [1/2] 推导知识库关系边（related_terms + 桥接句 + 别名等价）...
py scripts/kb_build.py --relations-only

echo.
echo [2/2] 全量重建：文档锚定 - 知识画像 - 文件/节点知识关联 ...
py scripts/kb_build.py

echo.
echo 完成。可在前端「知识库」页面查看结果。
pause
