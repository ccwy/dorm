//
//  AppDelegate.swift
//  DormManagement
//
//  传统 AppDelegate 生命周期（iOS 12 兼容，不使用 SceneDelegate）
//

import UIKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // 创建窗口（纯代码，不使用 Storyboard）
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = ViewController()
        window?.makeKeyAndVisible()
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // 应用进入前台活跃状态，保持屏幕常亮由 ViewController 管理
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // 应用即将失去前台状态（来电、锁屏等），暂停动画等非关键任务
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // 应用进入后台，iOS 默认会暂停应用，本地 Flask 服务随之暂停
        // 重新进入前台时由 ViewController 恢复
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // 应用即将回到前台
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // 应用即将终止，Python 进程随应用退出
    }

    // iOS 12 无 SceneDelegate，此方法无需实现
}