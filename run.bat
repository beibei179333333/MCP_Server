@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 群成员导出工具

rem ---- 找 Python ----
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo.
  echo [×] 没有找到 Python。
  echo     请先到 https://www.python.org/downloads/ 安装 Python 3，
  echo     安装时务必勾选 “Add Python to PATH”，装完后重新双击本文件。
  echo.
  pause
  exit /b 1
)

rem ---- 确保依赖已安装 ----
%PY% -c "import flask,requests,openpyxl" 1>nul 2>nul
if errorlevel 1 (
  echo [*] 首次运行，正在安装依赖 (flask / requests / openpyxl)...
  %PY% -m pip install --quiet flask requests openpyxl
  if errorlevel 1 (
    echo [×] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)

set "CMD=%~1"
if "%CMD%"=="" set "CMD=web"

if /i "%CMD%"=="web" (
  echo.
  echo =====================================================
  echo   群成员导出工具 已启动
  echo   浏览器请打开： http://localhost:8000
  echo   关闭本窗口即可停止
  echo =====================================================
  echo.
  rem 3 秒后自动打开浏览器（等服务起来）
  start "" cmd /c "timeout /t 3 >nul & start "" http://localhost:8000"
  %PY% -m group_export serve --port 8000
) else if /i "%CMD%"=="test" (
  %PY% tests\test_pipeline.py
  pause
) else (
  %PY% -m group_export %*
  pause
)

endlocal
