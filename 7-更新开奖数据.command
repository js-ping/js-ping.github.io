#!/bin/bash
# 更新开奖数据 —— 双击运行
# 把 lottery.html 里内嵌的开奖历史快照，追平到最新一期。
# 线上地址：https://uppjs.com/lottery.html
#
# 什么时候需要双击它：
#   平时不用管 —— GitHub 每天会自动跑一次（见 .github/workflows/update-lottery-data.yml）。
#   这个文件是「万一自动化没跑成」时的手动兜底，也能用来立刻补一次。

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; Y="\033[33m"; R="\033[31m"; N="\033[0m"

echo ""
echo -e "${B}  更新开奖数据${N}"
echo "  ========================================"
echo "  把 lottery.html 内嵌的历史快照追平到最新一期"
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
  osascript -e 'display dialog "没找到 Python 3，无法更新。

在「终端」里运行这一行就能装好：
xcode-select --install" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ② 拉数据、补进文件
if ! "$PY" scripts/更新开奖数据.py --apply; then
  echo ""
  echo -e "  ${R}✗ 没跑成${N}——请看上面的红字提示"
  osascript -e 'display dialog "更新没跑成，请看终端窗口里的提示。

常见原因：这台电脑连不上 uppjs.com（断网 / 代理）。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

echo ""

# ---------------------------------------------------------------- ③ 有没有变化
if git diff --quiet -- lottery.html; then
  echo "  ========================================"
  echo -e "  ${G}✓ 已经是最新${N}，没有需要改的地方"
  echo ""
  osascript -e 'display dialog "彩票页已经是开奖最新一期，不用更新 ✓" buttons {"好"} default button 1 with icon note' >/dev/null 2>&1
  read -n 1 -s -r -p "  按任意键关闭这个窗口..."
  exit 0
fi

echo "  本地文件已更新。变化如下："
echo ""
git --no-pager diff --stat -- lottery.html | sed 's/^/    /'
echo ""

# ---------------------------------------------------------------- ④ 问要不要上线
ANSWER=$(osascript -e 'button returned of (display dialog "开奖数据已补进 lottery.html ✓

要现在提交并上线吗？

（会推送到 GitHub，大约 1 分钟后线上生效）" buttons {"先不上线", "提交并上线"} default button "提交并上线" with icon note)' 2>/dev/null)

if [ "$ANSWER" != "提交并上线" ]; then
  echo -e "  ${Y}已跳过上线${N}：改动已经存在本地的 lottery.html 里，"
  echo "  想上线时双击「2-更新网站.command」即可。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 0
fi

# ---------------------------------------------------------------- ⑤ 提交
git add lottery.html
MSG="开奖数据更新 $(date '+%Y-%m-%d')"
if git commit -q -m "$MSG"; then
  echo "  ① 已提交：$MSG"
else
  echo -e "  ${R}✗ 提交失败${N}"
  osascript -e 'display dialog "提交失败，请看终端窗口里的提示。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ⑥ 推送
echo "  ② 推送到 GitHub..."
if git push -q origin main; then
  echo -e "  ${G}     推送成功${N}"
else
  echo ""
  echo -e "  ${R}✗ 推送失败${N}——多半是网络不通。"
  echo "     改动已安全提交在本地，网络恢复后重新双击本文件即可，不会丢。"
  osascript -e 'display dialog "推送失败：多半是网络不通。

改动已安全保存在本地，网络恢复后重新双击「7-更新开奖数据」就行，不会丢东西。" buttons {"好"} default button 1 with icon caution' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

echo ""
echo "  ========================================"
echo -e "  ${G}✓ 完成${N}"
echo "     线上  https://uppjs.com/lottery.html"
echo "     大约 1 分钟后生效"
echo ""
osascript -e 'display dialog "开奖数据已上线 ✓

https://uppjs.com/lottery.html
大约 1 分钟后生效。" buttons {"好"} default button 1 with icon note' >/dev/null 2>&1
read -n 1 -s -r -p "  按任意键关闭这个窗口..."
exit 0
