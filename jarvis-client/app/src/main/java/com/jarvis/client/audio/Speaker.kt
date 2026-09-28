package com.jarvis.client.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTimestamp
import android.media.AudioTrack
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

/**
 * Jarvis's voice, from whichever end has one.
 *
 * `/api/voice/say` may answer **503**, and that is a legitimate answer rather
 * than a failure. But the sentence that used to sit here - "speaking text the
 * client already holds reveals nothing" - was false, and it was the whole
 * argument for the fallback below.
 *
 * Handing text to `TextToSpeech` with an empty params Bundle uses whatever
 * engine is default, and on a stock handset that is Google's, which may
 * synthesise **over the network**. The text being spoken is Jarvis's reply,
 * composed from the owner's recalled facts. So the "local" fallback was
 * uploading exactly what rule 1 says never leaves the machine, on the normal
 * path, because the server's speech module is not installed and every voice
 * route is on its failure path on every request.
 *
 * (Written as "every voice route" on purpose. Kotlin block comments NEST, so
 * the literal route glob - a slash, "api/voice", a slash, a star - opens an
 * inner comment inside this KDoc, and the closing marker below then shuts
 * only that inner one. The whole file after it became comment, the Speaker
 * class was never declared, and five "unresolved reference" errors in two
 * other files were all downstream of it. Java does not nest block comments;
 * Kotlin does.)
 *
 * Two things now hold instead. The server says whether substituting our own
 * voice is acceptable at all (`client_fallback_ok`), and [speakOnDevice]
 * refuses to speak through anything that needs a network connection. Silence
 * with the reply on screen is a correct outcome; uploading it is not.
 *
 * Either way the level is published on [level] and handed to the face's
 * `setSpeechLevel`, so the reactor moves with the actual voice. When no level
 * arrives for half a second the face substitutes its own speech-shaped
 * envelope, so a device whose engine reports no audio still looks right — just
 * not with *his* cadence.
 *
 * Lip-sync (docs/LIPSYNC.md): the PC's clip is analysed whole into a mouth
 * track ([LipSync.forClip]: the clip's own analysis, with the PC's mouth
 * shapes from the voice engine's timing when the WAV carries them) before it
 * plays, and [mouthNow] reads that track
 * at the moment the owner is actually HEARING - the AudioTrack's own
 * presentation clock ([PresentedFrames]), not what has been written to it,
 * which runs ahead by the whole output path. [level] comes from the same
 * track at the same moment, so every face moves with the voice, not before it.
 */
class Speaker(private val context: Context) {

    private val _level = MutableStateFlow<Float?>(null)

    /**
     * 0..1 while speaking, null when silent. The face owns the envelope.
     *
     * For the PC's voice, the analysed clip's loudness at the moment being
     * heard (see [mouthNow], which the face reads first, every frame). For
     * the phone's own voice, the RMS of each chunk as the engine makes it -
     * ahead of the sound; [mouthNow] times that voice too.
     */
    val level: StateFlow<Float?> = _level.asStateFlow()

    private var tts: TextToSpeech? = null
    @Volatile private var track: AudioTrack? = null

    /**
     * Where the clip [play] is playing has got to, for [mouthNow]: the last
     * reading of the track's clock and the clip's mouth track. Replaced
     * whole (never changed in place) by [play]'s thread every few tens of
     * milliseconds, so a reader gets one consistent reading from one
     * volatile read. Null when [play] is not playing.
     */
    @Volatile private var heard: Heard? = null

    /** The phone's own voice as it arrives ([speakOnDevice]); null otherwise. */
    @Volatile private var onDevice: SpeechEnvelope? = null
    @Volatile private var onDeviceFloat = false

    private class Heard(
        val lips: LipSync.Track,
        val rate: Int,
        /** Frames presented at [atNanos]. */
        val frames: Long,
        val atNanos: Long,
        /** False while the reply is held (paused): no voice is sounding. */
        val running: Boolean,
        /** Frames written so far - nothing past this can be heard yet. */
        val limit: Long,
    )

