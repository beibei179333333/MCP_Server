@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Telegram 领取监控

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
%PY% -c "import mss, numpy, pyautogui, easyocr" 1>nul 2>nul
if errorlevel 1 (
  echo [*] 首次运行，正在安装监控依赖（mss / numpy / pyautogui / easyocr）...
  echo     easyocr 较大、首次会下载中文识别模型，请耐心等待（需联网）。
  %PY% -m pip install --quiet -r tg_monitor\requirements.txt
  if errorlevel 1 (
    echo [×] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)

echo.
echo =====================================================
echo   Telegram 领取监控 已启动（图形窗口）
echo   1) 先点「框选监控区域」把 Telegram 聊天窗口圈进去
echo   2) 再点「开始监控」
echo   紧急中止：把鼠标快速甩到屏幕左上角
echo =====================================================
echo.
%PY% -m tg_monitor
endlocal
