package com.jarvis.client

import android.content.Context
import android.util.Log
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Attention
import com.jarvis.client.net.EventStream
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.net.VersionInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Whether the event stream is up. Separate from whether Jarvis is busy. */
enum class LinkState { OFFLINE, RECONNECTING, CONNECTED }

/**
 * What Jarvis is *doing*, which is a different question from whether it is
 * available. The visual spec binds a colour to this one, never to power mode.
 */
enum class Activity { IDLE, LISTENING, THINKING, SPEAKING, WORKING, ERROR;

    companion object {
        fun from(wire: String?): Activity = when (wire?.lowercase()) {
            "listening" -> LISTENING
            "thinking" -> THINKING
            "speaking" -> SPEAKING
            "working" -> WORKING
            "error" -> ERROR
            else -> IDLE
        }
    }
}

/**
 * The eight face states. Seven come from activity and power; `banked` comes
 * from the server's arbiter and is never re-derived here — a client that
 * recomputes it will eventually black out a face that is mid-sentence.
 */
enum class FaceState { IDLE, LISTENING, THINKING, SPEAKING, APPROVAL, STANDBY, ERROR, BANKED }

/**
 * Process-wide state, shared by the activity, the foreground service and (later)
 * the quick-settings tile.
 *
 * A singleton for the same reason the other client has one: any of those can be
 * the entry point that cold-starts the process, and they must agree about the
 * link rather than each keeping their own.
 */
object JarvisRuntime {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    @Volatile private var started = false
    val isInitialized: Boolean get() = started

    lateinit var settings: ClientSettings
        private set
    lateinit var tokens: TokenStore
        private set
    lateinit var api: JarvisApi
        private set
    private lateinit var stream: EventStream

    private val _link = MutableStateFlow(LinkState.OFFLINE)
    val link: StateFlow<LinkState> = _link.asStateFlow()

    private val _linkDetail = MutableStateFlow<String?>(null)

    /** Why the link is down, in words, or null when it is up. */
    val linkDetail: StateFlow<String?> = _linkDetail.asStateFlow()

    /**
     * True whenever a decision must not be taken.
     *
     * Three ways to become stale, and they are not the same failure: the stream
     * is not connected, the server told us on `hello` that we fell off the ring
     * buffer, or no keepalive has arrived for longer than the server's ~20s
     * cadence allows. The third is the one that matters most, because the
     * socket has not noticed and everything still looks fine.
     */
    private val _stale = MutableStateFlow(true)
    val stale: StateFlow<Boolean> = _stale.asStateFlow()

    private val _version = MutableStateFlow<VersionInfo?>(null)
    val version: StateFlow<VersionInfo?> = _version.asStateFlow()

    private val _status = MutableStateFlow<StatusInfo?>(null)
    val status: StateFlow<StatusInfo?> = _status.asStateFlow()

    private val _activity = MutableStateFlow(Activity.IDLE)
    val activity: StateFlow<Activity> = _activity.asStateFlow()

    private val _power = MutableStateFlow("active")
    val power: StateFlow<String> = _power.asStateFlow()

    private val _pending = MutableStateFlow<List<PendingItem>>(emptyList())
    val pending: StateFlow<List<PendingItem>> = _pending.asStateFlow()

    private val _attention = MutableStateFlow(Attention())
    val attention: StateFlow<Attention> = _attention.asStateFlow()

    /** Non-null when something needs saying on screen and nowhere else will say it. */
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    private var streamJob: Job? = null
    private var watchdog: Job? = null

    @Volatile private var lastFrameAt = 0L

    @Synchronized
    fun initialize(context: Context) {
        if (started) return
        val app = context.applicationContext
        settings = ClientSettings(app)
        tokens = TokenStore(app)
        api = JarvisApi(settings, tokens)
        stream = EventStream(api)
        started = true
    }

    /** True once there is somewhere to talk to and something to talk with. */
    fun isPaired(): Boolean =
        started && !settings.baseUrl().isNullOrEmpty() && tokens.hasToken()

    // -------------------------------------------------------- handshake ----

