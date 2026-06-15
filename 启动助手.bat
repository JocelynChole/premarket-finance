@echo off
chcp 65001 >nul
title 盘前财经资讯研判智能体
setlocal enabledelayedexpansion

REM ============================================================
REM  盘前财经资讯研判智能体 · Windows 一键启动菜单
REM ============================================================

echo.
echo ============================================================
echo    盘前财经资讯研判智能体  v1.0
echo    Premarket Finance Dispatch
echo ============================================================
echo.

REM ---------- 检查 Python ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] 未检测到 Python，请先安装 Python 3.8+
    echo     下载地址：https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python !PYVER!

REM ---------- 进入脚本目录 ----------
cd /d "%~dp0"

REM ---------- 检查依赖 ----------
echo.
echo [1/4] 检查 Python 依赖...
python -c "import flask, requests, schedule" >nul 2>&1
if errorlevel 1 (
    echo [!] 缺少依赖，正在安装（首次约需 30s）...
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [X] 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)
echo [OK] 依赖完整

REM ---------- 检查 china-finance-rss ----------
echo.
echo [2/4] 检查 china-finance-rss 数据服务...
if not exist "china-finance-rss\server.py" (
    echo [!] 未找到 china-finance-rss 目录
    echo     需要从 GitHub 克隆数据采集服务
    echo.
    set /p CLONE=是否现在自动克隆？(Y/n):
    if /i not "!CLONE!"=="n" (
        echo 正在克隆 https://github.com/yuxuan-made/china-finance-rss.git ...
        git clone https://github.com/yuxuan-made/china-finance-rss.git
        if errorlevel 1 (
            echo [X] 克隆失败，请手动执行: git clone https://github.com/yuxuan-made/china-finance-rss.git
        ) else (
            echo [OK] 克隆完成
        )
    )
) else (
    echo [OK] china-finance-rss 已就绪
)

REM ---------- 检查 china-finance-rss 是否在运行 ----------
echo.
curl -s -o nul -w "%%{http_code}" http://localhost:8053/ 2>nul | findstr "200" >nul
if errorlevel 1 (
    echo [!] china-finance-rss 服务未在 :8053 运行
    echo     需要先启动数据服务才能抓取资讯
    set /p START_RSS=是否现在启动数据服务？(Y/n):
    if /i not "!START_RSS!"=="n" (
        echo.
        echo ============================================================
        echo   正在启动 china-finance-rss ...  请勿关闭此窗口
        echo ============================================================
        start "china-finance-rss" cmd /k "cd /d %~dp0china-finance-rss && python server.py"
        timeout /t 3 /nobreak >nul
        echo.
    )
) else (
    echo [OK] china-finance-rss 已在 :8053 运行
)

REM ---------- 主菜单 ----------
:menu
echo.
echo ============================================================
echo    启动选项
echo ============================================================
echo.
echo    [1] 启动 Web 服务（推荐）
echo        -> 浏览器打开 http://localhost:5000
echo.
echo    [2] 启动定时任务调度器（后台常驻）
echo        -> 自动每天 08:30 抓取、09:25 推送
echo.
echo    [3] 立即执行一次（抓取+分析+生成+推送）
echo        -> 命令行模式，看 log
echo.
echo    [4] 设置 Windows 任务计划（开机自启）
echo        -> 创建 4 个计划：数据服务/Web服务/抓取/推送
echo.
echo    [5] 仅启动数据服务 china-finance-rss
echo.
echo    [6] 查看 README
echo.
echo    [0] 退出
echo.
echo ============================================================
echo.

set /p OPT=请选择 (0-6):

if "%OPT%"=="1" goto :web
if "%OPT%"=="2" goto :scheduler
if "%OPT%"=="3" goto :runnow
if "%OPT%"=="4" goto :tasks
if "%OPT%"=="5" goto :rss
if "%OPT%"=="6" goto :readme
if "%OPT%"=="0" goto :end

echo [X] 无效选择
goto :menu

REM ---------- 选项 1: Web 服务 ----------
:web
echo.
echo ============================================================
echo   启动 Web 服务
echo   浏览器访问:  http://localhost:5000
echo   按 Ctrl+C 退出
echo ============================================================
echo.
python app.py
pause
goto :menu

REM ---------- 选项 2: 定时任务调度器 ----------
:scheduler
echo.
echo ============================================================
echo   启动定时任务调度器（后台常驻）
echo   抓取时间: 08:30 / 推送时间: 09:25
echo   按 Ctrl+C 退出
echo ============================================================
echo.
python scheduler.py
pause
goto :menu

REM ---------- 选项 3: 立即执行 ----------
:runnow
echo.
echo ============================================================
echo   立即执行一次完整流程
echo ============================================================
echo.
python scheduler.py --now
echo.
pause
goto :menu

REM ---------- 选项 4: Windows 任务计划 ----------
:tasks
echo.
python setup_tasks.py
goto :menu

REM ---------- 选项 5: 数据服务 ----------
:rss
if not exist "china-finance-rss\server.py" (
    echo.
    echo [X] 未找到 china-finance-rss\server.py
    echo     请先克隆：git clone https://github.com/yuxuan-made/china-finance-rss.git
    pause
    goto :menu
)
echo.
echo ============================================================
echo   启动 china-finance-rss（请勿关闭此窗口）
echo   端口: 8053
echo ============================================================
echo.
cd china-finance-rss
python server.py
pause
goto :menu

REM ---------- 选项 6: README ----------
:readme
if exist "README.md" (
    start "" README.md
) else (
    echo 未找到 README.md
    pause
)
goto :menu

:end
echo.
echo 再见！
endlocal
exit /b 0
