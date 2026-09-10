// PWA Service Worker - 仅用于推送通知，不使用离线缓存
const CACHE_NAME = 'dorm-pwa-v1';

// 从URL参数读取系统标题
const swTitle = new URL(self.location.href).searchParams.get('title') || '宿舍管理系统';

// 安装事件 - 立即激活
self.addEventListener('install', (event) => {
    console.log('[SW] Service Worker 安装中...');
    self.skipWaiting();
});

// 激活事件 - 立即接管所有客户端
self.addEventListener('activate', (event) => {
    console.log('[SW] Service Worker 已激活');
    event.waitUntil(self.clients.claim());
});

// 推送通知处理
self.addEventListener('push', (event) => {
    console.log('[SW] 收到推送通知');
    let data = {
        title: swTitle,
        body: '您有新的通知',
        icon: '/static/images/pwa/icon-192x192.png',
        url: '/'
    };
    
    if (event.data) {
        try {
            data = { ...data, ...event.data.json() };
        } catch (e) {
            data.body = event.data.text();
        }
    }
    
    const options = {
        body: data.body,
        icon: data.icon,
        badge: '/static/images/pwa/icon-72x72.png',
        data: {
            url: data.url || '/'
        },
        vibrate: [100, 50, 100],
        actions: [
            { action: 'open', title: '查看详情' },
            { action: 'close', title: '关闭' }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// 通知点击处理
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] 通知被点击', event.action);
    event.notification.close();
    
    if (event.action === 'close') {
        return;
    }
    
    const urlToOpen = event.notification.data?.url || '/';
    
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // 如果已有打开的窗口，聚焦到该窗口
            for (const client of clientList) {
                if (client.url.includes(self.location.origin) && 'focus' in client) {
                    client.navigate(urlToOpen);
                    return client.focus();
                }
            }
            // 否则打开新窗口
            return self.clients.openWindow(urlToOpen);
        })
    );
});

// 推送订阅变更处理
self.addEventListener('pushsubscriptionchange', (event) => {
    console.log('[SW] 推送订阅已变更，需要重新订阅');
    // 通知应用重新订阅
    event.waitUntil(
        self.clients.matchAll({ type: 'window' }).then((clientList) => {
            for (const client of clientList) {
                client.postMessage({
                    type: 'PUSH_SUBSCRIPTION_CHANGED'
                });
            }
        })
    );
});