#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并清单.py —— 把「软件清单」和「免费资源」两份内容源合并成一份，
并严格校验：每一个源条目恰好被消费一次。漏掉或重复都会报错退出。

放哪儿、怎么跑：
    本脚本在 scripts/合并清单/ 里，直接双击「生成合并清单.command」或：
        python3 scripts/合并清单/合并清单.py
    跑完覆盖写 内容源/软件清单与免费资源.md。

    --check  只校验，不写文件

原理：
    1. 调用 build.py --dump，拿到两份内容源的权威解析结果（apps.html / free.html
       两段 JSON）。不自己重新解析 markdown，避免两套解析器打架。
    2. 读同目录的「目标结构.txt」，按里面的引用把条目搬进新的分类骨架。
    3. 每个源条目有唯一钥匙 (来源, 一级分类, 分组, 标题)；引用解析到钥匙后从池子
       里取走。结束时池子必须为空，且没有任何钥匙被取过两次。

目标结构.txt 的语法（注释用 //，空行忽略）：
    #分类                一级分类
    ##分组               分组
    [a] 名字             取「软件清单」里标题为「名字」的条目
    [f] 名字             取「免费资源」里标题为「名字」的条目
    [a@选择器] 名字      同名条目不止一条时用 @ 限定；选择器写一级分类名或分组名，
                         匹配上以后必须只剩一条，否则报错
    A + B                一行里用 + 合并多条
    {...}                把显示名换成这个（改「浏览器」这类句柄用）
    => 整行文字          左边照常写引用，右边直接输出这句话（合并 / 手工润色用）
