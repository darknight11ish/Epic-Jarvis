package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Everything the client needs to find and re-find the desktop.
 *
 * The token is deliberately not here — it lives in [TokenStore], behind the
 * Keystore. This class holds only things that are not secrets.
 */
class ClientSettings(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _host = MutableStateFlow(prefs.getString(KEY_HOST, "") ?: "")

    /** A MagicDNS name or `host:port`. Empty until the user pairs. */
    val host: StateFlow<String> = _host.asStateFlow()

    fun setHost(value: String) {
        val trimmed = value.trim().trim('/')
        prefs.edit { putString(KEY_HOST, trimmed) }
        _host.value = trimmed
    }

    /**
     * The last event id seen on the stream, persisted so a process restart
     * resumes where it left off rather than re-reading the ring buffer from
     * wherever the server happens to be (§3, and the §7 checklist).
     */
    var lastEventId: String?
        get() = prefs.getString(KEY_LAST_EVENT, null)
        set(value) = prefs.edit { putString(KEY_LAST_EVENT, value) }

    /** Forgotten deliberately on a stale resume, so a replay cannot be attempted. */
    fun clearResumePoint() = prefs.edit { remove(KEY_LAST_EVENT) }

    /**
     * The base URL. `http` rather than `https`: the desktop serves plain HTTP
     * over the tailnet, which is why the network security config exists at all.
     * A name typed without a port gets Jarvis's, 4719 - see [BaseUrl].
     */
    fun baseUrl(): String? = BaseUrl.normalise(_host.value)

    private companion object {
        const val PREFS = "jarvis_client"
        const val KEY_HOST = "host"
        const val KEY_LAST_EVENT = "last_event_id"
    }
}
