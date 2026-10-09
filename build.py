#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py —— 把 markdown 内容源编译成一套零依赖的静态站点

用法：
    python3 build.py            # 生成首页 + 所有清单页 + 说明书
    python3 build.py --dump     # 只打印解析后的结构（JSON），用于校对内容有无丢失
    python3 build.py --preview  # 只写「本地资料/预览/」，连空页也出一份，用来先看效果

产出（会自动上线）：
    index.html    首页（导航，软件与资源放最显眼的位置）
    apps.html     软件与资源      <- 内容源/软件与资源.md + free-region.json（地域标记）
                  原本的「软件清单」和「免费资源」两页已经并进这一份
    free.html     旧地址，自动跳到 apps.html（老链接不失效）
    lottery.html  彩票选号工具   <- 独立单文件，不参与本脚本编译

产出（上线开关关着，随时可开）：
    links.html    网址书签      <- 内容源/网址书签.md（由「同步书签.py」从 Chrome 书签自动生成）
                  → LIST_PAGES 里那一条的 enabled 改成 True 即恢复

目录约定：
    凡是 markdown 内容源，一律放「内容源/」，根目录不留 .md。
    这样根目录只剩「要发布的东西（.html）+ 双击就能用的东西（.command）」，
    打开文件夹不会一眼看到十几个 .md 分不清哪个是哪个。
    唯一的例外是根目录的 README.md —— 它是 GitHub 仓库首页会读的那一份，
    内容正文已移到「内容源/软件与资源.md」，根目录那份只是仓库说明，不参与编译。

产出（只在本机，不上线）：
    本地资料/使用说明.html     <- 本地资料/使用说明.md
    「本地资料/」整个目录在 .gitignore 里，既不提交也不发布。

