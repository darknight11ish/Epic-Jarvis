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

        record = recorder
        running.set(true)
        recorder.startRecording()

        job = scope.launch {
            val buffer = ByteArray(CHUNK_BYTES)
            while (running.get()) {
                val read = recorder.read(buffer, 0, buffer.size)
                if (read > 0) {
                    onChunk(buffer, read)
                } else if (read < 0) {
                    Log.e(TAG, "AudioRecord.read error $read")
                    break
                }
            }
        }
        return true
    }

    fun stop() {
        if (!running.compareAndSet(true, false)) return
        job?.cancel()
        job = null
        record?.let { recorder ->
            runCatching { if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) recorder.stop() }
            runCatching { recorder.release() }
        }
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
