#!/bin/bash
# 编辑内容 —— 双击运行
# 用 VSCode 打开整个项目文件夹，左侧文件列表里点一下就能切换内容源

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

HINT="
可改的文件（左侧列表里点一下就能切换）：
  README.md      软件清单      ← 最常改
  links.md       网址书签
  使用说明.md     本说明书

改完之后：Cmd + S 保存，然后双击「2-更新网站.command」上线。"

# 优先打开「整个文件夹」——现在有三个内容源，文件列表里切换比单独开一个文件方便
for APP in "Visual Studio Code" "Cursor" "VSCodium" "Sublime Text" "BBEdit" "TextMate" "Typora" "MacDown"; do
  if [ -d "/Applications/$APP.app" ] || [ -d "$HOME/Applications/$APP.app" ]; then
    open -a "$APP" "$PWD"
    echo "✓ 已用「$APP」打开项目文件夹"
    echo "$HINT"
    echo ""
    read -n 1 -s -r -p "按任意键关闭这个窗口..."
    exit 0
  fi
done

# 都没装，用系统自带的「文本编辑」单独打开主文件
open -e "$FILE"
echo "✓ 已用系统「文本编辑」打开 README.md"
echo ""
echo "提示：装一个 VSCode 会顺手很多（免费），而且能一次看到全部文件。"
echo ""
read -n 1 -s -r -p "按任意键关闭这个窗口..."
exit 0