    /**
     * Jarvis's voice at the moment being heard, for the face - called every
     * frame, on the UI thread, so it only reads volatiles and the clock:
     * no lock, no allocation, no call into the audio system.
     *
     * Writes level, open, wide, round (each 0..1, the [LipSync.sample]
     * layout) into [out], which must hold at least 4, and returns true while
     * a real voice is playing - including its silent gaps, where the mouth
     * is closed (zeros) but a voice is still on. False, with zeros, when
     * nothing is playing, while the reply is held, and after [stop]: then the
     * face has no real voice to follow, and the animals keep their mouths
     * shut (a typed answer, Quiet mode, an answer kept on screen).
     *
     * The PC's voice gets the full mouth (open, wide, round) from the
     * analysed clip. The phone's own fallback voice gets an estimate of the
     * opening from loudness only - see [SpeechEnvelope] for why.
     */
    fun mouthNow(out: FloatArray): Boolean {
        if (!cancelled) {
            val h = heard
            if (h != null) {
                if (h.running && !paused) {
                    val t = HeardClock.seconds(h.frames, h.atNanos, System.nanoTime(), h.rate, true, h.limit)
                    // Outside the clip (its first lead-in, its very end) this
                    // writes zeros: a voice is on, the mouth is closed.
                    LipSync.sample(h.lips, t, out)
                    return true
                }
            } else {
                val e = onDevice
                if (e != null && e.sample(System.nanoTime(), out)) return true
            }
        }
        out[0] = 0f; out[1] = 0f; out[2] = 0f; out[3] = 0f
        return false
    }

    /**
     * One clip playing through [play]: its mouth track and the track's clock.
     * Used only on [play]'s own thread.
     */
    private inner class Playback(
        private val out: AudioTrack,
        private val rate: Int,
        private val lips: LipSync.Track?,
    ) {
        private val presented = PresentedFrames(rate)
        private val stamp = AudioTimestamp()
        private val scratch = FloatArray(4)

        /** Frames handed to the track so far. */
        var written = 0L

        /** The track was told to play - at the start and after each pause. */
        fun started() = presented.started(System.nanoTime())

        /**
         * Reads the track's clock, publishes it for [mouthNow], and sets
         * [level] from the mouth track at the moment being heard. False when
         * there is no mouth track (the analysis failed), so the caller keeps
         * the old per-chunk level instead.
         */
        fun refresh(running: Boolean): Boolean {
            val l = lips ?: return false
            val now = System.nanoTime()
            val ok = runCatching { out.getTimestamp(stamp) }.getOrDefault(false)
            val head = runCatching { out.playbackHeadPosition.toLong() and 0xFFFF_FFFFL }.getOrDefault(0L)
            val frames = presented.at(now, ok, stamp.framePosition, stamp.nanoTime, head)
            heard = Heard(l, rate, frames, now, running, written)
            if (running) {
                LipSync.sample(l, frames.toFloat() / rate, scratch)
                _level.value = scratch[0]
            }
            return true
        }
    }
    @Volatile private var cancelled = false

    /**
     * Paused while the PC checks whether the owner is talking over Jarvis
     * (interrupting by talking, voice/VoiceFlow.kt): [play] holds where it
     * is - the sound already queued in the track is paused too - until
     * [resume], or [stop] ends it. Only [play]'s path (the PC's voice) can
     * pause; the phone's own fallback voice ([speakOnDevice]) plays on.
     */
    @Volatile private var paused = false

