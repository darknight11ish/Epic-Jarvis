package com.jarvis.assistant.audio

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Microphone capture at 16 kHz / 16-bit / mono, pushed to the desktop as raw PCM.
 *
 * Uses VOICE_COMMUNICATION so the platform applies echo cancellation and noise
 * suppression — without it the handset's own speaker output feeds straight back
 * into the uplink during duplex playback.
 */
class AudioStreamer(
    private val context: Context,
    private val onChunk: (ByteArray, Int) -> Unit,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val running = AtomicBoolean(false)
    private var job: Job? = null
    private var record: AudioRecord? = null

    val isRecording: Boolean get() = running.get()

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    /** @return true when capture actually started. */
    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        if (running.get()) return true
        if (!hasPermission()) {
            Log.w(TAG, "RECORD_AUDIO not granted")
            return false
        }

        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
        if (minBuffer <= 0) {
            Log.e(TAG, "unsupported capture configuration")
            return false
        }
        val bufferSize = maxOf(minBuffer * 2, CHUNK_BYTES * 2)

        val recorder = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                CHANNEL,
                ENCODING,
                bufferSize,
            )
        } catch (e: Exception) {
            Log.e(TAG, "AudioRecord construction failed", e)
            return false
        }

        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialise")
            recorder.release()
            return false
        }

        // Inside the try, and before `running` is set: startRecording throws when
        // the microphone is held exclusively elsewhere (an in-progress call, a
        // concurrent-capture denial). Outside it, that throw propagated out of a
        // Compose click handler or a binder callback and left the native mic handle
        // open with isRecording still reporting true.
        try {
            recorder.startRecording()
        } catch (e: Exception) {
            Log.e(TAG, "startRecording rejected", e)
            runCatching { recorder.release() }
            return false
        }
        if (recorder.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            Log.e(TAG, "AudioRecord did not enter the recording state")
            runCatching { recorder.release() }
            return false
        }

        record = recorder
        running.set(true)

        job = scope.launch {
            val buffer = ByteArray(CHUNK_BYTES)
            try {
                while (running.get()) {
                    // Guarded for the same reason as the playback write: stop() can
                    // land while this is blocked in the native call, and nothing in
                    // this scope would catch an escaping throw.
                    val read = runCatching { recorder.read(buffer, 0, buffer.size) }
                        .getOrDefault(-1)
                    if (read > 0) {
                        onChunk(buffer, read)
                    } else if (read < 0) {
                        Log.e(TAG, "AudioRecord.read error $read")
                        break
                    }
                }
            } finally {
                // This coroutine owns the recorder and is the only thing that
                // releases it, so a release can never land under an in-flight read.
                runCatching { recorder.release() }
            }
        }
        return true
    }

    fun stop() {
        if (!running.compareAndSet(true, false)) return
        // stop() is safe to call while the reader is blocked in read() and is what
        // unblocks it; release() is left to the reader's own finally.
        record?.let { recorder ->
            runCatching {
                if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) recorder.stop()
            }
        }
        job?.cancel()
        job = null
        record = null
    }

    companion object {
        private const val TAG = "JarvisMic"
        const val SAMPLE_RATE = 16_000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT

        /** 20 ms of audio: small enough that barge-in feels instant. */
        private const val CHUNK_BYTES = SAMPLE_RATE / 50 * 2
    }
}
