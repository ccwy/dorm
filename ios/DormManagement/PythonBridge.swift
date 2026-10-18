import Foundation

typealias PyRef = UnsafeMutableRawPointer

class PythonBridge {

    static let shared = PythonBridge()

    // MARK: - 常量

    private let adapterModule = "utils.ios_adapter"

    // MARK: - 状态

    private(set) var isInitialized = false
    private var pyHandle: UnsafeMutableRawPointer?
    private var cachedAdapter: PyRef?
    private let adapterLock = NSLock()   // 保护 cachedAdapter 跨线程读写

    private init() {}

    // MARK: - Python C API 函数指针

    private var fnInitialize: (@convention(c) () -> Void)?
    private var fnIsInitialized: (@convention(c) () -> Int32)?
    private var fnRunString: (@convention(c) (UnsafePointer<CChar>) -> Int32)?
    private var fnImportModule: (@convention(c) (UnsafePointer<CChar>) -> PyRef?)?
    private var fnGetAttr: (@convention(c) (PyRef?, UnsafePointer<CChar>) -> PyRef?)?
    private var fnCallObject: (@convention(c) (PyRef?, PyRef?) -> PyRef?)?
    private var fnUnicodeAsUTF8: (@convention(c) (PyRef?) -> UnsafePointer<CChar>?)?
    private var fnDecRef: (@convention(c) (PyRef?) -> Void)?
    // 异常打印：PyObject_CallObject 返回 NULL 时调用，打印并清除挂起的 Python 异常
    private var fnErrPrint: (@convention(c) () -> Void)?
    // GIL 管理：跨线程调用 Python C API 必须持有 GIL
    private var fnGilStateEnsure: (@convention(c) () -> Int32)?
    private var fnGilStateRelease: (@convention(c) (Int32) -> Void)?
    private var fnEvalSaveThread: (@convention(c) () -> UnsafeMutableRawPointer?)?

    // MARK: - GIL 辅助

    /// 在当前线程获取 GIL 并执行闭包。
    /// 所有 Python C API 调用必须经此包裹，否则会崩溃或死锁。
    private func withGIL<T>(_ body: () -> T) -> T {
        let gstate = fnGilStateEnsure?() ?? 0
        defer { fnGilStateRelease?(gstate) }
        return body()
    }

    // MARK: - 初始化

    func initialize(documentsPath: String) {
        guard !isInitialized else { return }

        #if PYTHON_FRAMEWORK_AVAILABLE
        // 1. 注入环境变量（必须在 Py_Initialize 之前）
        setenv("IOS_ENV", "true", 1)
        setenv("IOS_DOCUMENT_DIR", documentsPath, 1)

        // Python 运行环境（对齐 kivy-ios 官方 main.m 方案）：
        // PYTHONHOME 指向 framework 的 Resources，CPython 据此定位
        //   <PYTHONHOME>/lib/python311.zip（标准库）和 lib/python3.11/site-packages
        // PYTHONPATH 显式包含 site-packages，确保第三方包可 import
        let frameworkPath = Bundle.main.privateFrameworksPath.map { $0 + "/Python.framework" }
            ?? "Python.framework"
        setenv("PYTHONHOME", frameworkPath + "/Resources", 1)
        setenv("PYTHONPATH", frameworkPath + "/Resources/lib/python3.11/site-packages", 1)
        setenv("PYTHONDONTWRITEBYTECODE", "1", 1)
        setenv("PYTHONNOUSERSITE", "1", 1)

        // 2. 加载 Python 动态库（使用 app bundle 内嵌 Frameworks 的绝对路径）
        let frameworkBinary = frameworkPath + "/Python"
        guard let handle = dlopen(frameworkBinary, RTLD_NOW | RTLD_GLOBAL) else {
            fatalError("[PythonBridge] 无法加载 Python.framework: \(String(cString: dlerror()))")
        }
        pyHandle = handle
        loadSymbols(handle)

        // 3. 初始化 Python 解释器（此后 GIL 由当前线程持有）
        fnInitialize?()
        isInitialized = fnIsInitialized?() != 0

        // 4. 将 App bundle 中的 Python 源码路径加入 sys.path
        injectPythonPath()

        // 5. 释放 GIL：主线程不再独占，后续各线程通过 PyGILState_Ensure 获取
        _ = fnEvalSaveThread?()
        #else
        isInitialized = false
        #endif
    }

