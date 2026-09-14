package com.jarvis.assistant.network

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.min

enum class ConnectionState { OFFLINE, RECONNECTING, CONNECTED }

/**
 * One frame off the wire, in arrival order.
 *
 * Text and binary share a single stream deliberately. Carrying them on two flows
 * loses the ordering between them, and that ordering is load-bearing: the tail of
 * a reply is binary PCM followed by a text `audio_stream_end`, so an independently
 * collected end event clears the stream tag while frames are still queued and the
 * last of every reply is discarded. The head has the mirror problem.
 */
sealed interface SocketSignal {
    class Event(val event: InboundEvent) : SocketSignal
    class Binary(val frame: ByteArray) : SocketSignal
}

/**
 * Persistent link to the desktop server.
 *
 * Reconnects with exponential backoff (1s, 2s, 4s … capped at 30s) and pings on
 * a 25-second interval to keep the Tailscale path warm while the handset dozes.
 * Without traffic the NAT mapping is reclaimed and inbound approval requests
 * stall until the next radio wake; carrier CGNAT gateways commonly reap idle
 * mappings at 30 seconds, so the interval has to sit comfortably under that.
 *
 * The whole dial/backoff/teardown state machine runs under [lock]. It is touched
 * from the main thread, from OkHttp's reader thread and from binder threads, and
 * every field in it is a read-modify-write.
 */