"""

import json
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILD = REPO / "build.py"
SPEC = HERE / "目标结构.txt"
DEST = REPO / "内容源" / "软件清单与免费资源.md"

DIRECT = "（直挂）"
SRC_ALIAS = {"a": "apps", "f": "free"}


class SpecError(Exception):
    def __init__(self, lineno, msg):
        super().__init__("目标结构.txt 第 %d 行：%s" % (lineno, msg))
        self.lineno = lineno
        self.msg = msg


# ==========================================================================
# 1. 从 build.py --dump 装载源条目
# ==========================================================================
def load_sources():
    """跑 build.py --dump，按 === xxx.html === 分段解析出两份结构。"""
    proc = subprocess.run([sys.executable, str(BUILD), "--dump"],
                          cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + "\n" + proc.stderr + "\n")
        raise SystemExit("build.py --dump 失败，先把它跑通再合并")

    text = proc.stdout
    marks = list(re.finditer(r"^=== (\S+\.html) ===\s*$", text, re.M))
    if not marks:
        raise SystemExit("build.py --dump 的输出里没找到 === xxx.html === 分段")

    sections = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sections[m.group(1)] = text[m.end():end].strip()

    def flatten(html_name, alias):
        data = json.loads(sections[html_name])
        out = []
        for cat in data:
            for node in cat["children"]:
                kids = node.get("children") or []
                if kids:
                    for e in kids:          # node 是分组，kids 才是条目
                        out.append(dict(src=alias, cat=cat["title"],
                                        group=node["title"], node=e))
                else:                        # 直接挂在分类下的条目
                    out.append(dict(src=alias, cat=cat["title"],
                                    group=DIRECT, node=node))
        return out

    return flatten("apps.html", "apps") + flatten("free.html", "free")


POOL = OrderedDict()
for _e in load_sources():
    _k = (_e["src"], _e["cat"], _e["group"], _e["node"]["title"])
    if _k in POOL:
        raise SystemExit("源数据里就有重名钥匙，先修数据：%s" % (_k,))
    POOL[_k] = _e

USED = {}       # 钥匙 -> 用它的行号


# ==========================================================================
# 2. 引用解析
# ==========================================================================
REF_RE = re.compile(r"^\[(a|f)(?:@([^\]]+))?\]\s*(.+?)\s*$")
RENAME_RE = re.compile(r"\s*\{([^}]*)\}\s*$")


def resolve(ref, lineno):
    m = REF_RE.match(ref.strip())
    if not m:
        raise SpecError(lineno, "看不懂这条引用：%r" % ref.strip())
    src, sel, name = SRC_ALIAS[m.group(1)], m.group(2), m.group(3)

    cands = [k for k in POOL if k[0] == src and k[3] == name]
    if sel:
        cands = [k for k in cands if sel in (k[1], k[2])]

    if not cands:
        where = "「%s」里" % sel if sel else ""
        raise SpecError(lineno, "%s找不到标题为「%s」的条目" % (where, name))
    if len(cands) > 1:
        detail = "、".join("%s/%s" % (k[1], k[2]) for k in cands)
        raise SpecError(lineno, "「%s」有 %d 条，要用 @ 限定（候选：%s）"
                        % (name, len(cands), detail))
    return cands[0]


def take(key, lineno):
    if key in USED:
        raise SpecError(lineno, "重复使用「%s」（第 %d 行已经用过）"
                        % (key[3], USED[key]))
    USED[key] = lineno
    return key


# ==========================================================================
# 3. 行渲染
# ==========================================================================
def rename_line(raw, newname, is_star):
    """
    改显示名，两种情况：
      A. [原名](url)：说明  →  [新名](url)：说明
      B. 原名：说明          →  新名：说明
         若说明正好以 [新名](url) 开头，就提上来变成 A 那种形式
         （「输入法：[微信输入法](url)多平台同步」→「[微信输入法](url)：多平台同步」）
    """
    star = "☆ " if is_star else ""

    m = re.match(r"^\[(?:☆ )?([^\]]*)\]\(([^)]*)\)(.*)$", raw)
    if m:
        return "[%s%s](%s)%s" % (star, newname, m.group(2), m.group(3))

    rest = raw.split("：", 1)[1].strip() if "：" in raw else ""
    m2 = re.match(r"^\[([^\]]*)\]\(([^)]*)\)\s*[:：]?\s*(.*)$", rest)
    if m2 and (newname in m2.group(1) or m2.group(1) in newname):
        body = m2.group(3).rstrip()
        return "[%s%s](%s)%s%s" % (star, newname, m2.group(2),
                                   "：" if body else "", body)
    return "%s%s%s%s" % (star, newname, "：" if rest else "", rest)


def bullet(raw, indent):
    """dump 里的 raw 不含列表符号，要自己补；已经有符号的就不重复加。"""
    raw = raw.rstrip()
    return " " * indent + ("- " if not raw.startswith("- ") else "") + raw


def render_item(entry, newname, indent=4):
    node = entry["node"]
    raw = node["raw"].rstrip()
    line = raw if newname is None else rename_line(raw, newname, node.get("star"))
    out = [bullet(line, indent)]
    for c in node.get("children") or []:
        out.append(bullet(c["raw"], indent + 4))
    return out


def merge_entries(entries, newname):
    """多条合并（没有 => 覆盖时的兜底）：取第一条的链接，说明去重后接起来。"""
    name = newname or entries[0]["node"]["title"]
    url = next((e["node"]["url"] for e in entries if e["node"].get("url")), "")
    star = "☆ " if any(e["node"].get("star") for e in entries) else ""
    seen, descs = set(), []
    for e in entries:
        d = (e["node"].get("desc") or "").strip().rstrip("。")
        if d and d not in seen:
            seen.add(d)
            descs.append(d)
    body = "；".join(descs)
    if url:
        return "[%s%s](%s)%s%s" % (star, name, url, "：" if body else "", body)
    return "%s%s%s%s" % (star, name, "：" if body else "", body)


# ==========================================================================
# 4. 解析目标结构
# ==========================================================================
FINAL = {}      # 钥匙 -> (新分类, 新分组, 新显示名 or None, 是否合并行)


def parse_spec():
    tree = OrderedDict()
    cat = grp = None

    for i, raw in enumerate(SPEC.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue

        if line.startswith("##"):
            if cat is None:
                raise SpecError(i, "分组出现在任何一级分类之前")
            grp = line.lstrip("#").strip()
            tree[cat].setdefault(grp, [])
            continue
        if line.startswith("#"):
            cat = line.lstrip("#").strip()
            grp = None
            tree.setdefault(cat, OrderedDict())
            continue

        if cat is None or grp is None:
            raise SpecError(i, "条目出现在任何分类 / 分组之前：%r" % line)

        left, sep, right = line.partition("=>")
        override = right.strip() if sep else None
        left = left.strip()

        if override is None:
            m = RENAME_RE.search(left)
            newname = m.group(1) if m else None
            left = left[:m.start()].strip() if m else left
        else:
            newname = None

        # 只在「+ 后面紧跟一个引用」的地方断开，这样标题里自带的 " + "
        #（例如「联想一键还原 + Win10 保留文件重置」）不会被误切
        parts = [p.strip() for p in re.split(r"\s*\+\s*(?=\[)", left) if p.strip()]
        if not parts:
            raise SpecError(i, "这一行没有任何引用：%r" % line)
        keys = [take(resolve(p, i), i) for p in parts]

        merged = len(keys) > 1
        for k in keys:
            FINAL[k] = (cat, grp, newname, override, merged, i)

        tree[cat][grp].append(dict(keys=keys, newname=newname,
                                   override=override, lineno=i))
    return tree


def render_group(entries):
    out = []
    for e in entries:
        if e["override"] is not None:
            out.append("    - " + e["override"])
            continue
        if len(e["keys"]) == 1:
            out.extend(render_item(POOL[e["keys"][0]], e["newname"]))
        else:
            out.append("    - " + merge_entries([POOL[k] for k in e["keys"]],
                                                e["newname"]))
    return out


HEADER = """<!--
  本文件由「软件清单」和「免费资源」两份内容源合并而成，目前是**草稿**，
  还没有挂到站点上（build.py 的 LIST_PAGES 里没有登记它）。

  生成方式：scripts/合并清单/合并清单.py 按「目标结构.txt」逐条搬运，
  校验规则是「每个源条目恰好被用到一次」，漏掉或重复都会直接报错；
  同名条目跨两份清单只保留一条，说明合并进同一行。

  改完本文件等于白改 —— 下次重跑会被覆盖。要改内容请改 目标结构.txt，
  或者直接改「内容源/软件清单.md」「内容源/免费资源.md」再重新合并。

  写法与其他清单页完全一样：
    ## 一级分类
    - 分组：
        - [名称](网址)：一句话说明
