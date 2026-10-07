/**
 * /api/lottery —— 把官方的开奖结果，转成本站自己的 JSON
 *
 * 为什么需要这一个函数：
 *   浏览器有同源策略，官方接口都不发 Access-Control-Allow-Origin，
 *   网页里直接 fetch 官方接口一定会被拦。这个函数跑在服务器上，由它去取；
 *   页面只请求自己站的 /api/lottery —— 同域，不算第三方请求。
 *
 * 调用方式：
 *   GET /api/lottery?ssq=2026114&dlt=26114
 *   两个参数是「页面内置快照已经到哪一期」。函数返回这之后的所有期，
 *   保证补上中间缺的期数，而不是只给最新一期（只给一期会让历史数组断层，
 *   走势图就把不连续的期当成连续的画）。
 *
 *   complete=false 表示缺口超出了本次取回的范围（页面快照太旧），
 *   这时页面应当放弃合并 —— 宁可少更新，也不能给出错误的历史。
 *
 * ── 为什么会跑成「多源」 ──────────────────────────────────────────────
 *   这个函数部署在 EdgeOne，出口在境外。2026-10-07 实测（境外出口）：
 *
 *     www.cwl.gov.cn            403   连站点首页都 403 —— 整个域名封境外
 *     webapi.sporttery.cn       567
 *     www.lottery.gov.cn        567
 *     www.17500.cn/getData/*.TXT  200  ← 有戏
 *     data.17500.cn/*.txt         200  ← 备用域名
 *
 *   也就是说：官方接口不是「反爬」，是「地域封锁」，改 UA / Referer 都没用。
 *   要拿官方接口，出口必须在中国大陆（自建大陆云函数 / 备案服务器）。
 *
 *   所以这里做成分级回退，而不是二选一：
 *     第 1 级  官方接口   —— 出口在大陆时命中，境外会快速 403/567 失败
 *     第 2 级  17500.cn 全量 TXT —— 境外实测可用，内容是官方公告的转录
 *     第 3 级  17500.cn 备用域名 / http
 *   哪一级先成用哪一级。将来若接了大陆云函数，代码一行都不用改，
 *   出口一变，第 1 级自动就命中了。
 *
 * ── 数据可信度 ────────────────────────────────────────────────────────
 *   17500.cn 是第三方数据站，不是官方。取回后逐行校验（期号递增、
 *   日期格式、球的个数与取值范围），任何一行不合规整份作废、退到下一级。
 *   校验不过宁可返回 ok:false 让页面用内嵌快照，也不把脏数据画上去。
 *   本站页脚与说明书里如实标注了实际用的是哪个源。
 *
 * 设计取舍：
 *   1. 两个彩种各抓各的，谁挂都不影响另一个。全挂返回 ok:false，页面退回内嵌快照。
 *   2. 带 10 分钟 CDN 缓存 + 1 小时后台续期，访客再多也打不到上游几次。
 *   3. 任何异常都返回 200 + JSON，不让页面拿到 5xx 去做错误处理 ——
 *      对访客来说，「拿不到新数据」和「没有新数据」是同一种结果。
 *
 * 部署：放在项目根目录的 cloud-functions/api/lottery.js，路径即 /api/lottery。
 */

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

const WANT = 100;   /* 官方接口一次最多取多少期：约够补两个月的空档 */

/* ══════════════════ 源表 ══════════════════
   kind: 'official' = 官方接口（JSON）  'txt' = 17500.cn 全量文本
   ms  : 单源超时。总预算要留在页面 12 秒的上限之内。 */

const SSQ_SOURCES = [
  { id: 'cwl',        label: '中国福利彩票官网', kind: 'official', ms: 2500,
    url: 'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice' +
         '?name=ssq&issueCount=' + WANT + '&pageNo=1&pageSize=' + WANT,
    ref: 'https://www.cwl.gov.cn/' },

  { id: '17500',      label: '17500.cn', kind: 'txt', ms: 5000,
    url: 'https://www.17500.cn/getData/ssq.TXT', ref: 'https://www.17500.cn/' },

  { id: '17500-data', label: '17500.cn 备用域名', kind: 'txt', ms: 5000,
    url: 'https://data.17500.cn/ssq_asc.txt', ref: 'https://www.17500.cn/' },

  { id: '17500-http', label: '17500.cn http', kind: 'txt', ms: 5000,
    url: 'http://www.17500.cn/getData/ssq.TXT', ref: 'https://www.17500.cn/' },
];

