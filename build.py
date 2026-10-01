#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py —— 把 README.md（唯一内容源）编译成单文件静态站点 index.html

用法：
    python3 build.py            # 生成 index.html
    python3 build.py --dump     # 只打印解析后的结构（JSON），用于校对内容有无丢失

设计原则：
    1. README.md 是唯一内容源，改内容只改 README，然后重跑本脚本。
    2. index.html 单文件、零依赖、离线可用，数据全部内联。
    3. 内容零丢失：解析不出来的东西会被收集到 orphans 里并告警，绝不静默丢弃。
"""

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "README.md"
OUT = ROOT / "index.html"

# --------------------------------------------------------------------------
# 1. 行内 Markdown -> HTML
# --------------------------------------------------------------------------

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def md_inline(s: str) -> str:
    """把一段行内 markdown 转成 HTML 片段。链接优先处理，避免 URL 里的冒号被误切。
    注意：链接旁文要分段转义，不能整段转义后再拼接，否则生成的 <a> 会被二次转义。"""
    out = []
    pos = 0
    for m in LINK_RE.finditer(s):
        out.append(inline_only(s[pos:m.start()]))
        text, url = m.group(1), m.group(2)
        text_html = inline_only(text)
        if url:
            out.append(
                f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{text_html}</a>'
            )
        else:
            out.append(text_html)
        pos = m.end()
    out.append(inline_only(s[pos:]))
    html_out = "".join(out)
    # 链接与中文/字母直接相邻时补一个细空格，避免「Snipaste最好用」这种粘连
    html_out = re.sub(r"</a>(?=[\u4e00-\u9fffA-Za-z0-9])", "</a>&#8201;", html_out)
    html_out = re.sub(r"(?<=[\u4e00-\u9fffA-Za-z0-9])<a ", "&#8201;<a ", html_out)
    return html_out


def inline_only(s: str) -> str:
    """粗体 / 删除线 / 行内代码。先转义再替换，避免注入。"""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = s.replace("  ", " ")
    return s


def plain(s: str) -> str:
    """用于 data-search，去掉所有标记。"""
    s = LINK_RE.sub(lambda m: m.group(1), s)
    return re.sub(r"[*~`]", "", s).strip()


# --------------------------------------------------------------------------
# 2. 解析 README -> 树
# --------------------------------------------------------------------------

BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
CONT_RE = re.compile(r"^\s*[：:]\s*(.*)$")


def parse_lines(text: str):
    """把 markdown 拍平成 (indent, content, kind, is_bullet) 序列。"""
    blocks = []
    in_comment = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line:
            if "-->" not in line.split("<!--", 1)[1]:
                in_comment = True
            continue
        if not line.strip():
            continue
        if line.startswith("## "):
            blocks.append(("cat", 0, line[3:].strip()))
            continue
        m = BULLET_RE.match(line)
        if m:
            indent = len(m.group(1))
            content = m.group(2).strip()
            if content == "":
                continue
            blocks.append(("item", indent, content, True))
            continue
        if line.strip() in ("-", "*", "+", "—", "–"):
            continue  # 空 bullet，原文里的占位符
        m = CONT_RE.match(line)
        if m and blocks and blocks[-1][0] == "item":
            # 续行：把内容并到上一条的描述里
            blocks[-1] = ("item", blocks[-1][1], blocks[-1][2] + "：" + m.group(1).strip(),
                          blocks[-1][3])
            continue
        blocks.append(("item", len(line) - len(line.lstrip()), line.strip(), False))
    return blocks


def mask_links(s: str):
    """把 markdown 链接替换成占位符，用于安全地按冒号切分标题/描述。"""
    store = []

    def rep(m):
        store.append(m.group(0))
        return f"\x00{len(store) - 1}\x00"

    return LINK_RE.sub(rep, s), store


def unmask(s: str, store):
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], s)


def make_node(text: str, is_bullet: bool = True):
    dep = "~~" in text
    bare = text.replace("~~", "").strip()
    node = {
        "title": bare,
        "url": "",
        "desc": "",
        "children": [],
        "dep": dep,
        "star": False,
        "has_link": False,
        "bullet": is_bullet,
    }

    star = False
    if bare.startswith("[☆") or "☆" in bare[:6]:
        star = True
    node["star"] = star or "（荐）" in bare
    if node["star"]:
        bare = bare.replace("☆", "").replace("（荐）", "")

    m = LINK_RE.match(bare)
    if m and m.start() == 0:
        title, url = m.group(1), m.group(2)
        rest = bare[m.end():]
        # 链接后面紧跟的中英文冒号才算描述分隔
        m2 = re.match(r"^\s*[：:]\s*(.*)$", rest)
        node["url"] = url
        node["has_link"] = True
        node["title"] = title
        node["desc"] = (m2.group(1) if m2 else rest.lstrip("，,、 ")).strip()
    else:
        # 先把行内链接整体遮起来，免得 URL 里的 "https:" 被当成标题/描述分隔符
        masked, store = mask_links(bare)
        parts = re.split(r"[：:]", masked, maxsplit=1)
        if len(parts) == 2 and parts[0].strip():
            node["title"] = unmask(parts[0], store).strip()
            node["desc"] = unmask(parts[1], store).strip()
        else:
            node["title"] = bare
    node["title"] = node["title"].replace("☆", "").strip()
    # 标题收尾清理：去掉句号、悬挂的冒号
    node["title"] = re.sub(r"[。.．]+$", "", node["title"]).strip()
    node["header"] = bare.endswith(("：", ":")) and not node["desc"] and not node["url"]
    node["title"] = node["title"].rstrip("：:").strip()
    node["raw"] = bare
    return node


def promote_headers(nodes):
    """把「小标题式」的条目提升为分组：纯文本行以冒号结尾（如 `工具类：`），
    或空描述的 bullet 且其后续同级条目缩进更深。"""
    i = 0
    while i < len(nodes):
        n = nodes[i]
        promote_headers(n["children"])
        head = n["header"]
        if not n["children"] and not n["has_link"] and head:
            plain_line = not n.get("bullet", True)
            deeper = (i + 1 < len(nodes)
                      and nodes[i + 1].get("indent", 0) > n.get("indent", 0))
            if plain_line or deeper:
                j = i + 1
                while j < len(nodes) and not nodes[j]["children"] and not nodes[j]["has_link"] \
                        and not nodes[j]["header"]:
                    n["children"].append(nodes[j])
                    j += 1
                del nodes[i + 1:j]
        i += 1
    return nodes


def build_tree(blocks):
    cats = []
    cur_cat = None
    stack = []  # (indent, node)

    root = {"title": "未分类", "children": [], "cat": True, "id": "misc"}
    for block in blocks:
        if block[0] == "cat":
            content = block[2]
            if cur_cat is not None:
                cats.append(cur_cat)
            slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", content).strip("-").lower()
            cur_cat = {"title": content, "children": [], "cat": True, "id": slug or "cat"}
            stack = []
            continue
        _, indent, content, is_bullet = block
        node = make_node(content, is_bullet)
        node["indent"] = indent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        elif cur_cat is not None:
            cur_cat["children"].append(node)
        else:
            root["children"].append(node)
        stack.append((indent, node))

    if cur_cat is not None:
        cats.append(cur_cat)
    if root["children"]:
        cats.append(root)
    for c in cats:
        promote_headers(c["children"])
    return cats


# --------------------------------------------------------------------------
# 3. 渲染 HTML
# --------------------------------------------------------------------------

DEP_GROUP_HINTS = ("已废除", "已弃用", "弃坑")


def render_node(node, ctx, depth=0):
    """把节点渲染成 HTML，返回 (html, 该节点下的分组锚点列表[(id, 标题, 层级)])。
    有子项且自身无链接 -> 分组(<details>)；否则算条目。"""
    kids = node["children"]
    is_group = bool(kids) and not node["has_link"]

    if is_group:
        ctx["g"] += 1
        gid = f"g{ctx['g']}"
        is_dep = any(h in node["title"] for h in DEP_GROUP_HINTS)
        attr = "" if is_dep else " open"
        cls = " grp" + (" grp-dep" if is_dep else "")
        desc = f'<p class="grp-desc">{md_inline(node["desc"])}</p>' if node.get("desc") else ""
        inner, sub_groups = "", []
        for k in kids:
            kh, kg = render_node(k, ctx, depth + 1)
            inner += kh
            sub_groups.extend(kg)
        html = (
            f'<details class="group{cls}" id="{gid}" data-spy{attr}>'
            f'<summary><span class="grp-title">{md_inline(node["title"])}</span>'
            f'<span class="grp-n">{leaf_count(kids)}</span></summary>'
            f'{desc}<div class="grp-body">{inner}</div></details>'
        )
        return html, [(gid, node["title"], depth)] + sub_groups

    # 叶子条目
    cls = ["item"]
    if node["dep"]:
        cls.append("dep")
    if node["star"]:
        cls.append("star")
    title_html = md_inline(node["title"])
    if node["url"]:
        title_html = (
            f'<a class="nm" href="{esc(node["url"])}" target="_blank" '
            f'rel="noopener noreferrer">{title_html}</a>'
        )
    else:
        title_html = f'<span class="nm">{title_html}</span>'

    badge = '<span class="badge" title="个人推荐">荐</span>' if node["star"] else ""
    desc_html = f'<span class="ds">{md_inline(node["desc"])}</span>' if node["desc"] else ""
    sub = ""
    if kids:
        sub = '<ul class="sub">' + "".join(
            f"<li>{render_item_inline(k)}</li>" for k in kids
        ) + "</ul>"

    search = plain(node["title"] + " " + node["desc"] + " " + " ".join(
        plain(k["title"] + k["desc"]) for k in kids))
    flags = f' data-s="{esc(search.lower())}"'
    if node["url"]:
        flags += ' data-l="1"'
    if node["star"]:
        flags += ' data-star="1"'
    return (
        f'<div class="{" ".join(cls)}"{flags}>'
        f'{title_html}{badge}{desc_html}{sub}</div>'
    ), []


def render_item_inline(node):
    t = md_inline(node["title"])
    if node["url"]:
        t = f'<a href="{esc(node["url"])}" target="_blank" rel="noopener noreferrer">{t}</a>'
    d = f' — <span class="ds">{md_inline(node["desc"])}</span>' if node["desc"] else ""
    return f"{t}{d}"


def leaf_count(nodes) -> int:
    """按「会渲染成 .item 的节点数」计数：有链接又有子项的，子项渲染成附注行，不单独计数。"""
    n = 0
    for x in nodes:
        if x["children"] and not x["has_link"]:
            n += leaf_count(x["children"])
        else:
            n += 1
    return n


def render(cats, updated: str) -> str:
    ctx = {"g": 0}
    body = []
    toc_cats = []

    for c in cats:
        groups = []
        body.append(f'<section class="sec" id="{c["id"]}" data-spy>')
        body.append(
            f'<h2>{esc(c["title"])}'
            f'<a class="anchor" href="#{c["id"]}" title="复制此节链接">#</a></h2>'
        )
        body.append('<div class="sec-body">')
        for n in c["children"]:
            html, gs = render_node(n, ctx)
            body.append(html)
            groups.extend(gs)
        body.append("</div></section>")
        toc_cats.append((c["id"], c["title"], leaf_count(c["children"]), groups))

    # 移动/窄屏用的顶部分类条
    nav = "".join(
        f'<a href="#{cid}">{esc(ct)}<span class="n">{n}</span></a>'
        for cid, ct, n, _ in toc_cats
    )

    # 桌面端侧边目录（分类 + 分组两级）
    toc = []
    for cid, ct, n, groups in toc_cats:
        toc.append(
            f'<div class="toc-cat"><a href="#{cid}" data-t="{cid}">{esc(ct)}'
            f'<span class="n">{n}</span></a>'
        )
        if groups:
            toc.append('<div class="toc-grp">')
            for gid, gtitle, gdepth in groups:
                d = f' data-d="{gdepth}"' if gdepth else ""
                toc.append(f'<a href="#{gid}" data-t="{gid}"{d}>{esc(gtitle)}</a>')
            toc.append("</div>")
        toc.append("</div>")

    page = TEMPLATE.replace("__NAV__", nav) \
                   .replace("__TOC__", "\n".join(toc)) \
                   .replace("__BODY__", "\n".join(body)) \
                   .replace("__UPDATED__", updated)
    # 计数直接从成品里数，保证页脚、导航、JS 三处口径一致
    total = len(re.findall(r'<div class="[^"]*\bitem\b[^"]*" data-s=', page))
    links = len(re.findall(r'href="https?://', page))
    return page.replace("__TOTAL__", str(total)).replace("__LINKS__", str(links))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>uppjs.com · 软件与硬件清单</title>
<meta name="description" content="个人整理的 Mac / PC / 手机软件与硬件清单，支持即时搜索。">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%232f6fed'/%3E%3Ctext x='16' y='23' font-size='19' font-family='sans-serif' font-weight='700' fill='%23fff' text-anchor='middle'%3Eu%3C/text%3E%3C/svg%3E">
<style>
:root{
  --bg:#f6f7f9; --panel:#ffffff; --panel2:#f0f2f5; --line:#e2e5ea;
  --fg:#1b1f24; --fg2:#5b626b; --fg3:#8b929c;
  --accent:#2f6fed; --accent-soft:#e8efff; --mark:#ffe9a8; --mark-fg:#3a2c00;
  --radius:10px; --hh:57px; --tocw:206px;
}
html[data-theme="dark"]{
  --bg:#14161a; --panel:#1c1f24; --panel2:#22262c; --line:#2e333a;
  --fg:#e6e8ec; --fg2:#a8b0ba; --fg3:#7c848e;
  --accent:#6ea0ff; --accent-soft:#22314f; --mark:#6b5a1a; --mark-fg:#ffeaa0;
}
@media (prefers-color-scheme: dark){
  html[data-theme="auto"]{
    --bg:#14161a; --panel:#1c1f24; --panel2:#22262c; --line:#2e333a;
    --fg:#e6e8ec; --fg2:#a8b0ba; --fg3:#7c848e;
    --accent:#6ea0ff; --accent-soft:#22314f; --mark:#6b5a1a; --mark-fg:#ffeaa0;
  }
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
}
a{color:var(--accent); text-decoration:none}
a:hover{text-decoration:underline}
code{background:var(--panel2); padding:1px 5px; border-radius:4px; font-size:12.5px;
     font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:4px}

/* ---------- 顶栏 ---------- */
header{
  position:sticky; top:0; z-index:50;
  background:var(--bg); border-bottom:1px solid var(--line);
}
@supports (backdrop-filter:blur(8px)){
  header{background:color-mix(in srgb,var(--bg) 86%,transparent); backdrop-filter:saturate(1.6) blur(10px)}
}
.bar{
  max-width:1180px; margin:0 auto; padding:9px 16px;
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
}
.brand{font-weight:700; font-size:15px; white-space:nowrap}
.brand span{color:var(--fg3); font-weight:400; margin-left:6px; font-size:13px}
.search{flex:1 1 240px; min-width:150px; position:relative}
.search input{
  width:100%; padding:8px 30px 8px 32px; border:1px solid var(--line); border-radius:var(--radius);
  background:var(--panel); color:var(--fg); font-size:14px; outline:none;
}
.search input:focus{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}
.search::before{content:"⌕"; position:absolute; left:11px; top:7px; color:var(--fg3); font-size:15px}
.search button{
  position:absolute; right:4px; top:4px; border:0; background:transparent; color:var(--fg3);
  font-size:16px; cursor:pointer; padding:4px 8px; border-radius:6px; display:none;
}
.search.has button{display:block}
.tools{display:flex; align-items:center; gap:8px; font-size:13px; color:var(--fg3); white-space:nowrap}
.tools button,.tools select{
  border:1px solid var(--line); background:var(--panel); color:var(--fg2);
  padding:6px 9px; border-radius:8px; cursor:pointer; font-size:13px; max-width:150px;
}
.tools button:hover,.tools select:hover{border-color:var(--accent); color:var(--accent)}
#count{font-variant-numeric:tabular-nums}

/* ---------- 窄屏分类条 ---------- */
nav.cats{position:sticky; top:var(--hh); z-index:40; background:var(--bg); border-bottom:1px solid var(--line)}
nav.cats .wrap{
  max-width:1180px; margin:0 auto; padding:8px 16px; display:flex; gap:6px;
  overflow-x:auto; scrollbar-width:none;
}
nav.cats .wrap::-webkit-scrollbar{display:none}
nav.cats a{
  white-space:nowrap; padding:5px 11px; border-radius:20px; border:1px solid var(--line);
  background:var(--panel); color:var(--fg2); font-size:13px;
}
nav.cats a:hover,nav.cats a.on{border-color:var(--accent); color:var(--accent); text-decoration:none}
nav.cats a .n{color:var(--fg3); margin-left:5px; font-size:11px}

/* ---------- 外壳 ---------- */
.shell{
  max-width:1180px; margin:0 auto; padding:16px 16px 0;
  display:flex; align-items:flex-start; gap:24px;
}
aside.toc{display:none}
main{flex:1; min-width:0; padding-bottom:34px}

@media (min-width:1024px){
  nav.cats{display:none}
  aside.toc{
    display:block; flex:0 0 var(--tocw); position:sticky; top:calc(var(--hh) + 14px);
    max-height:calc(100vh - var(--hh) - 28px); overflow-y:auto; overscroll-behavior:contain;
    padding-right:4px;
  }
  aside.toc::-webkit-scrollbar{width:6px}
  aside.toc::-webkit-scrollbar-thumb{background:var(--line); border-radius:3px}
}
.toc-h{font-size:11px; letter-spacing:.09em; color:var(--fg3); text-transform:uppercase;
       margin:0 0 7px 9px}
.toc-cat>a{
  display:flex; align-items:center; gap:8px; padding:5px 9px; border-radius:7px;
  font-weight:600; font-size:13px; color:var(--fg2);
}
.toc-cat>a span.n{margin-left:auto}
.toc-cat>a:hover{background:var(--panel2); color:var(--fg); text-decoration:none}
.toc-cat>a.on{background:var(--accent-soft); color:var(--accent)}
.toc-cat>a .n,.toc-grp a .n{font-size:11px; color:var(--fg3); font-weight:400}
.toc-grp{margin:1px 0 7px 9px; border-left:1px solid var(--line); padding-left:7px}
.toc-grp a{
  display:block; padding:3px 7px; border-radius:6px; font-size:12.5px; color:var(--fg3);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.toc-grp a:hover{color:var(--accent); background:var(--panel2); text-decoration:none}
.toc-grp a.on{color:var(--accent); background:var(--accent-soft)}
.toc-grp a[data-d="1"]{padding-left:18px; font-size:12px}

/* ---------- 主体 ---------- */
.sec{margin-bottom:22px; scroll-margin-top:calc(var(--hh) + 14px)}
.sec h2{
  font-size:17px; margin:0 0 10px; padding-bottom:7px; border-bottom:2px solid var(--line);
  display:flex; align-items:center; gap:8px;
}
.sec h2 .anchor{opacity:0; font-size:15px; color:var(--fg3)}
.sec h2:hover .anchor{opacity:1}
.sec-body{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:6px 14px}

details.group{border-bottom:1px dashed var(--line); padding:4px 0; scroll-margin-top:calc(var(--hh) + 14px)}
details.group:last-child{border-bottom:0}
details.group.grp-dep{opacity:.78}
details.group>summary{
  cursor:pointer; list-style:none; padding:7px 0; display:flex; align-items:center; gap:8px;
  font-weight:600; font-size:14px;
}
details.group>summary::-webkit-details-marker{display:none}
details.group>summary::before{
  content:"▸"; color:var(--fg3); font-size:11px; transition:transform .15s; display:inline-block;
}
details.group[open]>summary::before{transform:rotate(90deg)}
.grp-n{color:var(--fg3); font-weight:400; font-size:11.5px;
       background:var(--panel2); border-radius:10px; padding:0 7px}
.grp-desc{margin:0 0 6px 19px; color:var(--fg2); font-size:13px}
.grp-body{margin-left:19px; padding-bottom:6px}

.item{
  padding:5px 0 5px 12px; border-left:2px solid var(--line); margin:3px 0;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:8px;
}
.item:hover{border-left-color:var(--accent); background:var(--panel2)}
.item .nm{font-weight:600; color:var(--fg)}
.item a.nm{color:var(--accent)}
.item a.nm:hover{text-decoration:underline}
.item .ds{color:var(--fg2); font-size:13px; flex:1 1 260px}
.item .badge{
  font-size:10.5px; color:#fff; background:#d98a1f; border-radius:4px; padding:1px 5px;
  line-height:1.4;
}
.item.dep .nm{text-decoration:line-through; color:var(--fg3)}
.item.dep .ds{color:var(--fg3); text-decoration:line-through}
.item.cur{background:var(--accent-soft); border-left-color:var(--accent); border-radius:0 5px 5px 0}
ul.sub{margin:4px 0 2px 0; padding-left:16px; color:var(--fg2); font-size:13px; width:100%}
ul.sub li{margin:2px 0}
mark{background:var(--mark); color:var(--mark-fg); border-radius:2px; padding:0 1px}

@keyframes flash{from{background:var(--accent-soft)} to{background:transparent}}
.flash{animation:flash 1.2s ease-out}

.hidden{display:none !important}
.empty{display:none; text-align:center; color:var(--fg3); padding:44px 0; font-size:13.5px}
.empty.show{display:block}
.empty b{color:var(--fg2)}

/* ---------- 使用说明 ---------- */
.help{margin-top:28px; background:var(--panel); border:1px solid var(--line);
      border-radius:var(--radius); padding:6px 16px}
.help summary{cursor:pointer; font-weight:600; padding:8px 0}
.help h3{font-size:14px; margin:16px 0 6px}
.help p,.help li{color:var(--fg2); font-size:13px}
.help table{border-collapse:collapse; width:100%; margin:6px 0 4px}
.help td,.help th{border:1px solid var(--line); padding:5px 9px; font-size:13px; text-align:left;
                  vertical-align:top}
.help th{background:var(--panel2); font-weight:600}
.help kbd{background:var(--panel2); border:1px solid var(--line); border-bottom-width:2px;
          border-radius:4px; padding:0 5px; font-size:12px; font-family:inherit}

footer{
  max-width:1180px; margin:0 auto; padding:0 16px 46px; color:var(--fg3); font-size:12.5px;
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;
}
.totop{
  position:fixed; right:18px; bottom:18px; width:38px; height:38px; border-radius:50%;
  border:1px solid var(--line); background:var(--panel); color:var(--fg2); cursor:pointer;
  font-size:16px; display:none; z-index:60;
}
.totop.show{display:block}

@media (max-width:720px){
  .bar{padding:8px 12px; gap:8px}
  .brand span{display:none}
  .brand{font-size:14px}
  .tools{gap:6px}
  .tools button,.tools select{padding:6px 8px; font-size:12.5px}
  .shell{padding:12px 12px 0}
  .item .ds{flex-basis:100%; padding-left:0}
  .sec-body{padding:4px 10px}
  footer{padding:0 12px 34px}
}
@media print{
  header,nav.cats,aside.toc,.totop,.help{display:none}
  body{background:#fff}
  .shell{display:block; padding:0}
  .sec-body{border:0; padding:0}
  details.group{page-break-inside:avoid}
  details.group:not([open])>div,details.group:not([open])>p{display:block}
}
</style>
</head>
<body id="top">

<header>
  <div class="bar">
    <div class="brand">uppjs.com<span>软件与硬件清单</span></div>
    <div class="search" id="searchbox">
      <input id="q" type="search" placeholder="搜索软件名 / 说明，按 / 聚焦、↑↓ 选择" autocomplete="off">
      <button id="clr" title="清空">×</button>
    </div>
    <div class="tools">
      <span id="count"></span>
      <select id="filter" title="筛选">
        <option value="all">全部</option>
        <option value="link">有下载链接</option>
        <option value="star">我推荐的</option>
      </select>
      <button id="toggleAll" title="展开 / 折叠全部分组">折叠</button>
      <button id="theme" title="切换主题">主题</button>
    </div>
  </div>
</header>

<nav class="cats"><div class="wrap">__NAV__</div></nav>

<div class="shell">
  <aside class="toc">
    <p class="toc-h">目录</p>
__TOC__
  </aside>

  <main>
    <div class="empty" id="empty">
      没有匹配的条目。<br><b>试试更短的关键词</b>，或把筛选切回「全部」。
    </div>
__BODY__

    <details class="help" id="help">
      <summary>使用说明 / 关于本站</summary>
      <h3>这是什么</h3>
      <p>个人整理的软件、硬件与技巧清单，长期更新。收录标准只有一条：<strong>我自己在用、用得住</strong>。
         不接推广、不做商业排序。</p>
      <h3>键盘与鼠标</h3>
      <table>
        <tr><th>操作</th><th>作用</th></tr>
        <tr><td><kbd>/</kbd></td><td>聚焦搜索框（已聚焦时再按可清空）</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>清空搜索并退出</td></tr>
        <tr><td><kbd>↑</kbd> <kbd>↓</kbd></td><td>搜索时在结果之间移动</td></tr>
        <tr><td><kbd>Enter</kbd></td><td>打开当前选中条目的链接</td></tr>
        <tr><td>点击目录</td><td>左侧目录跳到分类或分组；已收起的分组会自动展开</td></tr>
        <tr><td>点击标题 #</td><td>跳转到该分类，可复制地址分享</td></tr>
      </table>
      <h3>搜索与筛选怎么用</h3>
      <p>直接输入关键词，匹配范围包括<strong>软件名 + 说明文字 + 子条目</strong>，大小写不敏感。
         搜索时所有分组会自动展开，没有命中的分组会被收起。例如输入
         <code>截图</code>、<code>下载</code>、<code>pdf</code>、<code>heic</code>。</p>
      <p>右上角筛选可以叠加在搜索之上：<strong>有下载链接</strong>只看能直接点开的条目，
         <strong>我推荐的</strong>只看标了「荐」的（对应清单里的 ☆ 标记）。</p>
      <h3>折叠与主题</h3>
      <p>点分组标题可折叠 / 展开；「折叠」按钮一键收起所有分组，便于总览。
         「主题」按钮在浅色 / 深色 / 跟随系统之间切换，选择记在本地浏览器里。
         宽屏时左侧目录会跟随滚动高亮当前所在位置。</p>
      <h3>内容怎么更新</h3>
      <p>本页由仓库里的 <code>README.md</code> 自动生成，README 是唯一内容源：</p>
      <p><code>编辑 README.md → 运行 python3 build.py → git push</code></p>
      <p>改内容只需动 README，不用碰这个页面的代码。</p>
      <h3>数据与隐私</h3>
      <ul>
        <li>纯静态页面，无后端、无数据库、无统计脚本、无第三方 CDN 请求。</li>
        <li>唯一的本地存储是主题偏好，不上传任何数据。</li>
        <li>页面上的链接都指向第三方站点，跳转后的行为不受本站控制。</li>
      </ul>
      <h3>免责声明</h3>
      <p>清单是个人使用记录，链接来自公开网络，不保证长期有效，也不提供任何软件下载托管。
         涉及系统激活、破解、绿色版等内容请自行判断合规性与安全风险，下载前建议用杀毒软件扫一遍。
         软件版权归各自厂商所有，请通过正规渠道购买授权。</p>
    </details>
  </main>
</div>

<footer>
  <span>内容源 README.md · 共 __TOTAL__ 条 · __LINKS__ 个外链 · 更新于 __UPDATED__</span>
  <span>纯静态 · 无追踪 · 无第三方请求</span>
</footer>

<button class="totop" id="totop" title="回到顶部">↑</button>

<script>
(function(){
  var q = document.getElementById('q'),
      box = document.getElementById('searchbox'),
      clr = document.getElementById('clr'),
      filter = document.getElementById('filter'),
      count = document.getElementById('count'),
      empty = document.getElementById('empty'),
      toggleAll = document.getElementById('toggleAll'),
      items = [].slice.call(document.querySelectorAll('.item')),
      groups = [].slice.call(document.querySelectorAll('details.group')),
      sections = [].slice.call(document.querySelectorAll('.sec')),
      spyTargets = [].slice.call(document.querySelectorAll('[data-spy]')),
      tocLinks = [].slice.call(document.querySelectorAll('.toc a[data-t]')),
      orig = new Map(),
      shown = [],
      cursor = -1,
      reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  items.forEach(function(el){ orig.set(el, el.innerHTML); });
  var savedOpen = groups.map(function(g){ return g.open; });

  function esc(s){
    return s.replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function escRe(s){ return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function paint(el, re){
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null),
        nodes = [], n;
    while((n = w.nextNode())){
      if(n.parentNode.nodeName === 'MARK') continue;
      if(re.test(n.nodeValue)) nodes.push(n);
    }
    nodes.forEach(function(node){
      var frag = document.createDocumentFragment(), text = node.nodeValue, last = 0, m;
      re.lastIndex = 0;
      while((m = re.exec(text))){
        if(m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var mk = document.createElement('mark');
        mk.textContent = m[0];
        frag.appendChild(mk);
        last = m.index + m[0].length;
        if(m[0] === '') re.lastIndex++;
      }
      if(last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  function setCursor(i){
    if(cursor > -1 && shown[cursor]) shown[cursor].classList.remove('cur');
    cursor = i;
    if(cursor > -1 && shown[cursor]){
      shown[cursor].classList.add('cur');
      shown[cursor].scrollIntoView({block:'center', behavior: reduced ? 'auto' : 'smooth'});
    }
  }

  function run(){
    var raw = q.value.trim(), term = raw.toLowerCase(), f = filter.value;
    var re = term ? new RegExp('(' + escRe(raw) + ')', 'gi') : null;

    shown = []; cursor = -1;

    items.forEach(function(el){
      el.innerHTML = orig.get(el);
      el.classList.remove('cur');
      var hit = (!term || (el.dataset.s || '').indexOf(term) !== -1);
      if(hit && f === 'link' && el.dataset.l !== '1') hit = false;
      if(hit && f === 'star' && el.dataset.star !== '1') hit = false;
      el.classList.toggle('hidden', !hit);
      if(hit){
        shown.push(el);
        if(re) paint(el, re);
      }
    });

    var filtering = term !== '' || f !== 'all';
    groups.forEach(function(g, i){
      if(!filtering){ g.open = savedOpen[i]; return; }
      g.open = true;
    });

    var visible = shown.length;
    sections.forEach(function(s){
      s.classList.toggle('hidden', !s.querySelector('.item:not(.hidden)'));
    });
    groups.forEach(function(g){
      g.classList.toggle('hidden', filtering && !g.querySelector('.item:not(.hidden)'));
    });

    empty.classList.toggle('show', filtering && visible === 0);
    box.classList.toggle('has', raw !== '');
    count.textContent = filtering
      ? visible + ' / ' + items.length
      : items.length + ' 条';

    var allOpen = groups.every(function(g){ return g.open || g.classList.contains('hidden'); });
    toggleAll.textContent = allOpen ? '折叠' : '全部展开';
    spy();
  }

  /* ---- 折叠 / 展开全部 ---- */
  toggleAll.addEventListener('click', function(){
    var anyClosed = groups.some(function(g){
      return !g.open && !g.classList.contains('hidden');
    });
    groups.forEach(function(g){ if(!g.classList.contains('hidden')) g.open = anyClosed; });
    savedOpen = groups.map(function(g){ return g.open; });
    this.textContent = anyClosed ? '折叠' : '全部展开';
  });

  /* ---- 搜索 ---- */
  var t;
  q.addEventListener('input', function(){ clearTimeout(t); t = setTimeout(run, 90); });
  clr.addEventListener('click', function(){ q.value = ''; run(); q.focus(); });
  filter.addEventListener('change', function(){ run(); });

  document.addEventListener('keydown', function(e){
    var typing = document.activeElement === q;
    if(e.key === '/' && !typing){ e.preventDefault(); q.focus(); q.select(); return; }
    if(e.key === 'Escape' && typing){ q.value = ''; run(); q.blur(); return; }
    if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){
      if(!shown.length) return;
      e.preventDefault();
      if(!typing) q.focus();
      var next = e.key === 'ArrowDown' ? cursor + 1 : cursor - 1;
      if(next < 0) next = shown.length - 1;
      if(next >= shown.length) next = 0;
      setCursor(next);
      return;
    }
    if(e.key === 'Enter' && cursor > -1 && shown[cursor]){
      var a = shown[cursor].querySelector('a.nm') ||
              shown[cursor].querySelector('.ds a') ||
              shown[cursor].querySelector('ul.sub a');
      if(a){ e.preventDefault(); window.open(a.href, '_blank', 'noopener'); }
    }
  });

  /* ---- 主题 ---- */
  var themeBtn = document.getElementById('theme'),
      modes = ['auto', 'light', 'dark'],
      label = {auto:'自动', light:'浅色', dark:'深色'};
  var saved = null;
  try{ saved = localStorage.getItem('uppjs-theme'); }catch(e){}
  saved = label[saved] ? saved : 'auto';
  document.documentElement.setAttribute('data-theme', saved);
  themeBtn.textContent = label[saved];
  themeBtn.addEventListener('click', function(){
    var cur = document.documentElement.getAttribute('data-theme') || 'auto';
    var next = modes[(modes.indexOf(cur) + 1) % modes.length];
    document.documentElement.setAttribute('data-theme', next);
    themeBtn.textContent = label[next];
    try{ localStorage.setItem('uppjs-theme', next); }catch(e){}
    spy();
  });

  /* ---- 顶栏高度 -> CSS 变量，供 sticky 定位 ---- */
  var header = document.querySelector('header');
  function measure(){
    document.documentElement.style.setProperty('--hh', header.offsetHeight + 'px');
  }

  /* ---- 滚动高亮目录 ---- */
  var ticking = false;
  function spy(){
    if(ticking) return;
    ticking = true;
    requestAnimationFrame(function(){
      ticking = false;
      var line = header.offsetHeight + 20, cur = null, i, el, top;
      for(i = 0; i < spyTargets.length; i++){
        el = spyTargets[i];
        if(el.classList.contains('hidden')) continue;
        top = el.getBoundingClientRect().top;
        if(top <= line) cur = el; else break;
      }
      if(!cur) cur = spyTargets[0];
      var id = cur ? cur.id : null;
      tocLinks.forEach(function(a){ a.classList.toggle('on', a.dataset.t === id); });
    });
  }

  /* ---- 目录跳转：展开目标分组 + 闪一下提示 ---- */
  function goTo(el){
    if(!el) return;
    if(el.tagName === 'DETAILS' && !el.open){
      el.open = true;
      savedOpen = groups.map(function(g){ return g.open; });
    }
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
    setTimeout(function(){ el.classList.remove('flash'); }, 1300);
  }
  document.querySelectorAll('.toc a[data-t], nav.cats a').forEach(function(a){
    a.addEventListener('click', function(){
      var id = (a.dataset.t || a.getAttribute('href').slice(1));
      goTo(document.getElementById(id));
      var s = document.querySelector('nav.cats .wrap');
      if(s) [].slice.call(s.children).forEach(function(x){
        x.classList.toggle('on', x === a);
      });
    });
  });
  window.addEventListener('hashchange', function(){
    if(location.hash) goTo(document.getElementById(location.hash.slice(1)));
  });

  /* ---- 回到顶部 ---- */
  var top = document.getElementById('totop');
  window.addEventListener('scroll', function(){
    top.classList.toggle('show', window.scrollY > 500);
    spy();
  }, {passive:true});
  top.addEventListener('click', function(){ window.scrollTo({top:0, behavior:'smooth'}); });

  window.addEventListener('resize', function(){ measure(); spy(); });
  measure();
  run();
  if(location.hash) goTo(document.getElementById(location.hash.slice(1)));
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# 4. 使用说明.md -> 使用说明.html（同一份内容，两个格式）
# --------------------------------------------------------------------------

HELP_SRC = ROOT / "使用说明.md"
HELP_OUT = ROOT / "使用说明.html"


def md_to_html(md: str) -> str:
    """说明文档用的 Markdown 子集 -> HTML。
    支持 h1-h4、段落、有序/无序列表、表格、代码块、引用、分隔线、
    粗体、行内代码、[文字](url)、<自动链接>。"""
    lines = md.split("\n")
    n = len(lines)
    out = []
    i = 0

    def inline(s: str) -> str:
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"&lt;(https?://[^\s&]+)&gt;",
                   r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                   r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', s)
        return s

    while i < n:
        line = lines[i]

        # 代码块
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + esc("\n".join(buf)) + "</code></pre>")
            continue

        # 分隔线
        if re.match(r"^-{3,}\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            lv = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lv, inline(m.group(2)), lv))
            i += 1
            continue

        # 表格
        if line.strip().startswith("|") and i + 1 < n \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += ["<th>" + inline(c) + "</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join("<td>" + inline(c) + "</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # 引用
        if line.startswith("> "):
            buf = []
            while i < n and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(x) for x in buf) + "</blockquote>")
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", line):
            buf = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                buf.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                i += 1
            out.append("<ol>" + "".join("<li>" + inline(x) + "</li>" for x in buf) + "</ol>")
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", line):
            buf = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                buf.append(re.sub(r"^[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join("<li>" + inline(x) + "</li>" for x in buf) + "</ul>")
            continue

        if not line.strip():
            i += 1
            continue

        # 段落
        buf = []
        while i < n and lines[i].strip() \
                and not re.match(r"^(#{1,4}\s|[-*]\s|\d+\.\s|>\s|```|-{3,}\s*$)", lines[i]):
            buf.append(lines[i])
            i += 1
        if not buf:
            buf = [lines[i]]
            i += 1
        out.append("<p>" + inline(" ".join(x.strip() for x in buf)) + "</p>")

    return "\n".join(out)


HELP_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>使用说明 · uppjs.com 维护手册</title>
<style>
:root{
  --bg:#fbfbf9; --card:#fff; --fg:#1c1c1a; --fg2:#565650; --fg3:#8e8e86;
  --line:#e4e4de; --accent:#a8681f; --soft:#f4f3ee; --code:#f2f1ea;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#141413; --card:#1c1c1a; --fg:#eceae4; --fg2:#b2b0a7; --fg3:#85837b;
    --line:#302f2c; --accent:#d9a05c; --soft:#232320; --code:#25241f;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
       "Microsoft YaHei",sans-serif;
}
article{max-width:800px; margin:0 auto; padding:40px 24px 80px}
h1{font-size:26px; line-height:1.4; margin:0 0 6px; letter-spacing:-.01em}
h2{font-size:19px; margin:38px 0 12px; padding-bottom:8px; border-bottom:1px solid var(--line)}
h3{font-size:16px; margin:26px 0 8px}
h4{font-size:15px; margin:20px 0 6px}
p{margin:10px 0}
a{color:var(--accent); text-decoration:none; border-bottom:1px solid var(--line)}
a:hover{border-bottom-color:var(--accent)}
hr{border:0; border-top:1px solid var(--line); margin:34px 0}
ul,ol{margin:10px 0; padding-left:24px}
li{margin:5px 0}
code{
  background:var(--code); border:1px solid var(--line); border-radius:4px;
  padding:1px 5px; font-size:13.5px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
pre{
  background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; overflow-x:auto; margin:14px 0;
}
pre code{background:none; border:0; padding:0; font-size:13.5px; line-height:1.65}
blockquote{
  margin:14px 0; padding:10px 16px; background:var(--soft);
  border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
}
blockquote p{margin:0}
table{border-collapse:collapse; width:100%; margin:16px 0; font-size:14px}
th,td{border:1px solid var(--line); padding:8px 12px; text-align:left; vertical-align:top}
th{background:var(--soft); font-weight:600}
tbody tr:nth-child(even){background:var(--soft)}
.back{
  display:inline-block; margin-bottom:22px; font-size:13.5px; color:var(--fg3);
  border-bottom:0;
}
.back:hover{color:var(--accent)}
@media (max-width:640px){
  article{padding:26px 16px 60px}
  h1{font-size:21px}
  h2{font-size:17px}
  table,thead,tbody,tr,th,td{display:block; width:100%}
  thead{display:none}
  table{margin:14px 0}
  tr{
    border:1px solid var(--line); border-radius:10px; margin:0 0 10px;
    padding:9px 13px; background:var(--card);
  }
  tbody tr:nth-child(even){background:var(--card)}
  td{border:0; padding:3px 0; font-size:13.5px; color:var(--fg2)}
  td:first-child{
    font-weight:600; color:var(--fg); font-size:14.5px; padding-bottom:5px;
    word-break:break-all;
  }
  pre{font-size:12.5px}
  blockquote{padding:9px 13px}
}
@media print{
  body{background:#fff; color:#000}
  .back{display:none}
  a{color:#000}
  h2{page-break-after:avoid}
  table,pre,blockquote{page-break-inside:avoid}
}
</style>
</head>
<body>
<article>
<a class="back" href="./">← 回到 uppjs.com</a>
__BODY__
</article>
</body>
</html>
"""


