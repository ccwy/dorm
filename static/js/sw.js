// sw.js - 最小 Service Worker，满足 PWA 安装条件
self.addEventListener('install', function() {
  // 立即激活，不等待旧 SW 关闭
  self.skipWaiting();
});

self.addEventListener('activate', function() {
  // 立即接管所有页面
  self.clients.claim();
});

// fetch：满足 Chrome 安装条件（必须有 fetch handler），离线时返回友好提示
self.addEventListener('fetch', function(event) {
  event.respondWith(
    fetch(event.request).catch(function() {
      // 仅对导航请求（页面）返回离线提示，其他请求正常失败
      if (event.request.mode === 'navigate') {
        return new Response(
          '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">' +
          '<meta name="viewport" content="width=device-width,initial-scale=1">' +
          '<title>离线提示</title><style>' +
          'body{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f5f5f5;color:#333}' +
          '.card{text-align:center;padding:2rem;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.1);max-width:90%}' +
          'h2{margin:0 0 .5rem;color:#555}p{margin:0;color:#888}' +
          '</style></head><body><div class="card">' +
          '<h2>📶 网络不可用</h2>' +
          '<p>请检查网络连接后重试</p>' +
          '</div></body></html>',
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      }
      return new Response('', { status: 503, statusText: 'Service Unavailable' });
    })
  );
});