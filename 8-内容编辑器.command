#!/bin/bash
# 内容编辑器（网页版）—— 双击运行
#   · 浏览器里像填表格一样加条目、改条目、拖拽排序
#   · 点「保存并上线」= 生成页面 + 提交 + 推送到 GitHub
#   · 只在本机跑，不联网、不装东西
# 想直接改 markdown 的话，双击「1-编辑内容.command」用 VSCode 改。

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; R="\033[31m"; Y="\033[33m"; N="\033[0m"

echo ""
echo -e "${B}  内容编辑器${N}"
echo "  ========================================"
echo ""

# ---------------------------------------------------------------- ① 找 Python 3
PY=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  PY="$(command -v python3 2>/dev/null)"
fi

if [ -z "$PY" ]; then
  echo -e "  ${R}✗ 没找到 Python 3${N}"
  osascript -e 'display dialog "没找到 Python 3，编辑器跑不起来。

在「终端」里运行这一行就能装好：
xcode-select --install" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

SRV="scripts/编辑内容/服务器.py"
if [ ! -f "$SRV" ]; then
  echo -e "  ${R}✗ 找不到 $SRV${N}"
  echo "     请确认这个 .command 文件和「scripts」文件夹在同一个地方。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ② 起服务
echo -e "  正在启动…（浏览器会自动打开；${Y}这个窗口要一直留着${N}，关掉就等于关掉编辑器）"
echo ""

"$PY" "$SRV"
CODE=$?

echo ""
if [ "$CODE" != "0" ]; then
  echo -e "  ${R}编辑器退出了（代码 $CODE）${N}——看上面最后几行提示。"
  echo ""
fi
read -n 1 -s -r -p "  按任意键关闭这个窗口..."
exit 0
