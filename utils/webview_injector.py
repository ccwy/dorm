
import webview
import threading
import time


def inject_login_check():
    """在WebView加载页面时注入登录状态检查的JavaScript"""
    try:
        # 获取当前窗口引用
        window = webview.windows[0]
        
        # 注入JS代码以检查登录状态并重定向到登录页面
        check_js = '''
        function checkLoginStatus() {
            // 检查用户是否已登录
            const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';
            
            // 如果已登录，强制清除登录状态
            if (isLoggedIn) {
                localStorage.removeItem('isLoggedIn');
                localStorage.removeItem('username');
                localStorage.removeItem('userId');
                console.log('强制清除前端登录状态');
                // 重定向到登录页面
                window.location.href = '/login';
            }
        }
        
        // 立即执行检查
        checkLoginStatus();
        
        // 添加页面加载事件监听，确保每个页面都检查登录状态
        window.addEventListener('load', checkLoginStatus);
        '''
        
        # 使用webview的evaluate_js方法注入JavaScript
        window.evaluate_js(check_js)
        print("已注入登录状态检查JavaScript")
    except Exception as e:
        print(f"注入JavaScript失败: {str(e)}")


def start_delayed_injection(delay_seconds=1):
    """启动延迟注入线程，确保WebView完全初始化后再注入JavaScript"""
    def delayed_injection():
        time.sleep(delay_seconds)  # 等待指定时间让WebView完全加载
        inject_login_check()
    
    # 启动一个线程进行延迟注入
    injection_thread = threading.Thread(target=delayed_injection, daemon=True)
    injection_thread.start()
    return injection_thread