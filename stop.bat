@echo off
chcp 936 >nul
echo 正在停止选购助手服务 ...

for %%p in (8000 5173) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        taskkill /f /pid %%a >nul 2>&1
    )
)

taskkill /f /fi "WINDOWTITLE eq 选购助手-后端*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq 选购助手-前端*" >nul 2>&1

echo 服务已停止。
if /i "%~1"=="/ci" exit /b 0
timeout /t 2 /nobreak >nul