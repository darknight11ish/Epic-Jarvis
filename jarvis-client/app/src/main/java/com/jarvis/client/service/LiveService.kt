package com.jarvis.client.service

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.audiofx.AcousticEchoCanceler
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.view.KeyEvent
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.audio.Wav
import com.jarvis.client.voice.LiveAudioRoute
import com.jarvis.client.voice.LiveExtras
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.MicNow
import com.jarvis.client.voice.MicOwner
import com.jarvis.client.voice.OrtTurnModel
import com.jarvis.client.voice.SmartTurn
import com.jarvis.client.voice.SpeechRun
import com.jarvis.client.voice.TurnEnd
import com.jarvis.client.voice.TurnModel
import com.jarvis.client.voice.TurnSettings
import com.jarvis.client.voice.VoiceFlow
import com.jarvis.client.voice.VoiceSession
import com.jarvis.client.voice.WakeClip
import com.jarvis.client.voice.WakeSpotter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Jarvis Live's microphone on this phone (the owner's decision and answers
 * of 2026-09-28; docs/LIVE-DESIGN.md). Runs only while a Live session is on
 * on THIS phone ([LiveRules.onHere]); the session itself is the PC's.
 *
 * WHAT IT DOES. Every sentence the owner says becomes one clip, cut where the
 * owner pauses (Smart Turn, with up to [LiveRules.TURN_MAX_PAUSE_MS] for an
 * unfinished sentence), and goes to the PC as `source=live`
 * ([VoiceSession.deliverLiveClip]). The PC checks the voice BEFORE any words
 * exist; this phone never turns speech into words. No wake word between
 * turns - that is what Live is.
 *
 * WHAT IT WILL NOT DO:
 *  - listen with the microphone open while [LiveRules.listen] says no: a card
 *    waits (cards are decided by tapping only), the link is stale (rule 4),
 *    Live is muted, the phone is on a call. The recorder is RELEASED then -
 *    not just ignored - so Android's own microphone sign goes off too. Through
 *    a voice pause ("other voices") it stays open: the PC checks those clips
 *    for the owner's voice only, so the owner carries on without a tap.
 *  - keep anything: clips are sent and forgotten; nothing is written to disk.
 *  - run without its notification: it stays on this phone (`setLocalOnly`),
 *    shows fixed words only - never anything said - and has End and Mute.
 *  - restart itself (START_NOT_STICKY), or start at boot.
 *
 * While Jarvis speaks, under "Interrupt by voice" (the default) it listens
 * through Android's echo canceller: another voice LOWERS Jarvis's voice while
 * the PC checks whose it was ([VoiceSession.bargeOnset]); only the owner's
 * stops it, and then the owner's sentence is sent as the next clip. Under
 * "Interrupt by tap only" the microphone is closed while Jarvis talks.
 *
 * A phone or video call pauses Live and it carries on after: read from
 * Android's audio mode (IN_CALL / IN_COMMUNICATION, [LiveRules.onCall]) - no
 * phone-state permission is needed for that. It never undoes the owner's own
 * Mute.
 *
 * THE LIVE EXTRAS (the owner's decisions of 2026-09-28; [LiveExtras]):
 *  - THE HEADSET BUTTON, through a media session that is active only while
 *    Live runs here: a press stops Jarvis talking, a long press turns the
 *    microphone off or on ([onHeadset]). It calls nothing else - it never
 *    approves, denies or starts anything. Android gives the button to the
 *    app that played sound last, so with music playing elsewhere the other
 *    app may get it; and on some phones holding it opens the phone's
 *    assistant instead. The Live screen says so.
 *  - A BLUETOOTH (OR CAR) MICROPHONE is used while one is connected, and its
 *    route's own words name which ([JarvisRuntime.liveMicWords]) - the Live
 *    screen drew that line until 2026-11-02, when the owner removed it. A
 *    car's Bluetooth is a HANDS-FREE device: its microphone only exists in a
 *    CALL, so that route records on `VOICE_COMMUNICATION` with the phone in
 *    `MODE_IN_COMMUNICATION` and the car as the communication device
 *    ([LiveAudioRoute] decides it, [applyRoute] does it). The phone's own
 *    microphone is used where there is no such device, and if Android refuses
 *    the Bluetooth one. The mode and the device are put back in a `finally`
 *    when Live stops, so a car is not left showing a call. No Bluetooth
 *    permission is needed: the device is picked from Android's own audio
 *    device lists (MODIFY_AUDIO_SETTINGS, already held).
 *    WHY IT IS THIS WAY, from the owner's report of 2026-11-02: *"when I am
 *    using jarvis live in my car and my phone is connected to Bluetooth it
 *    acts like it is in a call but jarvis cannot hear me."* The old code made
 *    the car the communication device and then recorded `VOICE_RECOGNITION` in
 *    `MODE_NORMAL` - the car showed a call and the recorder got silence.
 *  - "LIVE ENDED - RESUME" ([showResume]): a notification kept on this phone
 *    for the rest of the PC's 10 minutes after an end that can be resumed.
 */
class LiveService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loop: Job? = null

    @Volatile private var running = false
    private var shownSign: LiveRules.Sign? = null
    private var shownTalking = false

    /** Clips go to the PC one at a time, in order, while the microphone keeps being read. */
    private val sending = Mutex()

    /** The headset button, while Live runs here. */
    private var media: MediaSession? = null
    private val headsetKeys = LiveExtras.HeadsetKeys()

    /**
     * The audio route the phone is currently held in ([LiveAudioRoute]), or
     * null when nothing is applied. Kept so the mode and the communication
     * device can be put back - on every microphone close, not only at the end
     * (a car should not sit showing a call while Live is muted or a card is
     * up), and so a car connecting or disconnecting mid-session is noticed.
     */
    @Volatile private var route: LiveAudioRoute.Route? = null

    /** True once this service made a Bluetooth device the communication device (undone by [restoreRoute]). */
    private var headsetRouted = false

    /** The phone's audio mode before this service held one for a car's microphone, or null. */
    private var heldMode: Int? = null

    /** True while the old `startBluetoothSco()` was the way the call link came up (undone by [restoreRoute]). */
    private var scoLegacy = false

    /** A Bluetooth device type Android would not give a microphone through this session, or null. */
    private var refusedType: Int? = null

    /**
     * True when the call link had to be brought up again under an open
     * recorder - the Speaker's own call mode clears the communication device
     * when a reply ends. The recorder is then reopened so it is bound to the
     * new link (reported as "not proven on hardware" until a car says so).
     */
    private var routeDropped = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        ensureChannel(this)
        clearResume(this)
        if (!goForeground(LiveRules.sign(JarvisRuntime.liveStatus.value))) {
            stopSelf()
            return
        }
        openHeadsetButton()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_END -> {
                running = false
                // In the runtime's own scope: this service's scope is
                // cancelled by stopSelf below, and the End could be lost with
                // it (the review's B1).
                JarvisRuntime.liveEndNow("owner")
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_MUTE -> scope.launch { JarvisRuntime.liveMute(true) }
            ACTION_UNMUTE -> scope.launch { JarvisRuntime.liveMute(false) }
            ACTION_STOP_TALKING -> JarvisRuntime.voice.stopSpeaking()
        }
        if (loop == null) {
            running = true
            loop = scope.launch {
                try {
                    listen()
                } catch (t: Throwable) {
                    Log.w(TAG, "Jarvis Live listening stopped", t)
                    // WHICH failure it was (the owner's Pixel 9, 2026-10-17):
                    // a permission refusal or a foreground-service refusal has
                    // its own line and its own reason for the PC - it must
                    // never reach the end screen as "the owner ended it".
                    val stop = classifyStop(t) ?: LiveRules.LiveStop.MIC_STOPPED
                    refusedStop = stop
                    JarvisRuntime.liveNotice(LiveRules.stopWords(stop))
                } finally {
                    running = false
                    stopSelf()
                }
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        listening.value = false
        loop?.cancel()
        scope.cancel()
        runCatching { JarvisRuntime.voice.speaker.endVoiceCall() }
        runCatching { media?.release() }
        media = null
        // The phone must not be left in a car's call mode if this service goes
        // away before `listen`'s own finally has run (2026-11-02).
        runCatching { stopRoute() }
        JarvisRuntime.liveMicWords(null)
        super.onDestroy()
    }

    // ------------------------------------------------------ headset button

    /**
     * A media session, active only while Live runs here, so a headset's one
     * button reaches [onHeadset]. It plays nothing and shows no media card
     * (no media-style notification).
     */
    private fun openHeadsetButton() {
        media = runCatching {
            MediaSession(this, "JarvisLive").apply {
                setCallback(object : MediaSession.Callback() {
                    override fun onMediaButtonEvent(mediaButtonIntent: Intent): Boolean {
                        val e = mediaButtonIntent.getParcelableExtra(Intent.EXTRA_KEY_EVENT, KeyEvent::class.java)
                            ?: return false
                        if (e.keyCode !in LiveExtras.BUTTON_KEYS) return false
                        onHeadset(e.action, e.keyCode, e.repeatCount, e.downTime, e.eventTime)
                        return true
                    }
                })
                setPlaybackState(
                    PlaybackState.Builder()
                        .setActions(PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE)
                        .setState(PlaybackState.STATE_PLAYING, 0L, 1f)
                        .build(),
                )
                isActive = true
            }
        }.onFailure { Log.w(TAG, "no media session for the headset button", it) }.getOrNull()
    }

    /**
     * The headset button: a press stops Jarvis talking (unless "Don't
     * interrupt" is chosen), a long press turns the microphone off or on.
     * Nothing else - never an approval, a denial or a start.
     */
    private fun onHeadset(action: Int, keyCode: Int, repeat: Int, downTime: Long, eventTime: Long) {
        when (headsetKeys.onKey(action, keyCode, repeat, downTime, eventTime)) {
            LiveExtras.Press.STOP_TALKING ->
                if (JarvisRuntime.settings.interrupt.value != LiveRules.INTERRUPT_OFF) {
                    JarvisRuntime.voice.stopSpeaking()
                }
            LiveExtras.Press.MIC_TOGGLE -> {
                val muted = (JarvisRuntime.liveStatus.value?.get("muted") as? kotlinx.serialization.json.JsonPrimitive)
                    ?.content == "true"
                scope.launch { JarvisRuntime.liveMute(!muted) }
            }
            LiveExtras.Press.NONE -> Unit
        }
    }

    // --------------------------------------------------- the microphone route

    /**
     * What Android can see right now, as the pure decision wants it
     * ([LiveAudioRoute.Inputs]). Every call is wrapped: a device list is not
     * worth stopping Live for, and an empty one simply means the phone's own
     * microphone.
     */
    private fun routeInputs(speaking: Boolean): LiveAudioRoute.Inputs {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        val inputs = runCatching { am?.getDevices(AudioManager.GET_DEVICES_INPUTS)?.map { it.type }.orEmpty() }
            .getOrDefault(emptyList())
        val outputs = runCatching { am?.getDevices(AudioManager.GET_DEVICES_OUTPUTS)?.map { it.type }.orEmpty() }
            .getOrDefault(emptyList())
        val communication = runCatching {
            am?.availableCommunicationDevices?.map {
                LiveExtras.Mic(it.type, it.productName?.toString().orEmpty())
            }.orEmpty()
        }.getOrDefault(emptyList())
        return LiveAudioRoute.Inputs(
            inputTypes = inputs,
            outputTypes = outputs,
            communication = communication,
            speaking = speaking,
            // No microphone setting on this phone yet (checked 2026-11-02:
            // none in Settings, and none in the F.A.Q.). AUTO is therefore the
            // only value in use. LiveAudioRoute.MicChoice.PHONE - the car's
            // microphone is no good, use this phone's - is already decided and
            // tested; wiring a row to it is the only change that adds it.
            choice = LiveAudioRoute.MicChoice.AUTO,
        )
    }

    /**
     * The Android side of [LiveAudioRoute]: hold the audio mode and make the
     * communication device the route asks for, so a car's hands-free
     * microphone actually exists. Then wait, briefly, for the call link to
     * really come up - `setCommunicationDevice` is not instant, and a recorder
     * opened before the link is up gets silence, which is the bug this fixes.
     *
     * False when Android refused or the link never appeared: the caller then
     * records from the phone's own microphone instead
     * ([LiveAudioRoute.fallback]), because a route that yields silence is
     * worse than a phone microphone that works.
     */
    @Suppress("DEPRECATION") // startBluetoothSco: the old way, kept as the fallback below
    private suspend fun applyRoute(route: LiveAudioRoute.Route): Boolean {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return route.communicationType == null
        if (route.holdMode != null) {
            if (heldMode == null) heldMode = am.mode
            if (am.mode != route.holdMode) {
                runCatching { am.mode = route.holdMode }
            }
        }
        val type = route.communicationType ?: return true
        val device = runCatching { am.availableCommunicationDevices.firstOrNull { it.type == type } }.getOrNull()
            ?: return false
        if (am.communicationDevice?.id != device.id) {
            if (runCatching { am.setCommunicationDevice(device) }.getOrDefault(false)) {
                headsetRouted = true
            } else if (route.needsScoLink) {
                // The modern call was refused: the old way to bring the SCO
                // link up, which is all some cars/phones still answer to.
                val started = runCatching { am.startBluetoothSco() }.isSuccess
                if (!started) return false
                scoLegacy = true
                headsetRouted = true
            } else {
                return false
            }
        } else {
            headsetRouted = true
        }
        repeat(LINK_WAIT_STEPS) {
            if (callLinkUp(route)) return true
            delay(LINK_WAIT_STEP_MS)
        }
        return callLinkUp(route)
    }

    /** Is the call link this route needs actually up? Always true for a route that needs none. */
    @Suppress("DEPRECATION") // isBluetoothScoOn: reads the old link the fallback started
    private fun callLinkUp(route: LiveAudioRoute.Route): Boolean {
        val type = route.communicationType ?: return true
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return false
        if (runCatching { am.communicationDevice?.type }.getOrNull() == type) return true
        return scoLegacy && runCatching { am.isBluetoothScoOn }.getOrDefault(false)
    }

    /**
     * Put the phone back the way it was: let the communication device go, stop
     * the old SCO link if that is what came up, and restore the audio mode Live
     * held ([LiveAudioRoute.undo]). Safe to call more than once and safe to
     * call for a route that changed nothing.
     */
    @Suppress("DEPRECATION") // stopBluetoothSco: the other half of the fallback
    private fun restoreRoute(applied: LiveAudioRoute.Route) {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
        val undo = LiveAudioRoute.undo(applied, heldMode ?: am.mode)
        if (headsetRouted) runCatching { am.clearCommunicationDevice() }
        headsetRouted = false
        if (scoLegacy) {
            runCatching { am.stopBluetoothSco() }
            scoLegacy = false
        }
        undo.mode?.let { runCatching { am.mode = it } }
        heldMode = null
    }

    /** Let go of whatever route is applied - the microphone is closing. */
    private fun stopRoute() {
        route?.let { applied -> runCatching { restoreRoute(applied) } }
        route = null
    }

    // ------------------------------------------------------------- listening

    private suspend fun listen() {
        val voice = JarvisRuntime.voice
        if (!hasMicPermission()) {
            // The microphone permission is off: its own reason, never the
            // owner's End (2026-10-17).
            refusedStop = LiveRules.LiveStop.MIC_PERMISSION
            JarvisRuntime.liveNotice(LiveRules.stopWords(LiveRules.LiveStop.MIC_PERMISSION))
            JarvisRuntime.liveStop(LiveRules.whyOf(LiveRules.LiveStop.MIC_PERMISSION))
            return
        }
        // Smart Turn: optional. Without it a sentence ends after the fixed pause.
        val turnModel: TurnModel? = runCatching {
            OrtTurnModel.load(assets.open("$TURN_DIR/${OrtTurnModel.FILE}").use { it.readBytes() })
        }.onFailure { Log.w(TAG, "Smart Turn did not load; using the fixed pause", it) }.getOrNull()
        var rec: AudioRecord? = null
        var openOn: LiveAudioRoute.Route? = null
        var canceller: AcousticEchoCanceler? = null
        var inVoiceCall = false
        val ring = WakeClip.Ring((PREROLL_SECONDS * RATE).toInt())
        // [keepRing]: only the audio source changes (Jarvis stopped talking),
        // so the half-second before is the owner's sentence going on - kept
        // (the review's bug 1). A pause that closes the microphone drops it.
        fun close(keepRing: Boolean = false) {
            runCatching { rec?.stop() }
            runCatching { rec?.release() }
            rec = null
            MicNow.closed(MicOwner.Use.LIVE)
            runCatching { canceller?.release() }
            canceller = null
            openOn = null
            if (!keepRing) ring.clear()
        }
        try {
            while (running) {
                val status = JarvisRuntime.liveStatus.value
                if (!LiveRules.onHere(status)) break
                // A call pauses Live (the audio mode; neither Jarvis's own
                // echo-cancelling mode nor the call mode Live itself holds for
                // a car's microphone is a call - `ownMicCall`), and ends the
                // pause after.
                JarvisRuntime.liveCall(
                    LiveRules.onCall(audioMode(), voice.speaker.voiceCall, ownMicCall = route?.callMode == true),
                )
                val speaking = voice.phase.value == VoiceSession.Phase.SPEAKING || voice.lineSpeaking
                val may = LiveRules.listen(
                    status,
                    stale = JarvisRuntime.stale.value,
                    // A card of THIS session closes the microphone at once -
                    // the service used to leave that to the PC's pause, a
                    // second later (the review's bug 3).
                    cardShown = JarvisRuntime.liveCardHolds(),
                    answering = speaking,
                    interrupt = JarvisRuntime.settings.interrupt.value,
                )
                refreshNotification(status)
                // The microphone is shared (voice/MicOwner.kt): call recording
                // outranks Live, and while it is armed or recording Live keeps
                // its recorder CLOSED - paused, not killed, because Android
                // 14+ refuses to start a microphone service from the background
                // and a stopped Live could not come back.
                if (!may.mic || !MicNow.mayOpen(MicOwner.Use.LIVE).allowed) {
                    // Closed, not ignored: Android's microphone sign goes off,
                    // and so does the car's call mode - Live must not leave a
                    // car showing a call while it is muted or a card waits.
                    //
                    // The same question is what pauses Live while the hands-free
                    // answer window (2026-11-04) or the talk button holds the
                    // microphone: closed here rather than merely skipped, and
                    // reopened by the next pass once the microphone is free.
                    close()
                    stopRoute()
                    delay(IDLE_MS)
                    continue
                }
                if (speaking && !inVoiceCall) {
                    // The reply is playing: as a voice call, so the echo
                    // canceller can take Jarvis's own voice back out.
                    voice.speaker.beginVoiceCall()
                    inVoiceCall = true
                } else if (!speaking && inVoiceCall) {
                    voice.speaker.endVoiceCall()
                    inVoiceCall = false
                }
                // THE ROUTE, decided again every time round the loop
                // (LiveAudioRoute): a car connected or unplugged mid-session is
                // noticed here, and a car's hands-free microphone is only
                // reachable in the call configuration this puts the phone in.
                val applied = routeFor(speaking)
                if (rec == null || applied != openOn || routeDropped) {
                    routeDropped = false
                    close(keepRing = rec != null)
                    val opened = openRecorder(applied)
                    if (opened == null) {
                        JarvisRuntime.liveNotice("No microphone available right now.")
                        delay(IDLE_MS * 5)
                        continue
                    }
                    // The echo canceller goes on the voice-call path - used
                    // while Jarvis talks, and on a car's microphone all the
                    // time (that route records on the call path anyway).
                    if (applied.source == LiveAudioRoute.SRC_VOICE_COMMUNICATION) {
                        canceller = runCatching {
                            if (AcousticEchoCanceler.isAvailable()) {
                                AcousticEchoCanceler.create(opened.audioSessionId)?.also { it.enabled = true }
                            } else {
                                null
                            }
                        }.getOrNull()
                    }
                    opened.startRecording()
                    MicNow.opened(MicOwner.Use.LIVE)
                    rec = opened
                    openOn = applied
                    JarvisRuntime.liveMicWords(applied.words)
                }
                val clip = window(requireNotNull(rec), ring, turnModel, overReply = speaking) ?: continue
                // Not waited for: the recorder's buffer holds well under a
                // second, and the owner may already be saying the next thing
                // (a second thought joins the question - LiveRules.fold).
                scope.launch { sending.withLock { send(clip) } }
            }
        } finally {
            close()
            stopRoute()
            if (inVoiceCall) voice.speaker.endVoiceCall()
            turnModel?.close()
        }
    }

    /**
     * The route to record on for this moment, applied to the phone: the pure
     * decision ([LiveAudioRoute.decide]) plus the one thing only Android can
     * answer - whether it accepted it. When the car's microphone cannot be
     * made available the phone's own is used, and the route says the
     * Bluetooth one could not be used ([LiveAudioRoute.fallback]); the Live
     * screen drew that line until 2026-11-02. Never leaves the phone in a
     * route that was not applied.
     */
    private suspend fun routeFor(speaking: Boolean): LiveAudioRoute.Route {
        var inputs = routeInputs(speaking)
        // A Bluetooth microphone Android refused is not asked for again and
        // again: each attempt takes most of a second and flashes the car's
        // call mode. The phone's own microphone is used until that device
        // disconnects and comes back (a fresh Live session tries again).
        refusedType?.let { type ->
            if (inputs.communication.none { it.type == type }) refusedType = null
            else inputs = inputs.copy(choice = LiveAudioRoute.MicChoice.PHONE)
        }
        val want = LiveAudioRoute.decide(inputs)
        if (want == route) {
            // The same route as last time, and it may need putting back: the
            // Speaker's own call mode lets the communication device go when a
            // reply ends (Speaker.enterCall's undo).
            if (want.communicationType != null && !callLinkUp(want)) {
                routeDropped = true
                if (!applyRoute(want) || !callLinkUp(want)) route = fellBackTo(inputs, want.communicationType)
            }
            return requireNotNull(route)
        }
        stopRoute()
        route = if (applyRoute(want) && callLinkUp(want)) {
            want
        } else {
            fellBackTo(inputs, want.communicationType)
        }
        return requireNotNull(route)
    }

    /**
     * Record from the phone's own microphone instead: undo what was tried,
     * apply the fallback (whose own words name it), and remember not to ask
     * for that device again this session.
     */
    private suspend fun fellBackTo(inputs: LiveAudioRoute.Inputs, refused: Int?): LiveAudioRoute.Route {
        stopRoute()
        if (refused != null) refusedType = refused
        val fallback = LiveAudioRoute.fallback(inputs)
        applyRoute(fallback)
        return fallback
    }

    /**
     * One stretch of listening: until the owner has spoken and paused, or
     * [WINDOW_GRACE_SECONDS] of nothing, or Live says the microphone must
     * close. The clip, or null when nothing was said (or it is not to be
     * sent). [overReply]: Jarvis is speaking - the start of any speech lowers
     * its voice and asks the PC whose it was; the clip goes only if that
     * stopped the reply (it was the owner).
     */
    private suspend fun window(rec: AudioRecord, ring: WakeClip.Ring, turnModel: TurnModel?, overReply: Boolean): ShortArray? {
        val voice = JarvisRuntime.voice
        val settings = voice.status.value.turn
        val turn = if (turnModel != null && TurnSettings.useModel(settings, true)) {
            SmartTurn(turnModel, TurnSettings.threshold(settings))
        } else {
            null
        }
        val end = TurnEnd(
            graceSeconds = WINDOW_GRACE_SECONDS,
            askAfterSeconds = LiveRules.TURN_ASK_AFTER_MS / 1000f,
            maxPauseSeconds = if (turn != null) LiveRules.TURN_MAX_PAUSE_MS / 1000f else TurnEnd.PAUSE_WITHOUT_MODEL,
            maxSeconds = MAX_SECONDS,
            useModel = turn != null,
        )
        val prefix = ring.snapshot()
        val maxSamples = (MAX_SECONDS * RATE).toInt() + prefix.size
        var out = prefix.copyOf(maxOf(prefix.size + RATE * 2, RATE * 4))
        var count = prefix.size
        val buf = ShortArray(WakeSpotter.CHUNK)
        val stepMs = WakeSpotter.CHUNK * 1000L / RATE
        val speech = SpeechRun()
        var judging: Long? = null
        var heardStart = 0
        var checks = 0
        while (running && count < maxSamples) {
            // Every few steps: may the microphone still be open?
            if (++checks % CHECK_EVERY_STEPS == 0 && !stillOpen(overReply)) return null
            // A negative read is a dead recorder, not "nothing was said":
            // returning null here made `listen`'s `?: continue` re-read the
            // same dead recorder with no delay for ever, at full CPU and still
            // holding the microphone (2026-10-24). Thrown, it reaches the catch
            // in onStartCommand, which says the microphone stopped, and
            // `listen`'s own finally closes the recorder.
            if (!readFully(rec, buf)) throw MicStopped()
            ring.push(buf)
            if (count + buf.size > out.size) out = out.copyOf(minOf(maxSamples, out.size * 2))
            val take = minOf(buf.size, out.size - count)
            System.arraycopy(buf, 0, out, count, take)
            count += take
            val level = Wav.rms(buf, buf.size)
            if (overReply) {
                val now = SystemClock.elapsedRealtime()
                when (speech.step(now, level, stepMs)) {
                    SpeechRun.Event.ONSET -> voice.bargeOnset()?.let { id ->
                        judging = id
                        val since = now - (speech.startedAt ?: now) + VoiceFlow.PREROLL_MS
                        heardStart = maxOf(0, count - (since * RATE / 1000L).toInt())
                    }
                    SpeechRun.Event.CLIP_DUE -> judging?.let { id ->
                        val wav = Wav.encode(out.copyOfRange(heardStart, count))
                        // Not waited for: this loop must keep reading.
                        scope.launch { voice.judgeBargeIn(id, wav) }
                        judging = null
                    }
                    SpeechRun.Event.NONE -> Unit
                }
            }
            val step = end.push(level, stepMs / 1000f)
            if (step == TurnEnd.Step.END) break
            if (step == TurnEnd.Step.ASK && turn != null) {
                val finished = runCatching { turn.complete(out, count) }.getOrDefault(false)
                if (end.answer(finished) == TurnEnd.Step.END) break
            }
        }
        if (!end.heardSpeech) return null
        // Over a reply: sent only if it stopped the reply (the PC said the
        // voice was the owner's). Anyone else's words go nowhere.
        if (overReply && !voice.replyStopped()) return null
        return out.copyOf(count)
    }

    /**
     * May the microphone stay open for this window? (Rechecked while it
     * listens.) A window that began over a reply the owner's voice has just
     * stopped carries on: that is the owner's next sentence, and it goes to
     * the PC (the review's bug 1 - it used to be thrown away as soon as
     * Jarvis went quiet).
     */
    private fun stillOpen(overReply: Boolean): Boolean {
        val voice = JarvisRuntime.voice
        val speaking = voice.phase.value == VoiceSession.Phase.SPEAKING || voice.lineSpeaking
        if (speaking != overReply && !(overReply && voice.replyStopped())) return false
        val may = LiveRules.listen(
            JarvisRuntime.liveStatus.value,
            stale = JarvisRuntime.stale.value,
            cardShown = JarvisRuntime.liveCardHolds(),
            answering = speaking,
            interrupt = JarvisRuntime.settings.interrupt.value,
        )
        return may.mic && !MicNow.callRecordingHolds() && !LiveRules.onCall(
            audioMode(),
            voice.speaker.voiceCall,
            ownMicCall = route?.callMode == true,
        ) &&
            // Hands-free (2026-11-04): the answer window has the microphone,
            // and this window closes for it. It is the same question the two
            // conditions above answer - "may the microphone stay open" - and it
            // is asked of the ONE ledger (voice/MicOwner.kt) rather than of
            // another feature's state, so every part that records obeys one
            // rule. Live reopens on the next pass once the window is over.
            MicNow.mayOpen(MicOwner.Use.LIVE).allowed
    }

    private suspend fun send(clip: ShortArray) {
        val waited = VoiceFlow.trailingQuietMs(clip) ?: return
        val heard = JarvisRuntime.voice.deliverLiveClip(Wav.encode(clip), waited) ?: return
        JarvisRuntime.liveHeard(heard)
    }

    private fun audioMode(): Int =
        (getSystemService(Context.AUDIO_SERVICE) as? AudioManager)?.mode ?: AudioManager.MODE_NORMAL

    /**
     * The microphone stopped answering.
     *
     * `AudioRecord.read` reports a dead track with a negative code rather than
     * an exception (see [readFully]). Returning null for it was indistinguishable
     * from "nothing was said", so the listen loop re-read the same dead recorder
     * with no delay for ever, at full CPU, still holding it open (2026-10-24).
     * Thrown, it reaches `onStartCommand`'s catch, which classifies an unknown
     * exception as MIC_STOPPED and tells the owner; `listen`'s own `finally`
     * closes the recorder.
     */
    private class MicStopped : IllegalStateException("the microphone stopped answering")

    private fun readFully(rec: AudioRecord, buf: ShortArray): Boolean {
        var got = 0
        while (got < buf.size) {
            val n = rec.read(buf, got, buf.size - got)
            if (n <= 0) return false
            got += n
        }
        return true
    }

    /**
     * The recorder, opened as [route] says: `VOICE_COMMUNICATION` on the call
     * path for a car's or headset's hands-free microphone, `VOICE_RECOGNITION`
     * for the phone's own (the un-beautified path the voice print was trained
     * on), and the route's device preferred where Android lists it as an
     * input.
     */
    @SuppressLint("MissingPermission") // hasMicPermission() is checked before this is reached
    private fun openRecorder(route: LiveAudioRoute.Route): AudioRecord? {
        if (!hasMicPermission()) return null
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val rec = runCatching {
            AudioRecord(
                route.source,
                RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(min, WakeSpotter.CHUNK * 2) * 4,
            )
        }.getOrNull() ?: return null
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            return null
        }
        // The car's microphone by name where Android lists it as an input. On
        // most phones the communication device already routes it and this only
        // makes it certain; a refusal here is NOT fatal (the call route still
        // records from the communication device's microphone), so the recorder
        // is kept either way.
        route.expectedInputType?.let { type ->
            val input = runCatching {
                (getSystemService(Context.AUDIO_SERVICE) as? AudioManager)
                    ?.getDevices(AudioManager.GET_DEVICES_INPUTS)
                    ?.firstOrNull { it.type == type }
            }.getOrNull()
            if (input != null) runCatching { rec.setPreferredDevice(input) }
        }
        return rec
    }

    private fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    // ---------------------------------------------------------- notification

    private fun refreshNotification(status: kotlinx.serialization.json.JsonObject?) {
        val sign = LiveRules.sign(
            status,
            stale = JarvisRuntime.stale.value,
            cardShown = JarvisRuntime.liveCardHolds(),
        )
        val talking = JarvisRuntime.voice.phase.value == VoiceSession.Phase.SPEAKING &&
            JarvisRuntime.settings.interrupt.value != LiveRules.INTERRUPT_OFF
        if (sign == shownSign && talking == shownTalking) return
        shownTalking = talking
        goForeground(sign)
    }

    /**
     * The ongoing notification: fixed words only (the sign), never anything
     * said. It stays on this phone - never bridged to a watch - and has End
     * Live (never held), Mic off / Mic on / Listen anyway, and Stop talking
     * while Jarvis talks (unless "Don't interrupt" is chosen).
     */
    private fun goForeground(sign: LiveRules.Sign): Boolean {
        shownSign = sign
        val end = PendingIntent.getService(
            this, 11,
            Intent(this, LiveService::class.java).setAction(ACTION_END),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val muted = sign.mute.isNotEmpty() && sign.mute != LiveRules.MIC_OFF
        val stopTalking = PendingIntent.getService(
            this, 14,
            Intent(this, LiveService::class.java).setAction(ACTION_STOP_TALKING),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val mute = PendingIntent.getService(
            this, 12,
            Intent(this, LiveService::class.java).setAction(if (muted) ACTION_UNMUTE else ACTION_MUTE),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 13,
            Intent(this, MainActivity::class.java)
                .setAction(MainActivity.ACTION_OPEN_LIVE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        // P-7 (privacy audit 2026-10-27): every other notifier on this phone
        // redacts while notification content must be hidden; this one did not.
        // The session's own state line (minutes left, Mic off/Mic on, the PC's
        // `muted_words`) is what a stranger would read on a lock screen, so the
        // shared rule decides it - `SecurityRules.notificationsLocked`, the same
        // one ApprovalNotifier and the schedule notifier use.
        val locked = liveNoticeLocked(this)
        val words = LiveRules.noticeWords(
            locked = locked,
            appName = getString(R.string.app_name),
            title = sign.title.ifEmpty { LiveRules.TITLE },
            text = sign.detail.ifEmpty { LiveRules.SEEN.getValue("end_hint") },
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(words[0])
            .setContentText(words[1])
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            // PUBLIC is kept, and it is safe BECAUSE of the words above: while
            // the lock is on there is nothing in this notice but the app's own
            // name and one fixed line, which is exactly what
            // `ScheduleNotifier.locked` draws. The buttons stay too - a
            // foreground service must offer its own stop, and "End Live" is a
            // control, not a fact about the owner.
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            .addAction(0, LiveRules.END_LIVE, end)
            .addAction(0, sign.mute.ifEmpty { LiveRules.MIC_OFF }, mute)
            .apply { if (shownTalking) addAction(0, LiveRules.STOP_TALKING, stopTalking) }
            .build()
        return try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
            listening.value = true
            true
        } catch (e: Exception) {
            // Android 14+ refuses a microphone service started from the
            // background, or the permission is off. WHICH one is recorded
            // (2026-10-17) so the runtime can tell the PC the truth and the
            // end screen never blames the owner. Said, never retried.
            Log.w(TAG, "startForeground refused", e)
            val stop = classifyStop(e) ?: LiveRules.LiveStop.FGS_REFUSED
            refusedStop = stop
            JarvisRuntime.liveNotice(LiveRules.stopWords(stop))
            running = false
            listening.value = false
            false
        }
    }

    companion object {
        private const val TAG = "JarvisLive"
        const val CHANNEL_ID = "jarvis_live"
        private const val NOTIFICATION_ID = NotificationIds.LIVE
        const val ACTION_END = "com.jarvis.client.LIVE_END"
        const val ACTION_MUTE = "com.jarvis.client.LIVE_MUTE"
        const val ACTION_UNMUTE = "com.jarvis.client.LIVE_UNMUTE"
        const val ACTION_STOP_TALKING = "com.jarvis.client.LIVE_STOP_TALKING"

        /**
         * Whether this phone's notification CONTENT must be redacted right now
         * - App lock, "Hide memory lists and chat history", or a phone whose own
         * lock screen is not secure (M12). THE SHARED RULE, not a second one:
         * `SecurityRules.notificationsLocked`, the same call ApprovalNotifier,
         * the schedule notifier, the chat notifier and the handoff notifier
         * make. Read here rather than passed in because both Live notices are
         * rebuilt from the service's own state.
         *
         * P-7 of the 2026-10-27 privacy audit: these two notices were the only
         * ones left PUBLIC while the lock was on.
         */
        private fun liveNoticeLocked(context: Context): Boolean =
            com.jarvis.client.data.SecurityRules.notificationsLocked(
                JarvisRuntime.settings.security.value,
                com.jarvis.client.platform.DeviceSecure.isSecure(context),
            )

        /** The "Live is on your PC - move it here?" heads-up channel. */
        const val OFFER_CHANNEL_ID = "jarvis_live_offer"
        private const val OFFER_ID = NotificationIds.LIVE_OFFER

        /**
         * Why the microphone service last refused to start or stopped, as the
         * phone could tell - null when the last start was fine. Set where the
         * failure is caught ([goForeground], the listen loop, [start]); read by
         * `JarvisRuntime.liveStop` so the PC gets `fgs_refused` /
         * `mic_permission` / `mic_stopped` instead of a default "owner"
         * (2026-10-17). The DECISION itself is pure:
         * [LiveRules.stopForClasses], run by the JVM tests.
         */
        @Volatile var refusedStop: LiveRules.LiveStop? = null

        /** The throwable's class and its superclasses, as names - what the pure decision reads. */
        private fun classPath(t: Throwable): List<String> {
            val names = mutableListOf<String>()
            var c: Class<*>? = t.javaClass
            while (c != null) {
                names += c.name
                c = c.superclass
            }
            return names
        }

        /** Which stop a caught failure is, or null when it does not say. */
        fun classifyStop(t: Throwable?): LiveRules.LiveStop? =
            t?.let { LiveRules.stopForClasses(classPath(it)) }

        /**
         * True while the service holds the microphone as a foreground
         * service - Android said yes. The runtime waits for it before saying
         * "I'm listening." (the review's B7).
         */
        val listening = kotlinx.coroutines.flow.MutableStateFlow(false)
        private const val TURN_DIR = "turn"
        private const val RATE = WakeSpotter.SAMPLE_RATE

        /** Audio kept from before a window, so a sentence that began at its edge is whole. */
        private const val PREROLL_SECONDS = 0.5f

        /** A window with no speech ends after this, and the rules are read again. */
        private const val WINDOW_GRACE_SECONDS = 1.0f

        /** The longest sentence, under the PC's own 30 s. */
        private const val MAX_SECONDS = 25f

        /** While the microphone is closed, how often to look again. */
        private const val IDLE_MS = 200L

        /**
         * How long to wait for a car's call link to come up after asking for
         * it: `setCommunicationDevice` (and the old `startBluetoothSco`) answer
         * before the SCO link exists, and a recorder opened too early gets
         * silence. Twelve 50 ms looks are about as long as a car takes, and
         * short enough that a phone whose Bluetooth refuses is not stuck
         * waiting (2026-11-02).
         */
        private const val LINK_WAIT_STEPS = 12
        private const val LINK_WAIT_STEP_MS = 50L

        /** How often (in 80 ms steps) a window checks it may stay open: about every 0.4 s. */
        private const val CHECK_EVERY_STEPS = 5

        /** Call from the app's own screen, or from a reply the app received in front. False when Android refused. */
        fun start(context: Context): Boolean {
            refusedStop = null            // a fresh attempt: forget the last refusal
            return runCatching {
                ContextCompat.startForegroundService(context, Intent(context, LiveService::class.java))
            }.onFailure { t ->
                Log.w(TAG, "could not start", t)
                // Which refusal it was: the runtime reports THIS reason to the
                // PC (2026-10-17), never a default "owner".
                val stop = classifyStop(t) ?: LiveRules.LiveStop.FGS_REFUSED
                refusedStop = stop
                JarvisRuntime.liveNotice(LiveRules.stopWords(stop))
            }.isSuccess
        }

        /**
         * "Hey Jarvis" to this phone while Live runs on the PC: a heads-up,
         * kept on this phone, that opens the Live screen with "Move it here"
         * on it. Fixed words only; gone after 30 seconds.
         */
        fun showMoveOffer(context: Context, device: String) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED) return
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            runCatching {
                manager.createNotificationChannel(
                    NotificationChannel(OFFER_CHANNEL_ID, "Jarvis Live offers", NotificationManager.IMPORTANCE_HIGH)
                        .apply {
                            description = "\"Live is on your PC - move it here?\" when you say \"Hey Jarvis\" to " +
                                "this phone while Jarvis Live is on your PC."
                            setShowBadge(false)
                        },
                )
                val open = PendingIntent.getActivity(
                    context, 15,
                    Intent(context, MainActivity::class.java)
                        .setAction(MainActivity.ACTION_OPEN_LIVE)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                val n = NotificationCompat.Builder(context, OFFER_CHANNEL_ID)
                    .setLocalOnly(true)
                    .setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(LiveRules.moveWords(device))
                    .setContentText("Open Jarvis Live to move it to this phone.")
                    .setAutoCancel(true)
                    .setTimeoutAfter(30_000L)
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .setCategory(NotificationCompat.CATEGORY_STATUS)
                    .setContentIntent(open)
                    .addAction(0, "Move it here", open)
                    .build()
                manager.notify(OFFER_ID, n)
            }
        }

        /** "Live ended - Resume" (the Jarvis Live extras): its channel and id. */
        const val RESUME_CHANNEL_ID = "jarvis_live_resume"
        private const val RESUME_ID = NotificationIds.LIVE_RESUME

        /**
         * "Jarvis Live ended" with Resume Live, for [forMs] (the rest of the
         * PC's 10 minutes), after an end here that can be resumed. Kept on
         * this phone; fixed words only (why it ended, from the PC's fixed
         * list). Resume opens the app, which starts Live again in the same
         * chat - after App lock, and held on a stale link like the button.
         */
        fun showResume(context: Context, endedWords: String, forMs: Long) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED) return
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            runCatching {
                manager.createNotificationChannel(
                    NotificationChannel(RESUME_CHANNEL_ID, "Jarvis Live: Resume", NotificationManager.IMPORTANCE_DEFAULT)
                        .apply {
                            description = "\"Live ended - Resume\" for ten minutes after Jarvis Live ended by " +
                                "itself (it was quiet, or the time was up)."
                            setShowBadge(false)
                            setSound(null, null)
                        },
                )
                val resume = PendingIntent.getActivity(
                    context, 16,
                    Intent(context, MainActivity::class.java)
                        .setAction(MainActivity.ACTION_RESUME_LIVE)
                        .putExtra(
                            com.jarvis.client.InternalLaunch.EXTRA_PROOF,
                            com.jarvis.client.InternalLaunch.token(context),
                        )
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                // P-7 (privacy audit 2026-10-27): the same rule as the
                // foreground notice. "Live ended - Resume" says a session ran
                // on this phone and names the words it ended on; with the lock
                // on it says the fixed line only, which is what every other
                // Jarvis notifier does.
                val words = LiveRules.noticeWords(
                    locked = liveNoticeLocked(context),
                    appName = context.getString(R.string.app_name),
                    title = LiveExtras.RESUME_TITLE,
                    text = endedWords.ifEmpty { LiveExtras.RESUME_BUTTON },
                )
                val n = NotificationCompat.Builder(context, RESUME_CHANNEL_ID)
                    .setLocalOnly(true)
                    .setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(words[0])
                    .setContentText(words[1])
                    .setAutoCancel(true)
                    .setSilent(true)
                    .setTimeoutAfter(forMs.coerceAtLeast(1_000L))
                    .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                    .setCategory(NotificationCompat.CATEGORY_STATUS)
                    .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                    .setContentIntent(resume)
                    .addAction(0, LiveExtras.RESUME_BUTTON, resume)
                    .build()
                manager.notify(RESUME_ID, n)
            }
        }

        fun clearResume(context: Context) {
            runCatching {
                ContextCompat.getSystemService(context, NotificationManager::class.java)?.cancel(RESUME_ID)
            }
        }

        fun clearMoveOffer(context: Context) {
            runCatching {
                ContextCompat.getSystemService(context, NotificationManager::class.java)?.cancel(OFFER_ID)
            }
        }

        fun stop(context: Context) {
            runCatching { context.stopService(Intent(context, LiveService::class.java)) }
        }

        fun ensureChannel(context: Context) {
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Jarvis Live",
                    // Low: a status line for as long as the microphone is open, never a sound.
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = "Shown for as long as a Jarvis Live conversation is on on this phone."
                    setShowBadge(false)
                },
            )
        }
    }
}
