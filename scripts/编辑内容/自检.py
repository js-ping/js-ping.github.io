#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自检.py —— 编辑器的一键回归测试

跑法：双击「自检.command」，或者在终端里
        /usr/bin/python3 "scripts/编辑内容/自检.py"

测的是三件最要命的事：
    ① 拼行 / 解析往返无损 —— 网页里填的东西存回文件后，网站读到的还是同一份
    ② 改动不越界 —— 只动你编的那一条，别处（尤其是开头那几十行注释）一个字节不碰
    ③ 各种编辑动作的正确性 —— 增 / 改 / 删 / 上移 / 下移 / 拖拽，以及该拦的能拦住

全部在临时副本上跑，不碰真实的 内容源/。
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

sys.path.insert(0, str(ROOT))
import build                                     # noqa: E402

_spec = importlib.util.spec_from_file_location("linemodel", HERE / "行模型.py")
lm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lm)

OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  " + detail) if detail else ""))


def edit(text, op, **kw):
    """在给定文本上跑一次编辑，返回新文本。"""
    lines = text.split("\n")
    blocks = lm.split_blocks(text)
    if op == "update":
        new = lm.apply_update(lines, blocks, kw["line"], kw["fields"], build.make_node)
    elif op == "insert":
        new = lm.apply_insert(lines, blocks, kw.get("after"), kw["fields"],
                              kw.get("indent", 0), build.make_node)
    elif op == "delete":
        new = lm.apply_delete(lines, blocks, kw["line"])
    elif op == "move":
        r = lm.apply_move(lines, blocks, kw["line"], kw["dir"])
        return text if r is None else "\n".join(r)
    elif op == "move_to":
        new = lm.apply_move_to(lines, blocks, kw["line"], kw["dst"])
    else:
        raise ValueError(op)
    return "\n".join(new)


def items_of(text):
    """按 build.py 的口径把条目读出来，用于对账。"""
    cats = build.build_tree(build.parse_lines(text))
    out = []

    def walk(ns):
        for n in ns:
            if n["children"] and not n["has_link"]:
                walk(n["children"])
            else:
                out.append((n["title"], n["url"], n["desc"], n["note"], bool(n["star"])))
    for c in cats:
        walk(c["children"])
    return out


# ==========================================================================
print()
print("① 拼行 / 解析 往返无损")
print("-" * 60)
bad = lm.selfcheck(build.make_node)
check("往返自检（%d 组用例）" % len(lm.roundtrip_cases()), not bad)
for b in bad:
    print("     " + b)

print()
print("② 歧义写法要拦下来，不能存进去变成别的东西")
print("-" * 60)
w = lm.check_fields({"title": "《手册》：第一版", "url": "", "desc": "", "note": ""})
check("名字带冒号又没网址 -> 拦住", bool(w))
w = lm.check_fields({"title": "正常", "url": "https://a.com/", "desc": "前面｜后面", "note": ""})
check("简述里塞竖线 -> 拦住", bool(w))
w = lm.check_fields({"title": "正常", "url": "ftp://a.com/", "desc": "", "note": ""})
check("网址不是 http(s) -> 拦住", bool(w))
w = lm.check_fields({"title": "", "url": "", "desc": "", "note": ""})
check("名字空着 -> 拦住", bool(w))
w = lm.check_fields({"title": "《置身事内》", "url": "https://book.douban.com/x/",
                     "desc": "兰小欢", "note": "讲得比教科书明白", "star": True,
                     "plat": ["Mac"]})
check("正常内容 -> 放行", not w)

# ==========================================================================
print()
print("③ 增 / 改 / 删 / 排序 的实际效果")
print("-" * 60)

FIX = """<!--
  这一段是文件开头的说明注释，编辑器绝不能动它。
  第二行也一样。
-->

## 2026 年

### 读完

- ☆ [《置身事内》](https://book.douban.com/subject/35546622/)：兰小欢｜讲得比教科书明白
- [《纳瓦尔宝典》](https://book.douban.com/subject/35751077/)：埃里克·乔根森｜值得反复读

### 在读

- 一本还没读完的书：占个位
"""

n0 = len(items_of(FIX))
check("原始文件读到 3 条", n0 == 3, "实际 %d" % n0)

NEW = {"title": "《刻意练习》", "url": "https://book.douban.com/subject/26934348/",
       "desc": "安德斯·艾利克森", "note": "针对性训练那章最有用", "star": False, "plat": []}
t = edit(FIX, "insert", after=None, indent=0, fields=NEW)
check("追加一条 -> 变成 4 条", len(items_of(t)) == 4)
check("新条目拼写正确", "- [《刻意练习》](https://book.douban.com/subject/26934348/)"
      "：安德斯·艾利克森｜针对性训练那章最有用" in t)

