#!/bin/bash
# 体检链接 —— 双击运行
# 用你本机的真实网络，逐条测「软件与资源」页里的每个链接能不能打开，
# 把结果写进 free-region.json，然后自动生成网页并上线。
# 线上地址：https://uppjs.com/apps.html

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; Y="\033[33m"; R="\033[31m"; N="\033[0m"

echo ""
echo -e "${B}  体检链接${N}"
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
  osascript -e 'display dialog "没找到 Python 3，无法体检。

在「终端」里运行这一行就能装好：
xcode-select --install" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ② 跑体检
if ! "$PY" 体检链接.py; then
  echo ""
  echo -e "  ${R}✗ 体检没跑完${N}"
  osascript -e 'display dialog "体检没跑完，请看终端窗口里的红字提示。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

echo ""
echo -e "  ${B}体检完成${N}：free-region.json 已更新"
echo ""

# ---------------------------------------------------------------- ③ 问要不要上线
ANSWER=$(osascript -e 'button returned of (display dialog "体检完成 ✓

要现在把新标记生成网页并上线吗？

（这一步会提交并推送到 GitHub，大约 1 分钟后生效）" buttons {"先不上线", "生成并上线"} default button "生成并上线" with icon note)' 2>/dev/null)

if [ "$ANSWER" != "生成并上线" ]; then
  echo -e "  ${Y}已跳过上线${N}：标记已经存在本地，"
  echo "  想上线时双击「2-更新网站.command」即可。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 0
fi

# ---------------------------------------------------------------- ④ 生成网页
echo "  ① 生成网页中..."
if ! "$PY" build.py; then
  echo ""
  echo -e "  ${R}✗ 生成失败${N}"
  osascript -e 'display dialog "生成网页失败，请看终端窗口里的提示。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- ⑤ 提交
git add -A
PUSHED=0

if git diff --cached --quiet; then
  echo "  ② 内容没有变化，跳过提交"
else
  MSG="链接体检：刷新国内访问标记 $(date '+%Y-%m-%d %H:%M')"
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

# ---------------------------------------------------------------- ⑥ 推送
if [ "$PUSHED" = "1" ]; then
  echo "  ③ 推送到 GitHub..."
  if git push -q origin main; then
    echo -e "  ${G}     推送成功${N}"
  else
    echo ""
    echo -e "  ${R}✗ 推送失败${N}——多半是网络不通。"
    echo "     体检结果已安全存在本地，网络恢复后双击「2-更新网站.command」即可，不会丢。"
    osascript -e 'display dialog "推送失败：多半是网络不通。

体检结果已安全保存在本地，网络恢复后双击「2-更新网站」就行，不会丢东西。" buttons {"好"} default button 1 with icon caution' >/dev/null 2>&1
    echo ""
    read -n 1 -s -r -p "  按任意键关闭..."
    exit 1
  fi
else
  echo "  ③ 没有新内容，无需推送"
fi

echo ""
echo "  ========================================"
echo -e "  ${G}✓ 完成${N}"
echo "     线上  https://uppjs.com/apps.html"
echo "     大约 1 分钟后生效"
echo ""
osascript -e 'display dialog "已上线 ✓

https://uppjs.com/apps.html
大约 1 分钟后生效。" buttons {"好"} default button 1 with icon note' >/dev/null 2>&1
read -n 1 -s -r -p "  按任意键关闭这个窗口..."
exit 0
