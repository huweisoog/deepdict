@echo off
setlocal
cd /d "%~dp0"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo 还没有安装运行环境，先运行 install.bat。
    pause
    exit /b 1
)
start "" "%PYW%" "%~dp0run.pyw"
