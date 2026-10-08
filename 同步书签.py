#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步书签.py —— 把 Chrome 书签栏同步成 links.md（网址书签页的内容源）

你不用手动导出书签。脚本直接读 Chrome 自己的书签文件，
自动分类、清洗标题、去掉跟踪参数，写出 links.md。

配合「3-同步书签.command」使用：双击挂起来，之后在 Chrome 里加删书签，
半分钟内网页自己更新。

────────────────────────────────────────────────────────────
不发布到网页的内容，两类：
  ① 放在名为「不上网站」的文件夹里的（含它下面的子文件夹）
     —— 你自己控制的开关，Chrome 里拖进去就行
  ② 命中下面 AUTO_BLOCK 安全兜底规则的
     —— 个人后台 / 政务内网 / 破解激活 / 成人内容 / 机场代理 / 购物网盘

每次同步都会把「剔除了什么、为什么」打印出来，不会偷偷丢东西。
────────────────────────────────────────────────────────────

用法：
    python3 同步书签.py                 正常同步
    python3 同步书签.py --dry-run       只看结果，不写文件
    python3 同步书签.py --quiet         只输出一行结论（常驻脚本用）
    python3 同步书签.py --file X.json   指定 Chrome 书签文件
    python3 同步书签.py --from-html X.html   改用浏览器导出的书签 HTML
