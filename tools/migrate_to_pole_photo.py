"""一次性:把 line-map 的 photos/(照片+index.json)與 notes/index.json 搬到照片庫 Pole-photo 的新格式。

輸出:p/ 照片、t/ 縮圖(長邊 480)、i/<分片>.json 照片索引、n/<分片>.json 文字備註、.nojekyll
分片規則同 tools/sync_photos.py。key 是「線路名稱#桿號」,線路名稱取第一個 # 之前。

usage: python3 -I tools/migrate_to_pole_photos.py <line-map 資料夾> <Pole-photo 資料夾>
"""
import io, json, shutil, sys, pathlib


def shard_of(line):
    h = 0x811c9dc5
    for b in line.encode('utf-8'):
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    return format(h & 0xfff, '03x')


def thumb(data):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
    im.thumbnail((480, 480), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=60, optimize=True)
    return b.getvalue()


def merge(dst_dir, src_index):
    shards = {}
    for key, items in src_index.items():
        line = key.split('#', 1)[0]
        shards.setdefault(shard_of(line), {}).setdefault(key, []).extend(items)
    for sid, sh in shards.items():
        p = dst_dir / (sid + '.json')
        old = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        for k, v in sh.items():
            have = {x.get('f') or x.get('id') for x in old.get(k, [])}
            old[k] = sorted(old.get(k, []) + [x for x in v if (x.get('f') or x.get('id')) not in have], key=lambda x: -int(x.get('at') or 0))
        p.write_text(json.dumps(old, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return len(shards)


def main():
    lm, pp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    for d in ('p', 't', 'i', 'n'): (pp / d).mkdir(parents=True, exist_ok=True)
    (pp / '.nojekyll').write_text('', encoding='utf-8')
    idx = json.loads((lm / 'photos' / 'index.json').read_text(encoding='utf-8')) if (lm / 'photos' / 'index.json').exists() else {}
    n = 0
    for items in idx.values():
        for it in items:
            f = it['f']; src = lm / 'photos' / f
            if not src.exists(): sys.exit(f'找不到 {src}')
            shutil.copyfile(src, pp / 'p' / f)
            (pp / 't' / f).write_bytes(thumb(src.read_bytes())); n += 1
    s1 = merge(pp / 'i', idx)
    notes = json.loads((lm / 'notes' / 'index.json').read_text(encoding='utf-8')) if (lm / 'notes' / 'index.json').exists() else {}
    s2 = merge(pp / 'n', notes) if notes else 0
    print(f'照片 {n} 張({len(idx)} 支桿,{s1} 個分片);文字備註 {sum(len(v) for v in notes.values())} 則({s2} 個分片)')


if __name__ == '__main__':
    main()
