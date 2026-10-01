#!/bin/bash
# 更新网站 —— 双击运行
# 把 README.md 编译成 index.html，提交并推送到 GitHub
# 线上地址：https://uppjs.com

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; R="\033[31m"; N="\033[0m"

echo ""
echo -e "${B}  更新网站${N}"
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
  osascript -e 'display dialog "没找到 Python 3，无法生成网页。

在「终端」里运行这一行就能装好：
xcode-select --install" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ② 生成网页
echo "  ① 生成网页中（首页 + 软件清单 + 网址书签 + 使用说明）..."
if ! "$PY" build.py; then
  echo ""
  echo -e "  ${R}✗ 生成失败${N}——多半是 README.md 里某一行格式写错了"
  osascript -e 'display dialog "生成网页失败。

请看终端窗口里的红色提示，改好对应的 .md 再试一次。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ③ 提交
git add -A
PUSHED=0

if git diff --cached --quiet; then
  echo "  ② 内容没有变化，跳过提交"
else
  MSG="更新网站内容 $(date '+%Y-%m-%d %H:%M')"
  if git commit -q -m "$MSG"; then
    echo "  ② 已提交：$MSG"
    PUSHED=1
  else
    echo -e "  ${R}✗ 提交失败${N}"
    osascript -e 'display dialog "提交失败，请看终端窗口里的提示。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
    echo ""
    read -n 1 -s -r -p "  按任意键关闭..."
    exit 1
  fi
fi

# ---------------------------------------------------------------- ④ 推送
if [ "$PUSHED" = "1" ]; then
  echo "  ③ 推送到 GitHub..."
  if git push -q origin main; then
    echo -e "  ${G}     推送成功${N}"
  else
    echo ""
    echo -e "  ${R}✗ 推送失败${N}"
    echo "     最常见的原因是网络不通。"
    echo "     你的改动已经安全存在本地，网络恢复后重新双击本文件即可，不会丢。"
    osascript -e 'display dialog "推送失败：多半是网络不通。

改动的文件已安全保存在本地，网络恢复后重新双击「2-更新网站」就行，不会丢东西。" buttons {"好"} default button 1 with icon caution' >/dev/null 2>&1
    echo ""
    read -n 1 -s -r -p "  按任意键关闭..."
    exit 1
  fi
else
  echo "  ③ 没有新内容，无需推送"
fi

# ---------------------------------------------------------------- ⑤ 打开本地预览
open index.html

echo ""
echo "  ========================================"
echo -e "  ${G}✓ 完成${N}"
echo "     线上  https://uppjs.com"
echo "     大约 1 分钟后生效"
echo ""
osascript -e 'display dialog "网站已更新 ✓

线上地址：https://uppjs.com
大约 1 分钟后生效。" buttons {"好"} default button 1 with icon note' >/dev/null 2>&1
read -n 1 -s -r -p "  按任意键关闭这个窗口..."
exit 0
