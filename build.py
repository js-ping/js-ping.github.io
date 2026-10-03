#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py —— 把 markdown 内容源编译成一套零依赖的静态站点

用法：
    python3 build.py            # 生成首页 + 所有清单页 + 说明书
    python3 build.py --dump     # 只打印解析后的结构（JSON），用于校对内容有无丢失

产出：
    index.html    首页（导航，软件清单放最显眼的位置）
    apps.html     软件清单      <- README.md
    links.html    网址书签      <- links.md（由「同步书签.py」从 Chrome 书签自动生成）
    help.html     使用说明      <- 使用说明.md（同时产出「使用说明.html」）
    lottery.html  彩票选号工具   <- 独立单文件，不参与本脚本编译

设计原则：
    1. 内容源是 markdown，改内容只改源文件，然后重跑本脚本。
    2. 每个页面都是单文件、零依赖、离线可用，数据全部内联。
    3. 想加一个新清单页：往下面的 LIST_PAGES 里加一条即可，其余全自动。
"""

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "README.md"
OUT = ROOT / "index.html"

# ==========================================================================
# 【站点配置】—— 想改站名、开关功能，只改这一段
# ==========================================================================

SITE = "https://uppjs.com"
SITE_NAME = "uppjs.com"
SITE_SUB = "软件与网址清单"
SITE_DESC = ("自己在用的 Mac / PC / 手机软件、硬件和常用网址，整理成清单长期更新，支持即时搜索。"
             "不接推广、不做商业排序，收录标准只有一条：用得住。")
THEME_COLOR = "#2f6fed"

# 页面清单：想加一个新页面，往这里加一条就行。
#   src    —— 内容源（markdown 文件）
#   out    —— 生成的 html
#   layout —— "list" 普通清单 / "compact" 紧凑链接（书签页用）
LIST_PAGES = [
    dict(src="README.md", out="apps.html", kicker="Mac · Windows · 手机 · 外设",
         title="软件清单",
         sub="我自己在用的软件、硬件和外设，长期更新。收录标准只有一条：用得住。",
         layout="list"),
    dict(src="links.md", out="links.html", kicker="在线工具 · 资源站 · 常用站",
         title="网址书签",
         sub="从浏览器书签里整理出来的常用网址，按用途分好类，一个搜索框全都能搜到。",
         layout="compact"),
]

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


SLD2 = {"com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "co.uk",
        "com.hk", "com.tw", "co.jp", "com.au", "co.kr", "com.sg"}

# 这些字段以前是条目下面的「规格行」，现在一律不显示
META_DROP = {"免费", "开源", "平台", "价格", "验证", "官网", "替代", "坑"}


def host_of(url: str) -> str:
    """从链接里取主机名：https://chat.deepseek.com/x -> chat.deepseek.com"""
    m = re.match(r"https?://([^/?#]+)", url or "", re.I)
    if not m:
        return ""
    h = m.group(1).lower().split("@")[-1].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def reg_domain(h: str) -> str:
    """取可注册域名：chat.deepseek.com -> deepseek.com；a.com.cn -> a.com.cn"""
    p = [x for x in (h or "").split(".") if x]
    if len(p) <= 2:
        return ".".join(p)
    if ".".join(p[-2:]) in SLD2:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def drop_meta(nodes):
    """删掉残留的规格行（免费：是 / 平台：Win ...），老内容里可能还留着。"""
    kept = []
    for x in nodes:
        drop_meta(x["children"])
        if (not x["has_link"] and not x["children"]
                and x["title"].strip() in META_DROP):
            continue
        kept.append(x)
    return kept


def extract_star(title: str):
    """只认「☆ 名字」这一种标记：☆ 抽出来做成「荐」徽章，名字保持原样。
    括号里的备注（如「（开源）」「(6.25 版本)」）不再拆成小色块，原样留在名字里，
    这样页面上不会冒出一堆看不懂的标签。"""
    return "☆" in title, re.sub(r"\s{2,}", " ", title.replace("☆", "")).strip(" ·-—")


# 名称与简述之间：中英文冒号、逗号、顿号、句号都当分隔符，统一处理
DESC_SEP_RE = re.compile(r"^[\s：:，,、。.；;]+")
TAIL_PUNCT = "。.．；;，,、 "


