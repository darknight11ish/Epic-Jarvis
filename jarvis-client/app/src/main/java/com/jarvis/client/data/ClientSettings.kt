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

    private val _bargeIn = MutableStateFlow(
        if (prefs.contains(KEY_BARGE_IN)) prefs.getBoolean(KEY_BARGE_IN, false) else null,
    )

    /**
     * "Interrupt Jarvis while it talks" on this phone. Null until the owner
     * chooses: then the default applies - on only where the phone has an
     * echo canceller (`voice.BargeIn.enabled`).
     */
    val bargeIn: StateFlow<Boolean?> = _bargeIn.asStateFlow()

    fun setBargeIn(value: Boolean) {
        prefs.edit { putBoolean(KEY_BARGE_IN, value) }
        _bargeIn.value = value
    }

    private val _security = MutableStateFlow(SecurityRules.fromStored { prefs.getString(it, null) })

    /**
     * The lock and fingerprint settings (Checks, Security). On this phone
     * only: nothing here is ever sent to the PC. Only [setSecurity] writes
     * them, and the caller checks the fingerprint first for any loosening
     * (`SecurityRules.loosens`) - this class does not know how to ask.
     */
    val security: StateFlow<Security> = _security.asStateFlow()

    fun setSecurity(value: Security) {
        prefs.edit { SecurityRules.toStored(value).forEach { (k, v) -> putString(k, v) } }
        _security.value = value
    }

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
        const val KEY_BARGE_IN = "barge_in"
    }
}
