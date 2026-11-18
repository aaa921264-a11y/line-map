"""把「線路巡視紀錄」的全組電桿照片同步到照片庫 repo「Pole-photo」(GitHub Pages 公開),定位地圖直接顯示。

輸入:ArtifactData 匯出(out_dir)的資料夾,裡面有
  shared/app/polephotos/<id>.json  {line, pole, photos:[照片id], at}
  shared/app/photos/<照片id>.json   {data: "data:image/jpeg;base64,...", at}
輸出(Pole-photo 資料夾):
  p/<照片id>.jpg   照片
  t/<照片id>.jpg   縮圖(長邊 480);沒有 Pillow 時不做縮圖,索引標 "nt":1,網頁改用原圖
  i/<分片>.json    照片索引 {"民一幹#43": [{"f": "x.jpg", "at": 毫秒, "t": [標籤]}, ...新到舊]}
分片 = 線路名稱(UTF-8)的 FNV-1a 32 位元雜湊 & 0xfff,三位小寫十六進位(和網頁的 shardOf 相同)。
紀錄網頁刪掉的照片,這裡也會刪掉。
例外:檔名以 u_ 開頭的是直接在定位地圖上傳的照片,永遠保留;索引有 r 欄位(放在別的照片庫)的也不動。

usage: python3 -I tools/sync_photos.py <匯出資料夾> <Pole-photo 資料夾>
"""
import base64, io, json, re, sys, pathlib

USER_PREFIX = 'u_'
THUMB_EDGE, THUMB_Q = 480, 60


def shard_of(line):
    h = 0x811c9dc5
    for b in line.encode('utf-8'):
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
    return format(h & 0xfff, '03x')


def make_thumb(data):
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
        im.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
        b = io.BytesIO(); im.save(b, 'JPEG', quality=THUMB_Q, optimize=True)
        return b.getvalue()
    except Exception:
        return None


def main():
    src, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    pdir, tdir, idir = root / 'p', root / 't', root / 'i'
    for d in (pdir, tdir, idir): d.mkdir(parents=True, exist_ok=True)
    pp_dir, ph_dir = src / 'shared' / 'app' / 'polephotos', src / 'shared' / 'app' / 'photos'

    # 1) 讀現有分片
    shards = {}
    for f in idir.glob('*.json'):
        try: shards[f.stem] = json.loads(f.read_text(encoding='utf-8')) or {}
        except Exception: sys.exit(f'索引 {f} 讀不到,停止(避免蓋掉資料)')
    before = json.dumps(shards, sort_keys=True, ensure_ascii=False)

    # 2) 拿掉紀錄網頁同步來的舊項目(u_ 與別的照片庫的不動)
    old_synced = set()
    for sh in shards.values():
        for k in list(sh):
            keep = []
            for it in sh[k] if isinstance(sh[k], list) else []:
                n = str(it.get('f') or '')
                if n.startswith(USER_PREFIX) or it.get('r'): keep.append(it)
                else: old_synced.add(n)
            if keep: sh[k] = keep
            else: del sh[k]

    # 3) 加入這次匯出的照片
    new_synced, added, no_thumb = set(), 0, 0
    for f in sorted(pp_dir.glob('*.json')) if pp_dir.exists() else []:
        d = json.loads(f.read_text(encoding='utf-8'))
        line, pole = str(d.get('line') or ''), str(d.get('pole') or '')
        if not line or not pole: continue
        for pid in d.get('photos') or []:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(pid)) or str(pid).startswith(USER_PREFIX): continue
            name = pid + '.jpg'
            if not (pdir / name).exists():
                pf = ph_dir / (pid + '.json')
                if not pf.exists(): continue
                m = re.match(r'^data:image/(?:jpeg|jpg|png|webp);base64,(.+)$', json.loads(pf.read_text(encoding='utf-8')).get('data') or '', re.S)
                if not m: continue
                (pdir / name).write_bytes(base64.b64decode(m.group(1))); added += 1
            entry = {'f': name, 'at': int(d.get('at') or 0)}
            if not (tdir / name).exists():
                th = make_thumb((pdir / name).read_bytes())
                if th: (tdir / name).write_bytes(th)
            if not (tdir / name).exists(): entry['nt'] = 1; no_thumb += 1
            new_synced.add(name)
            shards.setdefault(shard_of(line), {}).setdefault(line + pole, []).append(entry)

    # 4) 刪掉紀錄網頁已刪的照片檔
    removed = sorted(old_synced - new_synced)
    for n in removed:
        for d in (pdir, tdir):
            if (d / n).exists(): (d / n).unlink()

    # 5) 寫回有變的分片
    for sid, sh in shards.items():
        for k in sh: sh[k].sort(key=lambda x: -int(x.get('at') or 0))
    if json.dumps(shards, sort_keys=True, ensure_ascii=False) != before:
        for sid, sh in shards.items():
            p = idir / (sid + '.json')
            txt = json.dumps(sh, ensure_ascii=False, separators=(',', ':'))
            if not p.exists() or p.read_text(encoding='utf-8') != txt: p.write_text(txt, encoding='utf-8')
    poles = sum(len(sh) for sh in shards.values())
    photos = sum(len(v) for sh in shards.values() for v in sh.values())
    user = sum(1 for sh in shards.values() for v in sh.values() for it in v if str(it.get('f', '')).startswith(USER_PREFIX))
    print(f'{poles} 支桿、{photos} 張照片(含直接上傳 {user} 張);紀錄網頁同步 {len(new_synced)} 張,新增 {added} 張,移除 {len(removed)} 張'
          + (f';{no_thumb} 張沒有縮圖(缺 Pillow)' if no_thumb else ''))


if __name__ == '__main__':
    main()
