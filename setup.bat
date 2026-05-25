@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 群成员导出工具 - 一键安装并启动

echo.
echo ===== 群成员导出工具 · 一键安装 =====
echo.
echo === 1/3 检查 / 自动安装 Python ===
call :findpy
if not defined PYEXE (
  echo 未检测到 Python，正在为你自动安装（首次约 1-3 分钟，请稍候）...
  where winget >nul 2>nul
  if !errorlevel! equ 0 (
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
  ) else (
    echo 正在下载 Python 安装包...
    powershell -ExecutionPolicy Bypass -NoProfile -Command "try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile $env:TEMP'\py_setup.exe'}catch{exit 1}"
    if exist "%TEMP%\py_setup.exe" (
      echo 正在安装 Python（静默，请稍候）...
      "%TEMP%\py_setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
    )
  )
  call :findpy
)
if not defined PYEXE (
  echo.
  echo [×] Python 没能自动装上。请手动安装：https://www.python.org/downloads/
  echo     安装第一屏勾选 “Add Python to PATH”，装完后重新双击本文件。
  echo.
  pause
  exit /b 1
)
echo     使用 Python: %PYEXE%

echo === 2/3 安装依赖 ===
"%PYEXE%" -m pip install --quiet --upgrade pip
"%PYEXE%" -m pip install --quiet flask requests openpyxl
if errorlevel 1 (
  echo [×] 依赖安装失败，请检查网络后重试。
  pause
  exit /b 1
)

echo === 3/3 启动服务 ===
echo.
echo =====================================================
echo   已启动！浏览器请打开： http://localhost:8000
echo   （4 秒后会自动打开浏览器）
echo   关闭本窗口即可停止；以后直接双击本文件即可
echo =====================================================
echo.
start "" cmd /c "timeout /t 4 >nul & start "" http://localhost:8000"
"%PYEXE%" -m group_export serve --port 8000
echo.
echo 服务已停止。
pause
exit /b 0

:findpy
set "PYEXE="
where py >nul 2>nul && ( set "PYEXE=py" & goto :eof )
for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | find /i "WindowsApps" >nul
  if errorlevel 1 ( set "PYEXE=%%P" & goto :eof )
)
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
if not defined PYEXE for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
goto :eof
