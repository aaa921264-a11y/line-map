"""全台電桿 → 圖層檔(台電開放資料「台灣電力公司電桿坐標及桿號」all.csv)。

每個區處寫桿號的習慣不同,所以:
  - 桃園市:跟原本一樣,只收「…幹 / …分線 / …支線」(加上望間、望湖分線),顏色沿用原本的。
  - 其他縣市:桿號開頭的文字就是線路名稱(例如 中寮幹#163、十吉192右#10 → 十吉、大河27 → 大河),
    同一縣市同名的桿視為同一條線;少於 5 支的不收(多半是打錯字)。
  - 同一個名稱出現在不同縣市、而且相距 1.5 公里以上 → 不同的線,桃園以外的名稱後面加(縣市)。
  - 澎湖、金門、連江的坐標是 119 度分帶,轉成本島 121 度分帶,地圖才能畫在一起。

usage: python3 tools/build_lines_tw.py <all.csv> <out dir> <colour seeds: old index or {name: colour} json> ...
"""
import csv, json, math, re, sys, collections, pathlib

SRC, OUT, OLDS = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3:]
OUT.mkdir(parents=True, exist_ok=True)
for f in list(OUT.glob('*.json')) + list(OUT.glob('d/*.json')): f.unlink()
EXTRA = ['望間分線', '望湖分線']
CHUNK_BYTES = 600_000
HOME = '桃園市'
ISLANDS = {'澎湖縣', '金門縣', '連江縣'}
N_COLORS = 20

# ---------- Transverse Mercator (GRS80) ----------
A_, F_ = 6378137.0, 1 / 298.257222101
E2 = F_ * (2 - F_); EP2 = E2 / (1 - E2)
def _M(phi):
    e2 = E2
    return A_ * ((1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256) * phi - (3 * e2 / 8 + 3 * e2 * e2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
                 + (15 * e2 * e2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi) - (35 * e2 ** 3 / 3072) * math.sin(6 * phi))
def tm_fwd(lat, lon, lon0, k0=0.9999, x0=250000):
    phi, lam = math.radians(lat), math.radians(lon - lon0)
    N = A_ / math.sqrt(1 - E2 * math.sin(phi) ** 2); T = math.tan(phi) ** 2; C = EP2 * math.cos(phi) ** 2
    A = lam * math.cos(phi)
    x = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * EP2) * A ** 5 / 120)
    y = k0 * (_M(phi) + N * math.tan(phi) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24 + (61 - 58 * T + T * T + 600 * C - 330 * EP2) * A ** 6 / 720))
    return x + x0, y
def tm_inv(X, Y, lon0, k0=0.9999, x0=250000):
    x, y = X - x0, Y
    M = y / k0; mu = M / (A_ * (1 - E2 / 4 - 3 * E2 * E2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 * e1 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu) \
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    C1 = EP2 * math.cos(phi1) ** 2; T1 = math.tan(phi1) ** 2
    N1 = A_ / math.sqrt(1 - E2 * math.sin(phi1) ** 2); R1 = A_ * (1 - E2) / (1 - E2 * math.sin(phi1) ** 2) ** 1.5
    D = x / (N1 * k0)
    lat = phi1 - (N1 * math.tan(phi1) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * EP2) * D ** 4 / 24
                                              + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * EP2 - 3 * C1 * C1) * D ** 6 / 720)
    lon = (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * EP2 + 24 * T1 * T1) * D ** 5 / 120) / math.cos(phi1)
    return math.degrees(lat), lon0 + math.degrees(lon)

def to_main(x, y, county):
    if county in ISLANDS:
        lat, lon = tm_inv(x, y, 119)
        if not (23 < lat < 26.5 and 118 < lon < 120.6): return None
        x, y = tm_fwd(lat, lon, 121)
        return x, y
    if not (140000 < x < 360000 and 2400000 < y < 2820000): return None
    return x, y

