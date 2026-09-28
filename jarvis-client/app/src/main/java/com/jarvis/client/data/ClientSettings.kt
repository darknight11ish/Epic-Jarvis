package com.jarvis.client.data

import android.content.Context
import android.media.audiofx.AcousticEchoCanceler
import androidx.core.content.edit
import com.jarvis.client.voice.LiveRules
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

    /** Whether this phone has an echo canceller: the interrupt default follows it. */
    val echoCanceller: Boolean by lazy {
        runCatching { AcousticEchoCanceler.isAvailable() }.getOrDefault(false)
    }

    private val _interrupt = MutableStateFlow(
        LiveRules.interruptChoice(
            saved = prefs.getString(KEY_INTERRUPT, null),
            oldBargeIn = if (prefs.contains(KEY_BARGE_IN)) prefs.getBoolean(KEY_BARGE_IN, false) else null,
            oldLive = prefs.getString(KEY_LIVE_INTERRUPT, null),
            echo = runCatching { AcousticEchoCanceler.isAvailable() }.getOrDefault(false),
        ),
    )

    /**
     * "Interrupting Jarvis" on this phone (voice.LiveRules.INTERRUPT):
     * "voice" (talking over Jarvis stops it for the owner's voice), "tap" (by
     * button only; the microphone is closed while Jarvis talks) or "off"
     * (don't interrupt). ONE setting since 2026-09-28 (the owner's answer):
     * it replaced "Interrupt Jarvis while it talks" and "Interrupting Jarvis
     * in Live", and an older choice carries over (the old switch turned off
     * becomes "off", Live's "tap only" becomes "tap"). Never chosen: by voice
     * only where the phone has an echo canceller, as before. This phone's
     * own; it changes only how this phone listens, never what is trusted.
     */
    val interrupt: StateFlow<String> = _interrupt.asStateFlow()

    fun setInterrupt(value: String) {
        val v = LiveRules.interruptChoice(value, null, null, echoCanceller)
        prefs.edit { putString(KEY_INTERRUPT, v) }
        _interrupt.value = v
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


    private val _keepAliveOfferPending = MutableStateFlow(prefs.getBoolean(KEY_KEEP_ALIVE_PENDING, false))

    /**
     * True while the one-time "Background restart" offer waits on Home
     * (phone walk-through C9, 2026-09-27): queued by the first successful
     * pairing ([queueKeepAliveOffer]), gone once the owner taps either of
     * its buttons ([answerKeepAliveOffer]). Two plain yes/no values on this
     * phone, nothing secret.
     */
    val keepAliveOfferPending: StateFlow<Boolean> = _keepAliveOfferPending.asStateFlow()

    /** Queues the offer - once ever, on this phone. A later pairing never queues it again. */
    fun queueKeepAliveOffer() {
        if (prefs.getBoolean(KEY_KEEP_ALIVE_OFFERED, false)) return
        prefs.edit {
            putBoolean(KEY_KEEP_ALIVE_OFFERED, true)
            putBoolean(KEY_KEEP_ALIVE_PENDING, true)
        }
        _keepAliveOfferPending.value = true
    }

    /** The owner answered the offer (either button): it does not come back. */
    fun answerKeepAliveOffer() {
        prefs.edit { putBoolean(KEY_KEEP_ALIVE_PENDING, false) }
        _keepAliveOfferPending.value = false
    }

    private val _watchNotifications = MutableStateFlow(prefs.getBoolean(KEY_WATCH_NOTIFICATIONS, false))

    /**
     * A CACHE of the PC's own smartwatch-notifications switch
     * ([com.jarvis.client.net.WatchNotify]), off by default - the same
     * direction every notification builder already defaults to
     * (`.setLocalOnly(true)`). This is not the setting's only copy: the PC
     * decides it, behind an approval card to turn it on; this is only what
     * the phone last heard, kept so a notification can be built without a
     * network round trip. [JarvisRuntime] writes it whenever it reads or
     * changes the real setting. Unknown or stale reads as OFF, on purpose -
     * staying on the phone leaks nothing, showing on a watch that never
     * asked would.
     */
    val watchNotifications: StateFlow<Boolean> = _watchNotifications.asStateFlow()

    fun setWatchNotifications(value: Boolean) {
        prefs.edit { putBoolean(KEY_WATCH_NOTIFICATIONS, value) }
        _watchNotifications.value = value
    }

    private val _phoneNotifications = MutableStateFlow(prefs.getBoolean(KEY_PHONE_NOTIFICATIONS, false))

    /**
     * A CACHE of the PC's own "read my phone's notifications" switch
     * ([com.jarvis.client.net.PhoneNotifications]), off by default. Not the
     * setting's only copy: the PC decides it, behind an approval card to
     * turn it on; this is only what the phone last heard, kept so
     * [com.jarvis.client.service.PhoneNotificationListenerService] can
     * decide whether to store anything without a network round trip on
     * every notification. [com.jarvis.client.JarvisRuntime] writes it
     * whenever it reads or changes the real setting. Unknown or stale
     * reads as OFF, on purpose - reading nothing leaks nothing.
     */
    val phoneNotifications: StateFlow<Boolean> = _phoneNotifications.asStateFlow()

    fun setPhoneNotifications(value: Boolean) {
        prefs.edit { putBoolean(KEY_PHONE_NOTIFICATIONS, value) }
        _phoneNotifications.value = value
    }

    private val _floatingAvatar = MutableStateFlow(
        FloatingAvatarMode.fromWire(prefs.getString(KEY_FLOATING_AVATAR, null)),
    )

    /**
     * "Floating Jarvis" (Settings -> This app, [FloatingAvatarMode]): off,
     * Bubble or Overlay. Off by default, like every new setting. Saved on
     * this phone only - nothing about it reaches the PC.
     */
    val floatingAvatar: StateFlow<FloatingAvatarMode> = _floatingAvatar.asStateFlow()

    fun setFloatingAvatar(mode: FloatingAvatarMode) {
        prefs.edit { putString(KEY_FLOATING_AVATAR, mode.wire) }
        _floatingAvatar.value = mode
    }

    /**
     * Whether the owner had "Listen on this phone" (Checks) on - set when it
     * is started from the app, cleared when it is stopped on purpose (the
     * switch, the notification's Stop, or the desktop's wake word going
     * off). Read only at boot, to offer ONE "tap to turn it back on"
     * notification ([WakeResume]); it never starts anything by itself.
     */
    var phoneListeningWanted: Boolean
        get() = prefs.getBoolean(KEY_LISTEN_WANTED, false)
        set(value) = prefs.edit { putBoolean(KEY_LISTEN_WANTED, value) }

    private val _quickTiles = MutableStateFlow(
        QuickTiles.slotsFrom { prefs.getString(KEY_TILE_PREFIX + it, null) },
    )

    /**
     * What each Quick Settings tile slot does ([QuickTiles]), always
     * [QuickTiles.SLOTS] long; null is "nothing chosen". On this phone only.
     */
    val quickTiles: StateFlow<List<TileAction?>> = _quickTiles.asStateFlow()

    fun setQuickTile(slot: Int, action: TileAction?) {
        if (slot !in 0 until QuickTiles.SLOTS) return
        prefs.edit {
            if (action == null) remove(KEY_TILE_PREFIX + slot) else putString(KEY_TILE_PREFIX + slot, action.wire)
        }
        _quickTiles.value = _quickTiles.value.toMutableList().also { it[slot] = action }
    }

    private val _homeWidgets = MutableStateFlow(
        (0 until com.jarvis.client.net.JarvisWidgets.SLOTS).map { slot ->
            prefs.getString(KEY_HOME_WIDGET_PREFIX + slot, null)
                ?.takeIf { com.jarvis.client.net.JarvisWidgets.validId(it) }
        },
    )

    /**
     * Which saved widget each home-screen "Jarvis widget" slot shows
     * ([com.jarvis.client.net.JarvisWidgets], docs/JARVIS-API.md section
     * 87), always [com.jarvis.client.net.JarvisWidgets.SLOTS] long; null is
     * "nothing chosen". Only the widget's id is kept here, on this phone -
     * never its words.
     */
    val homeWidgets: StateFlow<List<String?>> = _homeWidgets.asStateFlow()

    fun setHomeWidget(slot: Int, id: String?) {
        if (slot !in 0 until com.jarvis.client.net.JarvisWidgets.SLOTS) return
        val keep = id?.takeIf { com.jarvis.client.net.JarvisWidgets.validId(it) }
        prefs.edit {
            if (keep == null) remove(KEY_HOME_WIDGET_PREFIX + slot) else putString(KEY_HOME_WIDGET_PREFIX + slot, keep)
        }
        _homeWidgets.value = _homeWidgets.value.toMutableList().also { it[slot] = keep }
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
     *
     * Null, too, for an address off the owner's own networks ([OwnNetwork],
     * CLAUDE.md 2026-09-26) - one an older version saved included - so
     * nothing, the token above all, is ever sent there. And null for one on
     * the owner's own networks that Android will not let this app reach in
     * plain http:// (a home-network number, a `.local` name, a raw 100.x
     * mesh number - [PhoneAddress]), which used to be accepted and then fail
     * every request as "the connection dropped". Not silently: [baseProblem]
     * says why, and every request and the event stream show that sentence
     * where they would show any other connection failure.
     */
    fun baseUrl(): String? = BaseUrl.normalise(_host.value)?.takeIf { PhoneAddress.problem(it) == null }

    /** Why the saved address is not used, in one plain sentence, or null. */
    fun baseProblem(): String? = BaseUrl.normalise(_host.value)?.let { PhoneAddress.problem(it) }

    private companion object {
        const val PREFS = "jarvis_client"
        const val KEY_HOST = "host"
        const val KEY_LAST_EVENT = "last_event_id"
        const val KEY_BARGE_IN = "barge_in"
        const val KEY_ONE_MOMENT = "one_moment"
        const val KEY_HEARD_SOUND = "heard_sound"
        const val KEY_LIVE_INTERRUPT = "live_interrupt"
        const val KEY_INTERRUPT = "interrupt"
        const val KEY_WATCH_NOTIFICATIONS = "watch_notifications"
        const val KEY_PHONE_NOTIFICATIONS = "phone_notifications"
        const val KEY_KEEP_ALIVE_OFFERED = "keep_alive_offered"
        const val KEY_KEEP_ALIVE_PENDING = "keep_alive_pending"
        const val KEY_FLOATING_AVATAR = "floating_avatar"
        const val KEY_UPDATE_CHECKS = "update_checks"
        const val KEY_UPDATE_LAST_TRY = "update_last_try_ms"
        const val KEY_UPDATE_NEWER = "update_newer_line"
        const val KEY_UPDATE_PROBLEM = "update_problem"
        const val KEY_LISTEN_WANTED = "phone_listening_wanted"
        /** `quick_tile_0`, `quick_tile_1`, ... - one per tile slot. */
        const val KEY_TILE_PREFIX = "quick_tile_"
        const val KEY_HOME_WIDGET_PREFIX = "home_widget_"
    }
}