设计原则：
    1. 内容源是 markdown，改内容只改源文件，然后重跑本脚本。
    2. 每个页面都是单文件、零依赖、离线可用，数据全部内联。
    3. 想加一个新清单页：往下面的 LIST_PAGES 里加一条即可，其余全自动。
    4. 想临时撤下一个页面：把那条的 enabled 改成 False，代码和内容都留着。
    5. 内容与「实测数据」分开：内容源/软件与资源.md 只写有哪些资源，链接好不好打开由
       「6-体检链接.command」实测后写进 free-region.json。机器管链接还活着吗，
       人管该不该收它 —— 两件事不要混在一份文件里。
    6. 平台标记只标「挑系统」的：不写就是多平台通用，写在方括号里（[Mac] [Win] [安卓]…），
       页面渲染成名称右边的小徽章。默认全标反而没人看。"""

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# 所有 markdown 内容源都放在这个子目录里，根目录只留 html 和脚本。
# 想加一个新清单页：把 .md 丢进 内容源/，再到下面 LIST_PAGES 里加一条。
SRC_DIR = ROOT / "内容源"

SRC = SRC_DIR / "软件与资源.md"
OUT = ROOT / "index.html"

# --------------------------------------------------------------------------
# 产物写到哪儿
#   正常跑        -> 仓库根目录。生成完就等着提交上线。
#   带 --preview  -> 「本地资料/预览/」，而且**连还没有内容的空页也出一份**，
#                    用来"先看看这一页长什么样，再决定要不要填内容"。
#   「本地资料/」整个目录在 .gitignore 里（既不提交也不发布），
#   所以预览永远不会覆盖线上文件，也永远不会被误推上去。
# --------------------------------------------------------------------------
OUT_DIR = ROOT
PREVIEW = "--preview" in sys.argv
PREVIEW_DIR = ROOT / "本地资料" / "预览"

# ==========================================================================
# 【站点配置】—— 想改站名、开关功能，只改这一段
# ==========================================================================

SITE = "https://uppjs.com"
SITE_NAME = "uppjs.com"
SITE_SUB = "软件与工具清单"
SITE_DESC = ("自己在用的 Mac / PC / 手机软件、硬件与外设，整理成清单长期更新，支持即时搜索。"
             "不接推广、不做商业排序，收录标准只有一条：用得住。")
THEME_COLOR = "#2f6fed"

# 分享图目录（og:image）。每页一张，文件名 = 页面名（如 og/apps.png）。
# 找不到就回落到 og/default.png。图片由「生成分享图.py」一次性生成，build 只负责引用。
OG_DIR = "og"
OG_DEFAULT = "og/default.png"

# 页面清单：想加一个新清单页，往这里加一条就行，导航 / 卡片 / sitemap / 搜索全部自动继承。
#   src     —— 内容源（markdown 文件）
#   out     —— 生成的 html
#   title   —— 页面标题，同时用作文档<title>、导航文字、首页卡片标题
#   layout  —— "list" 普通清单 / "compact" 紧凑链接（网址书签那种）
#   ico     —— 首页卡片上的一个字图标
#   home    —— 首页卡片上的一句话（省略时用 sub）
#   enabled —— True 生成 / False 下线（内容源与代码都留着）
#              "auto" = 内容源里还没有真条目时不上线，首页显示为「规划中」；
#                       你往源文件里填了内容，重跑 build.py 就自动上线。
LIST_PAGES = [
    # —— 软件与资源：原来「软件清单」+「免费资源」两页，2026-10-08 并成一页 ——
    #    输出的文件名仍是 apps.html，老外链和搜索引擎收录的地址不用改。
    #    旧地址 free.html 由下面的 REDIRECTS 自动跳过来，不会 404。
    #    regions=True 表示这一页会读 free-region.json，给条目挂「慢 / 需代理」标记，
    #    并在筛选下拉里多出「只看国内直连」。那份数据由「6-体检链接.command」实测生成。
    dict(src="内容源/软件与资源.md", out="apps.html", kicker="Mac · Windows · 手机 · 网页 · 外设",
         title="软件与资源", ico="▤",
         sub="我在用的软件、硬件与外设，加上整理过的合法免费资源：开源软件、官方免费版与学生包、"
             "免费课程、公共领域书籍、可商用素材。收录标准只有一条：用得住。"
             "不接推广、不做商业排序。",
         home="软件、硬件外设 + 合法免费资源，合成一份，带搜索和平台标记。",
         layout="list", regions=True),
    # —— 文章归档：把公众号长文搬进来，是目前唯一能带外部流量的模块 ——
    dict(src="内容源/文章归档.md", out="articles.html", kicker="公众号长文归档",
         title="文章归档", ico="▦",
         sub="写过的长文，按主题归档。比在平台里一条条翻历史清楚得多。",
         home="写过的长文按主题归档，能搜、能分类。",
         layout="list", enabled="auto"),
    # —— 书单 / 影单：字段与筛选完全不同，所以分成两个页面（共用同一套模板） ——
    dict(src="内容源/书单.md", out="books.html", kicker="读过的书",
         title="书单", ico="▥",
         sub="读过的书，带年份、评分和一句短评。",
         home="看过的书，带年份、评分和一句短评。",
         layout="list", enabled="auto"),
    dict(src="内容源/影单.md", out="movies.html", kicker="看过的片子",
         title="影单", ico="▤",
         sub="看过的电影和剧集，带年份、评分和一句短评。",
         home="看过的电影和剧集，带年份、评分和一句短评。",
         layout="list", enabled="auto"),
    # —— 「现在」（Now 页）：数字花园的标配 ——
    #    写清我最近在忙什么、在学什么，一个月更新一次。它不追热点，
    #    但它是全站唯一能看出「这个站还活着」的地方，也是主页「最近」那块的出处。
    # —— 「现在」（Now 页）已下线（2026-10-08，用户要求去掉）——
    #    页面撤下，内容源 内容源/现在.md 整个留着。
    #    想恢复：把 enabled 改成 True，重跑 build.py，再双击「2-更新网站.command」。
    dict(src="内容源/现在.md", out="now.html", kicker="最近在忙什么",
         title="现在", ico="今",
         sub="我最近在忙什么、在学什么、在看什么。一个月更新一次，不追热点，"
             "只记真的还在推进的事 —— 停了的就删掉，不装样子。",
         home="最近在忙什么，一个月更新一次。",
         layout="list", enabled=False),
    # —— 专题合集：按「场景」把软件重新打包 ——
    #    内容源里只写条目名（不写网址），构建时去「软件与资源」查真身把
    #    网址 / 简述 / 平台标记带过来 —— 只引用，不复制，一条内容不存两份。
    #    手写了链接的条目原样保留，方便临时塞一个清单外的东西。
    # —— 已下线（2026-10-09，用户要求去掉）——
    #    页面撤下，内容源 内容源/专题.md 与引用机制（build_item_index /
    #    enrich_pack / pack 开关）全部留着，一条没删。
    #    想恢复：把 enabled 改成 True，重跑 build.py，再双击「2-更新网站.command」。
    dict(src="内容源/专题.md", out="packs.html", kicker="按场景挑软件",
         title="专题合集", ico="合",
         sub="同一批软件，按场景重新打包：装新 Mac 该装什么、Windows 装机清单、"
             "写东西用的一套、给孩子留的。条目全部引用自「软件与资源」，"
             "改一处两边都变。",
         home="按场景重新打包的一批清单，条目全部引用自软件与资源，不存两份。",
         layout="list", pack=True, enabled=False),
    # —— 网址书签：目前下线（2026-10-04 起），页面撤下、接口留着 ——
    #    想恢复：把 enabled 改成 True，重跑 build.py，再双击「2-更新网站.command」。
    #    下线期间 links.md 仍由「同步书签.py」照常更新，内容一条都不会丢。
    dict(src="内容源/网址书签.md", out="links.html", kicker="在线工具 · 资源站 · 常用站",
         title="网址书签", ico="链",
         sub="从浏览器书签里整理出来的常用网址，按用途分好类，一个搜索框全都能搜到。",
         home="常开的网站和在线工具，按用途分好类。",
         layout="compact", enabled=False),
]

# 文档页：散文式排版（跟「使用说明」同一套版式），不走清单页的搜索/目录骨架。
#   src —— 内容源；out —— 产物；title —— 标题与导航文字
#   404.md 会被托管平台自动用于 404，所以它固定产出到根目录的 404.html。
DOC_PAGES = [
    dict(src="内容源/关于.md", out="about.html", title="关于",
         desc="这个站是什么、为什么要做、怎么做的。"),
    dict(src="内容源/隐私说明.md", out="privacy.html", title="隐私说明", nav=False,
         desc="不收集数据、不设 Cookie、不请求第三方——这个站的隐私说明。"),
    dict(src="内容源/404.md", out="404.html", title="页面走丢了",
         desc="这个地址没有内容。", nav=False, sitemap=False, noindex=True),
]

# 更新日志：从 git 提交记录自动生成（不手写、不会过期），最多取最近 N 条。
CHANGELOG_OUT = "changelog.html"
CHANGELOG_MAX = 40

# 非清单、非文档的独立页面（手写的单文件工具），只有一个就够用。
TOOL_PAGES = [
    dict(title="彩票选号", href="lottery.html", ico="彩", nav=True,
         desc="双色球、大乐透随机选号与购票核对，附历史开奖走势图。纯离线单文件，不联网。"),
]

# 旧地址跳转：页面合并、改名之后，原来的网址不能直接 404 ——
# 别人收藏的、搜索引擎收录的、公众号文章里贴过的老链接，都由这张表兜住。
# 产出的是一个几十行的静态跳转页，零依赖、离线也一样能跳。
REDIRECTS = [
    dict(out="free.html", to="apps.html",
         title="免费资源已经并进「软件与资源」"),
]

# --------------------------------------------------------------------------
# ★ v2 新增：外观源文件
#    theme/theme.css  —— 新的设计层（配色、卡片、hero、动效）
#    theme/theme.js   —— 顶栏滚动态 / 打字机 / 入场动效
#    构建时读进来「内联」到每个页面，产物依旧是单文件、零外部请求。
#    想调外观只改这两个文件，不用碰这个 py。
# --------------------------------------------------------------------------
THEME_DIR = ROOT / "theme"


def _read_theme(name: str) -> str:
    p = THEME_DIR / name
    if not p.exists():
        print("!! 没找到 %s，外观层会是空的" % p)
        return ""
    return p.read_text(encoding="utf-8")


# 护栏：这两个文件是「内联」进页面的，一旦正文里出现结束标签，
# 浏览器会当场把 style / script 关掉，剩下的 CSS 全部漏到页面上变成文字。
# 踩过一次（CSS 注释里写了「内联到 </style> 之前」），所以在这里硬拦一道。
UPGRADE_CSS = _read_theme("theme.css")
if "</style" in UPGRADE_CSS.lower():
    raise SystemExit("theme/theme.css 里出现了 </style —— 会在页面里提前闭合样式表，"
                     "把注释里的这个写法改掉（例如写成「样式表末尾」）")
_JS_SRC = _read_theme("theme.js")
if "</script" in _JS_SRC.lower():
    raise SystemExit("theme/theme.js 里出现了 </script —— 会在页面里提前闭合脚本块，"
                     "把注释里的这个写法改掉")
UPGRADE_JS = '<script>\n' + _JS_SRC + '</script>'


def sidecard_html(current_out: str) -> str:
    """清单页左侧栏顶部的站点名片。计数用占位符，渲染完再填。"""
    others = []
    for p in all_pages():
        if p["href"] == current_out or p["href"] not in LIVE:
            continue
        if not p.get("nav", True):
            continue
        others.append(f'<a href="{p["href"]}">{esc(p["title"])}</a>')
    if current_out != "index.html":
        others.insert(0, '<a href="index.html">首页</a>')
    return f"""<div class="sidecard">
      <div class="top">
        <span class="av">U</span>
        <span class="nm">uppjs.com<i>个人清单站</i></span>
      </div>
      <p class="sg">收录标准只有一条：<b>我真的在用、而且用得住</b>。不接推广、不做商业排序。</p>
      <div class="st">
        <div><b>__SC_ITEMS__</b><i>条收录</i></div>
        <div><b>__SC_CATS__</b><i>个分类</i></div>
        <div><b>__SC_GROUPS__</b><i>个分组</i></div>
      </div>
      <div class="lnk">{''.join(others[:3])}</div>
    </div>"""


# --------------------------------------------------------------------------
# 0. 页面登记表 —— 导航 / 首页卡片 / sitemap / 分享图 都从这里取
#    想加页面只改上面的 LIST_PAGES / DOC_PAGES / TOOL_PAGES，别的地方不用动。
# --------------------------------------------------------------------------

LIVE = set()  # build 时先算好「这次哪些页面真的会生成」，再开渲染


def all_pages():
    """按展示顺序返回所有页面的元信息。nav=False 的页面不出现在顶部导航里。"""
    out = []
    for cfg in LIST_PAGES:
        out.append(dict(title=cfg["title"], href=cfg["out"], ico=cfg.get("ico", "·"),
                        kind="list", nav=True, cfg=cfg))
    for t in TOOL_PAGES:
        out.append(dict(title=t["title"], href=t["href"], ico=t["ico"],
                        kind="tool", nav=t.get("nav", True), desc=t["desc"]))
    for cfg in DOC_PAGES:
        out.append(dict(title=cfg["title"], href=cfg["out"], ico="问",
                        kind="doc", nav=cfg.get("nav", True),
                        sitemap=cfg.get("sitemap", True), cfg=cfg))
    out.append(dict(title="更新日志", href=CHANGELOG_OUT, ico="记", kind="doc", nav=True))
    return out


def nav_html(current=None, base="", cls="topnav"):
    """统一导航：谁活着就出现谁，顺序由 all_pages() 决定。"""
    items = []
    for p in all_pages():
        if not p.get("nav", True) or p["href"] not in LIVE:
            continue
        on = ' class="on"' if p["href"] == current else ""
        items.append(f'<a{on} href="{base}{p["href"]}">{esc(p["title"])}</a>')
    return "\n  ".join(items)


# 品牌后面那句小字。整站统一成一句，不在页面之间换 ——
# 每一页自己的定位由页头那句 kicker 说明，不占用导航栏。
BRAND_TAGLINE = "个人清单站"


def site_header(current=None, tools="", base=""):
    """全站唯一的顶栏 —— 首页 / 清单页 / 文档页三个模板都调这一个函数。

    统一的三件事：品牌区（logo + 站名 + 一句小字）、导航链接（顺序与高亮）、
    右侧工具区（永远在最右边，外观按钮每页都有）。
    页面之间只差「右侧多放什么」：清单页多一个搜索框和筛选，其它页不占位。
    """
    return (
        '<header>\n'
        '  <div class="bar">\n'
        f'    <a class="brand" href="{base}index.html">'
        f'<span class="logo">U</span>{esc(SITE_NAME)}<em>{esc(BRAND_TAGLINE)}</em></a>\n'
        f'    <nav class="nav-links">{nav_html(current, base)}</nav>\n'
        f'    <div class="tools">{tools}{SKIN_PANEL_HTML}</div>\n'
        '  </div>\n'
        '</header>'
    )


# 清单页在顶栏右侧多出来的那一块：搜索框 + 计数 + 筛选 + 折叠。
# 放在这里而不是模板里，是为了让 site_header() 成为顶栏的唯一出题口。
LIST_TOOLS = r"""      <div class="search" id="searchbox">
        <input id="q" type="search" placeholder="搜索名称 / 说明，按 / 聚焦、↑↓ 选择" autocomplete="off">
        <button id="clr" title="清空">×</button>
      </div>
      <span id="count"></span>
      <select id="filter" title="筛选">
        <option value="all">全部</option>
        <option value="link">有下载链接</option>
        <option value="star">我推荐的</option>__REGION_OPT____PLAT_OPT__
      </select>
      <button id="toggleAll" title="展开 / 折叠全部分组">折叠</button>"""


def og_image(href):
    """每页一张分享图；命名按页面名，缺了就回落到默认那张。"""
    cand = f"{OG_DIR}/{href.rsplit('.', 1)[0]}.png"
    return cand if (ROOT / cand).exists() else OG_DEFAULT


def rss_link_tag():
    """有文章归档才有 RSS —— 不给订阅者一个 404 的订阅入口。"""
    if "articles.html" in LIVE:
        return ('<link rel="alternate" type="application/rss+xml" '
                'title="uppjs.com · 文章归档" href="feed.xml">')
    return ""


def footer_nav(current=None):
    """页脚的全站地图：每个页面都能走到其它页面，不至于进了子页就出不来。"""
    parts = []
    if current != "index.html":
        parts.append('<a href="index.html">首页</a>')
    for p in all_pages():
        if not p.get("nav", True) or p["href"] not in LIVE or p["href"] == current:
            continue
        parts.append(f'<a href="{p["href"]}">{esc(p["title"])}</a>')
    parts.append('<a href="privacy.html">隐私说明</a>')
    if "articles.html" in LIVE:
        parts.append('<a href="feed.xml">RSS</a>')
    # v2：不再用「 · 」串起来 —— 新页脚是竖排一列，每个链接独立成行。
    return "\n        ".join(parts)


def breadcrumb_html(current_href, current_title, base=""):
    """面包屑：不只是一行字，同时喂给下面 JSON-LD 里的 BreadcrumbList。"""
    if current_href == "index.html":
        return ""
    return ('<nav class="crumbs" aria-label="面包屑">'
            f'<a href="{base}index.html">首页</a>'
            '<span class="sep">›</span>'
            f'<span class="cur">{esc(current_title)}</span></nav>')


def breadcrumb_jsonld(current_href, current_title):
    if current_href == "index.html":
        return []
    return [{"@type": "ListItem", "position": 1, "name": "首页",
             "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": current_title,
             "item": f"{SITE}/{current_href}"}]


def jsonld_html(graph):
    if not graph:
        return ""
    data = {"@context": "https://schema.org", "@graph": graph}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def site_jsonld():
    """全站通用的一段：告诉搜索引擎这是谁的站、叫什么。"""
    return [
        {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/",
         "name": f"{SITE_NAME} · {SITE_SUB}", "description": SITE_DESC,
         "inLanguage": "zh-CN"},
        {"@type": "Person", "@id": SITE + "/#author", "name": SITE_NAME,
         "url": SITE + "/about.html",
         "description": "把在用的软件、工具和写法整理成清单，长期更新。"},
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
        if line.startswith("### "):
            # 「### 分组名」= 显式分组（长文归档、书单这类内容用它比缩进更清楚）
            blocks.append(("sub", 0, line[4:].strip()))
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


# --------------------------------------------------------------------------
# 平台标记 —— 只标「挑系统」的条目
#
#   在条目行里任意位置写一个方括号标记，解析时会被抽走，正文里不留痕迹：
#       - [IINA](https://iina.io/) [Mac]：macOS 最强播放器……
#       - Edge [Win]：感觉这个浏览器同步起来更方便一点……
#   不写 = 多平台通用，页面不显示徽章。整页都标反而没人看，只标限制项才有信息量。
#   别名可以随便写（macOS / macOS 版 / iPhone / Windows / PC / Android…），
#   统一归到「显示名」上；几个平台写几个方括号，顺序按下面的 PLAT_ORDER 排。
# --------------------------------------------------------------------------
PLAT_ALIAS = {
    "mac": "Mac", "macos": "Mac", "mac os": "Mac", "osx": "Mac", "苹果": "Mac",
    "win": "Win", "windows": "Win", "pc": "Win",
    "ios": "iOS", "iphone": "iOS", "ipad": "iOS",
    "android": "安卓", "安卓": "安卓",
    "web": "网页", "网页": "网页",
}
PLAT_ORDER = ["Mac", "Win", "安卓", "iOS", "网页"]
# data-p 用的小写键，给筛选下拉用
PLAT_KEY = {"Mac": "mac", "Win": "win", "安卓": "android", "iOS": "ios", "网页": "web"}
PLAT_TIP = {"Mac": "只有 Mac 版", "Win": "只有 Windows 版", "安卓": "只有安卓版",
            "iOS": "只有 iPhone / iPad 版", "网页": "网页版，浏览器直接打开"}
# 搜索时也认这些词，输入 windows / android 能搜到对应的条目
PLAT_WORDS = {"Mac": "mac macos 苹果", "Win": "win windows pc",
              "安卓": "安卓 android", "iOS": "ios iphone ipad", "网页": "网页 web 在线"}

_PLAT_KEYS = sorted(PLAT_ALIAS, key=len, reverse=True)
# 「[名字](网址)」是 markdown 链接，别被当成平台标记 —— 所以后面加个负向断言
PLAT_RE = re.compile(
    r"\[\s*(" + "|".join(re.escape(k) for k in _PLAT_KEYS) + r")\s*\](?!\s*\()", re.I)


def take_platforms(text: str):
    """抽出 [Mac] / [Win] 这类平台标记，返回 (清干净的文字, [显示名...])。"""
    found = []

    def _rep(m):
        val = PLAT_ALIAS.get(re.sub(r"\s+", " ", m.group(1).strip().lower()))
        if val and val not in found:
            found.append(val)
        return ""

    out = PLAT_RE.sub(_rep, text)
    if found:
        found.sort(key=lambda v: PLAT_ORDER.index(v) if v in PLAT_ORDER else 99)
        # 标记被摘掉后可能留下多余空格，顺手压一下（"[IINA](url) [Mac]：说明" -> "[IINA](url) ：说明"）
        out = re.sub(r"[ \t]{2,}", " ", out).rstrip()
    return out, found


# 名称与简述之间：中英文冒号、逗号、顿号、句号都当分隔符，统一处理
DESC_SEP_RE = re.compile(r"^[\s：:，,、。.；;]+")
TAIL_PUNCT = "。.．；;，,、 "


def make_node(text: str, is_bullet: bool = True):
    text, plats = take_platforms(text)
    dep = "~~" in text
    bare = text.replace("~~", "").strip()

    # ☆ 是「荐」标记，两种写法都要认：
    #   ☆ [名字](网址)   —— 写在链接前面
    #   [☆ 名字](网址)   —— 写在链接文字里（内容源里现存的就是这种）
    # 关键是要**先**把行首那个 ☆ 摘掉再认链接：否则「☆ 」会把行首顶开，
    # LINK_RE 匹配不上，url 就成了空、has_link 变假，
    # 「有下载链接」筛选、地域标记、域名统计会一起漏掉这一条。
    lead_star = bool(re.match(r"☆\s*", bare))
    if lead_star:
        bare = re.sub(r"^☆\s*", "", bare)

    node = {
        "title": bare,
        "url": "",
        "desc": "",
        "note": "",
        "tags": [],
        "plat": plats,
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
    node["star"] = node["star"] or lead_star
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
        if block[0] == "sub":
            # 显式分组：后面到下一个 ## / ### 之前的条目都归它
            content = block[2]
            node = {"title": content, "url": "", "desc": "", "note": "", "tags": [],
                    "plat": [], "children": [], "dep": False, "star": False, "has_link": False,
                    "bullet": False, "header": False, "host": "", "raw": content,
                    "indent": -1, "group": True}
            (cur_cat if cur_cat is not None else root)["children"].append(node)
            stack = [(-1, node)]
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


# 「国内访问情况」的两档标记。cn（国内直连）不出徽章 —— 那是默认的、多数条目的状态，
# 满页都挂反而看不见重点；但 data-r 照样输出，好让「只看国内直连」能筛。
REGION_LEGEND = {
    "slow": ("慢", "rg-slow", "国内能打开，但偶尔慢，时好时坏"),
    "proxy": ("需代理", "rg-bad", "国内基本打不开，要代理才能访问"),
}

# 实测数据文件：由「6-体检链接.command」生成，按网址索引 -> "cn" / "slow" / "proxy"
REGION_FILE = ROOT / "free-region.json"


def load_regions():
    """读地域标记数据。文件不存在或读坏了都返回空 -> 整页不加标记，绝不因此构建失败。"""
    if not REGION_FILE.exists():
        return {}
    try:
        raw = json.loads(REGION_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print("!! %s 读不了（%s），这次不加地域标记" % (REGION_FILE.name, e))
        return {}
    return raw.get("urls") or {}


def apply_regions(cats):
    """把地域标记挂到条目上（按网址匹配）。返回挂上了多少条。"""
    by_url = load_regions()
    if not by_url:
        return 0
    n = 0
    for _cat, node in iter_leaf_items(cats):
        r = by_url.get(node.get("url") or "")
        if r == "cn" or r in REGION_LEGEND:
            node["region"] = r
            n += 1
    return n


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

    # 名称右边的小徽章：写了 ☆ 的挂「荐」；标了平台的挂平台名；有实测地域数据的挂「慢 / 需代理」
    chips = []
    if node["star"]:
        chips.append('<span class="badge" title="个人推荐">荐</span>')
    for p in node.get("plat") or []:
        chips.append('<span class="plat plat-%s" title="%s">%s</span>'
                     % (PLAT_KEY.get(p, "x"), esc(PLAT_TIP.get(p, p)), esc(p)))
    rg = node.get("region")
    if rg in REGION_LEGEND:
        label, badge_cls, tip = REGION_LEGEND[rg]
        chips.append('<span class="rg %s" title="%s">%s</span>' % (badge_cls, esc(tip), label))
    chips_html = ('<span class="chips">' + "".join(chips) + '</span>') if chips else ""

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
        + [PLAT_WORDS.get(p, p) for p in (node.get("plat") or [])]
        + [plain(k["title"] + k["desc"]) for k in kids]
    ))
    flags = f' data-s="{esc(search.lower())}"'
    if node["url"]:
        flags += ' data-l="1"'
    if node["star"]:
        flags += ' data-star="1"'
    if node.get("plat"):
        flags += ' data-p="%s"' % " ".join(PLAT_KEY.get(p, "x") for p in node["plat"])
    if node.get("region"):
        flags += ' data-r="%s"' % node["region"]
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


def empty_state(cfg: dict) -> str:
    """还没填内容的清单页：不摆一片空白，说清这页会放什么、内容该写进哪个文件。

    正常上线时，enabled="auto" 的空页根本不会被生成，所以这段只在
    「--preview 预览」或手动把空页设成 True 时才会出现。"""
    return (
        '<div class="blank">'
        '<div class="ic">%s</div>'
        '<h3>「%s」还在整理中</h3>'
        '<p>%s</p>'
        '<p class="hint">位置已经留好了。往 <code>%s</code> 里填第一条，重跑一次就会出现在这里。</p>'
        '</div>'
        % (esc(cfg.get("ico", "▤")), esc(cfg["title"]), esc(cfg["sub"]), esc(cfg["src"]))
    )


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

    # 一条条目都没有：给个像样的空状态，而不是一片空白
    if not body:
        body.append(empty_state(cfg))

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
            .replace("__SITE_HEADER__", site_header(cfg["out"]))
            .replace("__NAV__", nav)
            .replace("__TOOLS__", LIST_TOOLS)
            .replace("__TOC__", "\n".join(toc))
            .replace("__BODY__", "\n".join(body))
            .replace("__SIDECARD__", sidecard_html(cfg["out"]))
            .replace("__SC_ITEMS__", str(sum(leaf_count(c["children"]) for c in cats)))
            .replace("__SC_CATS__", str(len(cats)))
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__UPGRADE_CSS__", UPGRADE_CSS)
            .replace("__UPGRADE_JS__", UPGRADE_JS)
            .replace("__SKIN_SCRIPT__", SKIN_SCRIPT)
            .replace("__SKIN_PANEL_CSS__", SKIN_PANEL_CSS)
            .replace("__SKIN_PANEL_HTML__", SKIN_PANEL_HTML)
            .replace("__SKIN_PANEL_JS__", SKIN_PANEL_JS))
    page = fill_page(page, cfg).replace("__UPDATED__", esc(updated))

    # 计数直接从成品里数，保证页脚、顶栏、JS 三处口径一致
    total = len(re.findall(r'<div class="[^"]*\bitem\b[^"]*" data-s=', page))
    links = len(re.findall(r'href="https?://', page))
    groups = len(re.findall(r'<details class="group', page))
    return (page.replace("__TOTAL__", str(total))
                .replace("__LINKS__", str(links))
                .replace("__SC_GROUPS__", str(groups)))


def fill_page(page: str, cfg: dict) -> str:
    """把页面级文案填进模板。所有清单页共用同一套骨架，靠这里区分。"""
    canon = SITE + "/" + cfg["out"]
    og = og_image(cfg["out"])
    graph = site_jsonld() + [
        {"@type": "CollectionPage", "@id": canon + "#page", "url": canon,
         "name": cfg["title"], "description": cfg["sub"], "inLanguage": "zh-CN",
         "isPartOf": {"@id": SITE + "/#website"},
         "author": {"@id": SITE + "/#author"}},
        {"@type": "BreadcrumbList",
         "itemListElement": breadcrumb_jsonld(cfg["out"], cfg["title"])},
    ]
    rss = rss_link_tag()
    # 「只看国内直连」只给挂了地域数据的页面（regions=True），别的页面不多一个筛不动项的选项
    region_opt = ('\n        <option value="cn">只看国内直连</option>'
                  if cfg.get("regions") else "")
    # 「只有 XX 版」按页面里真实存在的平台标记来加 —— 这一页没标平台，就不多出空选项
    present = set()
    for m in re.finditer(r'data-p="([^"]*)"', page):
        present.update(m.group(1).split())
    plat_opt = "".join(
        '\n        <option value="p%s">%s</option>' % (key, label)
        for key, label in (("mac", "只有 Mac 版"), ("win", "只有 Windows 版"),
                           ("android", "只有安卓版"), ("ios", "只有 iPhone / iPad 版"),
                           ("web", "网页版"))
        if key in present)
    return (page
            .replace("__REGION_OPT__", region_opt)
            .replace("__PLAT_OPT__", plat_opt)
            .replace("__LAYOUT__", cfg["layout"])
            .replace("__BODYCLS__", "packpage" if cfg.get("pack") else "")
            .replace("__THEME_COLOR__", THEME_COLOR)
            .replace("__PAGE_TITLE__", esc(cfg["title"] + " · " + SITE_NAME))
            .replace("__PAGE_DESC__", esc(cfg["title"] + "：" + cfg["sub"]))
            .replace("__CANON__", esc(canon))
            .replace("__KICKER__", esc(cfg["kicker"]))
            .replace("__H1__", esc(cfg["title"]))
            .replace("__SUB__", esc(cfg["sub"]))
            .replace("__SRC__", esc(cfg["src"]))
            .replace("__OG_IMAGE__", esc(SITE + "/" + og))
            .replace("__JSONLD__", jsonld_html(graph))
            .replace("__RSS_LINK__", rss)
            .replace("__NAVFOOT__", footer_nav(cfg["out"]))
            .replace("__CRUMB__", breadcrumb_html(cfg["out"], cfg["title"]))
            .replace("__NAVTOP__", nav_html(cfg["out"])))


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
  border-radius:var(--r-xs); padding:5px 11px; font-size:13px; cursor:pointer;
  font-family:inherit; line-height:1.4;
}
.appear>button:hover{color:var(--fg); border-color:var(--fg3)}
.ap-panel{
  position:absolute; right:0; top:calc(100% + 9px); z-index:70; width:268px;
  background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
  padding:13px 13px 11px; text-align:left; white-space:normal;
  box-shadow:var(--sh3);   /* 浮层专用那一档：亮色大投影、暗色带内高光 */
}
.ap-panel[hidden]{display:none}
.ap-lab{
  font-size:10.5px; letter-spacing:.1em; color:var(--fg3); text-transform:uppercase;
  margin:0 0 7px; font-weight:600;
}
.ap-modes{display:flex; gap:6px; margin:0 0 13px}
.ap-modes button{
  flex:1; border:1px solid var(--line); background:var(--panel2); color:var(--fg2);
  border-radius:var(--r-xs); padding:6px 0; font-size:12.5px; cursor:pointer;
  font-family:inherit; white-space:nowrap;
}
.ap-modes button.on{border-color:var(--accent); background:var(--accent-soft); color:var(--accent); font-weight:600}
.ap-sw{display:grid; grid-template-columns:repeat(4,1fr); gap:7px; margin:0 0 13px}
.ap-sw button{
  width:100%; height:32px; border-radius:var(--r-xs); border:1px solid var(--line);
  cursor:pointer; padding:0;
}
.ap-sw button.on{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}
.ap-foot{display:flex; gap:6px; border-top:1px solid var(--line); padding-top:11px}
.ap-foot button{
  flex:1; border:1px solid var(--line); background:transparent; color:var(--fg2);
  border-radius:var(--r-xs); padding:6px 0; font-size:12.5px; cursor:pointer; font-family:inherit;
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
<script>document.documentElement.className+=" js";</script>
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
<meta property="og:site_name" content="uppjs.com">
<meta property="og:url" content="__CANON__">
<meta property="og:title" content="__PAGE_TITLE__">
<meta property="og:description" content="__PAGE_DESC__">
<meta property="og:image" content="__OG_IMAGE__">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="__PAGE_TITLE__">
<meta name="twitter:card" content="summary_large_image">
__RSS_LINK__
__JSONLD__
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
code{background:var(--panel2); padding:1px 5px; border-radius:var(--r-xs); font-size:12.5px;
     font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--r-xs)}

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
.search{flex:1 1 240px; min-width:150px; position:relative}
.search input{
  width:100%; padding:8px 30px 8px 32px; border:1px solid var(--line); border-radius:var(--radius);
  background:var(--panel); color:var(--fg); font-size:14px; outline:none;
}
.search input:focus{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft)}
.search::before{content:"⌕"; position:absolute; left:11px; top:7px; color:var(--fg3); font-size:15px}
.search button{
  position:absolute; right:4px; top:4px; border:0; background:transparent; color:var(--fg3);
  font-size:16px; cursor:pointer; padding:4px 8px; border-radius:var(--r-sm); display:none;
}
.search.has button{display:block}
.tools{display:flex; align-items:center; gap:8px; font-size:13px; color:var(--fg3); white-space:nowrap}
.tools>button,.tools>select,.tools>a.tool-link{
  border:1px solid var(--line); background:var(--panel); color:var(--fg2);
  padding:6px 9px; border-radius:var(--r-sm); cursor:pointer; font-size:13px; max-width:150px;
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
  white-space:nowrap; padding:5px 11px; border-radius:var(--r-full); border:1px solid var(--line);
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
  aside.toc::-webkit-scrollbar-thumb{background:var(--line); border-radius:var(--r-full)}
}
.toc-h{font-size:11px; letter-spacing:.09em; color:var(--fg3); text-transform:uppercase;
       margin:0 0 7px 9px}
.toc-cat>a{
  display:flex; align-items:center; gap:8px; padding:5px 9px; border-radius:var(--r-sm);
  font-weight:600; font-size:13px; color:var(--fg2);
}
.toc-cat>a span.n{margin-left:auto}
.toc-cat>a:hover{background:var(--panel2); color:var(--fg); text-decoration:none}
.toc-cat>a.on{background:var(--accent-soft); color:var(--accent)}
.toc-cat>a .n,.toc-grp a .n{font-size:11px; color:var(--fg3); font-weight:400}
.toc-grp{margin:1px 0 7px 9px; border-left:1px solid var(--line); padding-left:7px}
.toc-grp a{
  display:block; padding:3px 7px; border-radius:var(--r-xs); font-size:12.5px; color:var(--fg3);
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
.sec-body{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:12px 16px}

/* ---------- 空清单页：还没填内容的页面不摆一片空白 ----------
   类名故意不叫 .empty —— 页面里那个 .empty 是「搜索无结果」用的、
   默认 display:none，撞上的话这一段会被一起藏掉。 */
.blank{
  background:var(--panel); border:1px dashed var(--line); border-radius:var(--radius);
  padding:46px 26px 40px; text-align:center;
}
.blank .ic{
  width:54px; height:54px; line-height:54px; margin:0 auto 15px; font-size:24px;
  border-radius:var(--radius); background:var(--accent-soft); color:var(--accent);
}
.blank h3{font-size:16.5px; color:var(--fg); margin:0 0 9px; font-weight:600}
.blank p{margin:0 auto 9px; max-width:540px; color:var(--fg2); font-size:13.5px; line-height:1.85}
.blank p.hint{color:var(--fg3); font-size:12.5px; margin-bottom:0}
.blank code{
  background:var(--panel2); border:1px solid var(--line); border-radius:var(--r-xs);
  padding:1px 6px; font-size:12.5px; color:var(--fg2);
}

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
       background:var(--panel2); border-radius:var(--r-full); padding:0 7px}
.grp-desc{margin:0 0 6px 19px; color:var(--fg2); font-size:13px}
.grp-body{margin-left:19px; padding-bottom:6px}

.item{
  padding:6px 8px 6px 12px; border-left:2px solid var(--line); margin:2px 0;
  display:flex; flex-wrap:wrap; align-items:baseline; gap:5px 9px;
  border-radius:0 5px 5px 0;
}
.item:hover{background:var(--panel2)}
.item .nm{font-weight:600; color:var(--fg); font-size:14.5px; flex:0 1 auto; min-width:0}
.item a.nm{color:var(--accent)}
.item a.nm:hover{text-decoration:underline}
.item .chips{display:inline-flex; align-items:center; gap:4px; flex:0 0 auto}
/* 地域标记：颜色跟着主题走，暗色下自动变亮，不会糊成一片 */
.item .rg{
  font-size:10.5px; line-height:1.75; padding:0 6px; border-radius:var(--r-xs);
  white-space:nowrap; border:1px solid transparent;
}
.item .rg-slow{
  color:var(--warn-fav);
  border-color:color-mix(in srgb, var(--warn-fav) 38%, transparent);
  background:color-mix(in srgb, var(--warn-fav) 12%, transparent);
}
.item .rg-bad{
  color:var(--warn);
  border-color:color-mix(in srgb, var(--warn) 40%, transparent);
  background:color-mix(in srgb, var(--warn) 12%, transparent);
}
.item .ds{color:var(--fg2); font-size:13px; flex:1 1 280px; min-width:0}
.item .note{
  flex:1 1 100%; color:var(--fg3); font-size:12.5px; line-height:1.6;
  padding-left:9px; border-left:2px solid var(--line);
}
.item .note::before{content:"▸ "; color:var(--fg3)}
.item.dep .nm{text-decoration:line-through; color:var(--fg3)}
.item.dep .ds{color:var(--fg3); text-decoration:line-through}
.item.cur{background:var(--accent-soft)}
ul.sub{margin:4px 0 2px 0; padding-left:16px; color:var(--fg2); font-size:13px; width:100%}
ul.sub li{margin:2px 0}
mark{background:var(--mark); color:var(--mark-fg); border-radius:3px; padding:0 1px}

@keyframes flash{from{background:var(--accent-soft)} to{background:transparent}}
.flash{animation:flash 1.2s ease-out}

.hidden{display:none !important}
.empty{display:none; text-align:center; color:var(--fg3); padding:44px 0; font-size:13.5px}
.empty.show{display:block}
.empty b{color:var(--fg2)}

/* ---------- 页头 ---------- */
.pagehead{margin:0 0 20px}
.crumbs{font-size:12.5px; color:var(--fg3); margin:0 0 10px; display:flex; gap:6px; align-items:center}
.crumbs a{color:var(--fg3)}
.crumbs a:hover{color:var(--accent); text-decoration:none}
.crumbs .sep{color:var(--fg3); opacity:.6}
.crumbs .cur{color:var(--fg2)}
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
  border:1px solid var(--line); border-radius:var(--r-sm); background:var(--panel);
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
  padding:3px 7px; margin:0 -7px; border-left:0; border-radius:var(--r-sm);
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
      border-radius:var(--radius); padding:12px 18px}
.help summary{cursor:pointer; font-weight:600; padding:8px 0}
.help h3{font-size:14px; margin:16px 0 6px}
.help p,.help li{color:var(--fg2); font-size:13px}
.help table{border-collapse:collapse; width:100%; margin:6px 0 4px}
.help td,.help th{border:1px solid var(--line); padding:5px 9px; font-size:13px; text-align:left;
                  vertical-align:top}
.help th{background:var(--panel2); font-weight:600}
.help kbd{background:var(--panel2); border:1px solid var(--line); border-bottom-width:2px;
          border-radius:var(--r-xs); padding:0 5px; font-size:12px; font-family:inherit}

footer{
  max-width:1180px; margin:0 auto; padding:0 16px 46px; color:var(--fg3); font-size:12.5px;
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;
}
.fnav a{color:var(--fg3)}
.fnav a:hover{color:var(--accent); text-decoration:none}
.totop{
  position:fixed; right:18px; bottom:18px; width:38px; height:38px; border-radius:50%;
  border:1px solid var(--line); background:var(--panel); color:var(--fg2); cursor:pointer;
  font-size:16px; display:none; z-index:60;
}
.totop.show{display:block}

__SKIN_PANEL_CSS__

@media (max-width:720px){
  .bar{padding:8px 12px; gap:8px}
  .brand{font-size:14px}
  /* 2026-10-09：删掉了这里「把 .tools 撑满一整行」的老规则。
     当年搜索框 / 筛选 / 折叠都塞在顶栏的 .tools 里，窄屏放不下才独占一行；
     它们后来搬去了分类条（.cats-tools），顶栏只剩「外观」一个按钮 ——
     那条 width:100% 还在的话，手机上「外观」就孤零零占一整行，
     而手写的彩票页没这条反而正常，两页顶栏看着不一样。 */
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
/* >>> 外观层 v2（theme/theme.css，构建时内联） >>> */
__UPGRADE_CSS__
/* <<< 外观层 v2 <<< */
</style>
__SKIN_SCRIPT__
</head>
<body id="top" data-layout="__LAYOUT__" class="__BODYCLS__">

__SITE_HEADER__

<!-- 顶栏（header）全站焊死成同一副样子：品牌 + 页面导航 + 外观按钮，
     不因为页面不同而多一块少一块。搜索框 / 筛选 / 折叠这些只属于清单页的东西，
     2026-10-08 起搬到下面这一行（分类条的右端），清单页之间也保持一致。 -->
<nav class="cats"><div class="wrap"><div class="cats-scroll">__NAV__</div><div class="cats-tools">__TOOLS__</div></div></nav>

<div class="shell">
  <aside class="toc">
__SIDECARD__
    <p class="toc-h">本页目录</p>
__TOC__
  </aside>

  <main>
    <div class="pagehead">
__CRUMB__
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
         每次更新做了些什么，都记在<a href="changelog.html">更新日志</a>里。</p>
      <h3>数据与隐私</h3>
      <ul>
        <li>纯静态页面：没有后端、没有数据库、没有统计脚本、不请求任何第三方 CDN。</li>
        <li>本地存储只有一项——你的外观偏好，不上传任何数据。</li>
        <li>页面上的链接都指向第三方站点，跳转之后的行为不受本站控制。</li>
        <li>完整说明见<a href="privacy.html">隐私说明</a>，站点的来由见<a href="about.html">关于</a>。</li>
      </ul>
      <h3>免责声明</h3>
      <p>清单是个人使用记录，链接来自公开网络，不保证长期有效，
         也不提供任何软件下载托管。软件版权归各自厂商所有，请通过正规渠道购买授权。</p>
    </details>
  </main>
</div>

<footer>
  <div class="f-wrap">
    <div class="f-col">
      <div class="f-brand"><span class="logo">U</span><b>uppjs.com</b></div>
      <p>自己在用的软件、硬件和外设，整理成清单长期更新。<br>
         不接推广、不做商业排序，收录标准只有一条：用得住。</p>
      <div class="f-badges" style="margin-top:13px">
        <span>纯静态</span><span>无后端</span><span>无统计脚本</span><span>无第三方请求</span>
      </div>
    </div>
    <div class="f-col">
      <h4>站内导航</h4>
      <div class="fl">
        __NAVFOOT__
      </div>
    </div>
    <div class="f-col">
      <h4>本页数据</h4>
      <div class="rows">
        <div>源文件<b>__SRC__</b></div>
        <div>收录条目<b>__TOTAL__</b></div>
        <div>外部链接<b>__LINKS__</b></div>
        <div>更新时间<b>__UPDATED__</b></div>
      </div>
    </div>
  </div>
  <div class="f-bot">
    <span>© 2026 uppjs.com · 页面由 <code>build_v2.py</code> 从 markdown 编译生成</span>
    <span>没有 Cookie、没有埋点、没有第三方请求</span>
  </div>
</footer>

<button class="totop" id="totop" title="回到顶部">↑</button>
__UPGRADE_JS__

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
  function hasP(el, k){
    return (' ' + (el.dataset.p || '') + ' ').indexOf(' ' + k + ' ') !== -1;
  }
  var FILTERS = {
    link: function(el){ return el.dataset.l === '1'; },
    star: function(el){ return el.dataset.star === '1'; },
    cn: function(el){ return el.dataset.r === 'cn'; },
    pmac: function(el){ return hasP(el, 'mac'); },
    pwin: function(el){ return hasP(el, 'win'); },
    pandroid: function(el){ return hasP(el, 'android'); },
    pios: function(el){ return hasP(el, 'ios'); },
    pweb: function(el){ return hasP(el, 'web'); }
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
# 4. 首页 index.html（导航）
#    首页只干一件事：把「软件清单」顶到最显眼的位置，其余页面依次排开。
#    卡片从 LIST_PAGES / TOOL_PAGES 自动派生 —— 页面一下线，卡片自己就没了，
#    不用来回改两个地方。想加一个预告：往 PLANNED 里加一行。
#    页面上的所有数字都是从生成好的页面里数出来的，不写死。
# --------------------------------------------------------------------------

# 首页「规划中」占位：(标题, 图标, 想指向的页面 / None, 说明)。
# 那个页面一旦真的上线（进了 LIVE），这条会自动从「规划中」消失。
PLANNED = [
    ("文章归档", "▦", "articles.html", "写过的长文按主题归档，比在平台里翻历史清楚得多。"),
    ("书单", "▥", "books.html", "看过的书，带年份、评分和一句短评。"),
    ("影单", "▤", "movies.html", "看过的电影和剧集，带年份、评分和一句短评。"),
    ("网址书签", "链", "links.html", "常开的网站和在线工具，按用途分好类。"),
    ("拼音搜索", "拼", None, "打 wyyy 就能搜到「网易云」，不用来回切输入法。"),
    ("条目对比", "⇄", None, "把几条并排比参数，选哪个一目了然。"),
    ("失效链接体检", "检", None, "定期跑一遍外链，把 404 的挑出来。清单最怕的不是少，而是过期。"),
]


# 首页 hero 里打字机滚出来的那句话。想换文案只改这一行。
HOME_QUOTE = ("不接推广，不做商业排序 —— 收录标准只有一条："
              "我真的在用，而且用得住。")


def collect_stars(cats, page_title):
    """把一个清单页里标了 ☆ 的条目收出来，供首页「精选条目」用。"""
    out = []

    def walk(ns, group_title=""):
        for x in ns:
            if x.get("children") and not x.get("has_link"):
                walk(x["children"], x.get("title") or group_title)
            elif x.get("star"):
                out.append(dict(
                    title=plain(x["title"]),
                    url=x.get("url") or "",
                    desc=plain(x.get("desc") or ""),
                    src=page_title,
                    group=plain(group_title),
                ))

    # cats 是分类层，本身不是条目节点，从它们的 children 开始走
    for c in cats:
        walk(c["children"], c.get("title", ""))
    return out


def _glyph(title: str) -> str:
    """封面 / 图标上那个字：中文取首字，英文取首字母。"""
    t = (title or "·").strip()
    return t[0] if t else "·"


def _cover_glyph(ico, title):
    """▤ ▥ ▦ 这类方块符号当封面太单薄 —— 换成标题首字，一眼能认出是谁。"""
    if ico and ico[0] in "▤▥▦▧▨▩▣◈◇◆":
        return _glyph(title)
    return ico or _glyph(title)


def _frow(idx, ico, title, href, desc, meta, pin="", rev=False):
    """首页的图文大卡。封面是纯 CSS 渐变 —— 不引任何图片，页面依旧是零外部请求。"""
    g = "g%d" % (idx % 6 + 1)
    meta_html = "".join(f"<i>{m}</i>" for m in meta)
    pin_html = f'<span class="pin">{esc(pin)}</span>' if pin else ""
    cls = "frow rev" if rev else "frow"
    return (
        f'<a class="{cls} reveal" href="{href}">'
        f'<span class="fcover {g}">{_cover_glyph(ico, title)}</span>'
        f'<div class="ftxt">'
        f'<h3>{esc(title)}{pin_html}</h3>'
        f'<p>{desc}</p>'
        f'<span class="meta">{meta_html}</span>'
        f'<span class="go">进入</span>'
        f'</div></a>'
    )


# 首页「最近」模块：从这几页各取第一条，当「在读 / 在看 / 在写」。
# 取的是「作者排在最前面的那一条」—— 内容源里把最近的在最前，
# 这条约定比加一个日期字段省事，也不会让用户填错。
RECENT_SRC = [
    ("books.html", "在读", "书"),
    ("movies.html", "在看", "影"),
    ("articles.html", "在写", "文"),
]

# 侧栏个人名片上那句自我介绍。想换只改这一行。
HOME_BIO = ("做效率工具和 AI 工具的实践分享。不做测评，只看自己真在用、"
            "真踩过坑的东西 —— 工具好不好用，看你有没有用完它。")


def first_leaf(cats):
    """深度优先取第一条真正的条目（遇到分组就往下钻）。"""
    def walk(ns):
        for x in ns:
            kids = x.get("children") or []
            if kids and not x.get("has_link"):
                got = walk(kids)
                if got:
                    return got
            elif (x.get("title") or "").strip():
                return x
        return None
    return walk(cats or [])


def collect_recents(parsed):
    """首页「最近」用的数据：书单 / 影单 / 文章归档各取最新一条。

    某页还没上线（内容源是空的）就自然不出现 —— 不用手工维护这个列表。"""
    out = []
    for out_name, label, ico in RECENT_SRC:
        it = first_leaf(parsed.get(out_name))
        if not it:
            continue
        # 「简述 ｜ 点评」两段拼起来显示：点评那句才是别人真正想看的
        bits = [plain(it.get("desc") or ""), plain(it.get("note") or "")]
        desc = "｜".join(b for b in bits if b)
        out.append(dict(label=label, ico=ico, href=out_name,
                        title=plain(it.get("title") or ""),
                        url=it.get("url") or "", desc=desc))
    return out


def norm_key(s: str) -> str:
    """条目名归一化，用来在「软件与资源」里查同一条：
    去 markdown 标记、去 ☆ 与删除线、去空格和句尾标点、转小写。"""
    t = plain(s or "").replace("~~", "").replace("☆", "")
    t = re.sub(r"[\s\u3000]+", "", t).strip("。.．")
    return t.lower()


def build_item_index(cats):
    """把「软件与资源」的条目按标题建索引，供专题页引用。同名取第一条。"""
    idx = {}

    def walk(ns):
        for x in ns:
            if x.get("children") and not x.get("has_link"):
                walk(x["children"])
            else:
                k = norm_key(x.get("title"))
                if k and k not in idx:
                    idx[k] = x
    walk(cats or [])
    return idx


def enrich_pack(cats, index):
    """专题页的条目在内容源里只写了名字 —— 这里去「软件与资源」里查真身。

    网址 / 简述 / 平台 / 荐 全部带过来，**只引用不复制**，所以软件页改了描述，
    专题页跟着变，不存在两处内容打架的问题。
    内容源里写的那句「为什么选它」挪到 note（页面上单独一行显示）。

    返回在软件页里查不到的条目名，供构建时提示 —— 多半是名字写错了。"""
    miss = []

    def walk(ns):
        for x in ns:
            if x.get("children") and not x.get("has_link"):
                walk(x["children"])
                continue
            if x.get("url"):      # 自己带了链接的（手写的站外网址）原样保留
                continue
            hit = index.get(norm_key(x.get("title")))
            if not hit:
                if (x.get("title") or "").strip():
                    miss.append(x["title"])
                continue
            x["note"] = x.get("desc") or ""        # 专题里写的「为什么选它」
            x["desc"] = hit.get("desc") or ""      # 软件页的原简述
            x["url"] = hit.get("url") or ""
            x["has_link"] = bool(x["url"])
            x["host"] = host_of(x["url"])
            x["plat"] = hit.get("plat") or []
            x["star"] = bool(x.get("star") or hit.get("star"))
    walk(cats or [])
    return miss


def build_home(pages: dict, updated: str, stars=None, recents=None) -> str:
    """pages: {out 文件名: {"items":…, "links":…, "groups":…, "cats":[(id, 标题, 条数)]}}"""
    apps = pages.get("apps.html", {})
    apps_cats = apps.get("cats", [])
    stars = stars or []
    recents = recents or []

    # ---------- 主要板块：图文交替大卡 ----------
    rows, idx = [], 0
    for cfg in LIST_PAGES:
        if cfg["out"] not in LIVE:
            continue
        pg = pages.get(cfg["out"], {})
        meta = [f'<b>{pg.get("items", 0)}</b> 条收录',
                f'<b>{len(pg.get("cats", []))}</b> 个分类',
                f'<b>{pg.get("groups", 0)}</b> 个分组']
        if cfg.get("regions"):
            meta.append('已标 <b>国内能不能直连</b>')
        rows.append(_frow(idx, cfg.get("ico", "·"), cfg["title"], cfg["out"],
                          md_inline(cfg.get("home") or cfg["sub"]), meta,
                          pin=("主打" if cfg["out"] == "apps.html" else ""),
                          rev=bool(idx % 2)))
        idx += 1

    for t in TOOL_PAGES:
        if t["href"] not in LIVE:
            continue
        rows.append(_frow(idx, t["ico"], t["title"], t["href"],
                          md_inline(t["desc"]),
                          ['<b>纯离线</b> 单文件', '<b>不联网</b>', '<b>2</b> 种玩法'],
                          rev=bool(idx % 2)))
        idx += 1

    # ---------- 精选条目（各页标了 ☆ 的） ----------
    if stars:
        picks = stars[:6]
        tiles = []
        for i, s in enumerate(picks):
            if s["url"]:
                head = (f'<a class="tcard reveal" href="{esc(s["url"])}" target="_blank" '
                        f'rel="noopener noreferrer">')
                tail = "</a>"
            else:
                head, tail = '<div class="tcard reveal">', "</div>"
            tiles.append(
                f'{head}<span class="cnt">{esc(s["src"])}</span>'
                f'<div class="ti g{i % 6 + 1}">{esc(_glyph(s["title"]))}</div>'
                f'<h3>{esc(s["title"])}</h3>'
                f'<p>{esc(s["desc"]) or "—"}</p>{tail}'
            )
        stars_sec = f"""    <section>
      <div class="sec-h reveal">
        <i class="bar-i"></i>精选条目
        <span class="sub">· 清单里标了 ☆ 的那些</span>
        <a class="more" href="apps.html?view=star">看全部 →</a>
      </div>
      <div class="grid2">
{chr(10).join('        ' + t for t in tiles)}
      </div>
    </section>"""
    else:
        stars_sec = ""

    # ---------- 最近：在读 / 在看 / 在写 ----------
    # 数字花园的「生长感」全在这一块：主页能看出这个人最近在看什么、写什么。
    # 只有真上了线的页才会出现，所以书单 / 影单没内容时这里整块不渲染。
    if recents:
        cards = []
        for i, r in enumerate(recents):
            if r["url"]:
                tag = (f'<a class="tcard rc reveal" href="{esc(r["url"])}" '
                       f'target="_blank" rel="noopener noreferrer">')
            else:
                tag = f'<a class="tcard rc reveal" href="{r["href"]}">'
            cards.append(
                f'{tag}<span class="cnt">{esc(r["label"])}</span>'
                f'<div class="ti g{i % 6 + 1}">{esc(r["ico"])}</div>'
                f'<h3>{esc(r["title"])}</h3>'
                f'<p>{esc(r["desc"]) or "—"}</p></a>'
            )
        recent_sec = ("""    <section>
      <div class="sec-h reveal">
        <i class="bar-i"></i>最近
        <span class="sub">· 在读 / 在看 / 在写</span>
      </div>
      <div class="grid3">