    /**
     * `GET /api/version` first, on every launch and after every reconnect.
     * Branch on capabilities, never on version numbers.
     */
    suspend fun handshake(): ApiResult<VersionInfo> {
        val result = api.version()
        when (result) {
            is ApiResult.Ok -> {
                _version.value = result.value
                _notice.value = null
            }
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    private fun describe(e: ApiError): String = when (e) {
        ApiError.BadToken ->
            "The desktop refused that token. Check it in the HUD's settings and paste it again."
        ApiError.NotFound ->
            "Reached something at that address, but it is not a Jarvis server."
        ApiError.AlreadyHandled -> "Already handled elsewhere."
        is ApiError.Unreachable ->
            "Cannot reach the desktop: ${e.detail}. Check Tailscale is up on both ends."
        is ApiError.Server -> "The desktop answered ${e.code}."
        is ApiError.Malformed -> "The desktop sent something this app could not read."
    }

    fun noticeFor(e: ApiError): String = describe(e)

    fun clearNotice() { _notice.value = null }

    // ----------------------------------------------------------- stream ----

    fun startStream() {
        if (!started || streamJob?.isActive == true) return
        _link.value = LinkState.RECONNECTING

        streamJob = scope.launch {
            stream.connect(
                lastEventId = settings.lastEventId,
                onResumePoint = { settings.lastEventId = it },
            ).collect { signal ->
                lastFrameAt = System.currentTimeMillis()
                when (signal) {
                    is EventStream.Signal.Open -> onOpen(signal.hello)
                    is EventStream.Signal.Event -> onEvent(signal.event.kind)
                    is EventStream.Signal.Down -> {
                        _link.value =
                            if (signal.attempt == 0) LinkState.RECONNECTING else LinkState.OFFLINE
                        _linkDetail.value = signal.reason
                        _stale.value = true
                    }
                }
            }
        }

        watchdog = scope.launch {
            while (true) {
                delay(WATCHDOG_TICK_MS)
                val since = System.currentTimeMillis() - lastFrameAt
                if (_link.value == LinkState.CONNECTED && since > KEEPALIVE_GAP_MS) {
                    // The socket has not failed, so nothing else will tell us.
                    Log.w(TAG, "no frame for ${since}ms; treating the link as stale")
                    _stale.value = true
                    _linkDetail.value = "No keepalive for ${since / 1000}s"
                }
            }
        }
    }

    fun stopStream() {
        streamJob?.cancel(); streamJob = null
        watchdog?.cancel(); watchdog = null
        _link.value = LinkState.OFFLINE
        _stale.value = true
    }

    private suspend fun onOpen(hello: com.jarvis.client.net.HelloPayload?) {
        _link.value = LinkState.CONNECTED
        _linkDetail.value = null

        if (hello?.stale == true) {
            // We fell off the back of the 512-event ring buffer. Not caught up:
            // re-fetch everything and do NOT replay. Dropping the resume point
            // is deliberate — keeping it would invite a later attempt to
            // continue from an id the server no longer has.
            Log.i(TAG, "resumed stale; re-fetching all state")
            settings.clearResumePoint()
        }

        // A client that connects mid-turn has no other way to learn what Jarvis
        // is doing, so take it from hello rather than assuming idle.
        hello?.activity?.let { _activity.value = Activity.from(it) }
        hello?.power?.let { _power.value = it }

        refreshAll()
        _stale.value = false
    }

    /**
     * An event says *something changed*, not *here is the state*. So every one
     * of these re-fetches the real endpoint; the bus is a doorbell.
     */
    private suspend fun onEvent(kind: String) {
        when (kind) {
            "approval" -> refreshPending()
            "attention" -> refreshAttention()
            "activity" -> refreshStatus()
            "power", "persona" -> refreshStatus()
            "finding" -> Unit // the digest covers these; nothing to show live
            // A model download publishes progress here. The phone cannot start,
            // cancel or retry one, so rendering a bar for it would invite a tap
            // on a control that has to be somewhere else.
            "model" -> Unit
            "voice" -> Unit
            else -> Log.d(TAG, "unhandled event kind '$kind'")
        }
    }

    suspend fun refreshAll() {
        handshake()
        refreshStatus()
        refreshPending()
        refreshAttention()
    }

    suspend fun refreshStatus() {
        api.status().onOk { s ->
            _status.value = s
            s.activity?.let { _activity.value = Activity.from(it) }
            s.power?.let { _power.value = it }
        }
    }

    suspend fun refreshPending() {
        api.pending().onOk { _pending.value = it }
    }

    suspend fun refreshAttention() {
        // Not every server exposes this; a 404 simply means no budget to show.
        api.attention().onOk { _attention.value = it }
    }

    // -------------------------------------------------------- decisions ----

    /**
     * Why a decision cannot be taken right now, or null when it can.
     *
     * The stale check is the safety rule, not a nicety: approving against a
     * queue you cannot confirm is live is the hazard the whole gate exists to
     * prevent, and it is exactly what a cached inbox invites.
     */
    fun decisionBlocker(item: PendingItem, nowMs: Long = System.currentTimeMillis()): String? {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            return "Not connected to the desktop, so this decision cannot be delivered."
        }
        if (_pending.value.none { it.id == item.id }) {
            return "That request is no longer pending."
        }
        val expiry = item.expiresAtMs
        if (expiry != null && nowMs >= expiry) {
            return "That request expired. Ask the desktop to raise it again."
        }
        return null
    }

    suspend fun decide(item: PendingItem, approve: Boolean): ApiResult<Unit> {
        val blocker = decisionBlocker(item)
        if (blocker != null) {
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = if (approve) api.approve(item.id) else api.deny(item.id)
        when (result) {
            is ApiResult.Ok -> refreshPending()
            is ApiResult.Failed -> {
                if (result.error == ApiError.AlreadyHandled) {
                    // Routine when the desktop and the phone are both open.
                    _notice.value = "Already handled on the desktop."
                    refreshPending()
                } else {
                    _notice.value = describe(result.error)
                }
            }
        }
        return result
    }

    // ------------------------------------------------------------ faces ----

    /**
     * The face state, resolved the way the server resolves it.
     *
     * `banked` replaces only a *resting* face: if Jarvis is mid-sentence to
     * somebody who asked it something, that is foreground and keeps its own
     * state. The budget governs what Jarvis *starts*, never what it is in the
     * middle of.
     */
    fun faceState(): FaceState {
        if (_link.value != LinkState.CONNECTED) return FaceState.ERROR
        val act = _activity.value
        val resting = act == Activity.IDLE
        return when {
            act == Activity.ERROR -> FaceState.ERROR
            act == Activity.LISTENING -> FaceState.LISTENING
            act == Activity.THINKING || act == Activity.WORKING -> FaceState.THINKING
            act == Activity.SPEAKING -> FaceState.SPEAKING
            resting && _attention.value.banked -> FaceState.BANKED
            resting && _pending.value.isNotEmpty() -> FaceState.APPROVAL
            resting && _power.value == "standby" -> FaceState.STANDBY
            else -> FaceState.IDLE
        }
    }

    private const val TAG = "JarvisRuntime"

    /**
     * The server sends `: keepalive` every ~20s. Three missed is a dead
     * connection the socket has not noticed; below that a single late frame on
     * a dozing radio would flap the indicator for no reason.
     */
    private const val KEEPALIVE_GAP_MS = 70_000L
    private const val WATCHDOG_TICK_MS = 10_000L
}
