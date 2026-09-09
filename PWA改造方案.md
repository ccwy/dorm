# 宿舍管理系统 PWA 改造方案

## 一、项目现状分析

### 1.1 技术栈
- **后端**：Python Flask（蓝图架构，30+ 蓝图模块）
- **前端**：Jinja2 模板 + Tailwind CSS + Font Awesome + jQuery
- **移动端**：已有 Android WebView 原生壳应用（`android/` 目录）

### 1.2 前端结构
- 模板文件分布在 `templates/` 下 20+ 子目录，共 103+ 个 HTML 文件
- 所有页面通过 `{% include 'static.html' %}` 引入公共 `<head>` 部分
- `templates/static.html` 是全局头部模板，包含 charset、viewport、favicon、CSS/JS 引用
- 当前仅有 `<meta name="viewport">` 适配标签，**无任何 PWA 相关配置**

### 1.3 现有静态资源
- `static/favicon.svg` — SVG 格式网站图标
- `static/favicon.ico` — ICO 格式网站图标
- `static/images/` — 图片资源目录
- `static/css/style.css` — 自定义样式
- `static/js/` — JavaScript 文件

---

## 二、PWA 改造目标

| 目标 | 说明 |
|------|------|
| iOS 主屏幕添加 | 用户可通过 Safari「添加到主屏幕」创建桌面快捷方式 |
| 独立窗口体验 | 从主屏幕启动后隐藏 Safari 浏览器 UI，呈现类原生 App 体验 |
| 离线基础支持 | Service Worker 缓存核心静态资源，离线时可显示缓存页面 |
| 启动画面 | iOS 自动生成启动画面（apple-touch-icon + 启动图配置） |
| 状态栏适配 | 配置 iOS 状态栏样式，避免与页面内容冲突 |

---

## 三、改造步骤

### 3.1 创建 Web App Manifest 文件

**文件路径**：`static/manifest.json`

```json
{
  "name": "宿舍管理系统",
  "short_name": "宿舍管理",
  "description": "宿舍管理、水电计费、维修工单、物资管理一体化系统",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#3b82f6",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/static/images/pwa/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/static/images/pwa/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

**说明**：
- `display: standalone` — 隐藏浏览器 UI，全屏展示
- `orientation: portrait-primary` — 锁定竖屏方向，适合管理类应用
- `theme_color` — 需与项目主色一致（当前项目使用 Tailwind `text-primary`，对应 `#3b82f6`）

### 3.2 修改全局头部模板

**文件路径**：`templates/static.html`

在现有内容之后追加以下内容：

```html
<!-- PWA 配置 -->
<link rel="manifest" href="{{ url_for('static', filename='manifest.json') }}">
<meta name="theme-color" content="#3b82f6">
<!-- iOS 专用 PWA 配置 -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="宿舍管理">
<link rel="apple-touch-icon" href="{{ url_for('static', filename='images/pwa/apple-touch-icon.png') }}">
<!-- iOS 启动画面配置 (iPhone 14 Pro Max 尺寸示例) -->
<link rel="apple-touch-startup-image" href="{{ url_for('static', filename='images/pwa/splash-1290x2796.png') }}" media="screen and (device-width: 430px) and (device-height: 932px) and (-webkit-device-pixel-ratio: 3)">
```

**各标签说明**：

| 标签 | 作用 |
|------|------|
| `manifest` | 关联 Web App Manifest 文件 |
| `theme-color` | 浏览器地址栏颜色（Android Chrome 生效） |
| `apple-mobile-web-app-capable` | 设为 yes 后，从主屏幕打开将隐藏 Safari UI |
| `apple-mobile-web-app-status-bar-style` | iOS 状态栏样式：`default`（白底黑字）/ `black-translucent`（透明）/ `black`（黑底白字） |
| `apple-mobile-web-app-title` | 主屏幕图标下方显示的应用名称 |
| `apple-touch-icon` | iOS 主屏幕图标（必须 180x180px） |
| `apple-touch-startup-image` | iOS 启动画面图片 |

