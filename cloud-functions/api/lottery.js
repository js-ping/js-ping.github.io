/**
 * /api/lottery —— 把福彩 / 体彩官网的开奖，转成本站自己的 JSON
 *
 * 为什么需要这一个函数：
 *   浏览器有同源策略，而两个官网的接口都不发 Access-Control-Allow-Origin，
 *   网页里直接 fetch 官方接口一定会被拦。这个函数跑在服务器上，由它去取；
 *   页面只请求自己站的 /api/lottery —— 同域，不算第三方请求。
 *
 * 调用方式：
 *   GET /api/lottery?ssq=2026106&dlt=26104
 *   两个参数是「页面内置快照已经到哪一期」。函数返回这之后的所有期，
 *   保证补上中间缺的期数，而不是只给最新一期（只给一期会让历史数组断层，
 *   走势图就把不连续的期当成连续的画）。
 *
 *   complete=false 表示缺口超出了本次取回的范围（页面快照太旧），
 *   这时页面应当放弃合并 —— 宁可少更新，也不能给出错误的历史。
 *
 * 设计取舍：
 *   1. 两个源各抓各的，谁挂都不影响另一个。全挂返回 ok:false，页面退回内嵌快照。
 *   2. 带 10 分钟 CDN 缓存 + 1 小时后台续期，访客再多也打不到官网几次。
 *      同一个页面版本 → 同一个 URL → 缓存命中率高。
 *   3. 任何异常都返回 200 + JSON，不让页面拿到 5xx 去做错误处理 ——
 *      对访客来说，「拿不到新数据」和「没有新数据」是同一种结果。
 *
 * 部署：放在项目根目录的 cloud-functions/api/lottery.js，路径即 /api/lottery。
 */

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

const WANT = 100;   /* 一次最多取多少期：约够补两个月的空档 */

const SSQ_URL = 'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/' +
                'findDrawNotice?name=ssq&issueCount=' + WANT + '&pageNo=1&pageSize=' + WANT;

const DLT_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry' +
                '?gameNo=85&provinceId=0&isVerify=1&pageNo=1&pageSize=' + WANT;

async function getJSON(url, extraHeaders) {
  const res = await fetch(url, {
    headers: Object.assign({
      'User-Agent': UA,
      'Accept': 'application/json, text/plain, */*',
      'Accept-Language': 'zh-CN,zh;q=0.9',
    }, extraHeaders || {}),
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(url + ' -> HTTP ' + res.status);
  return res.json();
}

function nums(str, sep) {
  return String(str).split(sep)
    .map(x => parseInt(x, 10))
    .filter(n => Number.isInteger(n));
}

function asc(a, b) { return a - b; }

/* 双色球：result[0] 是最新一期 { code, date:"2026-10-06(二)", red:"07,18,...", blue:"10" }
   接口按「从新到旧」返回，这里翻成从旧到新，方便页面直接往后追加。 */
async function getSSQ(since) {
  const d = await getJSON(SSQ_URL, { 'Referer': 'https://www.cwl.gov.cn/' });
  const rows = (d && d.result ? d.result : []).map(function (r) {
    return {
      code: String(r.code),
      date: String(r.date).replace(/\(.*?\)/g, '').trim(),
      front: nums(r.red, ',').sort(asc),
      back: nums(r.blue, ','),
    };
  }).filter(function (r) {
    return r.front.length === 6 && r.back.length === 1;
  }).reverse();
  return slice(rows, since);
}

/* 大乐透：value.list 按「从新到旧」返回，
   lotteryDrawResult = "02 04 06 10 11 01 10"，7 个数 = 5 前区 + 2 后区。 */
async function getDLT(since) {
  const d = await getJSON(DLT_URL, { 'Referer': 'https://static.sporttery.cn/' });
  const raw = (d && d.value && d.value.list) || [];
  const rows = raw.map(function (r) {
    const all = nums(r.lotteryDrawResult, ' ');
    return {
      code: String(r.lotteryDrawNum),
      date: String(r.lotteryDrawTime),
      front: all.slice(0, 5).sort(asc),
      back: all.slice(5, 7),
    };
  }).filter(function (r) {
    return r.front.length === 5 && r.back.length === 2;
  }).reverse();
  return slice(rows, since);
}

/* 从 rows 里挑出比 since 新的那些，并判断缺口有没有超出这次取回的范围。 */
function slice(rows, since) {
  if (!rows.length) {
    return { complete: false, latest: null, list: [] };
  }
  const latest = rows[rows.length - 1];
  const oldest = Number(rows[0].code);
  const sinceNum = Number(since);

  const list = Number.isFinite(sinceNum)
    ? rows.filter(function (r) { return Number(r.code) > sinceNum; })
    : rows.slice(-30);

  return {
    /* 取回范围的最老一期 ≤ 页面已有的一期 → 中间没有洞。
       没传 since（首次访问）时按「覆盖完整」处理。 */
    complete: !Number.isFinite(sinceNum) || oldest <= sinceNum,
    latest: { code: latest.code, date: latest.date, front: latest.front, back: latest.back },
    list: list.map(function (r) { return [r.front, r.back, r.code, r.date]; }),
  };
}

async function handler(context) {
  const url = new URL((context && context.request && context.request.url) || 'https://x/api/lottery');
  const sinceSsq = url.searchParams.get('ssq') || '';
  const sinceDlt = url.searchParams.get('dlt') || '';

  const errors = {};
  const [ssq, dlt] = await Promise.all([
    getSSQ(sinceSsq).catch(function (e) { errors.ssq = String((e && e.message) || e); return null; }),
    getDLT(sinceDlt).catch(function (e) { errors.dlt = String((e && e.message) || e); return null; }),
  ]);

  const out = {
    ok: !!(ssq || dlt),
    updatedAt: new Date().toISOString(),
    source: '中国福利彩票官网 / 中国体彩网',
  };
  if (ssq) out.ssq = ssq;
  if (dlt) out.dlt = dlt;
  if (!out.ok) out.errors = errors;

  return new Response(JSON.stringify(out), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=UTF-8',
      'Cache-Control': 'public, s-maxage=600, stale-while-revalidate=3600',
    },
  });
}

export const onRequest = handler;
export default handler;