# ---------- 桿號 ----------
TOK_TY = re.compile(r'(左-|右-|右低|左低|左分|右分|低|右|左|分|-)?(\d+)([A-Z]?)')
def parse_ty(s):
    """桃園的寫法(跟 build_lines.py 一模一樣)"""
    spur = False
    s = re.sub(r'R(?=\d)', '右', s); s = re.sub(r'L(?=\d)', '左', s)
    s = s.replace('=', '-').replace('附', '分').replace('支', '分') if not s.endswith('支桿') else s
    for tail in ['(支桿)', '支桿', '(現)']:
        if s.endswith(tail): s = s[:-len(tail)]; spur = True
    toks, pos = [], 0
    for m in TOK_TY.finditer(s):
        if m.start() != pos: return None, spur
        mk = (m.group(1) or '').replace('左-', '左').replace('右-', '右')
        toks.append((mk, int(m.group(2)), m.group(3))); pos = m.end()
    if pos != len(s) or not toks or toks[0][0] != '': return None, spur
    return toks, spur

TOK_ANY = re.compile(r'([^\d]*?)(\d+)([A-Za-z]?)(?=\D|$)')
def parse_any(s):
    """其他縣市:數字之間的任何文字都當成分歧記號(分、支、枝、左右、LR、XY、東西南北、歧、低…)"""
    spur = False
    s = s.replace('#', '').replace('=', '-')
    m = re.search(r'(\D+)$', s)
    if m and not re.fullmatch(r'[A-Za-z]', m.group(1)):
        s = s[:m.start()]; spur = True          # 尾巴的「支線桿」「號」之類
    s = re.sub(r'R(?=\d)', '右', s); s = re.sub(r'L(?=\d)', '左', s)
    toks, pos = [], 0
    for m in TOK_ANY.finditer(s):
        if m.start() != pos: return None, spur
        toks.append((m.group(1), int(m.group(2)), m.group(3).upper())); pos = m.end()
    if pos != len(s) or not toks or toks[0][0] != '': return None, spur
    return toks, spur

NAME_OK = re.compile(r'^[一-鿿]{1,10}$')
def split_no(no, county):
    """→ (線路名稱, '#'+桿號) 或 None"""
    no = no.strip().replace('＃', '#').replace(' ', '').replace('　', '')
    no = re.sub(r'\((?:[A-Z]{2}\d{2}|現)\)$', '', no)      # 基隆的 (FB61)
    if county == HOME:
        if '#' not in no: return None
        at = no.index('#'); line = no[:at].replace('(現)', '')
        if not (line.endswith('幹') or line.endswith('分線') or line.endswith('支線') or line in EXTRA) or len(line) < 2: return None
        return line, no[at:]
    m = re.match(r'^([^\d#]+)#?(\d.*)$', no)
    if not m: return None
    line, rest = m.group(1), m.group(2)
    if not NAME_OK.match(line): return None
    if len(line) < 2: return None
    return line, '#' + rest.replace('#', '') if rest else None

# ---------- read ----------
groups = collections.defaultdict(list)       # (county, line) -> rows
dist_count = collections.defaultdict(collections.Counter)
stat = collections.Counter()
for r in csv.DictReader(open(SRC, encoding='utf-8-sig')):
    county = r['縣市'].strip(); stat[county, 'all'] += 1
    sp = split_no(r['桿號'], county)
    if not sp: continue
    try: xy = to_main(float(r['TWD_97_X']), float(r['TWD_97_Y']), county)
    except ValueError: xy = None
    if not xy: stat[county, 'badxy'] += 1; continue
    line, num = sp
    groups[county, line].append({'no': num, 'x': xy[0], 'y': xy[1], 'code': r['圖號座標'].strip(), 'form': r['形式'].strip(), 'dist': county + ' ' + r['行政區'].strip()})
    dist_count[county, line][county + ' ' + r['行政區'].strip()] += 1

