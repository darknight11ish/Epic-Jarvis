package com.jarvis.client.service

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
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
import com.jarvis.client.net.Heard
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.OrtTurnModel
import com.jarvis.client.voice.OrtWakeModels
import com.jarvis.client.voice.SmartTurn
import com.jarvis.client.voice.StopHead
import com.jarvis.client.voice.TurnEnd
import com.jarvis.client.voice.TurnModel
import com.jarvis.client.voice.TurnSettings
import com.jarvis.client.voice.VoiceSession
import com.jarvis.client.voice.WakeClip
import com.jarvis.client.voice.WakeRules
import com.jarvis.client.voice.WakeSpotter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Listens for "hey Jarvis" on this phone, while - and only while - the owner
 * has switched it on.
 *
 * WHAT IT DOES. The microphone stays open; every 80 ms the last two seconds go
 * through [WakeSpotter] (openWakeWord's "hey jarvis" model, on this phone,
 * through ONNX Runtime). Nothing is recorded to disk, nothing is sent, and no
 * words are recognised while it waits: the spotter produces one number, "how
 * much did that sound like hey Jarvis". When that number passes the desktop's
 * own threshold, the last [WakeClip.PREROLL_SECONDS] (which hold the phrase)
 * plus everything said after it until a pause become ONE clip, posted to
 * `/api/voice/utterance?source=wake_word` - the same route and path as the
 * talk button. The desktop checks the phrase again, checks the voice is the
 * owner's, and only then turns it into words (docs/WAKE-WORD.md).
 *
 * WHAT IT WILL NOT DO:
 *  - start unless the desktop says its wake word is ON ([WakeRules.mayListen]).
 *    Turning that on is an approval card on the desktop; this service cannot.
 *  - send while the event stream is stale ([WakeRules.mayPost], rule 4).
 *  - restart itself. START_NOT_STICKY, and it is never started at boot: after
 *    a reboot, or Android closing the app, it is off until switched on again.
 *    (Android would not allow a microphone service to start from the
 *    background anyway.)
 *  - run without its notification. Its own foreground-service type is
 *    `microphone` - separate from the event link's `specialUse` service, so
 *    each can stop without the other - and Android shows the microphone
 *    indicator for as long as it runs. That is correct and is not worked
 *    around (WAKE-WORD.md §2).
 *
 * While a voice turn is under way (Jarvis thinking or speaking) it stops
 * recording and does not listen, so Jarvis's own voice from the speaker is
 * never taken for a wake word - UNLESS "interrupt Jarvis while it talks" is
 * on ([BargeIn]; on by default only where the phone has an echo canceller).
 * Then, while Jarvis speaks, it listens through Android's echo canceller
 * (the voice-call microphone, with the reply played as a voice call so the
 * canceller can take it back out) for two things only: "stop", which
 * silences the reply and does nothing else, and "hey Jarvis", which silences
 * it and records what follows - sent to the PC and checked exactly like any
 * other "hey Jarvis". While the talk button records, it lets go of the
 * microphone entirely.
 */
