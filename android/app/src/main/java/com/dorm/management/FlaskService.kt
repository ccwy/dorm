package com.dorm.management

import android.app.*
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class FlaskService : Service() {

    companion object {
        private const val NOTIFICATION_CHANNEL_ID = "dorm_flask_service"
        private const val NOTIFICATION_ID = 1001
    }

    private var flaskThread: Thread? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = createNotification("宿舍管理系统运行中")
        startForeground(NOTIFICATION_ID, notification)

        // 在后台线程启动 Flask
        if (flaskThread == null || !flaskThread!!.isAlive) {
            flaskThread = Thread {
                try {
                    // 安全检查：确保 Python 已初始化（正常情况下 DormApplication.onCreate 已调用）
                    if (!Python.isStarted()) {
                        Python.start(AndroidPlatform(applicationContext))
                    }
                    val python = Python.getInstance()
                    val androidAdapter = python.getModule("utils.android_adapter")
                    androidAdapter.callAttr("set_android_context", this)
                    androidAdapter.callAttr("start_flask_server")
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }.also { it.start() }
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        flaskThread?.interrupt()
        flaskThread = null
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "Flask 后台服务",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "保持宿舍管理系统后台运行"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(text: String): Notification {
        val pendingIntent = Intent(this, MainActivity::class.java).let { notificationIntent ->
            PendingIntent.getActivity(
                this, 0, notificationIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }

        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("行政后勤管理系统")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }
}