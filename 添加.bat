@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d D:\policy-brief-site
python add_news.py
echo.
pause
