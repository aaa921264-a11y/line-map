// 封閉測試版的離線快取:網頁先用網路、沒網路用存的;電桿、街道、照片、底圖用存的(先存先用)
const CACHE = 'lmb-v1';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if(e.request.method !== 'GET') return;
  if(u.pathname.endsWith('/version.json') || u.hostname.endsWith('jsdelivr.net')) return;           // 版本檢查一律走網路
  if(e.request.mode === 'navigate'){
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(CACHE).then(k => k.put(e.request, c)); return r; })
      .catch(() => caches.match(e.request, { ignoreSearch: false }).then(r => r || caches.match(e.request, { ignoreSearch: true }))));
    return;
  }
  const data = /\/(d|roads|photos)\//.test(u.pathname) || u.hostname === 'wmts.nlsc.gov.tw';
  if(!data) return;
  const key = u.origin + u.pathname;   // 不管 ?t= 之類的參數
  const fresh = /index\.json$/.test(u.pathname);   // 索引檔:有網路就更新
  e.respondWith(caches.open(CACHE).then(async k => {
    const hit = await k.match(key);
    const net = fetch(e.request).then(r => { if(r.ok || r.type === 'opaque') k.put(key, r.clone()); return r; });
    if(hit && !fresh){ net.catch(() => {}); return hit; }
    return net.catch(() => hit || Response.error());
  }));
});
