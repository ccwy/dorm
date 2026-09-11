package com.dorm.management

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView

class DormWebChromeClient(private val activity: Activity) : WebChromeClient() {

    companion object {
        const val REQUEST_FILE_CHOOSER = 1001
    }

    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    override fun onShowFileChooser(
        webView: WebView?,
        filePathCallback: ValueCallback<Array<Uri>>?,
        fileChooserParams: FileChooserParams?
    ): Boolean {
        // 取消上一次未完成的回调（关键：防止WebView认为文件选择仍在进行）
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

    /**
     * 处理文件选择结果，由 MainActivity.onActivityResult 调用
     * @return true 表示成功处理了回调
     */
    fun handleFileChooserResult(resultCode: Int, data: Intent?): Boolean {
        if (filePathCallback == null) return false

        if (resultCode == Activity.RESULT_OK && data != null) {
            // 从结果中获取URI
            val result = data.data?.let { arrayOf(it) }
                ?: data.clipData?.let { clip ->
                    Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
                }
                ?: arrayOf()
            filePathCallback?.onReceiveValue(result)
        } else {
            // 用户取消或未选择文件，必须传 null 让 WebView 知道选择已结束
            filePathCallback?.onReceiveValue(null)
        }
        filePathCallback = null
        return true
    }

    override fun onProgressChanged(view: WebView?, newProgress: Int) {
        super.onProgressChanged(view, newProgress)
        // 通知 MainActivity 更新加载进度
        (activity as? MainActivity)?.updateWebProgress(newProgress)
    }
}