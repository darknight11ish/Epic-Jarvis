package com.jarvis.client

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.jarvis.client.data.AppearanceStore
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ActivityEvent
import com.jarvis.client.net.AnswerMark
import com.jarvis.client.net.AnswerMarkState
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Feedback
import com.jarvis.client.net.MemoryCards
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.SseEvent
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.net.EventStream
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.onOk
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.BigModel
import com.jarvis.client.net.SecondCard
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.net.VersionInfo
import com.jarvis.client.platform.UpdateChecker
import com.jarvis.client.widget.ApprovalWidget
import com.jarvis.client.widget.QuickLinkWidget
import androidx.glance.appwidget.updateAll
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import com.jarvis.client.voice.VoiceSession
import com.jarvis.client.voice.VoiceTraining
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * The raw JSON behind the brain screen.
 *
 * Deliberately untyped. §4 documents that these routes exist and what they are
 * for, and does not document their fields — so a data class here would be
 * invented keys, and invented keys fail silently as an empty panel.
 *
 * A null payload on its own no longer says WHY it is null. It used to be the
 * only signal, and it meant three different things at once: not read yet, the
 * read failed, and this backend does not have the route. The screen showed
 * all three as "Not available on this backend", which was wrong in two cases
 * out of three - and for `/api/content-risk` the wrong case was the dangerous
 * one, because a timed-out read made the rush-latch banner simply vanish
 * under a line that said "Live.". Each payload now has a [SectionRead] beside
 * it that says which of the four it is.
 */
data class BrainSnapshot(
    val compute: kotlinx.serialization.json.JsonObject? = null,
    val memory: kotlinx.serialization.json.JsonObject? = null,
    val ledger: kotlinx.serialization.json.JsonObject? = null,
    val skills: kotlinx.serialization.json.JsonObject? = null,
    val initiative: kotlinx.serialization.json.JsonObject? = null,
    /**
     * Unlike the others, NOT cleared by a failed read: it keeps the last
     * answer that did come back, with [contentRiskAtMs] saying how old that
     * is. A rush latch that disappears because the check failed reads as
     * "nothing is raising the tier", which the phone does not know.
     */
    val contentRisk: kotlinx.serialization.json.JsonObject? = null,
    /** When the whole board was last read. 0 means never, on this run of the app. */
    val fetchedAtMs: Long = 0L,
    val computeRead: SectionRead = SectionRead.Reading,
    val memoryRead: SectionRead = SectionRead.Reading,
    val ledgerRead: SectionRead = SectionRead.Reading,
    val skillsRead: SectionRead = SectionRead.Reading,
    val initiativeRead: SectionRead = SectionRead.Reading,
    val contentRiskRead: SectionRead = SectionRead.Reading,
    /** When [contentRisk] was last read successfully. 0 means never. */
    val contentRiskAtMs: Long = 0L,
    /**
     * True while a re-read is in flight, so Refresh can say "Refreshing…".
     * Without it, a tap that brought back identical data looked exactly like
     * a tap that did nothing.
     */
    val refreshing: Boolean = false,
    /**
     * The last model switch or install asked for from the phone, while its
     * approval card may still be waiting. Carried here, rather than in a flow
     * of its own, because it is shown on the same screen as the rest of this
     * snapshot and nowhere else.
     */
    val modelRequest: ModelRequest? = null,
)

/**
 * How one section's last read came back. Four states, drawn four ways:
 * "Reading…", "Not on this backend", "Could not read this: <reason>" with a
 * Retry, or the data itself.
 */
sealed interface SectionRead {
    /** Not answered yet on this run of the app. */
    data object Reading : SectionRead

    /** The route answered. The payload sits in the matching field. */
    data object Read : SectionRead

    /**
     * 404 or 503: the route or the subsystem behind it is not on this
     * backend. A fact about the desktop, not a fault, so it gets no Retry.
     */
    data object Absent : SectionRead

    /** Anything else - a timeout, a 500, a body that would not parse. */
    data class Failed(val reason: String) : SectionRead
}

/**
 * A model switch or install the phone asked for. Asking raises an approval
 * card on Home (tier `ask` on the server); nothing about the model changes
 * until that card is approved.
 */
data class ModelRequest(
    /** True for an install (a download), false for a switch. */
    val install: Boolean,
    val ref: String,
    /**
     * The card this request raised, when it could be told apart from the
     * cards already waiting; null when it could not. Only ever used to
     * scroll Home to the card - never to decide it.
     */
    val cardId: String?,
    val atMs: Long,
)

/**
 * The Inbox's own read state. The screen used to take none, so it said
 * "Live. Nothing waiting." before its first read had come back, and again
 * after a read that failed.
 */
data class InboxRead(
    val digest: SectionRead = SectionRead.Reading,
    val undo: SectionRead = SectionRead.Reading,
    val jobs: SectionRead = SectionRead.Reading,
    /** When the last read finished. 0 means never, on this run of the app. */
    val fetchedAtMs: Long = 0L,
    val refreshing: Boolean = false,
)

/** Whether the event stream is up. Separate from whether Jarvis is busy. */
enum class LinkState { OFFLINE, RECONNECTING, CONNECTED }

/**
 * What Jarvis is *doing*, which is a different question from whether it is
 * available. The visual spec binds a colour to this one, never to power mode.
 */
enum class Activity {
    IDLE, LISTENING, THINKING, SPEAKING, WORKING,

    /**
     * A running task, paused - AUTONOMY-PROPOSALS.md §3d. The desktop's
     * `backend/task-control.patch` reports it once a plan has really stopped
     * at a checkpoint with steps left, and keeps reporting it until the task
     * is resumed or stopped. Never set by this app on its own say-so.
     */
    PAUSED,
    ERROR;