class WakeWordService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loop: Job? = null

    @Volatile private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        ensureChannel(this)
        if (!goForeground(getString(R.string.wake_listening_text))) {
            stopSelf()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            running = false
            _state.value = WakeListen.Off
            stopSelf()
            return START_NOT_STICKY
        }
        if (loop == null && _state.value !is WakeListen.Failed) {
            running = true
            _state.value = WakeListen.Starting
            loop = scope.launch {
                try {
                    listen()
                } catch (t: Throwable) {
                    Log.w(TAG, "wake-word listening stopped", t)
                    fail("Listening stopped (${t.javaClass.simpleName}).")
                }
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        loop?.cancel()
        scope.cancel()
        if (_state.value !is WakeListen.Failed) _state.value = WakeListen.Off
        super.onDestroy()
    }

    // ------------------------------------------------------------- listening

    private suspend fun listen() {
        val voice = JarvisRuntime.voice
        voice.refreshStatus()
        WakeRules.mayListen(voice.answered.value, voice.status.value)?.let { return fail(it) }
        if (!hasMicPermission()) {
            return fail("Jarvis needs the microphone for this. Allow it, then switch listening on again.")
        }
        val models = runCatching {
            OrtWakeModels.load(
                asset(ASSET_DIR, OrtWakeModels.MEL_FILE),
                asset(ASSET_DIR, OrtWakeModels.EMB_FILE),
                asset(ASSET_DIR, OrtWakeModels.WAKE_FILE),
            )
        }.getOrElse {
            Log.w(TAG, "wake-word model did not load", it)
            return fail("The wake-word model could not be loaded (${it.javaClass.simpleName}).")
        }
        // Smart Turn: optional. Without it a sentence ends after the old
        // fixed second of quiet, exactly as before.
        val turnModel: TurnModel? = runCatching {
            OrtTurnModel.load(asset(TURN_DIR, OrtTurnModel.FILE))
        }.onFailure {
            Log.w(TAG, "Smart Turn did not load; using the fixed pause", it)
        }.getOrNull()
        // "Stop" while Jarvis talks: optional too. Without it, only "hey
        // Jarvis" can interrupt.
        val stopHead: StopHead? = runCatching {
            StopHead.parse(asset(ASSET_DIR, StopHead.FILE))
        }.onFailure {
            Log.w(TAG, "the stop word did not load", it)
        }.getOrNull()
        try {
            val spotter = WakeSpotter(models)
            val ring = WakeClip.Ring((WakeClip.PREROLL_SECONDS * RATE).toInt())
            var lastCheck = SystemClock.elapsedRealtime()
            while (running) {
                // The talk button owns the microphone while it records.
                if (voice.phase.value == VoiceSession.Phase.CAPTURING) {
                    _state.value = WakeListen.Paused
                    delay(200)
                    continue
                }
                val rec = openRecorder() ?: return fail("No microphone available right now.")
                try {
                    rec.startRecording()
                    spotter.reset()
                    ring.clear()
                    _state.value = WakeListen.Listening
                    goForeground(getString(R.string.wake_listening_text))
                    val buf = ShortArray(WakeSpotter.CHUNK)
                    while (running && voice.phase.value == VoiceSession.Phase.OFF) {
                        if (!readFully(rec, buf)) return fail("The microphone stopped.")
                        ring.push(buf)
                        val threshold = WakeRules.threshold(voice.status.value)
                        if (spotter.feed(buf).none { it >= threshold }) {
                            // Every few minutes: is the desktop's switch still on?
                            if (SystemClock.elapsedRealtime() - lastCheck > STATUS_EVERY_MS) {
                                lastCheck = SystemClock.elapsedRealtime()
                                voice.refreshStatus()
                                WakeRules.mayListen(voice.answered.value, voice.status.value)
                                    ?.let { return fail(it) }
                            }
                            continue
                        }

                        // Heard it.
                        val why = WakeRules.mayPost(
                            voice.answered.value,
                            voice.status.value,
                            JarvisRuntime.stale.value,
                        )
                        if (why != null) {
                            goForeground(why)
                            spotter.reset()
                            continue
                        }
                        _state.value = WakeListen.Heard
                        goForeground(getString(R.string.wake_heard_text))
                        var clip: ShortArray? = recordUntilPause(rec, ring.snapshot(), GRACE_SECONDS, turnModel)
                        // Not recording on this microphone while the desktop
                        // answers and Jarvis speaks: its own voice must not
                        // wake it. (With barge-in on, the echo-cancelled one
                        // listens instead - see answerListening.)
                        runCatching { rec.stop() }
                        while (clip != null && running) {
                            var (verdict, cutIn) = answerListening(clip, models, stopHead, turnModel)
                            if (cutIn == null && verdict != null &&
                                WakeRules.verdict(verdict) == WakeRules.Verdict.AWAKE
                            ) {
                                // "Hey Jarvis." and a pause: the next sentence.
                                rec.startRecording()
                                val next = recordUntilPause(
                                    rec,
                                    ShortArray(0),
                                    verdict.awakeSeconds.coerceIn(2f, 15f),
                                    turnModel,
                                )
                                runCatching { rec.stop() }
                                val answered = answerListening(next, models, stopHead, turnModel)
                                verdict = answered.first
                                cutIn = answered.second
                            }
                            if (verdict != null && WakeRules.verdict(verdict) == WakeRules.Verdict.STOP) {
                                return fail(verdict.reason.ifBlank { "The desktop stopped taking \"hey Jarvis\"." })
                            }
                            // "Hey Jarvis" said over the reply: that sentence
                            // is the next clip, through every check again.
                            clip = cutIn
                        }
                        break // reopen: a fresh recorder and a fresh spotter
                    }
                } finally {
                    runCatching { rec.stop() }
                    rec.release()
                }
                // A voice turn may still be finishing (the talk button's, say);
                // wait for it before listening again - listening for "stop"
                // and "hey Jarvis" meanwhile when barge-in is on.
                val answering = {
                    voice.phase.value != VoiceSession.Phase.OFF &&
                        voice.phase.value != VoiceSession.Phase.CAPTURING
                }
                if (running && answering() && bargeInOn()) {
                    try {
                        voice.speaker.beginVoiceCall()
                        val cutIn = listenWhileAnswering(answering, models, stopHead, turnModel)
                        while (running && answering()) delay(50)
                        if (cutIn != null && running) {
                            // Handed to the loop above as a fresh clip next
                            // time round would lose it; sent now instead.
                            answerListening(cutIn, models, stopHead, turnModel)
                        }
                    } finally {
                        voice.speaker.endVoiceCall()
                    }
                }
                while (running && answering()) {
                    delay(100)
                }
            }
        } finally {
            models.close()
            turnModel?.close()
        }
    }

    /**
     * Reads until the owner stops talking. [prefix] is the audio from before
     * the spotter fired, so the clip starts with "hey Jarvis" itself.
     *
     * When the sentence has ended is [TurnEnd]'s call: with Smart Turn
     * ([turnModel], and the PC's `turn.enabled`), a short pause asks the
     * model "finished?" - yes ends the clip at once, no keeps recording for
     * up to two seconds of quiet. Without it, the old fixed second. The
     * model hears sound and answers with one number; nothing here turns
     * speech into words.
     */
    private fun recordUntilPause(
        rec: AudioRecord,
        prefix: ShortArray,
        graceSeconds: Float,
        turnModel: TurnModel?,
    ): ShortArray {
        val maxSamples = (MAX_SECONDS * RATE).toInt()
        var out = prefix.copyOf(maxOf(prefix.size, RATE * 4).coerceAtMost(maxSamples))
        var count = prefix.size.coerceAtMost(maxSamples)
        val settings = JarvisRuntime.voice.status.value.turn
        val turn = if (turnModel != null && TurnSettings.useModel(settings, true)) {
            SmartTurn(turnModel, TurnSettings.threshold(settings))
        } else {
            null
        }
        val end = TurnEnd(
            graceSeconds = graceSeconds,
            askAfterSeconds = TurnSettings.askAfterSeconds(settings),
            maxPauseSeconds = if (turn != null) {
                TurnSettings.maxPauseSeconds(settings)
            } else {
                TurnEnd.PAUSE_WITHOUT_MODEL
            },
            maxSeconds = MAX_SECONDS - WakeClip.PREROLL_SECONDS,
            useModel = turn != null,
        )
        val buf = ShortArray(WakeSpotter.CHUNK)
        while (running && count < maxSamples) {
            if (!readFully(rec, buf)) break
            val take = minOf(buf.size, maxSamples - count)
            if (count + take > out.size) out = out.copyOf(minOf(maxSamples, out.size * 2))
            System.arraycopy(buf, 0, out, count, take)
            count += take
            val step = end.push(Wav.rms(buf, buf.size), WakeSpotter.CHUNK / RATE.toFloat())
            if (step == TurnEnd.Step.END) break
            if (step == TurnEnd.Step.ASK && turn != null) {
                // ~50-100 ms of model; the recorder's own buffer holds
                // several hundred, so nothing said meanwhile is lost.
                val finished = runCatching { turn.complete(out, count) }
                    .onFailure { Log.w(TAG, "Smart Turn failed on this pause", it) }
                    .getOrDefault(false)
                if (end.answer(finished) == TurnEnd.Step.END) break
            }
        }
        return out.copyOf(count)
    }

    /** The owner's switch, or the default: on only with an echo canceller. */
    private fun bargeInOn(): Boolean = BargeIn.enabled(
        JarvisRuntime.settings.bargeIn.value,
        runCatching { AcousticEchoCanceler.isAvailable() }.getOrDefault(false),
    )

    /**
     * Sends [clip] as a wake-word clip and waits for the whole answer. With
     * barge-in on, listens meanwhile (see [listenWhileAnswering]) and
     * returns, as the second value, what the owner said after "hey Jarvis"
     * over the reply - or null.
     */
    private suspend fun answerListening(
        clip: ShortArray,
        models: OrtWakeModels,
        stopHead: StopHead?,
        turnModel: TurnModel?,
    ): Pair<Heard?, ShortArray?> = coroutineScope {
        val voice = JarvisRuntime.voice
        val wav = Wav.encode(clip)
        if (!bargeInOn()) return@coroutineScope voice.deliverWakeClip(wav) to null
        voice.speaker.beginVoiceCall()
        try {
            val turn = async { voice.deliverWakeClip(wav) }
            val cutIn = listenWhileAnswering({ turn.isActive }, models, stopHead, turnModel)
            turn.await() to cutIn
        } finally {
            voice.speaker.endVoiceCall()
        }
    }

    /**
     * While [answering] and Jarvis is SPEAKING: the echo-cancelled
     * microphone, the wake spotter and the stop head on every 80 ms step.
     * "Stop" silences the reply ([VoiceSession.stopSpeaking]) and nothing
     * else. "Hey Jarvis" silences it and returns the clip of what follows,
     * recorded until the owner's pause. Nothing is sent from here.
     */
    private suspend fun listenWhileAnswering(
        answering: () -> Boolean,
        models: OrtWakeModels,
        stopHead: StopHead?,
        turnModel: TurnModel?,
    ): ShortArray? {
        val voice = JarvisRuntime.voice
        while (running && answering() && voice.phase.value != VoiceSession.Phase.SPEAKING) delay(50)
        if (!running || !answering()) return null
        val rec = openRecorder(MediaRecorder.AudioSource.VOICE_COMMUNICATION) ?: return null
        val canceller = runCatching {
            if (AcousticEchoCanceler.isAvailable()) {
                AcousticEchoCanceler.create(rec.audioSessionId)?.also { it.enabled = true }
            } else {
                null
            }
        }.getOrNull()
        try {
            rec.startRecording()
            val spotter = WakeSpotter(models)
            val ring = WakeClip.Ring((WakeClip.PREROLL_SECONDS * RATE).toInt())
            val buf = ShortArray(WakeSpotter.CHUNK)
            val stops = ArrayList<Float>(4)
            while (running && answering() && voice.phase.value == VoiceSession.Phase.SPEAKING) {
                if (!readFully(rec, buf)) return null
                ring.push(buf)
                stops.clear()
                val wakes = spotter.feed(buf, buf.size) { w -> stops.add(stopHead?.score(w) ?: 0f) }
                val wakeThreshold = WakeRules.threshold(voice.status.value)
                for (k in wakes.indices) {
                    when (
                        BargeIn.decide(
                            stopScore = stops.getOrElse(k) { 0f },
                            wakeScore = wakes[k],
                            stopThreshold = StopHead.THRESHOLD,
                            wakeThreshold = wakeThreshold,
                            speakingText = voice.speakingText.value,
                        )
                    ) {
                        BargeIn.Action.STOP_SPEAKING -> {
                            voice.stopSpeaking()
                            return null
                        }
                        BargeIn.Action.WAKE -> {
                            voice.stopSpeaking()
                            _state.value = WakeListen.Heard
                            return recordUntilPause(rec, ring.snapshot(), GRACE_SECONDS, turnModel)
                        }
                        BargeIn.Action.NONE -> Unit
                    }
                }
            }
            return null
        } finally {
            runCatching { rec.stop() }
            rec.release()
            runCatching { canceller?.release() }
        }
    }

    private fun readFully(rec: AudioRecord, buf: ShortArray): Boolean {
        var got = 0
        while (got < buf.size) {
            val n = rec.read(buf, got, buf.size - got)
            // A negative code, not an exception: a revoked permission or a
            // microphone taken by another app. Stop rather than spin.
            if (n <= 0) return false
            got += n
        }
        return true
    }

    @SuppressLint("MissingPermission") // hasMicPermission() is checked before this is reached
    private fun openRecorder(source: Int = MediaRecorder.AudioSource.VOICE_RECOGNITION): AudioRecord? {
        if (!hasMicPermission()) return null
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val rec = runCatching {
            AudioRecord(
                // VOICE_RECOGNITION, the same source the talk button uses: the
                // un-processed path a voice-print check wants. Barge-in asks
                // for VOICE_COMMUNICATION instead - the path Android's echo
                // canceller works on - only while Jarvis is speaking.
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

    private fun asset(dir: String, name: String): ByteArray =
        assets.open("$dir/$name").use { it.readBytes() }

    private fun fail(why: String) {
        running = false
        _state.value = WakeListen.Failed(why)
        stopSelf()
    }

    // ---------------------------------------------------------- notification

    private fun goForeground(text: String): Boolean {
        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, WakeWordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this,
            2,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.wake_listening_title))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            // Stopping is the safe direction, so it may be one tap from the
            // lock screen. (Nothing here can turn listening ON.)
            .addAction(0, getString(R.string.wake_stop), stop)
            .build()
        return try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
            true
        } catch (e: Exception) {
            // Android 14+ refuses a microphone service started from the
            // background or without the permission. Said, never retried.
            Log.w(TAG, "startForeground refused", e)
            _state.value = WakeListen.Failed(
                "Android did not allow Jarvis to listen (${e.javaClass.simpleName}). " +
                    "Open Jarvis and switch listening on from there.",
            )
            running = false
            false
        }
    }

    companion object {
        private const val TAG = "JarvisWakeWord"
        const val CHANNEL_ID = "jarvis_wake"
        private const val NOTIFICATION_ID = 0x4A57
        const val ACTION_STOP = "com.jarvis.client.STOP_WAKE_WORD"
        private const val ASSET_DIR = "wakeword"
        /** Smart Turn's model: `assets/turn/`. */
        private const val TURN_DIR = "turn"
        private const val RATE = WakeSpotter.SAMPLE_RATE
        /** How long to wait for words after "hey Jarvis" before sending the phrase alone. */
        private const val GRACE_SECONDS = 3f
        /** The clip's cap, under the desktop's 30 s. */
        private const val MAX_SECONDS = 17f
        private const val STATUS_EVERY_MS = 5 * 60 * 1000L

        private val _state = MutableStateFlow<WakeListen>(WakeListen.Off)

        /** What this phone's listener is doing. The Checks screen reads it. */
        val state: StateFlow<WakeListen> = _state.asStateFlow()

        /** Call from the app's own screen only - Android refuses it from the background. */
        fun start(context: Context) {
            if (_state.value is WakeListen.Failed) _state.value = WakeListen.Off
            runCatching {
                ContextCompat.startForegroundService(context, Intent(context, WakeWordService::class.java))
            }.onFailure {
                Log.w(TAG, "could not start", it)
                _state.value = WakeListen.Failed("Android did not allow Jarvis to listen (${it.javaClass.simpleName}).")
            }
        }

        fun stop(context: Context) {
            if (_state.value !is WakeListen.Failed) _state.value = WakeListen.Off
            runCatching {
                context.startService(Intent(context, WakeWordService::class.java).setAction(ACTION_STOP))
            }
        }

        fun ensureChannel(context: Context) {
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    context.getString(R.string.channel_wake_name),
                    // Low: a status line for as long as the microphone is
                    // open, never a sound.
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = context.getString(R.string.channel_wake_desc)
                    setShowBadge(false)
                },
            )
        }
    }
}

/** What the phone's "hey Jarvis" listener is doing. */
sealed interface WakeListen {
    data object Off : WakeListen
    data object Starting : WakeListen
    data object Listening : WakeListen
    /** It heard "hey Jarvis" and is recording or sending the sentence. */
    data object Heard : WakeListen
    /** The talk button has the microphone. */
    data object Paused : WakeListen
    data class Failed(val why: String) : WakeListen

    /** The microphone is (or may be) open. */
    val on: Boolean get() = this != Off && this !is Failed
}