# 在第 7 行（`- ☆ 《置身事内》`）后面插一条，应该落进「读完」这一组
lines_fix = FIX.split("\n")
line_shz = next(i for i, x in enumerate(lines_fix) if "置身事内" in x)
t = edit(FIX, "insert", after=line_shz, indent=0, fields=dict(NEW, title="《插在中间》"))
idx_new = t.split("\n").index([x for x in t.split("\n") if "《插在中间》" in x][0])
idx_old = [i for i, x in enumerate(t.split("\n")) if "纳瓦尔宝典" in x][0]
check("插在中间 -> 落在指定位置", idx_new == line_shz + 1 and idx_new < idx_old,
      "新条目在第 %d 行" % idx_new)

t2 = edit(t, "update", line=idx_new, fields=dict(NEW, title="《改过名字的》", star=True))
check("改一条 -> 名字和 ☆ 都生效",
      any(x[0] == "《改过名字的》" and x[4] for x in items_of(t2)))
check("改一条 -> 条数没变", len(items_of(t2)) == len(items_of(t)))

t3 = edit(t2, "delete", line=idx_new)
check("删一条 -> 条数回落", len(items_of(t3)) == 3)

t4 = edit(FIX, "move", line=line_shz, dir=1)
check("下移一位 -> 两条对调",
      [x[0] for x in items_of(t4)][:2] == ["《纳瓦尔宝典》", "《置身事内》"])
t5 = edit(t4, "move", line=line_shz + 1, dir=-1)
check("再上移一位 -> 换回来", [x[0] for x in items_of(t5)][:2] == ["《置身事内》", "《纳瓦尔宝典》"])
t6 = edit(FIX, "move", line=line_shz, dir=-1)
check("已经在头 -> 不乱动", t6 == FIX)

line_nwe = next(i for i, x in enumerate(FIX.split("\n")) if "纳瓦尔宝典" in x)
t7 = edit(FIX, "move_to", line=line_nwe, dst=line_shz)
check("拖拽：下面的拖到上面那条 -> 对调",
      [x[0] for x in items_of(t7)][:2] == ["《纳瓦尔宝典》", "《置身事内》"])
t8 = edit(FIX, "move_to", line=line_shz, dst=line_nwe)
check("拖拽：上面的拖到下面那条 -> 也换位",
      [x[0] for x in items_of(t8)][:2] == ["《纳瓦尔宝典》", "《置身事内》"])

# ==========================================================================
print()
print("④ 改动不越界（这条最要命：注释和别人的行必须一个字节都不动）")
print("-" * 60)

real = ROOT / "内容源" / "软件与资源.md"
if real.exists():
    src = real.read_text(encoding="utf-8")
    src_lines = src.split("\n")
    blocks = lm.split_blocks(src)
    first_item = next(b for b in blocks if b["kind"] == "item")
    f = lm.parse_item(build.make_node, first_item["text"])
    f = dict(f, note="自检临时改的短评")
    after = edit(src, "update", line=first_item["start"], fields=f)
    a_lines = after.split("\n")
    check("行数没变", len(a_lines) == len(src_lines),
          "%d -> %d" % (len(src_lines), len(a_lines)))
    diff = [i for i in range(min(len(a_lines), len(src_lines)))
            if a_lines[i] != src_lines[i]]
    check("只有被编辑的那一行变了", diff == [first_item["start"]],
          "变动行：%s（预期 %d）" % (diff, first_item["start"]))
    head = "\n".join(src_lines[:first_item["start"]])
    check("文件开头 %d 行（含说明注释）逐字节相同"
          % first_item["start"], after.startswith(head))
    check("条目总数没变", len(items_of(after)) == len(items_of(src)))
    # 再验证一次：update 一个条目后，把新文本解析回来，字段应该就是我们写进去的
    blocks2 = lm.split_blocks(after)
    b2 = next(b for b in blocks2 if b["kind"] == "item" and b["start"] == first_item["start"])
    back = lm.parse_item(build.make_node, b2["text"])
    check("改完再读回来，字段一模一样", back == f, "%s" % (back if back != f else ""))
else:
    check("找到 内容源/软件与资源.md", False, "文件不存在，跳过这一组")

# ==========================================================================
print()
print("⑤ 该拦的拦住")
print("-" * 60)
try:
    lm.need_item(lm.split_blocks(FIX), 3)          # 第 3 行是注释，不是条目
    check("对着非条目行改动 -> 报错", False)
except lm.EditError:
    check("对着非条目行改动 -> 报错", True)

# ==========================================================================
print()
print("=" * 60)
if BAD:
    print("✗ 没通过 %d 项：" % len(BAD))
    for b in BAD:
        print("   - " + b)
    sys.exit(1)
print("✓ 全部通过（%d 项）" % len(OK))
sys.exit(0)
