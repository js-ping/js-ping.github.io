/**
 * 临时探测函数（用完即删）—— 路径 /probe-src
 *
 * 目的：本站的 /api/lottery 跑在 EdgeOne 上，出口在境外，去抓福彩/体彩官网被封
 *      （cwl.gov.cn → 403，webapi.sporttery.cn → 567）。
 *      本函数用同一个境外出口，批量试所有已知的「彩票开奖数据源」，
 *      看有没有哪一个在境外可达。若有一个可用，就不必再引入大陆云函数。
 *
 * 输出：每个源的 HTTP 状态码 + 前若干字节正文 + 耗时。
 * 只读，不做任何写操作，不碰用户数据。
 */

const UA_WIN = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
               '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

const TARGETS = [
  { id: 'cwl-api-ssq',     tag: '官方',     url: 'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice?name=ssq&issueCount=3&pageNo=1&pageSize=3', ref: 'https://www.cwl.gov.cn/' },
  { id: 'cwl-root',        tag: '官方',     url: 'https://www.cwl.gov.cn/', ref: 'https://www.cwl.gov.cn/' },
  { id: 'sporttery-api',   tag: '官方',     url: 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=85&provinceId=0&isVerify=1&pageNo=1&pageSize=3', ref: 'https://www.lottery.gov.cn/' },
  { id: 'sporttery-root',  tag: '官方',     url: 'https://webapi.sporttery.cn/', ref: 'https://www.lottery.gov.cn/' },
  { id: 'lottery-gov',     tag: '官方',     url: 'https://www.lottery.gov.cn/', ref: 'https://www.lottery.gov.cn/' },
  { id: 'zhcw-ssq',        tag: '媒体',     url: 'https://www.zhcw.com/kjxx/ssq/', ref: 'https://www.zhcw.com/' },
  { id: 'zhcw-api',        tag: '媒体',     url: 'https://jc.zhcw.com/port/client_json.php?transactionType=10001001&lotteryId=1&issueCount=3&type=0', ref: 'https://www.zhcw.com/' },
  { id: '500-dc-ssq',      tag: '数据站',   url: 'https://datachart.500.com/ssq/history/newinc/history.php?limit=3', ref: 'https://datachart.500.com/ssq/history/history.shtml' },
  { id: '500-dc-dlt',      tag: '数据站',   url: 'https://datachart.500.com/dlt/history/newinc/history.php?limit=3', ref: 'https://datachart.500.com/dlt/history/history.shtml' },
  { id: '17500-txt-ssq',   tag: '数据站',   url: 'https://www.17500.cn/getData/ssq.TXT', ref: 'https://www.17500.cn/' },
  { id: '17500-txt-dlt',   tag: '数据站',   url: 'https://www.17500.cn/getData/dlt.TXT', ref: 'https://www.17500.cn/' },
  { id: '17500-home',      tag: '数据站',   url: 'https://www.17500.cn/', ref: 'https://www.17500.cn/' },
  { id: 'sina-zst',        tag: '门户',     url: 'https://match.lottery.sina.com.cn/lotto/pc_zst/index?lottoType=ssq&actionType=chzs', ref: 'https://lottery.sina.com.cn/' },
  { id: 'netease-award',   tag: '门户',     url: 'https://caipiao.163.com/award/ssq/', ref: 'https://caipiao.163.com/' },
];

function trim(s, n) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim().slice(0, n); }

async function probe(url, headers) {
  const t0 = Date.now();
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 6000);
  try {
    const res = await fetch(url, { headers, redirect: 'follow', signal: ac.signal });
    const text = await res.text();
    return {
      status: res.status,
      ms: Date.now() - t0,
      ct: trim(res.headers.get('content-type'), 50),
      len: text.length,
      head: trim(text, 170),
    };
  } catch (e) {
    return { status: 'ERR', ms: Date.now() - t0, err: trim(String(e && e.message || e), 120) };
  } finally {
    clearTimeout(timer);
  }
}

async function runOne(t) {
  const refOrigin = t.ref ? t.ref.replace(/^(https?:\/\/[^/]+).*$/, '$1') : '';
  const hdrs = { 'User-Agent': UA_WIN, 'Accept': 'application/json,text/html,text/plain,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9' };
  if (t.ref) hdrs['Referer'] = t.ref;

  const plain = await probe(t.url, {});
  const spoof = await probe(t.url, hdrs);

  const isOk = r => typeof r.status === 'number' && r.status >= 200 && r.status < 300 && r.len > 0;
  return {
    id: t.id, tag: t.tag,
    verdict: isOk(spoof) ? (isOk(plain) ? 'PASS-BOTH' : 'PASS-需要浏览器头') : (isOk(plain) ? 'PASS-裸请求' : 'FAIL'),
    plain, spoof, origin: refOrigin,
  };
}

async function handler(context) {
  const url = new URL((context && context.request && context.request.url) || 'https://x/probe-src');
  const peek = url.searchParams.get('peek') || '';

  // ---- 模式二：?peek=<id> —— 把某个源的头尾抓回来，验证「格式 + 新鲜度」 ----
  if (peek) {
    const t = TARGETS.filter(x => x.id === peek)[0];
    if (!t) return new Response(JSON.stringify({ err: 'unknown id: ' + peek }), { status: 400 });
    const refOrigin = t.ref ? t.ref.replace(/^(https?:\/\/[^/]+).*$/, '$1') : 'https://x/';
    const hdrs = { 'User-Agent': UA_WIN, 'Accept': 'application/json,text/html,text/plain,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9' };
    if (t.ref) { hdrs['Referer'] = t.ref; hdrs['Origin'] = refOrigin; }
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 10000);
    try {
      const res = await fetch(t.url, { headers: hdrs, redirect: 'follow', signal: ac.signal });
      const text = await res.text();
      const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      return new Response(JSON.stringify({
        id: t.id, url: t.url, status: res.status,
        totalLen: text.length, totalLines: lines.length,
        head5: lines.slice(0, 5).map(s => s.slice(0, 200)),
        tail8: lines.slice(-8).map(s => s.slice(0, 200)),
      }, null, 2), { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
    } catch (e) {
      return new Response(JSON.stringify({ id: t.id, status: 'ERR', err: String(e && e.message || e).slice(0, 200) }), {
        headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
    } finally { clearTimeout(timer); }
  }

  const only = (url.searchParams.get('only') || '').split(',').map(s => s.trim()).filter(Boolean);
  const list = only.length ? TARGETS.filter(t => only.includes(t.id)) : TARGETS;

  // 全部并发跑，单次上限 6 秒 → 整体最坏约 8 秒，够 EdgeOne 函数跑完
  const out = await Promise.all(list.map(runOne));

  const pass = out.filter(r => r.verdict.startsWith('PASS'));
  return new Response(JSON.stringify({
    at: new Date().toISOString(),
    egress: 'edgeone (境外)',
    summary: {
      总数: out.length,
      可行的: pass.map(r => r.id),
      全挂: pass.length === 0,
    },
    results: out,
  }, null, 2), {
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

export const onRequest = handler;
export default handler;