%s
      </div>
    </section>""" % chr(10).join('        ' + c for c in cards))
    else:
        recent_sec = ""

    # ---------- 规划中 ----------
    todo = [x for x in PLANNED if not (x[2] and x[2] in LIVE)]
    plan = "".join(
        f'<div class="tcard plan reveal"><div class="ti">{_cover_glyph(ico, t)}</div>'
        f'<h3>{esc(t)}<span class="st">规划中</span></h3><p>{esc(d)}</p></div>'
        for t, ico, _href, d in todo
    )

    # ---------- 侧栏：快速入口 ----------
    side_links = []
    for cfg in LIST_PAGES:
        if cfg["out"] not in LIVE:
            continue
        n = pages.get(cfg["out"], {}).get("items", 0)
        side_links.append(f'<a href="{cfg["out"]}"><span class="ic">{cfg.get("ico", "·")}</span>'
                          f'{esc(cfg["title"])}<span class="n">{n}</span></a>')
    for t in TOOL_PAGES:
        if t["href"] in LIVE:
            side_links.append(f'<a href="{t["href"]}"><span class="ic">{t["ico"]}</span>'
                              f'{esc(t["title"])}</a>')
    for p in all_pages():
        if p["kind"] == "doc" and p.get("nav", True) and p["href"] in LIVE:
            side_links.append(f'<a href="{p["href"]}"><span class="ic">{p["ico"]}</span>'
                              f'{esc(p["title"])}</a>')

    # ---------- 侧栏：分类标签云 ----------
    cloud = "".join(
        f'<a href="apps.html#{cid}">{esc(ct)}<span>{n}</span></a>'
        for cid, ct, n in apps_cats[:10]
    )

    # ---------- 侧栏：最近更新（读 git 提交记录，没仓库就整块不出现） ----------
    recent = [c for c in git_commits(6) if c[1]]
    if recent:
        items = "".join(
            f'<div><span>{esc(s[:38])}</span><b class="dt">{esc(d)}</b></div>'
            for d, s in recent)
        recent_card = f"""    <div class="pcard">
      <h3>最近更新<span class="r"><a href="changelog.html">全部 →</a></span></h3>
      <div class="rows">{items}</div>
    </div>
