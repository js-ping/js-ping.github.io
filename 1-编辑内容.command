#!/bin/bash
# 编辑内容 —— 双击运行
# 用 VSCode 打开整个项目文件夹，左侧文件列表里点一下就能切换内容源

cd "$(dirname "$0")" || exit 1

FILE="内容源/软件与资源.md"

if [ ! -f "$FILE" ]; then
  echo "✗ 找不到 内容源/软件与资源.md"
  echo "  请确认这个 .command 文件和「内容源」文件夹在同一个地方。"
  osascript -e 'display dialog "找不到 内容源/软件与资源.md。

请确认本文件与「内容源」文件夹在同一个地方。" buttons {"好"} default button 1 with icon stop' >/dev/null 2>&1
  echo ""
  read -n 1 -s -r -p "按任意键关闭..."
  exit 1
fi

HINT="
提示：日常改内容更推荐双击「8-内容编辑器.command」——浏览器里填表改，能拖拽排序、
      能预览、能一键上线，不用碰 markdown。这个窗口适合批量改结构、改分组。

可改的文件（全部在「内容源」文件夹里，左侧列表点一下就切换）：

  内容源/软件与资源.md     ★ 最常改的那一份：软件、硬件外设 + 合法免费资源
  内容源/文章归档.md       文章归档        ← 填了内容才上线，首页会显示成「规划中」
  内容源/书单.md           书单            ← 同上
  内容源/影单.md           影单            ← 同上
  内容源/关于.md           关于            ← 上线
  内容源/隐私说明.md       隐私说明        ← 上线
  本地资料/使用说明.md     使用说明        ← 只在本机看，不上线

每个文件开头都有一段说明，写着怎么加条目。照抄一行就行。

注意 1：本地资料/ 里的东西不会上线，也不会提交到 GitHub。
注意 2：内容源/网址书签.md 是自动生成的，手改会被下次同步覆盖。
        网址书签页目前是下线的，想恢复告诉我一声就行。
注意 3：.html 文件全部是自动生成的，手改会被覆盖。
注意 4：free-region.json 是「6-体检链接」跑出来的，手改会被下次体检覆盖。
        软件与资源.md 里不用写「慢 / 需代理」，那是自动测出来贴上去的。
注意 5：根目录的 README.md 是给 GitHub 仓库首页看的，不参与编译，改它不会影响网站。
注意 6：「归档/」里是已经退役的旧内容源和合并工具，再改也不会影响网站，别改。

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
echo "✓ 已用系统「文本编辑」打开 内容源/软件与资源.md"
echo ""
echo "提示：装一个 VSCode 会顺手很多（免费），而且能一次看到全部文件。"
echo ""
read -n 1 -s -r -p "按任意键关闭这个窗口..."
exit 0
