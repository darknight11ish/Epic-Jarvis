package com.jarvis.client

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.jarvis.client.data.AppearanceStore
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.net.EventStream
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.onOk
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.net.VersionInfo
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import com.jarvis.client.voice.VoiceSession
import kotlinx.coroutines.launch

/**
 * The raw JSON behind the brain screen.
 *
 * Deliberately untyped. §4 documents that these routes exist and what they are
 * for, and does not document their fields — so a data class here would be
 * invented keys, and invented keys fail silently as an empty panel. Null means
 * the route was not reachable or not present, which the screen says plainly
 * rather than rendering as zero.
 */
data class BrainSnapshot(
    val compute: kotlinx.serialization.json.JsonObject? = null,
    val memory: kotlinx.serialization.json.JsonObject? = null,
    val ledger: kotlinx.serialization.json.JsonObject? = null,
    val skills: kotlinx.serialization.json.JsonObject? = null,
    val initiative: kotlinx.serialization.json.JsonObject? = null,
    val contentRisk: kotlinx.serialization.json.JsonObject? = null,
    val fetchedAtMs: Long = 0L,
)

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

    /**
     * A handler, because everything in this app runs here.
     *
     * Without one, anything escaping a `scope.launch` — a voice turn, a refresh
     * — reached the default uncaught handler and took the process down. The
     * SupervisorJob keeps siblings alive but does nothing about the throw
     * itself.
     */
    private val crashes = CoroutineExceptionHandler { _, t ->
        Log.e(TAG, "unhandled in the runtime scope", t)
        _notice.value = t.message ?: "Something went wrong in the background."
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default + crashes)

    @Volatile private var started = false
    val isInitialized: Boolean get() = started

    lateinit var settings: ClientSettings
        private set
    lateinit var tokens: TokenStore
        private set

    /** Theme, face and the seven state bindings. Per device — see the class. */
    lateinit var appearance: AppearanceStore
        private set

    /**
     * The chat turn in flight.
     *
     * Process-wide rather than remembered in the composition, for two reasons:
     * the voice loop drives it from outside any activity, and a `remember`
     * does not survive a configuration change — so a rotation mid-answer used
     * to throw the reply away.
     */
    lateinit var chat: ChatSession
        private set

    /** Push-to-talk. Built even when the desktop reports no voice path. */
    lateinit var voice: VoiceSession
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

    private val _digest = MutableStateFlow<List<DigestItem>>(emptyList())
    val digest: StateFlow<List<DigestItem>> = _digest.asStateFlow()

    private val _undo = MutableStateFlow<List<UndoEntry>>(emptyList())
    val undo: StateFlow<List<UndoEntry>> = _undo.asStateFlow()

    private val _jobs = MutableStateFlow<List<JobRecord>>(emptyList())
    val jobs: StateFlow<List<JobRecord>> = _jobs.asStateFlow()

    private val _brain = MutableStateFlow(BrainSnapshot())

    /** What the brain screen shows. Fetched on demand, never polled. */
    val brain: StateFlow<BrainSnapshot> = _brain.asStateFlow()

    private val _absent = MutableStateFlow<Set<String>>(emptySet())

    /**
     * Routes whose subsystem answered "not running here".
     *
     * Distinct from "empty", and the difference is the whole reason it exists:
     * an inbox with no undo shelf because the undo module is off, and an inbox
     * with an empty undo shelf, look identical and mean opposite things.
     */
    val absent: StateFlow<Set<String>> = _absent.asStateFlow()

    /** Non-null when something needs saying on screen and nowhere else will say it. */
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    private val _face = MutableStateFlow(FaceState.IDLE)

    /**
     * The face state as a flow rather than a function call.
     *
     * It has to be observable: the reconnect grace below expires on a timer, and
     * a plain function only gets re-read when some *other* piece of state
     * happens to change. A face that stays wrong until the next unrelated event
     * is the same bug as a face that never updates.
     */
    val face: StateFlow<FaceState> = _face.asStateFlow()

    private var streamJob: Job? = null
    private var watchdog: Job? = null
    private var faceJob: Job? = null

    @Volatile private var lastFrameAt = 0L

    @Synchronized
    fun initialize(context: Context) {
        if (started) return
        val app = context.applicationContext

        // Built as LOCALS first, then published to the lateinit fields.
        //
        // Not style. The previous version assigned `chat = ChatSession(api)`
        // two lines above `api = JarvisApi(...)`, and because `api` is
        // lateinit the compiler had nothing to say about it — so every cold
        // start threw UninitializedPropertyAccessException out of the first
        // line of onCreate and the app closed before it drew anything.
        // Locals make the compiler enforce the order, so the whole class of
        // bug cannot come back the next time something is inserted here.
        val clientSettings = ClientSettings(app)
        val tokenStore = TokenStore(app)
        val jarvisApi = JarvisApi(clientSettings, tokenStore)
        val chatSession = ChatSession(jarvisApi)
        val voiceSession = VoiceSession(app, jarvisApi, scope) { text ->
            // The value `send` returns, not the shared flow read afterwards.
            // There is one `_reply`, so a typed message sent mid-answer would
            // cancel the spoken one and leave its own partial reply in there —
            // and Jarvis would say it aloud as the answer to the question that
            // was spoken.
            chatSession.send(text)?.takeIf { it.isNotBlank() }
        }

        settings = clientSettings
        tokens = tokenStore
        api = jarvisApi
        appearance = AppearanceStore(app)
        chat = chatSession
        voice = voiceSession
        stream = EventStream(jarvisApi)
        started = true

        faceJob = scope.launch {
            combine(_link, _activity, _power, _pending, _attention) { _, _, _, _, _ -> }
                .combine(voice.phase) { _, _ -> }
                .collectLatest {
                    _face.value = resolveFace()
                    if (_link.value != LinkState.CONNECTED) {
                        // Re-evaluate once the grace window is up, so a reconnect
                        // that does not come back does eventually show as an
                        // error. collectLatest cancels this the moment anything
                        // changes, so a reconnect that succeeds never reaches it.
                        delay(RECONNECT_GRACE_MS)
                        _face.value = resolveFace()
                    }
                }
        }
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
        ApiError.NotAvailable ->
            "That part of Jarvis is not running on the desktop right now."
        is ApiError.Unreachable ->
            "Cannot reach the desktop: ${e.detail}. Check Tailscale is up on both ends."
        is ApiError.Server -> "The desktop answered ${e.code}."
        is ApiError.Malformed -> "The desktop sent something this app could not read."
    }

    fun noticeFor(e: ApiError): String = describe(e)

    /**
     * Whether the backend reports a capability.
     *
     * §2: a capability that is false means **hide the UI for it**, not show a
     * button that 404s. Absent is also false — a server that predates a feature
     * does not report it at all.
     */
    fun can(name: String): Boolean = _version.value?.can(name) ?: false

    fun clearNotice() { _notice.value = null }

    /** For failures the UI has no other place to put. */
    fun setNotice(text: String) { _notice.value = text }

    // ----------------------------------------------------------- stream ----

    fun startStream() {
        if (!started || streamJob?.isActive == true) return
        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
        _link.value = LinkState.RECONNECTING

        streamJob = scope.launch {
            stream.connect(
                lastEventId = settings.lastEventId,
                onResumePoint = { settings.lastEventId = it },
            )
                // The one blocking socket in the app, and it was on the CPU
                // pool. Dispatchers.Default is sized to the core count — two on
                // a small phone — and this parks one of those threads on a
                // socket for the life of the connection, up to an hour, while
                // voice turns and the face collector contend for what is left.
                // Every other call in this app already uses Dispatchers.IO.
                .flowOn(Dispatchers.IO)
                .collect { signal ->
                lastFrameAt = SystemClock.elapsedRealtime()
                when (signal) {
                    is EventStream.Signal.Open -> onOpen(signal.hello)
                    is EventStream.Signal.Event -> onEvent(signal.event.kind)
                    // Nothing to do beyond the lastFrameAt above, which is the
                    // entire point of it arriving.
                    EventStream.Signal.Alive -> Unit
                    is EventStream.Signal.Down -> {
                        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
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
                // elapsedRealtime, not wall clock. An NTP correction or a
                // manual date change backwards made `since` negative, so
                // `since > KEEPALIVE_GAP_MS` was false and a genuinely dead
                // half-open socket was never marked stale — which silently
                // re-enabled the approval buttons this gate exists to hold.
                val since = SystemClock.elapsedRealtime() - lastFrameAt
                if (_link.value == LinkState.CONNECTED && since > KEEPALIVE_GAP_MS) {
                    // This marks the link stale; it does not repair it. The
                    // repair is the 90s read timeout on `streamClient` — before
                    // that existed this branch was the whole response to a
                    // half-open socket, and it was not a response at all: the
                    // approvals were refused, the socket was left parked, no
                    // reconnect was attempted, and the only line that clears
                    // staleness needs a frame that was never coming. The gate
                    // held shut for ever on a link nothing was trying to fix.
                    //
                    // The two are deliberately staggered: 70s here so the owner
                    // is told the link is doubtful before anything is torn
                    // down, 90s there so the socket recycles shortly after.
                    Log.w(TAG, "no frame for ${since}ms; treating the link as stale")
                    _stale.value = true
                    _linkDetail.value = "No keepalive for ${since / 1000}s"
                } else if (_link.value == LinkState.CONNECTED && _stale.value && lastFrameAt != 0L) {
                    // And back again. Staleness used to be a one-way door: the
                    // only `_stale = false` in this file is in onOpen, so a link
                    // the watchdog had given up on stayed condemned until the
                    // stream was torn down and rebuilt — up to an hour of every
                    // approval being refused with "not connected" on a
                    // connection that was answering.
                    Log.i(TAG, "keepalives resumed after ${since}ms; link is live again")
                    _stale.value = false
                    _linkDetail.value = null
                }
            }
        }
    }

    fun stopStream() {
        streamJob?.cancel(); streamJob = null
        watchdog?.cancel(); watchdog = null
        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
        _link.value = LinkState.OFFLINE
        _stale.value = true
    }

    private suspend fun onOpen(hello: com.jarvis.client.net.HelloPayload?) {
        _link.value = LinkState.CONNECTED
        linkDownSince = 0L
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
            // The memory extractor runs on its own once a conversation goes
            // quiet, so the review queue fills without anyone asking. The
            // event deliberately carries no fact text, and there is nothing
            // here worth showing: reviewing memory is desk work, and a count
            // on a phone invites a batch-accept control, which is precisely
            // the shape rule 4 forbids.
            // Announced as Signal.Open, and EventStream then falls through and
            // emits it as a generic event too - so this arrives on every
            // connect and was logging "unhandled event kind 'hello'" each
            // time. The Open carries the payload; there is nothing to do here.
            "hello" -> Unit
            "proposal" -> Unit
            // Face and bindings changed on another device. Each device renders
            // its own face and the server is only the sync channel, so this is
            // for a later change that reloads the appearance store - not a
            // reason to redraw anything now.
            "appearance" -> Unit
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
        when (val r = api.pending()) {
            is ApiResult.Ok -> {
                _pending.value = r.value
                _absent.value = _absent.value - "approvals"
            }
            is ApiResult.Failed ->
                // Gating switched off on the desktop. An empty approvals list
                // would say "nothing is waiting for you", which is true and
                // deeply misleading: nothing CAN wait, because nothing is
                // asking.
                if (r.error == ApiError.NotAvailable) {
                    _pending.value = emptyList()
                    _absent.value = _absent.value + "approvals"
                }
        }
    }

    suspend fun refreshAttention() {
        // Not every server exposes this; a 404 simply means no budget to show.
        api.attention().onOk { _attention.value = it }
    }

    /**
     * The shelf, the brief and the background work.
     *
     * Fetched on demand rather than kept live: none of it is urgent by design —
     * that is the whole point of a digest — and three more endpoints polled on
     * every event would undo the battery saving the single stream bought.
     */
    suspend fun refreshInbox() {
        val missing = mutableSetOf<String>()
        fun <T> note(key: String, result: ApiResult<T>, apply: (T) -> Unit) {
            when (result) {
                is ApiResult.Ok -> apply(result.value)
                is ApiResult.Failed ->
                    if (result.error == ApiError.NotAvailable) missing += key
            }
        }
        note("digest", api.digest()) { _digest.value = it }
        note("undo", api.undo()) { _undo.value = it }
        note("jobs", api.jobs()) { _jobs.value = it }
        // Only this function's own three keys. It used to assign the whole set,
        // so opening the inbox erased the "approvals" flag that refreshPending
        // had set — and the approvals screen went from "there is no approval
        // queue here" to an empty list with no explanation, which the comment
        // in refreshPending calls true and deeply misleading.
        _absent.value = _absent.value - INBOX_KEYS + missing
    }

    /**
     * The brain screen's data.
     *
     * On demand rather than live, and the reason is the same as the inbox's:
     * none of it changes at the display's rate. The active model changes every
     * few seconds, VRAM samples arrive around 1 Hz, and memory facts and jobs
     * are event-driven. Five more endpoints polled on every event would undo
     * the battery saving the single stream bought, to animate numbers that are
     * not moving.
     *
     * Each probe is independent and a 404 simply means that route is absent on
     * this backend — the screen renders the sections it got and says nothing
     * about the ones it did not, rather than showing an empty panel that looks
     * broken.
     */
    suspend fun refreshBrain() {
        refreshStatus()
        refreshAttention()
        api.jobs().onOk { _jobs.value = it }
        _brain.value = BrainSnapshot(
            compute = api.probe("/api/compute").orNull(),
            memory = api.probe("/api/memory/pending").orNull(),
            ledger = api.probe("/api/ledger").orNull(),
            skills = api.probe("/api/skills").orNull(),
            initiative = api.probe("/api/initiative").orNull(),
            contentRisk = api.probe("/api/content-risk").orNull(),
            fetchedAtMs = System.currentTimeMillis(),
        )
    }

    private fun <T> ApiResult<T>.orNull(): T? = (this as? ApiResult.Ok)?.value

    suspend fun revert(entry: UndoEntry): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val result = api.revert(entry.id)
        when (result) {
            is ApiResult.Ok -> refreshInbox()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    suspend fun cancelJob(job: JobRecord): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val result = api.cancelJob(job.id)
        when (result) {
            is ApiResult.Ok -> refreshInbox()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    /**
     * Stops a message inside its send window.
     *
     * A 409 here means the window closed and it went. Saying anything other
     * than that would be the lie the hold queue exists to avoid, so it is
     * reported plainly rather than as a generic failure.
     *
     * No caller yet: nothing in the API serves a hold handle. See [JarvisApi].
     */
    suspend fun cancelHold(handle: String): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val result = api.cancelHold(handle)
        when (result) {
            is ApiResult.Ok -> {
                _notice.value = "Stopped before it sent."
                refreshInbox()
            }
            is ApiResult.Failed -> {
                _notice.value = if (result.error == ApiError.AlreadyHandled) {
                    "Too late — that message has already gone. There is no unsend."
                } else {
                    describe(result.error)
                }
                refreshInbox()
            }
        }
        return result
    }

    /** Marks the brief read. Marking read is not approving anything in it. */
    suspend fun markDigestSeen() {
        api.digestSeen().onOk { refreshInbox() }
    }

    suspend fun setMuted(muted: Boolean) {
        val result = if (muted) api.mute() else api.unmute()
        when (result) {
            is ApiResult.Ok -> refreshAttention()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
    }

    /**
     * Why a state-changing call that is *not* a decision cannot be made now.
     *
     * Rule 4 blocks acting on a stale stream, and `decisionBlocker` was the
     * only place that read it — so the gate covered one of the write paths and
     * not the rest. `revert` is the call the API doc singles out as "the one
     * state-changing thing a phone may drive", and it went out against an undo
     * shelf that could be hours old; `cancelJob` went out against a job list
     * that could name jobs long finished. Neither is an approval. Both are
     * actions, and rule 4 is about actions.
     *
     * Deliberately not applied to `markDigestSeen`, `setMuted` or
     * `setWakeWord`: marking a brief read is idempotent and claims nothing
     * about the brief, and mute and the wake word are settings on this device's
     * relationship with Jarvis rather than verdicts on anything Jarvis is
     * holding. Refusing those on a stale link would be ceremony, not safety.
     */
    fun actionBlocker(): String? =
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            "Not connected to the desktop, so this cannot be delivered."
        } else {
            null
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

    /**
     * Keeps or discards one fact Jarvis proposed to remember. Mirrors
     * [decide]'s own shape - the same "not connected" refusal, since the
     * desktop's `brain_memory_decide` requires a live link before it will
     * act on this queue either - but against `BrainSnapshot.memory` rather
     * than the approval queue, because a proposed fact and a pending
     * approval are different queues with different lifetimes.
     */
    suspend fun decideMemory(id: Long, accept: Boolean): ApiResult<Unit> {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            val blocker = "Not connected to the desktop, so this decision cannot be delivered."
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = api.decideMemory(id, accept)
        when (result) {
            is ApiResult.Ok -> refreshBrain()
            is ApiResult.Failed -> _notice.value = describe(result.error)
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
    fun faceState(): FaceState = _face.value

    private fun resolveFace(nowMs: Long = System.currentTimeMillis()): FaceState {
        if (_link.value != LinkState.CONNECTED) {
            // A dropped radio on a train is not Jarvis being broken, and the
            // spec's error face is a *reversed* motion — a deliberately alarming
            // thing to show for a three-second blip between two cell towers.
            // Inside the grace window the face holds whatever it was doing; the
            // link bar already says "Reconnecting" in words, which is the honest
            // place for that news.
            //
            // Time since the link dropped, not which enum we are in: the stream
            // reports OFFLINE from the second retry onward, and it is still
            // retrying, so branching on the enum would put the error face up
            // about a second after the first failure.
            val down = linkDownSince
            if (down != 0L && nowMs - down > RECONNECT_GRACE_MS) return FaceState.ERROR
        }
        // This device's own microphone is a fact only this device knows: the
        // server has no idea the mic is open until the utterance arrives, so
        // there is nothing to re-derive and nothing to disagree with. The
        // moment the turn reaches the desktop, the server's `activity` takes
        // over again.
        when (voice.phase.value) {
            VoiceSession.Phase.CAPTURING -> return FaceState.LISTENING
            VoiceSession.Phase.VERIFYING -> return FaceState.THINKING
            VoiceSession.Phase.OFF -> Unit
            // THINKING and SPEAKING are the server's to report once the
            // transcript is in; falling through lets `activity` win.
            else -> Unit
        }
        val act = _activity.value
        val resting = act == Activity.IDLE
        return when {
            // Precedence, highest first: an error, then anything waiting on the
            // human, then what Jarvis is doing, then whether it is awake at all.
            //
            // Approval sits above activity and above banked, both deliberately.
            // Above activity because a question for the human outranks Jarvis
            // talking to itself. Above banked because banked is the state that
            // exists to be ignored and approval is the state that exists to pull
            // the eye — and they are separate queues, so `banked == true` with
            // something pending is entirely reachable. Ordered the other way
            // round, an approval arriving while banked rendered as a stopped
            // grey disc, on the device most likely to be the only one in the
            // room.
            act == Activity.ERROR -> FaceState.ERROR
            _pending.value.isNotEmpty() -> FaceState.APPROVAL
            act == Activity.LISTENING -> FaceState.LISTENING
            act == Activity.THINKING || act == Activity.WORKING -> FaceState.THINKING
            act == Activity.SPEAKING -> FaceState.SPEAKING
            resting && _attention.value.banked -> FaceState.BANKED
            // Quiet is a power mode that suppresses speech, which is what
            // standby renders. Leaving it on IDLE said "ready to talk" about a
            // machine that would not.
            resting && (_power.value == "standby" || _power.value == "quiet") -> FaceState.STANDBY
            else -> FaceState.IDLE
        }
    }

    private const val TAG = "JarvisRuntime"

    /**
     * The server sends `: keepalive` every ~20s. Three missed is a dead
     * connection the socket has not noticed; below that a single late frame on
     * a dozing radio would flap the indicator for no reason.
     */
    /** The three keys refreshInbox owns; it must not touch the rest of the set. */
    private val INBOX_KEYS = setOf("digest", "undo", "jobs")

    private const val KEEPALIVE_GAP_MS = 70_000L
    private const val WATCHDOG_TICK_MS = 10_000L

    /**
     * How long a reconnect may run before the face admits something is wrong.
     * Long enough to cover a handover between cell towers or a screen-off doze
     * wakeup; short enough that a desktop that has actually gone away does not
     * keep pretending to think.
     */
    private const val RECONNECT_GRACE_MS = 12_000L

    /** When the link was last lost, or 0 while it is up. */
    @Volatile private var linkDownSince = 0L
}