"""
    else:
        recent_card = ""

    # ---------- 汇总 ----------
    total = sum(x.get("items", 0) for x in pages.values())
    links = sum(x.get("links", 0) for x in pages.values())
    groups = sum(x.get("groups", 0) for x in pages.values())
    n_cats = sum(len(x.get("cats", [])) for x in pages.values())

    return (HOME_TEMPLATE
            .replace("__ROWS__", "\n        ".join(rows))
            .replace("__STARS_SEC__", stars_sec)
            .replace("__RECENT_SEC__", recent_sec)
            .replace("__BIO__", esc(HOME_BIO))
            .replace("__PLANNED__", plan)
            .replace("__SIDE_LINKS__", "\n        ".join(side_links))
            .replace("__SIDE_CLOUD__", cloud)
            .replace("__SIDE_RECENT__", recent_card.rstrip("\n"))
            .replace("__N_ALL__", str(total))
            .replace("__N_CATS__", str(n_cats))
            .replace("__N_GROUPS__", str(groups))
            .replace("__N_LINKS__", str(links))
            .replace("__N_PAGES__", str(len(LIVE)))
            .replace("__N_PLAN__", str(len(todo)))
            .replace("__QUOTE__", esc(HOME_QUOTE))
            .replace("__UPDATED__", esc(updated))
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__UPGRADE_CSS__", UPGRADE_CSS)
            .replace("__UPGRADE_JS__", UPGRADE_JS)
            .replace("__SKIN_SCRIPT__", SKIN_SCRIPT)
            .replace("__SKIN_PANEL_CSS__", SKIN_PANEL_CSS)
            .replace("__SKIN_PANEL_HTML__", SKIN_PANEL_HTML)
            .replace("__SKIN_PANEL_JS__", SKIN_PANEL_JS)
            .replace("__SITE__", SITE)
            .replace("__SITE_NAME__", SITE_NAME)
            .replace("__THEME_COLOR__", THEME_COLOR)
            .replace("__OG_IMAGE__", esc(SITE + "/" + og_image("index.html")))
            .replace("__SITE_HEADER__", site_header("index.html"))
            .replace("__RSS_LINK__", rss_link_tag())
            .replace("__NAVFOOT__", footer_nav("index.html"))
            .replace("__JSONLD__", jsonld_html(site_jsonld() + [
                {"@type": "CollectionPage", "@id": SITE + "/#page",
                 "url": SITE + "/", "name": f"{SITE_NAME} · {SITE_SUB}",
                 "description": SITE_DESC, "inLanguage": "zh-CN",
                 "isPartOf": {"@id": SITE + "/#website"}},
            ]))
            .replace("__SITE_DESC__", esc(SITE_DESC)))


HOME_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="auto">
<head>
<script>document.documentElement.className+=" js";</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__SITE_NAME__ · 软件与工具清单</title>
<meta name="description" content="__SITE_DESC__">
<link rel="canonical" href="__SITE__/">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="__THEME_COLOR__">
<meta property="og:type" content="website">
<meta property="og:site_name" content="uppjs.com">
<meta property="og:url" content="__SITE__/">
<meta property="og:title" content="__SITE_NAME__ · 软件与工具清单">
<meta property="og:description" content="__SITE_DESC__">
<meta property="og:image" content="__OG_IMAGE__">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="uppjs.com · 软件与工具清单">
<meta name="twitter:card" content="summary_large_image">
__RSS_LINK__
__JSONLD__
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
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--r-xs)}
__SKIN_PANEL_CSS__
/* >>> 外观层 v2（theme/theme.css，构建时内联） >>> */
__UPGRADE_CSS__
/* <<< 外观层 v2 <<< */
</style>
__SKIN_SCRIPT__
</head>
<body class="home">

__SITE_HEADER__

<section class="hero">
  <div class="hero-bg" aria-hidden="true"></div>

  <div class="hero-av reveal">U</div>
  <h1 class="hero-name reveal">__SITE_NAME__</h1>
  <p class="hero-en reveal" data-typer-en="TOOLS I ACTUALLY USE"></p>
  <div class="hero-quote reveal"
       data-typer-quote="__QUOTE__"
       data-quote-label="本站态度"></div>

  <div class="hero-cta reveal">
    <a class="btn btn-primary" href="apps.html">打开软件与资源</a>
    <a class="btn btn-ghost" href="lottery.html">彩票选号</a>
  </div>

  <a class="hero-scroll" href="#main" aria-label="向下滚动"><span></span></a>
</section>

<div class="wrap" id="main">

  <aside class="side">
    <div class="pcard me">
      <div class="av">U</div>
      <div class="nm">__SITE_NAME__</div>
      <p class="sg">让技术说人话</p>
      <p class="bio">__BIO__</p>
      <div class="sr">
        <div><b>__N_ALL__</b><i>条收录</i></div>
        <div><b>__N_CATS__</b><i>个分类</i></div>
        <div><b>__N_GROUPS__</b><i>个分组</i></div>
      </div>
      <a class="cta" href="apps.html">开始浏览</a>
      <a class="cta2" href="about.html">这个站是什么</a>
    </div>

    <div class="pcard">
      <h3>站点数据</h3>
      <div class="rows">
        <div>收录条目<b>__N_ALL__</b></div>
        <div>外链总数<b>__N_LINKS__</b></div>
        <div>页面数量<b>__N_PAGES__</b></div>
        <div>最近更新<b>__UPDATED__</b></div>
      </div>
    </div>

    <div class="pcard">
      <h3>快速入口</h3>
      <div class="slist">
__SIDE_LINKS__
      </div>
    </div>

    <div class="pcard">
      <h3>分类</h3>
      <div class="cloud">
__SIDE_CLOUD__
      </div>
    </div>

__SIDE_RECENT__
  </aside>

  <main class="content">

    <div class="notice reveal">
      <span class="b">✓</span>
      <span>全站 <b>__N_ALL__ 条</b>，全部是我自己真在用、用得住才写进来 ——
            没有推广位，没有商业排序，也没有人付钱能把自己塞进来。</span>
    </div>

__RECENT_SEC__

    <section>
      <div class="sec-h reveal">
        <i class="bar-i"></i>我整理的东西
        <span class="sub">· 各自独立成页，都能搜</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:15px">
__ROWS__
      </div>
    </section>

__STARS_SEC__

    <section>
      <div class="sec-h reveal">
        <i class="bar-i"></i>规划中
        <span class="sub">· 做好一个开一个，不摆空页面</span>
        <a class="more" href="changelog.html">更新日志 →</a>
      </div>
      <div class="grid3">
__PLANNED__
      </div>
    </section>

  </main>
</div>

<footer>
  <div class="f-wrap">
    <div class="f-col">
      <div class="f-brand"><span class="logo">U</span><b>uppjs.com</b></div>
      <p>自己在用的软件、硬件和外设，整理成清单长期更新。<br>
         不接推广、不做商业排序，收录标准只有一条：用得住。</p>
      <div class="f-badges" style="margin-top:13px">
        <span>纯静态</span><span>无后端</span><span>无统计脚本</span><span>无第三方请求</span>
      </div>
    </div>
    <div class="f-col">
      <h4>站内导航</h4>
      <div class="fl">
        __NAVFOOT__
      </div>
    </div>
    <div class="f-col">
      <h4>本站怎么做的</h4>
      <p>内容源是 markdown，所有页面由脚本编译成纯静态 HTML。
         唯一存进浏览器的，是你的外观偏好，不上传任何数据。</p>
      <div class="fl" style="margin-top:10px">
        <a href="about.html">关于这个站</a>
        <a href="sitemap.xml">站点地图</a>
      </div>
    </div>
  </div>
  <div class="f-bot">
    <span>© 2026 uppjs.com · 更新于 __UPDATED__</span>
    <span>没有 Cookie、没有埋点、没有第三方请求</span>
  </div>
</footer>

__UPGRADE_JS__
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
# 5. 文档页模板与内容
#    ① 上线文档页（about / privacy / 404 / 更新日志）—— 从 DOC_PAGES 和 git log 生成
#    ② 使用说明 —— 只在本机生成，不上线
#       内容源在「本地资料/」，那个目录写进了 .gitignore：
#       既不提交到 GitHub，也不会出现在 build 产物里，只在你自己电脑上。
#       想重新上线：把 help 加进 DOC_PAGES 即可。
# --------------------------------------------------------------------------

LOCAL_DIR = ROOT / "本地资料"
HELP_SRC = LOCAL_DIR / "使用说明.md"
HELP_OUT = LOCAL_DIR / "使用说明.html"


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

        def _link(m):
            url = m.group(2)
            ext = url.startswith("http") or url.startswith("//")
            tail = ' target="_blank" rel="noopener noreferrer"' if ext else ""
            return '<a href="%s"%s>%s</a>' % (url, tail, m.group(1))

        # 外链与站内相对链接（apps.html#xxx 这种）都支持 —— 站内互链是归档页最大的价值之一
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, s)
        return s

    while i < n:
        line = lines[i]

        # HTML 注释：整段跳过（内容源文件里用来写「怎么改」的说明，不上页面）
        if "<!--" in line:
            while i < n and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

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
<html lang="zh-CN" data-theme="auto">
<head>
<script>document.documentElement.className+=" js";</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PAGE_TITLE__</title>
<meta name="description" content="__PAGE_DESC__">
<link rel="canonical" href="__CANON__">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon-180.png">
__NOINDEX__
<meta property="og:type" content="article">
<meta property="og:site_name" content="uppjs.com">
<meta property="og:url" content="__CANON__">
<meta property="og:title" content="__PAGE_TITLE__">
<meta property="og:description" content="__PAGE_DESC__">
<meta property="og:image" content="__OG_IMAGE__">
<meta name="twitter:card" content="summary_large_image">
__JSONLD__
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
  background:var(--code); border:1px solid var(--line); border-radius:var(--r-xs);
  padding:1px 5px; font-size:13.5px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
pre{
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 16px; overflow-x:auto; margin:14px 0;
}
pre code{background:none; border:0; padding:0; font-size:13.5px; line-height:1.65}
blockquote{
  margin:14px 0; padding:10px 16px; background:var(--soft);
  border-left:3px solid var(--accent); border-radius:var(--r-sm);
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
/* 顶栏不再单独 styl —— 文档页现在与首页 / 清单页共用同一套 <header class="bar">，
   样式全部来自 theme/theme.css（下面那段 __UPGRADE_CSS__），改一处全站生效。 */
@media (max-width:640px){
  article{padding:26px 16px 60px}
  h1{font-size:21px}
  h2{font-size:17px}
  table,thead,tbody,tr,th,td{display:block; width:100%}
  thead{display:none}
  table{margin:14px 0}
  tr{
    border:1px solid var(--line); border-radius:var(--r-sm); margin:0 0 10px;
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
  header{display:none}
  a{color:#000}
  h2{page-break-after:avoid}
  table,pre,blockquote{page-break-inside:avoid}
}
__SKIN_PANEL_CSS__
/* >>> 外观层 v2（theme/theme.css，构建时内联） >>> */
__UPGRADE_CSS__
/* <<< 外观层 v2 <<< */
</style>
__SKIN_SCRIPT__
</head>
<body>
__SITE_HEADER__
<article>
__BODY__
</article>

<footer>
  <div class="f-wrap">
    <div class="f-col">
      <div class="f-brand"><span class="logo">U</span><b>uppjs.com</b></div>
      <p>自己在用的软件、硬件和外设，整理成清单长期更新。<br>
         不接推广、不做商业排序，收录标准只有一条：用得住。</p>
      <div class="f-badges" style="margin-top:13px">
        <span>纯静态</span><span>无后端</span><span>无统计脚本</span><span>无第三方请求</span>
      </div>
    </div>
    <div class="f-col">
      <h4>站内导航</h4>
      <div class="fl">
        __NAVFOOT__
      </div>
    </div>
    <div class="f-col">
      <h4>本站怎么做的</h4>
      <p>内容源是 markdown，所有页面由脚本编译成纯静态 HTML。
         唯一存进浏览器的，是你的外观偏好。</p>
      <div class="fl" style="margin-top:10px">
        <a href="index.html">回到首页</a>
        <a href="sitemap.xml">站点地图</a>
      </div>
    </div>
  </div>
  <div class="f-bot">
    <span>© 2026 uppjs.com</span>
    <span>没有 Cookie、没有埋点、没有第三方请求</span>
  </div>
</footer>

<script>
__SKIN_PANEL_JS__
</script>
__UPGRADE_JS__
</body>
</html>
"""


