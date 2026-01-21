@echo off
chcp 65001 >nul
echo ======================================
echo   股票推荐系统 - 一键安装脚本
echo ======================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未检测到Python，请先安装Python3
    echo    访问: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✓ 检测到Python
python --version
echo.

REM 安装依赖
echo 正在安装依赖包...
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ❌ 安装失败，请检查网络连接或手动安装:
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo ======================================
echo ✓ 安装成功！
echo ======================================
echo.
echo 使用方法:
echo   双击运行: run.bat
echo   或命令行: python stock_recommender.py
echo.
pause
