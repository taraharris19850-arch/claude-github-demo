#!/bin/bash
# 双击我，查看 scrape.center 爬虫学习进度
# Issue：#16
cd "$(dirname "$0")" || exit 1
./status.sh
echo
echo "按任意键关闭窗口…"
read -n 1 -s