def make_node(text: str, is_bullet: bool = True):
    dep = "~~" in text
    bare = text.replace("~~", "").strip()
    node = {
        "title": bare,
        "url": "",
        "desc": "",
        "note": "",
        "tags": [],
        "children": [],
        "dep": dep,
        "star": False,
        "has_link": False,
        "bullet": is_bullet,
    }

    m = LINK_RE.match(bare)
    if m and m.start() == 0:
        node["url"] = m.group(2)
        node["has_link"] = True
        node["title"] = m.group(1)
        # 链接后面不管是「：」「，」还是直接接字，都当简述
        node["desc"] = DESC_SEP_RE.sub("", bare[m.end():], count=1).strip()
    else:
        # 先把行内链接整体遮起来，免得 URL 里的 "https:" 被当成标题/描述分隔符
        masked, store = mask_links(bare)
        parts = re.split(r"[：:]", masked, maxsplit=1)
        if len(parts) == 2 and parts[0].strip():
            node["title"] = unmask(parts[0], store).strip()
            node["desc"] = unmask(parts[1], store).strip()
        else:
            node["title"] = bare

    # 「简述 ｜ 点评」：全角竖线后面是个人使用感受，页面上单独一行
    for sep in ("｜", "|"):
        if sep in node["desc"]:
            a, b = node["desc"].split(sep, 1)
            node["desc"], node["note"] = a.strip(), b.strip()
            break

    node["star"], node["title"] = extract_star(node["title"])
    node["host"] = host_of(node["url"])

    node["title"] = re.sub(r"[。.．]+$", "", node["title"]).rstrip("：:").strip()
    # 简述与点评去掉句尾标点，整页看起来才齐整
    node["desc"] = node["desc"].strip().rstrip(TAIL_PUNCT).strip()
    node["note"] = node["note"].strip().rstrip(TAIL_PUNCT).strip()
    node["header"] = bare.endswith(("：", ":")) and not node["desc"] and not node["url"]
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
        c["children"] = drop_meta(c["children"])
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
        is_dep = bool(node.get("dep")) or any(h in node["title"] for h in DEP_GROUP_HINTS)
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
        full = esc(plain(node["title"]))
        title_html = (
            f'<a class="nm" href="{esc(node["url"])}" target="_blank" '
            f'rel="noopener noreferrer" title="{full}">{title_html}</a>'
        )
    else:
        title_html = f'<span class="nm">{title_html}</span>'

    # 只有一个徽章：清单里写了 ☆ 的条目，名称右边挂一个「荐」
    chips_html = ('<span class="chips">'
                  '<span class="badge" title="个人推荐">荐</span></span>') \
        if node["star"] else ""

    host_html = ""
    if ctx.get("host") and node.get("host"):
        rd = reg_domain(node["host"])
        if rd not in ctx.get("host_hide", ()):
            host_html = (f'<span class="dm" title="{esc(node["host"])}">'
                         f'{esc(rd)}</span>')

    desc_html = f'<span class="ds">{md_inline(node["desc"])}</span>' if node["desc"] else ""
    note_html = f'<span class="note">{md_inline(node["note"])}</span>' if node["note"] else ""

    sub = ""
    if kids:
        sub = '<ul class="sub">' + "".join(
            f"<li>{render_item_inline(k)}</li>" for k in kids
        ) + "</ul>"

    search = plain(" ".join(
        [node["title"], node["desc"], node["note"], node.get("host", "")]
        + [plain(k["title"] + k["desc"]) for k in kids]
    ))
    flags = f' data-s="{esc(search.lower())}"'
    if node["url"]:
        flags += ' data-l="1"'
    if node["star"]:
        flags += ' data-star="1"'
    return (
        f'<div class="{" ".join(cls)}"{flags}>'
        f'{title_html}{chips_html}{host_html}{desc_html}{note_html}{sub}</div>'
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


def render(cats, cfg: dict, updated: str) -> str:
    """把解析好的分类树渲染成一整页 HTML。cfg 的字段见 LIST_PAGES。"""
    show_host = cfg.get("layout") == "compact"
    ctx = {"g": 0, "host": show_host, "host_hide": ()}

    # 先数一遍域名：满页都是的（github / csdn / 知乎…）不显示，免得刷屏
    if show_host:
        freq = {}

        def _count(ns):
            for x in ns:
                if x["children"] and not x["has_link"]:
                    _count(x["children"])
                elif x.get("host"):
                    rd = reg_domain(x["host"])
                    freq[rd] = freq.get(rd, 0) + 1

        for c in cats:
            _count(c["children"])
        ctx["host_hide"] = set(k for k, v in freq.items() if v >= 5)

    body, toc_cats = [], []

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

    # 窄屏顶部的分类横条
    nav = "".join(
        f'<a href="#{cid}">{esc(ct)}<span class="n">{n}</span></a>'
        for cid, ct, n, _ in toc_cats
    )

    # 宽屏左侧的两级目录
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

    page = (TEMPLATE
            .replace("__NAV__", nav)
            .replace("__TOC__", "\n".join(toc))
            .replace("__BODY__", "\n".join(body))
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__SKIN_SCRIPT__", SKIN_SCRIPT)
            .replace("__SKIN_PANEL_CSS__", SKIN_PANEL_CSS)
            .replace("__SKIN_PANEL_HTML__", SKIN_PANEL_HTML)
            .replace("__SKIN_PANEL_JS__", SKIN_PANEL_JS))
    page = fill_page(page, cfg).replace("__UPDATED__", esc(updated))

    # 计数直接从成品里数，保证页脚、顶栏、JS 三处口径一致
    total = len(re.findall(r'<div class="[^"]*\bitem\b[^"]*" data-s=', page))
    links = len(re.findall(r'href="https?://', page))
    return page.replace("__TOTAL__", str(total)).replace("__LINKS__", str(links))


def fill_page(page: str, cfg: dict) -> str:
    """把页面级文案填进模板。所有清单页共用同一套骨架，靠这里区分。"""
    canon = SITE + "/" + cfg["out"]
    return (page
            .replace("__LAYOUT__", cfg["layout"])
            .replace("__THEME_COLOR__", THEME_COLOR)
            .replace("__PAGE_TITLE__", esc(cfg["title"] + " · " + SITE_NAME))
            .replace("__PAGE_DESC__", esc(cfg["title"] + "：" + cfg["sub"]))
            .replace("__CANON__", esc(canon))
            .replace("__KICKER__", esc(cfg["kicker"]))
            .replace("__H1__", esc(cfg["title"]))
            .replace("__SUB__", esc(cfg["sub"]))
            .replace("__SRC__", esc(cfg["src"])))


# 下面两块被首页和所有清单页共用，改一次全站都变。
THEME_CSS = r""":root{
  --bg:#f6f7f9; --panel:#ffffff; --panel2:#f0f2f5; --line:#e2e5ea;
  --fg:#1b1f24; --fg2:#5b626b; --fg3:#767e89;
  --accent:#2f6fed; --accent-soft:#e8efff; --mark:#ffe9a8; --mark-fg:#3a2c00;
  --tag-attr-fg:#2c7554; --tag-attr-bg:#eef7f2; --tag-attr-bd:#cfe7dc;
  --tag-plat-fg:#2f6fed; --tag-plat-bg:#eef3ff; --tag-plat-bd:#d3e0fb;
  --warn:#bc5a33; --warn-fav:#c9971a;
  --radius:10px; --hh:57px; --tocw:206px;
}
html[data-theme="dark"]{
  --bg:#14161a; --panel:#1c1f24; --panel2:#22262c; --line:#2e333a;
  --fg:#e6e8ec; --fg2:#a8b0ba; --fg3:#7c848e;
  --accent:#6ea0ff; --accent-soft:#22314f; --mark:#6b5a1a; --mark-fg:#ffeaa0;
  --tag-attr-fg:#7fd3ae; --tag-attr-bg:#1b2a24; --tag-attr-bd:#2c4a3d;
  --tag-plat-fg:#8fb6ff; --tag-plat-bg:#1a2135; --tag-plat-bd:#2d3f63;
  --warn:#e08a63; --warn-fav:#e3b53c;
}
@media (prefers-color-scheme: dark){
  html[data-theme="auto"]{
    --bg:#14161a; --panel:#1c1f24; --panel2:#22262c; --line:#2e333a;
    --fg:#e6e8ec; --fg2:#a8b0ba; --fg3:#7c848e;
    --accent:#6ea0ff; --accent-soft:#22314f; --mark:#6b5a1a; --mark-fg:#ffeaa0;
    --tag-attr-fg:#7fd3ae; --tag-attr-bg:#1b2a24; --tag-attr-bd:#2c4a3d;
    --tag-plat-fg:#8fb6ff; --tag-plat-bg:#1a2135; --tag-plat-bd:#2d3f63;
    --warn:#e08a63; --warn-fav:#e3b53c;
  }
}"""


SKIN_SCRIPT = r"""<script>
/* 外观：明暗 + 底色。在首帧前应用，避免闪烁；设置只存在本机浏览器。 */
(function(){
  var VARS = ['--bg','--panel','--panel2','--line','--fg','--fg2','--fg3','--accent','--accent-soft'];
  function rgb(h){
    h = String(h || '').replace('#','');
    if(h.length === 3) h = h.charAt(0)+h.charAt(0)+h.charAt(1)+h.charAt(1)+h.charAt(2)+h.charAt(2);
    if(!/^[0-9a-fA-F]{6}$/.test(h)) return null;
    return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
  }
  function hex(c){
    var o = '#';
    for(var i = 0; i < 3; i++) o += ('0' + Math.max(0, Math.min(255, Math.round(c[i]))).toString(16)).slice(-2);
    return o;
  }
  function mix(a, b, t){
    var A = rgb(a), B = rgb(b);
    if(!A) return a;
    if(!B) return b;
    return hex([0,1,2].map(function(i){ return A[i] + (B[i] - A[i]) * t; }));
  }
  function lum(h){
    var c = rgb(h);
    if(!c) return 1;
    return (0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]) / 255;
  }
  function clear(){
    var st = document.documentElement.style;
    for(var i = 0; i < VARS.length; i++) st.removeProperty(VARS[i]);
  }
  function paint(bg){
    if(!rgb(bg)) return true;
    var W = '#ffffff', K = '#000000', L = lum(bg), light = L >= 0.45, st = document.documentElement.style;
    var t = light
      ? {panel: L > 0.93 ? '#ffffff' : mix(bg, W, .72), panel2: mix(bg, K, .05),
         line: mix(bg, K, .12), fg: mix(bg, K, .84), fg2: mix(bg, K, .57), fg3: mix(bg, K, .45),
         accent: '#2f6fed', soft: '#e8efff'}
      : {panel: mix(bg, W, .06), panel2: mix(bg, W, .11), line: mix(bg, W, .18),
         fg: mix(bg, W, .88), fg2: mix(bg, W, .64), fg3: mix(bg, W, .50),
         accent: '#6ea0ff', soft: mix(bg, '#2f6fed', .28)};
    st.setProperty('--bg', bg);
    st.setProperty('--panel', t.panel);
    st.setProperty('--panel2', t.panel2);
    st.setProperty('--line', t.line);
    st.setProperty('--fg', t.fg);
    st.setProperty('--fg2', t.fg2);
    st.setProperty('--fg3', t.fg3);
    st.setProperty('--accent', t.accent);
    st.setProperty('--accent-soft', t.soft);
    return light;
  }
  var SKIN = {
    modes: ['auto', 'light', 'dark'],
    label: {auto: '跟随系统', light: '浅色', dark: '深色'},
    presets: [
      {name: '默认', bg: ''},
      {name: '云白', bg: '#ffffff'},
      {name: '暖阳', bg: '#f7efd9'},
      {name: '护眼', bg: '#e6f1e1'},
      {name: '石青', bg: '#e5eef8'},
      {name: '藕荷', bg: '#f8eaef'},
      {name: '午夜蓝', bg: '#182233'},
      {name: '纯黑', bg: '#000000'}
    ],
    read: function(){
      try{ return JSON.parse(localStorage.getItem('uppjs-appearance') || 'null') || {}; }
      catch(e){ return {}; }
    },
    paint: paint,
    apply: function(s){
      var d = document.documentElement;
      if(s && s.bg){
        d.setAttribute('data-theme', paint(s.bg) ? 'light' : 'dark');
      }else{
        clear();
        d.setAttribute('data-theme', (s && s.mode) || 'auto');
      }
      return s;
    },
    save: function(s){
      try{ localStorage.setItem('uppjs-appearance', JSON.stringify(s)); }catch(e){}
    }
  };
  window.UPPJS_SKIN = SKIN;
  var s = SKIN.read();
  if(s.bg || s.mode === 'light' || s.mode === 'dark') SKIN.apply(s);
})();
</script>"""


SKIN_PANEL_CSS = r"""/* ---------- 外观面板（明暗 + 底色） ---------- */
.appear{position:relative}
.appear>button{
  border:1px solid var(--line); background:var(--panel); color:var(--fg2);
  border-radius:8px; padding:5px 11px; font-size:13px; cursor:pointer;
  font-family:inherit; line-height:1.4;
}
.appear>button:hover{color:var(--fg); border-color:var(--fg3)}
.ap-panel{
  position:absolute; right:0; top:calc(100% + 9px); z-index:70; width:268px;
  background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:13px 13px 11px; text-align:left; white-space:normal;
  box-shadow:0 14px 38px rgba(0,0,0,.20);
}
.ap-panel[hidden]{display:none}
.ap-lab{
  font-size:10.5px; letter-spacing:.1em; color:var(--fg3); text-transform:uppercase;
  margin:0 0 7px; font-weight:600;
}
.ap-modes{display:flex; gap:6px; margin:0 0 13px}
.ap-modes button{
  flex:1; border:1px solid var(--line); background:var(--panel2); color:var(--fg2);
  border-radius:8px; padding:6px 0; font-size:12.5px; cursor:pointer;
  font-family:inherit; white-space:nowrap;
}
.ap-modes button.on{border-color:var(--accent); background:var(--accent-soft); color:var(--accent); font-weight:600}
.ap-sw{display:grid; grid-template-columns:repeat(4,1fr); gap:7px; margin:0 0 13px}
.ap-sw button{
  width:100%; height:32px; border-radius:9px; border:1px solid var(--line);
  cursor:pointer; padding:0;
}
.ap-sw button.on{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}
.ap-foot{display:flex; gap:6px; border-top:1px solid var(--line); padding-top:11px}
.ap-foot button{
  flex:1; border:1px solid var(--line); background:transparent; color:var(--fg2);
  border-radius:8px; padding:6px 0; font-size:12.5px; cursor:pointer; font-family:inherit;
}
.ap-foot button:hover{color:var(--fg); background:var(--panel2)}
.ap-tip{font-size:11.5px; color:var(--fg3); line-height:1.55; margin:10px 0 0}
#apPick{position:absolute; width:0; height:0; opacity:0; pointer-events:none; border:0; padding:0}"""


SKIN_PANEL_HTML = r"""      <div class="appear">
        <button id="theme" title="外观：明暗与底色" aria-haspopup="dialog" aria-expanded="false">外观</button>
        <div class="ap-panel" id="apPanel" hidden>
          <p class="ap-lab">明暗</p>
          <div class="ap-modes" id="apModes"></div>
          <p class="ap-lab">底色</p>
          <div class="ap-sw" id="apSw"></div>
          <div class="ap-foot">
            <button id="apCustom" title="用取色器自选一个底色">自定义…</button>
            <button id="apReset" title="恢复默认外观">恢复默认</button>
          </div>
          <p class="ap-tip">选「底色」后明暗会自动适配，文字颜色跟着变，不用担心看不清。设置只保存在你自己的浏览器里。</p>
          <input type="color" id="apPick" value="#f6f7f9" tabindex="-1" aria-hidden="true">
        </div>
      </div>"""


SKIN_PANEL_JS = r"""  /* ---- 外观：明暗 + 底色 ---- */
  var SK = window.UPPJS_SKIN;
  if(SK){
    var themeBtn = document.getElementById('theme'),
        apPanel = document.getElementById('apPanel'),
        apModes = document.getElementById('apModes'),
        apSw = document.getElementById('apSw'),
        apReset = document.getElementById('apReset'),
        apCustom = document.getElementById('apCustom'),
        apPick = document.getElementById('apPick'),
        look = SK.read();
    if(typeof look.bg !== 'string') look.bg = '';
    if(!look.mode) look.mode = 'auto';

    function syncSkin(){
      [].forEach.call(apModes.children, function(b){
        b.classList.toggle('on', b.dataset.mode === look.mode);
      });
      [].forEach.call(apSw.children, function(b){
        b.classList.toggle('on', (b.dataset.bg || '') === look.bg);
      });
    }
    function useSkin(){
      SK.apply(look);
      SK.save(look);
      syncSkin();
      if(window.UPPJS_REMEASURE) window.UPPJS_REMEASURE();
    }
    function closeSkin(){
      apPanel.hidden = true;
      themeBtn.setAttribute('aria-expanded', 'false');
    }

    SK.modes.forEach(function(m){
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.mode = m;
      b.textContent = SK.label[m];
      b.addEventListener('click', function(){
        look.mode = m;
        look.bg = '';
        useSkin();
      });
      apModes.appendChild(b);
    });

    SK.presets.forEach(function(p){
      var b = document.createElement('button');
      b.type = 'button';
      b.dataset.bg = p.bg;
      b.title = '底色：' + p.name;
      b.setAttribute('aria-label', '底色：' + p.name);
      b.style.background = p.bg || 'linear-gradient(135deg,#fff 0 50%,#16181c 50% 100%)';
      b.addEventListener('click', function(){
        look.bg = p.bg;
        look.mode = p.bg ? (SK.paint(p.bg) ? 'light' : 'dark') : 'auto';
        useSkin();
      });
      apSw.appendChild(b);
    });

    apCustom.addEventListener('click', function(e){
      e.stopPropagation();
      apPick.click();
    });
    apPick.addEventListener('input', function(){
      look.bg = apPick.value;
      look.mode = SK.paint(apPick.value) ? 'light' : 'dark';
      useSkin();
    });
    apReset.addEventListener('click', function(){
      look = {mode: 'auto', bg: ''};
      useSkin();
    });

    themeBtn.addEventListener('click', function(e){
      e.stopPropagation();
      if(window.UPPJS_CLOSE_OTHERS) window.UPPJS_CLOSE_OTHERS();   // 面板互斥
      apPanel.hidden = !apPanel.hidden;
      themeBtn.setAttribute('aria-expanded', apPanel.hidden ? 'false' : 'true');
    });
    apPanel.addEventListener('click', function(e){ e.stopPropagation(); });
    document.addEventListener('click', function(){
      if(!apPanel.hidden) closeSkin();
      if(window.UPPJS_CLOSE_OTHERS) window.UPPJS_CLOSE_OTHERS();
    });
    document.addEventListener('keydown', function(e){
      if(e.key === 'Escape' && !apPanel.hidden) closeSkin();
    });
    syncSkin();
  }
"""


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PAGE_TITLE__</title>
<meta name="description" content="__PAGE_DESC__">
<meta name="theme-color" content="__THEME_COLOR__">
<link rel="canonical" href="__CANON__">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<meta property="og:type" content="website">
<meta property="og:url" content="__CANON__">
<meta property="og:title" content="__PAGE_TITLE__">
<meta property="og:description" content="__PAGE_DESC__">
<style>
__THEME_CSS__
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
.tools>button,.tools>select,.tools>a.tool-link{
  border:1px solid var(--line); background:var(--panel); color:var(--fg2);
  padding:6px 9px; border-radius:8px; cursor:pointer; font-size:13px; max-width:150px;
  white-space:nowrap;
}
.tools>button:hover,.tools>select:hover,.tools>a.tool-link:hover{
  border-color:var(--accent); color:var(--accent); text-decoration:none;
}
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
  padding:6px 8px 6px 12px; border-left:2px solid var(--line); margin:2px 0;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:5px 9px;
  border-radius:0 5px 5px 0;
}
.item:hover{border-left-color:var(--accent); background:var(--panel2)}
.item .nm{font-weight:600; color:var(--fg); font-size:14.5px; flex:0 1 auto; min-width:0}
.item a.nm{color:var(--accent)}
.item a.nm:hover{text-decoration:underline}
.item .chips{display:inline-flex; align-items:center; gap:4px; flex:0 0 auto}
.item .ds{color:var(--fg2); font-size:13px; flex:1 1 280px; min-width:0}
.item .note{
  flex:1 1 100%; color:var(--fg3); font-size:12.5px; line-height:1.6;
  padding-left:9px; border-left:2px solid var(--line);
}
.item .note::before{content:"▸ "; color:var(--fg3)}
.item.dep .nm{text-decoration:line-through; color:var(--fg3)}
.item.dep .ds{color:var(--fg3); text-decoration:line-through}
.item.cur{background:var(--accent-soft); border-left-color:var(--accent)}
ul.sub{margin:4px 0 2px 0; padding-left:16px; color:var(--fg2); font-size:13px; width:100%}
ul.sub li{margin:2px 0}
mark{background:var(--mark); color:var(--mark-fg); border-radius:2px; padding:0 1px}

