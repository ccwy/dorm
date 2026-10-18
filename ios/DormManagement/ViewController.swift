//
//  ViewController.swift
//  DormManagement
//
//  核心控制器，对齐 Android MainActivity.kt：
//  启动 Python Flask → 轮询进度 → WKWebView 加载 127.0.0.1:35168
//

import UIKit
import WebKit

class ViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {

    // MARK: - 常量（与 Android MainActivity 保持一致）

    private let flaskHost = "127.0.0.1"
    private let flaskPort = 35168
    private var flaskBaseURL: String { "http://\(flaskHost):\(flaskPort)" }
    private let maxServerWaitSeconds = 300
    private let pollInterval: TimeInterval = 0.5

    // MARK: - UI

    private var webView: WKWebView!
    private var loadingView: LoadingView!
    private var errorView: ErrorView!
    private var webProgress: UIProgressView! // 顶部细进度条

    // MARK: - 状态

    private var isServerReady = false
    private var systemTitle: String?
    private var progressTimer: Timer?
    private var launchStartTime: Date?
    private var lastPythonPct = 0
    private var lastPythonMsg = ""
    private var progressKvoToken: NSKeyValueObservation?
    private var didLoadWebView = false

    // MARK: - 生命周期

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .white
        setupUI()
        initializePython()
        startFlaskServer()
        startPolling()
    }

    deinit {
        progressTimer?.invalidate()
        progressKvoToken?.invalidate()
    }

    // MARK: - UI 构建（纯代码 Auto Layout）

    private func setupUI() {
        // WKWebView
        let config = WKWebViewConfiguration()
        config.preferences.javaScriptEnabled = true
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.translatesAutoresizingMaskIntoConstraints = false
        // 自定义 UA 标识（对齐 Android）
        webView.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 DormManagement/iOS"
        view.addSubview(webView)

        // 顶部细进度条（对应 Android webProgress）
        webProgress = UIProgressView(progressViewStyle: .bar)
        webProgress.progressTintColor = UIColor(red: 0.086, green: 0.365, blue: 1.0, alpha: 1.0)
        webProgress.trackTintColor = .clear
        webProgress.isHidden = true
        webProgress.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webProgress)

        // 加载遮罩（对应 Android loadingOverlay）
        loadingView = LoadingView()
        loadingView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(loadingView)

        // 错误页面（对应 Android errorView）
        errorView = ErrorView()
        errorView.translatesAutoresizingMaskIntoConstraints = false
        errorView.isHidden = true
        errorView.onRetry = { [weak self] in self?.retryLoadPage() }
        view.addSubview(errorView)

        // 约束
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            webProgress.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            webProgress.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webProgress.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webProgress.heightAnchor.constraint(equalToConstant: 3),

            loadingView.topAnchor.constraint(equalTo: view.topAnchor),
            loadingView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            loadingView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            loadingView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            errorView.topAnchor.constraint(equalTo: view.topAnchor),
            errorView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            errorView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            errorView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])

        loadingView.show()
        loadingView.updateProgress(pct: 5, msg: "正在初始化...")
    }

    // MARK: - Python 初始化与 Flask 启动

    private func initializePython() {
        let documentsPath = NSSearchPathForDirectoriesInDomains(.documentDirectory, .userDomainMask, true).first ?? ""
        PythonBridge.shared.initialize(documentsPath: documentsPath)
    }

    private func startFlaskServer() {
        launchStartTime = Date()
        // 后台线程启动 Flask（startServer 为阻塞调用）
        DispatchQueue.global(qos: .userInitiated).async {
            PythonBridge.shared.startServer()
        }
    }

    // MARK: - 进度轮询（对齐 Android waitForServerAndLoad）

    private func startPolling() {
        progressTimer?.invalidate()
        progressTimer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) { [weak self] _ in
            self?.pollOnce()
        }
    }

    private func pollOnce() {
        // 1. 读取 Python 启动进度
        let (pct, msg) = PythonBridge.shared.getProgress()
        if pct != lastPythonPct || msg != lastPythonMsg {
            lastPythonPct = pct
            lastPythonMsg = msg
            loadingView.updateProgress(pct: pct, msg: msg)
        }

        // 2. 首次获取进度后读取系统标题
        if systemTitle == nil && pct > 0 {
            let title = PythonBridge.shared.getSystemTitle()
            systemTitle = title
            loadingView.titleLabel.text = title
        }

        // 3. 检查超时
        if let start = launchStartTime, Date().timeIntervalSince(start) > TimeInterval(maxServerWaitSeconds) {
            progressTimer?.invalidate()
            showErrorPage("服务器启动超时，如果是首次连接MySQL创建数据库，耗时可能较长，请点击重试或重启应用再试")
            return
        }

        // 4. HTTP 探测服务器是否就绪（后台线程）
        guard !isServerReady else { return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            guard let url = URL(string: "\(self.flaskBaseURL)/login") else { return }
            var request = URLRequest(url: url)
            request.timeoutInterval = 2.0
            let task = URLSession.shared.dataTask(with: request) { data, response, _ in
                if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                    DispatchQueue.main.async {
                        self.onServerReady()
                    }
                }
            }
            task.resume()
        }
    }

    private func onServerReady() {
        guard !isServerReady else { return }
        isServerReady = true
        progressTimer?.invalidate()
        // 进度不低于 Python 当前进度，避免倒退
        let readyPct = max(lastPythonPct + 5, 95)
        loadingView.updateProgress(pct: readyPct, msg: "服务已就绪，正在加载页面...")
        loadWebView()
    }

    // MARK: - WebView 配置与加载

    private func loadWebView() {
        guard !didLoadWebView else { return }
        didLoadWebView = true
        // KVO 监听页面加载进度（顶部细进度条）
        progressKvoToken = webView.observe(\.estimatedProgress, options: .new) { [weak self] _, change in
            guard let self = self, let progress = change.newValue else { return }
            self.webProgress.progress = Float(progress)
            self.webProgress.isHidden = progress >= 1.0 || progress <= 0.0
            // 映射 WebView 进度到总进度（95→100）
            let total = 95 + Int(progress * 5)
            self.loadingView.updateProgress(pct: total, msg: "正在加载页面...")
        }
        guard let url = URL(string: "\(flaskBaseURL)/login") else { return }
        webView.load(URLRequest(url: url))
    }

    // MARK: - 错误处理与重试

    private func showErrorPage(_ message: String) {
        webView.loadHTMLString("", baseURL: nil)
        loadingView.isHidden = true
        errorView.show(message: message)
    }

    private func retryLoadPage() {
        errorView.hide()
        loadingView.isHidden = false
        loadingView.show()
        loadingView.updateProgress(pct: 5, msg: "正在重新连接服务...")
        isServerReady = false
        didLoadWebView = false
        progressKvoToken?.invalidate()
        lastPythonPct = 0
        lastPythonMsg = ""
        launchStartTime = Date()
        startPolling()
    }

    // MARK: - WKNavigationDelegate

    // 仅允许加载本地 Flask 服务，外部链接用系统浏览器打开
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }
        if isLocalFlaskURL(url) {
            decisionHandler(.allow)
        } else if url.scheme == "http" || url.scheme == "https" {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }

    /// 判断 URL 是否指向本地 Flask 服务（比较 host + port，避免前缀字符串绕过）
    private func isLocalFlaskURL(_ url: URL) -> Bool {
        guard let host = url.host else { return false }
        let port = url.port ?? 80
        return (host == flaskHost || host == "localhost") && port == flaskPort
    }

    // 检测下载响应：Content-Disposition 含 attachment 时取消导航，改用 URLSession 下载
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let httpResponse = navigationResponse.response as? HTTPURLResponse {
            let disposition = httpResponse.value(forHTTPHeaderField: "Content-Disposition") ?? ""
            if disposition.lowercased().contains("attachment") {
                decisionHandler(.cancel)
                handleDownload(response: httpResponse, disposition: disposition)
                return
            }
        }
        decisionHandler(.allow)
    }

    // 页面加载完成，隐藏加载遮罩
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loadingView.hide()
    }

    // 页面加载失败
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if !isServerReady {
            showErrorPage("服务连接失败，请稍后重试")
        } else {
            // 服务已就绪后的导航失败也提示，避免白屏无反馈
            loadingView.hide()
            showErrorPage("页面加载失败：\(error.localizedDescription)")
        }
    }

    // MARK: - 文件下载（对齐 Android handleDownload）

    private func handleDownload(response: HTTPURLResponse, disposition: String) {
        guard let url = response.url else { return }
        let filename = parseContentDisposition(disposition)
            ?? response.suggestedFilename
            ?? "download_\(Int(Date().timeIntervalSince1970))"

        showToast("正在下载: \(filename)")

        DispatchQueue.global(qos: .utility).async { [weak self] in
            var request = URLRequest(url: url)
            request.timeoutInterval = 60.0
            // 传递 Cookie 以通过登录验证
            let cookies = HTTPCookieStorage.shared.cookies(for: url) ?? []
            if !cookies.isEmpty {
                request.allHTTPHeaderFields = HTTPCookie.requestHeaderFields(with: cookies)
            }
            let task = URLSession.shared.downloadTask(with: request) { tempUrl, _, error in
                guard let self = self else { return }
                guard let tempUrl = tempUrl, error == nil else {
                    DispatchQueue.main.async { self.showToast("下载失败: \(error?.localizedDescription ?? "未知错误")") }
                    return
                }
                let saved = self.saveDownloadedFile(tempUrl: tempUrl, filename: filename)
                DispatchQueue.main.async {
                    if saved {
                        self.showToast("下载完成: \(filename)\n已保存到 Documents/Download/")
                    } else {
                        self.showToast("下载文件保存失败")
                    }
                }
            }
            task.resume()
        }
    }

    /// 将下载的临时文件复制到 Documents/Download/
    private func saveDownloadedFile(tempUrl: URL, filename: String) -> Bool {
        let documentsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        guard let downloadsDir = documentsDir?.appendingPathComponent("Download") else { return false }
        do {
            try FileManager.default.createDirectory(at: downloadsDir, withIntermediateDirectories: true)
            let destUrl = downloadsDir.appendingPathComponent(filename)
            if FileManager.default.fileExists(atPath: destUrl.path) {
                try FileManager.default.removeItem(at: destUrl)
            }
            try FileManager.default.copyItem(at: tempUrl, to: destUrl)
            return true
        } catch {
            return false
        }
    }

    /// 解析 Content-Disposition 头获取文件名（对齐 Android parseContentDisposition）
    private func parseContentDisposition(_ disposition: String) -> String? {
        if disposition.isEmpty { return nil }
        // filename*=UTF-8''编码文件名
        if let range = disposition.range(of: #"filename\*\s*=\s*UTF-8''([^;]+)"#, options: .regularExpression) {
            let raw = disposition[range]
            if let start = raw.range(of: "UTF-8''") {
                let encoded = String(raw[start.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                return encoded.removingPercentEncoding
            }
        }
        // filename="文件名"
        if let range = disposition.range(of: #"filename\s*=\s*"([^"]+)""#, options: .regularExpression) {
            let raw = disposition[range]
            if let start = raw.range(of: "\""), let end = raw.range(of: "\"", range: start.upperBound..<raw.endIndex) {
                return String(raw[start.upperBound..<end.lowerBound])
            }
        }
        // filename=文件名（无引号）
        if let range = disposition.range(of: #"filename\s*=\s*([^;]+)"#, options: .regularExpression) {
            let raw = disposition[range]
            if let start = raw.range(of: "=") {
                return String(raw[start.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return nil
    }

    // MARK: - Toast 提示

    private var toastAlert: UIAlertController?

    private func showToast(_ message: String) {
        // 防止连续下载时叠放多个弹窗
        if let existing = toastAlert, existing.presentingViewController != nil {
            existing.dismiss(animated: false)
        }
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        toastAlert = alert
        present(alert, animated: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            alert.dismiss(animated: true)
        }
    }
}