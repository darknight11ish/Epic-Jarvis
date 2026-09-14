package com.jarvis.client.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import kotlinx.coroutines.Dispatchers
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
 * than a failure: speaking text the client already holds reveals nothing and
 * skips no check, which is exactly why this half of the voice path is allowed
 * to be missing and the other half is not. So a 503 falls through to Android's
 * own synthesiser and nothing is weakened by it.
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
        } catch (e: IllegalStateException) {
            Log.w(TAG, "playback failed", e)
        } finally {
            runCatching { out.stop() }
            out.release()
            track = null
            _level.value = null
        }
    }

    /**
     * Android's own voice, used when the desktop has no engine.
     *
     * `onAudioAvailable` gives real levels where the engine supports it; where
     * it does not, the level simply never arrives and the face falls back to
     * its synthetic envelope, which is the behaviour the spec already
     * specifies for exactly this case.
     */
    suspend fun speakLocally(text: String) {
        if (text.isBlank()) return
        cancelled = false
        val engine = ensureTts() ?: return
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
    }
}
