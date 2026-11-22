#!/usr/bin/env python3
"""搜尋統計補丁 v10.35(只改正式版,測試版 beta/ 不動)

用法:  python3 -I apply_search_stats_patch.py <line-map 資料夾>
做的事:
  1. index.html:新增「🔎 搜尋統計」按鈕與獨立全螢幕畫面(全員/我個人)、搜尋紀錄上傳(Pole-photo r/search/)、搜尋熱點圖層
  2. SITE_BUILD 與 version.json 升到 v10.35(打開網頁的手機會自動換成新版)
安全:每個修改點都必須剛好找到 1 處才會動手,任何一處對不上就整個停止、不寫任何檔案;已經套過會拒絕再套。
退回:git revert 這次提交(或把 index.html、version.json 還原成 v10.34)。
"""
import sys, re, pathlib, subprocess, shutil, tempfile

VER, BUILD = 'v10.35', '20261122-082500'
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.')
idx, ver = root / 'index.html', root / 'version.json'
src = idx.read_text(encoding='utf-8')
if 'ssLog(' in src:
    sys.exit('已經套用過搜尋統計補丁,不重複套用。')

BLOCK = r"""// ---------- 搜尋統計(v10.35):每次找到結果就上傳一筆紀錄到 Pole-photo 的 r/search/<年-月>.json,統計畫面讀回來算 ----------
// 一筆紀錄:{ id, t 時間毫秒, u 這支手機的代碼, by 名字(沿用 lm:me), k 種類 pole/code/road, q 打的字, l 顯示名稱, ln 線路, no 桿號, la/lo 位置, c 縣市 }
// 沒網路或沒貼 token 時先存在這支手機(lm:ssq),之後補傳;上傳失敗不影響搜尋本身。只記錄「找得到結果」的搜尋。
const SS_Q_KEY = 'lm:ssq', SS_SID_KEY = 'lm:sid', SS_KIND = { pole: '電桿', code: '電力座標', road: '路名' };
let SS_Q = [], ssBusy = false, ssTimer = null, ssFailAt = 0;
function ssSid(){ let v = ''; try{ v = localStorage.getItem(SS_SID_KEY) || ''; if(!v){ v = rId(); localStorage.setItem(SS_SID_KEY, v); } }catch(e){} return v || 'anon'; }
function ssCounty(e){
  try{
    const m = e.line && LINE_META.get(e.line), c = m ? countyOf(m) : '';
    if(c) return c;
    if(typeof e.lat === 'number' && typeof MAP_COUNTIES !== 'undefined'){
      let best = '', bd = 1e9;
      MAP_COUNTIES.forEach(([n, la, lo]) => { const d = Math.hypot(la - e.lat, (lo - e.lng) * 0.92); if(d < bd){ bd = d; best = n; } });
      return best;
    }
  }catch(err){}
  return '';
}
function ssLog(e){
  try{
    const t = e.t || Date.now();
    const r = { id: t.toString(36) + Math.random().toString(36).slice(2, 5), t, u: ssSid(), by: rMe() || '', k: e.kind || '', q: String(e.q || '').slice(0, 40), l: String(e.label || '').slice(0, 40) };
    if(e.line) r.ln = e.line;
    if(e.no) r.no = e.no;
    if(typeof e.lat === 'number' && isFinite(e.lat) && typeof e.lng === 'number'){ r.la = +e.lat.toFixed(5); r.lo = +e.lng.toFixed(5); }
    const c = ssCounty(e); if(c) r.c = c;
    SS_Q.push(r); if(SS_Q.length > 300) SS_Q = SS_Q.slice(-300);
    lsSet(SS_Q_KEY, SS_Q);
    ssFlushSoon(20000);
  }catch(err){}
}
function ssFlushSoon(ms){ clearTimeout(ssTimer); ssTimer = setTimeout(ssFlush, ms); }
async function ssFlush(){
  if(ssBusy || !SS_Q.length || !ghTok() || navigator.onLine === false) return;
  if(Date.now() - ssFailAt < 60000){ ssFlushSoon(65000); return; }
  ssBusy = true;
  const batch = SS_Q.slice(0, 100), byM = {};
  batch.forEach(r => { const m = ymd(r.t).slice(0, 7); (byM[m] = byM[m] || []).push(r); });
  try{
    await rSave('搜尋紀錄 ' + batch.length + ' 筆', Object.keys(byM).map(m => ({ path: 'r/search/' + m + '.json', mutate: d => { byM[m].forEach(r => { d[r.id] = r; }); } })));
    const sent = new Set(batch.map(r => r.id));
    SS_Q = SS_Q.filter(r => !sent.has(r.id)); lsSet(SS_Q_KEY, SS_Q);
  }catch(e){ ssFailAt = Date.now(); }
  ssBusy = false;
  if(SS_Q.length) ssFlushSoon(Date.now() - ssFailAt < 60000 ? 65000 : 3000);
}
function ssBoot(){
  SS_Q = lsGet(SS_Q_KEY, []); if(!Array.isArray(SS_Q)) SS_Q = [];
  if(SS_Q.length) ssFlushSoon(8000);
  document.addEventListener('visibilitychange', () => { if(!document.hidden && SS_Q.length) ssFlushSoon(3000); });
  window.addEventListener('online', () => { if(SS_Q.length) ssFlushSoon(3000); });
  document.addEventListener('click', e => { if(e.target.closest && e.target.closest('[data-ss="open"]')) ssOpen(); });
}
// <ss-pure>
// 統計計算(純函式,不碰畫面):rows 是搜尋紀錄陣列
function ssAgg(rows){
  const A = { n: rows.length, users: new Map(), poles: new Map(), lines: new Map(), county: new Map(), day: new Map(), month: new Map(), hour: new Array(24).fill(0), first: 0, today: 0, geo: 0 };
  const todayS = ymd(Date.now());
  const bump = (m, key, r, sub) => {
    let o = m.get(key); if(!o){ o = { key, n: 0, last: 0, by: new Map(), kind: r.k || '', sub: new Map() }; m.set(key, o); }
    o.n++; if(r.t > o.last) o.last = r.t;
    const who = r.by || '未命名'; o.by.set(who, (o.by.get(who) || 0) + 1);
    if(sub) o.sub.set(sub, (o.sub.get(sub) || 0) + 1);
    return o;
  };
  rows.forEach(r => {
    const who = r.by || '未命名'; A.users.set(who, (A.users.get(who) || 0) + 1);
    if(!A.first || r.t < A.first) A.first = r.t;
    const d = ymd(r.t); A.day.set(d, (A.day.get(d) || 0) + 1);
    const mo = d.slice(0, 7); A.month.set(mo, (A.month.get(mo) || 0) + 1);
    A.hour[new Date(r.t).getHours()]++;
    if(d === todayS) A.today++;
    if(r.l) bump(A.poles, (r.k || '') + '|' + r.l, r);
    if(r.ln) bump(A.lines, r.ln, r, r.l || '');
    if(r.c) bump(A.county, r.c, r);
    if(typeof r.la === 'number') A.geo++;
  });
  return A;
}
const ssTop = (m, n) => Array.from(m.values()).sort((a, b) => b.n - a.n || b.last - a.last).slice(0, n);
function ssDays(A, days){   // 最近 days 天,每天的次數(含 0)
  const out = [], d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() - days + 1);
  for(let i = 0; i < days; i++){ const k = ymd(d); out.push([k, A.day.get(k) || 0]); d.setDate(d.getDate() + 1); }
  return out;
}
// </ss-pure>
// ---- 畫面 ----
const SSR = { scope: 'all', range: 3, rank: 'line', mon: '', open: {}, more: 50, rows: null, err: false };
function ssBars(list, key){
  if(!list.length) return '<div class="empty">還沒有資料。</div>';
  const max = list[0].n;
  return '<div class="bars">' + list.map(o => {
    const id = key + '|' + o.key, open = !!SSR.open[id], name = key === 'pole' ? o.key.split('|').slice(1).join('|') : o.key;
    return '<div class="bar"><button type="button" class="linkish" style="display:block;width:100%;text-decoration:none;color:inherit;text-align:left;min-height:44px" data-ss="row" data-k="' + esc(id) + '" aria-expanded="' + open + '">'
      + '<div class="bl"><span>' + esc(name) + (key === 'pole' && o.kind ? ' <small class="tag">' + esc(SS_KIND[o.kind] || '') + '</small>' : '') + '</span><b class="num">' + o.n + ' 次</b></div>'
      + '<div class="bt"><div class="bf" style="width:' + Math.max(3, Math.round(o.n / max * 100)) + '%"></div></div></button>'
      + (open ? '<div class="hint" style="margin:2px 0 6px">最後搜尋 ' + esc(hhmmDay(o.last)) + ' · 搜尋過的人:' + esc(Array.from(o.by.entries()).sort((a, b) => b[1] - a[1]).map(([w, n]) => w + '×' + n).join('、'))
        + (o.sub.size ? '<br>被搜尋的桿:' + esc(Array.from(o.sub.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([w, n]) => w + '×' + n).join('、')) : '') + '</div>' : '')
      + '</div>';
  }).join('') + '</div>';
}
function ssLineSvg(days){
  const W = 320, H = 112, pl = 26, pr = 8, pt = 10, pb = 20, vals = days.map(d => d[1]), max = Math.max(1, ...vals);
  const step = (W - pl - pr) / Math.max(1, vals.length - 1), X = i => pl + i * step, Y = v => pt + (H - pt - pb) * (1 - v / max);
  const pk = vals.indexOf(Math.max(...vals));
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="每日搜尋次數折線圖" style="width:100%;height:auto;display:block">'
    + '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(0) + '" y2="' + Y(0) + '" stroke="var(--line)"/><line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(max) + '" y2="' + Y(max) + '" stroke="var(--line)" stroke-dasharray="3 3"/>'
    + '<text x="' + (pl - 4) + '" y="' + (Y(max) + 3) + '" text-anchor="end" font-size="10" fill="var(--muted)">' + max + '</text><text x="' + (pl - 4) + '" y="' + (Y(0) + 3) + '" text-anchor="end" font-size="10" fill="var(--muted)">0</text>'
    + '<polyline fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" points="' + vals.map((v, i) => X(i).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ') + '"/>'
    + (vals[pk] > 0 ? '<circle cx="' + X(pk).toFixed(1) + '" cy="' + Y(vals[pk]).toFixed(1) + '" r="3.5" fill="var(--accent)"/>' : '')
    + '<text x="' + pl + '" y="' + (H - 4) + '" font-size="10" fill="var(--muted)">' + esc(days[0][0].slice(5)) + '</text><text x="' + (W - pr) + '" y="' + (H - 4) + '" text-anchor="end" font-size="10" fill="var(--muted)">' + esc(days[days.length - 1][0].slice(5)) + '</text></svg>';
}
function ssHourSvg(hour){
  const W = 320, H = 96, pl = 6, pb = 16, max = Math.max(1, ...hour), bw = (W - pl * 2) / 24, pk = hour.indexOf(Math.max(...hour));
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="一天中各時段搜尋次數" style="width:100%;height:auto;display:block">';
  hour.forEach((v, h) => { const bh = v ? Math.max(2, (H - pb - 8) * v / max) : 0;
    s += '<rect x="' + (pl + h * bw + 1).toFixed(1) + '" y="' + (H - pb - bh).toFixed(1) + '" width="' + (bw - 2).toFixed(1) + '" height="' + bh.toFixed(1) + '" rx="1.5" fill="' + (v && h === pk ? 'var(--accent)' : 'var(--soft)') + '"/>'; });
  [0, 6, 12, 18, 23].forEach(h => { s += '<text x="' + (pl + h * bw + bw / 2).toFixed(1) + '" y="' + (H - 3) + '" text-anchor="middle" font-size="10" fill="var(--muted)">' + h + '</text>'; });
  return s + '</svg>';
}
function ssBody(){
  if(SSR.rows === null) return '<div class="empty">讀取中…</div>';
  const sid = ssSid(), name = rMe();
  const rows = SSR.scope === 'me' ? SSR.rows.filter(r => r.u === sid || (name && r.by === name)) : SSR.rows;
  const A = ssAgg(rows), rangeName = { 1: '本月', 3: '近 3 個月', 12: '近 12 個月' }[SSR.range];
  let h = '<p class="hint" style="margin:0 0 8px">統計從開始記錄那天起算,只記「找得到結果」的搜尋' + (A.first ? ';目前最早一筆是 ' + esc(ymd(A.first)) : '') + '。'
    + (SSR.err ? '<br><b style="color:var(--danger)">有些月份讀不到,數字可能偏少。</b>' : '') + (SS_Q.length ? '<br>這支手機還有 ' + SS_Q.length + ' 筆還沒上傳(有網路時會自動補傳)。' : '') + '</p>';
  if(!A.n) return h + '<div class="empty">' + (SSR.scope === 'me' ? '你在' + rangeName + '還沒有搜尋紀錄。' : rangeName + '還沒有搜尋紀錄。') + '</div>';
  const topC = ssTop(A.county, 1)[0], tile = (n, t) => '<div class="stat"><b>' + n + '</b><span>' + t + '</span></div>';
  h += '<div class="stats">' + tile(A.n, rangeName + '搜尋次數') + tile(A.today, '今天') + tile(SSR.scope === 'me' ? A.lines.size : A.users.size, SSR.scope === 'me' ? '搜尋過的線路數' : '搜尋的人數') + tile(topC ? esc(topC.key) : '—', '最常搜尋的縣市') + '</div>';
  h += '<div class="section-title"><h2>熱門排行</h2><span class="count">前 10 名</span></div>'
    + '<div class="seg-tabs" role="tablist" style="margin-top:0"><button role="tab" type="button" data-ss="rank" data-v="line" aria-selected="' + (SSR.rank === 'line') + '">依線路</button><button role="tab" type="button" data-ss="rank" data-v="pole" aria-selected="' + (SSR.rank === 'pole') + '">依電桿/座標/路名</button></div>'
    + '<div style="margin-top:10px">' + ssBars(ssTop(SSR.rank === 'line' ? A.lines : A.poles, 10), SSR.rank) + '</div><p class="hint">點一項可以看詳細。</p>';
  const nd = SSR.range === 1 ? 30 : 90;
  h += '<div class="section-title"><h2>時間趨勢</h2><span class="count">最近 ' + nd + ' 天每日次數</span></div><div class="card">' + ssLineSvg(ssDays(A, nd)) + '</div>';
  if(A.month.size > 1){ const ms = Array.from(A.month.entries()).sort((a, b) => b[0].localeCompare(a[0])); h += '<div class="rc-tbl" style="margin-top:8px">' + ms.map(([m, n]) => '<div><b>' + esc(m) + '</b><span>' + n + ' 次</span></div>').join('') + '</div>'; }
  const pkH = A.hour.indexOf(Math.max(...A.hour));
  h += '<div class="section-title"><h2>一天中的時段</h2><span class="count">尖峰 ' + pad(pkH) + ':00–' + pad(pkH) + ':59(' + A.hour[pkH] + ' 次)</span></div><div class="card">' + ssHourSvg(A.hour) + '</div>';
  const cs = ssTop(A.county, 22);
  h += '<div class="section-title"><h2>縣市分布</h2><span class="count">' + cs.length + ' 個縣市</span></div>' + (cs.length ? ssBars(cs, 'county') : '<div class="empty">沒有縣市資料。</div>')
    + '<button class="btn wide" type="button" data-ss="heat" style="margin-top:10px"' + (A.geo ? '' : ' disabled') + '>' + (ssHeatOn ? '關閉地圖上的搜尋熱點' : '在地圖上看搜尋熱點(' + A.geo + ' 筆有位置)') + '</button>';
  const list = rows.filter(r => !SSR.mon || ymd(r.t).slice(0, 7) === SSR.mon);
  h += '<div class="section-title"><h2>明細</h2><span class="count">' + list.length + ' 筆</span></div>'
    + '<div class="rc-filt"><input type="month" data-ssf="mon" value="' + esc(SSR.mon) + '" aria-label="只看某個月份"></div>'
    + (list.length ? list.slice(0, SSR.more).map(r => '<article class="item" style="padding:8px 12px"><div class="t"><div class="title" style="font-size:14px">' + esc(r.l || r.q) + '</div><span class="tag">' + esc(SS_KIND[r.k] || '') + '</span></div>'
      + '<div class="meta num">' + esc(hhmmDay(r.t)) + ' · ' + esc(r.by || '未命名') + (r.c ? ' · ' + esc(r.c) : '') + (r.q && r.q !== r.l ? ' · 輸入「' + esc(r.q) + '」' : '') + '</div></article>').join('')
      + (list.length > SSR.more ? '<button class="btn ghost wide" type="button" data-ss="more">顯示更多(還有 ' + (list.length - SSR.more) + ' 筆)</button>' : '')
      : '<div class="empty">這個月份沒有紀錄。</div>');
  return h;
}
function ssShell(inner, withTabs){
  return '<div class="sheet"><div class="lh"><b>🔎 搜尋統計</b><span class="hint"></span><button class="btn sm" type="button" data-ss="close">關閉</button></div>'
    + (withTabs ? '<div class="seg-tabs" role="tablist"><button role="tab" type="button" data-ss="scope" data-v="all" aria-selected="' + (SSR.scope === 'all') + '">全員</button><button role="tab" type="button" data-ss="scope" data-v="me" aria-selected="' + (SSR.scope === 'me') + '">我個人</button></div>'
      + '<div class="rc-filt"><select data-ssf="range" aria-label="統計範圍">' + [[1, '本月'], [3, '近 3 個月'], [12, '近 12 個月']].map(([v, n]) => '<option value="' + v + '"' + (SSR.range === v ? ' selected' : '') + '>' + n + '</option>').join('') + '</select></div>' : '')
    + '<div class="lbody">' + inner + '</div></div>';
}
function ssPaint(){
  const el = $('ssSheet'); if(!el || el.hidden) return;
  const old = el.querySelector('.lbody'), sc = old ? old.scrollTop : 0;
  let inner;
  try{ inner = ssBody(); }catch(e){ inner = '<div class="warnbox">統計畫面出錯了,其他功能不受影響。請按關閉後再試一次。</div>'; }
  el.innerHTML = ssShell(inner, true);
  const nb = el.querySelector('.lbody'); if(nb) nb.scrollTop = sc;
}
async function ssRender(reload){
  const el = $('ssSheet'); if(!el || el.hidden) return;
  if(!ghTok()){ el.innerHTML = ssShell('<p class="hint">搜尋統計包含大家的搜尋位置,只有貼過 GitHub token 的組員才看得到。</p><div class="rc-tok">' + tokFormHtml('ss') + '</div>', false); return; }
  if(reload || SSR.rows === null){
    SSR.rows = null; SSR.err = false; ssPaint(); ssFlushSoon(0);
    try{
      const ms = rMonths(SSR.range), map = new Map();
      const parts = await Promise.all(ms.map(m => rLoad('r/search/' + m + '.json', true)));
      parts.forEach(d => rList(d).forEach(r => { if(r && r.id && r.t) map.set(r.id, r); }));
      SS_Q.forEach(r => { if(ms.includes(ymd(r.t).slice(0, 7))) map.set(r.id, r); });
      SSR.rows = Array.from(map.values()).sort((a, b) => b.t - a.t);
    }catch(e){ SSR.err = true; SSR.rows = SS_Q.slice(); }
  }
  ssPaint();
}
let SSHEAT = null, ssHeatOn = false;
function ssHeatSvg(L){
  if(!ssHeatOn || !SSHEAT) return '';
  const cells = new Map();
  SSHEAT.forEach(a => { const [x, y] = TPC.toPlane(a.lat, a.lng), k = Math.floor(x / 200) + ',' + Math.floor(y / 200); let c = cells.get(k); if(!c) cells.set(k, c = { n: 0, x: 0, y: 0 }); c.n++; c.x += x; c.y += y; });
  let out = '';
  cells.forEach(c => { const [x, y] = L.toScreen(c.x / c.n, c.y / c.n), r = Math.max(10, Math.min(60, 200 / L.mpp)) * Math.min(2.2, 0.8 + c.n * 0.12);
    out += '<circle class="sheat" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="' + r.toFixed(1) + '" style="opacity:' + Math.min(0.75, 0.25 + c.n * 0.08).toFixed(2) + '"/>'
      + (c.n > 1 ? '<text class="sheat-t" x="' + x.toFixed(1) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="middle">' + c.n + '</text>' : ''); });
  return out;
}
function ssOpen(){
  let el = $('ssSheet');
  if(!el){ el = document.createElement('div'); el.id = 'ssSheet'; el.className = 'modal layers rec'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); document.body.appendChild(el); el.addEventListener('click', ssClick); el.addEventListener('change', ssChange); }
  el.hidden = false; document.documentElement.classList.add('rec-open');
  ssRender(true);
}
function ssClose(){ const el = $('ssSheet'); if(el){ el.hidden = true; el.innerHTML = ''; } document.documentElement.classList.remove('rec-open'); }
async function ssClick(e){
  const b = e.target.closest('[data-ss]'); if(!b) return; const a = b.dataset.ss;
  try{
    if(a === 'close') ssClose();
    else if(a === 'savetok'){ if(await saveTokFrom($('ghTokIn'))) ssRender(true); }
    else if(a === 'scope'){ SSR.scope = b.dataset.v; SSR.more = 50; ssPaint(); }
    else if(a === 'rank'){ SSR.rank = b.dataset.v; ssPaint(); }
    else if(a === 'row'){ const k = b.dataset.k; SSR.open[k] = !SSR.open[k]; ssPaint(); }
    else if(a === 'more'){ SSR.more += 50; ssPaint(); }
    else if(a === 'heat'){
      if(ssHeatOn){ ssHeatOn = false; LMap.req(); toast('已關閉搜尋熱點'); ssPaint(); return; }
      const sid = ssSid(), name = rMe();
      const rows = (SSR.scope === 'me' ? SSR.rows.filter(r => r.u === sid || (name && r.by === name)) : SSR.rows).filter(r => typeof r.la === 'number' && typeof r.lo === 'number');
      SSHEAT = rows.map(r => ({ lat: r.la, lng: r.lo })).filter(inRegion);
      if(!SSHEAT.length){ toast('這些搜尋的位置都不在' + REGION.name + '範圍內'); return; }
      ssHeatOn = true; ssClose(); setFollow(false); LMap.fit(SSHEAT); LMap.req();
      $('mapWrap').scrollIntoView({ block: 'start', behavior: 'smooth' });
      toast('地圖上藍圈是搜尋熱點(' + (SSR.scope === 'me' ? '我個人' : '全員') + '),到統計畫面可以關閉', 4500);
    }
  }catch(err){ toast('統計畫面出錯了,請再試一次'); }
}
function ssChange(e){
  const t = e.target;
  if(t.dataset.ssf === 'range'){ SSR.range = +t.value; SSR.more = 50; ssRender(true); }
  if(t.dataset.ssf === 'mon'){ SSR.mon = t.value; SSR.more = 50; ssPaint(); }
}
"""