const DLT_SOURCES = [
  { id: 'sporttery',  label: '中国体彩网', kind: 'official', ms: 2500,
    url: 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry' +
         '?gameNo=85&provinceId=0&isVerify=1&pageNo=1&pageSize=' + WANT,
    ref: 'https://static.sporttery.cn/' },

  { id: '17500',      label: '17500.cn', kind: 'txt', ms: 5000,
    url: 'https://www.17500.cn/getData/dlt.TXT', ref: 'https://www.17500.cn/' },

  { id: '17500-data', label: '17500.cn 备用域名', kind: 'txt', ms: 5000,
    url: 'https://data.17500.cn/dlt_desc.txt', ref: 'https://www.17500.cn/' },

  { id: '17500-http', label: '17500.cn http', kind: 'txt', ms: 5000,
    url: 'http://www.17500.cn/getData/dlt.TXT', ref: 'https://www.17500.cn/' },
];

/* ══════════════════ 抓取 ══════════════════ */

async function fetchText(url, referer, ms) {
  const headers = {
    'User-Agent': UA,
    'Accept': 'application/json, text/plain, text/html, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
  };
  if (referer) headers['Referer'] = referer;
  const res = await fetch(url, { headers, redirect: 'follow', signal: AbortSignal.timeout(ms) });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.text();
}

function nums(str, sep) {
  return String(str).split(sep)
    .map(x => parseInt(x, 10))
    .filter(n => Number.isInteger(n));
}

function asc(a, b) { return a - b; }

/* ══════════════════ 各源 → 统一行格式 ══════════════════
   统一行：{ code: '2026114', date: '2026-10-06', front: [..], back: [..] }
   最终一批源（无论哪级命中）都跑同一套校验，校验不过就丢掉换下一级。 */

/* —— 一级：官方接口 —— */

function parseSSQ_official(text) {
  const d = JSON.parse(text);
  const rows = (d && d.result ? d.result : []).map(function (r) {
    return {
      code: String(r.code),
      date: String(r.date).replace(/\(.*?\)/g, '').trim(),
      front: nums(r.red, ',').sort(asc),
      back: nums(r.blue, ','),
    };
  }).reverse();          /* 接口是「从新到旧」，翻过来方便追加 */
  return rows;
}

function parseDLT_official(text) {
  const d = JSON.parse(text);
  const raw = (d && d.value && d.value.list) || [];
  return raw.map(function (r) {
    const all = nums(r.lotteryDrawResult, ' ');
    return {
      code: String(r.lotteryDrawNum),
      date: String(r.lotteryDrawTime),
      front: all.slice(0, 5).sort(asc),   /* "02 04 06 10 11 01 10" = 5 前 + 2 后 */
      back: all.slice(5, 7),
    };
  }).reverse();
}

/* —— 二级：17500.cn 全量 TXT ——
   一行一期，空格分隔，从旧到新（文件本身就是升序）：
     双色球  期号 日期 红1..红6 蓝 出球顺序… 销售额 奖池 …
     大乐透  期号 日期 前1..前5 后1 后2 出球顺序… 销售额 奖池 …
   期号：双色球 7 位（2003001），大乐透 5 位（07001）。
   注意大乐透第一列可能带前导零 —— 必须保留字符串，不能转数字。 */

function parseSSQ_txt(text) {
  const out = [];
  text.split(/\r?\n/).forEach(function (line) {
    const f = line.trim().split(/\s+/);
    if (f.length < 9) return;
    if (!/^\d{5,7}$/.test(f[0])) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f[1])) return;
    const red = f.slice(2, 8).map(Number);
    const blue = [Number(f[8])];
    if (red.some(n => !Number.isInteger(n) || n < 1 || n > 33)) return;
    if (!Number.isInteger(blue[0]) || blue[0] < 1 || blue[0] > 16) return;
    out.push({ code: f[0], date: f[1], front: red.slice().sort(asc), back: blue });
  });
  return out;
}

function parseDLT_txt(text) {
  const out = [];
  text.split(/\r?\n/).forEach(function (line) {
    const f = line.trim().split(/\s+/);
    if (f.length < 9) return;
    if (!/^\d{4,7}$/.test(f[0])) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f[1])) return;
    const front = f.slice(2, 7).map(Number);
    const back = f.slice(7, 9).map(Number);
    if (front.some(n => !Number.isInteger(n) || n < 1 || n > 35)) return;
    if (back.some(n => !Number.isInteger(n) || n < 1 || n > 12)) return;
    out.push({ code: f[0], date: f[1], front: front.slice().sort(asc), back });
  });
  return out;
}

/* ══════════════════ 整体校验 ══════════════════
   源可能返回广告页、错误页、被截断的半截文件 —— 这类内容行数远不够、
   或期号不递增。整份不过关就当这个源挂了，换下一个。 */