def md_desc(md: str, fallback: str) -> str:
    """从 markdown 里挑一句能当 description 的话：跳过注释、标题、列表、表格。"""
    text = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith(("#", "|", "-", "*", ">", "```", "!")) \
                or re.match(r"^\d+\.", s):
            continue
        return plain(s)[:110].strip()
    return fallback


def build_doc_page(src_md: str, title: str, out: str, base: str = "",
                   nav_current: str = None, noindex: bool = False,
                   desc: str = "", extra_body: str = "") -> str:
    """文档页渲染：markdown -> 散文式排版。about / privacy / 404 / 更新日志 / 使用说明 共用。"""
    canon = SITE + "/" + out
    desc = (desc or md_desc(src_md, title))[:150]
    graph = site_jsonld() + [
        {"@type": "WebPage", "@id": canon + "#page", "url": canon, "name": title,
         "description": desc, "inLanguage": "zh-CN",
         "isPartOf": {"@id": SITE + "/#website"},
         "author": {"@id": SITE + "/#author"}},
    ] + ([{"@type": "BreadcrumbList",
           "itemListElement": breadcrumb_jsonld(out, title)}] if not noindex else [])
    return (HELP_TEMPLATE
            .replace("__PAGE_TITLE__", esc(title + " · " + SITE_NAME))
            .replace("__PAGE_DESC__", esc(desc))
            .replace("__CANON__", esc(canon))
            .replace("__NOINDEX__", '<meta name="robots" content="noindex">' if noindex else "")
            .replace("__OG_IMAGE__", esc(SITE + "/" + og_image(out)))
            .replace("__JSONLD__", jsonld_html(graph))
            .replace("__SITE_HEADER__", site_header(nav_current, base=base))
            .replace("__NAVFOOT__", footer_nav(out))
            .replace("__SKIN_SCRIPT__", SKIN_SCRIPT)
            .replace("__SKIN_PANEL_CSS__", SKIN_PANEL_CSS)
            .replace("__SKIN_PANEL_JS__", SKIN_PANEL_JS)
            .replace("__UPGRADE_CSS__", UPGRADE_CSS)
            .replace("__UPGRADE_JS__", UPGRADE_JS)
            .replace("__BODY__", md_to_html(src_md) + extra_body))


