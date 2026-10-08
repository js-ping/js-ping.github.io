#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行模型.py —— 把 markdown 内容源拆成「块」，并且只改该改的行

为什么要有这一层：

    编辑器如果直接改文件，最怕的是「顺手把别的地方也改了」——注释没了、
    空行挤没了、某一行被重新规范化了。所以这里的原则是：

        ★ 只会重写你真正编辑过的那一个条目块，其余的行一个字节都不动。

    做法是把文件按行切成「块」（一个条目行 + 它下面的续行算一块），
    每个块记住自己占哪几行。编辑时只替换那一块，别的块原样拼回去。

解析规则**和 build.py 完全一致**（这一层的 parse 结果会拿去和
build.make_node 对账），所以不存在「编辑器显示一套、网站渲染另一套」。

块类型：
    comment  <!-- ... --> 注释块，原样保留，界面上折起来不显示
    blank    空行，原样保留
    cat      ## 一级分类
    sub      ### 分组
    item     - 条目（含它下面的续行 / 附注行）
    raw      其他无法归类的行（比如正文段落）
"""

import re

# —— 这几个正则和 build.py 里 parse_lines 用的是同一套 ——
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
CAT_RE = re.compile(r"^##\s+(.*)$")
SUB_RE = re.compile(r"^###\s+(.*)$")
CONT_RE = re.compile(r"^\s*[：:]\s*(.*)$")

PLAT_ALIAS = {
    "mac": "Mac", "macos": "Mac", "mac os": "Mac", "osx": "Mac", "苹果": "Mac",
    "win": "Win", "windows": "Win", "pc": "Win",
    "ios": "iOS", "iphone": "iOS", "ipad": "iOS",
    "android": "安卓", "安卓": "安卓",
    "web": "网页", "网页": "网页",
}
PLAT_ORDER = ["Mac", "Win", "安卓", "iOS", "网页"]


# ==========================================================================
# 一、扫描：把文件切成块
# ==========================================================================

def comment_mask(lines):
    """标出每一行是否落在 <!-- --> 注释块里。

    注释块里的内容 build.py 是不看的（内容源开头那一大段使用说明就是注释），
    所以这里也把它整块当"原样保留"处理。
    """
    mask = []
    in_comment = False
    for ln in lines:
        if in_comment:
            mask.append(True)
            if "-->" in ln:
                in_comment = False
            continue
        i = ln.find("<!--")
        if i >= 0:
            mask.append(True)
            if "-->" not in ln[i + 4:]:
                in_comment = True
            continue
        mask.append(False)
    return mask


def split_blocks(text):
    """把整份内容源切成块列表。

    返回的每一项：
        {"kind": "item", "start": 12, "end": 13, "indent": 4, "lines": [...]}
    start / end 是行号（end 不含），用来定位。
    """
    lines = text.split("\n")
    mask = comment_mask(lines)
    blocks = []

    for i, ln in enumerate(lines):
        kind = None
        if mask[i]:
            kind = "comment"
        elif not ln.strip():
            kind = "blank"
        elif ln.startswith("### "):
            kind = "sub"
        elif ln.startswith("## "):
            kind = "cat"
        elif BULLET_RE.match(ln):
            kind = "item"
        else:
            # 非 bullet 的正文行：跟着上一个条目当附注；否则算孤立的 raw
            if blocks and blocks[-1]["kind"] in ("item", "raw") and blocks[-1]["end"] == i:
                blocks[-1]["lines"].append(ln)
                blocks[-1]["end"] = i + 1
                continue
            kind = "raw"

        if kind in ("comment", "blank") and blocks and blocks[-1]["kind"] == kind \
                and blocks[-1]["end"] == i:
            # 连续的注释行 / 连续的空行合成一块，界面上好处理
            blocks[-1]["lines"].append(ln)
            blocks[-1]["end"] = i + 1
            continue

        blocks.append({"kind": kind, "start": i, "end": i + 1, "lines": [ln]})

    for b in blocks:
        if b["kind"] == "item":
            m = BULLET_RE.match(b["lines"][0])
            b["indent"] = len(m.group(1))
            b["body"] = m.group(2)
            b["text"] = join_body(b["lines"])
        elif b["kind"] == "sub":
            b["title"] = SUB_RE.match(b["lines"][0]).group(1).strip()
        elif b["kind"] == "cat":
            b["title"] = CAT_RE.match(b["lines"][0]).group(1).strip()
    return blocks


def join_body(lines):
    """把「条目行 + 它下面的续行」并成一段文字，规则和 build.py 的 parse_lines 一致：
    缩进的 `：xxx` 续行会被并进上一条的描述里。"""
    m = BULLET_RE.match(lines[0])
    text = m.group(2).strip()
    for extra in lines[1:]:
        c = CONT_RE.match(extra)
        text += "：" + (c.group(1).strip() if c else extra.strip())
    return text


# ==========================================================================
# 二、解析一个条目：交给 build.py 的 make_node，保证两边口径一致
# ==========================================================================

def parse_item(make_node, text):
    """用 build.py 的 make_node 解析条目文字，输出界面上要用的字段。"""
    n = make_node(text)
    return {
        "title": n["title"],
        "url": n["url"],
        "desc": n["desc"],
        "note": n["note"],
        "star": bool(n["star"]),
        "plat": list(n.get("plat") or []),
    }


# ==========================================================================
# 三、拼回一行：必须能被 parse_item 原样解析回来
# ==========================================================================

def render_item(f, indent=4):
    """字段 -> markdown 行。

    拼出来的写法是 `- ☆ [名字](网址)：简述｜短评 [Mac]`，理由：
      · ☆ 一律放行首（不管有没有网址），格式统一，读原文时一眼扫得出来；
      · 名字连网址一起写进链接，build.py 的 LINK_RE 匹配得到，url 不会丢；
      · 网址后面那段用「：」分隔，和现有内容源一致。
    拼完必须能原样解析回来 —— 服务器启动时会跑 roundtrip 自检。
    """
    pad = " " * max(0, int(indent))
    name = (f.get("title") or "").strip()
    url = (f.get("url") or "").strip()
    desc = (f.get("desc") or "").strip()
    note = (f.get("note") or "").strip()
    plats = [p for p in (f.get("plat") or []) if p in PLAT_ORDER]
    plats.sort(key=PLAT_ORDER.index)

    if url:
        head = "[%s](%s)" % (name, url)
    else:
        head = name

    line = pad + "- " + ("☆ " if f.get("star") else "") + head
    if desc or note:
        line += "：" + desc
        if note:
            line += "｜" + note
    if plats:
        line += " " + " ".join("[%s]" % p for p in plats)
    return line


def render_block_text(block, make_node):
    """把一个块的字段拼回「这个块应该长什么样」的完整文字（含换行）。"""
    if block["kind"] != "item":
        return "\n".join(block["lines"])
    line = render_item(block["fields"], block.get("indent", 0))
    tail = block["lines"][1:]
    return "\n".join([line] + tail)


# ==========================================================================
# 四、编辑动作：都基于「行号」定位，改完由调用方重新读盘
# ==========================================================================

class EditError(Exception):
    pass


def need_item(blocks, line):
    """按行号找一个 item 块，找不到就报错（而不是默默改错地方）。"""
    for b in blocks:
        if b["kind"] == "item" and b["start"] == line:
            return b
    raise EditError("第 %d 行不是一个条目，可能页面已经刷新过，请重试" % line)


def apply_update(lines, blocks, line, fields, make_node):
    b = need_item(blocks, line)
    new_line = render_item(fields, b.get("indent", 0))
    # 原块里的续行已经被并进 fields 了，所以这里整块换成一行，不会丢内容
    return lines[:b["start"]] + [new_line] + lines[b["end"]:]


def apply_delete(lines, blocks, line):
    b = need_item(blocks, line)
    before, after = lines[:b["start"]], lines[b["end"]:]
    # 顺手吃掉块后面紧跟的空行，免得删多了之后留一堆空行
    while after and not after[0].strip():
        after = after[1:]
    return before + after


def apply_insert(lines, blocks, after_line, fields, indent, make_node):
    """在 after_line 这一行**所在块的末尾**插入一条新条目。

    after_line 传 None / -1 表示插到文件最后。
    """
    new_line = render_item(fields, indent)
    if after_line is None or after_line < 0:
        # 追加到末尾：插在文件最后那串空行**之前**，不然新条目会飘到文件最外面
        k = len(lines)
        while k > 0 and not lines[k - 1].strip():
            k -= 1
        return lines[:k] + [new_line] + lines[k:]
    for b in blocks:
        if b["start"] <= after_line < b["end"] or b["start"] == after_line:
            return lines[:b["end"]] + [new_line] + lines[b["end"]:]
    raise EditError("第 %d 行找不到，可能页面已经刷新过，请重试" % after_line)


def _siblings(blocks, item):
    """找出和 item 同级（同缩进、同一个父级）的兄弟条目块。

    「同一个父级」在这里的判定：往前 / 往后走，遇到缩进更小的条目或者
    分类 / 分组标题就停 —— 说明已经跨出去了。
    """
    idx = blocks.index(item)
    out = []
    for b in blocks:
        if b["kind"] != "item":
            continue
        if b.get("indent", 0) == item.get("indent", 0):
            out.append(b)
    # 只保留"中间没有更浅层条目/分类/分组"的那一段连续区间
    head, tail = idx, idx

    def shallower(b):
        if b["kind"] in ("cat", "sub"):
            return True
        return b["kind"] == "item" and b.get("indent", 0) < item.get("indent", 0)

    while head - 1 >= 0 and not shallower(blocks[head - 1]):
        head -= 1
    while tail + 1 < len(blocks) and not shallower(blocks[tail + 1]):
        tail += 1
    win = set(id(x) for x in blocks[head:tail + 1] if x["kind"] == "item")
    return [x for x in out if id(x) in win]


def _move_range(lines, a, b):
    """交换 a、b 两个块的位置 —— 不管谁在上谁在下，结果都是两块对调，
    中间原本隔着的空行留在原地（不然反复上下移会让空行越攒越多）。"""
    first, second = (a, b) if a["start"] < b["start"] else (b, a)
    seg_first = lines[first["start"]:first["end"]]
    seg_second = lines[second["start"]:second["end"]]
    gap = lines[first["end"]:second["start"]]
    return (lines[:first["start"]] + seg_second + gap + seg_first
            + lines[second["end"]:])


def apply_move(lines, blocks, line, direction):
    """上移 / 下移一位（只跟同级兄弟换位置）。direction = -1 上移，+1 下移。"""
    item = need_item(blocks, line)
    sibs = _siblings(blocks, item)
    i = next((k for k, x in enumerate(sibs) if x is item), -1)
    if i < 0:
        raise EditError("找不到这个条目所在的同级位置")
    j = i + direction
    if j < 0 or j >= len(sibs):
        return None  # 已经在头/尾，什么都不做
    return _move_range(lines, item, sibs[j])


def apply_move_to(lines, blocks, src_line, dst_line):
    """拖拽排序：把 src 那一整块挪到 dst 的位置上（dst 顺势让开）。

    方向按「拖到哪儿就落在哪儿」来定，而不是一律插到后面：
        src 本来在 dst 下面 -> 往上拖 -> 落在 dst 前面
        src 本来在 dst 上面 -> 往下拖 -> 落在 dst 后面
    这样「拖到相邻那一条身上」一定会有变化，不会出现"拖了跟没拖一样"。

    不做成「连点很多次上移」，是因为那样中间任何一次出错都会留下
    一个改了一半的文件。这里一次性算好新顺序，一次落盘。
    """
    src = need_item(blocks, src_line)
    dst = need_item(blocks, dst_line)
    if src is dst:
        return lines
    si, di = src.get("indent", 0), dst.get("indent", 0)
    if si != di:
        raise EditError("只能在同一层里挪动：这一条缩进 %d，目标是 %d。"
                        "要换分组的话，先把两边缩进改成一样的。" % (si, di))
    seg = lines[src["start"]:src["end"]]
    rest = lines[:src["start"]] + lines[src["end"]:]
    if src["start"] < dst["start"]:
        pos = dst["end"] - len(seg)          # 往下拖：落在 dst 后面
    else:
        pos = dst["start"]                   # 往上拖：落在 dst 前面
    return rest[:pos] + seg + rest[pos:]


# ==========================================================================
# 五、往返自检：拼出来的行，必须能原样解析回同样的字段
# ==========================================================================

def roundtrip_cases():
    """覆盖各种组合，用来证明「拼行 -> 解析」是无损的。"""
    return [
        {"title": "IINA", "url": "https://iina.io/", "desc": "macOS 最强播放器",
         "note": "", "star": False, "plat": ["Mac"]},
        {"title": "《纳瓦尔宝典》", "url": "https://book.douban.com/subject/35751077/",
         "desc": "埃里克·乔根森", "note": "第一性原理那部分值得反复读", "star": True, "plat": []},
        {"title": "惠普 m126nw", "url": "", "desc": "用了三年还没坏", "note": "", "star": False, "plat": []},
        {"title": "纯名字没简述", "url": "", "desc": "", "note": "", "star": False, "plat": []},
        {"title": "手心输入法", "url": "https://www.xinshuru.com/", "desc": "干净，没广告",
         "note": "", "star": True, "plat": ["Win", "安卓"]},
        {"title": "只有短评没有简述", "url": "", "desc": "", "note": "就这一句", "star": False, "plat": []},
        {"title": "名字里带：冒号", "url": "https://example.com/", "desc": "有网址就不怕冒号",
         "note": "", "star": False, "plat": []},
        {"title": "网址在后面也认", "url": "https://example.org/a?b=1&c=2",
         "desc": "带查询串", "note": "备注", "star": True, "plat": ["网页"]},
    ]


def check_fields(f):
    """保存前把「这种写法本身有歧义」的情况挑出来。

    宁可拦下来讲清楚，也别存进去 —— 存进去就变成另一个东西了，
    而且下次打开时已经看不出原来是想要什么。
    """
    w = []
    title = (f.get("title") or "").strip()
    url = (f.get("url") or "").strip()
    desc = f.get("desc") or ""

    if not title:
        w.append("名字不能空着。")
    if url and not re.match(r"^https?://", url):
        w.append("网址要以 http:// 或 https:// 开头。")
    if url and ("]" in title or ")" in url or " " in url):
        w.append("名字里的「]」或网址里的「)」会让链接括号提前闭合，请换掉。")
    if ("：" in title or ":" in title) and not url:
        w.append("名字里有冒号、又没填网址 —— 冒号会被当成「名字 / 简述」的分界，"
                 "保存后会变成另一条。给这一条补个网址，或者把名字里的冒号换成「·」。")
    if "｜" in desc or "|" in desc:
        w.append("「简述」里不能有竖线 —— 竖线后面那截会被当成「短评」，"
                 "请把竖线去掉，或者直接写到短评那一栏。")
    return w


def selfcheck(make_node):
    """返回问题列表，空列表 = 全部通过。"""
    bad = []
    for f in roundtrip_cases():
        line = render_item(f, 4)
        text = BULLET_RE.match(line).group(2).strip()
        back = parse_item(make_node, text)
        for k in ("title", "url", "desc", "note", "star", "plat"):
            if back[k] != f[k]:
                bad.append("%s\n    拼出:%s\n    %s 对不上：%r -> %r"
                           % (f["title"], line, k, f[k], back[k]))
    return bad