# 同名、不同縣市、靠得很近 → 同一條線(跨縣市的線)
def bbox(L): xs = [p['x'] for p in L]; ys = [p['y'] for p in L]; return min(xs), min(ys), max(xs), max(ys)
def gap(a, b): return max(0, a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3])
by_name = collections.defaultdict(list)
for k in groups: by_name[k[1]].append(k)
merged = {}     # final key -> (county, name, rows, dist counter)
for name, keys in by_name.items():
    keys.sort(key=lambda k: -len(groups[k]))
    clusters = []
    for k in keys:
        bb = bbox(groups[k])
        for c in clusters:
            if gap(c['bb'], bb) < 1500:
                c['keys'].append(k); c['bb'] = (min(c['bb'][0], bb[0]), min(c['bb'][1], bb[1]), max(c['bb'][2], bb[2]), max(c['bb'][3], bb[3])); break
        else: clusters.append({'keys': [k], 'bb': bb})
    for c in clusters:
        rows = [p for k in c['keys'] for p in groups[k]]
        dc = collections.Counter();
        for k in c['keys']: dc.update(dist_count[k])
        county = max(c['keys'], key=lambda k: (k[0] == HOME, len(groups[k])))[0] if any(k[0] == HOME for k in c['keys']) else c['keys'][0][0]
        c.update(county=county, rows=rows, dc=dc, home=any(k[0] == HOME for k in c['keys']))
    # 名字:只有一條 → 原名;好幾條 → 桃園的保留原名,其他加(縣市)
    multi = len(clusters) > 1
    used = set()
    for c in sorted(clusters, key=lambda c: (not c['home'], -len(c['rows']))):
        if not multi or (c['home'] and name not in used): nm = name
        else:
            nm = f"{name}({c['county'][:2]})"
            i = 2
            while nm in used: nm = f"{name}({c['county'][:2]}{i})"; i += 1
        used.add(nm)
        if not c['home'] and len(c['rows']) < 5: continue
        if c['home'] and len(c['rows']) < 3: continue
        merged[nm] = c

FORMS = collections.Counter(p['form'] for c in merged.values() for p in c['rows'])
FORM_LIST = [f for f, _ in FORMS.most_common()]
FORM_IDX = {f: i for i, f in enumerate(FORM_LIST)}

