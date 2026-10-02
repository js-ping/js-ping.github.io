# -*- coding: utf-8 -*-
"""把浏览器导出书签的标题清洗成「看得懂的名字」。

输入：- [一串 SEO 垃圾](带跟踪参数的链接)
输出：- [干净的名字](干净链接)

用法：在项目目录里执行  python3 整理书签.py
"""
import io
import re

P = 'links.md'
s = io.open(P, encoding='utf-8').read()
LINE = re.compile(r'^(\s*)- \[(.*)\]\((\S+?)\)(.*)$')

# ---------------------------------------------------------------- URL

TRACK = re.compile(
    r'^(utm_[a-z]+|from|ref|referrer|source|spm|spm_id_from|share[a-z_]*|'
    r'_fid|_t|t|wdorigin|wdfrom|timestamp|cmpid|scene|src|sa|ved|'
    r'vd_source|tab|fr|clicktime|session_id|invite_code|f|tjlb|depth_1)$', re.I)
BAD_FRAG = {'readme', 'download', 'top', 'main', 'content', 'index', 'toc',
            'readme-ov-file', 'readme_zh', 'readme-cn', 'downloads',
            'install', 'rs'}


def clean_url(u):
    u = u.strip()
    head, _, frag = u.partition('#')
    base, _, q = head.partition('?')
    if q:
        keep = [kv for kv in q.split('&')
                if kv and not TRACK.match(kv.split('=')[0])]
        base += ('?' + '&'.join(keep)) if keep else ''
    if frag and frag.lower().split('=')[0] not in BAD_FRAG:
        return base + '#' + frag
    return base


def host_of(u):
    m = re.match(r'https?://([^/?#]+)', u, re.I)
    if not m:
        return ''
    h = m.group(1).lower().split('@')[-1].split(':')[0]
    return h[4:] if h.startswith('www.') else h


def is_root(u):
    m = re.match(r'https?://[^/?#]+(/[^?#]*)', u, re.I)
    p = (m.group(1) if m else '/') or '/'
    return re.sub(r'^/(zh|zh-cn|zh-hans-cn|cn|en|index\.html?)/?$', '/', p,
                  flags=re.I) == '/'


# ---------------------------------------------------------------- 词表

EMOJI = re.compile(
    '[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF'
    '\uFE0F\u2B00-\u2BFF\u2190-\u21FF\u2700-\u27BF]+')
ZERO_W = re.compile('[\u200b-\u200f\u202a-\u202e\u2060\ufeff]')

JUNK_WORDS = re.compile(
    r'官网|官方|首页|网站|网址|下载|免费|开源|大全|导航|集合|合集|汇总|'
    r'平台|神器|指南|攻略|教程|文档|手册|博客|专栏|社区|论坛|资讯|新闻|'
    r'资源|素材|工具集|工具网|软件|应用|中文版|汉化|学院|课程|品牌|'
    r'最好|最佳|最强|最全|领先|专业|一站式|在线|世界|梦想|正版|'
    r'高效|便捷|轻松|强大|简单|快速|实用|智能|创意|购买|特价|'
    r'Free|Download|Online|Official|Homepage|Home|Best|Documentation|Docs|'
    r'Browse|Archive|Library|Portal|Platform|Community|Blog|Tutorial|Stock')

SITE_TAIL = re.compile(
    r'^(知乎|知乎专栏|简书|掘金|稀土掘金|CSDN|博客园|开源中国|OSCHINA|'
    r'百度|腾讯云|阿里云|InfoQ|GitHub|Bilibili|哔哩哔哩|YouTube|少数派|'
    r'阮一峰的网络日志|SegmentFault|思否|51CTO|脚本之家|菜鸟教程|慕课网|'
    r'博客频道|个人文章|经验分享|Obsidian 中文论坛|挖互联网|Medium|'
    r'Dev\.to|Reddit|Stack Overflow|Hacker News|掘金社区|博客|频道|专栏|'
    r'软件|汉化|资源分享|官网|首页)'
    r'(\s*[·|｜].*)?$', re.I)

LEAD_JUNK = re.compile(
    r'^(\(\d+条消息\)|（\d+条消息）|【[^】]{1,12}】|\[[^\]]{1,12}\]|'
    r'在线版|在线阅读|在线|免费|开源|超长|推荐|分享|'
    r'Download|Get|Buy|Try)\s*[:：,，]?\s*', re.I)

DROP_SEG = re.compile(
    r'^(官方网站|官网|官方|首页|网站|网址|下载页面|下载页|下载地址|下载|'
    r'网页版|免费|开源|在线|中文网|中文站|帮助中心|旗舰店)$')

TAIL_JUNK = re.compile(
    r'\s*[-–—_·|｜]\s*$|(官网|官方网站|官方|下载页面|下载页|'
    r'下载地址|网页版|官方下载)\s*$|'
    r'\s*[（(][^）)]{0,16}[）)]?\s*$')