def build_help_html() -> str:
    """本机说明书：导航指向线上站点（本地文件用不了相对路径）。"""
    md = HELP_SRC.read_text(encoding="utf-8")
    return build_doc_page(md, "使用说明（本机）", "help.html",
                          base="https://uppjs.com/", noindex=True,
                          extra_body="\n<hr>\n<p><em>这份说明只在本机生成，不上线。</em></p>")


def git_commits(limit: int = CHANGELOG_MAX):
    """读 git 提交记录，用于自动生成更新日志。取不到就返回空列表。"""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "log", "-%d" % limit, "--date=format:%Y-%m-%d",
             "--format=%ad\x1f%s"],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []
        rows = []
        for line in out.stdout.splitlines():
            if "\x1f" not in line:
                continue
            d, s = line.split("\x1f", 1)
            s = s.strip()
            if not s or s.startswith("Merge "):
                continue
            rows.append((d.strip(), s))
        return rows
    except Exception:
        return []


def build_changelog_md() -> str:
    """把提交记录按日期归组，写成一段 markdown，交给文档页渲染。"""
    rows = git_commits()
    if not rows:
        return ("# 更新日志\n\n这个站的每一次改动都会记在这里，按时间倒序，"
                "最新的一次在最上面。\n\n*（暂时取不到提交记录。）*\n")
    lines = ["# 更新日志", "",
             "这个站的每一次改动都记在这里，最新的在最上面。"
             "记录由仓库的提交历史自动生成，不用手写，也就不会过期。", ""]
    day = None
    for d, s in rows:
        if d != day:
            day = d
            lines.append("## " + d)
            lines.append("")
        lines.append("- " + s)
    lines.append("")
    return "\n".join(lines)


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
    (OUT_DIR / "manifest.webmanifest").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_leaf_items(cats):
    """按渲染器的同一套判断，把树里的叶子条目拍平：[(分类名, 节点)]。"""
    out = []

    def walk(nodes, cat):
        for n in nodes:
            if n["children"] and not n["has_link"]:
                walk(n["children"], cat)
            else:
                out.append((cat, n))

    for c in cats:
        walk(c["children"], c["title"])
    return out