### 3.3 创建 Service Worker

**文件路径**：`static/sw.js`

```javascript
const CACHE_NAME = 'dorm-mgmt-v1';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/css/font-awesome.min.css',
  '/static/js/3.4.17.js',
  '/static/js/jquery.min.js',
  '/static/favicon.svg',
  '/static/favicon.ico',
  '/static/manifest.json'
];

// 安装事件：预缓存核心静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// 激活事件：清理旧版本缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// 请求拦截：网络优先，失败后回退缓存
self.addEventListener('fetch', (event) => {
  // 仅处理 GET 请求
  if (event.request.method !== 'GET') return;

  // API 请求和页面请求走网络优先策略
  if (event.request.url.includes('/api/') || event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // 缓存成功的页面响应
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // 网络失败时返回缓存
          return caches.match(event.request).then((cachedResponse) => {
            return cachedResponse || caches.match('/');
          });
        })
    );
    return;
  }

  // 静态资源：缓存优先策略
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      return cachedResponse || fetch(event.request).then((response) => {
        if (response.ok) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      });
    })
  );
});
```

**缓存策略说明**：

| 资源类型 | 策略 | 原因 |
|----------|------|------|
| CSS/JS/字体/图标 | 缓存优先 | 不常变化，减少网络请求 |
| HTML 页面 | 网络优先 | 数据频繁更新，确保用户看到最新内容 |
| API 请求 | 网络优先 | 实时数据，不可缓存 |

### 3.4 注册 Service Worker

**文件路径**：在 `templates/static.html` 末尾追加

```html
<!-- Service Worker 注册 -->
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
      navigator.serviceWorker.register('/static/sw.js')
        .then(function(registration) {
          console.log('SW 注册成功:', registration.scope);
        })
        .catch(function(error) {
          console.log('SW 注册失败:', error);
        });
    });
  }
</script>
```

### 3.5 准备 PWA 图标资源

**所需图标清单**：

| 文件名 | 尺寸 | 用途 | 路径 |
|--------|------|------|------|
| `icon-192.png` | 192x192 | Android Chrome / PWA 标准 | `static/images/pwa/icon-192.png` |
| `icon-512.png` | 512x512 | Android Chrome / PWA 启动画面 | `static/images/pwa/icon-512.png` |
| `apple-touch-icon.png` | 180x180 | iOS 主屏幕图标 | `static/images/pwa/apple-touch-icon.png` |
| `splash-1290x2796.png` | 1290x2796 | iOS 启动画面（iPhone 14 Pro Max） | `static/images/pwa/splash-1290x2796.png` |