VER = re.compile(r'\s*\bv?\d+(?:\.\d+){1,3}\b')
SEP = re.compile(r'\s*[|｜丨]\s*|\s+[—–-]\s+|\s*·\s*|\s*[：:]\s+|\s*[-–—]{2,}\s*')
LATIN_HEAD = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9 .+#_\-]{1,26}?)\s+(?=[\u4e00-\u9fff（(])')

GH = re.compile(r'^https?://github\.com/([^/]+)/([^/#?]+)', re.I)
GH_NON = {'orgs', 'users', 'topics', 'collections', 'sponsors', 'features',
          'about', 'settings', 'login', 'apps', 'marketplace', 'explore',
          'trending', 'search', 'notifications', 'pulls', 'issues'}

# 少数站点标题没法自动还原，直接指定名字（按 URL 正则匹配）
ALIAS = [
    (r'pixabay\.com', 'Pixabay'), (r'coverr\.co', 'Coverr'),
    (r'videvo\.net', 'Videvo'), (r'vox\.rocks', 'VOX'),
    (r'qiuziti\.com', '求字体网'),
    (r'sxt\.cn/Java', '速学堂 · Java 课程'), (r'sxt\.cn/?$', '速学堂'),
    (r'coding\.net/help', 'CODING 帮助中心'),
    (r'better365\.cn/apps', 'Better365 产品页'),
    (r'okaapps\.com/product', 'VidHub · 下载页'),
    (r'fuun\.fun/top/shadiao', 'FUUN.FUN · 沙雕网站'),
    (r'devdocs\.io', 'DevDocs'),
    (r'bz6000\.cn', '百战程序员'), (r'better365\.cn', 'Better365'),
    (r'aquasnap\.cn', 'AquaSnap'), (r'th-sjy\.com', 'th_sjy'),
    (r'30aitool\.com', '30Tool'), (r'nanophoto\.ai', 'NanoPhoto.AI'),
    (r'sando\.cn', '配音网'), (r'znds\.com', 'ZNDS 智能电视网'),
    (r'dfrobot\.com\.cn', 'Arduino 中文社区'), (r'dudianji\.com', '读典籍'),
    (r'lxwc\.com\.cn', '两小无猜网'), (r'wxxdh\.com', '二次元导航'),
    (r'rilijingling\.com', '日历精灵'), (r'httpcn\.com', '汉程国学网'),
    (r'v2fy\.com', '方圆小站'), (r'yxzhi\.com', 'TVBox 资源站'),
    (r'coding\.net', 'CODING'), (r'extfans\.com', 'Extfans'),
    (r'plugins\.jetbrains\.com/plugin/13710', '中文语言包'),
    (r'zh\.okaapps\.com', 'VidHub'), (r'dashgame\.com', 'Font Awesome'),
    (r'babeljs\.cn', 'Babel'), (r'alfredapp\.com|folivora\.ai', 'Alfred'),
    (r'peazip\.github\.io', 'PeaZip'),
    (r'github\.com/desktop|desktop\.github\.com', 'GitHub Desktop'),
    (r'z\.2rdh\.com', 'Z-Library'),
    (r'chatgpt\.com/\S*download', 'ChatGPT 下载'),
    (r'multipost\.app/install', 'MultiPost 安装引导'),
    (r'multipost\.app', 'MultiPost'), (r'blog\.sina\.com\.cn', '新浪博客'),
    (r'ccswitch\.io', 'CC Switch'), (r'ng-zorro|ng\.ant\.design', 'NG-ZORRO'),
    (r'learn-anything', 'Learn Anything'), (r'gitee\.com', '码云 Gitee'),
    (r'wuyou\.net', '无忧启动论坛'), (r'qdfuns\.com/?$', '前端网'),
]


def junk_head(seg):
    """这一段能不能当名字：站点名或宣传词就不行。"""
    seg = seg.strip()
    if not seg:
        return True
    return bool(SITE_TAIL.match(seg) or JUNK_WORDS.search(seg))


def junk_tail(seg):
    """这一段像不像宣传语。单个西文单词（Switch、LibreCAD）不算。"""
    seg = seg.strip()
    if junk_head(seg):
        return True
    if re.search(r'[\u4e00-\u9fff]', seg):
        return False
    return len(seg) >= 5 and ' ' in seg


def cut_head(t):
    segs = [x.strip() for x in SEP.split(t) if x.strip()]
    segs = [x for x in segs if not DROP_SEG.match(x)]
    if len(segs) < 2:
        return t
    # 开头那段本身就是宣传语（「免费素材照片 · Pexels」）-> 丢掉
    while len(segs) > 1 and junk_head(segs[0]) and not junk_head(segs[1]):
        segs = segs[1:]
    out = [segs[0]]
    for x in segs[1:]:
        if junk_head(x) or junk_tail(x):
            break
        out.append(x)
    t2 = ' '.join(out).strip()
    return t2 if 2 <= len(t2) < len(t) else t


