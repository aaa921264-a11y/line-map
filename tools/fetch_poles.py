"""下載台電「各縣市電桿坐標及桿號」開放資料(data.gov.tw)。先檢查 robots.txt,被禁止就停止。

python3 fetch_poles.py meta <out>            # 查資料集清單和下載網址
python3 fetch_poles.py download <out> <urls...>
"""
import json, os, sys, time, urllib.request, urllib.robotparser, urllib.parse, gzip
UA = 'line-map-bot/1.0 (+https://github.com/aaa921264-a11y/line-map)'
_rp = {}
def allowed(url):
    p = urllib.parse.urlparse(url); host = f'{p.scheme}://{p.netloc}'
    if host not in _rp:
        rp = urllib.robotparser.RobotFileParser()
        try:
            with urllib.request.urlopen(urllib.request.Request(host + '/robots.txt', headers={'User-Agent': UA}), timeout=20) as r:
                txt = r.read().decode('utf-8', 'replace')
            rp.parse(txt.splitlines()); _rp[host] = (rp, txt)
        except Exception as e:
            _rp[host] = (None, f'(讀不到 robots.txt:{e})')
    rp = _rp[host][0]
    return rp is None or (rp.can_fetch(UA, url) and rp.can_fetch('*', url))
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=180) as r:
        return r.read(), r.headers.get('content-type', ''), r.url
mode, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
log = []
if mode == 'meta':
    ids = [33305] + list(range(122725, 122750)) + list(range(139295, 139330))
    found = {}
    for i in ids:
        u = f'https://data.gov.tw/api/v2/rest/dataset/{i}'
        if not allowed(u): log.append(f'robots 不允許 {u}'); continue
        try:
            body, ct, _ = get(u); j = json.loads(body)
            r = j.get('result') or j
            title = r.get('title', '')
            if '電桿' in title: found[i] = r; log.append(f'{i} {title}')
        except Exception as e: log.append(f'{i} 錯誤 {e}')
        time.sleep(0.5)
    json.dump(found, open(f'{out}/datasets.json', 'w'), ensure_ascii=False, indent=1)
else:
    for k, u in enumerate(sys.argv[3:]):
        if not allowed(u): log.append(f'robots 不允許 {u}'); continue
        try:
            body, ct, final = get(u)
            name = f'{k:02d}_' + (os.path.basename(urllib.parse.urlparse(final).path) or 'file')[:60]
            with gzip.open(f'{out}/{name}.gz', 'wb') as f: f.write(body)
            log.append(f'ok {u} -> {name}.gz {len(body):,} bytes {ct}')
        except Exception as e: log.append(f'錯誤 {u} {e}')
        time.sleep(1)
for h, (_, txt) in _rp.items(): log.append(f'--- {h}/robots.txt ---\n{txt[:3000]}')
open(f'{out}/log.txt', 'w').write('\n'.join(log) + '\n'); print('\n'.join(log[:80]))
