#!/bin/bash
# 编辑内容 —— 双击运行
# 用 VSCode 打开 README.md（网站的唯一内容源）

cd "$(dirname "$0")" || exit 1

FILE="README.md"

if [ ! -f "$FILE" ]; then
  echo "✗ 找不到 README.md"
  echo "  请确认这个 .command 文件和 README.md 在同一个文件夹里。"
  osascript -e 'display dialog "找不到 README.md。

请确认本文件与 README.md 在同一个文件夹内。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "按任意键关闭..."
  exit 1
fi

# 按优先级挑一个已安装的编辑器（VSCode 优先）
for APP in "Visual Studio Code" "Cursor" "Typora" "Sublime Text" "MacDown" "BBEdit" "TextMate"; do
  if [ -d "/Applications/$APP.app" ] || [ -d "$HOME/Applications/$APP.app" ]; then
    open -a "$APP" "$FILE"
    echo "✓ 已用「$APP」打开 README.md"
    echo ""
    echo "改完之后：保存（Cmd+S），然后双击「2-更新网站.command」上线。"
    exit 0
  fi
done

# 都没装，用系统自带的「文本编辑」
open -e "$FILE"
echo "✓ 已用系统「文本编辑」打开 README.md"
echo ""
echo "提示：装一个 VSCode 会顺手很多（免费）。"
exit 0