**图标生成方式**：
1. 使用项目现有 `static/favicon.svg` 作为源文件
2. 推荐工具：
   - [RealFaviconGenerator](https://realfavicongenerator.net/) — 一键生成所有尺寸
   - [PWA Asset Generator](https://github.com/nicedoc/pwa-asset-generator) — 命令行工具
   - [Maskable.app Editor](https://maskable.app/editor) — 制作 maskable 图标

**目录结构**：
```
static/
└── images/
    └── pwa/
        ├── icon-192.png
        ├── icon-512.png
        ├── apple-touch-icon.png
        └── splash-1290x2796.png
```

### 3.6 iOS 启动画面完整配置（可选增强）

iOS 为每种设备尺寸需要不同的启动图。以下为常见设备配置，添加到 `templates/static.html`：

```html
<!-- iPhone 14 Pro Max -->
<link rel="apple-touch-startup-image" href="{{ url_for('static', filename='images/pwa/splash-1290x2796.png') }}" media="screen and (device-width: 430px) and (device-height: 932px) and (-webkit-device-pixel-ratio: 3)">
<!-- iPhone 14 / 13 Pro -->
<link rel="apple-touch-startup-image" href="{{ url_for('static', filename='images/pwa/splash-1170x2532.png') }}" media="screen and (device-width: 390px) and (device-height: 844px) and (-webkit-device-pixel-ratio: 3)">
<!-- iPhone SE (3rd gen) -->
<link rel="apple-touch-startup-image" href="{{ url_for('static', filename='images/pwa/splash-750x1334.png') }}" media="screen and (device-width: 375px) and (device-height: 667px) and (-webkit-device-pixel-ratio: 2)">
<!-- iPad Pro 12.9" -->
<link rel="apple-touch-startup-image" href="{{ url_for('static', filename='images/pwa/splash-2048x2732.png') }}" media="screen and (device-width: 1024px) and (device-height: 1366px) and (-webkit-device-pixel-ratio: 2)">
```

> **建议**：初期可仅配置最常用的 2-3 个尺寸，后续根据用户设备数据补充。

---

## 四、HTTPS 部署要求

PWA 的 Service Worker **强制要求 HTTPS 环境**（localhost 开发除外）。

### 4.1 部署方案

| 场景 | 推荐方案 |
|------|----------|
| 内网部署 | 自签名证书（OpenSSL 生成）+ Nginx 反向代理 |
| 公网部署 | Let's Encrypt 免费证书 + Nginx/Caddy |
| Docker 部署 | 在 `dockerfile` 前增加 Nginx 层处理 TLS |
| Android WebView | 本地 Flask 服务，无需 HTTPS（Service Worker 不生效，但其他 PWA meta 标签仍有效） |

### 4.2 Nginx HTTPS 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # PWA 相关头部
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;";

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Service Worker 文件不允许缓存
    location = /static/sw.js {
        proxy_pass http://127.0.0.1:5000;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        expires 0;
    }
}
```

---

## 五、Flask 后端适配

### 5.1 添加 Manifest 路由（可选）

如果需要动态生成 manifest.json（如根据系统配置动态设置应用名称），可在 Flask 中添加路由：

```python
# blueprints/other/__init__.py 或新建 blueprints/pwa/__init__.py

from flask import Blueprint, jsonify, url_for

pwa_bp = Blueprint('pwa', __name__)

@pwa_bp.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "宿舍管理系统",
        "short_name": "宿舍管理",
        "start_url": url_for('index', _external=True),
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#3b82f6",
        "icons": [
            {
                "src": url_for('static', filename='images/pwa/icon-192.png'),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": url_for('static', filename='images/pwa/icon-512.png'),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }), 200, {'Content-Type': 'application/manifest+json'}
```

> **注意**：如果使用静态文件方式（推荐初期），则无需此步骤，直接将 `manifest.json` 放在 `static/` 目录即可。

### 5.2 Service Worker 缓存版本管理

每次更新前端资源后，需更新 `static/sw.js` 中的 `CACHE_NAME`：

```javascript
// 版本更新时修改此处
const CACHE_NAME = 'dorm-mgmt-v2';  // v1 → v2
```

这会触发 Service Worker 的 `activate` 事件，自动清理旧缓存。

---

## 六、iOS 专属注意事项

### 6.1 iOS Safari PWA 限制

| 功能 | iOS 支持情况 | 备注 |
|------|-------------|------|
| 添加到主屏幕 | ✅ iOS 11.3+ | 核心功能 |
| 隐藏浏览器 UI | ✅ | 需 `apple-mobile-web-app-capable` |
| 推送通知 | ✅ iOS 16.4+ | 需用户主动授权 |
| 离线缓存 | ⚠️ 部分支持 | 缓存空间有限（约 50MB） |
| 后台同步 | ❌ | iOS 不支持 Background Sync API |
| 定期后台同步 | ❌ | iOS 不支持 Periodic Background Sync |
| 支付请求 API | ❌ | iOS PWA 中不可用 |

### 6.2 iOS PWA 常见问题及解决方案

#### 问题1：从主屏幕打开后，链接跳转到 Safari 浏览器
**原因**：iOS PWA 中点击外部链接会跳出独立窗口
**解决**：确保所有链接为同源路径，避免 `target="_blank"`

#### 问题2：iOS PWA 中 Cookie/Session 丢失
**原因**：iOS PWA 的 Cookie 存储与 Safari 独立
**解决**：
- 确保 Flask Session Cookie 设置了正确的 `SameSite` 和 `Secure` 属性
- 在 `config.py` 中配置：
```python
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = True  # HTTPS 环境下
SESSION_COOKIE_HTTPONLY = True
```

#### 问题3：iOS 状态栏遮挡内容
**原因**：`apple-mobile-web-app-status-bar-style` 设为 `black-translucent` 时，内容延伸到状态栏下方
**解决**：
- 推荐使用 `default` 样式（白底黑字，内容不延伸）
- 如需透明效果，需在 CSS 中添加 `padding-top: env(safe-area-inset-top)`

#### 问题4：iOS PWA 不支持刷新
**原因**：独立模式下无地址栏，无法手动刷新
**解决**：在页面中添加下拉刷新或刷新按钮（可选）

---

## 七、测试验证

### 7.1 Chrome DevTools 审查

1. 打开 Chrome DevTools → Application 面板
2. 检查 **Manifest** 部分：确认图标、名称、颜色正确
3. 检查 **Service Workers** 部分：确认 SW 已注册并激活
4. 检查 **Cache Storage** 部分：确认预缓存资源已存储
5. 使用 **Lighthouse** 审查：生成 PWA 评分报告

### 7.2 iOS Safari 测试

1. 在 iOS Safari 中打开系统 URL
2. 点击「分享」按钮 → 「添加到主屏幕」
3. 确认图标和名称正确显示
4. 从主屏幕启动，确认：
   - 无 Safari 地址栏/工具栏
   - 状态栏样式正确
   - 导航和功能正常
   - 图标和启动画面正确

### 7.3 离线测试

1. 正常访问系统后，开启 iOS 飞行模式
2. 从主屏幕重新打开应用
3. 确认已缓存页面可正常显示
4. 确认离线提示友好（如有自定义离线页面）

---

## 八、改造文件清单

| 序号 | 操作 | 文件路径 | 说明 |
|------|------|----------|------|
| 1 | 新建 | `static/manifest.json` | Web App Manifest 配置 |
| 2 | 新建 | `static/sw.js` | Service Worker 文件 |
| 3 | 新建 | `static/images/pwa/icon-192.png` | 192x192 PWA 图标 |
| 4 | 新建 | `static/images/pwa/icon-512.png` | 512x512 PWA 图标 |
| 5 | 新建 | `static/images/pwa/apple-touch-icon.png` | 180x180 iOS 图标 |
| 6 | 新建 | `static/images/pwa/splash-*.png` | iOS 启动画面图片 |
| 7 | 修改 | `templates/static.html` | 添加 PWA meta 标签 + SW 注册代码 |

---

## 九、实施优先级

### 阶段一：基础 PWA 适配（1-2 天）
- [ ] 创建 `manifest.json`
- [ ] 修改 `static.html` 添加 PWA meta 标签
- [ ] 生成 PWA 图标资源（192、512、apple-touch-icon）
- [ ] 部署 HTTPS

### 阶段二：Service Worker 集成（1 天）
- [ ] 创建 `sw.js` 基础版本
- [ ] 在 `static.html` 注册 Service Worker
- [ ] 配置缓存策略
- [ ] 测试离线功能

### 阶段三：iOS 优化增强（1-2 天）
- [ ] 配置 iOS 启动画面
- [ ] 处理 iOS Cookie/Session 兼容性
- [ ] 添加 safe-area CSS 适配
- [ ] 完整 iOS 设备测试

---

## 十、与 Android 端的互补策略

| 平台 | 方案 | 优势 |
|------|------|------|
| Android | 原生 WebView 壳应用（已有） | 完整系统权限、后台服务、推送通知 |
| iOS | PWA（本方案） | 零审核成本、自动更新、无需上架 |

两平台共用同一套 Flask 后端和前端代码，仅入口方式不同：
- Android：通过 WebView 加载本地/远程 Flask 服务
- iOS：通过 Safari → 添加到主屏幕 → PWA 模式访问远程 Flask 服务