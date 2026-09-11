package com.dorm.management

import android.app.Application
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class DormApplication : Application() {

    companion object {
        private const val TAG = "DormApplication"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "DormApplication onCreate")

        // 初始化 Chaquopy Python（Chaquopy 文档推荐在 Application.onCreate() 中调用）
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // 创建数据根目录（子目录由 Python ensure_data_dirs() 创建）
        // 使用 getExternalFilesDir(null) 获取外部存储应用专属目录
        // 路径: /sdcard/Android/data/com.dorm.management/files/
        // 优点: 系统文件管理器可访问，方便用户查看和管理数据
        // 回退: 如果外部存储不可用，使用内部存储 getFilesDir()
        val externalDir = getExternalFilesDir(null)
        val dataDir = if (externalDir != null) {
            externalDir.resolve("data")
        } else {
            Log.w(TAG, "外部存储不可用，回退到内部存储")
            getFilesDir()?.resolve("data")
        }
        if (dataDir != null && !dataDir.exists()) {
            dataDir.mkdirs()
            Log.i(TAG, "创建数据目录: ${dataDir.absolutePath}")
        }
    }
}