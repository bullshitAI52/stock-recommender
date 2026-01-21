@echo off
chcp 65001 >nul
echo ======================================
echo   股票推荐系统 - 启动中...
echo ======================================
echo.

python stock_recommender.py

echo.
echo ======================================
echo   运行完成！
echo ======================================
echo.
pause
