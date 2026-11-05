package com.jarvis.client.service

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.call.CallRecordNow
import com.jarvis.client.call.CallRecordChunks
import com.jarvis.client.call.CallRecordRules
import com.jarvis.client.call.CallRecordStore
import com.jarvis.client.call.Chunker
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.CallRecordWire
import com.jarvis.client.platform.DeviceSecure
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.MicNow
import com.jarvis.client.voice.MicOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonObject

/**
 * Records a phone call - on the MICROPHONE, because Android will not give this
 * app the call's own audio.
 *
 * THE OWNER'S REQUEST (2026-11-04): say *"record call"* to Jarvis; Jarvis
 * records the call, the PC turns it into words, dates it, works out who was
 * speaking and writes ONE note in the Obsidian vault named with the date and
 * time. This service is the phone's whole half of that. It never transcribes
 * and never writes a note: no `SpeechRecognizer`, no model, and it cannot see
 * the vault. It produces PCM, a date and a consent flag, and posts them to the
 * owner's own PC ([CallRecordRules] holds the frozen contract).
 *
 * THE PLATFORM TRUTH, which shapes everything here. A normal app cannot
 * capture `VOICE_CALL` - that source is privileged, and a sideloaded app never
 * has it. So the recording is the microphone, with the call on speaker: both
 * voices are caught acoustically. That has three consequences, all of them
 * visible rather than hidden:
 *  1. the source is `UNPROCESSED` where the platform opens it and `MIC`
 *     otherwise - **never `VOICE_COMMUNICATION`**, whose echo canceller
 *     removes exactly the far end this feature exists to keep;
 *  2. before recording, the service asks Android to put the call on speaker
 *     (`setCommunicationDevice(TYPE_BUILTIN_SPEAKER)`, with the old
 *     `setSpeakerphoneOn` as the fallback). When the platform refuses, the
 *     notification says [CallRecordRules.SPEAKER_ASK] - it never claims both
 *     sides were captured when one of them was never in the room;
 *  3. the notification carries "Recording - tell the other person" for the
 *     whole call. It never goes away, and it is the one thing this app can do
 *     about the person at the other end.
 *
 * WHAT IT DOES, in order: armed (a notification and a poll of `AudioManager.mode`,
 * no microphone open) -> a call starts (the mode becomes IN_CALL / IN_COMMUNICATION)
 * -> the microphone opens, PCM16LE mono 16 kHz goes to disk in 64 KiB chunks,
 * and each chunk is posted as it is cut -> the call ends -> `finish` -> the PC
 * writes the note. A chunk that cannot be sent is retried with the SAME
 * sequence number; if the PC is unreachable the audio stays on disk and the
 * notification says so. Nothing is ever thrown away because a network was
 * down - the exceptions are a recording under a second, which has no audio
 * worth a note and is discarded out loud, and the owner's own Delete on the
 * plate, which asks first and deletes only what the PC has not taken.
 *
 * THE MICROPHONE IS SHARED, so it is arbitrated: call recording claims it
 * through [MicNow] / [MicOwner] when it arms, and Live, the wake word and the
 * talk button keep theirs closed until it is released. Paused, not stopped:
 * Android 14+ refuses to START a microphone foreground service from the
 * background, so a stopped Live could not come back until the app was in
 * front - "paused and restored" would quietly become "off until the owner
 * notices".
 *
 * WHAT ENDS IT EARLY, each with its own sentence: a low battery, the headset
 * being unplugged, the microphone being refused or taken away, the owner
 * pressing Stop, or the app being shut down. Every one of them finishes the
 * upload rather than losing the audio.
 */
