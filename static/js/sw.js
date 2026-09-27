// sw.js - 最小 Service Worker，满足 PWA 安装条件
self.addEventListener('install', function() {
  // 立即激活，不等待旧 SW 关闭
  self.skipWaiting();
});

self.addEventListener('activate', function() {
  // 立即接管所有页面
  self.clients.claim();
});

// fetch 透传：满足 Chrome 安装条件（必须有 fetch handler），不缓存不拦截
self.addEventListener('fetch', function(event) {
  event.respondWith(fetch(event.request));
});