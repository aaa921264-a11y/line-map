"""查一支電桿的經緯度(給街景技能用)。

python3 tools/pole_lookup.py 民一43          → 民一幹#43 24.95xxx 121.07xxx
python3 tools/pole_lookup.py 中市幹#1-5支桿
資料:網站的 d/index.json + d/p*.json(全台電桿)。座標是 TWD97 TM2,換成經緯度。
"""
import json, math, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
ix = json.loads((root / 'd' / 'index.json').read_text(encoding='utf-8'))
q = re.sub(r'\s+', '', sys.argv[1]).replace('＃', '#')
short = lambda n: re.sub(r'(幹線|幹|分線|線)$', '', re.sub(r'\([^)]*\)$', '', n))
names = [r[0] for r in ix['lines']]
cands = [n for n in names if q.startswith(n)] or [n for n in names if short(n) and q.startswith(short(n))]
if not cands: sys.exit('找不到線路:' + q)
best = max(len(n) if q.startswith(n) else len(short(n)) for n in cands)
cands = [n for n in cands if (len(n) if q.startswith(n) else len(short(n))) == best]
rest = q[best:].lstrip('#').upper().replace('R', '右').replace('L', '左')
key = '#' + rest
A, F = 6378137.0, 1 / 298.257222101
def inv(X, Y, lon0=121, k0=0.9999, x0=250000):
    e2 = F * (2 - F); ep2 = e2 / (1 - e2); x = X - x0; M = Y / k0
    mu = M / (A * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256)); e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
    C = ep2 * math.cos(p1) ** 2; T = math.tan(p1) ** 2; N = A / math.sqrt(1 - e2 * math.sin(p1) ** 2); R = A * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5; D = x / (N * k0)
    lat = p1 - (N * math.tan(p1) / R) * (D * D / 2 - (5 + 3 * T + 10 * C - 4 * C * C - 9 * ep2) * D ** 4 / 24)
    lon = (D - (1 + 2 * T + C) * D ** 3 / 6) / math.cos(p1)
    return math.degrees(lat), lon0 + math.degrees(lon)
files = {r[0]: ix['files'][r[4]] for r in ix['lines']}
found = []
for n in cands:
    for l in json.loads((root / files[n]).read_text(encoding='utf-8'))['lines']:
        if l['name'] != n: continue
        for p in l['poles']:
            if p[0] == key: found.append((n, p))
if not found: sys.exit(f'{cands[0]} 找不到 {key}')
for n, p in found:
    lat, lng = inv(p[1], p[2])
    print(f'{n}{p[0]}\t{lat:.6f}\t{lng:.6f}\t{p[3]}')
