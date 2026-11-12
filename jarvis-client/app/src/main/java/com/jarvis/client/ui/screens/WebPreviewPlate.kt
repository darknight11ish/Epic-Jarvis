package com.jarvis.client.ui.screens

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.net.Uri
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome

/**
 * Sandboxed Mobile Web & Dev Server Preview (inspired by Mobile-Harness).
 *
 * Rules:
 * - Rule 1 & Rule 2: Strictly restricted to local and private mesh addresses (loopback, 192.168.*,
 *   10.*, 100.*, *.ts.net, *.nord). External public internet domains are blocked.
 * - Hardware sandbox: file access and ContentProvider access are disabled.
 * - Console telemetry: captures console.log / warn / error into a live developer tray.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun WebPreviewPlate(
    defaultUrl: String = "http://127.0.0.1:3000",
    onClose: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    var urlInput by remember { mutableStateOf(defaultUrl) }
    var currentUrl by remember { mutableStateOf(defaultUrl) }
    var pageTitle by remember { mutableStateOf("Ready") }
    var isLoading by remember { mutableStateOf(false) }
    var webViewRef by remember { mutableStateOf<WebView?>(null) }
    var showConsole by remember { mutableStateOf(false) }
    var securityWarning by remember { mutableStateOf<String?>(null) }
    val consoleLogs = remember { mutableStateListOf<ConsoleLog>() }

    fun isAllowedHost(url: String): Boolean {
        val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return false
        val host = uri.host?.lowercase() ?: return false
        if (host == "localhost" || host == "127.0.0.1") return true
        if (host.endsWith(".ts.net") || host.endsWith(".nord")) return true
        if (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("100.")) return true
        return false
    }

    fun navigate(target: String) {
        val clean = if (!target.startsWith("http://") && !target.startsWith("https://")) {
            "http://$target"
        } else {
            target
        }
        if (isAllowedHost(clean)) {
            securityWarning = null
            currentUrl = clean
            webViewRef?.loadUrl(clean)
        } else {
            securityWarning = "Blocked: Public external internet addresses are disabled (Rule 1 & Rule 2). Only local servers (127.0.0.1, private mesh) are allowed."
        }
    }

    Section("Web preview") {
        Plate {
            Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                // Top control bar
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextInput(
                        value = urlInput,
                        onValueChange = { urlInput = it },
                        modifier = Modifier.weight(1f),
                        placeholder = "http://127.0.0.1:3000",
                    )
                    Spacer(Modifier.width(8.dp))
                    Primary("Go", onClick = { navigate(urlInput) })
                    Spacer(Modifier.width(4.dp))
                    Quiet("Reload", onClick = { webViewRef?.reload() })
                    if (onClose != null) {
                        Spacer(Modifier.width(4.dp))
                        Quiet("Close", onClick = onClose)
                    }
                }

                Gap(6)

                // Quick Port Selector chips
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    listOf("3000", "5173", "8080", "8000").forEach { port ->
                        Quiet(":$port", onClick = {
                            urlInput = "http://127.0.0.1:$port"
                            navigate(urlInput)
                        })
                    }
                    Spacer(Modifier.weight(1f))
                    Quiet(
                        if (showConsole) "Hide Logs" else "Logs (${consoleLogs.size})",
                        onClick = { showConsole = !showConsole },
                    )
                }

                if (securityWarning != null) {
                    Gap(8)
                    Text(
                        text = securityWarning.orEmpty(),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.badInk,
                    )
                }

                Gap(8)

                // Status info
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(
                        text = if (isLoading) "Loading..." else pageTitle,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                        maxLines = 1,
                    )
                    Text(
                        text = currentUrl,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                        maxLines = 1,
                    )
                }

                Gap(6)

                // Sandboxed WebView container
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(380.dp)
                        .background(Color.White),
                ) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { ctx ->
                            WebView(ctx).apply {
                                webViewRef = this
                                settings.apply {
                                    javaScriptEnabled = true
                                    domStorageEnabled = true
                                    allowFileAccess = false
                                    allowContentAccess = false
                                    mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                                }
                                webViewClient = object : WebViewClient() {
                                    override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                                        isLoading = true
                                    }

                                    override fun onPageFinished(view: WebView?, url: String?) {
                                        isLoading = false
                                        pageTitle = view?.title ?: "Web Preview"
                                    }

                                    override fun shouldInterceptRequest(
                                        view: WebView?,
                                        request: WebResourceRequest?,
                                    ): WebResourceResponse? {
                                        val reqUrl = request?.url?.toString() ?: ""
                                        if (reqUrl.isNotBlank() && !isAllowedHost(reqUrl)) {
                                            // Deny external network requests
                                            return WebResourceResponse("text/plain", "UTF-8", null)
                                        }
                                        return super.shouldInterceptRequest(view, request)
                                    }
                                }
                                webChromeClient = object : WebChromeClient() {
                                    override fun onConsoleMessage(msg: ConsoleMessage?): Boolean {
                                        if (msg != null) {
                                            consoleLogs.add(
                                                ConsoleLog(
                                                    level = msg.messageLevel().name,
                                                    message = msg.message(),
                                                    lineNumber = msg.lineNumber(),
                                                    source = msg.sourceId().substringAfterLast('/'),
                                                ),
                                            )
                                        }
                                        return true
                                    }

                                    override fun onReceivedTitle(view: WebView?, title: String?) {
                                        if (!title.isNullOrBlank()) pageTitle = title
                                    }
                                }
                                loadUrl(currentUrl)
                            }
                        },
                    )
                }

                // Collapsible console logs
                if (showConsole) {
                    Gap(8)
                    Text("Console Telemetry", style = MaterialTheme.typography.labelMedium, color = chrome.textHi)
                    Gap(4)
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(140.dp)
                            .background(chrome.surface1)
                            .padding(6.dp),
                    ) {
                        if (consoleLogs.isEmpty()) {
                            Text("No console messages captured yet.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                        } else {
                            LazyColumn(modifier = Modifier.fillMaxSize()) {
                                items(consoleLogs) { log ->
                                    val color = when (log.level) {
                                        "ERROR" -> chrome.badInk
                                        "WARNING" -> chrome.warnInk
                                        else -> chrome.textMid
                                    }
                                    Text(
                                        text = "[${log.level}] ${log.source}:${log.lineNumber} - ${log.message}",
                                        style = MaterialTheme.typography.bodySmall.copy(fontSize = 11.sp),
                                        color = color,
                                    )
                                }
                            }
                        }
                    }
                    Gap(4)
                    Quiet("Clear logs", onClick = { consoleLogs.clear() })
                }
            }
        }
    }
}

data class ConsoleLog(
    val level: String,
    val message: String,
    val lineNumber: Int,
    val source: String,
)
