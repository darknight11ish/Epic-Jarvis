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
 *
 * Playback does not begin on the first byte. [PREROLL_MS] of audio is written
 * into the track first, giving the stream a jitter buffer: over cellular, packet
 * arrival is bursty, and starting immediately means the track drains faster than
 * the network refills it and the speech breaks up. The cost is a fixed startup
 * delay, which is invisible next to network and synthesis latency.
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

        val channelCount = if (channels >= 2) 2 else 1
        val channelMask =
            if (channelCount == 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val minBuffer = AudioTrack.getMinBufferSize(sampleRate, channelMask, ENCODING)
        if (minBuffer <= 0) {
            Log.e(TAG, "unsupported playback configuration ${sampleRate}Hz")
            return
        }

        val prerollBytes = sampleRate * channelCount * BYTES_PER_SAMPLE * PREROLL_MS / 1000
        // The track must hold the whole preroll plus headroom, otherwise the
        // writer blocks on a full buffer before playback has been allowed to start.
        val bufferSize = maxOf(minBuffer * 4, prerollBytes * 2)

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
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
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

        writer = scope.launch {
            var buffered = 0
            var started = false

            for (chunk in channel) {
                if (!playing.get()) break
                var offset = 0
                while (offset < chunk.size && playing.get()) {
                    val written = newTrack.write(chunk, offset, chunk.size - offset)
                    if (written <= 0) break
                    offset += written
                    buffered += written
                    if (!started && buffered >= prerollBytes) {
                        started = true
                        runCatching { newTrack.play() }
                    }
                }
            }

            // A reply shorter than the preroll still has to be heard.
            if (!started && playing.get() && buffered > 0) {
                runCatching { newTrack.play() }
            }
        }
    }

    fun enqueue(pcm: ByteArray) {
        if (!playing.get()) start(currentSampleRate)
        val channel = queue ?: return
        if (channel.trySend(pcm).isFailure) {
            Log.w(TAG, "playback queue full, dropping ${pcm.size} bytes")
        }
    }

    /** Lets whatever is already buffered finish, then tears down. */
    @Synchronized
    fun finish() {
        queue?.close()
        val pending = writer
        scope.launch {
            pending?.join()
            synchronized(this@AudioPlayer) {
                if (playing.get()) stopInternal(flush = false)
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
        private const val BYTES_PER_SAMPLE = 2
        private const val QUEUE_CAPACITY = 256

        /** Jitter budget before playback starts. */
        private const val PREROLL_MS = 120
    }
}
