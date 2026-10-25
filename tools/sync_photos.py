"""把「線路巡視紀錄」的全組電桿照片同步到網站的 photos/ 資料夾(公開),定位地圖直接顯示。

輸入:ArtifactData 匯出(out_dir)的資料夾,裡面有
  shared/app/polephotos/<id>.json  {line, pole, photos:[照片id], at}
  shared/app/photos/<照片id>.json   {data: "data:image/jpeg;base64,...", at}
輸出:photos/<照片id>.jpg 與 photos/index.json {"民一幹#43": [{"f": "x.jpg", "at": 毫秒}, ...新到舊]}
紀錄網頁刪掉的照片,這裡也會刪掉。

usage: python3 tools/sync_photos.py <匯出資料夾> <網站 photos 資料夾>
"""
import base64, json, os, re, sys, pathlib
src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
pp_dir, ph_dir = src / 'shared' / 'app' / 'polephotos', src / 'shared' / 'app' / 'photos'
index, keep = {}, set()
for f in sorted(pp_dir.glob('*.json')) if pp_dir.exists() else []:
    d = json.loads(f.read_text(encoding='utf-8'))
    line, pole = str(d.get('line') or ''), str(d.get('pole') or '')
    if not line or not pole: continue
    for pid in d.get('photos') or []:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(pid)): continue
        name = pid + '.jpg'
        if not (out / name).exists():
            pf = ph_dir / (pid + '.json')
            if not pf.exists(): continue
            m = re.match(r'^data:image/(?:jpeg|jpg|png|webp);base64,(.+)$', json.loads(pf.read_text(encoding='utf-8')).get('data') or '', re.S)
            if not m: continue
            (out / name).write_bytes(base64.b64decode(m.group(1)))
        keep.add(name)
        index.setdefault(line + pole, []).append({'f': name, 'at': int(d.get('at') or 0)})
for k in index: index[k].sort(key=lambda x: -x['at'])
removed = [f.name for f in out.glob('*.jpg') if f.name not in keep]
for n in removed: (out / n).unlink()
(out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'{len(index)} 支桿、{len(keep)} 張照片;移除 {len(removed)} 張')
