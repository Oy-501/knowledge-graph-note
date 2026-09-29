@echo off
chcp 65001 >nul
cd /d "c:\Users\yr200\Documents\trae_projects\YR\legacy"
set ELECTRON_CACHE=%cd%\.electron-cache
npx electron .