function sane(rows, opt) {
  if (!Array.isArray(rows) || rows.length < 100) return false;

  let prev = -Infinity;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const n = Number(r.code);
    if (!Number.isFinite(n) || n <= prev) return false;       /* 期号必须严格递增 */
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date)) return false;
    if (r.front.length !== opt.frontPick || r.back.length !== opt.backPick) return false;
    prev = n;
  }

  /* 最新一期的日期不能是未来，也不能太旧（超过 40 天说明源不更新了） */
  const latest = rows[rows.length - 1];
  const age = (Date.now() - Date.parse(latest.date + 'T12:00:00+08:00')) / 86400000;
  if (!(age > -2 && age < 40)) return false;

  return true;
}

/* ══════════════════ 分级回退 ══════════════════ */

const OPT_SSQ = { frontPick: 6, backPick: 1 };
const OPT_DLT = { frontPick: 5, backPick: 2 };

/* 按源的 kind 挑解析器，逐个试。这是唯一在用的抓取路径。 */
async function fromSources(sources, parsers, opt) {
  const tried = [];
  for (let i = 0; i < sources.length; i++) {
    const s = sources[i];
    try {
      const text = await fetchText(s.url, s.ref, s.ms);
      const rows = parsers[s.kind](text);
      if (!sane(rows, opt)) throw new Error('数据校验没过（' + rows.length + ' 行）');
      return { rows: rows, source: s.label, via: s.id };
    } catch (e) {
      tried.push(s.id + ': ' + String((e && e.message) || e).slice(0, 90));
    }
  }
  throw new Error(tried.join(' | '));
}

const PARSERS = {
  ssq: { official: parseSSQ_official, txt: parseSSQ_txt },
  dlt: { official: parseDLT_official, txt: parseDLT_txt },
};

/* 从 rows 里挑出比 since 新的那些，并判断缺口有没有超出这次取回的范围。 */
function slice(rows, since) {
  if (!rows.length) return { complete: false, latest: null, list: [] };

  const latest = rows[rows.length - 1];
  const oldest = Number(rows[0].code);
  const sinceNum = Number(since);
  /* 空字符串会被 Number() 转成 0，得单独判掉，否则「没传 since」会被
     当成「since = 0」，把所有历史都当更新返回。 */
  const hasSince = since !== '' && since !== null && since !== undefined
                   && Number.isFinite(sinceNum);

  const list = hasSince
    ? rows.filter(function (r) { return Number(r.code) > sinceNum; })
    : rows.slice(-30);

  return {
    /* 取回范围的最老一期 ≤ 页面已有的一期 → 中间没有洞。
       没传 since（首次访问）时按「覆盖完整」处理。 */
    complete: !hasSince || oldest <= sinceNum,
    latest: { code: latest.code, date: latest.date, front: latest.front, back: latest.back },
    list: list.map(function (r) { return [r.front, r.back, r.code, r.date]; }),
  };
}

async function getSSQ(since) {
  const r = await fromSources(SSQ_SOURCES, PARSERS.ssq, OPT_SSQ);
  r.part = slice(r.rows, since);
  return r;
}

async function getDLT(since) {
  const r = await fromSources(DLT_SOURCES, PARSERS.dlt, OPT_DLT);
  r.part = slice(r.rows, since);
  return r;
}

/* ══════════════════ 入口 ══════════════════ */

async function handler(context) {
  const url = new URL((context && context.request && context.request.url) || 'https://x/api/lottery');
  const sinceSsq = url.searchParams.get('ssq') || '';
  const sinceDlt = url.searchParams.get('dlt') || '';

  const errors = {};
  const [ssq, dlt] = await Promise.all([
    getSSQ(sinceSsq).catch(function (e) { errors.ssq = String((e && e.message) || e); return null; }),
    getDLT(sinceDlt).catch(function (e) { errors.dlt = String((e && e.message) || e); return null; }),
  ]);

  /* 如实回报这次实际用的是哪个源 —— 页面页脚会显示出来。 */
  const used = [ssq && ssq.source, dlt && dlt.source].filter(Boolean);
  const uniq = used.filter(function (v, i) { return used.indexOf(v) === i; });

  const out = {
    ok: !!(ssq || dlt),
    updatedAt: new Date().toISOString(),
    source: uniq.length ? uniq.join(' + ') : '',
    via: [ssq && ssq.via, dlt && dlt.via].filter(Boolean).join(','),
  };
  if (ssq) out.ssq = ssq.part;
  if (dlt) out.dlt = dlt.part;
  if (!out.ok) out.errors = errors;

  return new Response(JSON.stringify(out), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=UTF-8',
      /* 10 分钟 CDN 缓存 + 1 小时后台续期：访客再多也打不到上游几次。
         注意 s-maxage 让 getSSQ 的「最后一期」可能滞后 10 分钟 ——
         对开奖数据完全够用，且这个滞后是拿上游稳定性换的。 */
      'Cache-Control': 'public, s-maxage=600, stale-while-revalidate=3600',
    },
  });
}

export const onRequest = handler;
export default handler;
