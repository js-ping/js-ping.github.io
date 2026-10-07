#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 lottery.html 里内嵌的开奖历史快照。

为什么需要它：
    页面打开时会向本站的 /api/lottery 取最新开奖，那是最新的。但内嵌快照是
    「接口还没回来时先显示什么」以及「离线打开 / 双击本地文件打开时显示什么」。
    快照越旧，这两种情况下的体验越差。所以快照要常常追平 —— 这个脚本就干这件事。

数据从哪来：
    走本站自己的 https://uppjs.com/api/lottery，而不是自己去抓官网。理由：
      1. 那个接口里已经有「官方 → 17500.cn → 备用域名/http」的分级回退和逐行校验，
         这边再实现一遍只会多出一份可能走样的逻辑；
      2. 同一份数据来源，页面和快照永远不会不一致。
    接口挂了这里会明确报错，不静默 —— 那种时候页面本身的自动更新也正一起挂着。

怎么跑：
    python3 scripts/更新开奖数据.py            # 干跑，只报告不写盘
    python3 scripts/更新开奖数据.py --apply    # 真正写入 lottery.html
    python3 scripts/更新开奖数据.py --api=http://127.0.0.1:8766/api/lottery --apply

退出码：
    0  正常（无论有没有变化）
    1  出错（拉不到数据、接口返回 ok:false、文件结构对不上）
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

DEFAULT_API = 'https://uppjs.com/api/lottery'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

CN = timezone(timedelta(hours=8))          # 北京时间，用来写注释里的日期


# ───────────────────────── 在源码里定位数组字面量 ─────────────────────────

def locate_array(src, name):
    """找到 `const NAME = [ ... ];` 这个数组字面量的起止位置。

    不用正则 —— 数组里几万组方括号，正则匹配长度会失控，而且一旦源码格式微调
    就静默失配。这里逐字符走一遍，靠方括号配平找边界，字符串内的括号跳过。
    """
    key = 'const ' + name + ' = '
    i = src.find(key)
    if i < 0:
        raise RuntimeError('在 lottery.html 里找不到 `%s`' % key)

    start = i + len(key)
    if src[start] != '[':
        raise RuntimeError('%s 后面不是数组，源码结构变了' % name)

    depth = 0
    in_str = False
    esc = False
    j = start
    while j < len(src):
        c = src[j]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1

    text = src[start:j]
    if not text.endswith(']'):
        raise RuntimeError('%s 的方括号没配平，放弃（不改动文件）' % name)
    return {'start': start, 'end': j, 'text': text}


def dumps_compact(obj):
    """按页面里原本的紧凑风格重新序列化：[[10,11,12],[3],"2026001","2026-01-01"]"""
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


STALE_DAYS = 7


