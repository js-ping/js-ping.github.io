#!/bin/bash
# ============================================================
#  同步书签 —— 双击运行
#
#  挂起来之后，你在 Chrome 里加/删/改书签，网页会自动跟着更新。
#  关掉这个终端窗口（或者按 Ctrl+C）就停止监听，不会留任何后台进程。
#
#  默认「攒着推送」：本地随时更新，但不上线，
#  攒够了你双击「2-更新网站.command」一次性提交并发布。
#  想恢复成改一次上一次，把下面的 AUTO_PUSH 改成 1。
#
#  线上地址：https://uppjs.com/links.html
# ============================================================

cd "$(dirname "$0")" || exit 1

# ----------------- 想改行为，改这两行 -----------------
AUTO_PUSH=0        # 0 = 攒着，等你自己双击「2-更新网站」；1 = 每次改动都自动提交并推送
CHECK_SECONDS=20   # 多久检查一次 Chrome 书签有没有变

# Chrome 常常连着写好几次书签文件，发现变化后等它安静下来再同步
QUIET_SECONDS=12

B="\033[1m"; G="\033[32m"; R="\033[31m"; Y="\033[33m"; D="\033[2m"; N="\033[0m"

printf '\033]0;同步书签 —— uppjs.com\007'

# ---------------------------------------------------------------- 找 Python 3
PY=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
[ -z "$PY" ] && PY="$(command -v python3 2>/dev/null)"

if [ -z "$PY" ] || [ ! -f "同步书签.py" ]; then
  echo ""
  echo -e "  ${R}✗ 环境不完整${N}"
  [ -z "$PY" ] && echo "     没找到 Python 3。在「终端」里运行 xcode-select --install 就能装好。"
  [ ! -f "同步书签.py" ] && echo "     没找到 同步书签.py，请确认本文件放在网站文件夹里。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

CHROME_DIRS=(
  "$HOME/Library/Application Support/Google/Chrome"
  "$HOME/Library/Application Support/Chromium"
)

# 所有 Profile 的 Bookmarks 文件的「修改时间:大小」，拼成一个指纹
fingerprint() {
  local out="" d f
  for d in "${CHROME_DIRS[@]}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*/Bookmarks; do
      [ -f "$f" ] || continue
      out="$out$(stat -f '%m:%z' "$f" 2>/dev/null)|"
    done
  done
  printf '%s' "$out"
}

has_chrome() {
  local d
  for d in "${CHROME_DIRS[@]}"; do
    [ -d "$d" ] && return 0
  done
  return 1
}

if ! has_chrome; then
  echo ""
  echo -e "  ${R}✗ 没找到 Chrome 的书签文件${N}"
  echo "     找过这些位置："
  for d in "${CHROME_DIRS[@]}"; do echo "       $d"; done
  echo ""
  echo "     如果你用的是 Edge / Brave / Arc，改本文件开头的 CHROME_DIRS 就行。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

# ---------------------------------------------------------------- 同步 + 发布
PUSH_PENDING=0
PENDING=0

