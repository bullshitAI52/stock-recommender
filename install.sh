#!/bin/bash

echo "======================================"
echo "  股票推荐系统 - 一键安装脚本"
echo "======================================"
echo ""

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未检测到Python3，请先安装Python3"
    echo "   访问: https://www.python.org/downloads/"
    exit 1
fi

echo "✓ 检测到Python3: $(python3 --version)"
echo ""

# 安装依赖
echo "正在安装依赖包..."
echo ""

if pip3 install --break-system-packages -r requirements.txt; then
    echo ""
    echo "======================================"
    echo "✓ 安装成功！"
    echo "======================================"
    echo ""
    echo "使用方法:"
    echo "  运行: python3 stock_recommender.py"
    echo ""
    echo "或者使用快捷启动:"
    echo "  运行: ./run.sh"
    echo ""
else
    echo ""
    echo "❌ 安装失败，请检查网络连接或手动安装:"
    echo "   pip3 install --break-system-packages -r requirements.txt"
    exit 1
fi
