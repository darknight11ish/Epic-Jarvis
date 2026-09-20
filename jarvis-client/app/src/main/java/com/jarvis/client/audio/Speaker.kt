package com.jarvis.client.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
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
 */
class Speaker(private val context: Context) {

    private val _level = MutableStateFlow<Float?>(null)

    /** 0..1 while speaking, null when silent. Raw — the face owns the envelope. */
    val level: StateFlow<Float?> = _level.asStateFlow()

    private var tts: TextToSpeech? = null
    @Volatile private var track: AudioTrack? = null
    @Volatile private var cancelled = false

    /** Plays a WAV the desktop synthesised. Real levels, straight off the samples. */
    suspend fun play(wav: ByteArray) = withContext(Dispatchers.IO) {
        cancelled = false
        val pcm = runCatching { Wav.decode(wav) }.getOrNull() ?: return@withContext
        val rate = runCatching { Wav.rateOf(wav) }.getOrDefault(Wav.SAMPLE_RATE)
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
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
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

        try {
            out.play()
            var i = 0
            val chunk = 1024
            while (i < pcm.size && !cancelled) {
                val n = minOf(chunk, pcm.size - i)
                // write() returns a NEGATIVE error code rather than throwing, so
                // a non-positive result is the end of the road, not a short write.
                val written = out.write(pcm, i, n)
                if (written <= 0) break
                _level.value = Wav.rms(pcm.copyOfRange(i, i + n))
                i += written
            }
            // Let the last buffer drain. write() returns when the samples
            // are QUEUED, not when they have been heard, and stop() in the
            // finally below discards whatever is still queued - so the last
            // word of every reply was clipped by up to one buffer. Bounded,
            // so a track that never advances (a HAL that stalled) cannot hold
            // the voice loop; and skipped on cancel, where cutting the tail
            // is the whole point.
            if (!cancelled && i > 0) drain(out, i)
        } catch (e: IllegalStateException) {
            Log.w(TAG, "playback failed", e)
        } finally {
            runCatching { out.stop() }
            out.release()
            track = null
            _level.value = null
            abandonFocus(focus)
        }
    }

    /** Waits until the track has played [frames] frames, or a short bound passes. */
    private suspend fun drain(out: AudioTrack, frames: Int) {
        val deadline = System.currentTimeMillis() + DRAIN_MAX_MS
        while (!cancelled && System.currentTimeMillis() < deadline) {
            val head = runCatching { out.playbackHeadPosition }.getOrDefault(Int.MAX_VALUE)
            if (head >= frames) return
            delay(DRAIN_POLL_MS)
        }
    }

    private fun requestFocus(): AudioFocusRequest? {
        val manager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return null
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
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
        cancelled = false
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
        suspendCancellableCoroutine { cont ->
            val id = "jarvis-${System.nanoTime()}"
            engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) { _level.value = 0f }

                override fun onAudioAvailable(utteranceId: String?, audio: ByteArray?) {
                    if (audio == null || audio.size < 2) return
                    val shorts = ShortArray(audio.size / 2) { i ->
                        ((audio[i * 2].toInt() and 0xFF) or (audio[i * 2 + 1].toInt() shl 8)).toShort()
                    }
                    _level.value = Wav.rms(shorts)
                }

                override fun onDone(utteranceId: String?) {
                    _level.value = null
                    // The engine outlives the utterance, and this listener
                    // holds a continuation; left registered it kept the
                    // finished turn's coroutine reachable.
                    runCatching { engine.setOnUtteranceProgressListener(null) }
                    if (cont.isActive) cont.resume(Unit)
                }

                @Deprecated("Required by the abstract class", ReplaceWith(""))
                override fun onError(utteranceId: String?) {
                    _level.value = null
                    if (cont.isActive) cont.resume(Unit)
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    _level.value = null
                    if (cont.isActive) cont.resume(Unit)
                }
            })
            val params = Bundle()
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, params, id)
            cont.invokeOnCancellation { runCatching { engine.stop() }; _level.value = null }
        }
    }

    /** Stops whichever path is speaking. */
    fun stop() {
        cancelled = true
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

        /** Longest the tail is waited for; one buffer is a few tens of ms. */
        const val DRAIN_MAX_MS = 1_500L
        const val DRAIN_POLL_MS = 20L
    }
}
