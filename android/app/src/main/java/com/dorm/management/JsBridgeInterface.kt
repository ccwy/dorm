package com.dorm.management

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import android.webkit.JavascriptInterface
import androidx.core.app.NotificationCompat
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class JsBridgeInterface(private val activity: Activity) {

    companion object {
        private const val TAG = "JsBridge"
        private const val REQUEST_FILE_CHOOSER = 1001
        private const val REQUEST_CAMERA = 1002
        private const val NOTIFICATION_CHANNEL_ID = "dorm_management"
    }

    @JavascriptInterface
    fun chooseFile(acceptTypes: String): String {
        try {
            val intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.type = acceptTypes.ifEmpty { "*/*" }
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            activity.startActivityForResult(intent, REQUEST_FILE_CHOOSER)
        } catch (e: Exception) {
            Log.e(TAG, "chooseFile failed", e)
        }
        return ""
    }

    @JavascriptInterface
    fun takePhoto(): String {
        try {
            val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            if (intent.resolveActivity(activity.packageManager) != null) {
                val photoFile = createImageFile()
                val uri = FileProvider.getUriForFile(
                    activity, "${activity.packageName}.fileprovider", photoFile
                )
                intent.putExtra(MediaStore.EXTRA_OUTPUT, uri)
                intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                activity.startActivityForResult(intent, REQUEST_CAMERA)
            }
        } catch (e: Exception) {
            Log.e(TAG, "takePhoto failed", e)
        }
        return ""
    }

    @JavascriptInterface
    fun showNotification(title: String, message: String) {
        try {
            val notificationManager = activity.getSystemService(
                Context.NOTIFICATION_SERVICE
            ) as NotificationManager

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = NotificationChannel(
                    NOTIFICATION_CHANNEL_ID, "宿舍管理",
                    NotificationManager.IMPORTANCE_DEFAULT
                )
                notificationManager.createNotificationChannel(channel)
            }

            val notification = NotificationCompat.Builder(activity, NOTIFICATION_CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(title)
                .setContentText(message)
                .setAutoCancel(true)
                .build()
            notificationManager.notify(System.currentTimeMillis().toInt(), notification)
        } catch (e: Exception) {
            Log.e(TAG, "showNotification failed", e)
        }
    }

    @JavascriptInterface
    fun getDeviceInfo(): String {
        return JSONObject().apply {
            put("platform", "android")
            put("deviceModel", Build.MODEL)
            put("androidVersion", Build.VERSION.RELEASE)
            put("sdkVersion", Build.VERSION.SDK_INT)
            put("appId", activity.packageName)
        }.toString()
    }

    @JavascriptInterface
    fun exitApp() {
        activity.finish()
    }

    private fun createImageFile(): File {
        val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
        val storageDir = activity.getExternalFilesDir(Environment.DIRECTORY_PICTURES)
            ?: File(activity.filesDir, "pictures")
        if (!storageDir.exists()) storageDir.mkdirs()
        return File.createTempFile("JPEG_${timeStamp}_", ".jpg", storageDir)
    }
}