    private func loadSymbols(_ handle: UnsafeMutableRawPointer) {
        func sym<T>(_ name: String) -> T? {
            return dlsym(handle, name).map { unsafeBitCast($0, to: T.self) }
        }
        fnInitialize = sym("Py_Initialize")
        fnIsInitialized = sym("Py_IsInitialized")
        fnRunString = sym("PyRun_SimpleString")
        fnImportModule = sym("PyImport_ImportModule")
        fnGetAttr = sym("PyObject_GetAttrString")
        fnCallObject = sym("PyObject_CallObject")
        fnUnicodeAsUTF8 = sym("PyUnicode_AsUTF8")
        fnDecRef = sym("Py_DecRef")
        fnErrPrint = sym("PyErr_Print")
        fnGilStateEnsure = sym("PyGILState_Ensure")
        fnGilStateRelease = sym("PyGILState_Release")
        fnEvalSaveThread = sym("PyEval_SaveThread")
    }

    private func injectPythonPath() {
        guard let bundlePath = Bundle.main.resourcePath else { return }
        let script = """
        import sys
        _bundle = \(bundlePath.singleQuoted)
        if _bundle not in sys.path:
            sys.path.insert(0, _bundle)
        """
        _ = fnRunString?(script)
    }

    // MARK: - Flask 服务器控制

    func startServer() {
        #if PYTHON_FRAMEWORK_AVAILABLE
        guard isInitialized else {
            NSLog("[PythonBridge] Python 未初始化，无法启动服务器")
            fatalError("[PythonBridge] Python 未初始化，无法启动服务器")
        }
        withGIL {
            let adapter = getAdapter()
            guard let fn = fnGetAttr, let call = fnCallObject else { return }
            guard let method = fn(adapter, "start_flask_server") else {
                NSLog("[PythonBridge] 无法获取 start_flask_server 方法")
                return
            }
            defer { fnDecRef?(method) }
            if let result = call(method, nil) {
                fnDecRef?(result)
            } else {
                // PyObject_CallObject 返回 NULL 表示 Python 端抛出了异常。
                // 必须调用 PyErr_Print 打印并清除异常，否则异常被静默吞掉，
                // 后台线程无痕结束，主线程轮询 get_progress() 永远拿到 "0|正在初始化..."。
                NSLog("[PythonBridge] start_flask_server 抛出 Python 异常:")
                fnErrPrint?()
            }
        }
        #else
        NSLog("[PythonBridge] 开发占位：未链接 Python.framework")
        fatalError("[PythonBridge] 开发占位：需要 kivy-ios 编译的 Python.framework 才能启动 Flask 服务器")
        #endif
    }

    func getProgress() -> (Int, String) {
        #if PYTHON_FRAMEWORK_AVAILABLE
        guard isInitialized else { return (0, "正在初始化...") }
        if let str = withGIL({ callStringMethod("get_progress") }) {
            return parseProgress(str)
        }
        return (0, "正在初始化...")
        #else
        return (0, "开发模式：Python.framework 未链接")
        #endif
    }

    func getSystemTitle() -> String {
        #if PYTHON_FRAMEWORK_AVAILABLE
        guard isInitialized else { return "行政后勤管理系统" }
        return withGIL { callStringMethod("get_system_title") } ?? "行政后勤管理系统"
        #else
        return "行政后勤管理系统"
        #endif
    }

    // MARK: - 内部工具

    private func getAdapter() -> PyRef {
        adapterLock.lock()
        defer { adapterLock.unlock() }
        if let cached = cachedAdapter { return cached }
        guard let module = fnImportModule?(adapterModule) else {
            NSLog("[PythonBridge] 无法导入模块 \(adapterModule)")
            fatalError("[PythonBridge] 无法导入模块 \(adapterModule)")
        }
        cachedAdapter = module
        return module
    }

    /// 调用适配模块的无参方法并返回字符串结果。
    /// 必须在持有 GIL 时调用。
    private func callStringMethod(_ name: String) -> String? {
        let adapter = getAdapter()
        guard let fn = fnGetAttr, let call = fnCallObject, let utf8 = fnUnicodeAsUTF8 else {
            return nil
        }
        guard let method = fn(adapter, name) else { return nil }
        defer { fnDecRef?(method) }
        guard let result = call(method, nil) else { return nil }
        defer { fnDecRef?(result) }
        guard let cStr = utf8(result) else { return nil }
        return String(cString: cStr)
    }

    private func parseProgress(_ str: String) -> (Int, String) {
        let parts = str.split(separator: "|", maxSplits: 1)
        let pct = parts.count > 0 ? Int(parts[0]) ?? 0 : 0
        let msg = parts.count > 1 ? String(parts[1]) : ""
        return (pct, msg)
    }
}

// MARK: - String 辅助

extension String {
    /// 转为 Python 单引号字符串字面量（用于拼接到 PyRun_SimpleString 脚本中）
    var singleQuoted: String {
        "'" + replacingOccurrences(of: "\\", with: "\\\\")
             .replacingOccurrences(of: "'", with: "\\'") + "'"
    }
}