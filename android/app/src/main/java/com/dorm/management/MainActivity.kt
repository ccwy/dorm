package com.dorm.management

import android.content.Intent
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.*
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
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

    override fun onDestroy() {
        // 停止 Flask 服务
        val intent = Intent(this, FlaskService::class.java)
        stopService(intent)
        webView.destroy()
        super.onDestroy()
    }
}