def cut_latin_head(t):
    """「CC Switch 官方网站 - AI 编程工具统一管理平台」-> CC Switch"""
    m = LATIN_HEAD.match(t)
    if not m:
        return t
    head, rest = m.group(1).strip(), t[m.end():].strip()
    if len(head) < 6 and len(head.split()) < 2:
        return t
    if junk_tail(rest) and len(head) >= 4 and not junk_head(head):
        return head
    return t


def clean_title(t, u):
    t = EMOJI.sub(' ', ZERO_W.sub('', t))
    t = re.sub(r':[a-z0-9_+-]{2,28}:', '', t)
    t = re.sub(r'\s+', ' ', t).strip()

    for pat, name in ALIAS:
        if re.search(pat, u, re.I):
            return name

    gh = GH.match(u)
    if gh and gh.group(1).lower() not in GH_NON:
        base = '%s/%s' % (gh.group(1), re.sub(r'\.git$', '', gh.group(2)))
        if re.search(r'/(releases|tags)\b', u):
            return base + ' 发布页'
        if '/issues' in u:
            return base + ' Issues'
        fm = re.match(r'https?://github\.com/[^/]+/[^/]+/(?:blob|tree|raw)/'
                      r'[^/]+/(.+?)(?:[?#]|$)', u, re.I)
        if fm:
            repo = base.split('/', 1)[1].lower()
            fn = fm.group(1).rstrip('/').split('/')[-1]
            fn = re.sub(r'\.(md|markdown|txt|pdf|html?)$', '', fn, flags=re.I)
            low = fn.lower()
            if (len(fn) > 3 and not low.startswith('readme')
                    and low not in ('index', 'main', 'license')
                    and not low.startswith(repo) and not repo.startswith(low)):
                return '%s · %s' % (base, fn)
        return base

    t = LEAD_JUNK.sub('', t)
    # 中文站常见的「站名_栏目_栏目」：只留站名
    m = re.match(r'^(.{4,26}?)_\S', t)
    if m:
        t = m.group(1).strip()
    # 无空格的短横线：后面是宣传语才截断，且不能砍得只剩一点点
    if '://' not in t and '-' in t:
        parts = [x for x in t.split('-') if x.strip()]
        if (len(parts) >= 2 and not junk_head(parts[0])
                and junk_tail('-'.join(parts[1:]))
                and len(parts[0]) >= max(5, len(t) * 0.4)):
            t = parts[0]
    # 「名字，后面一段解释」
    m = re.match(r'^([^，,。；;！!？?]{2,26})[，,。；;](.{6,})$', t)
    if m and re.search(r'[\u4e00-\u9fff]', m.group(2)):
        t = m.group(1)

    t = cut_head(t)
    t = cut_latin_head(t)
    t = LEAD_JUNK.sub('', t)

    # 尾巴上挂着的「- 深海里的鱼」这类作者名
    m = re.match(r'^(.{10,})[-–—]\s*[\u4e00-\u9fff]{2,6}$', t)
    if m:
        t = m.group(1).strip()

    if len(t) <= 24:
        t = VER.sub(' ', t)

    for _ in range(3):
        t2 = TAIL_JUNK.sub('', t).strip(' -–—_·|｜,，。.、')
        if t2 == t:
            break
        t = t2

    for sep in (' | ', ' - ', ' – ', ' — ', ' · ', '｜'):
        if sep in t:
            a, b = [x.strip() for x in t.split(sep, 1)]
            if a and a == b:
                t = a

    t = re.sub(r'\s+', ' ', t).strip(' -–—_·|｜,，。.、:：')

    # 站点首页还留着宣传语，就退回域名
    if is_root(u) and len(t) > 18:
        return host_of(u) or t

    if len(t) > 26:
        head = t[:26]
        cut = max(head.rfind(p) for p in ' ，,。.、；;：:）)】」》〉·|-—')
        t = (head[:cut] if cut >= 12 else head).rstrip(' -–—_·|｜,，。.、') + '…'

    return t or host_of(u) or u


# ---------------------------------------------------------------- 跑

out, changed, seen, dups = [], 0, {}, []
for line in s.split('\n'):
    m = LINE.match(line)
    if not m:
        out.append(line)
        continue
    indent, title, url, tail = m.groups()
    url2 = clean_url(url)
    t2 = clean_title(title, url2)
    if t2 != title or url2 != url:
        changed += 1
    # 同一个 GitHub 仓库的多个页面合并成一条，别的按 URL 去重
    if 'github.com' in url2 and re.match(r'^[\w.\-]+/[\w.\-]+$', t2) \
            and len(t2.split('/')) == 2:
        key = 'gh:' + t2.lower().rstrip(' /')
    else:
        key = re.sub(r'^https?://(www\.)?', '', url2).split('#')[0].rstrip('/').lower()
    if key in seen:
        dups.append(t2)
        continue
    seen[key] = 1
    out.append('%s- [%s](%s)%s' % (indent, t2, url2, tail.rstrip()))

io.open(P, 'w', encoding='utf-8').write('\n'.join(out))
print('改动 %d 条；去重 %d 条' % (changed, len(dups)))
