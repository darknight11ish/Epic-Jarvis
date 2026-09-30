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
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
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
import com.jarvis.client.voice.LiveExtras
import com.jarvis.client.voice.LiveRules
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
 *  - A BLUETOOTH HEADSET'S MICROPHONE is preferred while one is connected
 *    ([preferHeadset]: Android's communication device, and the recorder's
 *    preferred input); if it cannot be used the phone's own is, and the Live
 *    screen says which ([JarvisRuntime.liveMicWords]). No Bluetooth
 *    permission is needed: the headset is picked from Android's own audio
 *    device lists (MODIFY_AUDIO_SETTINGS, already held).
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

    /** True once this service made a Bluetooth headset the communication device (undone at the end). */
    private var headsetRouted = false

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
                    JarvisRuntime.liveNotice("The microphone stopped. Start Jarvis Live again from the Live screen.")
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
        releaseHeadset()
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

    // ------------------------------------------------------ Bluetooth headset

    /**
     * A connected Bluetooth headset, made the communication device so its
     * microphone can be used (Android 12+'s way; minSdk is 33), and the
     * matching input for the recorder - or null to use the phone's own.
     */
    private fun preferHeadset(): Pair<LiveExtras.Mic, AudioDeviceInfo?>? {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return null
        try {
            val comm = am.availableCommunicationDevices
            val picked = LiveExtras.pickHeadset(
                comm.map { LiveExtras.Mic(it.type, it.productName?.toString().orEmpty()) },
            ) ?: return null
            val device = comm.first { it.type == picked.type }
            if (am.communicationDevice?.id != device.id && !am.setCommunicationDevice(device)) {
                return null
            }
            headsetRouted = true
            val input = am.getDevices(AudioManager.GET_DEVICES_INPUTS).firstOrNull { it.type == device.type }
            return picked to input
        } catch (e: Exception) {
            Log.w(TAG, "the Bluetooth headset could not be chosen", e)
            return null
        }
    }

    private fun releaseHeadset() {
        if (!headsetRouted) return
        headsetRouted = false
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
        runCatching { am.clearCommunicationDevice() }
    }

    // ------------------------------------------------------------- listening

    private suspend fun listen() {
        val voice = JarvisRuntime.voice
        if (!hasMicPermission()) {
            JarvisRuntime.liveNotice("Jarvis needs the microphone for Jarvis Live. Allow it, then start Live again.")
            JarvisRuntime.liveStop("owner")
            return
        }
        // Smart Turn: optional. Without it a sentence ends after the fixed pause.
        val turnModel: TurnModel? = runCatching {
            OrtTurnModel.load(assets.open("$TURN_DIR/${OrtTurnModel.FILE}").use { it.readBytes() })
        }.onFailure { Log.w(TAG, "Smart Turn did not load; using the fixed pause", it) }.getOrNull()
        var rec: AudioRecord? = null
        var recSource = -1
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
            runCatching { canceller?.release() }
            canceller = null
            recSource = -1
            if (!keepRing) ring.clear()
        }
        try {
            while (running) {
                val status = JarvisRuntime.liveStatus.value
                if (!LiveRules.onHere(status)) break
                // A call pauses Live (the audio mode; Jarvis's own echo-
                // cancelling mode does not count), and ends the pause after.
                JarvisRuntime.liveCall(LiveRules.onCall(audioMode(), voice.speaker.voiceCall))
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
                if (!may.mic) {
                    // Closed, not ignored: Android's microphone sign goes off.
                    close()
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
                val source = if (speaking) {
                    MediaRecorder.AudioSource.VOICE_COMMUNICATION
                } else {
                    MediaRecorder.AudioSource.VOICE_RECOGNITION
                }
                if (rec == null || recSource != source) {
                    close(keepRing = rec != null)
                    val opened = openPreferred(source)
                    if (opened == null) {
                        JarvisRuntime.liveNotice("No microphone available right now.")
                        delay(IDLE_MS * 5)
                        continue
                    }
                    if (speaking) {
                        canceller = runCatching {
                            if (AcousticEchoCanceler.isAvailable()) {
                                AcousticEchoCanceler.create(opened.audioSessionId)?.also { it.enabled = true }
                            } else {
                                null
                            }
                        }.getOrNull()
                    }
                    opened.startRecording()
                    rec = opened
                    recSource = source
                }
                val clip = window(requireNotNull(rec), ring, turnModel, overReply = speaking) ?: continue
                // Not waited for: the recorder's buffer holds well under a
                // second, and the owner may already be saying the next thing
                // (a second thought joins the question - LiveRules.fold).
                scope.launch { sending.withLock { send(clip) } }
            }
        } finally {
            close()
            if (inVoiceCall) voice.speaker.endVoiceCall()
            turnModel?.close()
        }
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
            if (!readFully(rec, buf)) return null
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
        return may.mic && !LiveRules.onCall(audioMode(), voice.speaker.voiceCall)
    }

    private suspend fun send(clip: ShortArray) {
        val waited = VoiceFlow.trailingQuietMs(clip) ?: return
        val heard = JarvisRuntime.voice.deliverLiveClip(Wav.encode(clip), waited) ?: return
        JarvisRuntime.liveHeard(heard)
    }

    private fun audioMode(): Int =
        (getSystemService(Context.AUDIO_SERVICE) as? AudioManager)?.mode ?: AudioManager.MODE_NORMAL

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
     * The recorder, through a connected Bluetooth headset's microphone when
     * there is one, else the phone's own - and the Live screen told which.
     */
    private fun openPreferred(source: Int): AudioRecord? {
        val headset = preferHeadset()
        val rec = openRecorder(source) ?: return null
        if (headset == null) {
            releaseHeadset()
            JarvisRuntime.liveMicWords(LiveExtras.micWords(null))
            return rec
        }
        val input = headset.second
        val took = input != null && runCatching { rec.setPreferredDevice(input) }.getOrDefault(false)
        if (!took) releaseHeadset()
        JarvisRuntime.liveMicWords(if (took) LiveExtras.micWords(headset.first) else LiveExtras.micWords(headset.first, fellBack = true))
        return rec
    }

    @SuppressLint("MissingPermission") // hasMicPermission() is checked before this is reached
    private fun openRecorder(source: Int): AudioRecord? {
        if (!hasMicPermission()) return null
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val rec = runCatching {
            AudioRecord(
                source,
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
        val title = sign.title.ifEmpty { LiveRules.TITLE }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(sign.detail.ifEmpty { LiveRules.SEEN.getValue("end_hint") })
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
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
            // background or without the permission. Said, never retried.
            Log.w(TAG, "startForeground refused", e)
            JarvisRuntime.liveNotice(
                "Android did not let Jarvis Live listen from the background. Open Jarvis, " +
                    "then start Live from the Live screen.",
            )
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

        /** The "Live is on your PC - move it here?" heads-up channel. */
        const val OFFER_CHANNEL_ID = "jarvis_live_offer"
        private const val OFFER_ID = NotificationIds.LIVE_OFFER

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

        /** How often (in 80 ms steps) a window checks it may stay open: about every 0.4 s. */
        private const val CHECK_EVERY_STEPS = 5

        /** Call from the app's own screen, or from a reply the app received in front. False when Android refused. */
        fun start(context: Context): Boolean =
            runCatching {
                ContextCompat.startForegroundService(context, Intent(context, LiveService::class.java))
            }.onFailure {
                Log.w(TAG, "could not start", it)
                JarvisRuntime.liveNotice(
                    "Android did not let Jarvis Live listen from the background. Open Jarvis, then " +
                        "start Live from the Live screen.",
                )
            }.isSuccess

        /**
         * "Hey Jarvis" to this phone while Live runs on the PC: a heads-up,
         * kept on this phone, that opens the Live screen with "Move it here"
         * on it. Fixed words only; gone after 30 seconds.
         */
        fun showMoveOffer(context: Context, device: String) {
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
                val n = NotificationCompat.Builder(context, RESUME_CHANNEL_ID)
                    .setLocalOnly(true)
                    .setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(LiveExtras.RESUME_TITLE)
                    .setContentText(endedWords.ifEmpty { LiveExtras.RESUME_BUTTON })
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