    /**
     * Play as a voice call, so the phone's echo canceller can take Jarvis's
     * voice back out of what the microphone hears (barge-in: "stop" or "hey
     * Jarvis" while it talks). Set by the "hey Jarvis" listener only while
     * it listens through the echo canceller.
     *
     * Android's echo canceller works from what is being played on the
     * voice-call path, so the reply is played with USAGE_VOICE_COMMUNICATION
     * while the phone is in communication mode, and sent to the loudspeaker
     * (communication audio otherwise goes to the earpiece). [beginVoiceCall]
     * and [endVoiceCall] bracket a whole reply, so the phone does not switch
     * modes between sentences. Off, everything is exactly as before.
     */
    @Volatile var voiceCall: Boolean = false
        private set

    @Volatile private var leaveCall: (() -> Unit)? = null

    /** Before a reply is spoken: play it as a voice call (see [voiceCall]). */
    fun beginVoiceCall() {
        if (voiceCall) return
        voiceCall = true
        leaveCall = enterCall()
    }

    /** After it: everything back as it was. Safe to call twice. */
    fun endVoiceCall() {
        voiceCall = false
        val undo = leaveCall
        leaveCall = null
        undo?.invoke()
    }

    private fun usage(): Int =
        if (voiceCall) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_ASSISTANT

    /** Enters communication mode on the loudspeaker; returns how to undo it, or null. */
    private fun enterCall(): (() -> Unit)? {
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return null
        val before = manager.mode
        return runCatching {
            manager.mode = AudioManager.MODE_IN_COMMUNICATION
            val speakerOut = manager.availableCommunicationDevices
                .firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
            // A headset, if one is connected, is left alone: Android picks it.
            // Every kind the owner might wear or have chosen, not only wired
            // and Bluetooth: a USB-C headset and a hearing aid were forced
            // back onto the loudspeaker. A Bluetooth LE speaker is not worn,
            // but it is an output the owner connected on purpose, so it is
            // left alone too. All of these exist at minSdk 33 (USB headset
            // API 26, hearing aid 28, the two BLE types 31).
            val headset = manager.availableCommunicationDevices.any { it.type in OWN_OUTPUTS }
            if (speakerOut != null && !headset) manager.setCommunicationDevice(speakerOut)
            val undo: () -> Unit = {
                runCatching { manager.clearCommunicationDevice() }
                runCatching { manager.mode = before }
            }
            undo
        }.getOrElse {
            Log.w(TAG, "could not enter communication mode", it)
            runCatching { manager.mode = before }
            null
        }
    }

    /**
     * Clears the stop flag. Call once per turn, BEFORE anything is spoken.
     *
     * This exists because [play] and [speakOnDevice] used to clear it
     * themselves, on entry - which quietly erased a cancel that had already
     * arrived. A reply is spoken sentence by sentence as it streams
     * (`VoiceSession.speakStreamed`), so each sentence is a separate [play];
     * the owner sliding to cancel during sentence one set the flag, and
     * sentence two - already past its `api.say` and entering [play] - wiped
     * it and spoke in full. `play`'s write loop has no suspension point, so
     * cancelling the coroutine could not stop it either. Jarvis finished a
     * sentence out loud after being told to stop.
     *
     * Arming here and nowhere else means the flag only ever clears when a
     * new turn genuinely begins.
     */
    fun arm() {
        cancelled = false
        paused = false
        ducked = false
    }

    /**
     * Jarvis Live: another voice while Jarvis talks LOWERS it while the PC
     * checks whose voice it was (voice.LiveRules.barge) - it stops only for
     * the owner. Cleared by [arm] and [duck] (false).
     */
    @Volatile private var ducked = false

    fun duck(on: Boolean) {
        ducked = on
        runCatching { track?.setVolume(if (on) com.jarvis.client.voice.LiveRules.DUCK_VOLUME else 1f) }
    }

    /** Holds the reply where it is (see [paused]). */
    fun pause() {
        paused = true
    }

    /** Carries on from where [pause] held it. */
    fun resume() {
        paused = false
    }