@keyframes flash{from{background:var(--accent-soft)} to{background:transparent}}
.flash{animation:flash 1.2s ease-out}

.hidden{display:none !important}
.empty{display:none; text-align:center; color:var(--fg3); padding:44px 0; font-size:13.5px}
.empty.show{display:block}
.empty b{color:var(--fg2)}

/* ---------- 页头 ---------- */
.pagehead{margin:0 0 20px}
.pagehead .kicker{
  font-size:11.5px; letter-spacing:.1em; color:var(--accent);
  margin:0 0 5px; text-transform:uppercase;
}
.pagehead h1{font-size:23px; margin:0 0 7px; letter-spacing:-.01em}
.pagehead .sub{color:var(--fg2); font-size:13.5px; margin:0; max-width:660px}
a.brand{color:var(--fg)}
a.brand:hover{color:var(--accent); text-decoration:none}

/* ---------- 紧凑布局：网址书签页 ---------- */
body[data-layout="compact"] .sec-body{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(296px,1fr));
  gap:12px; align-items:start;
}
body[data-layout="compact"] details.group{
  border:1px solid var(--line); border-radius:10px; background:var(--panel);
  padding:11px 13px 12px;
}
body[data-layout="compact"] details.group>summary{
  padding:0 0 8px; margin:0 0 5px; font-size:13px; font-weight:600;
  border-bottom:1px solid var(--line); color:var(--fg);
}
body[data-layout="compact"] details.group>summary .grp-n{
  color:var(--fg3); font-weight:400; font-size:11.5px;
}
body[data-layout="compact"] .grp-body{padding-left:0; margin-left:0}
body[data-layout="compact"] .item{
  padding:3px 7px; margin:0 -7px; border-left:0; border-radius:6px;
  gap:0 9px; font-size:13.5px; line-height:1.55;
}
body[data-layout="compact"] .item:hover{background:var(--panel2); border-left-color:transparent}
body[data-layout="compact"] .item .nm{
  flex:1 1 auto; min-width:0; font-weight:400; font-size:13.5px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
body[data-layout="compact"] .item a.nm{color:var(--fg)}
body[data-layout="compact"] .item a.nm:hover{color:var(--accent); text-decoration:none}
/* 右侧的来源域名：不抢眼，但一眼能看出是哪个站 */
body[data-layout="compact"] .item .dm{
  flex:0 0 auto; max-width:40%; font-size:10.5px; color:var(--fg3); opacity:.7;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
body[data-layout="compact"] .item:hover .dm{opacity:1}
body[data-layout="compact"] .item .ds{flex:1 1 100%; font-size:11.8px; color:var(--fg3)}
body[data-layout="compact"] .item ul.sub{flex:1 1 100%; font-size:12.5px}
body[data-layout="compact"] .sec-body > .item{grid-column:1/-1}
/* 窄屏：单列，别让卡片被内容撑出去 */
body[data-layout="compact"] details.group,
body[data-layout="compact"] .sec-body > .item{min-width:0}
@media (max-width:720px){
  body[data-layout="compact"] .sec-body{grid-template-columns:minmax(0,1fr)}
  body[data-layout="compact"] .item .nm{white-space:normal}
}

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

__SKIN_PANEL_CSS__

@media (max-width:720px){
  .bar{padding:8px 12px; gap:8px}
  .brand span{display:none}
  .brand{font-size:14px}
  /* 窄屏按钮多，工具区独占一行并允许换行，避免顶栏横向溢出 */
  .tools{gap:6px; flex-wrap:wrap; white-space:normal; width:100%; justify-content:flex-start}
  .tools>button,.tools>select,.tools>a.tool-link{padding:6px 8px; font-size:12.5px}
  .appear>button{padding:6px 8px; font-size:12.5px}
  .ap-panel{position:fixed; top:calc(var(--hh) + 6px); right:12px; left:auto;
            width:min(276px,calc(100vw - 24px))}
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
__SKIN_SCRIPT__
</head>
<body id="top" data-layout="__LAYOUT__">

<header>
  <div class="bar">
    <a class="brand" href="index.html">uppjs.com<span>__KICKER__</span></a>
    <div class="search" id="searchbox">
      <input id="q" type="search" placeholder="搜索名称 / 说明，按 / 聚焦、↑↓ 选择" autocomplete="off">
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
      <a class="tool-link" href="index.html" title="回到首页">首页</a>
__SKIN_PANEL_HTML__
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
    <div class="pagehead">
      <p class="kicker">__KICKER__</p>
      <h1>__H1__</h1>
      <p class="sub">__SUB__</p>
    </div>
    <div class="empty" id="empty">
      没有匹配的条目。<br><b>试试更短的关键词</b>，或把筛选切回「全部」。
    </div>
__BODY__

    <details class="help" id="help">
      <summary>这一页怎么用 / 关于本站</summary>
      <h3>这是什么</h3>
      <p>我自己在用的东西整理成的一份清单，长期更新。收录标准只有一条：
         <strong>我真的在用、而且用得住</strong>。不接推广、不做商业排序。</p>
      <h3>最常用的三个动作</h3>
      <table>
        <tr><th>动作</th><th>怎么做</th></tr>
        <tr><td>找东西</td><td>顶栏搜索框直接打字，名称、说明、子条目全文都能搜到，
            <strong>大小写无所谓，中文英文都行</strong></td></tr>
        <tr><td>只看某一类</td><td>点左侧目录（手机上点顶部分类条）跳到分类；点分组标题可以折叠/展开</td></tr>
        <tr><td>换配色</td><td>右上角「外观」——明暗三档 + 8 种底色 + 自定义取色</td></tr>
      </table>
      <h3>键盘快捷键</h3>
      <table>
        <tr><td><kbd>/</kbd></td><td>跳到搜索框</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>清空搜索</td></tr>
        <tr><td><kbd>↑</kbd> <kbd>↓</kbd></td><td>在搜索结果之间移动</td></tr>
        <tr><td><kbd>Enter</kbd></td><td>打开选中的那一条</td></tr>
      </table>
      <h3>搜索的小细节</h3>
      <p>搜索时所有分组会自动展开，没命中的分组会收起来，
         分组标题右边的数字会变成<strong>「命中数 / 总数」</strong>。
         试试搜 <code>截图</code>、<code>下载</code>、<code>pdf</code>、<code>heic</code>。</p>
      <p>右上角的筛选可以和搜索叠加用：<strong>有下载链接</strong>只看能直接点开的，
         <strong>我推荐的</strong>只看我标了 ☆ 的。</p>
      <h3>内容怎么更新</h3>
      <p>本页由仓库里的 <code>__SRC__</code> 自动生成，改内容只改那一个文件，不用碰这个页面的代码。
         具体步骤见<a href="help.html">使用说明</a>。</p>
      <h3>数据与隐私</h3>
      <ul>
        <li>纯静态页面：没有后端、没有数据库、没有统计脚本、不请求任何第三方 CDN。</li>
        <li>本地存储只有一项——你的外观偏好，不上传任何数据。</li>
        <li>页面上的链接都指向第三方站点，跳转之后的行为不受本站控制。</li>
      </ul>
      <h3>免责声明</h3>
      <p>清单是个人使用记录，链接来自公开网络，不保证长期有效，
         也不提供任何软件下载托管。软件版权归各自厂商所有，请通过正规渠道购买授权。</p>
    </details>
  </main>
</div>

<footer>
  <span>内容源 __SRC__ · 共 __TOTAL__ 条 · __LINKS__ 个外链 · 更新于 __UPDATED__</span>
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
  // 记住每个分组的原始条目数，搜索时改显示「命中 / 总数」
  groups.forEach(function(g){
    var n = g.querySelector('summary .grp-n');
    if(n) n.dataset.n = n.textContent;
  });

  // 筛选：函数式，想加新筛选往这里加一行就行
  var FILTERS = {
    link: function(el){ return el.dataset.l === '1'; },
    star: function(el){ return el.dataset.star === '1'; }
  };

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
      if(hit && FILTERS[f] && !FILTERS[f](el)) hit = false;
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
      var hit = g.querySelectorAll('.item:not(.hidden)').length;
      var n = g.querySelector('summary .grp-n');
      if(n) n.textContent = filtering ? hit + ' / ' + n.dataset.n : n.dataset.n;
      g.classList.toggle('hidden', filtering && hit === 0);
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

  // 供共用组件（外观面板）回调，避免组件之间硬耦合
  window.UPPJS_REMEASURE = function(){ measure(); };

__SKIN_PANEL_JS__


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
  // 从首页带 ?view=link / ?view=star 过来时，直接切到对应筛选
  var want = (location.search.match(/[?&]view=(link|star)\b/) || [])[1];
  if(want && filter.querySelector('[value="' + want + '"]')){
    filter.value = want;
    run();
  }
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# 4. 导航页 hub.html（工具台）
#    所有模块都在这张表里。想加一个模块：往 HUB_MODULES 里加一行。
#    st="live" 可点击 / st="plan" 显示「规划中」占位（灰色不可点）
# --------------------------------------------------------------------------
# 4. 首页 index.html（导航）
#    首页只干一件事：把「软件清单」顶到最显眼的位置，其余页面依次排开。
#    想加一个入口：往 OTHER_PAGES 里加一行；想加一个预告：往 PLANNED 里加一行。
#    页面上的所有数字都是从生成好的页面里数出来的，不写死。
# --------------------------------------------------------------------------

OTHER_PAGES = [
    ("网址书签", "链", "links.html",
     "我自己常开的网站和在线工具，按用途分好类。一个搜索框全都能搜到。"),
    ("彩票选号", "彩", "lottery.html",
     "双色球、大乐透随机选号与购票核对，附历史开奖走势图。纯离线单文件，不联网。"),
    ("使用说明", "问", "help.html",
     "网站怎么用、内容怎么写、出问题怎么办。零技术基础也能看懂，手机上直接打开。"),
]

PLANNED = [
    ("文章归档", "▦", "公众号写过的长文按主题归档，比在公众号里翻历史清楚得多。"),
    ("书单 / 影单", "▥", "看过的书和片子，带一句短评。"),
    ("备考资料", "▧", "一建相关的笔记索引、错题和资料清单。"),
    ("拼音搜索", "拼", "打 wyyy 就能搜到「网易云」，不用来回切输入法。"),
    ("条目对比", "⇄", "把几条并排比参数，选哪个一目了然。"),
    ("失效链接体检", "检", "定期跑一遍外链，把 404 的挑出来。清单最怕的不是少，而是过期。"),
]


def build_home(pages: dict, updated: str) -> str:
    """pages: {out 文件名: {"items":…, "links":…, "groups":…, "cats":[(id, 标题, 条数)]}}"""
    apps = pages.get("apps.html", {})
    bm = pages.get("links.html", {})
    apps_cats = apps.get("cats", [])
    bm_cats = bm.get("cats", [])

    # —— 主角：软件清单 ——
    chips = "".join(
        f'<a class="chip" href="apps.html#{cid}">{esc(ct)}<span>{n}</span></a>'
        for cid, ct, n in apps_cats[:8]
    )
    feature = f"""  <section class="feature">
    <div class="f-head">
      <span class="ico">▤</span>
      <div class="f-txt">
        <h2>软件清单</h2>
        <p>Mac / PC / 手机软件、硬件与外设。收录标准只有一条：<strong>我真的在用、而且用得住</strong>。</p>
      </div>
      <a class="f-go" href="apps.html">打开清单 →</a>
    </div>
    <div class="f-facts">
      <span><b>{apps.get("items", 0)}</b> 条收录</span>
      <span><b>{apps.get("groups", 0)}</b> 个分组</span>
      <span><b>{len(apps_cats)}</b> 个分类</span>
    </div>
    <div class="f-chips">{chips}</div>
    <div class="f-quickrow">
      <a href="apps.html?view=star">★ 我推荐的</a>
      <a href="apps.html?view=link">有下载链接的</a>
    </div>
  </section>"""

    # —— 其它页面 ——
    cards = []
    for t, ico, href, d in OTHER_PAGES:
        tag = ""
        if href == "links.html":
            tag = f'<span class="tag">{bm.get("items", 0)} 条</span>'
            d = f"{len(bm_cats)} 个分类，" + d
        cards.append(f'<a class="card" href="{href}">{tag}'
                     f'<span class="ico">{ico}</span><h3>{esc(t)}</h3>'
                     f'<p>{esc(d)}</p></a>')

    plan = "".join(
        f'<div class="card plan"><span class="ico">{ico}</span>'
        f'<h3>{esc(t)}<span class="st">规划中</span></h3><p>{esc(d)}</p></div>'
        for t, ico, d in PLANNED
    )

    total = sum(x.get("items", 0) for x in pages.values())
    n_plan = len(PLANNED)

    return (HOME_TEMPLATE
            .replace("__FEATURE__", feature)
            .replace("__CARDS__", "\n      ".join(cards))
            .replace("__PLANNED__", plan)
            .replace("__N_ALL__", str(total))
            .replace("__N_PLAN__", str(n_plan))
            .replace("__UPDATED__", esc(updated))
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__SKIN_SCRIPT__", SKIN_SCRIPT)
            .replace("__SKIN_PANEL_CSS__", SKIN_PANEL_CSS)
            .replace("__SKIN_PANEL_HTML__", SKIN_PANEL_HTML)
            .replace("__SKIN_PANEL_JS__", SKIN_PANEL_JS)
            .replace("__SITE__", SITE)
            .replace("__SITE_NAME__", SITE_NAME)
            .replace("__THEME_COLOR__", THEME_COLOR)
            .replace("__SITE_DESC__", esc(SITE_DESC)))


HOME_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__SITE_NAME__ · 软件与网址清单</title>
<meta name="description" content="__SITE_DESC__">
<link rel="canonical" href="__SITE__/">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="__THEME_COLOR__">
<meta property="og:type" content="website">
<meta property="og:url" content="__SITE__/">
<meta property="og:title" content="__SITE_NAME__ · 软件与网址清单">
<meta property="og:description" content="__SITE_DESC__">
<style>
__THEME_CSS__
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;
}
a{color:var(--accent); text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:4px}

/* ---------- 顶栏 ---------- */
header{position:sticky; top:0; z-index:50; background:var(--bg); border-bottom:1px solid var(--line)}
@supports (backdrop-filter:blur(8px)){
  header{background:color-mix(in srgb,var(--bg) 86%,transparent); backdrop-filter:saturate(1.6) blur(10px)}
}
.bar{max-width:980px; margin:0 auto; padding:9px 16px; display:flex; align-items:center; gap:10px; flex-wrap:wrap}
.brand{font-weight:700; font-size:15px; white-space:nowrap; color:var(--fg)}
a.brand:hover{color:var(--accent); text-decoration:none}
.brand span{color:var(--fg3); font-weight:400; margin-left:6px; font-size:13px}
.nav-links{display:flex; gap:2px; margin-left:4px}
.nav-links a{color:var(--fg2); font-size:13px; padding:5px 9px; border-radius:7px; white-space:nowrap}
.nav-links a:hover{background:var(--panel2); color:var(--fg); text-decoration:none}
.tools{margin-left:auto; display:flex; align-items:center; gap:8px; white-space:nowrap}
__SKIN_PANEL_CSS__

/* ---------- 主体 ---------- */
main{max-width:980px; margin:0 auto; padding:30px 16px 56px}

/* 页头 */
.hero{margin:0 0 26px}
.hero .kicker{font-size:11.5px; letter-spacing:.1em; color:var(--accent); margin:0 0 6px; text-transform:uppercase}
.hero h1{font-size:30px; margin:0 0 10px; letter-spacing:-.02em}
.hero p{color:var(--fg2); margin:0 0 9px; font-size:14.5px; max-width:700px}
.hero .hint{color:var(--fg3); font-size:12.5px; margin:0}
.hero .hint b{color:var(--fg2)}

/* ---------- 主角：软件清单 ---------- */
.feature{
  border:1px solid var(--line); border-radius:14px; background:var(--panel);
  padding:20px 22px 18px; margin:0 0 30px;
}
.feature .f-head{display:flex; align-items:flex-start; gap:14px; flex-wrap:wrap}
.feature .ico{
  flex:none; display:flex; align-items:center; justify-content:center;
  width:40px; height:40px; border-radius:11px;
  background:var(--accent-soft); color:var(--accent); font-size:19px;
}
.feature .f-txt{flex:1 1 250px; min-width:0}
.feature h2{margin:0 0 5px; font-size:20px; letter-spacing:-.01em}
.feature p{margin:0; color:var(--fg2); font-size:13.5px; line-height:1.6; max-width:560px}
a.f-go{
  flex:none; margin-left:auto; align-self:center;
  background:var(--accent); color:#fff; font-weight:600; font-size:13.5px;
  padding:9px 16px; border-radius:9px; white-space:nowrap;
}
a.f-go:hover{text-decoration:none; filter:brightness(1.08)}
.feature .f-facts{
  display:flex; flex-wrap:wrap; gap:6px 20px;
  margin:15px 0 0; padding:13px 0 0; border-top:1px solid var(--line);
  color:var(--fg3); font-size:12.5px;
}
.feature .f-facts b{color:var(--fg); font-size:15px; font-weight:700; margin-right:4px}
.feature .f-chips{display:flex; flex-wrap:wrap; gap:7px; margin:13px 0 0}
.chip{
  display:inline-flex; align-items:center; gap:6px;
  border:1px solid var(--line); background:var(--bg); color:var(--fg2);
  border-radius:999px; padding:4px 11px; font-size:12.5px;
}
.chip:hover{border-color:var(--accent); color:var(--accent); text-decoration:none}
.chip span{color:var(--fg3); font-size:11.5px}
.feature .f-quickrow{display:flex; flex-wrap:wrap; gap:9px; margin:14px 0 0}
.feature .f-quickrow a{
  border:1px solid var(--line); background:var(--bg); color:var(--fg2);
  border-radius:8px; padding:6px 12px; font-size:12.8px;
}
.feature .f-quickrow a:hover{border-color:var(--accent); color:var(--accent); text-decoration:none}

/* ---------- 其它区块 ---------- */
section.block{margin-top:30px}
section.block>h2{
  font-size:12.5px; letter-spacing:.07em; color:var(--fg3); font-weight:600;
  margin:0 0 12px; display:flex; align-items:center; gap:8px; white-space:nowrap;
}
section.block>h2 .sub{font-weight:400; letter-spacing:0; font-size:12px}
section.block>h2::after{content:""; flex:1; height:1px; background:var(--line)}
.cards{display:grid; grid-template-columns:repeat(auto-fill,minmax(292px,1fr)); gap:12px}
.cards.wide{grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
.card{
  position:relative; display:block; color:var(--fg);
  background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:15px 16px 16px; transition:border-color .13s, transform .13s;
}
a.card:hover{border-color:var(--accent); text-decoration:none; transform:translateY(-1px)}
.card .ico{
  display:flex; align-items:center; justify-content:center;
  width:28px; height:28px; border-radius:8px; margin-bottom:9px;
  background:var(--panel2); color:var(--fg2); font-size:15px; line-height:1; font-weight:600;
}
a.card:hover .ico{background:var(--accent-soft); color:var(--accent)}
.card h3{margin:0 0 5px; font-size:14.5px; display:flex; align-items:center; gap:7px}
.card p{margin:0; color:var(--fg2); font-size:12.8px; line-height:1.62}
.card p strong{color:var(--fg)}
.card .st{
  font-size:10.5px; font-weight:600; color:var(--fg3);
  background:var(--panel2); border:1px solid var(--line); border-radius:4px; padding:1px 6px;
}
.card.plan{opacity:.62; cursor:default}
.card .tag{
  position:absolute; right:14px; top:15px;
  font-size:10.5px; color:var(--accent); background:var(--accent-soft);
  border-radius:4px; padding:1px 6px;
}

footer{
  max-width:980px; margin:0 auto; padding:0 16px 50px; color:var(--fg3); font-size:12.5px;
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;
}
@media (max-width:760px){
  .bar{padding:8px 12px}
  .brand span{display:none}
  .nav-links a{padding:5px 7px}
  main{padding:20px 12px 50px}
  .hero h1{font-size:25px}
  .feature{padding:17px 16px 16px}
  a.f-go{width:100%; text-align:center; margin-left:0; order:9}
  .cards{grid-template-columns:1fr}
  .card.plan{opacity:.75}
  .ap-panel{right:-8px; width:min(268px,calc(100vw - 26px))}
}
</style>
__SKIN_SCRIPT__
</head>
<body>

<header>
  <div class="bar">
    <a class="brand" href="index.html">__SITE_NAME__<span>个人清单站</span></a>
    <nav class="nav-links">
      <a href="apps.html">软件清单</a>
      <a href="links.html">网址书签</a>
      <a href="lottery.html">彩票选号</a>
      <a href="help.html">使用说明</a>
    </nav>
    <div class="tools">
__SKIN_PANEL_HTML__
    </div>
  </div>
</header>

<main>
  <div class="hero">
    <p class="kicker">个人清单站</p>
    <h1>__SITE_NAME__</h1>
    <p>自己在用的软件、硬件和网址，整理成清单长期更新。
       <strong>不接推广、不做商业排序</strong>，收录标准只有一条：用得住。</p>
    <p class="hint">全站 <b>__N_ALL__</b> 条 · 更新于 __UPDATED__</p>
  </div>

__FEATURE__

  <section class="block">
    <h2>还有这些</h2>
    <div class="cards wide">
      __CARDS__
    </div>
  </section>

  <section class="block">
    <h2>规划中<span class="sub">· 做好一个开一个</span></h2>
    <div class="cards">
      __PLANNED__
    </div>
  </section>
</main>

<footer>
  <span>纯静态 · 无后端 · 无统计脚本 · 无第三方请求</span>
  <span>内容源 README.md / links.md · 更新于 __UPDATED__</span>
</footer>

<script>
(function(){
  /* 外观面板的绑定逻辑（与清单页共用同一份，改一次两边都变） */
__SKIN_PANEL_JS__
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# 5. 使用说明.md -> 使用说明.html（同一份内容，两个格式）
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
<title>使用说明 · uppjs.com</title>
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
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
.topnav{display:flex; flex-wrap:wrap; gap:6px; margin:0 0 22px}
.topnav a{
  font-size:13px; color:var(--fg2); border:1px solid var(--line);
  border-radius:8px; padding:5px 11px; border-bottom:1px solid var(--line);
}
.topnav a:hover{color:var(--accent); border-color:var(--accent); text-decoration:none}
.topnav a.on{color:var(--accent); border-color:var(--accent); background:var(--soft)}
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
  .topnav{display:none}
  a{color:#000}
  h2{page-break-after:avoid}
  table,pre,blockquote{page-break-inside:avoid}
}
</style>
</head>
<body>
<article>
<a class="back" href="./">← 回到 uppjs.com 首页</a>
<nav class="topnav">
  <a href="./">首页</a>
  <a href="apps.html">软件清单</a>
  <a href="links.html">网址书签</a>
  <a class="on" href="help.html">使用说明</a>
</nav>
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


def build_manifest():
    """PWA manifest：加到手机主屏后全屏打开，像个 App。
    故意不做 Service Worker —— 离线缓存会让改完的内容迟迟不更新，
    对「改 README 就该立刻生效」的站来说得不偿失。"""
    data = {
        "name": f"{SITE_NAME} · {SITE_SUB}",
        "short_name": SITE_NAME.split(".")[0],
        "description": SITE_DESC,
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#f6f7f9",
        "theme_color": THEME_COLOR,
        "lang": "zh-CN",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }
    (ROOT / "manifest.webmanifest").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_seo(today: str):
    """生成 robots.txt 与 sitemap.xml，跟着每次更新一起产出，不用手动维护。"""
    (ROOT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE,
        encoding="utf-8")
    pages = [("", "1.0", "weekly"), ("apps.html", "0.9", "weekly"),
             ("links.html", "0.8", "weekly"), ("lottery.html", "0.6", "monthly"),
             ("help.html", "0.5", "monthly")]
    urls = "\n".join(
        "  <url><loc>%s/%s</loc><lastmod>%s</lastmod><changefreq>%s</changefreq>"
        "<priority>%s</priority></url>" % (SITE, p, today, cf, pr)
        for p, pr, cf in pages)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + urls + "\n</urlset>\n", encoding="utf-8")


def main():
    today = git_date()
    dump = "--dump" in sys.argv
    pages = {}

    for cfg in LIST_PAGES:
        src = ROOT / cfg["src"]
        if not src.exists():
            print("跳过 %s：文件不存在" % cfg["src"])
            continue
        cats = build_tree(parse_lines(src.read_text(encoding="utf-8")))
        if dump:
            print("=== %s ===" % cfg["src"])
            print(json.dumps(cats, ensure_ascii=False, indent=1))
            continue

        page = render(cats, cfg, today)
        out = ROOT / cfg["out"]
        out.write_text(page, encoding="utf-8")

        n = len(re.findall(r'<div class="[^"]*\bitem\b[^"]*" data-s=', page))
        links = len(re.findall(r'href="https?://', page))
        groups = len(re.findall(r'<details class="group', page))
        pages[cfg["out"]] = dict(
            items=n, links=links, groups=groups,
            cats=[(c["id"], c["title"], leaf_count(c["children"])) for c in cats],
        )
        print("已生成 %s：%d 个分类 / %d 个分组 / %d 个条目 / %d 个外链 / %d KB"
              % (out.name, len(cats), groups, n, links, len(page) // 1024))

    if dump:
        return

    home = build_home(pages, today)
    (ROOT / "index.html").write_text(home, encoding="utf-8")
    print("已生成 index.html（首页）：全站 %d 条 / %d 个页面 / %d KB"
          % (sum(x["items"] for x in pages.values()), len(pages), len(home) // 1024))

    # 说明书的 HTML 版，跟着一起更新，保证 md / html 两个版本永远同步
    # 另存一份英文名 help.html，方便在手机上直接输入网址访问
    if HELP_SRC.exists():
        help_out = build_help_html()
        HELP_OUT.write_text(help_out, encoding="utf-8")
        (ROOT / "help.html").write_text(help_out, encoding="utf-8")
        print("已生成 %s 与 help.html：%d KB" % (HELP_OUT.name, len(help_out) // 1024))

    build_seo(today)
    print("已生成 robots.txt 与 sitemap.xml")

    build_manifest()
    print("已生成 manifest.webmanifest")


if __name__ == "__main__":
    main()
