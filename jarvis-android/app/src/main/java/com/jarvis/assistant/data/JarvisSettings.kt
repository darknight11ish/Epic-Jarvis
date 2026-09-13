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

    private val _hasSecret = MutableStateFlow(!prefs.getString(KEY_SECRET, "").isNullOrEmpty())

    /** Whether a signing key exists, without exposing the key itself to the UI. */
    val hasSharedSecret: StateFlow<Boolean> = _hasSecret.asStateFlow()

    var sharedSecret: String
        get() = prefs.getString(KEY_SECRET, "") ?: ""
        set(value) {
            prefs.edit { putString(KEY_SECRET, value) }
            _hasSecret.value = value.isNotEmpty()
        }

    private val _hasAuthToken = MutableStateFlow(!prefs.getString(KEY_TOKEN, "").isNullOrEmpty())
    val hasAuthToken: StateFlow<Boolean> = _hasAuthToken.asStateFlow()

    /** Sent as `Authorization: Bearer` on the upgrade request, before the socket opens. */
    var authToken: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) {
            prefs.edit { putString(KEY_TOKEN, value) }
            _hasAuthToken.value = value.isNotEmpty()
        }

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
        private const val KEY_TOKEN = "auth_token"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_HANDS_FREE = "hands_free"

        /** Tailscale CGNAT range; replace with your own desktop's Tailscale IP. */
        const val DEFAULT_SERVER = "100.64.0.1:4719"
        const val WS_PATH = "/api/mobile/ws"

        /**
         * Whether an unencrypted `ws://` target is somewhere the traffic cannot
         * leave the private network.
         *
         * Android's network security config cannot express this: its domain rules
         * take hostnames and IP literals, not CIDR ranges, so a 100.64.0.0/10 rule
         * is not writable there and the check has to live in code.
         */
        fun isCleartextTargetPrivate(url: String): Boolean {
            if (!url.startsWith("ws://", ignoreCase = true)) return true
            val host = hostOf(url)?.lowercase() ?: return false

            if (host == "localhost" || host == "::1" || host.startsWith("127.")) return true
            if (host.endsWith(".ts.net") || host.endsWith(".local")) return true

            val octets = host.split('.')
            if (octets.size != 4) return false
            val parts = octets.map { it.toIntOrNull() ?: return false }
            if (parts.any { it !in 0..255 }) return false

            return when {
                // Tailscale CGNAT range.
                parts[0] == 100 && parts[1] in 64..127 -> true
                parts[0] == 10 -> true
                parts[0] == 192 && parts[1] == 168 -> true
                parts[0] == 172 && parts[1] in 16..31 -> true
                else -> false
            }
        }

        fun hostOf(url: String): String? {
            val schemeEnd = url.indexOf("://").takeIf { it >= 0 }?.plus(3) ?: return null
            val rest = url.substring(schemeEnd)
            val authority = rest.substringBefore('/')
            if (authority.startsWith("[")) return authority.substringAfter('[').substringBefore(']')
            return authority.substringBefore(':').takeUnless { it.isEmpty() }
        }

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
