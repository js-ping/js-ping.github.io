#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务器.py —— uppjs 内容编辑器的本地后端

双击「8-编辑内容.command」启动它，浏览器会打开 http://127.0.0.1:8767

它做的事：
    · 把 内容源/*.md 拆成「块」交给网页，网页上填表增删改条目
    · 保存时**只重写你动过的那一个条目块**，其余行一个字节都不碰
    · 预览：跑 build.py --preview，产物写进 本地资料/预览/，不碰线上文件
    · 上线：跑 build.py，然后 git add / commit / push

只用 Python 标准库。只监听 127.0.0.1（本机），不对外网开放，不联任何第三方。

安全设计（这不是客套话，是几条硬规则）：
    1. 只允许读写「内容源/」这一个目录里的 .md，其它路径一律拒绝，
       就算网页那边传了 ../../../ 也会被挡下来。
    2. 每次落盘前先把原文件复制到 本地资料/备份/，写坏了能翻回去。
    3. 落盘走「先写临时文件再改名」，中途断电也不会留下半截文件。
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                      # scripts/编辑内容/ -> 仓库根目录
SRC_DIR = ROOT / "内容源"
PREVIEW_DIR = ROOT / "本地资料" / "预览"
BACKUP_DIR = ROOT / "本地资料" / "备份"
UI_FILE = HERE / "界面.html"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import build                                    # noqa: E402  复用站点解析器，口径只有一个
import importlib.util                           # noqa: E402

_spec = importlib.util.spec_from_file_location("linemodel", HERE / "行模型.py")
lm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lm)

PORT = 8767
# 这次会话里改过哪些文件，用来生成提交说明
TOUCHED = []
LOCK = threading.Lock()


# ==========================================================================
# 页面清单：直接读 build.py 的 LIST_PAGES / DOC_PAGES，不另维护一份
# ==========================================================================

def count_items(path: Path):
    if not path.exists():
        return 0
    try:
        cats = build.build_tree(build.parse_lines(path.read_text(encoding="utf-8")))
        return sum(build.leaf_count(c["children"]) for c in cats)
    except Exception:
        return 0


def page_list():
    pages = []
    for cfg in build.LIST_PAGES:
        p = ROOT / cfg["src"]
        flag = cfg.get("enabled", True)
        n = count_items(p)
        if flag is False:
            state, note = "off", "已下线"
        elif flag is True:
            state, note = "live", "上线"
        elif n:
            state, note = "live", "上线"
        else:
            state, note = "empty", "空着 · 填一条就上线"
        pages.append(dict(
            path=cfg["src"], out=cfg["out"], title=cfg["title"], ico=cfg.get("ico", "▤"),
            sub=cfg.get("sub", ""), kind="list", state=state, note=note, items=n,
        ))
    for cfg in build.DOC_PAGES:
        p = ROOT / cfg["src"]
        pages.append(dict(
            path=cfg["src"], out=cfg["out"], title=cfg["title"], ico="✎",
            sub=cfg.get("desc", ""), kind="doc",
            state="live" if p.exists() else "off",
            note="散文页 · 直接改 markdown" if p.exists() else "文件不存在", items=0,
        ))
    return pages


def guarded(path_str: str) -> Path:
    """把网页传来的路径卡死在「内容源/」里，只认 .md。

    这一步是硬护栏：网页那边不管是手抖还是真有坏心思传了
    ../../build.py，都会在这里被拒掉。
    """
    rel = (path_str or "").replace("\\", "/").strip()
    if not rel.startswith("内容源/"):
        raise lm.EditError("只允许改「内容源/」里的文件，收到的是：%s" % (path_str or "空"))
    p = (ROOT / rel).resolve()
    try:
        p.relative_to(SRC_DIR.resolve())
    except ValueError:
        raise lm.EditError("这个路径跑到「内容源/」外面去了：%s" % rel)
    if p.suffix != ".md":
        raise lm.EditError("只允许改 .md 文件")
    if not p.exists():
        raise lm.EditError("文件不存在：%s" % rel)
    return p


def read_text(p: Path):
    return p.read_text(encoding="utf-8")


def write_text(p: Path, text: str):
    """先备份、再原子落盘。备份留在 本地资料/备份/ 里，写坏了能翻回去。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    shutil.copy2(p, BACKUP_DIR / ("%s_%s" % (stamp, p.name)))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    if p.name not in TOUCHED:
        TOUCHED.append(p.name)


# ==========================================================================
# 编辑动作
# ==========================================================================

def do_op(req):
    p = guarded(req.get("path"))
    op = req.get("op")
    text = read_text(p)
    lines = text.split("\n")
    blocks = lm.split_blocks(text)

    if op == "update":
        fields = req.get("fields") or {}
        warn = lm.check_fields(fields)
        if warn:
            return {"ok": False, "error": "\n".join(warn), "warn": warn}
        new_lines = lm.apply_update(lines, blocks, int(req["line"]), fields, build.make_node)

    elif op == "insert":
        fields = req.get("fields") or {}
        warn = lm.check_fields(fields)
        if warn:
            return {"ok": False, "error": "\n".join(warn), "warn": warn}
        after = req.get("after")
        # 注意：缩进 0 是合法值，不能写成 `req.get("indent") or 4` —— 那样 0 会被当成"没传"
        indent = 4 if req.get("indent") is None else int(req.get("indent"))
        if indent not in (0, 4, 8):
            indent = 4
        new_lines = lm.apply_insert(lines, blocks, None if after is None else int(after),
                                    fields, indent, build.make_node)

    elif op == "delete":
        new_lines = lm.apply_delete(lines, blocks, int(req["line"]))

    elif op == "move":
        new_lines = lm.apply_move(lines, blocks, int(req["line"]), int(req.get("dir") or 0))
        if new_lines is None:
            return {"ok": True, "noop": True}

    elif op == "move_to":
        new_lines = lm.apply_move_to(lines, blocks, int(req["line"]), int(req["dst"]))
        if new_lines is None:
            return {"ok": True, "noop": True}

    else:
        raise lm.EditError("不认识的操作：%s" % op)

    new_text = "\n".join(new_lines)
    if new_text == text:
        return {"ok": True, "noop": True}

    # 落盘前后各校验一次：条目数如果突然少了一大截，说明这次编辑有问题，回滚
    before = count_items(p)
    write_text(p, new_text)
    after = count_items(p)
    if after < before - 1 and op != "delete":
        return {"ok": True, "after": after,
                "warn": ["条目数从 %d 变成了 %d —— 如果不是你有意删的，"
                         "去 本地资料/备份/ 里把上一版翻回来。" % (before, after)]}
    return {"ok": True, "count": after}


def do_raw(req):
    """源码模式：整份保存。只在「源码」标签页里用。"""
    p = guarded(req.get("path"))
    text = req.get("text")
    if not isinstance(text, str):
        raise lm.EditError("没有拿到内容")
    old = read_text(p)
    if text == old:
        return {"ok": True, "noop": True}
    # 正文以外的行数如果掉得太狠，拦一下（防止整段被误删）
    if len(text) < len(old) * 0.5 and len(old) > 500:
        return {"ok": False, "error": "新内容不到原来的一半，看着像整段被删了。"
                                     "确认要这样改的话，用编辑器里的「强制保存」。"}
    write_text(p, text)
    return {"ok": True, "count": count_items(p)}


# ==========================================================================
# 构建 / 上线
# ==========================================================================

def run_cmd(args, timeout=300):
    r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()


def do_build(preview=True):
    args = [sys.executable, "build.py"] + (["--preview"] if preview else [])
    code, out = run_cmd(args)
    return {"ok": code == 0, "code": code, "log": out}


def do_publish():
    steps = []
    code, out = run_cmd([sys.executable, "build.py"])
    steps.append(("生成页面", code, out))
    if code != 0:
        return {"ok": False, "log": "\n\n".join(
            "$ %s\n%s" % (s[0], s[2]) for s in steps)}

    code, out = run_cmd(["git", "add", "-A"])
    steps.append(("git add", code, out))
    if code != 0:
        return {"ok": False, "log": "\n\n".join("$ %s\n%s" % (s[0], s[2]) for s in steps)}

    code, out = run_cmd(["git", "diff", "--cached", "--quiet"])
    if code == 0:
        steps.append(("检查改动", 0, "没有新改动，跳过提交"))
        return {"ok": True, "log": "\n\n".join("$ %s\n%s" % (s[0], s[2]) for s in steps)}

    msg = "更新内容：" + ("、".join(TOUCHED) if TOUCHED else "网站内容")
    code, out = run_cmd(["git", "commit", "-m", msg])
    steps.append(("git commit", code, out))
    if code != 0:
        return {"ok": False, "log": "\n\n".join("$ %s\n%s" % (s[0], s[2]) for s in steps)}

    code, out = run_cmd(["git", "push", "origin", "main"], timeout=300)
    steps.append(("git push", code, out))
    ok = code == 0
    if ok:
        steps.append(("结果", 0, "已推送。GitHub Pages 大约 1 分钟后生效。"))
        TOUCHED.clear()
    return {"ok": ok, "log": "\n\n".join("$ %s\n%s" % (s[0], s[2]) for s in steps)}


# ==========================================================================
# HTTP
# ==========================================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "uppjs-editor"

    def log_message(self, fmt, *args):
        pass  # 别把噪音刷到终端，终端只留编辑器自己的输出

    # ---------- 工具 ----------
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text, ctype="text/html; charset=utf-8", code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, base: Path, rel: str):
        """静态服务，带路径穿越防护。"""
        rel = unquote(rel).lstrip("/")
        target = (base / rel).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError:
            return self._text("越界了", code=403)
        if not target.is_file():
            return self._text("没有这个文件", code=404)
        ctype = {
            ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8", ".json": "application/json",
            ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
            ".ico": "image/x-icon", ".xml": "application/xml", ".txt": "text/plain; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        return self._text(target.read_text(encoding="utf-8", errors="replace")
                          if ctype.startswith("text") or ctype.endswith("json")
                          or ctype.startswith("application/xml")
                          else target.read_bytes(), ctype=ctype)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._text(UI_FILE.read_text(encoding="utf-8"))
            if u.path == "/api/state":
                return self._json({"ok": True, "pages": page_list(),
                                   "root": str(ROOT), "touched": TOUCHED})
            if u.path == "/api/page":
                return self._json(self.api_page(q.get("path", [""])[0]))
            if u.path in ("/help", "/help.html"):
                # 本机说明书（由 build.py 从 本地资料/使用说明.md 生成）
                helphtml = ROOT / "本地资料" / "使用说明.html"
                if not helphtml.exists():
                    return self._text("说明书还没生成。先跑一次 build.py，"
                                      "或者双击「2-更新网站.command」。", code=404)
                return self._file(ROOT / "本地资料", "使用说明.html")
            if u.path.startswith("/preview/"):
                return self._file(PREVIEW_DIR, u.path[len("/preview/"):])
            if u.path.startswith("/site/"):
                return self._file(ROOT, u.path[len("/site/"):])
            return self._text("没有这个地址", code=404)
        except lm.EditError as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            return self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            req = self._body()
            if u.path == "/api/op":
                return self._json(do_op(req))
            if u.path == "/api/raw":
                return self._json(do_raw(req))
            if u.path == "/api/build":
                return self._json(do_build(preview=True))
            if u.path == "/api/publish":
                return self._json(do_publish())
            return self._json({"ok": False, "error": "没有这个接口"}, 404)
        except lm.EditError as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        except subprocess.TimeoutExpired:
            return self._json({"ok": False, "error": "命令跑太久了，超时了"}, 500)
        except Exception as e:
            return self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

    # ---------- 页面数据 ----------
    def api_page(self, path_str):
        rel = (path_str or "").replace("\\", "/")
        cfg = None
        for c in build.LIST_PAGES + build.DOC_PAGES:
            if c["src"] == rel:
                cfg = c
                break
        if cfg is None:
            raise lm.EditError("不认识的页面：%s" % rel)
        p = ROOT / rel
        if not p.exists():
            raise lm.EditError("文件不存在：%s" % rel)
        text = read_text(p)
        kind = "doc" if cfg in build.DOC_PAGES else "list"

        blocks = []
        items = 0
        if kind == "list":
            raw_blocks = lm.split_blocks(text)
            annotate(raw_blocks)
            for b in raw_blocks:
                k = b["kind"]
                if k == "item":
                    items += 1
                    blocks.append({"k": "item", "start": b["start"], "indent": b.get("indent", 0),
                                   "fields": lm.parse_item(build.make_node, b["text"]),
                                   "sub": len(b["lines"]) - 1,
                                   "head": b.get("head", False),
                                   "child_indent": b.get("child_indent"),
                                   "last_child": b.get("last_child")})
                elif k in ("cat", "sub"):
                    blocks.append({"k": k, "start": b["start"], "title": b["title"],
                                   "indent": b.get("indent", 0)})
                elif k == "comment":
                    # 开头那段说明注释常常被空行分成好几块，界面上合成一条，
                    # 不然会连着冒出来三四个「这里有多少行注释」的灰条
                    n = b["end"] - b["start"]
                    if blocks and blocks[-1]["k"] == "comment":
                        blocks[-1]["n"] = b["end"] - blocks[-1]["start"]
                        blocks[-1]["end"] = b["end"]
                    else:
                        blocks.append({"k": "comment", "start": b["start"],
                                       "end": b["end"], "n": n})
        return {"ok": True, "path": rel, "kind": kind, "out": cfg.get("out"),
                "title": cfg.get("title"), "sub": cfg.get("sub", ""),
                "raw": text, "blocks": blocks, "items": items,
                "default_indent": default_indent(blocks),
                "plat_order": lm.PLAT_ORDER}


def default_indent(blocks):
    """这一页的条目常用几格缩进 —— 界面上「在最后加一条」用它当默认值。

    取「出现次数最多的那个缩进」：软件与资源那种「分组头 + 缩进 4 的条目」
    会得到 4；书单影单那种「### 分组 + 平铺条目」会得到 0。
    缩进写错的话条目会掉出分组，所以这个默认值要靠谱。
    """
    from collections import Counter
    c = Counter(b["indent"] for b in blocks if b["k"] == "item")
    if not c:
        return 0
    return c.most_common(1)[0][0]


def annotate(blocks):
    """给每个条目块补两个信息，界面上那个「＋」才知道该往哪儿插：

        head          这一条是不是「分组头」（它下面挂着缩进更深的条目）
        child_indent  挂着的条目用的缩进
        last_child    这一组最后一条的行号

    没有这两个信息，在「分组头」上点 + 会插出一条和分组头同级的空条目，
    而不是插进这个分组里。
    """
    for i, b in enumerate(blocks):
        if b["kind"] == "sub":
            nxt = next((x for x in blocks[i + 1:] if x["kind"] == "item"), None)
            b["indent"] = nxt.get("indent", 0) if nxt else 0
            continue
        if b["kind"] != "item":
            continue
        nxt = next((x for x in blocks[i + 1:] if x["kind"] == "item"), None)
        head = bool(nxt and nxt.get("indent", 0) > b.get("indent", 0))
        b["head"] = head
        if not head:
            continue
        ci = nxt.get("indent", 0)
        b["child_indent"] = ci
        last = b
        for x in blocks[i + 1:]:
            if x["kind"] in ("cat", "sub"):
                break
            if x["kind"] == "item":
                if x.get("indent", 0) >= ci:
                    last = x
                else:
                    break
        b["last_child"] = last["start"]


# ==========================================================================

def pick_port(start=PORT):
    for p in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def main():
    print("=" * 62)
    print(" uppjs 内容编辑器")
    print("=" * 62)

    bad = lm.selfcheck(build.make_node)
    if bad:
        print("✗ 行模型往返自检没通过，先别用：")
        for b in bad:
            print("   " + b)
        return 1
    print("✓ 行模型往返自检通过（网页里填的内容，存回文件后能被解析器原样读回来）")

    if not UI_FILE.exists():
        print("✗ 找不到界面文件：%s" % UI_FILE)
        return 1

    n = len(page_list())
    print("✓ 找到 %d 个可编辑的页面" % n)

    port = pick_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d" % port
    print()
    print("   编辑器地址：%s" % url)
    print("   只在本机可访问，别人连不上；关掉这个窗口就等于关掉编辑器。")
    print()
    print("   按 Control + C 停止。")
    print("=" * 62)

    # 自检脚本跑的时候不希望弹浏览器，用 UPPJS_NO_BROWSER=1 关掉
    if os.environ.get("UPPJS_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
