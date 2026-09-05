package com.dorm.management

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Environment
import android.view.View
import android.view.WindowManager
import android.webkit.*
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.chaquo.python.Python
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    companion object {
        private const val FLASK_PORT = 35168
        private const val FLASK_HOST = "127.0.0.1"
        private const val FLASK_BASE_URL = "http://$FLASK_HOST:$FLASK_PORT"
        private const val MAX_SERVER_WAIT_SECONDS = 30
    }

    private lateinit var webView: WebView
    private lateinit var errorView: TextView
    private lateinit var loadingOverlay: LinearLayout
    private lateinit var loadingProgressBar: ProgressBar
    private lateinit var loadingStatus: TextView
    private lateinit var loadingPercent: TextView
    private lateinit var webProgress: ProgressBar
    private var python: Python? = null
    private var isServerReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        val splashScreen = installSplashScreen()
        super.onCreate(savedInstanceState)

        // 保持屏幕常亮
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        setContentView(R.layout.activity_main)

        // 初始化视图
        webView = findViewById(R.id.webview)
        errorView = findViewById(R.id.errorView)
        loadingOverlay = findViewById(R.id.loadingOverlay)
        loadingProgressBar = findViewById(R.id.loadingProgressBar)
        loadingStatus = findViewById(R.id.loadingStatus)
        loadingPercent = findViewById(R.id.loadingPercent)
        webProgress = findViewById(R.id.webProgress)

        // Python 已在 DormApplication.onCreate() 中初始化
        python = Python.getInstance()

        // 更新加载状态
        updateLoadingProgress(10, "正在启动服务...")

        // 启动 Flask 后台服务
        startFlaskServer()

        // 配置 WebView
        configureWebView()

        // 等待服务器就绪并加载页面
        waitForServerAndLoad()

        // 保持启动屏直到服务器就绪
        splashScreen.setKeepOnScreenCondition { !isServerReady }
    }

    private fun updateLoadingProgress(progress: Int, status: String) {
        runOnUiThread {
            loadingProgressBar.progress = progress
            loadingPercent.text = "$progress%"
            loadingStatus.text = status
        }
    }

    private fun startFlaskServer() {
        val intent = Intent(this, FlaskService::class.java)
        startForegroundService(intent)
    }

    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = true
            allowContentAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " DormManagement/Android"
        }

        // WebViewClient — 仅允许加载本地 Flask 服务
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?, request: WebResourceRequest?
            ): Boolean {
                val url = request?.url?.toString() ?: return false
                if (url.startsWith(FLASK_BASE_URL) ||
                    url.startsWith("http://localhost:$FLASK_PORT")) {
                    return false
                }
                // 外部链接用系统浏览器打开
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                startActivity(intent)
                return true
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                // 页面加载完成，隐藏加载覆盖层
                hideLoadingOverlay()
            }

            override fun onReceivedError(
                view: WebView?, request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    showErrorPage("服务连接失败，请稍后重试")
                }
            }

            override fun onReceivedSslError(
                view: WebView?, handler: SslErrorHandler?, error: SslError?
            ) {
                // 本地 HTTP 不应有 SSL 错误，忽略
                handler?.cancel()
            }
        }

        // WebChromeClient — 文件选择和加载进度
        webView.webChromeClient = DormWebChromeClient(this)

        // 注册 JS Bridge
        webView.addJavascriptInterface(JsBridgeInterface(this), "AndroidBridge")

        // 文件下载处理 — 将下载文件保存到公共 Downloads 目录
        webView.setDownloadListener { url, userAgent, contentDisposition, mimetype, contentLength ->
            handleDownload(url, contentDisposition, mimetype)
        }
    }

    /**
     * 处理 WebView 中的文件下载请求
     * 使用系统 DownloadManager 将文件保存到公共 Downloads 目录
     */
    private fun handleDownload(url: String, contentDisposition: String, mimetype: String) {
        try {
            val request = DownloadManager.Request(Uri.parse(url))

            // 设置请求头（本地Flask服务需要）
            request.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url))

            // 从 Content-Disposition 解析文件名
            val filename = parseContentDisposition(contentDisposition)
                ?: Uri.parse(url)?.lastPathSegment
                ?: "download_${System.currentTimeMillis()}"

            // 设置文件名和 MIME 类型
            request.setTitle(filename)
            request.setDescription("宿舍管理系统下载")
            request.setMimeType(mimetype.ifEmpty { "*/*" })

            // 保存到公共 Downloads 目录（所有Android版本可用，无需权限）
            // Android 10+ 通过 MediaStore 插入，旧版本直接写入
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)

            // 允许在通知栏显示下载进度
            request.setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
            )

            // 使用系统 DownloadManager 执行下载
            val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            dm.enqueue(request)

            runOnUiThread {
                Toast.makeText(this, "正在下载: $filename", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            runOnUiThread {
                Toast.makeText(this, "下载失败: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    /**
     * 解析 Content-Disposition 头获取文件名
     * 格式: attachment; filename="文件名.sql" 或 filename*=UTF-8''文件名
     */
    private fun parseContentDisposition(contentDisposition: String): String? {
        if (contentDisposition.isBlank()) return null

        // 尝试匹配 filename*=UTF-8''编码文件名
        val utf8Pattern = Regex("""filename\*\s*=\s*UTF-8''(.+?)(?:;|$)""")
        utf8Pattern.find(contentDisposition)?.let { match ->
            return java.net.URLDecoder.decode(match.groupValues[1].trim(), "UTF-8")
        }

        // 尝试匹配 filename="文件名"
        val quotedPattern = Regex("""filename\s*=\s*"(.+?)"(?:;|$)""")
        quotedPattern.find(contentDisposition)?.let { match ->
            return match.groupValues[1]
        }

        // 尝试匹配 filename=文件名（无引号）
        val plainPattern = Regex("""filename\s*=\s*([^;]+)""")
        plainPattern.find(contentDisposition)?.let { match ->
            return match.groupValues[1].trim()
        }

        return null
    }

    private fun waitForServerAndLoad() {
        Thread {
            var retries = 0
            val maxRetries = MAX_SERVER_WAIT_SECONDS * 2  // 500ms 间隔

            // 阶段1: 启动服务 (10% → 40%)
            updateLoadingProgress(15, "正在启动后端服务...")

            while (retries < maxRetries) {
                try {
                    val url = URL("$FLASK_BASE_URL/login")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.requestMethod = "GET"
                    conn.connectTimeout = 2000
                    conn.readTimeout = 2000
                    val responseCode = conn.responseCode
                    conn.disconnect()
                    if (responseCode == 200) {
                        isServerReady = true
                        // 阶段2: 服务就绪，开始加载页面 (40% → 60%)
                        updateLoadingProgress(40, "服务已就绪，正在加载页面...")
                        runOnUiThread {
                            webView.loadUrl("$FLASK_BASE_URL/login")
                        }
                        return@Thread
                    }
                } catch (e: Exception) {
                    // 服务器尚未就绪，继续等待
                }

                // 渐进更新进度 (15% → 38%)
                val estimatedProgress = 15 + (retries * 23 / maxRetries)
                if (retries % 4 == 0) {
                    updateLoadingProgress(estimatedProgress, "正在启动后端服务...")
                }
                retries++
                Thread.sleep(500)
            }
            runOnUiThread { showErrorPage("服务器启动超时，请重启应用") }
        }.start()
    }

    /**
     * 由 DormWebChromeClient 调用，更新 WebView 页面加载进度
     * 进度范围: 40% → 100% (服务就绪后)
     */
    fun updateWebProgress(newProgress: Int) {
        runOnUiThread {
            // 映射 WebView 进度 (0-100) 到总进度 (40-100)
            val totalProgress = 40 + (newProgress * 60 / 100)
            loadingProgressBar.progress = totalProgress
            loadingPercent.text = "$totalProgress%"

            // WebView 顶部进度条
            webProgress.progress = newProgress
            if (newProgress > 0 && newProgress < 100) {
                webProgress.visibility = View.VISIBLE
            }

            // 更新状态文字
            when {
                newProgress < 30 -> loadingStatus.text = "正在加载页面资源..."
                newProgress < 70 -> loadingStatus.text = "正在渲染页面..."
                newProgress < 100 -> loadingStatus.text = "即将完成..."
            }

            if (newProgress == 100) {
                webProgress.visibility = View.GONE
            }
        }
    }

    private fun hideLoadingOverlay() {
        runOnUiThread {
            loadingOverlay.animate()
                .alpha(0f)
                .setDuration(300)
                .withEndAction {
                    loadingOverlay.visibility = View.GONE
                }
                .start()
        }
    }

    private fun showErrorPage(message: String) {
        runOnUiThread {
            webView.loadUrl("about:blank")
            loadingOverlay.visibility = View.GONE
            errorView.text = message
            errorView.visibility = View.VISIBLE
        }
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    @Deprecated("Deprecated in API 30+, but required for file chooser compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        // 处理文件选择结果
        if (requestCode == DormWebChromeClient.REQUEST_FILE_CHOOSER) {
            (webView.webChromeClient as? DormWebChromeClient)?.handleFileChooserResult(resultCode, data)
        }
    }

    override fun onDestroy() {
        // 停止 Flask 服务
        val intent = Intent(this, FlaskService::class.java)
        stopService(intent)
        webView.destroy()
        super.onDestroy()
    }
}