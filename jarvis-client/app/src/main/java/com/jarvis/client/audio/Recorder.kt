package com.jarvis.client.audio

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * One complete utterance, captured.
 *
 * Deliberately not a stream. The server takes one WAV and gives one verdict —
 * push-to-talk and the wake word are the same transport, so there is nothing to
 * stream and nothing to keep open. A capture that cannot be held open is also a
 * capture that cannot be left open by mistake.
 *
 * **Nothing here transcribes.** No `SpeechRecognizer`, no on-device model. The
 * owner voice-print gate can only check a voice if it is given the voice; send
 * text and the gate has nothing to examine, and "is this the owner?" becomes
 * "is this someone holding the owner's phone?". `/api/voice/status` carries
 * `audio_in.client_stt_allowed: false` so this is checkable rather than merely
 * promised — see `VoiceRulesTest`.
 */
class Recorder(private val context: Context) {

    /** Why a capture produced nothing. All of them are shown, none are retried. */
    sealed interface Failure {
        data object NoPermission : Failure
        data object Unavailable : Failure
        data object TooShort : Failure
        data class Failed(val detail: String) : Failure
    }

    sealed interface Result {
        data class Captured(val wav: ByteArray, val seconds: Float) : Result
        data class Refused(val why: Failure) : Result
    }

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * Records until [stopWhen] returns true, the cap is reached, or the scope
     * is cancelled.
     *
     * @param onLevel per-buffer RMS, 0..1. Fed straight to the face's listening
     *   envelope — the shell smooths it, so this must stay raw.
     */
    @SuppressLint("MissingPermission") // checked above; the lint cannot see through it
    suspend fun record(
        maxSeconds: Float = 30f,
        onLevel: (Float) -> Unit = {},
        stopWhen: () -> Boolean,
    ): Result = withContext(Dispatchers.IO) {
        if (!hasPermission()) return@withContext Result.Refused(Failure.NoPermission)

        val rate = usableRate() ?: return@withContext Result.Refused(Failure.Unavailable)
        val minBuf = AudioRecord.getMinBufferSize(
            rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuf <= 0) return@withContext Result.Refused(Failure.Unavailable)

        // VOICE_RECOGNITION, not MIC: it asks the platform for the un-beautified
        // path — no AGC ramp, no noise suppression tuned for telephony — which
        // is what a voice-print embedder wants. MIC's processing is exactly the
        // kind that makes a familiar voice score lower.
        val recorder = runCatching {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                rate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                minBuf * 4,
            )
        }.getOrElse { return@withContext Result.Refused(Failure.Failed(it.javaClass.simpleName)) }

        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            return@withContext Result.Refused(Failure.Unavailable)
        }

        val captured = ArrayList<Short>(rate * 4)
        val buffer = ShortArray(minBuf.coerceAtLeast(1024))
        val maxSamples = (maxSeconds * rate).toInt()

        try {
            recorder.startRecording()
            while (!stopWhen() && captured.size < maxSamples) {
                val n = recorder.read(buffer, 0, buffer.size)
                // read() returns a NEGATIVE error code rather than throwing.
                // Treating "<= 0" as end-of-stream is what keeps a revoked
                // permission or a stolen microphone from spinning forever.
                if (n <= 0) break
                onLevel(Wav.rms(buffer, n))
                for (i in 0 until n) captured.add(buffer[i])
            }
        } catch (e: IllegalStateException) {
            Log.w(TAG, "capture failed", e)
            return@withContext Result.Refused(Failure.Failed(e.javaClass.simpleName))
        } finally {
            runCatching { recorder.stop() }
            recorder.release()
            onLevel(0f)
        }

        val seconds = captured.size / rate.toFloat()
        // The server refuses below 0.2s — a gate handed 50ms of hiss produces a
        // number, and that number means nothing. Refusing here saves a round
        // trip and says the same thing sooner.
        if (seconds < MIN_SECONDS) return@withContext Result.Refused(Failure.TooShort)

        val pcm = ShortArray(captured.size) { captured[it] }
        val resampled = Wav.resample(pcm, rate)
        Result.Captured(Wav.encode(resampled), resampled.size / Wav.SAMPLE_RATE.toFloat())
    }

    /**
     * 16 kHz if the device will give it, otherwise something it will, resampled
     * afterwards. The brief says resample on the device and this is where.
     */
    private fun usableRate(): Int? = RATES.firstOrNull { rate ->
        val size = AudioRecord.getMinBufferSize(
            rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        size > 0
    }

    private companion object {
        const val TAG = "JarvisRecorder"
        const val MIN_SECONDS = 0.2f

        /** 16k first, so the common case needs no resampling at all. */
        val RATES = intArrayOf(16_000, 48_000, 44_100, 32_000, 22_050, 8_000).toList()
    }
}