class CallRecordService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val uploadLock = Mutex()

    private var loop: Job? = null

    @Volatile private var running = false

    /** The rules' own state. The service only applies [CallRecordRules.Effect]s to it. */
    @Volatile private var state = CallRecordRules.State()

    private var store: CallRecordStore? = null
    private var session: CallRecordStore.Session? = null

    /** Where the audio is read, and where it is cut. Touched only by the capture loop and the endings. */
    @Volatile private var recorderField: AudioRecord? = null
    private var captureJob: Job? = null
    private val chunker = Chunker()

    /** When recording began, on the monotonic clock, for the elapsed line. */
    @Volatile private var startedRealtime = 0L

    /** Did the platform let the call go on speaker? False is said out loud. */
    @Volatile private var speakerOn = true

    /** The last second shown in the notification, so it is rebuilt once a second, not once a read. */
    private var shownSecond = -1L

    /** Why the recorder stopped by itself, if it did - said in the notification and on the plate. */
    @Volatile private var stopWords: String? = null

    private val endings = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                // A long call can outlast the battery. Stopping there keeps
                // the audio that exists instead of dying with a hot mic.
                Intent.ACTION_BATTERY_LOW -> finish(CallRecordRules.Event.LOW_BATTERY)
                // The headset went away (`ACTION_AUDIO_BECOMING_NOISY`): the
                // route changed under the recorder, so the audio from here on
                // is not the audio that was asked for.
                AudioManager.ACTION_AUDIO_BECOMING_NOISY -> finish(CallRecordRules.Event.HEADSET_UNPLUGGED)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        store = CallRecordStore(CallRecordStore.folder(filesDir))
        ensureChannel(this)
        // System broadcasts only, and this service is not exported: nothing
        // else on the phone can make it stop recording.
        runCatching {
            ContextCompat.registerReceiver(
                this,
                endings,
                IntentFilter().apply {
                    addAction(Intent.ACTION_BATTERY_LOW)
                    addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
                },
                ContextCompat.RECEIVER_NOT_EXPORTED,
            )
        }.onFailure { Log.w(TAG, "no battery/headset watch; recording still runs", it) }
        publish()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                when (state.phase) {
                    CallRecordRules.Phase.RECORDING -> finish(CallRecordRules.Event.OWNER_STOP)
                    CallRecordRules.Phase.ARMED -> {
                        stopWords = CallRecordRules.STOPPED_TEXT
                        apply(CallRecordRules.Event.OWNER_STOP)
                        publish()
                        stopSelf()
                    }
                    // A Stop while the upload is running cannot un-send what
                    // the PC already has. The rules keep the rest on this
                    // phone; the service goes away and the plate offers to
                    // send it later.
                    CallRecordRules.Phase.SENDING -> {
                        apply(CallRecordRules.Event.OWNER_STOP)
                        publish()
                        stopSelf()
                    }
                    CallRecordRules.Phase.OFF -> stopSelf()
                }
                return START_NOT_STICKY
            }
            ACTION_SEND_WAITING -> {
                stopWords = "Sending the recording to your PC…"
                if (!foreground()) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                start()
                scope.launch {
                    sendWaiting(attempts = SEND_NOW_ATTEMPTS)
                    // Nothing is armed or recording: this service was only up
                    // to send, and it goes away when that has been tried.
                    if (state.phase == CallRecordRules.Phase.OFF) stopSelf()
                }
                return START_NOT_STICKY
            }
            ACTION_DISCARD -> {
                // THE OWNER'S OWN DISCARD, after the plate's confirmation. A
                // recording whose card was denied, or that cannot be sent, must
                // not sit on this phone for ever with no way to remove it (the
                // privacy audit's D7). Only what the PC has NOT taken is ever
                // deleted: `discardUnsent` cannot touch a finished recording.
                // It needs no microphone and no foreground notification, so a
                // started service is enough - the app is in front on the plate.
                scope.launch {
                    val gone = store?.discardUnsent() ?: 0
                    stopWords = CallRecordRules.deleted(gone)
                    publish()
                    if (state.phase == CallRecordRules.Phase.OFF) stopSelf()
                }
                return START_NOT_STICKY
            }
            ACTION_ARM, null -> {
                if (!foreground()) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                start()
                // Claim the microphone so Live, the wake word and the talk
                // button let go of it before a call can arrive.
                if (state.phase == CallRecordRules.Phase.OFF) {
                    apply(CallRecordRules.Event.ARM)
                    publish()
                }
                // Anything left from an earlier call goes up by itself while
                // the microphone waits for a call.
                scope.launch { sendWaiting(attempts = 1) }
                return START_NOT_STICKY
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        loop?.cancel()
        captureJob?.cancel()
        closeRecorder()
        runCatching { unregisterReceiver(endings) }
        // The app is going away. The audio on disk IS the recording; the
        // upload resumes the next time this service starts, and the plate says
        // how many are waiting.
        val open = session
        if (open != null) {
            if (state.phase == CallRecordRules.Phase.RECORDING) {
                state = state.copy(phase = CallRecordRules.Phase.SENDING)
                announceWaiting()
            } else if (open.finished()) {
                open.remove()
            }
        }
        MicNow.disarm()
        scope.cancel()
        publish()
        super.onDestroy()
    }

    // ---------------------------------------------------------- the loop ---

    private fun start() {
        if (loop != null) return
        running = true
        loop = scope.launch {
            try {
                supervise()
            } catch (t: Throwable) {
                Log.w(TAG, "call recording stopped", t)
                stopWords = "Call recording stopped: ${t.javaClass.simpleName}."
            } finally {
                running = false
                closeRecorder()
                session?.let { if (it.finished()) it.remove() }
                MicNow.disarm()
                publish()
                stopSelf()
            }
        }
    }

    /**
     * Once every [POLL_MS]: is a call on, and does that change what should be
     * happening? This is the ONE place the audio mode is read, so a call that
     * starts while the owner is in another app is noticed, and a call that
     * ends is noticed the same way - with no phone-state permission
     * (`LiveRules.onCall`, the same rule Live already uses).
     */
    private suspend fun supervise() {
        while (running) {
            val on = callOn()
            when (state.phase) {
                CallRecordRules.Phase.ARMED -> if (on) beginRecording()
                CallRecordRules.Phase.RECORDING ->
                    if (on) tick() else finish(CallRecordRules.Event.CALL_END)
                else -> Unit
            }
            delay(POLL_MS)
        }
    }

    /** Update the clock in the notification, once a second. */
    private fun tick() {
        val elapsed = SystemClock.elapsedRealtime() - startedRealtime
        val second = elapsed / 1000L
        if (second == shownSecond) return
        shownSecond = second
        publish()
    }

    /**
     * Is a real call on? The SAME rule Live uses ([LiveRules.onCall]): Jarvis's
     * own two modes are `MODE_IN_COMMUNICATION`, so a reply being spoken is
     * never mistaken for a call, and `MODE_IN_CALL` always is one.
     */
    private fun callOn(): Boolean {
        val mode = (getSystemService(Context.AUDIO_SERVICE) as? AudioManager)?.mode
            ?: AudioManager.MODE_NORMAL
        val ownVoiceCall = runCatching { JarvisRuntime.voice.speaker.voiceCall }.getOrDefault(false)
        return LiveRules.onCall(mode, ownVoiceCall)
    }

    // ------------------------------------------------------- the capture ---

    /**
     * A call started: open the microphone and begin. Nothing is recorded if the
     * microphone cannot be opened - the owner is told which reason it was, and
     * the arming is not silently kept.
     */
    private fun beginRecording() {
        if (captureJob != null) return
        if (!hasMicPermission()) {
            stopWords = "Call recording needs Microphone permission on this phone."
            finish(CallRecordRules.Event.MIC_REFUSED)
            return
        }
        val may = MicNow.mayOpen(MicOwner.Use.CALL_RECORD)
        if (!may.allowed) {
            stopWords = may.why
            finish(CallRecordRules.Event.MIC_REFUSED)
            return
        }
        // Speaker first, so both voices are in the room for the microphone.
        speakerOn = wantSpeaker()
        val opened = openRecorder()
        if (opened == null) {
            stopWords = "No microphone was available for the call."
            finish(CallRecordRules.Event.MIC_REFUSED)
            return
        }
        val began = System.currentTimeMillis()
        val sessionNow = store?.begin(began)
        if (sessionNow == null) {
            runCatching { opened.release() }
            stopWords = "This phone would not open a file for the recording."
            finish(CallRecordRules.Event.MIC_REFUSED)
            return
        }
        session = sessionNow
        startedRealtime = SystemClock.elapsedRealtime()
        chunker.reset()
        state = CallRecordRules.next(
            state.copy(phase = CallRecordRules.Phase.ARMED, startedAtMs = began),
            CallRecordRules.Event.CALL_START,
        ).state
        MicNow.opened(MicOwner.Use.CALL_RECORD)
        recorderField = opened
        shownSecond = -1
        publish()
        runCatching { opened.startRecording() }
        captureJob = scope.launch { readUntilStopped(opened) }
    }

    /**
     * The read loop. One buffer in, exact chunks out, each written to disk
     * BEFORE it is offered to the uploader - the file is the record, not the
     * socket.
     */
    private fun readUntilStopped(rec: AudioRecord) {
        val buffer = ShortArray(READ_SAMPLES)
        var sinceUpload = SystemClock.elapsedRealtime()
        try {
            while (running && state.phase == CallRecordRules.Phase.RECORDING) {
                // The microphone can be taken away mid-call (a permission
                // revoked, Android's own call UI, another app): ask again.
                if (!MicNow.mayOpen(MicOwner.Use.CALL_RECORD).allowed) {
                    stopWords = MicOwner.RECORDING_REFUSAL
                    finish(CallRecordRules.Event.MIC_REFUSED)
                    break
                }
                val n = rec.read(buffer, 0, buffer.size)
                if (n <= 0) {
                    // A NEGATIVE read is a dead recorder, not silence. Ending
                    // the recording here is what keeps a hot mic from running
                    // with nothing being saved.
                    stopWords = MIC_STOPPED_WORDS
                    finish(CallRecordRules.Event.MIC_REFUSED)
                    break
                }
                val pcm = toLittleEndian(buffer, n)
                // ONE writer: the chunk file is created under the same lock the
                // ending uses, so the tail cannot land inside a chunk.
                synchronized(chunker) {
                    for (chunk in chunker.push(pcm, pcm.size)) write(chunk)
                }
                state = state.copy(bytes = state.bytes + pcm.size)
                // The uploader is nudged about once a second; it drains as
                // many chunks as the PC will take, in order - and closes NOTHING
                // (`finish = false`): the call is still on.
                val now = SystemClock.elapsedRealtime()
                if (now - sinceUpload >= UPLOAD_NUDGE_MS) {
                    sinceUpload = now
                    if (!uploadLock.isLocked) scope.launch { drain(attempts = 1, finish = false) }
                }
            }
        } catch (t: Throwable) {
            // Never a silent stop: the notification says the microphone
            // failed and the audio already cut is kept.
            Log.w(TAG, "capture failed", t)
            stopWords = MIC_STOPPED_WORDS
            finish(CallRecordRules.Event.MIC_REFUSED)
        }
    }

    /** The last, short chunk goes to disk too, then the microphone closes. */
    private fun closeRecorder() {
        captureJob = null
        runCatching { recorderField?.stop() }
        runCatching { recorderField?.release() }
        recorderField = null
        synchronized(chunker) {
            chunker.flush()?.let { write(it) }
        }
        MicNow.closed(MicOwner.Use.CALL_RECORD)
    }

    private fun write(bytes: ByteArray) {
        val s = session ?: return
        if (s.writeChunk(bytes) < 0) {
            stopWords = "This phone would not save the recording."
        }
    }

    /** PCM16LE, exactly as `format: "s16le"` promises. */
    private fun toLittleEndian(samples: ShortArray, count: Int): ByteArray {
        val out = ByteArray(count * CallRecordRules.BYTES_PER_SAMPLE)
        var at = 0
        for (i in 0 until count) {
            val v = samples[i].toInt()
            out[at++] = (v and 0xFF).toByte()
            out[at++] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }

    /**
     * The recorder, opened at 16 kHz mono PCM16. `UNPROCESSED` when Android
     * gives it (no AGC, no noise suppression: an honest acoustic picture), and
     * `MIC` when it does not. `VOICE_COMMUNICATION` is never asked for - its
     * echo canceller deletes the other person.
     */
    @SuppressLint("MissingPermission") // hasMicPermission() is checked by every caller
    private fun openRecorder(): AudioRecord? {
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val bufferBytes = maxOf(min * 2, CallRecordRules.CHUNK_BYTES)
        val sources = intArrayOf(MediaRecorder.AudioSource.UNPROCESSED, MediaRecorder.AudioSource.MIC)
        for (source in sources) {
            val rec = runCatching {
                AudioRecord(source, RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, bufferBytes)
            }.getOrNull() ?: continue
            if (rec.state == AudioRecord.STATE_INITIALIZED) return rec
            runCatching { rec.release() }
        }
        return null
    }

    /**
     * Ask Android for the speaker, so the microphone can hear the other person
     * too. `setCommunicationDevice` is the modern way and the only one that
     * matters on this app's minSdk (33); the old `setSpeakerphoneOn` is kept as
     * the documented fallback for a platform that refuses the modern call.
     */
    @Suppress("DEPRECATION") // setSpeakerphoneOn: the documented fallback
    private fun wantSpeaker(): Boolean {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val speaker = runCatching {
                am.availableCommunicationDevices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
            }.getOrNull()
            if (speaker != null && runCatching { am.setCommunicationDevice(speaker) }.getOrDefault(false)) {
                return true
            }
        }
        val legacy = runCatching {
            am.setSpeakerphoneOn(true)
            am.isSpeakerphoneOn
        }.getOrDefault(false)
        return legacy
    }

    /** Let the call go back where it was, so the owner's next call is not stuck on speaker. */
    @Suppress("DEPRECATION") // setSpeakerphoneOn: the other half of the fallback
    private fun releaseSpeaker() {
        val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
        runCatching { am.clearCommunicationDevice() }
        runCatching { if (am.isSpeakerphoneOn) am.setSpeakerphoneOn(false) }
    }

    private fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    // -------------------------------------------------------- the endings ---

    /**
     * End the recording - whichever way it ended. The microphone closes FIRST
     * and the chunk already cut goes to disk, then the upload finishes. The
     * same path for every ending, so none of them can lose audio.
     */
    private fun finish(event: CallRecordRules.Event) {
        if (state.phase != CallRecordRules.Phase.RECORDING) return
        val elapsed = SystemClock.elapsedRealtime() - startedRealtime
        closeRecorder()
        if (elapsed < 1000L) {
            // Under a second, there is nothing a note could be made from (and
            // the PC refuses an empty recording). This is the ONE place audio
            // is deleted, and it is said out loud.
            stopWords = "That call lasted under a second, so there was nothing to keep."
            apply(CallRecordRules.Event.TOO_SHORT)
            publish()
            stopSelf()
            return
        }
        apply(event)
        publish()
        scope.launch {
            val sent = drain(attempts = FINISH_ATTEMPTS, finish = true)
            if (sent) {
                stopWords = CallRecordRules.SENT_TEXT
                apply(CallRecordRules.Event.SENT)
            } else {
                stopWords = CallRecordRules.WAITING_TEXT
                apply(CallRecordRules.Event.UPLOAD_WAITING)
            }
            publish()
            stopSelf()
        }
    }

    /** Say that a finished-but-unsent recording is waiting, on a notification of its own. */
    private fun announceWaiting() {
        val s = session
        if (s != null && s.hasAudio()) noticeWaiting(this)
    }

    // -------------------------------------------------------- the upload ---

    /**
     * Send everything on this phone the PC has not taken, oldest first.
     *
     * [finish] is false while a recording is STILL RUNNING: the pieces go up
     * as they are cut, and the session must not be closed mid-call - the PC
     * would write a note for half a conversation. It is true for every other
     * caller (the end of a call, the plate's button, a start with a queue),
     * where `finish` is exactly what closes the note.
     *
     * False means "not yet": the audio stays exactly where it is and the
     * caller says it is waiting. True means every recording is finished and
     * its folder is gone.
     */
    private suspend fun drain(attempts: Int, finish: Boolean): Boolean = uploadLock.withLock {
        val s = store ?: return@withLock false
        val live = if (finish) null else session
        for (each in s.unsent()) {
            if (!send(each, attempts.coerceAtLeast(1), complete = each !== live)) return@withLock false
        }
        true
    }

    /** The explicit "send it now" path (the plate's button, or a start with a queue). */
    private suspend fun sendWaiting(attempts: Int) {
        if (!drain(attempts, finish = true)) store?.unsent()?.lastOrNull()?.let { noticeWaiting(this) }
        publish()
    }

    /**
     * One recording: `start` (once, for its session id), then every chunk in
     * `seq` order with the SAME number retried on failure, then `finish`.
     *
     * The order is the contract: the PC appends chunks in `seq` order, so a
     * skipped number is a hole in the middle of the audio that nothing later
     * repairs, and the repeat is what the retry is for.
     *
     * [complete] false sends the pieces that exist and stops there, leaving
     * the session open: that is a call still in progress, and closing it would
     * have the PC write a note for half a conversation.
     */
    private suspend fun send(session: CallRecordStore.Session, attempts: Int, complete: Boolean): Boolean {
        if (!session.hasAudio()) {
            // Nothing but a session id: the PC would be asked to finish an
            // empty recording. Let it go.
            session.markFinished(null)
            session.remove()
            return true
        }
        var pc = session.pcSession
        if (pc == null) {
            var tries = 0
            while (pc == null && tries < attempts) {
                val res = JarvisRuntime.api.callRecordStart(session.startedAtMs)
                if (res is ApiResult.Ok) pc = CallRecordWire.started(res.value)
                if (pc == null) {
                    tries++
                    if (tries < attempts) delay(backoff(tries))
                }
            }
            if (pc == null) return false
            session.setPcSession(pc)
        }
        // EVERY chunk the PC does not have, in order - including the retry that
        // a crash needs. A 409 naming `expected` means the PC already holds
        // every seq below it, so those are recorded as sent and the loop moves
        // on to the real gap instead of retrying the same number for ever
        // (call/CallRecordChunks.kt, and the privacy audit's D3).
        val server = pc
        val sent = CallRecordChunks.send(
            session = session,
            attempts = attempts,
            post = { seq, pcm ->
                val res = JarvisRuntime.api.callRecordChunk(server, seq, pcm)
                (res as? ApiResult.Ok<JsonObject>)?.value
            },
            pause = { tries -> delay(backoff(tries)) },
        )
        if (!sent) return false
        if (!complete) return true
        var tries = 0
        while (tries < attempts) {
            val res = JarvisRuntime.api.callRecordFinish(
                pc,
                session.durationSec(),
                CallRecordRules.title(session.startedAtMs),
            )
            if (res is ApiResult.Ok) {
                val done = CallRecordWire.finished(res.value)
                if (done == null) return false
                session.markFinished(done.note)
                session.remove()
                return true
            }
            tries++
            if (tries < attempts) delay(backoff(tries))
        }
        return false
    }

    private fun backoff(tries: Int): Long = minOf(MAX_BACKOFF_MS, 1000L shl (tries - 1).coerceIn(0, 4))

    // ---------------------------------------------------- the notification ---

    /**
     * The ongoing notification: the state, the clock while recording, the
     * consent line, and Stop. Fixed words only; redacted on a locked phone by
     * the one shared rule every Jarvis notifier uses.
     */
    private fun build(): Notification {
        val phase = state.phase
        val elapsed = if (phase == CallRecordRules.Phase.RECORDING) {
            SystemClock.elapsedRealtime() - startedRealtime
        } else {
            0L
        }
        val title = when (phase) {
            CallRecordRules.Phase.RECORDING -> "${CallRecordRules.RECORDING_TITLE} ${CallRecordRules.clock(elapsed)}"
            CallRecordRules.Phase.ARMED -> CallRecordRules.ARMED_TITLE
            else -> CallRecordRules.PLATE_TITLE
        }
        val speakerAsk = phase == CallRecordRules.Phase.RECORDING && !speakerOn
        val text = when (phase) {
            CallRecordRules.Phase.RECORDING ->
                if (speakerAsk) "${CallRecordRules.CONSENT_LINE}. ${CallRecordRules.SPEAKER_ASK}"
                else CallRecordRules.CONSENT_LINE
            CallRecordRules.Phase.ARMED -> CallRecordRules.ARMED_TEXT
            else -> stopWords ?: CallRecordRules.STOPPED_TEXT
        }
        val locked = SecurityRules.notificationsLocked(
            JarvisRuntime.settings.security.value,
            DeviceSecure.isSecure(this),
        )
        val words = CallRecordRules.noticeWords(
            locked = locked,
            appName = getString(R.string.app_name),
            title = title,
            text = text,
        )
        val stop = PendingIntent.getService(
            this, 21,
            Intent(this, CallRecordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 22,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(words[0])
            .setContentText(words[1])
            .setStyle(NotificationCompat.BigTextStyle().bigText(words[1]))
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            .addAction(0, STOP_LABEL, stop)
            .build()
    }

    /** Put the notification up (and keep the service in the foreground). False when Android refused. */
    private fun foreground(): Boolean = try {
        ServiceCompat.startForeground(
            this,
            NotificationIds.CALL_RECORD,
            build(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
        )
        true
    } catch (e: Exception) {
        // Android 14+ refuses a microphone service started from the
        // background, or the permission is off. Said, never retried.
        Log.w(TAG, "startForeground refused", e)
        stopWords = "Android did not let call recording run. A microphone service can only start with Jarvis open on screen."
        running = false
        false
    }

    private fun publish() {
        // The recording in progress is not "waiting to send": it is this call.
        val live = session
        val waiting = store?.unsent()?.count { it.hasAudio() && it !== live } ?: 0
        CallRecordNow.publish(
            CallRecordNow.Status(
                phase = state.phase,
                startedAtMs = state.startedAtMs,
                elapsedMs = if (state.phase == CallRecordRules.Phase.RECORDING) {
                    SystemClock.elapsedRealtime() - startedRealtime
                } else {
                    0L
                },
                waiting = waiting,
                said = stopWords,
                speaker = speakerOn,
            ),
        )
        if (running && (state.phase == CallRecordRules.Phase.RECORDING || state.phase == CallRecordRules.Phase.ARMED)) {
            foreground()
        }
    }

    /**
     * Apply one event through the rules, and put the phone back when the rules
     * say the recording is over. The service never decides a transition
     * itself - that is what makes the state machine testable.
     */
    private fun apply(event: CallRecordRules.Event) {
        val step = CallRecordRules.next(state, event)
        state = step.state
        for (effect in step.effects) {
            when (effect) {
                CallRecordRules.Effect.CLAIM_MIC -> MicNow.arm()
                CallRecordRules.Effect.RELEASE_MIC -> {
                    MicNow.closed(MicOwner.Use.CALL_RECORD)
                    MicNow.disarm()
                }
                CallRecordRules.Effect.STOP_CAPTURE -> closeRecorder()
                CallRecordRules.Effect.KEEP_QUEUE -> announceWaiting()
                CallRecordRules.Effect.DISCARD -> {
                    session?.let {
                        val bytes = it.bytes()
                        it.remove()
                        Log.i(TAG, "discarded a $bytes byte recording that was under a second")
                    }
                    session = null
                }
                CallRecordRules.Effect.SAY_ARMED -> stopWords = null
                CallRecordRules.Effect.SAY_RECORDING -> stopWords = null
                CallRecordRules.Effect.SAY_STOPPED -> stopWords = stopWords ?: CallRecordRules.STOPPED_TEXT
                CallRecordRules.Effect.SAY_SENT,
                CallRecordRules.Effect.SAY_WAITING -> Unit
                // The service is already the foreground service; capture and
                // upload are started by their own callers, because both need
                // this class's own state and scope.
                CallRecordRules.Effect.START_SERVICE,
                CallRecordRules.Effect.START_CAPTURE,
                CallRecordRules.Effect.FINISH,
                CallRecordRules.Effect.STOP_SERVICE -> Unit
            }
        }
        if (state.phase == CallRecordRules.Phase.OFF) releaseSpeaker()
    }

    companion object {
        private const val TAG = "JarvisCallRecord"

        /** Its own channel: a recording has its own words and its own importance. */
        const val CHANNEL_ID = "jarvis_call_record"

        /** The waiting notice's own channel. */
        const val WAITING_CHANNEL_ID = "jarvis_call_record_waiting"

        private const val STOP_LABEL = "Stop"

        const val ACTION_ARM = "com.jarvis.client.CALL_RECORD_ARM"
        const val ACTION_STOP = "com.jarvis.client.CALL_RECORD_STOP"
        const val ACTION_SEND_WAITING = "com.jarvis.client.CALL_RECORD_SEND"
        /** The owner's own discard, from the plate's confirmed Delete. */
        const val ACTION_DISCARD = "com.jarvis.client.CALL_RECORD_DISCARD"

        /** 16 kHz, as the contract's `sample_rate`. */
        private const val RATE = CallRecordRules.SAMPLE_RATE

        /** One read: 100 ms of audio, so a chunk is cut about every 2 s. */
        private const val READ_SAMPLES = 1_600

        /** How often the audio mode is looked at. A call cannot be missed for longer than this. */
        private const val POLL_MS = 500L

        /** How often a recording in progress nudges the uploader. */
        private const val UPLOAD_NUDGE_MS = 1_000L

        /** How many times a send is tried before the phone says it is waiting. */
        private const val FINISH_ATTEMPTS = 6
        private const val SEND_NOW_ATTEMPTS = 3

        /** The longest wait between tries: 16 s. */
        private const val MAX_BACKOFF_MS = 16_000L

        /** Said when the microphone stops answering, in its own words. */
        private const val MIC_STOPPED_WORDS = "The microphone stopped answering, so the recording ended."

        /** The channel, made once when the service is created. */
        fun ensureChannel(context: Context) {
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            runCatching {
                manager.createNotificationChannel(
                    NotificationChannel(CHANNEL_ID, "Call recording", NotificationManager.IMPORTANCE_LOW).apply {
                        description = "The one notification shown while Jarvis records a phone call, with Stop " +
                            "and the reminder to tell the other person."
                        setShowBadge(false)
                    },
                )
            }
        }

        /**
         * "Call recording kept on this phone", posted when the PC could not be
         * reached. Its own notification (not the ongoing one), so it survives
         * the service stopping, and it says the audio is safe.
         */
        fun noticeWaiting(context: Context) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                return
            }
            val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
            runCatching {
                manager.createNotificationChannel(
                    NotificationChannel(
                        WAITING_CHANNEL_ID,
                        "Call recordings waiting",
                        NotificationManager.IMPORTANCE_DEFAULT,
                    ).apply { setShowBadge(true) },
                )
                val open = PendingIntent.getActivity(
                    context, 23,
                    Intent(context, MainActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                val locked = SecurityRules.notificationsLocked(
                    JarvisRuntime.settings.security.value,
                    DeviceSecure.isSecure(context),
                )
                val words = CallRecordRules.noticeWords(
                    locked = locked,
                    appName = context.getString(R.string.app_name),
                    title = CallRecordRules.WAITING_TITLE,
                    text = CallRecordRules.WAITING_TEXT,
                )
                manager.notify(
                    NotificationIds.CALL_RECORD_WAITING,
                    NotificationCompat.Builder(context, WAITING_CHANNEL_ID)
                        .setLocalOnly(true)
                        .setSmallIcon(R.drawable.ic_notification)
                        .setContentTitle(words[0])
                        .setContentText(words[1])
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                        .setCategory(NotificationCompat.CATEGORY_STATUS)
                        .setContentIntent(open)
                        .build(),
                )
            }
        }

        /** Is there anything on this phone the PC has not taken? The plate asks. */
        fun waitingCount(context: Context): Int = runCatching {
            CallRecordStore(CallRecordStore.folder(context.filesDir)).unsent().count { it.hasAudio() }
        }.getOrDefault(0)
    }
}