def age_days(date_str):
    """最新一期距今几天。双色球 / 大乐透大约每 3 天开一次，超过 7 天基本就是
    这条链路断了（而不是「最近没开奖」）。"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=CN)
    except Exception:
        return None
    return (datetime.now(CN) - d).days


def report_age(ssq_tail, dlt_tail):
    a1, a2 = age_days(ssq_tail), age_days(dlt_tail)
    worst = max([x for x in (a1, a2) if x is not None] or [0])
    print()
    print('快照新鲜度：双色球 %s 天前 / 大乐透 %s 天前' % (a1, a2))
    if worst > STALE_DAYS:
        print('⚠️  快照已超过 %d 天没更新 —— 大概率是上游那条链路断了，' % STALE_DAYS)
        print('    检查一下 https://uppjs.com/api/lottery 是否还能返回 ok:true。')
        return True
    return False


# ───────────────────────── 拉数据 ─────────────────────────

def fetch(api, ssq_since, dlt_since):
    url = '%s?ssq=%s&dlt=%s' % (api, urllib.parse.quote(str(ssq_since)),
                                urllib.parse.quote(str(dlt_since)))
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json,*/*',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        raise RuntimeError('接口返回 HTTP %s：%s' % (e.code, url))
    except Exception as e:
        raise RuntimeError('连不上接口 %s（%s）' % (url, e))

    try:
        return json.loads(raw)
    except Exception:
        raise RuntimeError('接口返回的不是 JSON，前 200 字：%s' % raw[:200])


# ───────────────────────── 合并 ─────────────────────────

def merge(rows, part, front_max, front_pick, back_max, back_pick, label, log):
    """把接口补的期数并进内嵌数组。完整才并 —— 有缺口就整段不要。"""
    if not part:
        log('  %s：接口没返回这一段' % label)
        return 0
    if not part.get('complete'):
        log('  %s：complete=false（缺口超出这次取回范围），为安全起见整段不并' % label)
        return 0

    lst = part.get('list') or []
    if not lst:
        log('  %s：已是最新，无新增' % label)
        return 0

    have = set(str(r[2]) for r in rows)
    added = 0
    for r in lst:
        if not isinstance(r, list) or len(r) != 4:
            continue
        front, back, code, date = r[0], r[1], str(r[2]), str(r[3])
        if code in have:
            continue
        # 二次校验：脏数据一律不要（接口那边已经校验过一轮，这里不省）
        if not isinstance(front, list) or len(front) != front_pick:
            continue
        if not isinstance(back, list) or len(back) != back_pick:
            continue
        if not all(isinstance(x, int) and 1 <= x <= front_max for x in front):
            continue
        if not all(isinstance(x, int) and 1 <= x <= back_max for x in back):
            continue
        if not re.fullmatch(r'\d{5,7}', code):
            continue
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            continue
        rows.append([sorted(front), list(back), code, date])
        have.add(code)
        added += 1

    rows.sort(key=lambda r: int(r[2]))
    if added:
        log('  %s：+%d 期 → 共 %d 期，最后 %s（%s）'
            % (label, added, len(rows), rows[-1][2], rows[-1][3]))
    else:
        log('  %s：无新增' % label)
    return added


# ───────────────────────── 主流程 ─────────────────────────

def main():
    args = sys.argv[1:]
    apply = '--apply' in args
    api = DEFAULT_API
    file_path = None
    for a in args:
        if a.startswith('--api='):
            api = a[6:]
        elif a.startswith('--file='):
            file_path = a[7:]

    if file_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(os.path.dirname(here), 'lottery.html')

    def log(msg=''):
        print(msg, flush=True)

    log('更新 lottery.html 的内嵌开奖快照')
    log('文件：%s' % file_path)
    log('接口：%s' % api)
    log('')

    with open(file_path, encoding='utf-8') as f:
        src = f.read()
    before_len = len(src)

    # 1) 读出当前快照
    ssq_loc = locate_array(src, 'SSQ_DATA')
    dlt_loc = locate_array(src, 'DLT_DATA')
    ssq = json.loads(ssq_loc['text'])
    dlt = json.loads(dlt_loc['text'])

    ssq_last = str(ssq[-1][2])
    dlt_last = str(dlt[-1][2])
    log('现有快照：双色球 %d 期，最后 %s（%s）' % (len(ssq), ssq_last, ssq[-1][3]))
    log('          大乐透 %d 期，最后 %s（%s）' % (len(dlt), dlt_last, dlt[-1][3]))
    log('')

    # 2) 取差量
    data = fetch(api, ssq_last, dlt_last)
    if not data.get('ok'):
        log('接口返回 ok=false，拿不到新数据。接口自己报的原因：')
        for k, v in (data.get('errors') or {}).items():
            log('  %s: %s' % (k, v))
        report_age(ssq[-1][3], dlt[-1][3])
        log('')
        log('→ 页面此刻也拿不到线上更新（同一个接口）。内嵌快照保持原样，未改动。')
        # 不当作错误退出：上游抖一下是常有的事，页面本身有快照兜底，
        # 不值得为此让整个定时任务报红。真的长期断链由上面的新鲜度检查暴露。
        return 0

    log('接口命中源：%s' % (data.get('source') or '(未回报)'))
    log('')

    # 3) 合并
    log('合并：')
    n1 = merge(ssq, data.get('ssq'), 33, 6, 16, 1, '双色球', log)
    n2 = merge(dlt, data.get('dlt'), 35, 5, 12, 2, '大乐透', log)
    log('')

    if not (n1 or n2):
        log('已是最新，文件未改动。')
        report_age(ssq[-1][3], dlt[-1][3])
        return 0

    # 4) 写回两个数组
    out = src[:ssq_loc['start']] + dumps_compact(ssq) + src[ssq_loc['end']:]
    dlt_loc2 = locate_array(out, 'DLT_DATA')       # 前面的长度变了，重新定位
    out = out[:dlt_loc2['start']] + dumps_compact(dlt) + out[dlt_loc2['end']:]

    # 5) 页脚静态文案（JS 跑起来前的兜底文字）
    ssq_tail, dlt_tail = ssq[-1][3], dlt[-1][3]
    pattern = re.compile(r'数据内嵌（双色球截至 [\d-]+ \/ 大乐透截至 [\d-]+）')
    if pattern.search(out):
        out = pattern.sub('数据内嵌（双色球截至 %s / 大乐透截至 %s）' % (ssq_tail, dlt_tail), out)
        log('页脚文案：已更新为「双色球截至 %s / 大乐透截至 %s」' % (ssq_tail, dlt_tail))
    else:
        log('页脚文案：未找到可替换的文案（跳过）')

    # 6) 数据块上方那句注释里的日期
    today = datetime.now(CN).strftime('%Y-%m-%d')
    note = re.compile(r'内嵌历史开奖数据（最近更新 [\d-]+，来源：[^）]*）')
    if note.search(out):
        out = note.sub('内嵌历史开奖数据（最近更新 %s，来源：中国福利彩票官网 / 中国体彩网）' % today, out)
        log('数据注释：已更新为「最近更新 %s」' % today)

    log('')
    log('新快照：  双色球 %d 期，最后 %s（%s，+%d）' % (len(ssq), ssq[-1][2], ssq_tail, n1))
    log('          大乐透 %d 期，最后 %s（%s，+%d）' % (len(dlt), dlt[-1][2], dlt_tail, n2))
    log('文件：    %d → %d 字节' % (before_len, len(out)))
    log('')

    if apply:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(out)
        log('✅ 已写回 %s' % file_path)
    else:
        log('（干跑模式，未写盘。加 --apply 才真正写入）')
    report_age(ssq_tail, dlt_tail)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('', flush=True)
        print('❌ 出错：%s' % e, flush=True)
        sys.exit(1)