"""

import argparse
import html
import json
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent
OUT_MD = ROOT / "内容源" / "网址书签.md"

# ==========================================================================
# 【配置区】一般不用动
# ==========================================================================

# Chrome 书签文件在哪。多个 Profile 会合并处理。
CHROME_ROOTS = [
    Path.home() / "Library/Application Support/Google/Chrome",
    Path.home() / "Library/Application Support/Chromium",
]

# 丢进这些名字的文件夹（含子文件夹）→ 一律不发布。
# 想在 Chrome 里排除点什么，就新建一个叫「不上网站」的文件夹塞进去。
EXCLUDE_FOLDERS = ("不上网站", "不上网页", "不发布", "不公开",
                   "_private", "private", "no-publish")

# 白名单：填上文件夹名，就变成「只有这些文件夹里的才发布」，其余全不上网。
# 留空 = 不开白名单（当前就是不开）。
ONLY_PUBLISH_FOLDERS = ()

# 安全兜底总开关。等书签都归置妥当了，可以改成 False 关掉。
AUTO_BLOCK = True

# ==========================================================================
# 安全兜底：这些内容放到公开网站上会出问题，默认一律剔除
# ==========================================================================

AUTO_BLOCK_RULES = [
    ("个人后台", [
        r'paypal\.com', r'dash\.cloudflare\.com', r'console\.volcengine',
        r'console\.aliyun', r'creator\.douyin\.com', r'cp\.kuaishou\.com',
        r'mp\.toutiao\.com', r'om\.qq\.com', r'baijiahao\.baidu\.com',
        r'mp\.dayu\.com', r'weibo\.com/u/', r'weibo\.com/\d', r'jianshu\.com/u/',
        r'zhihu\.com/creator', r'zhihu\.com/people', r'channels\.weixin\.qq\.com',
        r'mp\.weixin\.qq\.com', r'studio\.ixigua\.com', r'mp\.iqiyi\.com',
        r'yuque\.com', r'wakatime\.com/dashboard', r'nls-portal',
        r'weixin\.qq\.com/cgi-bin', r'github\.com/settings',
        r'moonshot\.cn/chat', r'routinehub\.co/user/',
    ]),
    ("政务与单位内部系统", [
        # .gov.cn 一律不上公开网站 —— 这类基本是你的个人办事/注册/考试入口
        r'\.gov\.cn', r'\.gov\.', r'//\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
        r'jlgcs', r'sdzk\.cn', r'jxjy\.jnhrss',
        r'安全管控平台', r'智慧住建', r'交易中心', r'继续教育',
        r'人事考试', r'管理服务平台', r'注册管理系统', r'监理工程师注册',
        r'山东省专业技术人员', r'人才服务',
    ]),
    ("破解与激活码站", [
        r'激活', r'activation', r'activator', r'\bactivate\b', r'lanyus',
        r'medeming', r'jetbrains-active', r'zhile\.io', r'hellomac', r'破解',
        r'绿色破解', r'汉化破解', r'serials\.ws', r'\bkms\b', r'注册码',
        r'正版授权购买', r'unlock', r'appstorrent', r'哈喽马克',
        r'\bmwlib\b', r'msdn.*key', r'product.?key',
    ]),
    ("成人内容", [
        r'javscraper', r'javbus', r'avmoo', r'18av', r'成人视频',
    ]),
    ("机场与代理", [
        r'natfrp', r'goubanjia', r'shadowrocket', r'psiphon', r'one\.one\.one\.one',
        r't\.me/|telegram', r'科学上网', r'梯子', r'\bvpn\b', r'机场',
        r'clash', r'v2ray', r'v2yun', r'vless', r'trojan', r'shadowsocks',
        r'edgetunnel', r'xray', r'sing-box', r'穿墙', r'vip视频破解',
        r'v2fast\.co', r'xsus1\.com', r'ldxp\.cn', r'molurb\.com', r'serv00\.com',
        r'唯兔云', r'良心云',
    ]),
    # 彩票：跟你的「彩票选号工具」是两回事，混进书签页会被乱分类，默认挡掉。
    # 想把官方开奖查询放进书签页，删掉这一组即可。
    ("彩票相关", [
        r'lottery', r'彩票', r'体彩', r'福彩', r'中彩', r'zhcw\.com',
        r'\d{2,3}\.com/(shtml|ssq|dlt)', r'500\.com/(ssq|dlt|kj|kaijiang)',
    ]),
    ("购物与网盘分享", [
        r'shop\d+\.taobao', r'tmall\.com/item', r'item\.jd\.com',
        r'pan\.baidu\.com/s/', r'aliyundrive\.com/s/', r'lanzou\w*\.com/b0',
        r'/s/[A-Za-z0-9]{6,}$',
    ]),
]

# ==========================================================================
# 一、把书签读成 (路径, 标题, 网址) 列表
# ==========================================================================


def read_chrome_json(path):
    """读 Chrome 的 Bookmarks（JSON）。Chrome 正在写时可能读到半个文件，重试几次。"""
    for i in range(6):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            if i == 5:
                raise
            time.sleep(0.4)
    return None


def walk_json(node, path, sink):
    """深度优先遍历，顺序就是你在 Chrome 里看到的顺序。"""
    for ch in node.get("children") or []:
        if ch.get("type") == "folder":
            name = ch.get("name") or ""
            walk_json(ch, path + [name], sink)
        else:
            url = (ch.get("url") or "").strip()
            if url:
                sink.append((tuple(path), (ch.get("name") or "").strip(), url))


def load_from_json():
    """把本机所有 Chrome Profile 的书签合并成一张表。"""
    files = []
    for root in CHROME_ROOTS:
        if not root.is_dir():
            continue
        for prof in sorted(root.iterdir()):
            if not prof.is_dir() or prof.name in ("System Profile", "Guest Profile",
                                                  "Crashpad", "ShaderCache"):
                continue
            bk = prof / "Bookmarks"
            if bk.is_file():
                files.append((prof.name, bk))

    links, folders = [], 0
    for name, bk in files:
        data = read_chrome_json(bk)
        if not data:
            continue
        roots = data.get("roots") or {}
        for key in ("bookmark_bar", "other", "synced"):
            node = roots.get(key)
            if not isinstance(node, dict):
                continue
            # 「其他书签」「已同步」这两栏的根名不算路径，免得分类时被带偏
            head = [] if key == "bookmark_bar" else [node.get("name") or key]
            walk_json(node, head, links)
        folders += 1
    return links, len(files)


# ---------- Netscape 导出的 HTML（备用通道） ----------

NETSCAPE_RE = re.compile(
    r'<H3[^>]*>(.*?)</H3>|<A HREF="([^"]*)"[^>]*>(.*?)</A>|<DL>|</DL>', re.I | re.S)


def load_from_html(src):
    """备用通道：读浏览器「导出书签」那种 HTML。
    注意 Netscape 格式里 <H3> 出现在它自己的 <DL> 之前，所以文件夹名要延后一格再入栈。"""
    text = Path(src).read_text(encoding="utf-8", errors="ignore")
    out, stack, pending = [], [], None
    for m in NETSCAPE_RE.finditer(text):
        if m.group(0) == "<DL>":
            stack.append(pending)
            pending = None
        elif m.group(0) == "</DL>":
            if stack:
                stack.pop()
        elif m.group(1) is not None:
            pending = html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip()
        else:
            url = html.unescape(m.group(2) or "").strip()
            title = html.unescape(re.sub("<[^>]+>", "", m.group(3) or "")).strip()
            if url:
                out.append((tuple(x for x in stack if x), title, url))
    return out


# ==========================================================================
# 二、剔除
# ==========================================================================


def folder_excluded(path):
    """路径里任何一层叫「不上网站」之类，就整个跳过。"""
    return any((seg or "").strip().lower() in
               tuple(x.lower() for x in EXCLUDE_FOLDERS) for seg in path)


def whitelist_ok(path):
    if not ONLY_PUBLISH_FOLDERS:
        return True
    want = tuple(x.lower() for x in ONLY_PUBLISH_FOLDERS)
    return any((seg or "").strip().lower() in want for seg in path)


def auto_block_reason(title, url):
    """返回命中的类别名；没命中返回 None。网址和标题都扫一遍。"""
    hay = (url or "") + " \u0000 " + (title or "")
    for reason, pats in AUTO_BLOCK_RULES:
        for p in pats:
            if re.search(p, hay, re.I):
                return reason
    return None


# ==========================================================================
# 三、分类
# ==========================================================================

CATS = [
    ("AI 工具", "AI", "对话、编程、绘图、配音，能用得上的都在这"),
    ("开发与编程", "CODE", "文档教程、GitHub 精选、前后端、IDE 与插件"),
    ("软件下载与系统", "SOFT", "Win / Mac 软件站、系统镜像、浏览器扩展"),
    ("在线工具", "TOOL", "打开网页就能用，不装软件"),
    ("设计素材", "ART", "图库、视频素材、音效、字体、表情包"),
    ("影视资源", "MOVIE", "在线看、下载、找片名和台词"),
    ("电子书与古籍", "BOOK", "电子书站、古籍国学、图书馆与文献"),
    ("学习与考试", "STUDY", "英语、考证、教材，和软件无关的学习资源"),
    ("自媒体与内容", "MEDIA", "热点榜单、素材与配音、内容生产"),
    ("导航与搜索", "NAV", "导航站、网盘搜索、聚合搜索"),
    ("生活与家庭", "LIFE", "日历、地图、便民、孩子教育"),
]

# 有序规则表：从上往下第一个命中就定案。越具体的排越前。
# (正则, 分类key, 分组名)
RULES = [
    # ---- AI ----
    (r'chatgpt|claude\.ai|claude\.com/product|deepseek|kimi\.moonshot|doubao|豆包|'
     r'ai-bot|30aitool|cumora|yyai8|边界ai|openai|copilot|coze|chat\.|ai工具|'
     r'ai 工具|ai角色|ai 角色', 'AI', '对话与助手'),
    (r'cursor|cc-?switch|ccswitch|claude.?code|ai.?编程|paper2gui|omnivoice',
     'AI', 'AI 编程与语音'),
    (r'stable.?diffusion|midjourney|nano.?photo|comfy|即梦|可灵|ai.?绘|ai.?draw',
     'AI', 'AI 绘图与视频'),
    (r'audio|voice|tts|whisper|audiblez|配音|语音合成|shenyandayi|深言达意',
     'AI', 'AI 语音与文字'),
    (r'agency-agents|trendradar|multipost|ebook-treasure', 'AI', 'AI 工具与项目'),

    # ---- 开发与编程 ----
    (r'github\.com|gitee\.com|gitlab|git-scm|gist\.github', 'CODE', 'GitHub 精选'),
    (r'stackoverflow|segmentfault|cnblogs|csdn\.net|blog\.csdn|oschina|v2ex|'
     r'juejin|掘金|zhihu\.com|zhuanlan\.zhihu|jianshu|博客园|imhuay|4chan',
     'CODE', '社区与博客'),
    (r'runoob|liaoxuefeng|w3school|w3cschool|readthedocs|devdocs|docschina|印记中文|'
     r'tutorial|教程|手册|指南|cookbook|learn-anything|tigdig|overapi|tableconvert|'
     r'菜鸟|易百|yiibai|ituring|zealdocs|avnpc|iswbm|pycharm|在线手册',
     'CODE', '文档与教程'),
    (r'css|javascript|\bjs\b|html|vue|react|webpack|npm|node\.js|nodejs|sass|'
     r'bootstrap|bootcss|bootcdn|ant\.design|layui|babel|eslint|'
     r'前端|front|qdfuns|codepen|purecss|learnlayout|html-cn|cube-ui|mint-ui|'
     r'element|ng\.ant|fontawesome|color-themes|zeal', 'CODE', '前端与 Web'),
    (r'python|flask|django|scrapy|requests-html|pythontab|pythondoc|'
     r'pythoncaff', 'CODE', 'Python'),
    (r'\bjava\b|java1234|how2j|bjsxt|sxt\.cn|itheima|kotlin|spring|'
     r'android|安卓|developer\.android|hukai|flutter', 'CODE', 'Java 与 Android'),
    (r'vscode|code\.visualstudio|jetbrains|idea|sublime|iterm|编辑器|插件|extension|'
     r'confluence|jrebel|tomcat|material-theme|colorsublime', 'CODE', '编辑器与插件'),
    (r'leetcode|lintcode|algorithm|interview|面试|算法|data-structures',
     'CODE', '算法与面试'),
    (r'obsidian|joplin|notion|语雀|pkmer|markdown|hexo|jekyll|静态网站|'
     r'\bblog\b|backup', 'CODE', '笔记与建站'),
    (r'coding\.net|flutterchina|githubs\.cn|codeceo|r2coding|bz6000|yuanstudy|'
     r'mooc\.cn|免费编程|编程学习|源码|代码托管|程序员的|freecodecamp|stepik|'
     r'codecademy|leancode', 'CODE', '编程学习与资源'),

    # ---- iOS 快捷指令 ----
    (r'routinehub|kejicut|ipaojj|shareshortcuts|sspai\.com/page/playbook|'
     r'快捷指令|捷径|bandcase', 'SOFT', 'iOS 快捷指令'),

    # ---- 软件下载与系统 ----
    (r'macadd|macwk|xclient|xmac|macbl|mac618|macz\.com|digit77|ifmac|'
     r'macbv|okaapps|gofans|mac-awesome|better365|iina|alfred|'
     r'macbartender|alt-tab|topnotch|mounty|picsee|picview|shottr|folivora|'
     r'keyboardmaestro|tessoa|barly|anydisplay|binarynights|ezip|awehunt|'
     r'macports|mirrors\.sdu|mac用户|macbook|mac 版|mac软件|macos|'
     r'axure|ais|immich|vidhub|transmission|keka|nightfall|qlvideo|sidescreen|'
     r'betterdisplay|exelban|bruno|maczip|forklift|xscreensaver',
     'SOFT', 'Mac 软件'),
    (r'peazip|msdn|itellyou|hellowindows|xitongku|winfr|softcnkiller|ventoy|wepe|'
     r'rufus|wuyou|geekuninstaller|everything|voidtools|alldup|renamer|'
     r'bandisoft|potplayer|codecguide|ffmpeg|shutterencoder|virtualbox|raidrive|'
     r'duban|杜比|win10|win11|win7|windows|系统|装机|驱动|联想',
     'SOFT', 'Windows 与装机'),
    (r'chrome|crx|扩展迷|extfans|crxsoso|tampermonkey|violentmonkey|darkreader|'
     r'油猴|浏览器插件|插件下载', 'SOFT', '浏览器扩展'),
    (r'mpv|totalfinder|访达|binarynights|xiles|moo0|aquasnap|foobar2000|folder.?peek|'
     r'drbuho|buho|uniclipboard|uninclipboard|snippetslab|'
     r'music|桌面美化|skyfonts|consolas', 'SOFT', 'Mac 与 Windows 小工具'),
    (r'abdownloadmanager|ab 下载|greenvideo|视频下载|cobalt|qingwendang|轻文档|'
     r'\bndm\b|\bidm\b|下载管理', 'SOFT', '下载工具'),
    (r'iplaysoft|ghxi\.com|dayanzai|th-sjy|ruboard|ruancang|xiaozhongjishu|61ku|'
     r'osssr|guanwangxia|zhuangit|sixv|异次元|果核|大眼仔|软件下载|汉化|'
     r'xszn|fmhy|sodapdf|pdf24|51zxw|softmall|mou0', 'SOFT', '软件下载站'),

    # ---- 在线工具 ----
    (r'zamzar|alltoall|cloudconvert|ilovepdf|pdf24|pdfedit|soda.?pdf|adapter|'
     r'在线格式|格式转换|字幕工具|crossub|format', 'TOOL', '文件转换与 PDF'),
    (r'waifu2x|bigjpg|upscayl|tinypng|图片无损|图片压缩|图片转|图片处理|photomosh|'
     r'图转|抠图|字符画|二维码|qrcode|qrbtf', 'TOOL', '图片处理'),
    (r'tool\.lu|tool\.oschina|tool\.chinaz|tool\.browser|工具箱|小工具|miku|'
     r'ababtools|tboxn|帮小忙|30tool|jikecg|极客工具箱|dict\.|计算器|guid|'
     r'guidgen|时间戳|正则|regex|fakeupdate|打字测试|typing\.io|ipaddress|'
     r'站长|fakeupdate|菜鸟工具|在线html|在线工具', 'TOOL', '在线工具箱'),
    (r'exiftool|exif|加水印|图片信息|文件信息', 'TOOL', '文件处理'),
    (r'ankiweb|陪读蛙|readfrog|刷题|题库|an2\.net', 'TOOL', '学习辅助'),

    # ---- 设计素材 ----
    (r'pixabay|pexels|unsplash|foodiesfeed|wallhaven|2dwallpapers|图库|图片素材|'
     r'壁纸|海报|chineseposter|宣传画|shotdeck|strawberry', 'ART', '图片与壁纸'),
    (r'videvo|coverr|thosefree|aigei|newcger|vjshi|mfsc123|素材|icons8|'
     r'coolvox|sando|bangongziyuan|taira-komori|generative\.fm|fugue|'
     r'预告片|预告片世界', 'ART', '视频与音频素材'),
    (r'fontke|qiuziti|字体|font|palette|配色|color.?themes|设计',
     'ART', '字体与配色'),
    (r'emoji|zhuangbi|表情|meme|梗图|jiandan|easycover|封面|v2fy|煎蛋',
     'ART', '表情与封面'),

    # ---- 影视资源 ----
    (r'yxzhi|tvbox|直播源|电视直播|znds', 'MOVIE', '电视与直播'),
    (r'hdmoli|6v|hao6v|549\.tv|cgdict|meijutt|影视|在线观看|看电影|美剧|'
     r'yingshi|xxsnav|1mj\.cc|2rdh|meijuw', 'MOVIE', '在线影视'),
    (r'cilixiong|磁力|磁力熊|taijuwang|夸克网盘资源|网盘资源|pan友圈|盘友圈',
     'MOVIE', '下载与资源'),
    (r'subzin|findmovie|zhaotaici|台词|字幕|预告片|yingshiguang|33台词',
     'MOVIE', '字幕与台词'),

    # ---- 电子书与古籍 ----
    (r'gushiwen|shuge|shidianguji|chinese-poetry|sou-yun|quanxue|zdic|漢典|汉典|'
     r'hanziyuan|daorenjia|shiren\.org|guoxue|dudianji|国学|古籍|古诗|'
     r'诗人|诗词|典籍|书格|读典籍|识典', 'BOOK', '古籍与国学'),
    (r'bookstack|epubee|jbiaojerry|ebook|电子书|library|图书馆|z-?lib|znew|'
     r'wdl\.org|laohuabao|连环画|kindle|微信读书|书栈', 'BOOK', '电子书与图书馆'),
    (r'allhistory|全历史|ageeye|发现中国|ncpssd|文献|nlc\.cn|国家哲学|世界数字图书馆',
     'BOOK', '历史与文献'),

    # ---- 学习与考试 ----
    (r'ncego|英语|english|level-up-tips|pindushu|自然拼读|单词|音标|lightyear',
     'STUDY', '英语学习'),
    (r'bimbim|revit|autodesk|筑浪|bim|真题|考证|职称|建造|监理|一建|二建|'
     r'233\.com|geogebra', 'STUDY', '考证与职业'),
    (r'教材|试卷|课本|china-?textbook|数学|物理|化学|periodic|高中|初中|小学|'
     r'k12|deep-?sea|neal\.fun|元素周期表|考试酷|examcoo|vipexam|网校',
     'STUDY', '教材与学科'),
    (r'开课|课程|edu\.|阿里云大学|mooc|学堂|尚学堂|百战程序员|传智|黑马',
     'STUDY', '在线课程'),

    # ---- 自媒体与内容 ----
    (r'tophub|redian\.me|热点|榜单|trend|热榜|smzdk|什么值得看|今日热榜',
     'MEDIA', '热点与数据'),
    (r'kaolamedia|betteropc|jiamushuo|运营|自媒体|流量', 'MEDIA', '运营与增长'),
    (r'clipchamp|剪辑|配图|lang123|配音|字幕|排版|素材|jiandan|大拍档|琅琅',
     'MEDIA', '内容生产'),

    # ---- 导航与搜索 ----
    (r'giffox|pikasoo|chongbuluo|虫部落|搜索|search|聚合|快搜|皮卡',
     'NAV', '搜索与聚合'),
    (r'导航|nav\.|daohang|gitnavi|monknow|jikedaohang|qinight|fuliba|googax|'
     r'wxxdh|lackar|新标签页|newtab|iiice|下次一定|柒夜', 'NAV', '导航站'),
    (r'ysepan|zscc|知识船仓|资源避难所|kuake|panyq|网盘|盘搜|upyunso|资源社|'
     r'flysheep|夸克|资源猴|资源库', 'NAV', '网盘与资源'),

    (r'izuiyou|jandan|fuun\.fun|ffffound|enjoy\.bot|bwasti|dicomp|funny|'
     r'搞笑|有意思|奇趣|随机|博物馆|字源|etymology', 'LIFE', '有趣网站'),

    # ---- 生活与家庭 ----
    (r'arduino|创客|dfrobot|taichi-maker|scratch|少儿|儿童|幼儿|字帖|识字|'
     r'an2\.net|youjiao|成语|lxwc|两小无猜|中国诗人|连环画报', 'LIFE', '孩子教育'),
    (r'5adanci|rilijing|日历|tianditu|地图|天气|健康|记账|菜谱|'
     r'便民|paperme|打印纸|calculator|计算|geo|国家地理', 'LIFE', '日常实用'),
    (r'douban\.com/note|摘录|读书笔记', 'LIFE', '阅读与摘录'),
]

# 兜底：一条规则都没命中时，按书签原本所在的文件夹给个去处
FOLDER_CAT = [
    (r'影视', 'MOVIE'),
    (r'^CODE$|^Android$|^Python$|^Web$|^Java$|^IDE$|^GitHub|面试|^学习$|^经典$|'
     r'^收藏$|^工具$|^安卓$|BIM', 'CODE'),
    (r'^MAC$|Mac软件|数码科技|^软件$|扩展|插件', 'SOFT'),
    (r'电子书|古文|书籍|文学历史|国学|古籍', 'BOOK'),
    (r'^考试$|英语|办公|考试', 'STUDY'),
    (r'^孩子$|arduino', 'LIFE'),
    (r'导航|搜索', 'NAV'),
    (r'壁纸|灵感素材|素材|设计', 'ART'),
    (r'自媒体|^UP$|账号|流量', 'MEDIA'),
    (r'^AI$|AI学习', 'AI'),
    (r'生产力|obsidian|^临时$|^常用$|^其他$', 'TOOL'),
]


def classify(title, url, path):
    hay = (title + " " + url).lower()
    for pat, cat, _ in RULES:
        if re.search(pat, hay, re.I):
            return cat
    joined = "/".join(path)
    for p, c in FOLDER_CAT:
        if re.search(p, joined, re.I):
            return c
    return "TOOL"


def subcat(cat, title, url):
    """只在「同一个大类」的规则里找分组，绝不串到别的大类去。
    串出去的话分组名不在 sub_order(cat) 里，组装时会被漏掉。"""
    hay = (title + " " + url).lower()
    for pat, c, sub in RULES:
        if c == cat and sub and re.search(pat, hay, re.I):
            return sub
    return None


def sub_order(cat):
    seen = []
    for _, c, sub in RULES:
        if c == cat and sub and sub not in seen:
            seen.append(sub)
    return seen


# ==========================================================================
# 四、标题与网址清洗
# ==========================================================================

TRACK = re.compile(
    r'^(utm_[a-z]+|hm[a-z]{2}|from|ref|referrer|source|spm|spm_id_from|share[a-z_]*|'
    r'_fid|_t|t|wdorigin|wdfrom|timestamp|cmpid|scene|src|sa|ved|'
    r'vd_source|fr|clicktime|session_id|invite_code|tjlb|depth_1)$', re.I)
BAD_FRAG = {'readme', 'download', 'top', 'main', 'content', 'index', 'toc', 'home',
            'readme-ov-file', 'readme_zh', 'readme-cn', 'downloads',
            'install', 'rs'}

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
    r'Browse|Archive|Library|Portal|Platform|Community|Blog|Tutorial|Stock',
    re.I)

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
SEP = re.compile(r'\s*[|｜丨]\s*|\s+[—–-]\s+|\s*[·•‧]\s*|\s*[：:]\s+|\s*[-–—]{2,}\s*')
LATIN_HEAD = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9 .+#_\-]{1,26}?)\s+(?=[\u4e00-\u9fff（(])')

GH = re.compile(r'^https?://github\.com/([^/]+)/([^/#?]+)', re.I)
GH_NON = {'orgs', 'users', 'topics', 'collections', 'sponsors', 'features',
          'about', 'settings', 'login', 'apps', 'marketplace', 'explore',
          'trending', 'search', 'notifications', 'pulls', 'issues'}

ALIAS = [
    (r'pixabay\.com', 'Pixabay'), (r'coverr\.co', 'Coverr'),
    (r'videvo\.net', 'Videvo'), (r'vox\.rocks', 'VOX'),
    (r'qiuziti\.com', '求字体网'),
    (r'sxt\.cn/Java', '速学堂 · Java 课程'), (r'sxt\.cn/?$', '速学堂'),
    (r'coding\.net/help', 'CODING 帮助中心'),
    (r'better365\.cn/apps', 'Better365 产品页'),
    (r'okaapps\.com/product', 'VidHub · 下载页'),
    (r'fuun\.fun/top/shadiao', 'FUUN.FUN · 沙雕网站'),
    (r'fuun\.fun', 'FUUN.FUN'),
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
    (r'tuya\.cn|tuya\.com', '涂鸦智能'),
    # 书签标题本身就是光秃秃的域名，人工给个名字
    (r'spdpd\.net', '视频大拍档'),
    (r'zhuangit\.ababtools\.com', '装个机'),
    (r'ababtools\.com', 'ABABTOOLS'),
    (r'ncego\.com', '极速英语'),
    (r'daorenjia\.com', '道人家 · 中华道藏'),
    (r'zscc\.ysepan\.com', '知识船仓'),
    (r'kuakezy\.cc', '夸克资源社'),
    (r'plugin\.csdn\.net', 'CSDN 开发助手'),
    (r'css\.cuishifeng\.cn', 'CSS 参考手册'),
    (r'learn\.shayhowe\.com', 'Learn to Code HTML & CSS'),
    (r'xiles\.net', 'xiles 应用'),
    (r'www\.macz\.com|macz\.com', 'MacZ'),
    (r'topnotch\.app', 'TopNotch 隐藏刘海'),
    (r'shareshortcuts\.com', 'ShareShortcuts'),
    (r'alger\.fun', 'AlgerMusicPlayer'),
    (r'paywallbuster\.com', 'PaywallBuster'),
    (r'mfsc123\.com', 'MFSC123 免费商用素材'),
    (r'hanziyuan\.net', '汉字字源'),
    (r'quanxue\.cn', '劝学网'),
    (r'shiren\.org', '中国诗人资料馆'),
    (r'znew\.pages\.dev', 'Z-Library 镜像'),
    (r'jiamushuo\.com', '嘉木说'),
    (r'colormatch\.polarr\.com', 'Polarr 滤镜匹配'),
    (r'search\.chongbuluo\.com', '虫部落快搜'),
    (r'chongbuluo\.com', '虫部落'),
    (r'guidgen\.com', 'GUID 生成器'),
    (r'fakeupdate\.net', 'FakeUpdate 模拟界面'),
    (r'periodic-table-pro', '元素周期表 Pro'),
    (r'kimi\.moonshot\.cn', 'Kimi'),
    (r'layui\.com', 'Layui'),
    (r'pythontab\.com', 'PythonTab'),
    (r'codeceo\.com', 'CodeCeo 编程学习'),
    (r'upscayl', 'Upscayl'),
    (r'hellowindows\.cn', 'HelloWindows'),
    (r'qingwendang\.com', '轻文档'),
    (r'arduino\.nxez\.com', 'Arduino 实验室'),
]


def clean_url(u):
    u = (u or "").strip()
    # Chrome 里手打过的网址可能带空格，直接写进 markdown 会把链接截断
    u = u.replace(" ", "%20")
    head, _, frag = u.partition('#')
    base, _, q = head.partition('?')
    if q:
        keep = [kv for kv in q.split('&')
                if kv and not TRACK.match(kv.split('=')[0])]
        base += ('?' + '&'.join(keep)) if keep else ''
    # 顺手把路径里重复的斜杠收一下（www.mfsc123.com// 这种）
    base = re.sub(r'(?<=[^:])//+', '/', base)
    if frag and frag.lower().split('=')[0] not in BAD_FRAG:
        return base + '#' + frag
    return base


def host_of(u):
    m = re.match(r'https?://([^/?#]+)', u or "", re.I)
    if not m:
        return ''
    h = m.group(1).lower().split('@')[-1].split(':')[0]
    return h[4:] if h.startswith('www.') else h


def is_root(u):
    m = re.match(r'https?://[^/?#]+(/[^?#]*)', u or "", re.I)
    p = (m.group(1) if m else '/') or '/'
    return re.sub(r'^/(zh|zh-cn|zh-hans-cn|cn|en|index\.html?)/?$', '/', p,
                  flags=re.I) == '/'


def junk_head(seg):
    seg = (seg or "").strip()
    if not seg:
        return True
    return bool(SITE_TAIL.match(seg) or JUNK_WORDS.search(seg))


def junk_tail(seg):
    seg = (seg or "").strip()
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
    t = EMOJI.sub(' ', ZERO_W.sub('', t or ""))
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
            fn = unquote(fm.group(1)).rstrip('/').split('/')[-1]
            fn = re.sub(r'\.(md|markdown|txt|pdf|html?)$', '', fn, flags=re.I)
            low = fn.lower()
            if (3 < len(fn) <= 22 and ' ' not in fn and not low.startswith('readme')
                    and low not in ('index', 'main', 'license')
                    and not low.startswith(repo) and not repo.startswith(low)):
                return '%s · %s' % (base, fn)
        return base

    t = LEAD_JUNK.sub('', t)
    m = re.match(r'^(.{4,26}?)_\S', t)
    if m:
        t = m.group(1).strip()
    if '://' not in t and '-' in t:
        parts = [x for x in t.split('-') if x.strip()]
        if (len(parts) >= 2 and not junk_head(parts[0])
                and junk_tail('-'.join(parts[1:]))
                and len(parts[0]) >= max(5, len(t) * 0.4)):
            t = parts[0]
    m = re.match(r'^([^，,。；;！!？?]{2,26})[，,。；;](.{6,})$', t)
    if m and re.search(r'[\u4e00-\u9fff]', m.group(2)):
        t = m.group(1)

    t = cut_head(t)
    t = cut_latin_head(t)
    t = LEAD_JUNK.sub('', t)

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

    for sep in (' | ', ' - ', ' – ', ' — ', ' · ', ' • ', '｜'):
        if sep in t:
            a, b = [x.strip() for x in t.split(sep, 1)]
            if a and a == b:
                t = a

    t = re.sub(r'\s+', ' ', t).strip(' -–—_·|｜,，。.、:：')

    if is_root(u) and len(t) > 18:
        return host_of(u) or t

    if len(t) > 26:
        head = t[:26]
        cut = max(head.rfind(p) for p in ' ，,。.、；;：:）)】」》〉·|-—')
        t = (head[:cut] if cut >= 12 else head).rstrip(' -–—_·|｜,，。.、') + '…'

    return t or host_of(u) or u


def dedup_key(url, title):
    if 'github.com' in url and re.match(r'^[\w.\-]+/[\w.\-]+$', title) \
            and len(title.split('/')) == 2:
        return 'gh:' + title.lower().rstrip(' /')
    return re.sub(r'^https?://(www\.)?', '', url).split('#')[0].rstrip('/').lower()


# ==========================================================================
# 五、组装 内容源/网址书签.md
# ==========================================================================

HEADER = """<!--
  内容源/网址书签.md —— 网址书签页的内容源。

  ⚠ 这个文件是「同步书签.py」自动生成的，手改会在下次同步时被覆盖。
    想加网址 → 在 Chrome 里收藏；想删 → 在 Chrome 里删；想调整分类 → 改脚本里的 RULES。

  不想发布的书签：在 Chrome 里新建一个叫「不上网站」的文件夹，塞进去就行。

  格式（和软件清单完全一样）：
    ## 分类名          ← 一级分类，会生成一个大区块
    - 分组名：        ← 二级分组（可选）
        - [名称](网址)：一句话说明
  不写说明也行，只写 [名称](网址) 即可。
