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
import com.jarvis.client.voice.MicClaim
import com.jarvis.client.voice.MicOwner
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
 * **It takes the app's one microphone ledger while it records** (voice/MicOwner.kt,
 * [MicClaim]): the hands-free answer window holds it for its own ten seconds, and
 * this recorder does not open a second `AudioRecord` over a card being answered —
 * it says so, in [Failure.MicBusy], and records nothing. That is the whole of
 * "one part of this app records at a time", and it is a claim rather than a hope
 * because both sides go through the same ledger.
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

        /**
         * Another part of this app holds the microphone. [why] is a whole
         * sentence, never blank - the owner pressed the button, so a silent
         * return would read as a broken button.
         */
        data class MicBusy(val why: String) : Failure

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
    suspend fun record(
        maxSeconds: Float = 30f,
        onLevel: (Float) -> Unit = {},
        stopWhen: () -> Boolean,
        onBuffer: ((buffer: ShortArray, n: Int, captured: ShortArray, count: Int, rate: Int) -> Boolean)? = null,
    ): Result = withContext(Dispatchers.IO) {
        if (!hasPermission()) return@withContext Result.Refused(Failure.NoPermission)
        // ONE microphone, four things that want it (voice/MicOwner.kt). The
        // hands-free answer window holds it for the ten seconds it is hearing an
        // answer; opening a second AudioRecord over that gets silence, or worse,
        // and the ledger is the one place that decides. Taken BEFORE the
        // AudioRecord exists and given back in a `finally`, so a capture that
        // fails halfway cannot leave the microphone held by a button nobody is
        // pressing any more.
        when (val claim = MicClaim.take(MicOwner.TALK)) {
            MicClaim.Now.Open -> Unit
            is MicClaim.Now.Busy -> return@withContext Result.Refused(Failure.MicBusy(claim.why))
        }
        try {
            capture(maxSeconds, onLevel, stopWhen, onBuffer)
        } finally {
            MicClaim.free(MicOwner.TALK)
        }
    }

    /**
     * The capture itself, with the microphone already this part's.
     *
     * Split out of [record] so the claim and its release are one visible pair
     * that no early return can skip: every refusal below leaves the `finally`
     * above to give the ledger back.
     */
    @SuppressLint("MissingPermission") // checked in record(); the lint cannot see through it
    private fun capture(
        maxSeconds: Float,
        onLevel: (Float) -> Unit,
        stopWhen: () -> Boolean,
        onBuffer: ((buffer: ShortArray, n: Int, captured: ShortArray, count: Int, rate: Int) -> Boolean)?,
    ): Result {
        val rate = usableRate() ?: return Result.Refused(Failure.Unavailable)
        val minBuf = AudioRecord.getMinBufferSize(
            rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuf <= 0) return Result.Refused(Failure.Unavailable)

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
        }.getOrElse { return Result.Refused(Failure.Failed(it.javaClass.simpleName)) }

        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            return Result.Refused(Failure.Unavailable)
        }

        // Clamped, because this comes from the desktop. `max_seconds: 0` — or
        // a missing/garbled value — made maxSamples zero, so the read loop
        // never ran once and every capture came back TooShort: "hold the button
        // while you speak", to someone who was.
        val maxSamples = (maxSeconds.coerceIn(1f, 120f) * rate).toInt()
        // A primitive array grown by doubling rather than an ArrayList<Short>.
        // The list looks equivalent and is not: every sample would be boxed,
        // and the Short cache only covers -128..127, so an audio signal misses
        // it on essentially every sample. Thirty seconds at 48 kHz is 1.4
        // million short-lived objects — tens of megabytes of garbage collected
        // while the microphone is open, which is the one moment in this app
        // where a GC pause is audible.
        var captured = ShortArray(minOf(maxSamples, rate * 4).coerceAtLeast(1024))
        var count = 0
        val buffer = ShortArray(minBuf.coerceAtLeast(1024))

        try {
            recorder.startRecording()
            while (!stopWhen() && count < maxSamples) {
                val n = recorder.read(buffer, 0, buffer.size)
                // read() returns a NEGATIVE error code rather than throwing.
                // Treating "<= 0" as end-of-stream is what keeps a revoked
                // permission or a stolen microphone from spinning forever.
                if (n <= 0) break
                onLevel(Wav.rms(buffer, n))
                // Never past the cap: a final buffer that straddles it is
                // truncated rather than allowed to overshoot.
                val take = minOf(n, maxSamples - count)
                if (count + take > captured.size) {
                    var size = captured.size
                    while (size < count + take) size *= 2
                    captured = captured.copyOf(minOf(size, maxSamples))
                }
                System.arraycopy(buffer, 0, captured, count, take)
                count += take
                if (onBuffer?.invoke(buffer, n, captured, count, rate) == true) break
            }
        } catch (e: IllegalStateException) {
            Log.w(TAG, "capture failed", e)
            return Result.Refused(Failure.Failed(e.javaClass.simpleName))
        } finally {
            runCatching { recorder.stop() }
            recorder.release()
            onLevel(0f)
        }

        val seconds = count / rate.toFloat()
        // The server refuses below 0.2s — a gate handed 50ms of hiss produces a
        // number, and that number means nothing. Refusing here saves a round
        // trip and says the same thing sooner.
        if (seconds < MIN_SECONDS) return Result.Refused(Failure.TooShort)

        val resampled = Wav.resample(captured.copyOf(count), rate)
        return Result.Captured(Wav.encode(resampled), resampled.size / Wav.SAMPLE_RATE.toFloat())
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
