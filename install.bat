@echo off
setlocal
cd /d "%~dp0"
echo 正在准备 DeepDict 运行环境...
where python >nul 2>nul
if errorlevel 1 (
    echo 没有找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH。
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    python -m venv --system-site-packages .venv
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q comtypes uiautomation
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q PyQt5 pywin32 requests
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m deepdict --selftest
echo.
echo 安装完成。双击 run.bat 启动。
pause
