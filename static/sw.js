const CACHE="scios-live10";
const ASSETS=[
  "/",
  "/assets/live.css?v=live9",
  "/assets/ux-refinement.css?v=live10",
  "/assets/access.js?v=live10",
  "/assets/backup.js?v=live10",
  "/assets/ux-refinement.js?v=live10",
  "/assets/enhancements.js?v=live9",
  "/assets/live.js?v=live9",
  "/assets/ui.js",
  "/assets/workspace-detail.js",
  "/assets/icon.svg?v=live10",
  "/assets/manifest.webmanifest?v=live10"
];
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener("activate",event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=="GET"||url.pathname.startsWith("/api/")||url.pathname.startsWith("/ops/"))return;
  event.respondWith(fetch(event.request,{cache:"no-store"}).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response;}).catch(()=>caches.match(event.request)));
});