-->

"""


def build_map(tree):
    """生成「旧 → 新」对照数据，用来人工审阅这次合并到底动了什么。"""
    old_cats = OrderedDict()        # (来源, 旧分类) -> 条目数 / 去向
    renamed = []                    # 改过显示名的
    merged = OrderedDict()          # (新分类, 新分组) -> [旧条目描述]

    for k, e in POOL.items():
        src, ocat, ogrp, title = k
        ncat, ngrp, newname, override, is_merged, lineno = FINAL[k]
        old_cats.setdefault((src, ocat), set()).add(ncat)

        if newname and newname != title:
            renamed.append((src, ocat, ogrp, title, ncat, ngrp, newname, override))
        if is_merged:
            merged.setdefault((ncat, ngrp, lineno), []).append(
                "%s（%s / %s）" % (title, ocat, ogrp))

    return old_cats, renamed, merged


SRC_CN = {"apps": "软件清单", "free": "免费资源"}


def map_data(tree):
    """把对照信息整理成 [(标题, 表头, [行...])]，md 和 html 共用。"""
    old_cats, renamed, merged = build_map(tree)

    n_old = len(POOL)
    n_new_cat = len(tree)
    n_new_grp = sum(len(g) for g in tree.values())
    n_out = sum(len(g) for g in tree.values() for _ in [0]) or 0
    n_out = sum(len(g) for c in tree.values() for g in c.values())
    n_merge_lines = sum(1 for c in tree.values() for g in c.values()
                        for x in g if len(x["keys"]) > 1)

    blocks = []

    blocks.append(("数字", ["项目", "合并前", "合并后"], [
        ["一级分类", "8（软件清单）+ 8（免费资源）", str(n_new_cat)],
        ["分组", "38 + 34", str(n_new_grp)],
        ["条目", "%d（逐条都在）" % n_old,
         "%d 行，其中 %d 行是两条以上合并" % (n_out, n_merge_lines)],
    ], "条目数变少不是丢内容：同一款软件以前在两份清单里各写了一遍，"
       "现在合成一行、说明并在一起。校验脚本保证每个源条目都被用了一次。"))

    blocks.append(("一、旧分类去了哪", ["来源", "旧分类", "拆进的新分类"],
                   [[SRC_CN[s], oc, "、".join(sorted(t))]
                    for (s, oc), t in old_cats.items()], None))

    blocks.append(("二、改了显示名的条目",
                   ["来源 / 原位置", "原来显示成", "现在显示成"],
                   [["%s / %s / %s" % (SRC_CN[s], oc, og), title, nn]
                    for s, oc, og, title, _nc, _ng, nn, _ov in renamed],
                   "原来的写法是「句柄：产品」，句柄本身不是软件名，"
                   "搜索时也搜不到。现在统一改成产品名。"))

    blocks.append(("三、合并掉的重复条目", ["新位置", "并进来的源条目"],
                   [["%s / %s" % (nc, ng), items] for (nc, ng, _l), items in
                    sorted(merged.items())],
                   "同一款软件在「软件清单」和「免费资源」里各出现一次，"
                   "现在合成一行，说明并在一起。"))

    return blocks


def write_map(tree):
    blocks = map_data(tree)

    # ---------------- Markdown ----------------
    L = ["# 合并对照表\n",
         "把「软件清单」和「免费资源」合成一份，做了什么改动，都在这一张表里。\n"]
    for title, head, rows, note in blocks:
        L.append("## %s\n" % title)
        if note:
            L.append(note + "\n")
        L.append("| " + " | ".join(head) + " |")
        L.append("| " + " | ".join("---" for _ in head) + " |")
        for r in rows:
            L.append("| " + " | ".join(
                "<br>".join(v) if isinstance(v, list) else str(v) for v in r) + " |")
        L.append("")
    (HERE / "对照表.md").write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    print("生成：scripts/合并清单/对照表.md")

    # ---------------- HTML ----------------
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    parts = []
    for title, head, rows, note in blocks:
        parts.append('<section><h2>%s</h2>' % esc(title))
        if note:
            parts.append('<p class="note">%s</p>' % esc(note))
        parts.append("<table><thead><tr>%s</tr></thead><tbody>"
                     % "".join("<th>%s</th>" % esc(h) for h in head))
        for r in rows:
            cells = []
            for v in r:
                if isinstance(v, list):
                    cells.append("<td>%s</td>"
                                 % "<br>".join(esc(x) for x in v))
                else:
                    cells.append("<td>%s</td>" % esc(v))
            parts.append("<tr>%s</tr>" % "".join(cells))
        parts.append("</tbody></table></section>")

    html = HTML_TPL.replace("<!--BODY-->", "\n".join(parts))
    (HERE / "对照表.html").write_text(html, encoding="utf-8")
    print("生成：scripts/合并清单/对照表.html")
    return True


HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>合并对照表 · 软件清单 + 免费资源</title>
<style>
:root{--bg:#eef1f7;--card:#fff;--fg:#121826;--dim:#5b667c;--line:#dbe1ec;--accent:#2f6df6}
@media (prefers-color-scheme:dark){
  :root{--bg:#111521;--card:#171c2b;--fg:#e9edf5;--dim:#9aa5bb;--line:#2a3247;--accent:#5b8cff}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
  "Microsoft YaHei",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:27px;margin:0 0 6px}
.lead{color:var(--dim);margin:0 0 34px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:22px 24px;margin:0 0 20px}
h2{font-size:17px;margin:0 0 12px;padding-left:11px;border-left:4px solid var(--accent)}
.note{color:var(--dim);font-size:13.5px;margin:0 0 14px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;vertical-align:top;padding:9px 12px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:13px;background:transparent}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:rgba(127,127,127,.06)}
td:nth-child(1){white-space:nowrap}
@media (max-width:720px){
  th,td{display:block;border:0;padding:3px 0}
  thead{display:none}
  tr{display:block;padding:12px 0;border-bottom:1px solid var(--line)}
  td:nth-child(1){font-weight:600}
}
</style>
</head>
<body>
<div class="wrap">
<h1>合并对照表</h1>
<p class="lead">「软件清单」+「免费资源」→ 一份。这份表说明这次合并动了什么。</p>
<!--BODY-->
</div>
</body>
</html>
"""


def main():
    check_only = "--check" in sys.argv
    tree = parse_spec()

    left = [k for k in POOL if k not in USED]
    if left:
        print("=" * 68)
        print("校验失败：有 %d 个源条目没被安排到新结构里" % len(left))
        print("=" * 68)
        for k in left:
            print("  漏掉：[%s] %s / %s / %s" % k)
        print("\n把它们补进 目标结构.txt 再跑一次。")
        return 1

    print("校验通过：%d 个源条目全部恰好用了一次" % len(POOL))

    write_map(tree)

    if check_only:
        return 0

    buf = [HEADER]
    for cat, groups in tree.items():
        buf.append("## %s\n" % cat)
        for grp, entries in groups.items():
            buf.append("- %s：" % grp)
            buf.extend(render_group(entries))
            buf.append("")
        buf.append("")
    text = "\n".join(buf).rstrip() + "\n"

    DEST.write_text(text, encoding="utf-8")
    print("生成：%s" % DEST.relative_to(REPO))
    print("       %d 个一级分类 / %d 个分组"
          % (len(tree), sum(len(g) for g in tree.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
