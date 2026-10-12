package com.slidegen.app

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class MainActivity : Activity() {

    private lateinit var webView: WebView
    private var pickedUri: Uri? = null
    private var pickedName: String = ""

    private val reqPickFile = 1001

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // 仅调试包开启 WebView 远程调试，正式包不开启
        if (BuildConfig.DEBUG) {
            WebView.setWebContentsDebuggingEnabled(true)
        }

        webView = WebView(this)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.webViewClient = WebViewClient()
        webView.addJavascriptInterface(Bridge(), "Android")
        setContentView(webView)

        webView.loadUrl("file:///android_asset/index.html")
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != reqPickFile) return

        val uri = if (resultCode == RESULT_OK) data?.data else null
        if (uri != null) {
            try {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                )
            } catch (_: Exception) { /* 某些 provider 不支持持久化，忽略 */ }

            pickedUri = uri
            pickedName = queryDisplayName(uri)
            runOnUiThread {
                webView.evaluateJavascript(
                    "window.onFilePicked(${jsStr(pickedName)}, ${jsStr(uri.toString())});",
                    null
                )
            }
        } else {
            runOnUiThread {
                webView.evaluateJavascript("window.onPickCancelled();", null)
            }
        }
    }

    private fun queryDisplayName(uri: Uri): String {
        var name = uri.lastPathSegment ?: "chart.mc"
        try {
            contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && cursor.moveToFirst()) {
                    name = cursor.getString(idx)
                }
            }
        } catch (_: Exception) { }
        return name
    }

    private fun readText(uri: Uri): String {
        return contentResolver.openInputStream(uri)?.use { input ->
            input.bufferedReader(Charsets.UTF_8).readText()
        } ?: throw IllegalStateException("无法读取所选文件（输入流为空）。")
    }

    /**
     * 在原文件所在目录创建一个 .bak 备份（内容为修改前的原文）。
     * 使用 DocumentsContract 在同级目录创建子文档，兼容本地存储 provider。
     */
    /**
     * 在原文件所在目录创建 .bak 备份（内容为修改前的原文）。
     * 优先使用 DocumentsContract 在同级目录创建；某些提供者（如「下载」目录）
     * 不允许应用在目录内创建文件，此时退回 MediaStore 写入「下载」集合。
     * 返回 (备份文件名, 提示信息)；文件名为 null 表示备份失败。
     */
    private fun makeBackup(uri: Uri, originalText: String): Pair<String?, String?> {
        val bakName = pickedName + ".bak"
        val bytes = originalText.toByteArray(Charsets.UTF_8)
        var lastErr = "未知错误"

        // 1) 尝试在原文件同级目录创建 .bak
        try {
            val authority = uri.authority ?: throw IllegalStateException("无 authority")
            val docId = DocumentsContract.getDocumentId(uri)
            val cut = docId.lastIndexOf('/')
            if (cut <= 0) throw IllegalStateException("无法解析父目录")
            val parentUri = DocumentsContract.buildDocumentUri(authority, docId.substring(0, cut))
            val created = DocumentsContract.createDocument(
                contentResolver, parentUri, "application/octet-stream", bakName
            ) ?: throw IllegalStateException("createDocument 返回 null")
            contentResolver.openOutputStream(created, "wt")?.use { it.write(bytes) }
                ?: throw IllegalStateException("输出流为空")
            return Pair(bakName, null)
        } catch (e: Exception) {
            lastErr = e.message ?: e.toString()
        }

        // 2) 退回 MediaStore：写入系统「下载」集合（API 29+ 无需额外权限）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, bakName)
                    put(MediaStore.MediaColumns.MIME_TYPE, "application/octet-stream")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                }
                val item = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: throw IllegalStateException("MediaStore insert 返回 null")
                contentResolver.openOutputStream(item)?.use { it.write(bytes) }
                    ?: throw IllegalStateException("MediaStore 输出流为空")
                return Pair(bakName, "原目录不允许写入备份，已将 .bak 存入系统「下载」目录。")
            } catch (e: Exception) {
                lastErr = e.message ?: e.toString()
            }
        }

        return Pair(null, lastErr)
    }

    private fun jsStr(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) {
            when (c) {
                '\\' -> sb.append("\\\\")
                '"' -> sb.append("\\\"")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        sb.append("\"")
        return sb.toString()
    }

    inner class Bridge {

        /** 打开系统文件管理器，可视化选择一个 .mc 谱面文件 */
        @JavascriptInterface
        fun pickFile() {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(
                    Intent.EXTRA_MIME_TYPES,
                    arrayOf("application/octet-stream", "text/plain", "*/*")
                )
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            }
            @Suppress("DEPRECATION")
            runOnUiThread { startActivityForResult(intent, reqPickFile) }
        }

        /** 当前是否已经选择文件 */
        @JavascriptInterface
        fun hasFile(): Boolean = pickedUri != null

        @JavascriptInterface
        fun fileName(): String = pickedName

        /** 读取当前所选谱面文件的文本内容 */
        @JavascriptInterface
        fun readFile(): String {
            val uri = pickedUri ?: return ""
            return try {
                readText(uri)
            } catch (e: Exception) {
                ""
            }
        }

        /**
         * 将生成的 Slide 写回原文件（同一目录、同一文件）。
         * 写入前先在原目录生成 .bak 备份。
         * 返回 JSON: {"ok":true,"bak":"song.mc.bak"} 或 {"ok":false,"error":"..."}
         */
        @JavascriptInterface
        fun writeBack(slideText: String): String {
            val uri = pickedUri ?: return "{\"ok\":false,\"error\":\"尚未选择谱面文件。\"}"
            return try {
                val original = readText(uri)

                val marker = "\"note\":["
                val idx = original.indexOf(marker)
                if (idx < 0) {
                    return "{\"ok\":false,\"error\":\"未在谱面文件中找到 \\\"note\\\":[ 标记。\"}"
                }

                val (bakName, bakNote) = makeBackup(uri, original)

                // 仅在首处 "\"note\":[" 之后插入，与桌面版 replace(..., 1) 行为一致
                val insertAt = idx + marker.length
                val newContent = original.substring(0, insertAt) + slideText + "," +
                        original.substring(insertAt)

                contentResolver.openOutputStream(uri, "wt")?.use { out ->
                    out.write(newContent.toByteArray(Charsets.UTF_8))
                } ?: return "{\"ok\":false,\"error\":\"无法写入文件（输出流为空）。\"}"

                if (bakName != null && bakNote == null) {
                    "{\"ok\":true,\"bak\":${jsStr(bakName)}}"
                } else if (bakName != null) {
                    "{\"ok\":true,\"bak\":${jsStr(bakName)},\"warn\":${jsStr(bakNote!!)}}"
                } else {
                    "{\"ok\":true,\"bak\":null,\"warn\":${jsStr("备份未生成：$bakNote")}}"
                }
            } catch (e: Exception) {
                "{\"ok\":false,\"error\":${jsStr(e.message ?: e.toString())}}"
            }
        }

        /** 调用 Python 核心计算 Slide，返回 JSON 结果字符串 */
        @JavascriptInterface
        fun generate(paramsJson: String): String {
            return try {
                val module = Python.getInstance().getModule("slide_core")
                module.callAttr("generate", paramsJson).toString()
            } catch (e: Exception) {
                "{\"ok\":false,\"error\":${jsStr(e.message ?: e.toString())}}"
            }
        }
    }
}
