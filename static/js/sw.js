// sw.js - 最小 Service Worker，仅满足 PWA 安装条件，不做离线缓存
self.addEventListener('install', function() {
  // 立即激活，不等待旧 SW 关闭
  self.skipWaiting();
});

self.addEventListener('activate', function() {
  // 立即接管所有页面
  self.clients.claim();
});

// 所有请求直接透传网络，不拦截不缓存