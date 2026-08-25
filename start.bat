@echo off
chcp 936 >nul
cd /d "%~dp0"

echo ============================================================
echo   购物决策助手 Agent  一键启动
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 goto :no_python
where npm >nul 2>&1
if errorlevel 1 goto :no_node

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
for /f %%v in ('node --version 2^>^&1') do set "NODEVER=%%v"
echo [检查] Python %PYVER%  /  Node %NODEVER%
echo.

if exist "local.env" (
  echo [配置] 已找到 local.env，将加载其中的 LLM / Postgres 配置
) else (
  echo [配置] 未找到 local.env，将走离线策略决策 + 内存记忆（功能完整）
  echo        要接 API Key 或 Postgres：copy local.env.example local.env，详见 docs\CONFIG.md
)
echo.
echo [1/4] 检查后端依赖 ...
python -c "import fastapi, uvicorn, httpx" >nul 2>&1
if errorlevel 1 goto :install_backend
echo        后端依赖已就绪
goto :check_frontend

:install_backend
echo        首次运行,正在安装后端依赖,请稍候 ...
python -m pip install -q -r "backend\requirements.txt"
if errorlevel 1 goto :backend_failed
echo        后端依赖安装完成

:check_frontend
echo [2/4] 检查前端依赖 ...
if exist "frontend\node_modules" goto :frontend_ready
echo        首次运行,正在安装前端依赖,可能需要几分钟 ...
pushd "frontend"
call npm install --silent
if errorlevel 1 goto :frontend_failed
popd
echo        前端依赖安装完成
goto :run_backend

:frontend_ready
echo        前端依赖已就绪

:run_backend
echo [3/4] 启动后端服务 http://127.0.0.1:8000 ...
start "选购助手-后端" /min cmd /c "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

set /a TRIES=0
:wait_backend
set /a TRIES+=1
timeout /t 1 /nobreak >nul
python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)" >nul 2>&1
if not errorlevel 1 goto :backend_ok
if %TRIES% lss 30 goto :wait_backend
echo        [警告] 后端未在 30 秒内就绪,请查看"选购助手-后端"窗口
goto :run_frontend

:backend_ok
echo        后端已就绪

:run_frontend
echo [4/4] 启动前端界面 http://localhost:5173 ...
start "选购助手-前端" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo ============================================================
echo   启动完成
echo ------------------------------------------------------------
echo   界面地址   http://localhost:5173
echo   接口文档   http://127.0.0.1:8000/docs
echo   数据模式   mock  本地样本,不访问外部平台
echo.
echo   试试对它说:
echo     预算 7000 左右,主要编程开发,经常带出门
echo ------------------------------------------------------------
echo   停止服务:双击 stop.bat
echo ============================================================
echo.
if /i "%~1"=="/ci" exit /b 0
echo 按任意键关闭本窗口,服务会继续在后台运行 ...
pause >nul
exit /b 0

:no_python
echo [错误] 未找到 Python,请安装 Python 3.11+ 并加入 PATH
echo        https://www.python.org/downloads/
goto :fail

:no_node
echo [错误] 未找到 Node.js,请安装 Node.js 18+ 并加入 PATH
echo        https://nodejs.org/
goto :fail

:backend_failed
echo [错误] 后端依赖安装失败,请检查网络,或手动执行:
echo        python -m pip install -r backend\requirements.txt
goto :fail

:frontend_failed
popd
echo [错误] 前端依赖安装失败,请检查网络,或手动执行:
echo        cd frontend  然后  npm install
goto :fail

:fail
echo.
if /i "%~1"=="/ci" exit /b 1
pause >nul
exit /b 1