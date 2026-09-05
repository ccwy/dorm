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
        val dataDir = getFilesDir()?.resolve("data")
        if (dataDir != null && !dataDir.exists()) {
            dataDir.mkdirs()
        }
    }
}