DATE_RE = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


def item_date(node, fallback: str) -> str:
    """条目日期：优先取「简述/点评」里的 2026-08 这种写法，取不到就用 fallback。"""
    for s in (node.get("desc", ""), node.get("note", ""), node.get("raw", "")):
        m = DATE_RE.search(s or "")
        if m:
            return "%s-%s" % (m.group(1), m.group(2)) + ("-%s" % m.group(3) if m.group(3) else "")
    return fallback


def rfc822(day: str) -> str:
    """2026-08 / 2026-08-14 -> RFC822（RSS 要的时间格式）。"""
    parts = [int(x) for x in day.split("-")]
    y, mo = parts[0], parts[1]
    d = parts[2] if len(parts) > 2 else 1
    import datetime
    dt = datetime.date(y, mo, d)
    return dt.strftime("%a, %d %b %Y 00:00:00 +0800")


def redirect_page(r: dict) -> str:
    """旧地址的跳转页：一个几十行的静态 HTML，零依赖、离线也能跳，深浅色都跟系统走。
    除了 meta refresh 还带一段 JS —— 这样老链接后面带的 #锚点 也能一起带过去。"""
    to = r["to"]
    title = r.get("title") or "这个页面搬家了"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={to}">
<link rel="canonical" href="{esc(SITE + '/' + to)}">
<title>{esc(title)} · {esc(SITE_NAME)}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#12161f;--fg2:#5a6472;--line:#e2e5ea;--accent:#2f6fed}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161a21;--fg:#e8ecf3;--fg2:#9aa4b2;--line:#242a34;--accent:#5b8cff}}}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:var(--bg);color:var(--fg);padding:24px;
 font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:18px;
 padding:30px 28px;max-width:460px;text-align:center}}
h1{{font-size:18px;margin:0 0 8px}}
p{{color:var(--fg2);font-size:13.5px;margin:0 0 18px}}
a{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;
 border-radius:12px;padding:9px 18px;font-weight:600}}