    /**
     * A short sound of the phone's own - "I heard you" (voice/VoiceFlow.kt
     * `HeardSound`) - played once and forgotten. Not a reply: it neither
     * reads nor clears the stop flag, and nothing waits for it. A failure is
     * logged and ignored; the sound is a courtesy.
     */
    fun playTone(pcm: ShortArray, rate: Int) {
        if (pcm.isEmpty()) return
        runCatching {
            val out = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build(),
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build(),
                )
                .setTransferMode(AudioTrack.MODE_STATIC)
                .setBufferSizeInBytes(pcm.size * 2)
                .build()
            out.write(pcm, 0, pcm.size)
            // Released once it has played (a static track plays from its
            // own buffer): the marker fires at the last frame.
            out.notificationMarkerPosition = pcm.size
            out.setPlaybackPositionUpdateListener(object : AudioTrack.OnPlaybackPositionUpdateListener {
                override fun onMarkerReached(track: AudioTrack?) {
                    runCatching { track?.release() }
                }

                override fun onPeriodicNotification(track: AudioTrack?) = Unit
            })
            out.play()
        }.onFailure { Log.w(TAG, "could not play the heard-you sound", it) }
    }

    /**
     * Plays a WAV the desktop synthesised. The level and the mouth come from
     * the whole clip, analysed before it plays, read at the moment heard.
     */
    suspend fun play(wav: ByteArray) = withContext(Dispatchers.IO) {
        // Re-checked here, not cleared. See [arm].
        if (cancelled) return@withContext
        val pcm = runCatching { Wav.decode(wav) }.getOrNull() ?: return@withContext
        val rate = runCatching { Wav.rateOf(wav) }.getOrDefault(Wav.SAMPLE_RATE)
        // The whole clip, analysed up front: a few milliseconds for a
        // sentence, done before the first sample sounds. Guarded like the
        // decode - a failure here costs the mouth, never the voice. When the
        // PC put the voice engine's own mouth shapes in the WAV (the "jmth"
        // chunk after the sound), they shape the mouth; the level is still
        // this clip's own. Without them it is the analysis alone.
        val lips = runCatching { LipSync.forClip(wav, pcm, rate) }.getOrNull()
        val minBuf = AudioTrack.getMinBufferSize(
            rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT,
        ).coerceAtLeast(4096)

        // Inside the try. `build()` throws when the native track cannot be
        // created — a rate the device will not open, or the audio HAL briefly
        // out of tracks because another app holds them — and it sat outside the
        // guard that would have cleaned up, so the throw escaped `play`,
        // `speak`, `deliver` and the launch, and killed the process mid-answer.
        val out = runCatching {
            AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(usage())
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build(),
                )
                .setBufferSizeInBytes(minBuf)
                .build()
        }.getOrElse {
            Log.w(TAG, "could not open an audio track", it)
            return@withContext
        }
        track = out

        // Audio focus, asked for and given back. Without it Jarvis spoke over
        // music and phone calls and was neither ducked nor paused by them:
        // USAGE_ASSISTANT describes the stream to the mixer, it does not ask
        // the other apps to make room. TRANSIENT_MAY_DUCK is the assistant
        // shape - music dips while he talks and comes back when he stops.
        // A refused request still plays; focus is a courtesy to other apps,
        // not a permission to speak.
        val focus = requestFocus()
        val playback = Playback(out, rate, lips)

        try {
            out.play()
            playback.started()
            if (ducked) runCatching { out.setVolume(com.jarvis.client.voice.LiveRules.DUCK_VOLUME) }
            var i = 0
            val chunk = 1024
            while (i < pcm.size && !cancelled) {
                // Held while the PC checks an interruption: the track too, so
                // what is already queued in it stops sounding at once.
                if (paused) holdWhilePaused(out, playback)
                if (cancelled) break
                val n = minOf(chunk, pcm.size - i)
                // write() returns a NEGATIVE error code rather than throwing, so
                // a non-positive result is the end of the road, not a short write.
                val written = out.write(pcm, i, n)
                if (written <= 0) break
                playback.written = (i + written).toLong()
                // The level at what is being HEARD, from the analysed clip.
                // It used to be this chunk's RMS - the chunk just queued,
                // which the owner hears a whole buffer and output path later.
                if (!playback.refresh(running = true)) _level.value = Wav.rms(pcm.copyOfRange(i, i + n))
                i += written
            }
            // Let the last buffer drain. write() returns when the samples
            // are QUEUED, not when they have been heard, and stop() in the
            // finally below discards whatever is still queued - so the last
            // word of every reply was clipped by up to one buffer. Bounded,
            // so a track that never advances (a HAL that stalled) cannot hold
            // the voice loop; and skipped on cancel, where cutting the tail
            // is the whole point.
            if (!cancelled && i > 0) drain(out, i, playback)
        } catch (e: IllegalStateException) {
            Log.w(TAG, "playback failed", e)
        } finally {
            // Before the track goes: the face must not read a clock that
            // has stopped.
            heard = null
            runCatching { out.stop() }
            out.release()
            track = null
            _level.value = null
            abandonFocus(focus)
        }
    }

    /** Pauses [out] until [resume] or [stop]; then plays on (unless stopped). */
    private suspend fun holdWhilePaused(out: AudioTrack, playback: Playback) {
        runCatching { out.pause() }
        // Held where it is: the mouth closes and stays at this point of the clip.
        playback.refresh(running = false)
        _level.value = null
        while (paused && !cancelled) delay(PAUSE_POLL_MS)
        if (!cancelled) {
            runCatching { out.play() }
            playback.started()
            playback.refresh(running = true)
        }
    }

    /** Waits until the track has played [frames] frames, or a short bound passes. */
    private suspend fun drain(out: AudioTrack, frames: Int, playback: Playback) {
        var deadline = System.currentTimeMillis() + DRAIN_MAX_MS
        while (!cancelled && System.currentTimeMillis() < deadline) {
            if (paused) {
                // A pause during the tail: held, and the wait starts again after.
                holdWhilePaused(out, playback)
                deadline = System.currentTimeMillis() + DRAIN_MAX_MS
                continue
            }
            val head = runCatching { out.playbackHeadPosition }.getOrDefault(Int.MAX_VALUE)
            if (head >= frames) return
            // The tail is still being heard: keep the face's clock fresh.
            playback.refresh(running = true)
            delay(DRAIN_POLL_MS)
        }
    }

    /**
     * Called when something else takes the audio focus while Jarvis is
     * speaking (a call ringing or starting). Jarvis Live uses it to stop
     * talking and pause for the call (JarvisRuntime.liveFocusLost - which
     * checks the phone's call state itself, so a focus change of Jarvis's
     * own is never taken for a call).
     */
    @Volatile var onFocusLost: (() -> Unit)? = null

    private fun requestFocus(): AudioFocusRequest? {
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return null
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(usage())
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setOnAudioFocusChangeListener { change ->
                if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
                    runCatching { onFocusLost?.invoke() }
                }
            }
            .build()
        val granted = runCatching { manager.requestAudioFocus(request) }
            .getOrDefault(AudioManager.AUDIOFOCUS_REQUEST_FAILED)
        return if (granted == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) request else null
    }

    private fun abandonFocus(request: AudioFocusRequest?) {
        if (request == null) return
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
        runCatching { manager.abandonAudioFocusRequest(request) }
    }

    /**
     * Android's own voice, used when the desktop has no engine.
     *
     * `onAudioAvailable` gives real levels where the engine supports it; where
     * it does not, the level simply never arrives and the face falls back to
     * its synthetic envelope, which is the behaviour the spec already
     * specifies for exactly this case.
     */
    /**
     * Speaks, but only through a voice that does not touch the network.
     *
     * Returns false when there is no such voice - no engine, or every voice on
     * the handset is cloud-backed. The caller must then show the text and say
     * the voice is unavailable, NOT fall back to the default engine.
     */
    suspend fun speakOnDevice(text: String): Boolean {
        if (text.isBlank()) return true
        // Refused rather than cleared, for the reason in [arm]: a cancel that
        // arrived while the previous sentence was playing must survive into
        // this one.
        if (cancelled) return false
        val engine = ensureTts() ?: return false

        // Chosen explicitly, never left to the engine default. `voices` can
        // return null, and can throw on a few OEM engines, so it is guarded.
        val offline = runCatching {
            engine.voices.orEmpty().filter { v ->
                !v.isNetworkConnectionRequired &&
                    TextToSpeech.Engine.KEY_FEATURE_NETWORK_SYNTHESIS !in v.features.orEmpty()
            }
        }.getOrDefault(emptyList())

        val wanted = java.util.Locale.getDefault().language
        val voice = offline.firstOrNull { it.locale.language == wanted } ?: offline.firstOrNull()
        if (voice == null) {
            Log.w(TAG, "no on-device voice; refusing to speak rather than synthesising remotely")
            return false
        }
        if (runCatching { engine.setVoice(voice) }.getOrNull() != TextToSpeech.SUCCESS) {
            Log.w(TAG, "could not select the on-device voice; refusing to speak")
            return false
        }

        speakThrough(engine, text)
        return true
    }

    private suspend fun speakThrough(engine: TextToSpeech, text: String) {
        // Re-checked after init. `stop()` during the ~1s first-run engine setup
        // set the flag, and nothing read it again before speaking — so Jarvis
        // could start talking after the owner had cancelled.
        if (cancelled) return
        // A fresh mouth for this sentence; the last one's must not carry over.
        onDevice = null
        onDeviceFloat = false
        suspendCancellableCoroutine { cont ->
            val id = "jarvis-${System.nanoTime()}"
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) { _level.value = 0f }

                /** Whether the engine described its audio (below) for this utterance. */
                @Volatile private var began = false

                // How the engine's audio is laid out, before the first of it.
                // Only this utterance's: a flushed earlier one can still be
                // reporting on the same engine.
                override fun onBeginSynthesis(
                    utteranceId: String?,
                    sampleRateInHz: Int,
                    audioFormat: Int,
                    channelCount: Int,
                ) {
                    if (utteranceId != id) return
                    began = true
                    onDeviceFloat = audioFormat == AudioFormat.ENCODING_PCM_FLOAT
                    // 8-bit is not decoded; its mouth stays shut rather than wrong.
                    onDevice = if (audioFormat == AudioFormat.ENCODING_PCM_8BIT) {
                        null
                    } else {
                        SpeechEnvelope(sampleRateInHz.takeIf { it in 4_000..192_000 } ?: Wav.SAMPLE_RATE, channelCount)
                    }
                }

                override fun onAudioAvailable(utteranceId: String?, audio: ByteArray?) {
                    if (audio == null || audio.size < 2) return
                    // The level as before (the chunk as it arrives). The face
                    // reads [mouthNow] first, which times this voice to when
                    // it is heard rather than when it was made.
                    if (!onDeviceFloat) {
                        val shorts = ShortArray(audio.size / 2) { i ->
                            ((audio[i * 2].toInt() and 0xFF) or (audio[i * 2 + 1].toInt() shl 8)).toShort()
                        }
                        _level.value = Wav.rms(shorts)
                    }
                    if (utteranceId != id) return
                    val now = System.nanoTime()
                    // An engine that never described its audio: the usual
                    // 16-bit mono, at the rate most engines use.
                    val e = onDevice ?: if (began) null else SpeechEnvelope(Wav.SAMPLE_RATE).also { onDevice = it }
                    if (onDeviceFloat) e?.addFloat(audio, now) else e?.add16(audio, now)
                }

                override fun onDone(utteranceId: String?) {
                    if (utteranceId == id) onDevice = null
                    _level.value = null
                    // The engine outlives the utterance, and this listener
                    // holds a continuation; left registered it kept the
                    // finished turn's coroutine reachable.
                    runCatching { engine.setOnUtteranceProgressListener(null) }
                    if (cont.isActive) cont.resume(Unit)
                }

                @Deprecated("Required by the abstract class", ReplaceWith(""))
                override fun onError(utteranceId: String?) {
                    onDevice = null
                    _level.value = null
                    if (cont.isActive) cont.resume(Unit)
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    onDevice = null
                    _level.value = null
                    if (cont.isActive) cont.resume(Unit)
                }
            })
            val params = Bundle()
            // The same voice-call path as [play] while barge-in listens, so
            // the echo canceller has this voice to take back out too.
            runCatching {
                engine.setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(usage())
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
            }
            val queued = engine.speak(text, TextToSpeech.QUEUE_FLUSH, params, id)
            // A rejected utterance is not guaranteed any callback at all on
            // every OEM engine - `onError` is documented for a FAILURE
            // during synthesis, not for `speak()` itself refusing to queue
            // one. Without this, that path left the listener registered and
            // the continuation suspended forever: a Jarvis reply that failed
            // to queue never resumed the voice loop for any later turn.
            if (queued != TextToSpeech.SUCCESS) {
                Log.w(TAG, "speak() refused the utterance (code $queued)")
                onDevice = null
                _level.value = null
                runCatching { engine.setOnUtteranceProgressListener(null) }
                if (cont.isActive) cont.resume(Unit)
                return@suspendCancellableCoroutine
            }
            cont.invokeOnCancellation { runCatching { engine.stop() }; onDevice = null; _level.value = null }
        }
    }

    /** Stops whichever path is speaking. */
    fun stop() {
        cancelled = true
        paused = false
        // The mouth closes now, not when [play]'s loop next looks.
        heard = null
        onDevice = null
        runCatching { track?.pause() }
        runCatching { tts?.stop() }
        _level.value = null
    }

    fun release() {
        stop()
        runCatching { tts?.shutdown() }
        tts = null
    }

    private suspend fun ensureTts(): TextToSpeech? {
        tts?.let { return it }
        return suspendCancellableCoroutine { cont ->
            var engine: TextToSpeech? = null
            engine = TextToSpeech(context) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    tts = engine
                    if (cont.isActive) cont.resume(engine) else runCatching { engine?.shutdown() }
                } else {
                    // Shut down, not just dropped. A TextToSpeech holds a bound
                    // ServiceConnection; on a device with no engine data this
                    // branch ran once per voice turn and leaked a binding each
                    // time, for the life of the process.
                    Log.w(TAG, "no local text-to-speech engine")
                    runCatching { engine?.shutdown() }
                    if (cont.isActive) cont.resume(null)
                }
            }
            // Cancelled while waiting for first-run init — which takes about a
            // second — left the engine built inside this block with nobody to
            // shut it down.
            cont.invokeOnCancellation { runCatching { engine?.shutdown() } }
        }
    }

    private companion object {
        const val TAG = "JarvisSpeaker"

        /** Outputs the voice-call mode must not override with the loudspeaker. */
        val OWN_OUTPUTS = setOf(
            AudioDeviceInfo.TYPE_WIRED_HEADSET,
            AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
            AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_BLE_SPEAKER,
            AudioDeviceInfo.TYPE_USB_HEADSET,
            AudioDeviceInfo.TYPE_HEARING_AID,
        )

        /** Longest the tail is waited for; one buffer is a few tens of ms. */
        const val DRAIN_MAX_MS = 1_500L
        const val DRAIN_POLL_MS = 20L

        /** How often a paused reply looks again for resume or stop. */
        const val PAUSE_POLL_MS = 20L
    }
}
