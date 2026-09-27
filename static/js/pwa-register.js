// pwa-register.js - PWA Service Worker 注册
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    // 使用相对路径注册，通配任意域名
    navigator.serviceWorker.register('./sw.js', { scope: './' })
      .then(function(reg) {
        console.log('PWA Service Worker 注册成功, scope:', reg.scope);
      })
      .catch(function(err) {
        console.log('PWA Service Worker 注册失败:', err);
      });
  });
}