</style>
<script>location.replace("{to}" + location.hash);</script>
</head>
<body>
<div class="box">
<h1>{esc(title)}</h1>
<p>没有自动跳过去的话，点下面这个。</p>
<a href="{esc(to)}">前往新页面 →</a>
</div>
</body>
</html>
"""


def sitemap_pages():
    """sitemap 的页面清单：活着、且标了 sitemap 的页面。"""
    weight = {"apps.html": ("0.9", "weekly"), "articles.html": ("0.9", "weekly"),
              "books.html": ("0.7", "weekly"), "movies.html": ("0.7", "weekly"),
              "links.html": ("0.7", "weekly"), "lottery.html": ("0.6", "monthly"),
              "about.html": ("0.5", "monthly"), "changelog.html": ("0.4", "monthly"),
              "privacy.html": ("0.3", "yearly")}
    out = [("", "1.0", "weekly")]
    for p in all_pages():
        if p["href"] in LIVE and p.get("sitemap", True):
            pr, cf = weight.get(p["href"], ("0.5", "monthly"))
            out.append((p["href"], pr, cf))
    return out


def build_seo(today: str):
    """生成 robots.txt 与 sitemap.xml，跟着每次更新一起产出，不用手动维护。"""
    (OUT_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE,
        encoding="utf-8")
    urls = "\n".join(
        "  <url><loc>%s/%s</loc><lastmod>%s</lastmod><changefreq>%s</changefreq>"
        "<priority>%s</priority></url>" % (SITE, p, today, cf, pr)
        for p, pr, cf in sitemap_pages())
    (OUT_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + urls + "\n</urlset>\n", encoding="utf-8")


LOTTERY_MARK = "<!-- uppjs:seo -->"

# 手写单文件页（lottery.html）的顶栏同步标记。
#   它不参与编译，顶栏当初是抄的一份老拷贝 —— 全站顶栏一改，它就掉队
#   （2026-10-08 那次「顶栏焊死 + 放宽到 70px」之后它还是旧样子）。
#   所以构建时把两样东西幂等注入进去，都用标记包住、重跑只替换标记之间的内容：
#     ① 结构：整块 <header> = site_header("lottery.html", tools=这一页自己的按钮)
#     ② 样式：theme.css 的「3. 顶栏」整段，原样搬过来（不重写，免得又多一份会掉队的拷贝）
#   想改彩票页顶栏 → 去改 theme.css / site_header()，重跑构建自动同步。
LOT_HDR_S = "<!--UPP:HEADER:start-->"
LOT_HDR_E = "<!--UPP:HEADER:end-->"
LOT_CSS_S = "<!--UPP:HEADER-CSS:start-->"
LOT_CSS_E = "<!--UPP:HEADER-CSS:end-->"


def theme_section(num):
    """从 theme.css 里原样抠出一整段（按 `/* ==== 数字. 名字 ==== */` 分节）。

    单文件页要复用某段样式时用它，而不是手抄一份 —— 抄的那份迟早掉队。
    """
    css = (THEME_DIR / "theme.css").read_text(encoding="utf-8")
    marks = list(re.finditer(r"/\* ={10,}\n\s*(\d+)\. [^\n]*\n\s*={10,} \*/", css))
    for i, m in enumerate(marks):
        if m.group(1) == str(num):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(css)
            return css[m.start():end].rstrip()
    return ""


def tool_header_css():
    """给单文件页用的顶栏覆盖样式：令牌（第 1 节）+ 顶栏（第 3 节）+ 变量 --hh。

    放在单文件页自己样式的后面，同名规则后写覆盖先写 —— 这样它自己的旧值会被压掉。

    2026-10-09 补搬了第 1 节：顶栏那一节里到处引用 --r-sm / --r-xs / --ease 这些令牌，
    只搬第 3 节的话，单文件页里这几个变量是空的 —— var() 拿不到值就回落成初始值，
    圆角直接变成 0，彩票页的顶栏会方得跟全站不是一回事。以后新令牌也一并跟过来。
    """
    css = (THEME_DIR / "theme.css").read_text(encoding="utf-8")
    hh = re.search(r"--hh:([^;]+);", css)
    hh_v = hh.group(1).strip() if hh else "70px"
    # 这里用字符串拼接而不是 % / f-string：搬过来的 CSS 里迟早会出现 `%` 或 `{}`
    # （color-mix 的百分比、@media 的大括号），一格式化就炸。
    return (LOT_CSS_S + "\n<style>\n"
            "/* ⚠️ 这一段由 build.py 自动从 theme/theme.css 搬来，别手改 —— 下次构建会被覆盖。\n"
            "   搬的是两节：① 圆角 / 阴影 / 曲线等令牌　② 顶栏本身。\n"
            "   想让本页顶栏变样，去改 theme/theme.css 的「3. 顶栏」那一节，重跑构建即可。 */\n"
            + theme_section(1) + "\n" + theme_section(3) + "\n"
            + ":root{--hh:" + hh_v + "}\n</style>\n"
            + LOT_CSS_E)


def sync_tool_header(doc):
    """把单文件页的顶栏换成全站那一副（结构 + 样式），幂等。

    这一页自己的功能按钮（「📅 数据快照」）从旧顶栏里捞出来，原样带过去 ——
    同步的是「壳」，不是「内容」。
    """
    # ① 结构
    btn = ""
    m = re.search(r'<button[^>]*onclick="showDataInfo\(\)"[^>]*>.*?</button>', doc, re.S)
    if m:
        btn = m.group(0).strip() + "\n      "
    hdr = LOT_HDR_S + "\n" + site_header("lottery.html", tools=btn) + "\n" + LOT_HDR_E
    if LOT_HDR_S in doc:
        doc = re.sub(re.escape(LOT_HDR_S) + r".*?" + re.escape(LOT_HDR_E),
                     lambda _: hdr, doc, count=1, flags=re.S)
    else:
        doc = re.sub(r"<header>.*?</header>", lambda _: hdr, doc, count=1, flags=re.S)

    # ② 样式（放 </head> 前，靠后写覆盖掉它自己的旧值）
    css = tool_header_css()
    if LOT_CSS_S in doc:
        doc = re.sub(re.escape(LOT_CSS_S) + r".*?" + re.escape(LOT_CSS_E),
                     lambda _: css, doc, count=1, flags=re.S)
    elif "</head>" in doc:
        doc = doc.replace("</head>", css + "</head>", 1)
    return doc


def patch_lottery():
    """给手写的 lottery.html 补上分享图 / 结构化数据，并把顶栏同步成全站那一副。

    它是独立单文件、不参与编译，所以这里做「幂等注入」：
      · 顶栏（结构 + 样式）：每次构建都重刷 —— 全站顶栏改了，它就跟着改
      · head 里的 SEO 段：只在缺的时候插一次
    这样即使以后整份换掉 lottery.html，重跑 build.py 也会自动补回来。
    """
    p = ROOT / "lottery.html"
    if not p.exists():
        return False
    doc = p.read_text(encoding="utf-8")
    synced = sync_tool_header(doc)
    changed = synced != doc
    doc = synced

    if PREVIEW:
        # 预览模式下 lottery.html 不参与编译，写出同步后的副本，别去改原件
        (OUT_DIR / "lottery.html").write_text(doc, encoding="utf-8")
        return False

    if LOTTERY_MARK in doc:
        if changed:
            p.write_text(doc, encoding="utf-8")
        return changed
    og = og_image("lottery.html")
    graph = site_jsonld() + [
        {"@type": "WebApplication", "@id": SITE + "/lottery.html#app",
         "url": SITE + "/lottery.html", "name": "双色球 / 大乐透选号工具",
         "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any",
         "inLanguage": "zh-CN", "isPartOf": {"@id": SITE + "/#website"},
         "author": {"@id": SITE + "/#author"},
         "description": "双色球、大乐透随机选号与购票核对，附历史开奖走势图。纯前端单文件，不联网。"},
        {"@type": "BreadcrumbList", "itemListElement": breadcrumb_jsonld(
            "lottery.html", "彩票选号")},
    ]
    block = "\n".join([
        LOTTERY_MARK,
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="uppjs.com">',
        '<meta property="og:url" content="%s/lottery.html">' % SITE,
        '<meta property="og:title" content="双色球 / 大乐透选号工具 · uppjs.com">',
        '<meta property="og:description" content="随机选号与购票核对，附历史开奖走势图。'
        '纯前端单文件，不联网、不上传任何信息。">',
        '<meta property="og:image" content="%s/%s">' % (SITE, og),
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="robots" content="index,follow">',
        jsonld_html(graph),
    ])
    anchor = '<link rel="canonical" href="%s/lottery.html">' % SITE
    if anchor in doc:
        doc = doc.replace(anchor, anchor + "\n" + block, 1)
    elif "</title>" in doc:
        doc = doc.replace("</title>", "</title>\n" + block, 1)
    else:
        return False
    p.write_text(doc, encoding="utf-8")
    return True


def build_feed(cats, today: str):
    """RSS 2.0：只做「文章归档」这一条。没有文章就不生成（宁可没有，也别给个空订阅）。"""
    items = []
    for cat, n in iter_leaf_items(cats):
        url = n.get("url")
        if not url:
            continue
        day = item_date(n, today)
        title = (n.get("title") or "").strip() or url
        desc = (n.get("note") or n.get("desc") or "").strip()
        items.append((day, title, url, desc, cat))
    if not items:
        return None
    items.sort(key=lambda x: x[0], reverse=True)
    entries = []
    for day, title, url, desc, cat in items[:30]:
        entries.append(
            "  <item>\n"
            "    <title>%s</title>\n"
            "    <link>%s</link>\n"
            "    <guid isPermaLink=\"true\">%s</guid>\n"
            "    <category>%s</category>\n"
            "    <pubDate>%s</pubDate>\n"
            "    <description>%s</description>\n"
            "  </item>" % (esc(title), esc(url), esc(url), esc(cat),
                           rfc822(day), esc(desc))
        )
    newest = rfc822(items[0][0])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        '  <title>uppjs.com · 文章归档</title>\n'
        '  <link>%s/articles.html</link>\n'
        '  <description>写过的长文，按主题归档。</description>\n'
        '  <language>zh-cn</language>\n'
        '  <lastBuildDate>%s</lastBuildDate>\n'
        '  <atom:link href="%s/feed.xml" rel="self" type="application/rss+xml"/>\n'
        '%s\n'
        '</channel>\n</rss>\n'
        % (SITE, newest, SITE, "\n".join(entries)))


def clean_orphans():
    """把「这次没生成、但上一轮留下来的」页面 html 删掉。

    为什么需要这一步：enabled=False（或内容源改没了）之后，build.py 本来就
    只是「不再产出」，旧 html 还躺在目录里 —— 而 EdgeOne 发的是整个目录，
    所以页面看着下线了，网址照样返回 200。以前只能手动 git rm，容易忘。

    安全边界（删错比漏删严重得多，所以这里收得很紧）：
      ① 只认三张登记表里写过的文件名 —— 首页、更新日志、手写页面一概不碰；
      ② 判断标准是「这次在不在 LIVE 里」，不是「表里面有没有出现过」；
      ③ 顺带清掉同名分享图 og/<页面名>.png，免得留一堆没人引用的死文件；
      ④ 预览模式只提示不动手 —— 预览目录本来就能随时删了重出。

    一句话：想让页面彻底消失，把 enabled 改成 False（或删掉内容源），重跑构建就行。
    """
    known = [cfg["out"] for cfg in LIST_PAGES]
    known += [cfg["out"] for cfg in DOC_PAGES]
    known += [t["href"] for t in TOOL_PAGES]

    def why(name):
        """打印一句人话原因，方便看到「咦我的页面怎么没了」时立刻知道动了哪。"""
        for cfg in LIST_PAGES:
            if cfg["out"] != name:
                continue
            if cfg.get("enabled", True) is False:
                return "这一页在 build.py 里被关掉了（enabled=False）"
            if not (ROOT / cfg["src"]).exists():
                return "内容源 %s 找不到了" % cfg["src"]
            return "内容源 %s 里还没有条目（auto：往里面填一条就会自动上线）" % cfg["src"]
        for cfg in DOC_PAGES:
            if cfg["out"] == name:
                return "内容源 %s 找不到了" % cfg["src"]
        for t in TOOL_PAGES:
            if t["href"] == name:
                return "源文件 %s 找不到了" % t["href"]
        return "这一轮没有生成它"

    dead = [n for n in dict.fromkeys(known) if n not in LIVE and (OUT_DIR / n).exists()]
    if not dead:
        return

    print("\n-- 清理已下线的旧页面 --")
    for name in dead:
        og_file = OUT_DIR / OG_DIR / (name.rsplit(".", 1)[0] + ".png")
        og_note = ""
        if og_file.exists():
            og_note = "、分享图 og/%s" % og_file.name
            if not PREVIEW:
                og_file.unlink()
        if PREVIEW:
            print("  预览发现 %s：%s（正式构建会删掉 %s%s）"
                  % (name, why(name), name, og_note))
        else:
            (OUT_DIR / name).unlink()
            print("  已删除 %s：%s%s\n     想恢复：改回去再跑一次构建就行，内容都还在。"
                  % (name, why(name), og_note))
    print("")


def main():
    global OUT_DIR
    today = git_date()
    dump = "--dump" in sys.argv
    pages = {}
    parsed = {}

    if PREVIEW:
        OUT_DIR = PREVIEW_DIR
        if not OUT_DIR.exists():
            OUT_DIR.mkdir(parents=True)
        print("预览模式：产物写到 %s（不会碰线上文件）" % OUT_DIR.relative_to(ROOT))

    # ---------- 第一遍：先决定这次哪些页面会生成 ----------
    # 导航、首页卡片、sitemap、RSS 链接都要先知道结果，所以决策和渲染必须分开。
    for cfg in LIST_PAGES:
        flag = cfg.get("enabled", True)
        if flag is False:
            print("已下线 %s（enabled=False，内容源 %s 留着，想恢复改回 True）"
                  % (cfg["out"], cfg["src"]))
            continue
        src = ROOT / cfg["src"]
        if not src.exists():
            print("跳过 %s：内容源 %s 不存在" % (cfg["out"], cfg["src"]))
            continue
        cats = build_tree(parse_lines(src.read_text(encoding="utf-8")))
        if cfg.get("regions"):
            n_rg = apply_regions(cats)
            print("  %s：挂了 %d 条地域标记（数据来自 %s）"
                  % (cfg["out"], n_rg, REGION_FILE.name))
        n_found = sum(leaf_count(c["children"]) for c in cats)
        if flag == "auto" and n_found == 0:
            if PREVIEW:
                print("预览 %s：%s 里还没有条目，出的是空页骨架" % (cfg["out"], cfg["src"]))
            else:
                print("跳过 %s：%s 里还没有条目，先不挂上去（往源文件里填内容，重跑即可自动上线）"
                      % (cfg["out"], cfg["src"]))
                continue
        parsed[cfg["out"]] = cats
        LIVE.add(cfg["out"])

    for cfg in DOC_PAGES:
        if (ROOT / cfg["src"]).exists():
            LIVE.add(cfg["out"])
        else:
            print("跳过 %s：内容源 %s 不存在" % (cfg["out"], cfg["src"]))
    LIVE.add(CHANGELOG_OUT)
    for t in TOOL_PAGES:
        if (ROOT / t["href"]).exists():
            LIVE.add(t["href"])

    # ---------- 下线就要真的看不见：把上一轮留下的旧页面删掉 ----------
    # 放在决策之后、渲染之前：趁着 LIVE 已经算清楚、又还没开始写新文件。
    # 「现在」这页就是吃了这个亏 —— enabled=False 之后 html 还在线上返回 200。
    clean_orphans()

    if dump:
        for out, cats in parsed.items():
            print("=== %s ===" % out)
            print(json.dumps(cats, ensure_ascii=False, indent=1))
        return

    # ---------- 专题页：把只写了名字的条目补全成真条目 ----------
    # 必须在渲染之前做：补完的 url / desc / plat 会一起进 html。
    apps_index = build_item_index(parsed.get("apps.html") or [])
    for cfg in LIST_PAGES:
        if not cfg.get("pack") or not parsed.get(cfg["out"]):
            continue
        miss = enrich_pack(parsed[cfg["out"]], apps_index)
        if miss:
            print("  ⚠ %s：这 %d 条在「软件与资源」里没找到同名条目，"
                  "页面上会是没链接的普通文字：%s"
                  % (cfg["out"], len(miss), "、".join(str(m) for m in miss[:8])))

    # ---------- 第二遍：渲染清单页 ----------
    for cfg in LIST_PAGES:
        cats = parsed.get(cfg["out"])
        if cats is None:
            continue
        page = render(cats, cfg, today)
        out = OUT_DIR / cfg["out"]
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

    # ---------- 旧地址跳转页：页面合并之后，收藏夹里的老链接不能 404 ----------
    for r in REDIRECTS:
        if r["to"] not in LIVE:
            continue
        (OUT_DIR / r["out"]).write_text(redirect_page(r), encoding="utf-8")
        print("已生成 %s：跳转到 %s" % (r["out"], r["to"]))

    # ---------- 文档页：关于 / 隐私 / 404 / 更新日志 ----------
    for cfg in DOC_PAGES:
        if cfg["out"] not in LIVE:
            continue
        html = build_doc_page((ROOT / cfg["src"]).read_text(encoding="utf-8"),
                              cfg["title"], cfg["out"], nav_current=cfg["out"],
                              noindex=cfg.get("noindex", False),
                              desc=cfg.get("desc", ""))
        (OUT_DIR / cfg["out"]).write_text(html, encoding="utf-8")
        print("已生成 %s（文档页 / %d KB）" % (cfg["out"], len(html) // 1024))

    cl_html = build_doc_page(build_changelog_md(), "更新日志", CHANGELOG_OUT,
                             nav_current=CHANGELOG_OUT)
    (OUT_DIR / CHANGELOG_OUT).write_text(cl_html, encoding="utf-8")
    n_cl = len(git_commits())
    print("已生成 %s（更新日志，自动取自最近 %d 条提交）" % (CHANGELOG_OUT, n_cl))

    # ---------- 首页 ----------
    # 首页「精选条目」取各清单页里标了 ☆ 的：一个人推荐过什么，比总数更能说明这站靠不靠谱。
    stars = []
    for cfg in LIST_PAGES:
        cs = parsed.get(cfg["out"])
        if cs and cfg.get("layout") == "list":
            stars.extend(collect_stars(cs, cfg["title"]))
    # 首页「最近」取书单 / 影单 / 文章归档的首条，全部来自已解析的内容，不另存一份。
    recents = collect_recents(parsed)
    home = build_home(pages, today, stars, recents)
    (OUT_DIR / "index.html").write_text(home, encoding="utf-8")
    print("已生成 index.html（首页）：全站 %d 条 / %d 个页面 / %d KB"
          % (sum(x["items"] for x in pages.values()), len(pages), len(home) // 1024))

    # ---------- RSS：只做文章归档 ----------
    feed = build_feed(parsed.get("articles.html") or [], today)
    if feed:
        (OUT_DIR / "feed.xml").write_text(feed, encoding="utf-8")
        print("已生成 feed.xml（RSS 订阅）")
    else:
        print("未生成 feed.xml（文章归档还没有内容）")

    # ---------- 说明书：只写「本地资料/」，不上线 ----------
    if HELP_SRC.exists():
        help_out = build_help_html()
        if not LOCAL_DIR.exists():
            LOCAL_DIR.mkdir(parents=True)
        HELP_OUT.write_text(help_out, encoding="utf-8")
        (LOCAL_DIR / "help.html").write_text(help_out, encoding="utf-8")
        print("已生成本地说明书（不上线）：%s" % HELP_OUT.relative_to(ROOT))

    build_seo(today)
    print("已生成 robots.txt 与 sitemap.xml（%d 个页面）" % len(sitemap_pages()))

    if patch_lottery():
        print("已同步 lottery.html：顶栏（结构 + 样式）对齐全站，并补上分享图与结构化数据")

    build_manifest()
    print("已生成 manifest.webmanifest")

    # ---------- 收尾自检 ----------
    # ① 占位符没被替换干净 = 上面某处接线漏了，页面上会出现 __XXX__ 这种字样
    # ② 标签开闭不平衡 = 某个模板拼坏了，页面版式会整块塌掉
    # 这两类错都「不报错、但肉眼才看得出」，所以在这里硬拦一道。
    import re as _re
    bad = []
    for p in sorted(OUT_DIR.glob("*.html")):
        t = p.read_text(encoding="utf-8")
        left = {x for x in _re.findall(r"__[A-Z][A-Z0-9_]{2,}__", t)}
        if left:
            bad.append("%s 里还有没替换的占位符：%s" % (p.name, "、".join(sorted(left))))
        for tag in ("div", "section", "main", "aside", "article", "a", "span"):
            o = len(_re.findall(r"<%s[\s>]" % tag, t))
            c = t.count("</%s>" % tag)
            if o != c:
                bad.append("%s 的 <%s> 开 %d / 闭 %d 对不上" % (p.name, tag, o, c))
    if bad:
        print("\n!! 自检没通过：")
        for b in bad:
            print("   - " + b)
        raise SystemExit(1)
    print("自检通过：占位符全部替换、主要标签开闭平衡")


if __name__ == "__main__":
    main()
