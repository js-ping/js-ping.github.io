#!/bin/bash
# 重新生成「内容源/软件清单与免费资源.md」
# 双击即可。会先跑 build.py --dump 拿最新内容，再按「目标结构.txt」合并 + 校验。
# 校验不过会停在窗口里让你看原因，不会写出半成品。

cd "$(dirname "$0")/../.." || exit 1

echo "工作目录：$(pwd)"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "找不到 python3。macOS 自带的 /usr/bin/python3 一般都有，"
  echo "如果确实没有，去 python.org 装一个再双击本文件。"
  echo
  echo "按回车关闭。"; read -r _
  exit 1
fi

python3 scripts/合并清单/合并清单.py
rc=$?

echo
if [ $rc -eq 0 ]; then
  echo "──────────────────────────────────────────────"
  echo "好了。合并稿已写到：内容源/软件清单与免费资源.md"
  echo "想上站的话，去 build.py 的 LIST_PAGES 里登记它。"
else
  echo "──────────────────────────────────────────────"
  echo "没通过校验（退出码 $rc）。上面写了原因，"
  echo "照着改「目标结构.txt」再双击一次。"
fi
echo
echo "按回车关闭。"
read -r _
