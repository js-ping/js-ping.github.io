#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成分享图（og:image）—— 1200×630，全站每页一张。

为什么要它：把网址发到微信 / 群里时，对方看到的卡片有没有图，点击率差很多。
没有 og:image 的站，分享出去就是一行灰字。

怎么跑：
    双击「4-生成分享图.command」，或者在网站文件夹里执行：
        python3 生成分享图.py

原理：把每一页的文案套进同一个 HTML 模板，
      用本机装好的 Chrome 无头模式截一张 1200×630 的图。
      **不联网、不装任何东西、不上传任何内容。**

产物：og/<页面名>.png（例如 og/apps.png）
      某个页面没有对应的图时，build.py 会自动回落到 og/default.png。
所以加新页面后想给它单独做一张，只要在下面 PAGES 里加一行再跑一次。
"""

import subprocess
import sys
import html
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent
OG_DIR = ROOT / "og"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

ACCENT = "#2f6fed"

# 页面名 -> (小标签, 主标题, 副标题)
PAGES = {
    "default":   ("uppjs.com", "软件与工具清单", "自己在用的软件、硬件与外设，整理成清单长期更新"),
    "index":     ("个人清单站", "uppjs.com", "软件与资源 · 文章归档 · 书影单 · 小工具"),
    "apps":      ("Mac · Windows · 手机 · 外设 + 免费资源", "软件与资源", "收录标准只有一条：我真的在用、而且用得住"),
    "articles":  ("公众号长文归档", "文章归档", "写过的长文，按主题归档，能搜、能分类"),
    "books":     ("读过的书", "书单", "带年份、评分和一句短评"),
    "movies":    ("看过的片子", "影单", "带年份、评分和一句短评"),
    "lottery":   ("纯离线小工具", "彩票选号", "双色球 / 大乐透 随机选号与购票核对"),
    "links":     ("在线工具 · 资源站", "网址书签", "常开的网站和在线工具，按用途分好类"),
    "about":     ("关于", "关于这个站", "是什么、为什么做、怎么做的"),
    "privacy":   ("隐私说明", "不收集你的任何数据", "没有统计脚本 · 没有 Cookie · 没有第三方请求"),
    "changelog": ("更新日志", "这个站一直在改", "每一次改动都记在这里"),
    "404":       ("404", "这个地址没有内容", "可能是链接打错了，或者是页面改过名字"),
}

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{width:1200px;height:630px;overflow:hidden}
  body{
    background:#f6f7f9;
    font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
    color:#1b1f24;
    position:relative;
  }
  /* 底纹：淡淡的点阵 + 右上角一片光 */
  .dots{
    position:absolute; inset:0;
    background-image:radial-gradient(#d7dbe2 1.4px, transparent 1.4px);
    background-size:26px 26px;
    opacity:.55;
  }
  .glow{
    position:absolute; width:760px; height:760px; right:-260px; top:-330px;
    background:radial-gradient(closest-side, ACCENT_SOFT, transparent 72%);
    border-radius:50%;
  }
  .glow2{
    position:absolute; width:520px; height:520px; left:-220px; bottom:-300px;
    background:radial-gradient(closest-side, #e6ecf7, transparent 70%);
    border-radius:50%;
  }
  .bar{position:absolute; left:0; top:0; width:14px; height:100%;
       background:linear-gradient(180deg, ACCENT, #7aa7ff)}
  .card{position:absolute; inset:0; padding:74px 84px; display:flex; flex-direction:column}
  .kicker{
    font-size:25px; letter-spacing:.16em; color:ACCENT; font-weight:600;
    text-transform:uppercase; margin-bottom:26px;
  }
  h1{
    font-size:86px; line-height:1.14; font-weight:800; letter-spacing:-.02em;
    max-width:960px;
  }
  h1.sm{font-size:66px}
  .sub{
    margin-top:30px; font-size:31px; line-height:1.5; color:#5b626b;
    max-width:930px; font-weight:400;
  }
  .foot{
    margin-top:auto; display:flex; align-items:center; gap:16px;
    font-size:26px; color:#767e89; font-weight:500;
  }
  .foot .dot{width:9px; height:9px; border-radius:50%; background:ACCENT}
  .foot b{color:#1b1f24; font-weight:700; letter-spacing:.01em}
  .glyph{
    position:absolute; right:64px; bottom:44px; font-size:230px; line-height:1;
    color:#e8ebf0; font-weight:800; letter-spacing:-.04em; user-select:none;
  }
</style></head>
<body>
  <div class="dots"></div><div class="glow"></div><div class="glow2"></div>
  <div class="bar"></div>
  <div class="card">
    <div class="kicker">KICKER</div>
    <h1 class="TITLE_CLS">TITLE</h1>
    <div class="sub">SUB</div>
    <div class="foot"><span class="dot"></span><b>uppjs.com</b><span>CLOSE</span></div>
  </div>
  <div class="glyph">GLYPH</div>
</body></html>
"""


def find_chrome():
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def render(chrome, name, kicker, title, sub, profile, wait=30):
    """截一张图。

    注意：无头 Chrome 在 macOS 上截完图之后经常不肯自己退出（进程挂着），
    所以这里不等它结束 —— 轮询产物文件，图一落地就把进程收掉。
    """
    glyph = name
    if name in ("index", "default"):
        glyph = "uppjs"
    page = (TEMPLATE
            .replace("ACCENT_SOFT", "#dbe6fd")
            .replace("ACCENT", ACCENT)
            .replace("KICKER", html.escape(kicker))
            .replace("TITLE_CLS", "sm" if len(title) > 8 else "")
            .replace("TITLE", html.escape(title))
            .replace("SUB", html.escape(sub))
            .replace("CLOSE", html.escape("· 整理成清单，长期更新"))
            .replace("GLYPH", html.escape(glyph)))
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "card.html"
        hp.write_text(page, encoding="utf-8")
        out = OG_DIR / f"{name}.png"
        if out.exists():
            out.unlink()
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--no-default-browser-check", "--disable-extensions",
               f"--user-data-dir={profile}",
               "--force-device-scale-factor=1", "--window-size=1200,630",
               f"--screenshot={out}", hp.as_uri()]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = time.time() + wait
        ok = False
        while time.time() < deadline:
            if out.exists() and out.stat().st_size > 4000:
                time.sleep(0.5)      # 让它把文件写完
                if out.stat().st_size > 4000:
                    ok = True
                    break
            if proc.poll() is not None:
                ok = out.exists() and out.stat().st_size > 4000
                break
            time.sleep(0.25)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
        if not ok:
            print("  ✗ %s: 渲染失败" % name)
        return ok


def main():
    chrome = find_chrome()
    if not chrome:
        print("找不到 Chrome / Chromium / Edge，无法生成分享图。")
        print("装了 Chrome 之后再跑一次即可；不跑也不影响网站 —— ")
        print("build.py 找不到 og/<页面>.png 时会自动回落到 og/default.png。")
        return 1
    OG_DIR.mkdir(exist_ok=True)
    print("用 %s" % chrome)
    ok = 0
    with tempfile.TemporaryDirectory() as profile:
        for name, (kicker, title, sub) in PAGES.items():
            if render(chrome, name, kicker, title, sub, profile):
                size = (OG_DIR / f"{name}.png").stat().st_size // 1024
                print("  ✓ og/%s.png  (%d KB)" % (name, size))
                ok += 1
    print("\n完成：%d/%d 张，都在 og/ 目录里。" % (ok, len(PAGES)))
    print("想改文案，改本文件顶部的 PAGES，再跑一次。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