def build_help_html() -> str:
    md = HELP_SRC.read_text(encoding="utf-8")
    # 去掉开头的 H1，模板里已有语义（避免和 .back 挤在一起时重复感）
    return HELP_TEMPLATE.replace("__BODY__", md_to_html(md))


def git_date() -> str:
    import subprocess
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    from datetime import date
    return date.today().isoformat()


def main():
    text = SRC.read_text(encoding="utf-8")
    blocks = parse_lines(text)
    cats = build_tree(blocks)

    if "--dump" in sys.argv:
        print(json.dumps(cats, ensure_ascii=False, indent=1))
        return

    html_out = render(cats, git_date())
    OUT.write_text(html_out, encoding="utf-8")
    n = len(re.findall(r'<div class="[^"]*\bitem\b[^"]*" data-s=', html_out))
    links = len(re.findall(r'href="https?://', html_out))
    groups = len(re.findall(r'<details class="group', html_out))
    print(f"已生成 {OUT.name}：{len(cats)} 个分类 / {groups} 个分组 / {n} 个条目 / "
          f"{links} 个外链 / {len(html_out)//1024} KB")

    # 说明书的 HTML 版，跟着一起更新，保证 md / html 两个版本永远同步
    # 另存一份英文名 help.html，方便在手机上直接输入网址访问
    if HELP_SRC.exists():
        help_out = build_help_html()
        HELP_OUT.write_text(help_out, encoding="utf-8")
        (ROOT / "help.html").write_text(help_out, encoding="utf-8")
        print(f"已生成 {HELP_OUT.name} 与 help.html：{len(help_out)//1024} KB")


if __name__ == "__main__":
    main()
