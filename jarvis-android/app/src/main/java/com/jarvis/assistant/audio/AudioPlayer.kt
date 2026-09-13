package com.jarvis.assistant.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Low-latency playback of PCM streamed down from the desktop.
 *
 * Chunks land on a bounded channel and are drained by a single writer coroutine,
 * so a burst from the server cannot block the WebSocket reader thread.
 */
class AudioPlayer {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val playing = AtomicBoolean(false)

    private var track: AudioTrack? = null
    private var writer: Job? = null
    private var queue: Channel<ByteArray>? = null
    private var currentSampleRate = DEFAULT_SAMPLE_RATE

    val isPlaying: Boolean get() = playing.get()

    @Synchronized
    fun start(sampleRate: Int = DEFAULT_SAMPLE_RATE, channels: Int = 1) {
        if (playing.get() && sampleRate == currentSampleRate) return
        stopInternal(flush = true)

        val channelMask =
            if (channels >= 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val minBuffer = AudioTrack.getMinBufferSize(sampleRate, channelMask, ENCODING)
        if (minBuffer <= 0) {
            Log.e(TAG, "unsupported playback configuration ${sampleRate}Hz")
            return
        }

        val newTrack = try {
            AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(ENCODING)
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelMask)
                        .build(),
                )
                .setBufferSizeInBytes(minBuffer * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
                .build()
        } catch (e: Exception) {
            Log.e(TAG, "AudioTrack construction failed", e)
            return
        }

        if (newTrack.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(TAG, "AudioTrack failed to initialise")
            newTrack.release()
            return
        }

        val channel = Channel<ByteArray>(capacity = QUEUE_CAPACITY)
        currentSampleRate = sampleRate
        track = newTrack
        queue = channel
        playing.set(true)
        newTrack.play()

        writer = scope.launch {
            for (chunk in channel) {
                if (!playing.get()) break
                var offset = 0
                while (offset < chunk.size && playing.get()) {
                    val written = newTrack.write(chunk, offset, chunk.size - offset)
                    if (written <= 0) break
                    offset += written
                }
            }
        }
    }

    fun enqueue(pcm: ByteArray) {
        if (!playing.get()) start(currentSampleRate)
        val channel = queue ?: return
        val result = channel.trySend(pcm)
        if (result.isFailure) {
            Log.w(TAG, "playback queue full, dropping ${pcm.size} bytes")
        }
    }

    /** Lets whatever is already buffered finish, then tears down. */
    @Synchronized
    fun finish() {
        queue?.close()
        scope.launch {
            writer?.join()
            synchronized(this@AudioPlayer) {
                if (playing.get()) {
                    runCatching { track?.stop() }
                    stopInternal(flush = false)
                }
            }
        }
    }

    /** Barge-in: drop everything queued and silence the speaker immediately. */
    @Synchronized
    fun flushNow() {
        stopInternal(flush = true)
    }

    @Synchronized
    fun release() {
        stopInternal(flush = true)
    }

    private fun stopInternal(flush: Boolean) {
        playing.set(false)
        queue?.close()
        queue = null
        writer?.cancel()
        writer = null
        track?.let { t ->
            runCatching {
                if (t.playState != AudioTrack.PLAYSTATE_STOPPED) t.pause()
                if (flush) t.flush()
                t.stop()
            }
            runCatching { t.release() }
        }
        track = null
    }

    companion object {
        private const val TAG = "JarvisPlayer"
        const val DEFAULT_SAMPLE_RATE = 22_050
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        private const val QUEUE_CAPACITY = 256
    }
}
