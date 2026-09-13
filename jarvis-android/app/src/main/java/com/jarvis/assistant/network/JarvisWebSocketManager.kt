package com.jarvis.assistant.network

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit
import kotlin.math.min

enum class ConnectionState { OFFLINE, RECONNECTING, CONNECTED }

/**
 * Persistent link to the desktop server.
 *
 * Reconnects with exponential backoff (1s, 2s, 4s … capped at 30s) and relies on
 * OkHttp's 45-second ping/pong to keep the Tailscale path warm while the handset
 * is dozing — without traffic the NAT mapping is reclaimed and inbound approval
 * requests would stall until the next radio wake.
 */
class JarvisWebSocketManager private constructor() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val client: OkHttpClient = OkHttpClient.Builder()
        .pingInterval(PING_SECONDS, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val _state = MutableStateFlow(ConnectionState.OFFLINE)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    private val _events = MutableSharedFlow<InboundEvent>(
        replay = 0,
        extraBufferCapacity = 128,
    )
    val events: SharedFlow<InboundEvent> = _events.asSharedFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var url: String? = null
    @Volatile private var shutdown = true
    private var attempt = 0
    private var reconnectJob: Job? = null

    /**
     * Monotonic dial counter. Every [Listener] remembers the generation it was
     * created for and ignores its own callbacks once superseded, so cancelling a
     * socket to re-dial elsewhere cannot trigger a reconnect back to the old URL.
     */
    @Volatile private var generation = 0

    /** Idempotent: re-dials only when the target URL actually changed. */
    fun connect(wsUrl: String) {
        if (!shutdown && url == wsUrl && socket != null) return
        url = wsUrl
        shutdown = false
        attempt = 0
        redial()
    }

    fun disconnect() {
        shutdown = true
        reconnectJob?.cancel()
        reconnectJob = null
        socket?.close(NORMAL_CLOSURE, "client shutdown")
        socket = null
        _state.value = ConnectionState.OFFLINE
    }

    /** Forces a fresh dial, e.g. after the user edits the server address. */
    fun reconnectNow() {
        if (url == null) return
        shutdown = false
        attempt = 0
        redial()
    }

    private fun redial() {
        generation += 1
        reconnectJob?.cancel()
        reconnectJob = null
        val stale = socket
        socket = null
        stale?.cancel()
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

    private fun openSocket() {
        val target = url ?: return
        _state.value = ConnectionState.RECONNECTING
        val request = Request.Builder().url(target).build()
        socket = client.newWebSocket(request, Listener(generation))
    }

    private fun scheduleReconnect() {
        if (shutdown) return
        if (reconnectJob?.isActive == true) return
        val backoff = min(BASE_BACKOFF_MS shl min(attempt, 5), MAX_BACKOFF_MS)
        attempt += 1
        _state.value = ConnectionState.RECONNECTING
        reconnectJob = scope.launch {
            delay(backoff)
            if (!shutdown) openSocket()
        }
    }

    private inner class Listener(private val gen: Int) : WebSocketListener() {

        private val current: Boolean get() = gen == generation

        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (!current) {
                webSocket.cancel()
                return
            }
            socket = webSocket
            attempt = 0
            _lastError.value = null
            _state.value = ConnectionState.CONNECTED
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
            if (!_events.tryEmit(event)) {
                Log.w(TAG, "event buffer full, dropped ${event::class.simpleName}")
            }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            // Reserved for future binary downlink; audio arrives as audio_chunk today.
            Log.d(TAG, "ignoring ${bytes.size} byte binary frame")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(NORMAL_CLOSURE, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (!current) return
            if (socket === webSocket) socket = null
            if (shutdown) {
                _state.value = ConnectionState.OFFLINE
            } else {
                scheduleReconnect()
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (!current) return
            if (socket === webSocket) socket = null
            _lastError.value = t.message ?: t::class.java.simpleName
            Log.w(TAG, "socket failure: ${_lastError.value}")
            if (shutdown) {
                _state.value = ConnectionState.OFFLINE
            } else {
                scheduleReconnect()
            }
        }
    }

    companion object {
        private const val TAG = "JarvisWS"
        private const val PING_SECONDS = 45L
        private const val BASE_BACKOFF_MS = 1_000L
        private const val MAX_BACKOFF_MS = 30_000L
        private const val NORMAL_CLOSURE = 1000

        @Volatile private var instance: JarvisWebSocketManager? = null

        fun get(): JarvisWebSocketManager =
            instance ?: synchronized(this) {
                instance ?: JarvisWebSocketManager().also { instance = it }
            }
    }
}