-->
"""


def assemble(buckets):
    out = [HEADER]
    for name, key, _ in CATS:
        items = buckets.get(key) or []
        out.append("## %s" % name)
        out.append("")
        if not items:
            out.append("- （待补充）")
            out.append("")
            continue
        subs = OrderedDict()
        for t, u in sorted(items, key=lambda x: x[0]):
            subs.setdefault(subcat(key, t, u), []).append((t, u))
        order = [n for n in sub_order(key) if n in subs]
        # 保险带：sub_order 里没登记到的分组也一并输出，绝不静默丢条目
        for n in subs:
            if n is not None and n not in order:
                order.append(n)
        if None in subs:
            order.append(None)
        if len(order) <= 1:
            only = order[0] if order else None
            for t, u in subs.get(only) or []:
                out.append("- [%s](%s)" % (t, u))
            out.append("")
            continue
        for nm in order:
            grp = subs[nm]
            out.append("- %s：" % ("其它" if nm is None else nm))
            for t, u in grp:
                out.append("    - [%s](%s)" % (t, u))
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# ==========================================================================
# 六、跑
# ==========================================================================

C = dict(b="\033[1m", g="\033[32m", y="\033[33m", r="\033[31m",
         d="\033[2m", n="\033[0m")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--dry-run", action="store_true", help="只看结果，不写文件")
    ap.add_argument("--quiet", action="store_true", help="只输出一行结论")
    ap.add_argument("--file", help="指定 Chrome 书签文件（.json）")
    ap.add_argument("--from-html", help="改用浏览器导出的书签 HTML")
    args = ap.parse_args()

    quiet = args.quiet

    def say(s=""):
        if not quiet:
            print(s)

    # ---- 读 ----
    if args.from_html:
        links = load_from_html(args.from_html)
        src_desc = args.from_html
    elif args.file:
        data = read_chrome_json(Path(args.file))
        links = []
        roots = (data or {}).get("roots") or {}
        for key in ("bookmark_bar", "other", "synced"):
            node = roots.get(key)
            if isinstance(node, dict):
                walk_json(node, [] if key == "bookmark_bar" else [node.get("name") or key],
                          links)
        src_desc = args.file
    else:
        links, nprof = load_from_json()
        src_desc = "Chrome（%d 个 Profile 合并）" % max(nprof, 1) if nprof else "Chrome"

    if not links:
        print("%s✗ 没读到任何书签%s" % (C["r"], C["n"]))
        print("  确认 Chrome 路径：~/Library/Application Support/Google/Chrome/*/Bookmarks")
        return 2

    # ---- 过滤 + 分类 ----
    buckets = {}
    seen = {}
    gone_folder, gone_auto, gone_dup = [], [], []
    reason_count = OrderedDict()

    for path, title, url in links:
        if EXCLUDE_FOLDERS and folder_excluded(path):
            gone_folder.append((title, "/".join(path)))
            continue
        if not whitelist_ok(path):
            gone_folder.append((title, "/".join(path)))
            continue
        if AUTO_BLOCK:
            why = auto_block_reason(title, url)
            if why:
                gone_auto.append((title, why))
                reason_count[why] = reason_count.get(why, 0) + 1
                continue
        u2 = clean_url(url)
        t2 = clean_title(title, u2)
        k = dedup_key(u2, t2)
        if k in seen:
            gone_dup.append(t2)
            continue
        seen[k] = 1
        # 注意：分类必须用「洗干净的网址」。
        # 原始网址里带着 ?utm_source=chatgpt.com 这类跟踪参数，
        # 拿它分类会让 chatgpt 之类的关键词误命中（曾经把 Shottr 判成 AI 工具）。
        buckets.setdefault(classify(title, u2, path), []).append((t2, u2))

    kept = sum(len(v) for v in buckets.values())
    md = assemble(buckets)

    # ---- 报告 ----
    say("")
    say("  %s同步书签%s  %s" % (C["b"], C["n"], src_desc))
    say("  " + "─" * 46)
    say("  书签总数          %5d 条" % len(links))
    if gone_folder:
        say("  %s「不上网站」排除   %5d 条%s" % (C["d"], len(gone_folder), C["n"]))
    if gone_auto:
        say("  %s安全兜底排除      %5d 条%s" % (C["d"], len(gone_auto), C["n"]))
    if gone_dup:
        say("  %s重复合并          %5d 条%s" % (C["d"], len(gone_dup), C["n"]))
    say("  %s发布到网页        %5d 条%s" % (C["g"], kept, C["n"]))
    say("")

    if gone_auto and not quiet:
        say("  安全兜底挡下的内容（前 12 条，全都会被排除）")
        for t, why in gone_auto[:12]:
            say("    %s·%s %-38s %s%s" % (C["d"], C["n"], t[:38], why, ""))
        if len(gone_auto) > 12:
            say("    %s· 还有 %d 条…%s" % (C["d"], len(gone_auto) - 12, C["n"]))
        say("")
        say("    %s按类别：%s" % (C["d"], "、".join(
            "%s %d" % (k, v) for k, v in reason_count.items()) + C["n"]))
        say("    想放行某一条：把它从脚本的 AUTO_BLOCK_RULES 里删掉对应的词")
        say("    想全部放行：把脚本顶部的 AUTO_BLOCK 改成 False")
        say("")

    if not quiet:
        say("  分类分布")
        for name, key, _ in CATS:
            n = len(buckets.get(key) or [])
            bar = "█" * min(int(n / 8) + (1 if n else 0), 26)
            say("    %-14s %4d  %s%s%s" % (name, n, C["d"], bar, C["n"]))
        say("")

    # ---- 写 ----
    old = OUT_MD.read_text(encoding="utf-8") if OUT_MD.exists() else ""
    changed = old.strip() != md.strip()
    if changed and not args.dry_run:
        OUT_MD.write_text(md, encoding="utf-8")

    if args.dry_run:
        say("  %s（试运行，没有写文件）%s" % (C["y"], C["n"]))
    elif changed:
        say("  %s✓ 内容源/网址书签.md 已更新%s" % (C["g"], C["n"]))
    else:
        say("  %s· 和上一次一样，没有变化%s" % (C["d"], C["n"]))
    say("")

    print("__SYNC__ changed=%d kept=%d total=%d" % (1 if changed else 0, kept, len(links)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
