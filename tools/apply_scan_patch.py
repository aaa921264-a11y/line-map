#!/usr/bin/env python3
"""把「拍照辨識事故單」接進定位地圖(正式版 index.html 與測試版 beta/index.html 都用這支)。
做三件事:
  1. 巡視紀錄 → 事故 分頁,「＋ 新增事故」下面加一顆「📷 拍照辨識事故單」連到 scan/ 頁面。
  2. 從 scan/ 帶回來(網址尾巴 #scan)時,自動開「新增事故」表單並預填;幹線＋桿號比對得到就帶入電桿位置。
  3. 儲存事故時,如果辨識頁勾了「同時建立工作日誌草稿」,同一個 commit 多寫一筆工作日誌(進行中、關聯這筆事故)。
用法(在 line-map repo 根目錄;scan/index.html 要先放好):
  python3 -I tools/apply_scan_patch.py beta/index.html 20261122-120000 v10.34
  python3 -I tools/apply_scan_patch.py index.html      20261122-120000 v10.34
第 2、3 個參數是新的 build 與版本號;有給的話,同一個資料夾的 version.json 會一起更新。
任何一個定位點對不上就整支不改、直接報錯(不會改壞檔案)。"""
import re, sys, pathlib

JS = r'''// ---------- 拍照辨識事故單:從 scan/ 頁面帶回來的內容,開「新增事故」表單並預填 ----------
// scan/ 頁面把辨識結果存在 localStorage 'lm:scan'(同一個網站,兩頁共用),再跳回這裡並加上 #scan。
async function scanHandoff(){
  if(location.hash !== '#scan') return;
  history.replaceState(null, '', location.pathname + location.search);
  let d = null;
  try{ d = JSON.parse(localStorage.getItem('lm:scan') || 'null'); localStorage.removeItem('lm:scan'); }catch(e){}
  if(!d || !d.pre || Date.now() - d.at > 30 * 60 * 1000){ toast('沒有可帶入的辨識資料,請重新拍照'); return; }
  const pre = d.pre;
  for(let i = 0; i < 50 && !LINE_META.size; i++) await new Promise(r => setTimeout(r, 100));   // 等線路索引載入
  try{
    const name = [pre.line, pre.line + '線'].filter(Boolean).find(n => LINE_META.has(n) || S.byLine.has(n));
    if(name){
      pre.line = name;
      await ensureLines([name]);
      const p = findPole(name, pre.pole);
      if(p && hasLoc(p)){ pre.loc = { lat: +p.lat.toFixed(6), lng: +p.lng.toFixed(6) }; pre.pole = p.poleNo || pre.pole; }
    }
  }catch(e){}
  recOpen('acc', 'form', { kind: 'acc', pre, withLog: !!d.withLog });
  toast(pre.loc ? '已帶入辨識結果,並比對到電桿位置。請檢查後按「儲存」' : '已帶入辨識結果,桿位沒比對到,請手動確認位置。檢查後按「儲存」', 5500);
}
'''

LOG = r'''
      if(!edit && RS.ctx.withLog){   // 拍照辨識:同時建立工作日誌草稿(進行中,關聯這筆事故)
        const lg = { id: rId(), date: (r.start || '').slice(0, 10), cat: '事故搶修', start: (r.start || '').slice(11, 16), end: '', line: r.line, pole: r.pole, place: r.address || '', loc: L,
          content: (r.types || []).join('、') + (r.customer ? '(' + r.customer + ')' : ''), leader: rMe(), crew: '', outage: false, mat: '', status: 'doing', next: '', due: '', weather: '', acc: r.id, ph: [], at: now, upd: now };
        if(by) lg.by = by;
        edits.push({ path: 'r/log/' + rYm(lg.date) + '.json', mutate: d => { d[lg.id] = lg; } });
        scanLogMade = true;
      }'''

def once(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit('找不到定位點(%s):出現 %d 次,應該剛好 1 次,沒有修改任何檔案' % (what, n))
    return s.replace(old, new)

def main():
    path = pathlib.Path(sys.argv[1]); build = sys.argv[2] if len(sys.argv) > 2 else None; ver = sys.argv[3] if len(sys.argv) > 3 else None
    s = path.read_text(encoding='utf-8')
    if 'scanHandoff' in s:
        sys.exit('這個檔案已經加過了(有 scanHandoff),沒有修改')
    beta = 'function betaTap(' in s or 'function betaBoot(' in s
    href = '../scan/?from=beta' if beta else 'scan/?from=main'
    # 1) 事故清單上方的按鈕
    old = "'<button class=\"btn wide\" type=\"button\" data-rk=\"new\" data-kind=\"acc\">＋ 新增事故</button>'"
    new = old + " + '<a class=\"btn ghost wide\" href=\"" + href + "\" style=\"margin-top:8px;text-decoration:none\">📷 拍照辨識事故單</a>'"
    s = once(s, old, new, '新增事故按鈕')
    # 2) 接收程式(放在「畫面」區塊前面)
    s = once(s, '// ---- 畫面 ----\nlet RS = null;', JS.rstrip('\n') + '\n// ---- 畫面 ----\nlet RS = null;', '畫面區塊')
    # 3) 儲存事故時一起建工作日誌草稿
    s = once(s, "      edits.push({ path: 'r/acc.json', mutate: d => { d[r.id] = r; } });", "      edits.push({ path: 'r/acc.json', mutate: d => { d[r.id] = r; } });" + LOG, '儲存事故')
    s = once(s, "      msg = (edit ? '更新' : '新增') + '事故 ' + r.line + ' ' + r.pole;", "      msg = (edit ? '更新' : '新增') + '事故 ' + r.line + ' ' + r.pole + (scanLogMade ? '(含工作日誌草稿)' : '');", '事故 commit 訊息')
    s = once(s, "    let msg = '';\n    if(kind === 'acc'){", "    let msg = '', scanLogMade = false;\n    if(kind === 'acc'){", 'msg 宣告')
    # 4) 開啟時檢查有沒有辨識結果
    s = once(s, '\n  showVersion();\n', '\n  showVersion();\n  try{ scanHandoff(); }catch(e){}\n', '啟動區塊')
    # 5) 版本
    if build:
        s, n = re.subn(r'const SITE_BUILD = "\d{8}-\d{6}";', 'const SITE_BUILD = "%s";' % build, s)
        if n != 1: sys.exit('找不到 SITE_BUILD')
    path.write_text(s, encoding='utf-8')
    vj = path.parent / 'version.json'
    if build and ver and vj.exists():
        vj.write_text('{"build": "%s", "ver": "%s"}' % (build, ver), encoding='utf-8'); print('已更新', vj)
    print('OK', path, '(測試版)' if beta else '(正式版)')
main()
