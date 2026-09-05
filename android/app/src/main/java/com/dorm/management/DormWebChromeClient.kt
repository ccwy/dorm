package com.dorm.management

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView

class DormWebChromeClient(private val activity: Activity) : WebChromeClient() {

    companion object {
        private const val REQUEST_FILE_CHOOSER = 1001
    }

    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    override fun onShowFileChooser(
        webView: WebView?,
        filePathCallback: ValueCallback<Array<Uri>>?,
        fileChooserParams: FileChooserParams?
    ): Boolean {
        this.filePathCallback?.onReceiveValue(null)
        this.filePathCallback = filePathCallback

        try {
            val intent = fileChooserParams?.createIntent()
            activity.startActivityForResult(intent, REQUEST_FILE_CHOOSER)
        } catch (e: Exception) {
            this.filePathCallback = null
            return false
        }
        return true
    }

    override fun onProgressChanged(view: WebView?, newProgress: Int) {
        super.onProgressChanged(view, newProgress)
        // 通知 MainActivity 更新加载进度
        (activity as? MainActivity)?.updateWebProgress(newProgress)
    }
}