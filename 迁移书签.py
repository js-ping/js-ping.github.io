#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迁移书签.py —— 把被「安全兜底规则」挡住的书签，统一搬进「不上网站」文件夹

背景
────────────────────────────────────────────────────────────
「同步书签.py」有两道闸，决定哪些书签不上公开网页：

  ① 「不上网站」文件夹   —— 你手动控制，拖进去就行
  ② AUTO_BLOCK 安全兜底  —— 脚本自动挡（个人后台 / 政务内网 / 破解激活 /
                            成人内容 / 机场代理 / 彩票 / 购物网盘）

第 ② 类虽然不会上网，但在 Chrome 里还是散落在各个文件夹里，
看不出「到底哪些没上网站」，事后想核对或者想放行某一条都很麻烦。

这个脚本干一件事：
    把所有命中安全兜底规则的书签，按命中原因分好类，
    搬到「不上网站」文件夹下面（子文件夹就是原因）。
    搬完之后，Chrome 里一眼看清全部不上网的条目；
    想让哪条重新上网，直接从文件夹里拖出去就行。

⚠ 脚本只动 Chrome 的书签文件，不动网页内容。
   这些书签本来就没被发布，所以搬完 links.md 一个字都不会变。

⚠ Chrome 只在启动时读一次书签文件。
   所以要改这个文件，必须先退出 Chrome，改完再打开——
   脚本会自动帮你做这件事（退出前会问你，标签页会恢复）。

用法
────────────────────────────────────────────────────────────
    python3 迁移书签.py --dry-run        只列清单，绝不改文件
    python3 迁移书签.py                  真搬（先退 Chrome，搬完自动重开）
    python3 迁移书签.py --no-relaunch    搬完不重开 Chrome
    python3 迁移书签.py --yes            不提问，直接干（配合 .command 用）
    python3 迁移书签.py --profile Default   只处理指定 Profile
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = Path.home() / "Library/Application Support/Google/Chrome/_uppjs备份"

# ------------------------------------------------------------------ 输出配色
C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m",
     "d": "\033[2m", "b": "\033[1m", "n": "\033[0m"}
if not sys.stdout.isatty():
    C = {k: "" for k in C}


def say(s=""):
    print(s)


