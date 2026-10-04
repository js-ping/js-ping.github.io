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
  README.md               软件清单        ← 最常改，改完会上线
  articles.md             文章归档        ← 填了内容才上线，首页会显示成「规划中」
  books.md                书单            ← 同上
  movies.md               影单            ← 同上
  about.md                关于            ← 上线
  privacy.md              隐私说明        ← 上线
  本地资料/使用说明.md     使用说明        ← 只在本机看，不上线

每个文件开头都有一段说明，写着怎么加条目。照抄一行就行。

注意 1：本地资料/ 里的东西不会上线，也不会提交到 GitHub。
注意 2：links.md（网址书签）是自动生成的，手改会被下次同步覆盖。
        网址书签页目前是下线的，想恢复告诉我一声就行。
注意 3：.html 文件全部是自动生成的，手改会被覆盖。

改完之后：Cmd + S 保存，然后双击「2-更新网站.command」上线。"

# 优先打开「整个文件夹」——文件列表里切换比单独开一个文件方便
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