class JarvisWebSocketManager private constructor() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .pingInterval(PING_SECONDS, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val _state = MutableStateFlow(ConnectionState.OFFLINE)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    /**
     * Bounded, and the producer blocks rather than discarding when it fills.
     *
     * The previous buffer dropped on overflow with a log line, which meant a burst
     * of base64 audio chunks could push an `approval_request` out of the buffer: the
     * user never saw the prompt and the desktop waited on a gate nobody could answer.
     * Blocking the reader thread instead closes the TCP window and makes the desktop
     * slow down, which is the correct place for the pressure to land.
     */
    private val signals = Channel<SocketSignal>(capacity = SIGNAL_BUFFER)
    val incoming: Flow<SocketSignal> = signals.receiveAsFlow()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var url: String? = null
    @Volatile private var authToken: String? = null
    @Volatile private var shutdown = true
    private var attempt = 0
    private var reconnectJob: Job? = null

    /**
     * Monotonic dial counter. Every [Listener] remembers the generation it was
     * created for and ignores its own callbacks once superseded, so cancelling a
     * socket to re-dial elsewhere cannot trigger a reconnect back to the old URL.
     *
     * Bumped by every path that invalidates the current socket — including
     * [openSocket] and [disconnect], both of which used to leave it alone. Leaving
     * it alone let a late `onFailure` from the previous generation schedule a second
     * dial at the *current* generation, so two sockets were live and both listeners
     * believed they were current: duplicated approvals and doubled audio.
     */
    private val generation = AtomicInteger(0)

    /** Idempotent: re-dials only when the target URL or token actually changed. */
    fun connect(wsUrl: String, token: String? = null) {
        synchronized(lock) {
            val normalizedToken = token?.takeIf { it.isNotBlank() }
            val sameTarget = url == wsUrl && authToken == normalizedToken
            // A reconnect already armed for this same target is progress, not a reason
            // to start over. Re-dialling here reset `attempt` on every caller, so the
            // backoff never grew past its first step for as long as anything polled
            // connect() — which onResume and every queued send do.
            if (!shutdown && sameTarget && (socket != null || reconnectJob?.isActive == true)) return
            url = wsUrl
            authToken = normalizedToken
            shutdown = false
            attempt = 0
            redial()
        }
    }

    fun disconnect() {
        synchronized(lock) {
            shutdown = true
            generation.incrementAndGet()
            reconnectJob?.cancel()
            reconnectJob = null
            socket?.cancel()
            socket = null
            _state.value = ConnectionState.OFFLINE
        }
    }

    /** Forces a fresh dial, e.g. after the user edits the server address. */
    fun reconnectNow() {
        synchronized(lock) {
            if (url == null) return
            shutdown = false
            attempt = 0
            redial()
        }
    }

    private fun redial() {
        reconnectJob?.cancel()
        reconnectJob = null
        openSocket()
    }

    fun send(message: OutboundMessage): Boolean {
        val ws = socket ?: return false
        return try {
            ws.send(JarvisJson.encodeToString(OutboundMessage.serializer(), message))
        } catch (e: Exception) {
            Log.w(TAG, "send failed", e)
            false
        }
    }

    /** Raw microphone PCM. Bracketed by audio_input_start / audio_input_end. */
    fun sendAudio(pcm: ByteArray, length: Int = pcm.size): Boolean {
        val ws = socket ?: return false
        return try {
            ws.send(pcm.toByteString(0, length))
        } catch (e: Exception) {
            Log.w(TAG, "audio send failed", e)
            false
        }
    }

    /** Caller must hold [lock]. */
    private fun openSocket() {
        val target = url ?: return
        if (shutdown) return
        val gen = generation.incrementAndGet()
        val stale = socket
        socket = null
        stale?.cancel()

        _state.value = ConnectionState.RECONNECTING
        val request = Request.Builder()
            .url(target)
            .apply { authToken?.let { header("Authorization", "Bearer $it") } }
            .build()
        val ws = client.newWebSocket(request, Listener(gen))
        // Re-check under the same lock: disconnect() may have bumped the generation
        // while newWebSocket was dialling, and an orphan socket here is exactly how
        // the plaintext refusal used to end up with a live link behind it.
        if (gen == generation.get() && !shutdown) socket = ws else ws.cancel()
    }

    private fun scheduleReconnect() {
        synchronized(lock) {
            if (shutdown) return
            if (reconnectJob?.isActive == true) return
            val backoff = min(BASE_BACKOFF_MS shl min(attempt, 5), MAX_BACKOFF_MS)
            attempt += 1
            _state.value = ConnectionState.RECONNECTING
            reconnectJob = scope.launch {
                delay(backoff)
                synchronized(lock) { if (!shutdown) openSocket() }
            }
        }
    }

    /**
     * Hands a frame to the consumer, blocking this reader thread if the consumer is
     * behind. Dropping is not an option here — see [signals].
     */
    private fun dispatch(signal: SocketSignal) {
        if (signals.trySend(signal).isSuccess) return
        runBlocking { signals.send(signal) }
    }

    private inner class Listener(private val gen: Int) : WebSocketListener() {

        private val current: Boolean get() = gen == generation.get()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (!current) {
                webSocket.cancel()
                return
            }
            synchronized(lock) {
                if (gen != generation.get()) {
                    webSocket.cancel()
                    return
                }
                socket = webSocket
                attempt = 0
                _lastError.value = null
                _state.value = ConnectionState.CONNECTED
            }
            Log.i(TAG, "connected to ${webSocket.request().url}")
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (!current) return
            val event = try {
                JarvisJson.decodeFromString(InboundEvent.serializer(), text)
            } catch (e: Exception) {
                // An unrecognised `type` is not fatal; the desktop may be newer.
                Log.w(TAG, "dropping unparseable frame: ${e.message}")
                return
            }
            dispatch(SocketSignal.Event(event))
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            if (!current) return
            if (bytes.size < 2) return
            dispatch(SocketSignal.Binary(bytes.toByteArray()))
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(NORMAL_CLOSURE, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (!current) return
            synchronized(lock) { if (socket === webSocket) socket = null }
            if (shutdown) _state.value = ConnectionState.OFFLINE else scheduleReconnect()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (!current) return
            synchronized(lock) { if (socket === webSocket) socket = null }
            _lastError.value = t.message ?: t::class.java.simpleName
            Log.w(TAG, "socket failure: ${_lastError.value}")
            if (shutdown) _state.value = ConnectionState.OFFLINE else scheduleReconnect()
        }
    }

    companion object {
        private const val TAG = "JarvisWS"
        private const val PING_SECONDS = 25L
        private const val BASE_BACKOFF_MS = 1_000L
        private const val MAX_BACKOFF_MS = 30_000L
        private const val NORMAL_CLOSURE = 1000

        /** ~5s of 20ms audio frames, so an ordinary reply never touches the producer. */
        private const val SIGNAL_BUFFER = 256

        @Volatile private var instance: JarvisWebSocketManager? = null

        fun get(): JarvisWebSocketManager =
            instance ?: synchronized(this) {
                instance ?: JarvisWebSocketManager().also { instance = it }
            }
    }
}
