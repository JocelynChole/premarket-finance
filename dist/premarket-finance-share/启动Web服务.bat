@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   启动盘前财经 Web 服务
echo   浏览器请访问:  http://localhost:5000
echo   按 Ctrl+C 关闭
echo ============================================================
echo.
python app.py
pause
