// sw.js - 最小 Service Worker，满足 PWA 安装条件
self.addEventListener('install', function() {
  self.skipWaiting();
});

self.addEventListener('activate', function() {
  self.clients.claim();
});

// 空的 fetch handler：满足 Chrome 安装条件，不拦截任何请求
self.addEventListener('fetch', function() {});