    companion object {
        fun from(wire: String?): Activity = when (wire?.lowercase()) {
            "listening" -> LISTENING
            "thinking" -> THINKING
            "speaking" -> SPEAKING
            "working" -> WORKING
            "paused" -> PAUSED
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
     * "A newer version is available": one GET to GitHub's public release
     * page for this app, never to the PC. See [UpdateChecker].
     */
    lateinit var updates: UpdateChecker
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

    /**
     * The owner's right/wrong mark on the answer now on screen, keyed by that
     * answer's id so a mark can never be shown beside a different answer.
     * Null until the owner marks something. In memory only, like the answer
     * itself; the desktop keeps the real record (`feedback.db`).
     */
    private val _answerMark = MutableStateFlow<AnswerMarkState?>(null)
    val answerMark: StateFlow<AnswerMarkState?> = _answerMark.asStateFlow()

    private val _status = MutableStateFlow<StatusInfo?>(null)
    val status: StateFlow<StatusInfo?> = _status.asStateFlow()

    private val _activity = MutableStateFlow(Activity.IDLE)
    val activity: StateFlow<Activity> = _activity.asStateFlow()

    /**
     * What Jarvis is doing right now, in words, or null when it has nothing to
     * say. AUTONOMY-PROPOSALS §3c: the backend's per-step `announce()`
     * sentence, carried as `activity_detail` beside `activity`. Read off the
     * activity event when it carries one and off `/api/status` otherwise.
     * Ephemeral by contract - never stored, never fed back anywhere.
     */
    private val _activityDetail = MutableStateFlow<String?>(null)
    val activityDetail: StateFlow<String?> = _activityDetail.asStateFlow()

    /**
     * The tool loop's `step` events in words, newest last, as the desktop's
     * Brain → Live shows them ([com.jarvis.client.net.Steps]). In memory
     * only, at most [com.jarvis.client.net.Steps.KEEP] lines; tool names
     * only, never what a tool read. Empty until the PC sends one - it sends
     * them only while tools are switched on.
     */
    private val _steps = MutableStateFlow<List<com.jarvis.client.net.Steps.Line>>(emptyList())
    val steps: StateFlow<List<com.jarvis.client.net.Steps.Line>> = _steps.asStateFlow()

    /** Mind's Clear on the steps list. Only this phone's copy; nothing is sent. */
    fun clearSteps() {
        _steps.value = emptyList()
    }

    /**
     * `/api/models`, or null when this backend does not offer the capability
     * or has not been asked yet. Switching between models the desktop already
     * has was allowed onto the phone on 2026-09-18, and installing a typed
     * model name on 2026-09-20 (CLAUDE.md) - both only ever ASK, through an
     * approval card. Browsing what could be installed is still off the phone.
     */
    private val _models = MutableStateFlow<ModelsInfo?>(null)
    val models: StateFlow<ModelsInfo?> = _models.asStateFlow()

    /**
     * `/api/second-card`: what the PC found, and the second-card switches
     * ([com.jarvis.client.net.SecondCard]). Read on each connect, on the Mind
     * screen, after every switch, and after an approval is decided while one
     * of its cards was waiting. Chat reads it too: a picture is only offered
     * while the PC says Pictures is working.
     */
    private val _secondCard = MutableStateFlow<SecondCard.Read>(SecondCard.Read.NotAsked)
    val secondCard: StateFlow<SecondCard.Read> = _secondCard.asStateFlow()

    /**
     * Which note apps the desktop said are set up, as last asked
     * ([noteTargets]) - or null before the first answer. Chat reads it to
     * say, under the box, where a `#log` / `#obs` / `#joplin` line will be
     * filed ([com.jarvis.client.net.NoteCapture.chip]). The send asks again.
     */
    private val _noteTargets = MutableStateFlow<com.jarvis.client.net.NoteCapture.Targets?>(null)
    val noteTargetsKnown: StateFlow<com.jarvis.client.net.NoteCapture.Targets?> =
        _noteTargets.asStateFlow()

    /**
     * `/api/big-model`: what the PC found for the big model (slow), and its
     * switches ([BigModel]). Read on the Mind screen, after every switch,
     * after a `deep` event (a finished question changes the measured speed)
     * and after an approval is decided while one of its cards was waiting.
     */
    private val _bigModel = MutableStateFlow<BigModel.Read<BigModel.Status>>(BigModel.Read.NotAsked)
    val bigModel: StateFlow<BigModel.Read<BigModel.Status>> = _bigModel.asStateFlow()

    /**
     * `/api/deep`: the deep questions and their answers. Read on the Mind
     * screen, after asking, on every `deep` event (the doorbell for a
     * finished question), and - only while one is still going - every
     * [BigModel.DEEP_POLL_MS] while its plate is on screen.
     */
    private val _deep = MutableStateFlow<BigModel.Read<BigModel.Deep>>(BigModel.Read.NotAsked)
    val deep: StateFlow<BigModel.Read<BigModel.Deep>> = _deep.asStateFlow()

    private val _power = MutableStateFlow("active")
    val power: StateFlow<String> = _power.asStateFlow()

    private val _pending = MutableStateFlow<List<PendingItem>>(emptyList())
    val pending: StateFlow<List<PendingItem>> = _pending.asStateFlow()

    /**
     * The ids whose approve or deny is in flight right now.
     *
     * Two taps on Approve about 100ms apart both got past [decisionBlocker] and
     * both POSTed: the blocker's "no longer pending" test reads `_pending`, and
     * `_pending` does not change until the first POST has come back. The brain
     * screen already holds a `busyId` for exactly this on memory decisions;
     * approvals never got the same treatment.
     */
    private val _deciding = MutableStateFlow<Set<String>>(emptySet())
    val deciding: StateFlow<Set<String>> = _deciding.asStateFlow()

    private val _attention = MutableStateFlow(Attention())
    val attention: StateFlow<Attention> = _attention.asStateFlow()

    private val _digest = MutableStateFlow<List<DigestItem>>(emptyList())
    val digest: StateFlow<List<DigestItem>> = _digest.asStateFlow()

    private val _undo = MutableStateFlow<List<UndoEntry>>(emptyList())
    val undo: StateFlow<List<UndoEntry>> = _undo.asStateFlow()

    private val _inboxRead = MutableStateFlow(InboxRead())

    /** Whether each Inbox list has been read, failed, or is not on this backend. */
    val inboxRead: StateFlow<InboxRead> = _inboxRead.asStateFlow()

    private val _jobs = MutableStateFlow<List<JobRecord>>(emptyList())
    val jobs: StateFlow<List<JobRecord>> = _jobs.asStateFlow()

    private val _brain = MutableStateFlow(BrainSnapshot())

    /**
     * What the brain screen shows. Fetched on demand - when the screen opens,
     * on Refresh or Retry - and polled only if the screen is given an
     * auto-refresh interval, which is off unless the owner turns it on.
     */
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
    private var widgetJob: Job? = null

    /** The forced restart in flight, so two taps on Reconnect do not stack. */
    private var restartJob: Job? = null

    @Volatile private var lastFrameAt = 0L

    /**
     * Whether the approval queue has actually been re-read since the connection
     * now open was opened.
     *
     * The watchdog's un-stale branch used to fire on "connected and stale"
     * alone. [onOpen] sets CONNECTED on its first line but only clears
     * staleness after four sequential HTTP calls, so during a slow refresh the
     * watchdog could open the gate over the queue cached from *before* the
     * disconnect. Cleared again whenever a refresh fails, so a queue that could
     * not be confirmed never counts as confirmed.
     */
    @Volatile private var refreshedSinceOpen = false

    /**
     * Whether this connection has already had its one full refresh.
     *
     * EventStream announces the connect as `Open(null)` and then the hello frame
     * as `Open(hello)`, and both land in [onOpen] — so every single connect ran
     * `refreshAll` twice, eight HTTP requests to learn one state.
     */
    @Volatile private var openRefreshDone = false

    /** The newest resume point not yet written to disk. See [noteResumePoint]. */
    @Volatile private var resumePointPending: String? = null
    @Volatile private var resumePointWrittenAt = 0L

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
        // The link check is a lambda, not a value: it is read at the moment
        // "hey Jarvis" ON is asked for, and `actionBlocker` reads the flows.
        val voiceSession = VoiceSession(app, jarvisApi, scope, linkBlocker = { actionBlocker() }) { text, onDelta ->
            // The value `send` returns, not the shared flow read afterwards.
            // There is one `_reply`, so a typed message sent mid-answer would
            // cancel the spoken one and leave its own partial reply in there —
            // and Jarvis would say it aloud as the answer to the question that
            // was spoken. `onDelta` is this same call's own local callback,
            // not a subscription to that shared flow - see ChatSession.send's
            // own doc for why that distinction is the whole point.
            chatSession.send(text, onDelta)?.takeIf { it.isNotBlank() }
        }

        settings = clientSettings
        tokens = tokenStore
        api = jarvisApi
        appearance = AppearanceStore(app)
        updates = UpdateChecker(clientSettings)
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

        // The home-screen widgets have no collector of their own —
        // GlanceAppWidget draws once when asked and then goes back to being
        // inert, so something on this side has to ask again every time the
        // state they show could have changed. `updateAll` re-runs
        // provideGlance and pushes the new RemoteViews to every placed
        // instance; combine, not two separate collectors, so a pending item
        // arriving in the same tick as a link change still resolves to one
        // redraw.
        //
        // BOTH widgets, not just the approvals one. QuickLinkWidget renders
        // `link` and has `updatePeriodMillis="0"`, so when it was left out of
        // this loop nothing ever asked it to redraw: it froze on whatever it
        // showed when the launcher first drew it.
        //
        // `_stale` is in the combine, and leaving it out was a real bug rather
        // than an omission of taste: [ApprovalWidget] computes its `live` from
        // `stale.value` AND `link.value`, so a `_stale` transition that reaches
        // no collector changes what the widget WOULD draw without redrawing it.
        // Both directions were wrong, and both are the ordinary path:
        //
        //  - Connecting. `onOpen` sets `_link = CONNECTED` (redraw, `_stale`
        //    still true), then `refreshAll()` assigns `_pending` (redraw,
        //    `_stale` STILL true), and only then clears `_stale` - which
        //    emitted nothing. The last frame the launcher ever got was the one
        //    taken while `live` was false, so a real queue rendered
        //    "Approvals pending — desktop unreachable", with no Deny button, on
        //    a healthy link, indefinitely. With an empty queue it was worse:
        //    re-assigning `emptyList()` is conflated away by StateFlow, so the
        //    widget sat on "Not checked yet" for ever.
        //  - Going stale. The watchdog sets `_stale = true` and deliberately
        //    leaves `_link` CONNECTED, so nothing redrew and the widget kept
        //    offering a Deny that `decisionBlocker` would refuse, explaining
        //    itself only in an in-app notice nobody is looking at - which is
        //    the exact failure ApprovalWidget's own comment claims to prevent.
        widgetJob = scope.launch {
            combine(_pending, _link, _stale) { _, _, _ -> }.collect {
                ApprovalWidget().updateAll(app)
                QuickLinkWidget().updateAll(app)
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
                // A new handshake may be a different (or upgraded) server:
                // ask it about the appearance route afresh.
                appearanceRoute = null
            }
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    private fun describe(e: ApiError): String = when (e) {
        ApiError.BadToken ->
            "The desktop refused that token. On the PC, open Jarvis Desktop's Settings, " +
                "press \"Show the token for my phone\" and type it in again."
        ApiError.NotFound ->
            "Reached something at that address, but it is not a Jarvis server."
        ApiError.AlreadyHandled -> "Already handled elsewhere."
        ApiError.NotAvailable ->
            "That part of Jarvis is not running on the desktop right now."
        is ApiError.Unreachable ->
            "Cannot reach the desktop: ${e.detail}. Check your private network (Tailscale or NordVPN Meshnet) is up on both ends."
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

    /**
     * @param force true only for a reconnect the owner asked for by tapping.
     *   Automatic callers must leave it false: the early return when a stream is
     *   already running is what stops the retry paths stacking connections.
     */
    fun startStream(force: Boolean = false) {
        if (!started) return
        val running = streamJob
        if (running?.isActive == true) {
            // On a half-open socket the job stays "active" until OkHttp's 90s
            // read timeout recycles it, so the Reconnect button did nothing at
            // all for up to a minute and a half — the tap hit this early return
            // and the user had no way to tell the button from a dead one. A
            // reconnect the owner asked for replaces the job instead.
            if (!force || restartJob?.isActive == true) return
            Log.i(TAG, "reconnect asked for; replacing the running stream")
            streamJob = null
            watchdog?.cancel(); watchdog = null
            _link.value = LinkState.RECONNECTING
            _stale.value = true
            refreshedSinceOpen = false
            openRefreshDone = false
            restartJob = scope.launch {
                // cancelAndJoin, not cancel(). Cancelling and dropping the
                // handle in the same breath — which is what stopStream does —
                // leaves the old collector alive for a moment beside the new
                // one, both writing `lastEventId`, and that is how the
                // persisted resume point goes backwards.
                running.cancelAndJoin()
                // Released before re-entering, or the guard below would see a
                // restart in flight and refuse to start the replacement.
                restartJob = null
                startStream()
            }
            return
        }
        // A forced restart is already tearing the old stream down and will start
        // the new one itself; an automatic caller landing in that window would
        // otherwise open a second connection beside it.
        if (restartJob?.isActive == true) return
        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
        _link.value = LinkState.RECONNECTING
        // A new connection has confirmed nothing and refreshed nothing yet.
        refreshedSinceOpen = false
        openRefreshDone = false

        streamJob = scope.launch {
            stream.connect(
                lastEventId = settings.lastEventId,
                onResumePoint = { noteResumePoint(it) },
            )
                // Stamped HERE, upstream of `flowOn`'s buffer, so the clock the
                // watchdog reads advances when a frame ARRIVES rather than when
                // the collector gets round to it. The collector suspends for
                // tens of seconds inside onOpen -> refreshAll (four HTTP calls)
                // and onEvent -> refreshPending; stamping below the buffer meant
                // every keepalive that arrived during that work went uncounted,
                // and the 70s watchdog declared a perfectly healthy stream stale
                // and refused every approval on it.
                .onEach { lastFrameAt = SystemClock.elapsedRealtime() }
                // The one blocking socket in the app, and it was on the CPU
                // pool. Dispatchers.Default is sized to the core count — two on
                // a small phone — and this parks one of those threads on a
                // socket for the life of the connection, up to an hour, while
                // voice turns and the face collector contend for what is left.
                // Every other call in this app already uses Dispatchers.IO.
                .flowOn(Dispatchers.IO)
                .collect { signal ->
                when (signal) {
                    is EventStream.Signal.Open -> onOpen(signal.hello)
                    is EventStream.Signal.Event -> onEvent(signal.event)
                    // Nothing to do beyond the stamp in `onEach` above, which
                    // is the entire point of it arriving.
                    EventStream.Signal.Alive -> Unit
                    is EventStream.Signal.Down -> {
                        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
                        _link.value =
                            if (signal.attempt == 0) LinkState.RECONNECTING else LinkState.OFFLINE
                        _linkDetail.value = signal.reason
                        _stale.value = true
                        // This connection is over, so the next Open is a new one
                        // and owes us its own refresh before the watchdog may
                        // clear staleness or a second refreshAll may run.
                        refreshedSinceOpen = false
                        openRefreshDone = false
                        flushResumePoint()
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
                    // Every OTHER place in this file that sets `_stale = true`
                    // pairs it with this - except, until now, here. Without it,
                    // a queue refreshed long ago (before this gap even started)
                    // was enough to satisfy the branch below the moment a bare
                    // keepalive slipped through, with the pending list never
                    // re-read at all. `EventStream.Signal.Alive` only stamps
                    // `lastFrameAt` (see `onEach` above `.collect` in
                    // `startStream`) - it proves the socket delivered a byte, not
                    // that any approval-resolving event survived the gap it just
                    // came out of.
                    refreshedSinceOpen = false
                } else if (_link.value == LinkState.CONNECTED && _stale.value && lastFrameAt != 0L) {
                    // And back again. Staleness used to be a one-way door: the
                    // only `_stale = false` in this file, before this branch
                    // existed, was in onOpen - so a link the watchdog had
                    // given up on stayed condemned until the stream was torn
                    // down and rebuilt.
                    //
                    // `refreshedSinceOpen` is still the load-bearing test: it
                    // only opens the gate once `refreshPending` has actually
                    // run since the gap was declared, which a real
                    // `"approval"` event forces via `onEvent` but a bare
                    // keepalive never does (see the comment on the branch
                    // above). The line that USED to sit here read exactly
                    // that flag and stopped, on the reasoning that the 90s
                    // hard read timeout on `streamClient` would force a real
                    // reconnect within twenty more seconds either way.
                    //
                    // It does not, in the one case that matters most: a
                    // socket that keeps answering. OkHttp's read timeout
                    // measures the gap since the last byte, so it only ever
                    // fires after a TRUE 90s silence - and a link whose
                    // keepalives merely slowed to 75s, or arrive on schedule
                    // again the moment the gap crosses 70s, never produces
                    // one. `EventStream.Signal.Down` never arrives,
                    // `onOpen` never re-runs, and `refreshedSinceOpen` never
                    // becomes true on its own. Reproduced by tracing the
                    // state machine by hand, not on a device: a link that
                    // recovers by resuming its OWN keepalive schedule,
                    // without ever going the full 90s silent, stayed
                    // condemned until an unrelated approval event happened
                    // to arrive - which, on a quiet night, could be never.
                    //
                    // So this branch now asks directly rather than waiting to
                    // be handed the answer. `refreshPending` is a plain GET;
                    // it needs the phone's normal network path, not this
                    // specific SSE socket, so it can succeed even seconds
                    // before the stream itself would notice anything. Called
                    // in this coroutine rather than `scope.launch`, so it
                    // naturally serialises against the next tick instead of
                    // risking two overlapping refreshes.
                    if (refreshedSinceOpen) {
                        Log.i(TAG, "keepalives resumed after ${since}ms; link is live again")
                        _stale.value = false
                        _linkDetail.value = null
                    } else if (since <= KEEPALIVE_GAP_MS) {
                        Log.i(TAG, "stale link still connected; asking directly rather than waiting")
                        refreshPending()
                        // `refreshPending` sets `refreshedSinceOpen` itself on
                        // success (and leaves it false, with its own notice,
                        // on failure) - open the gate now rather than making
                        // the owner wait for a tick that would only re-read
                        // the same flag.
                        if (refreshedSinceOpen) {
                            _stale.value = false
                            _linkDetail.value = null
                        }
                    }
                    // `since > KEEPALIVE_GAP_MS` here (stale, and still no
                    // frame within the gap) is deliberately left to the
                    // branch above: it re-declares staleness on the next
                    // tick, which is a no-op beyond re-logging, and asking
                    // again here would just be a second attempt at a request
                    // already timing out.
                }
            }
        }
    }

    fun stopStream() {
        restartJob?.cancel(); restartJob = null
        streamJob?.cancel(); streamJob = null
        watchdog?.cancel(); watchdog = null
        // Whatever the coalescing in noteResumePoint was still holding back, or
        // stopping the service would throw away the last few events' progress.
        flushResumePoint()
        if (linkDownSince == 0L) linkDownSince = System.currentTimeMillis()
        _link.value = LinkState.OFFLINE
        _stale.value = true
        refreshedSinceOpen = false
        openRefreshDone = false
    }

    /**
     * Remembers the resume point without writing it every time.
     *
     * Called once per event, from the stream thread, and the setter it feeds
     * writes SharedPreferences. A replay after time offline delivers hundreds of
     * events in a burst, which queued hundreds of `apply()` writes off that
     * thread. So only the newest id is kept and it is written at most once per
     * [RESUME_WRITE_GAP_MS]; the remainder is flushed when the connection ends.
     * Losing a second of progress to a process kill costs a short replay, and a
     * replayed event is only a doorbell — the refresh it rings for is
     * idempotent, so re-delivery is harmless where a skipped id is not.
     */
    private fun noteResumePoint(id: String) {
        resumePointPending = id
        val now = SystemClock.elapsedRealtime()
        if (now - resumePointWrittenAt >= RESUME_WRITE_GAP_MS) {
            resumePointWrittenAt = now
            flushResumePoint()
        }
    }

    private fun flushResumePoint() {
        val id = resumePointPending ?: return
        resumePointPending = null
        settings.lastEventId = id
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
            // The held-back id goes too. Otherwise the next flush writes it
            // straight back and resurrects the resume point this branch exists
            // to forget.
            resumePointPending = null
            settings.clearResumePoint()
        }

        // A client that connects mid-turn has no other way to learn what Jarvis
        // is doing, so take it from hello rather than assuming idle.
        hello?.activity?.let { _activity.value = Activity.from(it) }
        hello?.power?.let { _power.value = it }

        // At most one refresh per connection. EventStream emits Open twice —
        // once on connect, once when the hello frame lands — and both used to
        // run the full refresh, so a single connect cost eight HTTP requests.
        // The connect-time one already reads state from after the socket opened,
        // which is everything the second would fetch, the stale-resume case
        // above included.
        if (openRefreshDone) return
        openRefreshDone = true

        refreshAll()
        // Only open the gate if the queue was actually re-read: refreshPending
        // clears this flag when the fetch failed, and approving against a queue
        // that could not be confirmed is the exact hazard the gate is for.
        if (refreshedSinceOpen) _stale.value = false
    }

    /**
     * An event says *something changed*, not *here is the state*. So every one
     * of these re-fetches the real endpoint; the bus is a doorbell.
     */
    private suspend fun onEvent(event: SseEvent) {
        when (event.kind) {
            "approval" -> {
                refreshPending()
                // A second-card switch waiting on a card has no event of its
                // own (docs/JARVIS-API.md section 12: "re-read it after a
                // card is decided"). A decided card changes the queue, and
                // this is the doorbell for that, so the switches are asked
                // again - only while one of them is waiting.
                val sc = _secondCard.value
                if (sc is SecondCard.Read.Loaded && sc.status.pending.isNotEmpty()) {
                    recheckSecondCardAfterDecision(sc.status.pending)
                }
                // The big model's switches work the same way
                // (docs/JARVIS-API.md section 14: "read GET /api/big-model
                // again after a card is decided").
                val bm = _bigModel.value
                if (bm is BigModel.Read.Loaded<BigModel.Status> && bm.value.pending.isNotEmpty()) {
                    recheckBigModelAfterDecision(bm.value.pending)
                }
                // And the voice cards: "hey Jarvis" ON and a voice training.
                // Neither has an event of its own either, so without this the
                // Checks screen said "Waiting" over a card already decided.
                if (voice.answered.value && voice.status.value.cardWaiting) {
                    recheckVoiceAfterDecision()
                }
            }
            // A deep question finished (`{"id", "state"}` only - a doorbell,
            // never the question or the answer). The list is re-read for the
            // answer, and the switches for the speed it measured.
            "deep" -> {
                refreshDeep()
                refreshBigModel()
            }
            "attention" -> refreshAttention()
            "activity" -> {
                // The one field read straight off an event rather than
                // re-fetched: the progress line is ephemeral and travels on
                // the doorbell itself. Absent means nothing to say, so the
                // line clears - a stale "Step 2/3" under an idle face would
                // be worse than none.
                // `value.detail`, where the bus puts it - see ActivityEvent.
                // This read `activity_detail`, which no backend sends.
                _activityDetail.value = ActivityEvent.detail(event.data, ACTIVITY_DETAIL_MAX)
                refreshStatus()
            }
            "power", "persona" -> refreshStatus()
            // The brief covers these; the Watches plate on Mind reads its
            // lists again, as the desktop's Brain does.
            "finding" -> _watchTick.update { it + 1 }
            // A model download publishes progress here. The phone CAN start
            // one - Install, by typed name, raises a card (the owner's
            // 2026-09-20 amendment; see installModel) - but it cannot cancel
            // or retry one, so no progress bar is drawn: it would invite a tap
            // on a control that has to be on the desktop. The LIST is re-read,
            // though: an install finishing, or a switch or rollback made on
            // the desktop, should change what the phone's own picker shows.
            "model" -> refreshModels()
            "voice" -> Unit
            // Announced as Signal.Open, and EventStream then falls through and
            // emits it as a generic event too - so this arrives on every
            // connect and was logging "unhandled event kind 'hello'" each
            // time. The Open carries the payload; there is nothing to do here.
            "hello" -> Unit
            // The memory extractor runs on its own once a conversation goes
            // quiet (and a "Remember:" makes a card at once), so the review
            // queue fills without anyone asking. The event carries no fact
            // text - it is a doorbell - so the queue itself is re-read, and
            // the Brain screen's cards (one card, one decision, each) show
            // what arrived. This used to be ignored, with a comment saying
            // reviewing memory was desk work; the phone has had review cards
            // since, and they sat stale until something else refreshed them.
            "proposal" -> refreshMemoryQueue()
            // Face and bindings changed on another device. Each device renders
            // its own face and the server is only the sync channel, so this
            // just re-reads the shared document; nothing here redraws
            // anything directly.
            "appearance" -> refreshAppearance()
            // One step of the tool loop - asking the model, a tool starting,
            // finishing or refused - kept for Mind's "What Jarvis is doing".
            // It used to fall through to "unhandled" below.
            "step" -> {
                val line = com.jarvis.client.net.Steps.Line(
                    com.jarvis.client.net.Steps.clock(System.currentTimeMillis()),
                    com.jarvis.client.net.Steps.text(event.data),
                )
                _steps.update { com.jarvis.client.net.Steps.append(it, line) }
            }
            else -> Log.d(TAG, "unhandled event kind '${event.kind}'")
        }
    }

    suspend fun refreshAll() {
        handshake()
        refreshStatus()
        refreshPending()
        refreshAttention()
        // One small read, so chat knows whether a picture can be offered.
        refreshSecondCard()
        // And one more, so chat can say where a `#log` line will be filed.
        noteTargets()
    }

    suspend fun refreshStatus() {
        api.status().onOk { s ->
            _status.value = s
            s.activity?.let { _activity.value = Activity.from(it) }
            s.power?.let { _power.value = it }
            // Only ever SET from status, never cleared by it: a status poll
            // that omits the field says nothing about whether a step is
            // running, whereas the activity event above is authoritative.
            s.activityDetail?.takeIf { it.isNotBlank() }?.let {
                _activityDetail.value = it.take(ACTIVITY_DETAIL_MAX)
            }
            // Idle means no step is running, whatever the last event said.
            if (_activity.value == Activity.IDLE) _activityDetail.value = null
        }
    }

    /**
     * Re-reads the model list, on a backend that has one. On any other it is
     * cleared, so the picker hides rather than showing a stale list.
     */
    suspend fun refreshModels() {
        if (version.value?.can("models") != true) {
            _models.value = null
            return
        }
        api.models().onOk { _models.value = it }
    }

    /**
     * Asks the desktop to make [ref] the active model.
     *
     * Asks, not does: `switch_model` is tier `ask` on the server, so a 2xx
     * here means a decision card was raised, not that the model changed. The
     * card arrives on the stream like any other and is answered like any
     * other - which is exactly rule 4 holding for a config change.
     */
    suspend fun switchModel(ref: String): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val waitingBefore = _pending.value.map { it.id }.toSet()
        val result = api.switchModel(ref)
        when (result) {
            is ApiResult.Ok -> {
                refreshPending()
                refreshModels()
                // Said on the Mind screen, where the tap was. It used to say
                // nothing at all: the button showed "…" for a moment and then
                // looked exactly as before, which reads as broken and invites
                // a second tap.
                noteModelRequest(install = false, ref = ref, waitingBefore = waitingBefore)
            }
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    /**
     * Records a switch or install that raised a card, for the Mind screen's
     * "Waiting for your approval" line.
     *
     * The POST answers with no id, so the card is found by difference: the
     * one waiting now that was not waiting before the ask. If that is not
     * exactly one card - the re-read failed, or something else arrived at
     * the same moment - [ModelRequest.cardId] is null and Home is opened
     * without scrolling to a particular card. Either way the id is only
     * used to scroll; nothing is ever decided from here.
     */
    private fun noteModelRequest(install: Boolean, ref: String, waitingBefore: Set<String>) {
        val fresh = _pending.value.filter { it.id !in waitingBefore }
        val request = ModelRequest(
            install = install,
            ref = ref.trim(),
            cardId = fresh.singleOrNull()?.id,
            atMs = System.currentTimeMillis(),
        )
        _brain.update { it.copy(modelRequest = request) }
    }

    /** Back to the previous model. Tier `auto` on the server - never waits. */
    suspend fun rollbackModel(): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val result = api.rollbackModel()
        when (result) {
            is ApiResult.Ok -> refreshModels()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    /**
     * Asks the desktop to download and install [ref].
     *
     * The phone-side half of CLAUDE.md's 2026-09-20 amendment: install joins
     * switch as tier `ask`, so this is the exact same shape as
     * [switchModel] - a 2xx means a decision card was raised, not that
     * anything downloaded. `ref` is typed in by the owner; there is no
     * on-phone browsing of what is installABLE, only of what already IS
     * ([refreshModels]).
     *
     * Deliberately does NOT call [refreshModels] on success, unlike
     * [switchModel] - nothing about the installed list has changed yet, only
     * a pending decision has appeared, and that decision has to be approved
     * (very possibly on the desktop, since a fresh download is exactly the
     * kind of six-to-ten-second wait worth watching) before anything is
     * different. The list catches up on its own: the `"model"` SSE event
     * already re-reads it once the desktop actually finishes, same as it
     * does for a switch made from the desktop's own Brain window.
     */
    suspend fun installModel(ref: String): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        // A blank ref is a UI bug, not a user error worth its own message -
        // the caller (ModelsPlate) disables Install until something is
        // typed, the same way it already disables Use/Roll back. Trimmed
        // rather than validated further: what counts as a real model name
        // is the desktop's call, not this app's to second-guess.
        val waitingBefore = _pending.value.map { it.id }.toSet()
        val result = api.installModel(ref.trim())
        when (result) {
            is ApiResult.Ok -> {
                refreshPending()
                // In the Model plate, with a way to reach the card, rather than
                // the shared notice it used to set. That notice said "approve
                // it" without saying where, and the card is on Home, not on
                // the screen the owner was looking at.
                noteModelRequest(install = true, ref = ref, waitingBefore = waitingBefore)
            }
            // describeDraft, not describe: a 404 here almost certainly means a
            // desktop old enough to predate this route, and describe's own
            // wording for that - "not a Jarvis server" - reads as the
            // connection being hijacked. amendPending and pauseTask already
            // draw this distinction for the same reason; install missed it
            // because it was written by copying switchModel/rollbackModel,
            // neither of which is new enough on the server to ever 404 this
            // way in practice.
            is ApiResult.Failed -> _notice.value = describeDraft(result.error)
        }
        return result
    }

    // ------------------------------------------------------ second card ----

    /**
     * Re-reads `/api/second-card`. A failed read replaces what was there:
     * the plate then says it could not ask, rather than showing switches the
     * PC may no longer agree with - and chat stops offering a picture.
     */
    suspend fun refreshSecondCard() {
        _secondCard.value = SecondCard.readOf(api.secondCard())
    }

    /**
     * Re-reads the switches after an approval was decided while one of their
     * cards [waiting] - at once, then twice more a little later if the PC
     * still says it waits. The PC writes the switch when its own wait for the
     * card returns, which can land just after the event that woke this, so
     * one read alone could leave the plate on "Waiting" over a card already
     * answered. Stops as soon as any of those cards is no longer waiting.
     * Launched, so the event loop is not held up.
     */
    private fun recheckSecondCardAfterDecision(waiting: List<String>) {
        scope.launch {
            for (wait in SECOND_CARD_RECHECK_MS) {
                delay(wait)
                refreshSecondCard()
                val now = (_secondCard.value as? SecondCard.Read.Loaded)?.status?.pending ?: return@launch
                if (!now.containsAll(waiting)) return@launch
            }
        }
    }

    /**
     * Turns one second-card switch off, or asks for it to be turned on, then
     * asks the PC what actually happened - the same shape as the wake word
     * ([com.jarvis.client.voice.VoiceSession.setWakeWord]).
     *
     * ON raises one approval card on the PC (`second_card_enable`, tier
     * `ask`), so a success means "a card is up", never "it is on"; the card
     * is decided on the PC or in this phone's approval list, one at a time,
     * like any other. OFF is immediate. Either way the reply is not trusted
     * for the state: [refreshSecondCard] decides what the plate shows.
     *
     * Refused while the link is down or stale ([actionBlocker], rule 4).
     *
     * @param feature a feature id, or [SecondCard.MASTER] for the main switch.
     * @return a sentence to show, or null when the plate already says it.
     */
    suspend fun setSecondCard(feature: String, enabled: Boolean): String? {
        actionBlocker()?.let { return it }
        val result = api.setSecondCard(feature, enabled)
        // The card should appear in this phone's approvals too.
        if (enabled && result is ApiResult.Ok) refreshPending()
        refreshSecondCard()
        return SecondCard.replyLine(result)
    }

    // -------------------------------------------------------- big model ----

    /**
     * Re-reads `/api/big-model`. A failed read replaces what was there: the
     * plate then says it could not ask, rather than showing switches the PC
     * may no longer agree with.
     */
    suspend fun refreshBigModel() {
        _bigModel.value = BigModel.readOf(api.bigModel())
    }

    /** [recheckSecondCardAfterDecision], for the big model's switches. */
    private fun recheckBigModelAfterDecision(waiting: List<String>) {
        scope.launch {
            for (wait in SECOND_CARD_RECHECK_MS) {
                delay(wait)
                refreshBigModel()
                val now = (_bigModel.value as? BigModel.Read.Loaded<BigModel.Status>)?.value?.pending
                    ?: return@launch
                if (!now.containsAll(waiting)) return@launch
            }
        }
    }

    /**
     * [recheckSecondCardAfterDecision], for the voice cards (the wake word's
     * and voice training's): re-reads `/api/voice/status` at once, then twice
     * more a little later while it still says a card waits. The PC records
     * the outcome when its own wait for the card returns, which can land
     * just after the event that woke this.
     */
    private fun recheckVoiceAfterDecision() {
        scope.launch {
            for (wait in SECOND_CARD_RECHECK_MS) {
                delay(wait)
                voice.refreshStatus()
                if (!voice.answered.value || !voice.status.value.cardWaiting) return@launch
            }
        }
    }

    /**
     * Turns one big-model switch off, or asks for it to be turned on, then
     * asks the PC what actually happened - the same shape as [setSecondCard].
     *
     * ON raises one approval card on the PC (`big_model_enable`, tier `ask`),
     * so a success means "a card is up", never "it is on"; the card is
     * decided on the PC or in this phone's approval list, one at a time. OFF
     * is immediate. Either way [refreshBigModel] decides what the plate shows.
     *
     * Refused while the link is down or stale ([actionBlocker], rule 4).
     *
     * @param switch [BigModel.MASTER], [BigModel.WIKI] or [BigModel.DEEP].
     * @return a sentence to show, or null when the plate already says it.
     */
    suspend fun setBigModel(switch: String, enabled: Boolean): String? {
        actionBlocker()?.let { return it }
        val result = api.setBigModel(switch, enabled)
        // The card should appear in this phone's approvals too.
        if (enabled && result is ApiResult.Ok) refreshPending()
        refreshBigModel()
        // Turning the deep-questions switch changes whether a question can be asked.
        refreshDeep()
        return BigModel.replyLine(result)
    }

    /** Re-reads `/api/deep`. Starts nothing on the PC. */
    suspend fun refreshDeep() {
        _deep.value = BigModel.deepReadOf(api.deep())
    }

    /**
     * "Ask slowly": queues one deep question on the PC. No approval card per
     * question - the switch was approved with one, and a question acts on
     * nothing - but it is still held on a stale or dropped link (rule 4).
     * The list is re-read either way, so the new question shows at once.
     */
    suspend fun askDeep(question: String): BigModel.Asked {
        actionBlocker()?.let { return BigModel.Asked(it, queued = false) }
        val limit = (_deep.value as? BigModel.Read.Loaded<BigModel.Deep>)?.value?.questionChars ?: 4000
        BigModel.askProblem(question, limit)?.let { return BigModel.Asked(it, queued = false) }
        val asked = BigModel.askReply(api.deepAsk(question))
        refreshDeep()
        return asked
    }

    /**
     * Why a picture cannot be sent right now, or null when it can: asks the
     * PC again first, so a Pictures switch turned off since the last read
     * stops the send rather than handing the picture to a model that cannot
     * see it.
     */
    suspend fun pictureBlocker(): String? {
        actionBlocker()?.let { return it }
        refreshSecondCard()
        val read = _secondCard.value
        if (SecondCard.visionAvailable(read)) return null
        val why = com.jarvis.client.net.ChatPicture.notWorkingWhy(read)
        return "The picture was not sent: Pictures on the second graphics card is not " +
            "working right now" + (why?.let { " ($it)" } ?: "") + "."
    }

    /**
     * "Train my voice": sends the owner's recorded clips to the desktop.
     *
     * The same shape as [installModel]: a success means **an approval card
     * was raised**, not that anything changed. The desktop learns the voice
     * only once that card is approved (on the desktop or here, like any
     * other card) and throws the clips away whatever the answer.
     *
     * Blocked while the link is down or stale ([actionBlocker]): sending
     * raises a card, and a card raised against a stream this phone cannot
     * confirm is live is the thing rule 4 is about. The clips are not logged
     * and not kept here - the caller drops them once this says accepted.
     */
    suspend fun sendVoiceTraining(clips: List<ByteArray>): VoiceTraining.SendResult {
        actionBlocker()?.let { return VoiceTraining.SendResult(false, it) }
        // mic=phone: since 2026-09-24 the PC keeps one voice print per
        // microphone, and this is the phone's.
        return when (val result = api.enrollVoice(clips, VoiceTraining.MIC)) {
            is ApiResult.Ok -> {
                val accepted = VoiceTraining.accepted(result.value)
                // The card should appear in this phone's approvals too.
                if (accepted) refreshPending()
                VoiceTraining.SendResult(accepted, VoiceTraining.replyLine(result.value))
            }
            is ApiResult.Failed -> VoiceTraining.SendResult(
                false,
                when (result.error) {
                    // No such route: the PC has not had voice-enroll.patch yet.
                    ApiError.NotFound ->
                        "Your PC does not have voice training yet. Run the patch script on " +
                            "the PC first (backend/README.md, \"Train my voice\")."
                    ApiError.NotAvailable ->
                        "Voice training is not installed on your PC yet."
                    else -> describe(result.error)
                },
            )
        }
    }

    /**
     * The "someone else" check: another person's clips, scored on the PC
     * against the owner's print and thrown away there. Changes nothing and
     * raises no card, so it is not gated on the link the way a write is -
     * but it is refused outright unless the PC says it understands it
     * ([VoiceTraining.canCheck]): an older PC would read these clips as a
     * training and raise a card to make the other person "the owner".
     */
    suspend fun checkVoiceWithSomeoneElse(clips: List<ByteArray>): VoiceTraining.CheckResult {
        if (!VoiceTraining.canCheck(voice.status.value, voice.answered.value)) {
            return VoiceTraining.CheckResult(
                false,
                "Your PC does not have this check yet. Run the patch script on the PC first.",
            )
        }
        return when (val result = api.calibrateVoice(clips, VoiceTraining.MIC)) {
            is ApiResult.Ok -> VoiceTraining.checkResult(result.value)
            is ApiResult.Failed -> VoiceTraining.CheckResult(false, describe(result.error))
        }
    }

    /**
     * Asks the PC to use a stricter bar for the owner's voice on this
     * phone's microphone. Like [sendVoiceTraining], a success means a card
     * was raised - the bar changes only once it is approved.
     */
    suspend fun proposeVoiceThreshold(value: Double): VoiceTraining.SendResult {
        actionBlocker()?.let { return VoiceTraining.SendResult(false, it) }
        if (!VoiceTraining.canCheck(voice.status.value, voice.answered.value)) {
            return VoiceTraining.SendResult(false, "Your PC does not have this setting yet.")
        }
        return when (val result = api.proposeVoiceThreshold(value, VoiceTraining.MIC)) {
            is ApiResult.Ok -> {
                val accepted = VoiceTraining.accepted(result.value)
                if (accepted) refreshPending()
                VoiceTraining.SendResult(accepted, VoiceTraining.replyLine(result.value))
            }
            is ApiResult.Failed -> VoiceTraining.SendResult(false, describe(result.error))
        }
    }

    // -------------------------------------------------------- appearance ----

    /**
     * Whether this server answers `/api/appearance`, learnt by asking it:
     * true once it answered, false once it said 404, null until asked (and
     * again after every handshake).
     *
     * Needed because the capability flag alone was never enough. The
     * backend's `/api/version` did not list `appearance` at all (the rebuilt
     * `jarvis_events._capability_probe` had no entry for it until
     * 2026-09-23, and the owner's server may still be older), while
     * `appearance.patch` had added the route - so gating on the flag meant
     * the phone never synced its face with the desktop. Now the flag is
     * trusted when it says yes, and when it is absent the route is tried
     * once and a 404 is taken as "not on this server", the same thing §2's
     * false flag means.
     */
    @Volatile private var appearanceRoute: Boolean? = null

    private fun noteAppearanceRoute(result: ApiResult<*>) {
        when {
            result is ApiResult.Ok -> appearanceRoute = true
            result is ApiResult.Failed && result.error == ApiError.NotFound -> appearanceRoute = false
            // Anything else (unreachable, a 500) says nothing about the route.
        }
    }

    /**
     * Pulls the shared face/bindings document - after pairing, on the
     * `appearance` SSE event, or on demand. A backend known not to have the
     * route (see [appearanceRoute]) is not asked again, and [AppearanceStore]
     * keeps behaving exactly as it did before this existed. Silent on
     * failure - the local store already has a face, and a sync miss is not
     * worth a notice banner on every reconnect.
     */
    suspend fun refreshAppearance() {
        if (!can("appearance") && appearanceRoute == false) return
        val result = api.getAppearance()
        noteAppearanceRoute(result)
        if (result is ApiResult.Ok) {
            appearance.applySyncDocument(org.json.JSONObject(result.value.toString()))
        }
    }

    /**
     * Pushes this device's face/bindings so the owner's other device picks
     * it up - called after any local change to either. Same silent-on-
     * failure reasoning as [refreshAppearance]: this is a convenience sync,
     * not a decision, and nothing on this screen depends on it succeeding.
     */
    suspend fun pushAppearance() {
        if (!can("appearance")) {
            // Ask first, without applying what comes back: applying it here
            // would overwrite the change this push is about to send.
            if (appearanceRoute == null) noteAppearanceRoute(api.getAppearance())
            if (appearanceRoute != true) return
        }
        api.postAppearance(appearance.toSyncDocument().toString())
    }

    /**
     * [pushAppearance] on the runtime's own scope, for a push that must not
     * die with a screen. The Appearance screen sends the state colours once
     * its Undo window closes, and one way it closes is the screen leaving -
     * including a rotation, which also cancels every scope the activity's
     * composition owns, so a push launched there could be cancelled before
     * it was sent and leave the desktop silently out of step.
     */
    fun pushAppearanceDetached() {
        scope.launch { pushAppearance() }
    }

    suspend fun refreshPending() {
        when (val read = api.pendingRead()) {
            is ApiResult.Ok -> {
                val items = read.value.items
                _pending.value = items
                // A row this phone could not read is still a decision waiting
                // on the desktop. Say so, rather than show a shorter list as
                // if it were the whole queue. The rows it COULD read stay
                // decidable: one odd row used to fail the whole read, which
                // left every card stuck behind "Could not re-read what is
                // waiting" (see decodePendingRows).
                val skipped = read.value.skipped
                if (skipped > 0) {
                    Log.w(TAG, "$skipped approval row(s) could not be read")
                    _notice.value = if (skipped == 1) {
                        "1 waiting approval could not be read on this phone. Open Jarvis on the desktop to see it."
                    } else {
                        "$skipped waiting approvals could not be read on this phone. Open Jarvis on the desktop to see them."
                    }
                }
                // A model request whose card has been answered - approved,
                // denied or expired - is no longer waiting, so the Mind
                // screen stops saying it is. One whose card could not be
                // identified is dropped by the next refreshBrain instead.
                val waitingOn = _brain.value.modelRequest?.cardId
                if (waitingOn != null && items.none { it.id == waitingOn }) {
                    _brain.update { b ->
                        if (b.modelRequest?.cardId == waitingOn) b.copy(modelRequest = null) else b
                    }
                }
                _absent.value = _absent.value - "approvals"
                // What is on screen is now what the desktop holds. This is the
                // only thing that earns the gate the right to open.
                refreshedSinceOpen = true
            }
            is ApiResult.Failed -> {
                // Gating switched off on the desktop. An empty approvals list
                // would say "nothing is waiting for you", which is true and
                // deeply misleading: nothing CAN wait, because nothing is
                // asking.
                if (read.error == ApiError.NotAvailable) {
                    _pending.value = emptyList()
                    _absent.value = _absent.value + "approvals"
                    // Answered, just with "there is no queue here". Nothing is
                    // being hidden, so this does not hold the gate shut.
                    refreshedSinceOpen = true
                } else {
                    // Every other failure used to be swallowed whole: no log, no
                    // notice, `_pending` silently keeping its old contents while
                    // `_stale` stayed false — so the owner could approve from an
                    // arbitrarily old list, and one malformed item turned the
                    // whole refresh into a silent no-op. A queue that could not
                    // be re-read is precisely what stale means, so say so and let
                    // the gate that already reads it do the refusing.
                    Log.w(TAG, "could not re-read the approval queue: ${read.error}")
                    refreshedSinceOpen = false
                    _stale.value = true
                    _linkDetail.value = "Could not re-read what is waiting"
                    _notice.value = describe(read.error)
                }
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
        inboxReadsInFlight.incrementAndGet()
        _inboxRead.update { it.copy(refreshing = true) }
        try {
            val missing = mutableSetOf<String>()
            // Every failure used to be dropped here except NotAvailable, so a
            // timed-out read left the old list on screen - or, on the first
            // read, an empty one under "Live. Nothing waiting." A failed list
            // keeps its last contents (they are still true as of when they
            // were read) and now says it could not be re-read.
            fun <T> note(key: String, result: ApiResult<T>, apply: (T) -> Unit): SectionRead =
                when (result) {
                    is ApiResult.Ok -> {
                        apply(result.value)
                        SectionRead.Read
                    }
                    is ApiResult.Failed -> {
                        if (result.error == ApiError.NotAvailable) missing += key
                        readOf(result.error)
                    }
                }
            val digest = note("digest", api.digest()) { _digest.value = it }
            val undo = note("undo", api.undo()) { _undo.value = it }
            val jobs = note("jobs", api.jobs()) { _jobs.value = it }
            // Only this function's own three keys. It used to assign the whole set,
            // so opening the inbox erased the "approvals" flag that refreshPending
            // had set — and the approvals screen went from "there is no approval
            // queue here" to an empty list with no explanation, which the comment
            // in refreshPending calls true and deeply misleading.
            _absent.value = _absent.value - INBOX_KEYS + missing
            _inboxRead.update {
                it.copy(
                    digest = digest,
                    undo = undo,
                    jobs = jobs,
                    fetchedAtMs = System.currentTimeMillis(),
                )
            }
        } finally {
            // In a finally, so leaving the screen mid-read (which cancels the
            // LaunchedEffect that started it) cannot strand "Refreshing…".
            val left = inboxReadsInFlight.decrementAndGet()
            _inboxRead.update { it.copy(refreshing = left > 0) }
        }
    }

    /** Overlapping refreshInbox calls, so the first to finish does not clear "refreshing" early. */
    private val inboxReadsInFlight = java.util.concurrent.atomic.AtomicInteger(0)

    /** Overlapping refreshBrain calls; same reason as [inboxReadsInFlight]. */
    private val brainReadsInFlight = java.util.concurrent.atomic.AtomicInteger(0)

    /**
     * 404 and 503 mean "not on this backend"; everything else is a failure
     * worth a Retry. Worded by [describe], the same sentences every notice
     * uses - except NotFound, whose notice wording ("not a Jarvis server")
     * is about the address as a whole and would be wrong for one route.
     */
    private fun readOf(e: ApiError): SectionRead = when (e) {
        ApiError.NotFound, ApiError.NotAvailable -> SectionRead.Absent
        else -> SectionRead.Failed(describe(e))
    }

    /** The payload and how it came back, from one probe. */
    private fun ApiResult<JsonObject>.asSection(): Pair<JsonObject?, SectionRead> = when (this) {
        is ApiResult.Ok -> value to SectionRead.Read
        is ApiResult.Failed -> null to readOf(error)
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
     * Each probe is independent. A 404 or 503 means that route is absent on
     * this backend, and any other failure means the read did not work; the
     * snapshot records which, per section ([SectionRead]), so the screen can
     * tell "not here" from "could not read" from "still reading".
     */
    suspend fun refreshBrain() {
        brainReadsInFlight.incrementAndGet()
        _brain.update { it.copy(refreshing = true) }
        try {
            // Together, not one after another. This was nine serial round trips
            // - and it ran again after EVERY memory decision, so keeping ten facts
            // cost ninety requests. Each read is independent of the others, so
            // they overlap; the screen still gets one snapshot, stamped once.
            coroutineScope {
                val status = async { refreshStatus() }
                val attention = async { refreshAttention() }
                val jobs = async { api.jobs().onOk { _jobs.value = it } }
                val models = async { refreshModels() }
                val compute = async { api.probe("/api/compute").asSection() }
                val memory = async { api.probe(MemoryCards.PENDING_PATH).asSection() }
                val ledger = async { api.probe("/api/ledger").asSection() }
                val skills = async { api.probe(com.jarvis.client.net.Skills.PATH).asSection() }
                val initiative = async { api.probe("/api/initiative").asSection() }
                val contentRisk = async { api.probe("/api/content-risk").asSection() }
                val secondCardRead = async { refreshSecondCard() }
                val bigModelRead = async { refreshBigModel() }
                val deepRead = async { refreshDeep() }
                val (computeData, computeRead) = compute.await()
                val (memoryData, memoryRead) = memory.await()
                val (ledgerData, ledgerRead) = ledger.await()
                val (skillsData, skillsRead) = skills.await()
                val (initiativeData, initiativeRead) = initiative.await()
                val (riskData, riskRead) = contentRisk.await()
                val now = System.currentTimeMillis()
                _brain.update { prev ->
                    BrainSnapshot(
                        compute = computeData,
                        memory = memoryData,
                        ledger = ledgerData,
                        skills = skillsData,
                        initiative = initiativeData,
                        // The one section that keeps its last answer through a
                        // failed read - see BrainSnapshot.contentRisk. Absent
                        // clears it: a backend with no scanner has no latch.
                        contentRisk = when (riskRead) {
                            is SectionRead.Failed -> prev.contentRisk
                            else -> riskData
                        },
                        contentRiskAtMs = when (riskRead) {
                            SectionRead.Read -> now
                            is SectionRead.Failed -> prev.contentRiskAtMs
                            else -> 0L
                        },
                        fetchedAtMs = now,
                        computeRead = computeRead,
                        memoryRead = memoryRead,
                        ledgerRead = ledgerRead,
                        skillsRead = skillsRead,
                        initiativeRead = initiativeRead,
                        contentRiskRead = riskRead,
                        refreshing = prev.refreshing,
                        // Kept only while its card is known to still be
                        // waiting. One whose card could not be identified
                        // lasts until this next read of the board, and no
                        // longer - better to drop the line than to keep
                        // claiming a card is waiting after it was answered.
                        // `_pending` is read here, inside the update, so a
                        // request noted while these reads were out is checked
                        // against the queue as it is now, not as it was.
                        modelRequest = prev.modelRequest?.takeIf { req ->
                            req.cardId != null && _pending.value.any { it.id == req.cardId }
                        },
                    )
                }
                status.await()
                attention.await()
                jobs.await()
                models.await()
                secondCardRead.await()
                bigModelRead.await()
                deepRead.await()
            }
        } finally {
            val left = brainReadsInFlight.decrementAndGet()
            _brain.update { it.copy(refreshing = left > 0) }
        }
    }

    /**
     * Just the review queue - all a memory decision can have changed.
     *
     * Leaves [BrainSnapshot.fetchedAtMs] alone. It used to stamp it, which
     * made the screen claim the whole board had just been read when only
     * this one section had.
     */
    suspend fun refreshMemoryQueue() {
        val (memory, read) = api.probe(MemoryCards.PENDING_PATH).asSection()
        _brain.update { it.copy(memory = memory, memoryRead = read) }
    }

    /**
     * "What did I believe on this date?" - a one-shot read, never held as app
     * state the way [brain] is: the Brain screen asks for exactly one moment
     * and throws the answer away the moment a different one is asked for. A
     * failure is surfaced through the same shared [notice] every other read
     * on this screen uses, rather than a dedicated error field.
     */
    suspend fun memoryAsOf(epochSeconds: Long): ApiResult<JsonObject> {
        val result = api.memoryFacts(epochSeconds)
        if (result is ApiResult.Failed) {
            _notice.value = describe(result.error)
            return result
        }
        // The desktop answers a moment it cannot use with TODAY's facts and
        // no `known_at`. Shown under the typed date, that would be today's
        // memory passed off as the past - so it is refused here instead.
        val body = (result as ApiResult.Ok).value
        val knownAt = (body["known_at"] as? JsonPrimitive)
            ?.takeIf { !it.isString }?.content?.toDoubleOrNull()
        if (knownAt == null) {
            val why = "The desktop answered without using that date, so nothing is shown."
            _notice.value = why
            return ApiResult.Failed(ApiError.Malformed(why))
        }
        return result
    }

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

    /**
     * Stops a message still inside its send window - `/api/holds/cancel`.
     * Always the safe direction (it only stops something), so no approval
     * card; still held while the link is stale, like every other write here.
     * A 409 means it already went, and there is no unsend - said as that,
     * not as "already handled elsewhere".
     */
    suspend fun cancelHold(entry: UndoEntry): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val handle = entry.holdHandle
            ?: return ApiResult.Failed(ApiError.Malformed("not a held message"))
        val result = api.cancelHold(handle)
        when (result) {
            is ApiResult.Ok -> {
                _notice.value = "Stopped before it went."
                refreshInbox()
            }
            is ApiResult.Failed -> _notice.value =
                if (result.error == ApiError.AlreadyHandled) {
                    "That one has already gone - there is no unsend."
                } else {
                    describe(result.error)
                }
        }
        return result
    }

    /**
     * Switch the desktop to Active, Quiet or Standby (`backend/power-mode.patch`).
     *
     * Going quieter always goes through. Waking ("active") is held while the
     * link is stale - rule 4 - because it is the direction that makes Jarvis
     * do more. The desktop still decides through its gate (`power_manage`,
     * "auto" in the owner's own config: the safe direction either way). The
     * Power field changes when the desktop's `power` event says so, not here.
     */
    suspend fun setPower(mode: String): ApiResult<Unit> {
        if (mode == "active") {
            actionBlocker()?.let {
                _notice.value = it
                return ApiResult.Failed(ApiError.Unreachable(it))
            }
        }
        return when (val result = api.setPower(mode)) {
            is ApiResult.Ok -> {
                val said = (result.value["message"] as? kotlinx.serialization.json.JsonPrimitive)
                    ?.content
                _notice.value = said ?: "Power mode request sent."
                refreshStatus()
                ApiResult.Ok(Unit)
            }
            is ApiResult.Failed -> {
                _notice.value = if (result.error == ApiError.NotFound) {
                    "This desktop cannot change power mode yet - its backend needs the power-mode patch."
                } else {
                    describe(result.error)
                }
                ApiResult.Failed(result.error)
            }
        }
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

    /**
     * Marks the brief read. Marking read is not approving anything in it.
     *
     * A failure is reported like every other call's. It used to be dropped
     * whole - `onOk` with no other branch - so a "Mark read" that did not
     * reach the desktop left the brief exactly as it was, with no word why.
     */
    suspend fun markDigestSeen() {
        when (val result = api.digestSeen()) {
            is ApiResult.Ok -> refreshInbox()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
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
     * Deliberately not applied to `markDigestSeen` or `setMuted`: marking a
     * brief read is idempotent and claims nothing about the brief, and mute is
     * a setting on this device's relationship with Jarvis rather than a
     * verdict on anything Jarvis is holding. Refusing those on a stale link
     * would be ceremony, not safety.
     *
     * Turning the wake word ON is NOT in that list any more. It used to be,
     * described as a mere setting, but it raises a `change_own_config`
     * approval card on the desktop - a card-raising action like the second
     * card or a model switch - so [VoiceSession.setWakeWord] holds it here
     * too ([com.jarvis.client.voice.WakeRules.requestBlocker]). Turning it
     * OFF still always goes: it only closes a microphone.
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
     *
     * Deliberately silent on `needsChoice`: this blocker gates BOTH decisions,
     * and denying a multi-option item needs no option ("refusing is always
     * the safe direction" - see [decide]'s own check, which is where that one
     * lives, gated on `approve` in a way this shared function cannot be).
     */
    fun decisionBlocker(item: PendingItem, nowMs: Long = System.currentTimeMillis()): String? {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            return "Not connected to the desktop, so this decision cannot be delivered."
        }
        if (item.id in _deciding.value) {
            // A double-tap on Approve sent two POSTs: both taps reached here
            // before the first reply came back, and the test below reads
            // `_pending`, which does not change until it has.
            return "That decision is already on its way."
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

    /**
     * [decide], on the runtime's own scope.
     *
     * A decision launched from a composable's scope died with the screen: a
     * rotation during the round trip cancelled the coroutine after the POST
     * had landed, the result was dropped, the card sat there looking
     * undecided and a second tap sent it again. This scope outlives every
     * screen, so the answer is always collected and the card always follows.
     */
    fun decideDetached(item: PendingItem, approve: Boolean) {
        scope.launch { decide(item, approve) }
    }

    suspend fun decide(item: PendingItem, approve: Boolean): ApiResult<Unit> {
        // Checked here rather than only in [ApprovalCard]'s `canApprove`: this
        // is the one function that actually sends the decision, the same
        // reason the staleness check lives in [decisionBlocker] and not in
        // each screen. A disabled button is a courtesy, not a gate - this app
        // has paid for skipping that distinction before (the approvals
        // widget's own `connected` check missing the stale case, same shape
        // of bug). No route exists yet that can tell the server which option
        // was meant (`net/ApiModels.kt`'s `needsChoice` doc comment), so
        // approving one at all - from this call, whatever screen, widget, or
        // future surface reaches it - would silently apply whichever plan
        // the server defaults to.
        if (approve && item.needsChoice) {
            val msg = "This proposal offers ${item.options.size} options, and no " +
                "Jarvis client can pick one yet. Deny still works."
            _notice.value = msg
            return ApiResult.Failed(ApiError.Unreachable(msg))
        }
        val blocker = decisionBlocker(item)
        if (blocker != null) {
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        // Claimed before the POST and released in `finally`, so a screen that
        // goes away mid-flight (cancellation) or a throw cannot leave the id
        // latched and every later attempt at it refused.
        _deciding.update { it + item.id }
        try {
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
        } finally {
            _deciding.update { it - item.id }
        }
    }

    /**
     * A route this desktop may not have yet is reported as such, not as the
     * generic "wrong address" wording [describe] gives every other 404 -
     * see [JarvisApi.amend] and [JarvisApi.pauseTask]'s own doc comments for
     * why a 404 means something more specific here.
     */
    private fun describeDraft(e: ApiError, amend: Boolean = false): String =
        com.jarvis.client.net.TaskControl.failure(e, amend) ?: describe(e)

    /**
     * A note sent before the first decision on a proposal -
     * AUTONOMY-PROPOSALS.md §3b, matching the desktop's own `amend()`.
     *
     * Deliberately not gated on [decisionBlocker] the way [decide] is: a
     * note is never itself a verdict on anything Jarvis is holding, only a
     * message attached to one - the same reasoning that already excuses
     * `markDigestSeen`/`setMuted` from that gate.
     *
     * What the desktop does with it (`backend/task-control.patch`): the note
     * is kept WITH the card, the card itself does not change, and the model
     * reads the note together with the owner's answer. So success says
     * exactly that, and the queue is refreshed in case the card was answered
     * elsewhere meanwhile.
     */
    suspend fun amendPending(id: String, note: String): ApiResult<Unit> {
        val result = api.amend(id, note)
        when (result) {
            is ApiResult.Ok -> {
                _notice.value = com.jarvis.client.net.TaskControl.NOTE_KEPT
                refreshPending()
            }
            is ApiResult.Failed -> _notice.value = describeDraft(result.error, amend = true)
        }
        return result
    }

    /**
     * Pause, resume, stop, or add a note to whatever Jarvis is running -
     * AUTONOMY-PROPOSALS.md §3d, served by the desktop's
     * `backend/task-control.patch`. Pause, Stop and the note are never gated
     * on [decisionBlocker]: sending "please stop" is safe to attempt
     * regardless of the event stream's own staleness - the moment you most
     * want Stop is the moment the link is misbehaving - and none of them is
     * a verdict on anything pending.
     *
     * **Resume is the exception, and does not carry on by itself.** The
     * desktop raises one approval card listing the steps that are left and
     * runs them only if that card is approved; being the one control that
     * makes work go again, it is held while the link is stale (rule 4).
     *
     * **This function must never set `_activity` to PAUSED itself.** A
     * request succeeding only means the desktop accepted the HTTP call, not
     * that it actually paused - the honesty rule the desktop's own widget
     * learned the hard way (see `AUTONOMY-PROPOSALS.md` §3d's own account of
     * it). The UI shows Paused only once a real event reports
     * `activity: "paused"`, through the ordinary [Activity.from] path.
     */
    suspend fun pauseTask(): ApiResult<Unit> = runTaskAction { api.pauseTask() }

    suspend fun resumeTask(): ApiResult<Unit> {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            val blocker = com.jarvis.client.net.TaskControl.RESUME_WHILE_STALE
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = runTaskAction { api.resumeTask() }
        if (result is ApiResult.Ok) _notice.value = com.jarvis.client.net.TaskControl.RESUME_ASKED
        return result
    }

    suspend fun stopTask(): ApiResult<Unit> = runTaskAction { api.stopTask() }

    suspend fun injectTaskNote(note: String): ApiResult<Unit> =
        runTaskAction { api.injectTaskNote(note) }

    /**
     * Files a note in Logseq, Joplin or Obsidian through the desktop - the owner's own
     * words, no model - and reports how it ended in the shared notice, in the
     * desktop's own words (see [com.jarvis.client.net.NoteCapture]).
     *
     * Not gated on [decisionBlocker]: filing a note is not an answer to
     * anything Jarvis is holding, and the write itself goes through the
     * desktop's approval gate under the owner's own rules. If a card is up,
     * this keeps asking on the runtime's own scope - so leaving the screen
     * does not lose the answer - until it is final or [NoteCapture.GIVE_UP_MS]
     * passes, and never says "Filed" before the desktop does.
     */
    suspend fun fileNote(target: String, text: String): ApiResult<Unit> {
        val first = api.captureNote(target, text)
        val job = when (first) {
            is ApiResult.Failed -> {
                _notice.value = com.jarvis.client.net.NoteCapture.failure(first.error)
                    ?: describe(first.error)
                return ApiResult.Failed(first.error)
            }
            is ApiResult.Ok -> first.value
        }
        val said = com.jarvis.client.net.NoteCapture.describe(job, target)
        _notice.value = said.text
        val id = com.jarvis.client.net.NoteCapture.jobId(job)
        if (!said.final && id != null) {
            scope.launch {
                val started = SystemClock.elapsedRealtime()
                // Survives a dropped link and a failed poll or two - see JobFollow.
                val follow = com.jarvis.client.net.JobFollow()
                while (true) {
                    delay(com.jarvis.client.net.NoteCapture.POLL_MS)
                    if (SystemClock.elapsedRealtime() - started > com.jarvis.client.net.NoteCapture.GIVE_UP_MS) {
                        _notice.value = com.jarvis.client.net.NoteCapture.GAVE_UP
                        break
                    }
                    if (!follow.shouldPoll(_link.value == LinkState.CONNECTED)) continue
                    val next = api.noteStatus(id)
                    if (next is ApiResult.Failed) {
                        if (!follow.failed()) continue
                        _notice.value = "Lost track of the note (${describe(next.error)}). " +
                            "Check the approval card on the desktop and your notes app."
                        break
                    }
                    follow.answered()
                    val now = com.jarvis.client.net.NoteCapture.describe(
                        (next as ApiResult.Ok).value, target,
                    )
                    if (now.final) {
                        _notice.value = now.text
                        break
                    }
                }
            }
        }
        return ApiResult.Ok(Unit)
    }

    /**
     * Which note apps the desktop is set up for, asked fresh each time the
     * quick-note plate opens. A failure is [NoteCapture.Targets.Unknown] with
     * the reason, so the plate shows no button rather than all of them.
     */
    suspend fun noteTargets(): com.jarvis.client.net.NoteCapture.Targets {
        val t = when (val r = api.noteTargets()) {
            is ApiResult.Ok -> com.jarvis.client.net.NoteCapture.targets(r.value)
            is ApiResult.Failed ->
                com.jarvis.client.net.NoteCapture.targetsFailure(r.error, describe(r.error))
        }
        _noteTargets.value = t
        return t
    }

    /**
     * A chat line that starts with `#log`, `#obs`, `#joplin` (and the rest of
     * [com.jarvis.client.net.NoteCapture.PREFIXES]) files the rest as a note
     * instead of asking Jarvis - the desktop's quickbar does the same.
     *
     * Asks the desktop which note apps are set up first, then follows the
     * desktop's own decision ([com.jarvis.client.net.NoteCapture.chatNote]):
     * an app the PC says is not set up, or an empty note, is refused here
     * with nothing sent. Otherwise [fileNote] sends it, and reports how it
     * ended in the desktop's words.
     *
     * @return true once the note was accepted (filed, or waiting for its
     *   card), so the caller can clear the chat box; false keeps the words.
     */
    suspend fun fileChatNote(p: com.jarvis.client.net.NoteCapture.Prefixed): Boolean =
        when (val plan = com.jarvis.client.net.NoteCapture.chatNote(p, noteTargets())) {
            is com.jarvis.client.net.NoteCapture.ChatNote.NotFiled -> {
                _notice.value = plan.why
                false
            }
            is com.jarvis.client.net.NoteCapture.ChatNote.File ->
                fileNote(plan.target, plan.text) is ApiResult.Ok
        }

    // ------------------------------------------------------------- wiki ----

    private val _wikiJob =
        MutableStateFlow<Pair<String, com.jarvis.client.net.Wiki.Said>?>(null)

    /**
     * The document this phone last asked to add to the wiki, and how that is
     * going, in the desktop's own words - null until something is asked.
     */
    val wikiJob: StateFlow<Pair<String, com.jarvis.client.net.Wiki.Said>?> =
        _wikiJob.asStateFlow()

    /** `GET /api/wiki` - see [com.jarvis.client.net.Wiki]. */
    suspend fun wiki(): ApiResult<JsonObject> = api.wiki()

    /**
     * "Add to wiki" for one document. The desktop's model reads it, then one
     * approval card is raised - nothing is written until it is answered.
     *
     * Held on a stale or dropped link ([actionBlocker], rule 4): the card it
     * raises should be answered from a queue known to be live. Like
     * [fileNote], the job is followed on the runtime's own scope, so leaving
     * the screen does not lose the answer, and [wikiJob] never says "added"
     * before the desktop does.
     */
    suspend fun addToWiki(source: String): ApiResult<Unit> {
        actionBlocker()?.let {
            _wikiJob.value = source to com.jarvis.client.net.Wiki.Said(it, final = true, done = false)
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        val job = when (val first = api.wikiIngest(source)) {
            is ApiResult.Failed -> {
                val text = com.jarvis.client.net.Wiki.failure(first.error) ?: describe(first.error)
                _wikiJob.value = source to com.jarvis.client.net.Wiki.Said(text, final = true, done = false)
                return ApiResult.Failed(first.error)
            }
            is ApiResult.Ok -> first.value
        }
        val said = com.jarvis.client.net.Wiki.describe(job)
        _wikiJob.value = source to said
        val id = com.jarvis.client.net.Wiki.jobId(job)
        if (!said.final && id != null) {
            scope.launch {
                val started = SystemClock.elapsedRealtime()
                // Survives a dropped link and a failed poll or two - see JobFollow.
                val follow = com.jarvis.client.net.JobFollow()
                while (true) {
                    delay(com.jarvis.client.net.Wiki.POLL_MS)
                    if (SystemClock.elapsedRealtime() - started > com.jarvis.client.net.Wiki.GIVE_UP_MS) {
                        _wikiJob.value = source to com.jarvis.client.net.Wiki.Said(
                            com.jarvis.client.net.Wiki.GAVE_UP, final = true, done = false,
                        )
                        break
                    }
                    if (!follow.shouldPoll(_link.value == LinkState.CONNECTED)) continue
                    val next = api.wikiJob(id)
                    if (next is ApiResult.Failed) {
                        if (!follow.failed()) continue
                        _wikiJob.value = source to com.jarvis.client.net.Wiki.Said(
                            "Lost track of it (${describe(next.error)}). Check the approval " +
                                "card on the desktop and the wiki folder.",
                            final = true, done = false,
                        )
                        break
                    }
                    follow.answered()
                    val now = com.jarvis.client.net.Wiki.describe((next as ApiResult.Ok).value)
                    _wikiJob.value = source to now
                    if (now.final) break
                }
            }
        }
        return ApiResult.Ok(Unit)
    }

    // ------------------------------------------------------------ watch ----

    private val _watchTick = MutableStateFlow(0)

    /**
     * Goes up by one on every `finding` event, so the Watches plate on Mind
     * reads its two lists again - the desktop's Brain re-reads the same two
     * on that event (`brain.js`, `refreshes.finding`).
     */
    val watchTick: StateFlow<Int> = _watchTick.asStateFlow()

    /** `GET /api/watch` - see [com.jarvis.client.net.Watch]. */
    suspend fun watch(): ApiResult<JsonObject> = api.watch()

    /** `GET /api/watch/report` - a peek; it marks nothing read. */
    suspend fun watchReport(): ApiResult<JsonObject> = api.watchReport()

    /**
     * Watch a GitHub topic. Creating a watch is turning something ON, so it
     * is held while the link is down or stale ([actionBlocker], rule 4). If
     * the PC asks first, its card is answered like any other.
     *
     * @return whether the PC took it (added, or waiting for its card), and
     *   the sentence to show. Not taken leaves the form filled in.
     */
    suspend fun addWatch(
        name: String,
        query: String,
        minStars: String,
        language: String,
        notify: Boolean,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Watch.addBody(name, query, minStars, language, notify)
            ?: return false to "Type a name. Min stars, if you fill it in, must be a whole number."
        return when (val r = writeNoticingCards { api.watchAdd(body) }) {
            is ApiResult.Ok -> (r.value !is com.jarvis.client.net.DesktopWrite.Outcome.Refused) to
                com.jarvis.client.net.Watch.addSaid(name.trim(), r.value)
            is ApiResult.Failed -> false to ("Not added. " +
                (com.jarvis.client.net.Watch.failure(r.error) ?: describe(r.error)))
        }
    }

    /**
     * Forget a topic. Never held on a stale link: it only stops something,
     * the same rule as every OFF on this phone.
     */
    suspend fun removeWatch(name: String): String =
        when (val r = writeNoticingCards { api.watchRemove(name) }) {
            is ApiResult.Ok -> com.jarvis.client.net.Watch.removeSaid(name, r.value)
            is ApiResult.Failed -> "Not forgotten. " +
                (com.jarvis.client.net.Watch.failure(r.error) ?: describe(r.error))
        }

    /**
     * "Mark these read". Not held on a stale link, like the brief's own
     * mark-read ([markDigestSeen]) and like the desktop's: it approves and
     * starts nothing.
     */
    suspend fun markWatchSeen(): String =
        when (val r = writeNoticingCards { api.watchSeen() }) {
            is ApiResult.Ok -> com.jarvis.client.net.Watch.seenSaid(r.value)
            is ApiResult.Failed -> "Not marked read. " +
                (com.jarvis.client.net.Watch.failure(r.error) ?: describe(r.error))
        }

    // --------------------------------------------------- memory counts ----

    /** `GET /api/memory/status` - see [com.jarvis.client.net.MemoryCounts]. Read-only. */
    suspend fun memoryStatus(): ApiResult<JsonObject> =
        api.probe(com.jarvis.client.net.MemoryCounts.STATUS_PATH)

    /** Whether learning is on, off `GET /api/memory/facts?limit=1`. */
    suspend fun memoryLearning(): Boolean? =
        (api.probe(com.jarvis.client.net.MemoryCounts.LEARNING_PATH) as? ApiResult.Ok)
            ?.value?.let { com.jarvis.client.net.MemoryCounts.learning(it) }

    /**
     * The learning switch. ON is held on a stale link (rule 4) and raises an
     * approval card on the PC; OFF is never held - it only narrows what
     * Jarvis does. @return the sentence to show under the switch.
     */
    suspend fun setLearning(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setLearning(on) }) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryCounts.learningSaid(on, r.value)
            is ApiResult.Failed -> "Not changed. " + describe(r.error)
        }
    }

    // ----------------------------------------------------------- skills ----

    /**
     * Removes one skill ([com.jarvis.client.net.Skills]), after the Mind
     * screen's own "are you sure". Not held on a stale link: it only takes
     * something away, the same rule as every OFF here - and the desktop does
     * not hold it either. If the PC raises a card for it, that is said.
     * The list is read again either way.
     *
     * @return the sentence to show under the list.
     */
    suspend fun removeSkill(name: String): String {
        val said = when (val r = writeNoticingCards { api.removeSkill(name) }) {
            is ApiResult.Ok -> com.jarvis.client.net.Skills.removeSaid(name, r.value)
            is ApiResult.Failed -> "Not removed. " +
                (com.jarvis.client.net.Skills.failure(r.error) ?: describe(r.error))
        }
        refreshSkills()
        return said
    }

    /** Just the skills list - all a removal can have changed. */
    suspend fun refreshSkills() {
        val (skills, read) = api.probe(com.jarvis.client.net.Skills.PATH).asSection()
        _brain.update { it.copy(skills = skills, skillsRead = read) }
    }

    /**
     * Sends one change whose answer's shape is not written down, and counts
     * it as waiting for a card when a new card turned up in the queue while
     * it was out ([com.jarvis.client.net.DesktopWrite.withNewCard]) - so the
     * phone never says "done" over a card it can see.
     */
    private suspend fun writeNoticingCards(
        call: suspend () -> ApiResult<com.jarvis.client.net.DesktopWrite.Outcome>,
    ): ApiResult<com.jarvis.client.net.DesktopWrite.Outcome> {
        val before = _pending.value.map { it.id }.toSet()
        val r = call()
        if (r !is ApiResult.Ok) return r
        refreshPending()
        val newCard = _pending.value.any { it.id !in before }
        return ApiResult.Ok(com.jarvis.client.net.DesktopWrite.withNewCard(r.value, newCard))
    }

    private suspend fun runTaskAction(call: suspend () -> ApiResult<Unit>): ApiResult<Unit> {
        val result = call()
        if (result is ApiResult.Failed) _notice.value = describeDraft(result.error)
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
            // The queue alone. A full refreshBrain here was nine requests per
            // fact kept or discarded, for five sections the decision cannot
            // have touched.
            is ApiResult.Ok -> refreshMemoryQueue()
            is ApiResult.Failed -> _notice.value = describe(result.error)
        }
        return result
    }

    /**
     * "Both are true" on a correction card: keep the new fact and the old
     * one (`memory-intake.patch`). Gated exactly like [decideMemory] - it is
     * a decision on the same queue, so it waits for a live link.
     *
     * 409 means the desktop refused the third answer for this card (it has
     * no old fact to keep); 404 that the card was already answered. Either
     * way the card list is re-read so the screen shows the truth, and the
     * owner is told in one plain sentence.
     */
    suspend fun keepBothMemory(id: Long): ApiResult<Unit> {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            val blocker = "Not connected to the desktop, so this decision cannot be delivered."
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = api.keepBothMemory(id)
        when (result) {
            is ApiResult.Ok -> refreshMemoryQueue()
            is ApiResult.Failed -> {
                _notice.value = when (result.error) {
                    ApiError.AlreadyHandled ->
                        "The desktop would not keep both for that card. Answer it with Keep or Discard."
                    ApiError.NotFound -> "That card was already answered."
                    else -> describe(result.error)
                }
                refreshMemoryQueue()
            }
        }
        return result
    }

    /**
     * Marks the answer [turnId] right or wrong - or takes the mark back when
     * the owner taps the mark already chosen ([Feedback.nextMark]).
     *
     * Not an approval, and it never changes memory. It is still a write to
     * the desktop that can end in a "stop using this fact?" card, so it
     * follows the same rule as the other writes here: nothing is sent while
     * the link is down or stale ([actionBlocker]).
     *
     * One answer at a time, and a second tap while the first is on its way
     * is ignored rather than queued. If the desktop cannot take marks for
     * this answer (404: it does not know the answer; 503: the feedback
     * module is not installed), the buttons are swapped for one quiet line -
     * no error wall.
     */
    fun markAnswerDetached(turnId: String, tapped: AnswerMark) {
        // On the runtime's own scope, like [decideDetached]: a rotation must
        // not cancel the call between the POST and the state update, which
        // would leave the buttons greyed out as "saving" for good.
        scope.launch { markAnswer(turnId, tapped) }
    }

    suspend fun markAnswer(turnId: String, tapped: AnswerMark): ApiResult<Unit> {
        actionBlocker()?.let {
            _notice.value = it
            return ApiResult.Failed(ApiError.Unreachable(it))
        }
        // Check-and-claim in one atomic step. Two quick taps each launch on
        // the multi-threaded runtime scope, and a separate read-then-write
        // let both through - two marks racing, and the screen free to end up
        // showing the one the desktop did not keep.
        var claimed = false
        var current = AnswerMark.NONE
        _answerMark.update { s ->
            val mine = s?.takeIf { it.turnId == turnId }
            if (mine?.busy == true || mine?.unavailable == true) {
                claimed = false
                s
            } else {
                claimed = true
                current = mine?.mark ?: AnswerMark.NONE
                AnswerMarkState(turnId, current, busy = true)
            }
        }
        if (!claimed) return ApiResult.Failed(ApiError.AlreadyHandled)
        val next = Feedback.nextMark(current, tapped)
        val result = api.markAnswer(turnId, next)
        _answerMark.update { s ->
            if (s == null || s.turnId != turnId) {
                s
            } else {
                when (result) {
                    is ApiResult.Ok -> s.copy(mark = next, busy = false)
                    is ApiResult.Failed -> when (result.error) {
                        ApiError.NotFound, ApiError.NotAvailable ->
                            s.copy(busy = false, unavailable = true)
                        else -> s.copy(busy = false)
                    }
                }
            }
        }
        if (result is ApiResult.Failed &&
            result.error != ApiError.NotFound && result.error != ApiError.NotAvailable
        ) {
            _notice.value = "That mark did not reach the desktop. " + describe(result.error)
        }
        return result
    }

    /**
     * Answers the daily overnight-tidy card (not built yet: "enable" only
     * records the wish, and nothing runs). Same
     * shape as [decideMemory]: a live link is required for the same reason -
     * the desktop's own `/api/memory/sleep_time` handler is behind the same
     * connection this queue is.
     */
    suspend fun setSleepTime(enabled: Boolean? = null, remind: Boolean? = null): ApiResult<Unit> {
        if (_stale.value || _link.value != LinkState.CONNECTED) {
            val blocker = "Not connected to the desktop, so this decision cannot be delivered."
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = api.setSleepTime(enabled, remind)
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
            if (down != 0L) {
                val silentFor = nowMs - down
                // Long enough that this is almost certainly not a blip - the
                // laptop lid is closed, or the machine actually went to sleep.
                // The spec's error face is a deliberately alarming reversed
                // motion, and a sleeping machine is not a broken one. BANKED
                // already exists for exactly "nothing is wrong, nothing needs
                // you right now" - reused rather than inventing a state the
                // desktop would also need to agree on, since this is a purely
                // local, phone-side judgement call about how long is "a while".
                if (silentFor > LONG_SILENCE_MS) return FaceState.BANKED
                if (silentFor > RECONNECT_GRACE_MS) return FaceState.ERROR
            }
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
            act == Activity.THINKING || act == Activity.WORKING || act == Activity.PAUSED ->
                FaceState.THINKING
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

    /** How often the coalesced resume point may reach SharedPreferences. */
    private const val RESUME_WRITE_GAP_MS = 2_000L

    private const val KEEPALIVE_GAP_MS = 70_000L
    private const val WATCHDOG_TICK_MS = 10_000L

    /** A status line, not a log: anything longer is cut before it is shown. */
    private const val ACTIVITY_DETAIL_MAX = 200

    /**
     * How long a reconnect may run before the face admits something is wrong.
     * Long enough to cover a handover between cell towers or a screen-off doze
     * wakeup; short enough that a desktop that has actually gone away does not
     * keep pretending to think.
     */
    private const val RECONNECT_GRACE_MS = 12_000L

    /** When to re-read the second-card switches after a decision: see [recheckSecondCardAfterDecision]. */
    private val SECOND_CARD_RECHECK_MS = longArrayOf(0L, 1_500L, 5_000L)

    /**
     * Past this, "reconnecting" stops being the honest word for it. Short
     * enough that checking the phone a few minutes after the desktop actually
     * went to sleep shows calm rather than alarm; long enough that no real
     * network blip - a train, a lift, a bad patch of wifi - ever reaches it.
     */
    private const val LONG_SILENCE_MS = 180_000L

    /** When the link was last lost, or 0 while it is up. */
    @Volatile private var linkDownSince = 0L
}