CSS = """#ssSheet{z-index:65;}
#ssSheet[hidden]{display:none;}
.map .sheat{fill:#1a73e8;}
.map .sheat-t{font-size:12px; font-weight:700; fill:#fff;}
"""
BTN = '\n    <button class="btn ghost wide" type="button" data-ss="open" style="margin-top:8px">🔎 搜尋統計(全員與我個人)</button>'

edits = [
  ('#recSheet[hidden]{display:none;}', '#recSheet[hidden]{display:none;}\n' + CSS.rstrip('\n')),
  ('📋 巡視紀錄(事故、巡修、工作日誌、統計)</button>', '📋 巡視紀錄(事故、巡修、工作日誌、統計)</button>' + BTN),
  ('function addHist(e){\n  e.t = Date.now();\n', 'function addHist(e){\n  e.t = Date.now();\n  ssLog(e);   // v10.35:同時記一筆到搜尋統計(出錯不影響搜尋)\n'),
  ('// ---------- 搜尋紀錄(只存在這支手機的瀏覽器,不佔網站空間) ----------', BLOCK + '// ---------- 搜尋紀錄(只存在這支手機的瀏覽器,不佔網站空間) ----------'),
  ('+ measureSvg(L);', '+ measureSvg(L) + ssHeatSvg(L);'),
  ('  checkNewVersion();\n  showVersion();\n', '  checkNewVersion();\n  showVersion();\n  try{ ssBoot(); }catch(e){}\n'),
  ('紀錄只存在這支手機,不會上傳。', '這裡的紀錄存在這支手機;找到結果的搜尋會另外上傳,供「搜尋統計」使用。'),
  ('const SITE_BUILD = "20261121-074500";', 'const SITE_BUILD = "%s";' % BUILD),
]
out = src
for old, new in edits:
    n = out.count(old)
    if n != 1:
        sys.exit('找不到唯一的修改點(找到 %d 處),整個補丁取消、沒有改任何檔案:%r' % (n, old[:40]))
    out = out.replace(old, new, 1)

# 語法檢查:把 <script> 抽出來交給 node(沒有 node 就略過)
node = shutil.which('node')
if node:
    m = re.search(r'<script>\n(.*?)</script>', out, re.S)
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / 'check.js'; f.write_text(m.group(1), encoding='utf-8')
        r = subprocess.run([node, '--check', str(f)], capture_output=True, text=True)
        if r.returncode: sys.exit('新程式語法有誤,沒有改任何檔案:\n' + r.stderr)
else:
    print('(找不到 node,略過語法檢查)')

vj = ver.read_text(encoding='utf-8')
new_vj = re.sub(r'"build":\s*"[^"]*"', '"build": "%s"' % BUILD, vj)
new_vj = re.sub(r'"ver":\s*"[^"]*"', '"ver": "%s"' % VER, new_vj)
idx.write_text(out, encoding='utf-8'); ver.write_text(new_vj, encoding='utf-8')
print('完成:index.html、version.json 已升到', VER, BUILD)