# ------------------------------------------------------------------ 复用主脚本的规则
def load_sync_module():
    """把 同步书签.py 当模块加载，共用同一套规则，绝不抄第二份。"""
    p = ROOT / "同步书签.py"
    if not p.is_file():
        say("  %s✗ 找不到 同步书签.py，请确认本文件放在网站文件夹里%s" % (C["r"], C["n"]))
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("uppjs_sync_rules", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SYNC = load_sync_module()
CHROME_ROOTS = SYNC.CHROME_ROOTS
EXCLUDE_FOLDERS = SYNC.EXCLUDE_FOLDERS
AUTO_BLOCK_RULES = SYNC.AUTO_BLOCK_RULES
auto_block_reason = SYNC.auto_block_reason

REASON_ORDER = [r for r, _ in AUTO_BLOCK_RULES]
EXCL_LOWER = tuple(x.strip().lower() for x in EXCLUDE_FOLDERS)


# ==========================================================================
# 一、Chrome 书签文件的读写
# ==========================================================================

CHROME_EPOCH_OFFSET = 11644473600  # 1601-01-01 → 1970-01-01 之间的秒数


def chrome_time():
    """Chrome 内部时间：1601 年起的微秒数，字符串。"""
    return str(int((time.time() + CHROME_EPOCH_OFFSET) * 1_000_000))


def read_json(path):
    for i in range(6):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            if i == 5:
                raise
            time.sleep(0.4)


def checksum(doc):
    """复刻 Chromium 的 Bookmarks checksum（MD5）。

    规则（见 components/bookmarks/browser/bookmark_codec.cc）：
        前序遍历 bookmark_bar → other → synced；
        每个节点依次喂入  id(UTF-8) + name(UTF-16LE) + type(UTF-8)，
        url 节点再喂 url(UTF-8)，文件夹节点接着递归子节点。
        —— 没有分隔符、没有长度、没有 JSON。
    只喂 id（不管名字/网址）算出来的值会对不上，别偷懒。
    """
    import hashlib
    m = hashlib.md5()

    def u8(s):
        m.update(s.encode("utf-8"))

    def u16(s):
        m.update(s.encode("utf-16-le", "surrogatepass"))

    def node(n):
        u8(n["id"])
        u16(n.get("name", ""))
        u8(n["type"])
        if n.get("type") == "url":
            u8(n.get("url", ""))
        else:
            for c in n.get("children") or []:
                node(c)

    for key in ("bookmark_bar", "other", "synced"):
        r = (doc.get("roots") or {}).get(key)
        if isinstance(r, dict):
            node(r)
    return m.hexdigest()


def write_json(path, doc):
    """原子替换 + 保持 0600 权限，模仿 Chrome 自己的写法。"""
    doc["checksum"] = checksum(doc)
    tmp = path.parent / (path.name + ".uppjs-tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=3)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def find_profiles(only=None):
    out = []
    for root in CHROME_ROOTS:
        if not root.is_dir():
            continue
        for prof in sorted(root.iterdir()):
            if not prof.is_dir() or prof.name in ("System Profile", "Guest Profile",
                                                  "Crashpad", "ShaderCache"):
                continue
            if only and prof.name != only:
                continue
            bk = prof / "Bookmarks"
            if bk.is_file():
                out.append((prof.name, bk))
    return out


# ==========================================================================
# 二、规划搬运
# ==========================================================================

def find_target(roots):
    """找「不上网站」文件夹。先看书签栏顶层，再看别处。返回 (node, 描述)。"""
    def top_level(container, label):
        for ch in container.get("children") or []:
            if (ch.get("type") == "folder"
                    and (ch.get("name") or "").strip().lower() in EXCL_LOWER):
                return ch, label

    for key, label in (("bookmark_bar", "书签栏"), ("other", "其他书签"),
                       ("synced", "移动设备书签")):
        c = roots.get(key)
        if isinstance(c, dict):
            hit = top_level(c, "%s 顶层" % label)
            if hit:
                return hit

    deep = []

    def walk(n, path):
        for ch in n.get("children") or []:
            if ch.get("type") != "folder":
                continue
            name = (ch.get("name") or "").strip()
            if name.lower() in EXCL_LOWER:
                deep.append((ch, "/".join(path + [name])))
            walk(ch, path + [name])

    for key, label in (("bookmark_bar", "书签栏"), ("other", "其他书签"),
                       ("synced", "移动设备书签")):
        c = roots.get(key)
        if isinstance(c, dict):
            walk(c, [label])
    if deep:
        return deep[0]
    return None, None


def plan_moves(roots, target):
    """返回 [(父节点, 节点, 命中原因)]，跳过已经在「不上网站」里的。"""
    moves = []

    def walk(node, excluded):
        for ch in node.get("children") or []:
            if ch.get("type") == "folder":
                if ch is target:
                    continue
                name = (ch.get("name") or "").strip()
                walk(ch, excluded or name.lower() in EXCL_LOWER)
            else:
                if excluded:
                    continue
                reason = auto_block_reason(ch.get("name") or "", ch.get("url") or "")
                if reason:
                    moves.append((node, ch, reason))

    for key in ("bookmark_bar", "other", "synced"):
        r = roots.get(key)
        if isinstance(r, dict):
            walk(r, False)
    return moves


def make_folder(name, next_id):
    return OrderedDict([
        ("children", []),
        ("date_added", chrome_time()),
        ("date_modified", chrome_time()),
        ("guid", str(uuid.uuid4())),
        ("id", str(next_id)),
        ("name", name),
        ("type", "folder"),
    ])


def collect_ids(node, sink):
    sink.append(node)
    for ch in node.get("children") or []:
        collect_ids(ch, sink)


def apply_moves(doc, target, moves):
    """真正动手：摘下来、分好类、挂到目标文件夹下面。"""
    roots = doc["roots"]

    # 1) 找到全局最大 id，新建子文件夹时接着往下排
    counter = [max([int(x) for x in _all_ids(roots) if x.isdigit()] or [0])]

    # 2) 从原位置摘下来（同一父节点内按下标倒序删，避免错位）
    by_parent = OrderedDict()
    for parent, node, reason in moves:
        by_parent.setdefault(id(parent), []).append((parent, node, reason))
    for _, lst in by_parent.items():
        parent = lst[0][0]
        kids = parent["children"]
        pos = {id(k): i for i, k in enumerate(kids)}
        for i in sorted((pos[id(n)] for _, n, _ in lst), reverse=True):
            del kids[i]

    # 3) 目标文件夹里，按原因建子文件夹
    subs = {}
    for ch in target.get("children") or []:
        if ch.get("type") == "folder":
            subs[(ch.get("name") or "").strip()] = ch

    def sub_for(reason):
        if reason in subs:
            return subs[reason]
        counter[0] += 1
        f = make_folder(reason, counter[0])
        target.setdefault("children", []).append(f)
        subs[reason] = f
        return f

    # 按规则表顺序建，Chrome 里看着整齐
    for reason in REASON_ORDER:
        if any(r == reason for _, _, r in moves):
            sub_for(reason)

    # 4) 挂上去
    for _, node, reason in moves:
        sub_for(reason).setdefault("children", []).append(node)

    return counter[0]


# ==========================================================================
# 三、Chrome 开关
# ==========================================================================

def chrome_running():
    return subprocess.run(["pgrep", "-x", "Google Chrome"],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def quit_chrome():
    say("  %s正在退出 Chrome ……%s" % (C["d"], C["n"]))
    subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if not chrome_running():
            return True
        time.sleep(0.5)
    return False


def start_chrome():
    subprocess.run(["open", "-a", "Google Chrome"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def backup(path, tag):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dst = BACKUP_DIR / ("%s-%s.json" % (path.parent.name, tag))
    shutil.copy2(path, dst)
    # 顺带留一份最新的，方便一眼找到
    latest = BACKUP_DIR / ("%s-最新.json" % path.parent.name)
    shutil.copy2(path, latest)
    return dst


# ==========================================================================
# 四、主流程
# ==========================================================================

def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--dry-run", action="store_true", help="只列清单，不改文件")
    ap.add_argument("--yes", action="store_true", help="不提问，直接干")
    ap.add_argument("--no-relaunch", action="store_true", help="搬完不重开 Chrome")
    ap.add_argument("--profile", default=None, help="只处理指定 Profile，如 Default")
    args = ap.parse_args()

    say("")
    say("  %s把「不上网站」的书签收拢到文件夹里%s" % (C["b"], C["n"]))
    say("  " + "─" * 46)

    profiles = find_profiles(args.profile)
    if not profiles:
        say("  %s✗ 没找到 Chrome 书签文件%s" % (C["r"], C["n"]))
        say("     找过：%s" % "、".join(str(r) for r in CHROME_ROOTS))
        return 1

    plans = []
    for name, path in profiles:
        doc = read_json(path)
        roots = doc.get("roots") or {}
        target, where = find_target(roots)
        moves = plan_moves(roots, target)
        plans.append({"name": name, "path": path, "doc": doc,
                      "target": target, "where": where, "moves": moves})

    # ---------------------------------------------------------- 报告
    total = 0
    for p in plans:
        mv = p["moves"]
        total += len(mv)
        say("")
        say("  %sProfile %s%s  %s%s%s" % (C["b"], p["name"], C["n"],
                                          C["d"], p["path"], C["n"]))
        if p["target"] is None:
            say("    %s目标文件夹：还没有「不上网站」%s" % (C["y"], C["n"]))
            say("       %s要在书签栏里先建一个叫「不上网站」的文件夹吗？"
                "脚本会自动建在书签栏第一位。%s" % (C["d"], C["n"]))
        else:
            say("    目标文件夹：%s「不上网站」（%s）%s"
                % (C["g"], p["where"], C["n"]))
        say("    待收拢：%s%d 条%s" % (C["b"], len(mv), C["n"]))

        if not mv:
            say("    %s✓ 已经全部归置好了，没东西要搬%s" % (C["g"], C["n"]))
            continue

        groups = OrderedDict()
        for _, node, reason in mv:
            groups.setdefault(reason, []).append(node)
        for reason in REASON_ORDER:
            if reason not in groups:
                continue
            items = groups.pop(reason)
            say("")
            say("      %s%s  ·  %d 条%s" % (C["y"], reason, len(items), C["n"]))
            for n in items[:6]:
                title = (n.get("name") or "").strip() or "(无标题)"
                if len(title) > 30:
                    title = title[:30] + "…"
                say("        %s· %s%s" % (C["d"], title, C["n"]))
            if len(items) > 6:
                say("        %s· …… 另外 %d 条%s" % (C["d"], len(items) - 6, C["n"]))

    say("")
    say("  " + "─" * 46)
    say("  合计要搬运 %s%d 条%s" % (C["b"], total, C["n"]))

    if args.dry_run:
        say("  %s（试运行，Chrome 和书签文件都没动）%s" % (C["y"], C["n"]))
        say("")
        return 0

    if total == 0:
        say("  %s✓ 没有需要搬运的，收工%s" % (C["g"], C["n"]))
        say("")
        return 0

    # ---------------------------------------------------------- 动 Chrome
    was_running = chrome_running()
    if was_running:
        say("")
        say("  %s⚠ 要改 Chrome 的书签文件，必须先退出 Chrome%s"
            % (C["y"], C["n"]))
        say("  %s  Chrome 只在启动时读一次这个文件；" % C["d"])
        say("  边开边改，改动会被它覆盖掉。%s" % C["n"])
        say("  %s  退出是正常的「退出」，标签页下次打开会恢复。%s" % (C["d"], C["n"]))
        if not args.yes:
            try:
                ans = input("\n  现在退出 Chrome 并继续？[回车继续 / n 取消] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans in ("n", "no"):
                say("  已取消，什么都没改。")
                return 0
        if not quit_chrome():
            say("  %s✗ Chrome 没能在 30 秒内退出，已中止，书签文件没动。%s"
                % (C["r"], C["n"]))
            say("     多半是有弹窗挡着。手动退出 Chrome 后重跑一次即可。")
            return 1
        say("  %s✓ Chrome 已退出%s" % (C["g"], C["n"]))
    else:
        say("  %s· Chrome 没在运行，直接改文件%s" % (C["d"], C["n"]))

    # ---------------------------------------------------------- 备份 + 写
    say("")
    tag = time.strftime("%Y%m%d-%H%M%S")
    ok = 0
    try:
        for p in plans:
            if not p["moves"]:
                continue
            dst = backup(p["path"], tag)
            say("  %s✓ 已备份%s %s" % (C["g"], C["n"], dst))

            doc = p["doc"]
            roots = doc["roots"]
            target = p["target"]
            if target is None:
                bar = roots.get("bookmark_bar")
                if not isinstance(bar, dict):
                    say("  %s✗ 找不到书签栏，跳过%s" % (C["r"], C["n"]))
                    continue
                target = make_folder("不上网站", 0)
                target["id"] = str(max(
                    [int(n) for n in _all_ids(roots) if n.isdigit()] or [0]) + 1)
                bar.setdefault("children", []).insert(0, target)
                say("  %s✓ 已在书签栏顶部新建「不上网站」%s" % (C["g"], C["n"]))
            apply_moves(doc, target, p["moves"])
            write_json(p["path"], doc)

            chk = read_json(p["path"])
            if checksum(chk) != chk.get("checksum"):
                raise RuntimeError("写回后校验和不自洽")
            ok += len(p["moves"])
            say("  %s✓ 已搬入 %d 条，校验和已重算%s" % (C["g"], len(p["moves"]), C["n"]))
    except Exception as e:
        say("  %s✗ 出错了：%s%s" % (C["r"], e, C["n"]))
        say("  %s  备份在 %s，需要的话手动拷回去覆盖 Bookmarks 即可。%s"
            % (C["d"], BACKUP_DIR, C["n"]))
        if was_running:
            start_chrome()
            say("  %s· 已重新打开 Chrome%s" % (C["d"], C["n"]))
        return 1

    say("")
    say("  %s✓ 完成，共搬运 %d 条%s" % (C["g"], ok, C["n"]))
    say("  %s  备份目录：%s%s" % (C["d"], BACKUP_DIR, C["n"]))

    if was_running and not args.no_relaunch:
        start_chrome()
        say("  %s✓ 已重新打开 Chrome（标签页会恢复）%s" % (C["g"], C["n"]))
    say("")
    return 0


def _all_ids(roots):
    out = []

    def walk(n):
        out.append(str(n.get("id", "")))
        for ch in n.get("children") or []:
            walk(ch)

    for key in ("bookmark_bar", "other", "synced"):
        r = roots.get(key)
        if isinstance(r, dict):
            walk(r)
    return out


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  已取消。")
        sys.exit(130)
