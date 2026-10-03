#!/bin/bash
# ============================================================
#  整理「不上网站」—— 双击运行
#
#  把所有被安全兜底规则挡住的书签，按原因分好类，
#  搬进 Chrome 书签栏里的「不上网站」文件夹。
#
#  为什么要有这一步：
#    「同步书签.py」会自动挡下个人后台 / 政务内网 / 破解激活 /
#    成人内容 / 机场代理 / 彩票 / 购物网盘这七类书签，不让它们上网页。
#    但它们在你的 Chrome 里还是散在各处，看不出哪些没上网。
#    搬进「不上网站」之后，一眼就能看清全部，想放行哪条拖出去就行。
#
#  ⚠ 这个操作会先退出 Chrome（Chrome 只在启动时读一次书签文件），
#    改完会再帮你打开，标签页会恢复。退出前会跟你确认一次。
# ============================================================

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; R="\033[31m"; Y="\033[33m"; D="\033[2m"; N="\033[0m"

printf '\033]0;整理不上网站 —— uppjs.com\007'

# ---------------------------------------------------------------- 找 Python 3
PY=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
[ -z "$PY" ] && PY="$(command -v python3 2>/dev/null)"

if [ -z "$PY" ] || [ ! -f "迁移书签.py" ]; then
  echo ""
  echo -e "  ${R}✗ 环境不完整${N}"
  [ -z "$PY" ] && echo "     没找到 Python 3。在「终端」里运行 xcode-select --install 就能装好。"
  [ ! -f "迁移书签.py" ] && echo "     没找到 迁移书签.py，请确认本文件放在网站文件夹里。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

echo ""
echo -e "${B}  整理「不上网站」${N}"
echo "  =================================================="
echo "  把被自动规则挡下的书签，按原因分类搬进「不上网站」。"
echo -e "  ${D}· 会先退出 Chrome，改完自动重开（标签页恢复）${N}"
echo -e "  ${D}· 改之前会自动备份书签文件${N}"
echo -e "  ${D}· 网页内容不会变——这些书签本来就没被发布${N}"
echo "  =================================================="
echo ""

"$PY" 迁移书签.py
STATUS=$?

if [ $STATUS -ne 0 ]; then
  echo -e "  ${R}✗ 没成功，什么都没改坏，可以放心重试${N}"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit $STATUS
fi

# ---------------------------------------------------------------- 顺手确认网页没变
echo -e "  ${D}检查网页内容有没有连带变化……${N}"
OUT="$("$PY" 同步书签.py 2>&1)"
if ! printf '%s' "$OUT" | grep -q '__SYNC__ changed=1'; then
  echo -e "  ${G}✓${N} 网页内容一个字没变，不用重新发布"
  echo ""
  exit 0
fi

echo -e "  ${Y}·${N} 网页内容跟着变了，正在重新生成并发布……"
if ! "$PY" build.py > /tmp/uppjs_build.log 2>&1; then
  echo -e "  ${R}✗ 生成网页失败${N}"
  tail -6 /tmp/uppjs_build.log | sed 's/^/     /'
  echo "     可以手动双击「2-更新网站.command」重试。"
  echo ""
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "整理不上网站 $(date '+%Y-%m-%d %H:%M')" || {
    echo -e "  ${R}✗ 提交失败${N}"; read -n 1 -s -r -p "  按任意键关闭..."; exit 1; }
  if git push -q origin main 2>/dev/null; then
    echo -e "  ${G}✓${N} 已发布  ${D}https://uppjs.com/links.html 约 1 分钟后生效${N}"
  else
    echo -e "  ${Y}·${N} 推送失败（多半是网络不通），改动已在本地，下次同步会自动重试"
  fi
fi
echo ""
exit 0
