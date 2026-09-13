package com.jarvis.assistant.data

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

/**
 * Single-user configuration: which desktop to talk to and the shared secret used
 * to sign approval decisions. Backed by plain SharedPreferences — the secret is
 * only meaningful to the paired desktop and never leaves the Tailnet.
 */
class JarvisSettings(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _serverAddress = MutableStateFlow(
        prefs.getString(KEY_SERVER, DEFAULT_SERVER) ?: DEFAULT_SERVER,
    )
    val serverAddress: StateFlow<String> = _serverAddress.asStateFlow()

    private val _handsFree = MutableStateFlow(prefs.getBoolean(KEY_HANDS_FREE, false))
    val handsFree: StateFlow<Boolean> = _handsFree.asStateFlow()

    /** Stable per-install identifier the desktop pairs against. */
    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
            prefs.edit { putString(KEY_DEVICE_ID, it) }
        }

    var sharedSecret: String
        get() = prefs.getString(KEY_SECRET, "") ?: ""
        set(value) = prefs.edit { putString(KEY_SECRET, value) }

    fun setServerAddress(value: String) {
        val trimmed = value.trim()
        prefs.edit { putString(KEY_SERVER, trimmed) }
        _serverAddress.value = trimmed
    }

    fun setHandsFree(value: Boolean) {
        prefs.edit { putBoolean(KEY_HANDS_FREE, value) }
        _handsFree.value = value
    }

    /**
     * Accepts a bare host, `host:port`, or a full ws/wss/http/https URL and
     * normalises it to the WebSocket endpoint the desktop server exposes.
     */
    fun resolveWebSocketUrl(): String = normalizeToWebSocketUrl(_serverAddress.value)

    companion object {
        private const val PREFS = "jarvis_settings"
        private const val KEY_SERVER = "server_address"
        private const val KEY_SECRET = "shared_secret"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_HANDS_FREE = "hands_free"

        /** Tailscale CGNAT range; replace with your own desktop's Tailscale IP. */
        const val DEFAULT_SERVER = "100.64.0.1:4719"
        const val WS_PATH = "/api/mobile/ws"

        fun normalizeToWebSocketUrl(raw: String): String {
            val input = raw.trim().ifEmpty { DEFAULT_SERVER }
            val withScheme = when {
                input.startsWith("ws://") || input.startsWith("wss://") -> input
                input.startsWith("http://") -> "ws://" + input.removePrefix("http://")
                input.startsWith("https://") -> "wss://" + input.removePrefix("https://")
                else -> "ws://$input"
            }
            val schemeEnd = withScheme.indexOf("://") + 3
            val hasPath = withScheme.indexOf('/', schemeEnd) >= 0
            return if (hasPath) withScheme else withScheme.trimEnd('/') + WS_PATH
        }
    }
}
