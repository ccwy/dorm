package com.dorm.management

import android.app.Application
import android.util.Log

class DormApplication : Application() {

    companion object {
        private const val TAG = "DormApplication"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "DormApplication onCreate")

        // 创建数据目录
        val dataDir = getExternalFilesDir(null)?.resolve("data")
        if (dataDir != null && !dataDir.exists()) {
            dataDir.mkdirs()
        }

        val dbDir = getExternalFilesDir(null)?.resolve("data/db")
        if (dbDir != null && !dbDir.exists()) {
            dbDir.mkdirs()
        }

        val backupDir = getExternalFilesDir(null)?.resolve("data/backups")
        if (backupDir != null && !backupDir.exists()) {
            backupDir.mkdirs()
        }
    }
}