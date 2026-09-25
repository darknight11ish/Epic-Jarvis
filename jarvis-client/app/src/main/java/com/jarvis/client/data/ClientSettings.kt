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

    private val _oneMoment = MutableStateFlow(prefs.getBoolean(KEY_ONE_MOMENT, true))

    /**
     * "Say 'One moment' if I'm kept waiting" on this phone (voice.OneMoment),
     * on by default - the desktop's switch of the same name is its own. The
     * PC's `[voice] one_moment_enabled` can still turn the clip off for both.
     */
    val oneMoment: StateFlow<Boolean> = _oneMoment.asStateFlow()

    fun setOneMoment(value: Boolean) {
        prefs.edit { putBoolean(KEY_ONE_MOMENT, value) }
        _oneMoment.value = value
    }

    private val _heardSound = MutableStateFlow(prefs.getBoolean(KEY_HEARD_SOUND, false))

    /**
     * "Play a short sound when I finish speaking" on this phone
     * (voice.HeardSound), OFF by default (the owner's choice, 2026-09-25),
     * beside [oneMoment]. The sound is
     * made on the phone; nothing about it is on the PC. The desktop's switch
     * of the same name is its own.
     */
    val heardSound: StateFlow<Boolean> = _heardSound.asStateFlow()

    fun setHeardSound(value: Boolean) {
        prefs.edit { putBoolean(KEY_HEARD_SOUND, value) }
        _heardSound.value = value
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

    private val _updateChecks = MutableStateFlow(prefs.getBoolean(KEY_UPDATE_CHECKS, true))

    /**
     * "Check for new versions" (Checks, This app). On by default; off means
     * the phone never asks GitHub at all (`net/UpdateCheck.kt`).
     */
    val updateChecks: StateFlow<Boolean> = _updateChecks.asStateFlow()

    fun setUpdateChecks(on: Boolean) {
        prefs.edit {
            putBoolean(KEY_UPDATE_CHECKS, on)
            // Off forgets what the last check found, so nothing stale is
            // shown if it is turned back on later.
            if (!on) {
                remove(KEY_UPDATE_NEWER)
                remove(KEY_UPDATE_PROBLEM)
            }
        }
        _updateChecks.value = on
    }

    /** When GitHub was last asked (wall clock, so it survives a restart), or null. */
    var updateLastTryMs: Long?
        get() = prefs.getLong(KEY_UPDATE_LAST_TRY, -1L).takeIf { it >= 0 }
        set(value) = prefs.edit { if (value == null) remove(KEY_UPDATE_LAST_TRY) else putLong(KEY_UPDATE_LAST_TRY, value) }

    /** The line for a newer build, as last found, or null. Shown until a check says otherwise. */
    var updateNewerLine: String?
        get() = prefs.getString(KEY_UPDATE_NEWER, null)
        set(value) = prefs.edit { if (value == null) remove(KEY_UPDATE_NEWER) else putString(KEY_UPDATE_NEWER, value) }

    /** Why the last check did not get an answer, for Checks only, or null. */
    var updateProblem: String?
        get() = prefs.getString(KEY_UPDATE_PROBLEM, null)
        set(value) = prefs.edit { if (value == null) remove(KEY_UPDATE_PROBLEM) else putString(KEY_UPDATE_PROBLEM, value) }

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
        const val KEY_ONE_MOMENT = "one_moment"
        const val KEY_HEARD_SOUND = "heard_sound"
        const val KEY_UPDATE_CHECKS = "update_checks"
        const val KEY_UPDATE_LAST_TRY = "update_last_try_ms"
        const val KEY_UPDATE_NEWER = "update_newer_line"
        const val KEY_UPDATE_PROBLEM = "update_problem"
    }
}
