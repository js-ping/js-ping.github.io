#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
链接体检 —— 用你本机的真实网络，逐条测「软件与资源」页里每个链接能不能打开。

怎么跑：
    双击「6-体检链接.command」，或者在网站文件夹里执行：
        python3 体检链接.py

做什么：
    1. 从 内容源/软件与资源.md 里取出全部链接；
    2. 逐条真实访问，记录状态码和耗时；
    3. 把结论写进 free-region.json；
    4. 接着双击「2-更新网站.command」，页面上的「慢 / 需代理」标记就换成实测结果。

注意：这一页现在是「软件 + 硬件 + 免费资源」合并后的一份，链接有三百多条，
      跑一轮比原来久（大概 4~6 分钟），中途别关窗口。

判定标准（写死在这里，想改就改）：
    连不上 / 超时          -> proxy（页面上标「需代理」）
    401 / 403 / 429        -> slow（站点反爬，浏览器手动打开通常是正常的）
    2xx / 3xx 且 3 秒内      -> cn（页面上不出徽章，但属于「国内直连」）
    2xx / 3xx 但超过 3 秒    -> slow
    其它 4xx / 5xx          -> slow

为什么要重试：
    网络偶发抖动很常见。一次连不上就判定「需代理」会误伤 —— 脚本对连不上的
    会换更长的超时再试两次，三次都失败才算。

一句话记住：这个脚本只管「链接还活着吗」，不管「该不该收它」。后者是你的事。
"""

import concurrent.futures
import datetime
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
FREE_SRC = ROOT / "内容源" / "软件与资源.md"
REGION_FILE = ROOT / "free-region.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SLOW_MS = 3000
WORKERS = 8


def load_build():
    """借用 build.py 的解析器，保证「脚本看到的条目」和「页面渲染的条目」完全一致。"""
    spec = importlib.util.spec_from_file_location("uppjs_build", ROOT / "build.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["uppjs_build"] = mod
    spec.loader.exec_module(mod)
    return mod


def level_of(code, ms):
    if code == "000":
        return "proxy"
    if code in ("401", "403", "429"):
        return "slow"
    if code.startswith(("2", "3")):
        return "cn" if ms < SLOW_MS else "slow"
    return "slow"


def probe(url, timeout):
    """返回 (状态码, 耗时毫秒, 错误摘要)。"""
    try:
        p = subprocess.run(
            ["curl", "-sSL", "-o", "/dev/null",
             "-w", "%{http_code} %{time_total}",
             "-A", UA, "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout * 2 + 20)
        parts = p.stdout.strip().split()
        code = parts[0] if parts else "000"
        ms = int(float(parts[1]) * 1000) if len(parts) > 1 else 0
        err = p.stderr.strip().split("\n")[-1][:70] if p.stderr.strip() else ""
        return code, ms, err
    except Exception as e:
        return "000", 0, str(e)[:70]


def probe_hard(url):
    """连不上的再给两次机会（换更长超时），避免把网络抖动误判成「需代理」。"""
    last = probe(url, 20)
    if level_of(last[0], last[1]) != "proxy":
        return last
    for t in (30, 30):
        cur = probe(url, t)
        if level_of(cur[0], cur[1]) != "proxy":
            return cur
    return last


def main():
    if not FREE_SRC.exists():
        print("✗ 找不到 内容源/软件与资源.md，确认这个脚本和「内容源」文件夹在同一处。")
        return 1

    b = load_build()
    cats = b.build_tree(b.parse_lines(FREE_SRC.read_text(encoding="utf-8")))
    items = [(n["title"], n["url"]) for _c, n in b.iter_leaf_items(cats) if n.get("url")]
    if not items:
        print("✗ 内容源/软件与资源.md 里没找到带链接的条目。")
        return 1

    print("=" * 64)
    print("开始体检：%d 条链接，大约 1~2 分钟，别关窗口" % len(items))
    print("测的是你这台机器、当前网络的真实情况。")
    print("=" * 64)

    results = {}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(probe_hard, u): (n, u) for n, u in items}
        for f in concurrent.futures.as_completed(futs):
            name, url = futs[f]
            code, ms, err = f.result()
            lvl = level_of(code, ms)
            results[url] = {"name": name, "level": lvl, "code": code, "ms": ms}
            done += 1
            sym = {"cn": "通", "slow": "慢", "proxy": "断"}[lvl]
            print("[%3d/%d] %s  %-26s %-5s %sms" % (done, len(items), sym, name, code, ms))

    stat = Counter(r["level"] for r in results.values())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = {
        "_说明": "各链接的国内访问情况实测结果。cn=国内直连，slow=时快时慢，proxy=需代理。"
               "由「6-体检链接.command」自动生成。条目按网址索引。",
        "_更新时间": now,
        "_来源": "本机实测",
        "_统计": dict(stat),
        "urls": {u: r["level"] for u, r in sorted(results.items())},
    }
    REGION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")

    print()
    print("=" * 64)
    print("国内直连 %d 条 · 时快时慢 %d 条 · 需代理 %d 条"
          % (stat.get("cn", 0), stat.get("slow", 0), stat.get("proxy", 0)))
    print("结果已写入 free-region.json（更新时间 %s）" % now)

    dead = sorted((r["name"], u) for u, r in results.items() if r["level"] == "proxy")
    if dead:
        print()
        print("【本机连不上，页面会上标成「需代理」】")
        for name, url in dead:
            print("   %-26s %s" % (name, url))
        print("   只有一两条的话，多半是站点临时故障或本机网络波动，重跑一次即可刷新。")

    print()
    print("下一步：双击「2-更新网站.command」，页面上的标记就换成这份实测结果。")
    print("提醒：这份结果反映的是【你现在这台机器、当前网络】。")
    print("      开着代理跑，结果会和关掉代理不一样。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