do_sync() {
  local label="$1" verbose="$2" out status

  echo ""
  echo -e "  ${D}──────── $(date '+%H:%M:%S')  $label ────────${N}"

  out="$("$PY" 同步书签.py 2>&1)"
  status=$?

  if [ $status -ne 0 ]; then
    echo -e "  ${R}✗ 同步失败${N}"
    printf '%s\n' "$out" | tail -8 | sed 's/^/     /'
    return 1
  fi

  if [ "$verbose" = "1" ]; then
    printf '%s\n' "$out" | grep -v '^__SYNC__' | sed 's/^/  /'
  else
    printf '%s\n' "$out" | grep -v '^__SYNC__' | sed -n '3,9p' | sed 's/^/  /'
  fi

  if ! printf '%s' "$out" | grep -q '__SYNC__ changed=1'; then
    echo -e "  ${D}书签没变化，跳过${N}"
    return 0
  fi

  if ! "$PY" build.py > /tmp/uppjs_build.log 2>&1; then
    echo -e "  ${R}✗ 生成网页失败${N}"
    tail -6 /tmp/uppjs_build.log | sed 's/^/     /'
    return 1
  fi
  echo -e "  ${G}✓${N} 本地网页已重新生成"

  # ---------------------------------------------------------- 攒着推送模式
  # 只更新本地文件，不 git add、不 commit、不 push。
  # 攒下的改动交给「2-更新网站.command」一次性提交并发布。
  if [ "$AUTO_PUSH" != "1" ]; then
    PENDING=$((PENDING + 1))
    echo -e "  ${G}✓${N} 改动已攒在本地  ${D}（已攒 ${PENDING} 处，还没上线）${N}"
    echo -e "  ${D}   想上线：双击「2-更新网站.command」，会一次性提交并推送${N}"
    return 0
  fi

  git add -A
  if git diff --cached --quiet; then
    echo -e "  ${D}· 没有需要提交的改动${N}"
    return 0
  fi

  git commit -q -m "同步 Chrome 书签 $(date '+%Y-%m-%d %H:%M')" || {
    echo -e "  ${R}✗ 提交失败${N}"; return 1; }
  echo -e "  ${G}✓${N} 已提交到本地"

  if git push -q origin main 2>/dev/null; then
    PUSH_PENDING=0
    echo -e "  ${G}✓${N} 已推送  ${D}https://uppjs.com/links.html 约 1 分钟后生效${N}"
  else
    PUSH_PENDING=1
    echo -e "  ${Y}·${N} 推送失败（多半是网络不通）"
    echo -e "      改动已安全存在本地，下一轮会自动重试"
  fi
  return 0
}

# ---------------------------------------------------------------- 开场
echo ""
echo -e "${B}  书签自动同步${N}"
echo "  =================================================="
echo "  你在 Chrome 里加/删/改书签，网页会自动跟着更新。"
echo ""
echo -e "  ${D}· 关掉这个窗口就停止监听，不留后台进程${N}"
echo -e "  ${D}· 不想公开的书签，在 Chrome 里丢进「不上网站」文件夹${N}"
if [ "$AUTO_PUSH" = "1" ]; then
  echo -e "  ${D}· 每次同步都会自动提交并推送到线上${N}"
else
  echo -e "  ${D}· 本地网页随时更新，但不会自动上线${N}"
  echo -e "  ${D}  （攒够了双击「2-更新网站」一次性提交并发布）${N}"
fi
echo "  =================================================="

LAST="$(fingerprint)"
do_sync "启动，先同步一次" 1

echo ""
echo -e "  ${G}✓ 已挂起，正在监听${N}"
echo -e "  ${D}  每 ${CHECK_SECONDS} 秒检查一次。现在可以直接去 Chrome 收藏东西了。${N}"
if [ "$PENDING" -gt 0 ] 2>/dev/null; then
  echo -e "  ${Y}·${N} 本地有改动还没上线，双击「2-更新网站.command」即可发布"
fi
echo -e "  ${D}  想停下来：关掉这个窗口，或按 Ctrl+C。${N}"
echo ""

# ---------------------------------------------------------------- 循环
while true; do
  sleep "$CHECK_SECONDS"

  # 上次推送失败的话，先补一次推送
  if [ "$PUSH_PENDING" = "1" ]; then
    if git push -q origin main 2>/dev/null; then
      PUSH_PENDING=0
      echo -e "  ${D}$(date '+%H:%M:%S')${N}  ${G}✓${N} 补推送成功"
    fi
  fi

  NOW="$(fingerprint)"
  if [ "$NOW" = "$LAST" ]; then
    continue
  fi

  # 等 Chrome 写完，别同步到写了一半的文件
  sleep "$QUIET_SECONDS"
  LAST="$(fingerprint)"
  do_sync "检测到书签变化" 0
done
