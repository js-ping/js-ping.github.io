#!/bin/bash
# 编辑器自检 —— 双击运行
# 跑一遍回归测试，确认编辑器改文件不会改坏东西。改完编辑器代码后跑一跑。

cd "$(dirname "$0")" || exit 1

B="\033[1m"; G="\033[32m"; R="\033[31m"; N="\033[0m"

echo ""
echo -e "${B}  编辑器自检${N}"
echo "  ========================================"

PY=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$p" ]; then PY="$p"; break; fi
done
[ -z "$PY" ] && PY="$(command -v python3 2>/dev/null)"

if [ -z "$PY" ]; then
  echo -e "  ${R}✗ 没找到 Python 3${N}"
  read -n 1 -s -r -p "  按任意键关闭..."
  exit 1
fi

"$PY" "自检.py"
CODE=$?

echo ""
if [ "$CODE" = "0" ]; then
  echo -e "  ${G}✓ 通过${N}——编辑器可以放心用"
else
  echo -e "  ${R}✗ 没通过${N}——先别用编辑器改内容，把上面的 ✗ 修好再说"
fi
echo ""
read -n 1 -s -r -p "  按任意键关闭这个窗口..."
exit 0
