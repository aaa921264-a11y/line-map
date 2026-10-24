"""在 changelog.json 加一筆每月自動更新的紀錄(新增 / 保留 / 移除)。

python3 tools/changelog.py poles <舊 d/index.json> <新 d/index.json>
python3 tools/changelog.py roads <舊 roads/index.json> <新 roads/index.json>
"""
import json, sys, datetime, os
kind, old_f, new_f = sys.argv[1:4]
load = lambda f: json.load(open(f, encoding='utf-8')) if os.path.exists(f) else {}
old, new = load(old_f), load(new_f)
today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
def names(ix): return {r[0]: r[1] for r in ix.get('lines', [])}
def few(xs, n=40): xs = sorted(xs); return xs[:n] + ([f'…等共 {len(xs)} 條'] if len(xs) > n else [])
if kind == 'poles':
    a, b = names(old), names(new)
    add, rem, keep = set(b) - set(a), set(a) - set(b), set(a) & set(b)
    changed = [n for n in keep if a[n] != b[n]]
    pa, pb = sum(a.values()), sum(b.values())
    e = {'date': today, 'ver': '自動', 'title': '每月更新全台電桿(台電開放資料)',
         'added': ([f'新的線路 {len(add)} 條:'] + few(add)) if add else [],
         'kept': [f'{len(keep)} 條線保留(顏色不變),其中 {len(changed)} 條電桿數有增減', f'電桿總數 {pa:,} → {pb:,} 支({pb - pa:+,})'],
         'removed': ([f'台電資料裡已經沒有的線路 {len(rem)} 條:'] + few(rem)) if rem else []}
else:
    ra, rb, na, nb = old.get('roads', 0), new.get('roads', 0), old.get('named', 0), new.get('named', 0)
    e = {'date': today, 'ver': '自動', 'title': '每月更新全台街道(OpenStreetMap)',
         'added': [f'道路 {ra:,} → {rb:,} 條({rb - ra:+,})', f'路名 {na:,} → {nb:,} 個({nb - na:+,})'] if (rb != ra or nb != na) else [],
         'kept': ['其他道路保留,自繪街道的畫法不變'], 'removed': [] if rb >= ra else [f'減少 {ra - rb:,} 條(OpenStreetMap 上已刪除或合併的路段)']}
log = load('changelog.json') or []
log.append(e)
json.dump(log, open('changelog.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(e, ensure_ascii=False))