def link(L, parse):
    def key(toks): return '/'.join(f'{a}{b}{c}' for a, b, c in toks)
    def dist(a, b): return math.hypot(a['x'] - b['x'], a['y'] - b['y'])
    idx = collections.defaultdict(list)
    for r in L:
        r['toks'], r['spur'] = parse(r['no'][1:])
        r['k'] = (key(r['toks']) + ('|spur' if r['spur'] else '')) if r['toks'] else None
        if r['k']: idx[r['k']].append(r)
    for r in L:
        if r['toks'] and r['spur'] and key(r['toks']) not in idx:
            idx[key(r['toks'])].append(r); r['spur'] = False; r['k'] = key(r['toks'])
    # 桿號查不到前一支時,找「最近的」同名桿;用格子加速
    G = 300
    grid = collections.defaultdict(list)
    for r in L: grid[int(r['x'] // G), int(r['y'] // G)].append(r)
    def near(k, r):
        c = [o for o in idx.get(k, []) if o is not r]
        return min(c, key=lambda o: dist(o, r)) if c else None
    def find_parent(r):
        t = list(r['toks'])
        while t:
            mk, n, letter = t[-1]
            if letter:
                t[-1] = (mk, n, '')
                q = near(key(t), r)
                if q: return q
                continue
            for m in range(n - 1, max(0, n - 40), -1):
                q = near(key(t[:-1] + [(mk, m, '')]), r)
                if q: return q
            t = t[:-1]
            if t:
                q = near(key(t), r)
                if q: return q
        return None
    def nearest_any(r):
        gx, gy = int(r['x'] // G), int(r['y'] // G); best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid.get((gx + dx, gy + dy), []):
                    if o is not r and o['toks'] and (best is None or dist(o, r) < dist(best, r)): best = o
        return best
    for r in L:
        if r['toks'] is None: p = nearest_any(r)
        elif r['spur']: p = near(key(r['toks']), r)
        else: p = find_parent(r)
        r['parent'] = p if p is not None and p is not r and dist(p, r) < 500 else None
    order_key = lambda r: (0, [(t[1], t[0], t[2]) for t in r['toks']]) if r['toks'] else (1, r['no'])
    L.sort(key=order_key)
    pos = {id(r): i for i, r in enumerate(L)}
    out = []
    for r in L:
        kind = 'l' if r['toks'] and any('低' in t[0] for t in r['toks']) else ('b' if (r['toks'] and len(r['toks']) > 1) or r['spur'] else 't')
        out.append([r['no'], round(r['x'], 1), round(r['y'], 1), r['code'], pos[id(r['parent'])] if r['parent'] else -1, kind, FORM_IDX[r['form']]])
    return out

lines = []
for nm, c in merged.items():
    poles = link(c['rows'], parse_ty if c['home'] else parse_any)
    xs, ys = [p[1] for p in poles], [p[2] for p in poles]
    lines.append({'name': nm, 'county': c['county'], 'n': len(poles), 'dist': c['dc'].most_common(1)[0][0],
                  'bb': [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))], 'poles': poles})
print('線路', len(lines), '電桿', sum(l['n'] for l in lines))

# ---------- 顏色:桃園沿用原本的;其他用貪婪著色,150 m 內的線不同色 ----------
# 顏色種子:之前的全台 index、桃園原本的顏色(後面的優先)。每個月更新時,已經有的線維持原本的顏色
old = {}
for f in OLDS:
    j = json.load(open(f, encoding='utf-8'))
    old.update({r[0]: r[5] for r in j['lines']} if isinstance(j, dict) and 'lines' in j else j)
cell = 150
grid = collections.defaultdict(set)
for li, l in enumerate(lines):
    for q in l['poles']: grid[(int(q[1] // cell), int(q[2] // cell))].add(li)
adj = [set() for _ in lines]
for (gx, gy), here in grid.items():
    near = set()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1): near |= grid.get((gx + dx, gy + dy), set())
    for a in here: adj[a] |= near - {a}
color = [old.get(l['name'], -1) for l in lines]
use = collections.Counter(c for c in color if c >= 0)
for i in sorted((i for i in range(len(lines)) if color[i] < 0), key=lambda i: -len(adj[i])):
    taken = collections.Counter(color[j] for j in adj[i] if color[j] >= 0)
    free = [c for c in range(N_COLORS) if c not in taken]
    c = min(free, key=lambda c: use[c]) if free else min(range(N_COLORS), key=lambda c: taken[c])
    color[i] = c; use[c] += 1
clash = sum(1 for i in range(len(lines)) for j in adj[i] if j > i and color[i] == color[j])
print(f'同色相鄰 {clash} 對 / {sum(len(a) for a in adj)//2}')

# ---------- 分檔:依行政區,每檔約 600 KB ----------
by_dist = collections.defaultdict(list)
for l in lines: by_dist[l['dist']].append(l)
chunks = []
for d in sorted(by_dist):
    cur, size = [], 0
    for l in sorted(by_dist[d], key=lambda l: (l['bb'][0] + l['bb'][2])):
        s = len(json.dumps(l['poles'], ensure_ascii=False, separators=(',', ':')).encode())
        if cur and size + s > CHUNK_BYTES: chunks.append((d, cur)); cur, size = [], 0
        cur.append(l); size += s
    if cur: chunks.append((d, cur))

dists = sorted(by_dist)
index = {'source': '台電開放資料「台灣電力公司電桿坐標及桿號」', 'bbScale': 10, 'forms': FORM_LIST, 'files': [], 'dists': dists, 'lines': []}
for ci, (d, ls) in enumerate(chunks):
    fn = f'd/p{ci + 1:03d}.json'
    body = json.dumps({'lines': [{'name': l['name'], 'poles': l['poles']} for l in ls]}, ensure_ascii=False, separators=(',', ':'))
    (OUT / 'd').mkdir(exist_ok=True); (OUT / fn).write_text(body)
    index['files'].append(fn)
    for l in ls:
        index['lines'].append([l['name'], l['n'], dists.index(l['dist']), [b // 10 for b in l['bb']], ci, color[lines.index(l)] if False else None])
# colour lookup without O(n^2)
cmap = {l['name']: color[i] for i, l in enumerate(lines)}
for r in index['lines']: r[5] = cmap[r[0]]
index['lines'].sort(key=lambda r: r[0])
(OUT / 'lines-index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')))

total = sum(l['n'] for l in lines)
sizes = [(OUT / f).stat().st_size for f in index['files']]
print(f'{len(lines)} 條線、{total} 支桿;{len(chunks)} 個檔,最大 {max(sizes)/1024:.0f} KB,合計 {sum(sizes)/1024/1024:.1f} MB;index {(OUT / "lines-index.json").stat().st_size // 1024} KB')
cov = collections.Counter();
for l in lines: cov[l['county']] += l['n']
for k in sorted({k for k, _ in stat}): print(f'  {k}: {cov[k]}/{stat[k, "all"]} 支({100 * cov[k] / max(1, stat[k, "all"]):.0f}%)')
