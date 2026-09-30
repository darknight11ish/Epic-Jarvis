package com.jarvis.client

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.jarvis.client.data.AppearanceStore
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.ModelsCacheStore
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ActivityEvent
import com.jarvis.client.net.AnswerMark
import com.jarvis.client.net.AnswerMarkState
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.CachedModels
import com.jarvis.client.net.Feedback
import com.jarvis.client.net.MemoryCards
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.onOk
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.GateHistoryItem
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.SseEvent
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.net.EventStream
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.BigModel
import com.jarvis.client.net.Hardware
import com.jarvis.client.net.InboxTidy
import com.jarvis.client.net.PcHelp
import com.jarvis.client.net.SecondCard
import com.jarvis.client.net.SignedApproval
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
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.voice.StrictVoice
import com.jarvis.client.voice.VoiceRounds
import com.jarvis.client.voice.VoiceSession
import com.jarvis.client.voice.VoiceTraining
import com.jarvis.client.voice.liveIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
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
    /** "Activity" - past approvals. Its own key: see [pastApprovals]. */
    val activity: SectionRead = SectionRead.Reading,
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

    /**
     * The application context, for the one notification this object posts
     * itself: a timer, an alarm or a reminder that went off on the PC
     * ([onScheduleEvent]). The application's, never an Activity's.
     */
    @Volatile private var appContext: Context? = null
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
     * `/api/models`, or null when this backend does not offer the capability,
     * has not been asked yet, or the most recent read failed. Switching
     * between models the desktop already has was allowed onto the phone on
     * 2026-09-18, and installing a typed model name on 2026-09-20
     * (CLAUDE.md) - both only ever ASK, through an approval card. Browsing
     * what could be installed is still off the phone.
     *
     * Null on a failure - rather than the previous session's last good
     * value staying put in silence - since [refreshModels]'s 2026-09-28
     * cache addition: [modelsCache] is what a failed read falls back to
     * now, WITH a visible "last saw this at…" label
     * (`docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`), so there is no longer a
     * reason for this flow to also carry an unlabelled stale answer. This
     * has no other reader today ([modelsView] combines this with
     * [modelsCache] for `BrainScreen.kt`'s `ModelsPlate`), so nothing else
     * depended on the old behaviour.
     */
    private val _models = MutableStateFlow<ModelsInfo?>(null)
    val models: StateFlow<ModelsInfo?> = _models.asStateFlow()

    private lateinit var modelsCacheStore: ModelsCacheStore

    private val _modelsCache = MutableStateFlow<CachedModels?>(null)

    /**
     * The phone's own last successful `GET /api/models` read, held on disk
     * (`docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`) so Brain -> Model has
     * something to show, clearly marked as old, whenever [refreshModels]
     * fails - including on a cold start, before any read this run has
     * succeeded at all. Loaded once at [initialize] and refreshed only as
     * a side effect of a live read succeeding; never re-read specially,
     * per the design doc's section 4 ("do not sync or refresh the cache on
     * demand"). See [com.jarvis.client.net.ModelsView] for how the screen
     * turns this, plus [models], into what it actually draws.
     */
    val modelsCache: StateFlow<CachedModels?> = _modelsCache.asStateFlow()

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

    /**
     * `/api/hardware`: the PC's graphics cards and the three setups it worked
     * out for them ([Hardware]). Read on the Mind screen, after every choice,
     * step and measurement, and after an approval is decided while a step's
     * card was waiting.
     */
    private val _hardware = MutableStateFlow<Hardware.Read>(Hardware.Read.NotAsked)
    val hardware: StateFlow<Hardware.Read> = _hardware.asStateFlow()

    private val _power = MutableStateFlow("active")
    val power: StateFlow<String> = _power.asStateFlow()

    /**
     * Why the PC is in that power mode, in its own sentence (`GET /api/version`
     * `capabilities.power.why`), or null when it did not say. The face reads
     * it for one thing: a focus session's Quiet shows the focus buddy, not a
     * sleeping animal ([com.jarvis.client.face.RestingFace]). `/api/status`
     * and the `power` event carry only the mode, so it is read again from the
     * handshake route on every `power` event, as the desktop does.
     */
    private val _powerWhy = MutableStateFlow<String?>(null)

    /**
     * Lockdown is on (backend jarvis_asks_first.py, 2026-09-28): every way out
     * of the PC asks first, or has stopped. From `/api/version`'s
     * `capabilities.lockdown` at every handshake, then the `lockdown` event.
     * False from a PC without it. Home says so while it is true.
     */
    private val _lockdown = MutableStateFlow(false)
    val lockdown: StateFlow<Boolean> = _lockdown.asStateFlow()

    /**
     * The PC's "Watch with me" status - `{on, state, left_s, ...}`, never a
     * word from the screen ([com.jarvis.client.net.ScreenRules], JARVIS-API
     * section 62) - so Home can show the same "Jarvis is watching" sign the
     * PC shows, with Stop. Null before the first read or on a PC without it.
     */
    private val _screenWatch = MutableStateFlow<JsonObject?>(null)
    val screenWatch: StateFlow<JsonObject?> = _screenWatch.asStateFlow()

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

    /**
     * "Activity" - past approvals, read-only (ease-of-use audit, 2026-09-27,
     * row 11). Never the same list as [pending]: this is `/api/pending`'s
     * `history` array, fetched by name ([JarvisApi.gateHistoryRead]), which
     * is a different call to a different key than the one [refreshPending]
     * makes - see that function's own comment on why the two must not mix.
     */
    private val _pastApprovals = MutableStateFlow<List<GateHistoryItem>>(emptyList())
    val pastApprovals: StateFlow<List<GateHistoryItem>> = _pastApprovals.asStateFlow()

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

    private val _problem = MutableStateFlow<com.jarvis.client.net.PlainErrors.Shown?>(null)

    /**
     * The last failure put into plain words ([com.jarvis.client.net.PlainErrors]):
     * its fix button and its scrubbed Details. It belongs to the notice on
     * screen only while [notice] is its [com.jarvis.client.net.PlainErrors.Shown.text]
     * - Home checks that, so a later, different notice never shows an old
     * failure's button or Details.
     */
    val problem: StateFlow<com.jarvis.client.net.PlainErrors.Shown?> = _problem.asStateFlow()

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

    private val _faceOffline = MutableStateFlow(false)

    /**
     * Jarvis cannot be reached: the link has been down or stale past the
     * grace ([com.jarvis.client.face.FaceLink]). [face] is STANDBY while this
     * is true; the face adds its hollow ring and TalkBack says "Jarvis isn't
     * connected" (FaceView's `offline`).
     */
    val faceOffline: StateFlow<Boolean> = _faceOffline.asStateFlow()

    private val _faceFocusQuiet = MutableStateFlow(false)

    /**
     * The face is IDLE (not STANDBY) because a focus session put the PC on
     * Quiet ([com.jarvis.client.face.RestingFace]): the focus buddy shows.
     * Only TalkBack's words use it (FaceView's `focusQuiet`).
     */
    val faceFocusQuiet: StateFlow<Boolean> = _faceFocusQuiet.asStateFlow()

    private val _faceSerious = MutableStateFlow(false)

    /**
     * A serious moment: a crisis answer is being given or spoken
     * (docs/JARVIS-API.md section 38.1, the `wellbeing` event). The animal
     * faces hold a calm, plain, neutral pose while this is true (FaceView's
     * `serious`); the mouth still follows the voice. Set by the event only -
     * true on `{"serious": true}`, false on `{"serious": false}` - with a
     * safety net: [SERIOUS_NET_MS] after the last true with no false, it
     * ends by itself, so a missed frame can never leave the face neutral for
     * good. A reconnect keeps what it had (section 38.1).
     */
    val faceSerious: StateFlow<Boolean> = _faceSerious.asStateFlow()
    private var seriousNet: Job? = null

    /** The serious moment's safety net: 600 s + 300 s (section 38.1). */
    private const val SERIOUS_NET_MS = 900_000L

    /** Where the phone keeps its copy of the sky settings (SkySettings.encode). */
    private const val SKY_PREFS = "jarvis_sky"
    private const val SKY_KEY = "stored"

    /**
     * When the link was cut - down, or up but stale - for the face; 0 while
     * it is healthy. Set from [linkDownSince] when that is earlier (the drop
     * itself), else from the moment the face job first saw it. Only the face
     * job touches it.
     */
    private var faceCutSince = 0L

    private var streamJob: Job? = null
    private var watchdog: Job? = null
    private var faceJob: Job? = null
    private var widgetJob: Job? = null
    private var boardJob: Job? = null

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
        val modelsStore = ModelsCacheStore(app)
        val jarvisApi = JarvisApi(clientSettings, tokenStore)
        // A temporary chat only on a PC that says it has one (docs/JARVIS-API.md
        // section 18.1): read from the last handshake, when it is asked.
        val chatSession = ChatSession(jarvisApi, canTemporary = { can(com.jarvis.client.net.TemporaryChat.CAPABILITY) })
        // The link check is a lambda, not a value: it is read at the moment
        // "hey Jarvis" ON is asked for, and `actionBlocker` reads the flows.
        val voiceSession = VoiceSession(
            app,
            jarvisApi,
            scope,
            linkBlocker = { actionBlocker() },
            // For "private answers stay on screen": tools that ran (the `step`
            // event), and whether the stream could have told us.
            toolWatch = {
                com.jarvis.client.voice.PrivateAloud.Watch(
                    runs = toolRuns,
                    drops = streamOpens,
                    live = _link.value == LinkState.CONNECTED && !_stale.value,
                    privateRuns = privateToolRuns,
                    screenRuns = screenReads,
                )
            },
            // "Say 'One moment' if I'm kept waiting" (Checks), read when a
            // tool starts during a spoken question.
            oneMoment = { clientSettings.oneMoment.value },
            // "Play a short sound when I finish speaking" (Checks), read
            // each time the "I heard you" sound would play.
            heardSoundOn = { clientSettings.heardSound.value },
            // Where the owner cut a spoken answer off: sent once, with the
            // next question (typed or spoken), as `interrupted`.
            onCutOff = { said -> chatSession.cutOff.cut(said, android.os.SystemClock.elapsedRealtime()) },
            // "Open a chat" while Floating Jarvis is up (JARVIS-API §56).
            // Gated here, not in VoiceSession, on the setting being
            // anything but OFF: the phrase always still reaches the model
            // like any other sentence (see the constructor param's own
            // doc) - this only decides whether it ALSO pops the app to the
            // front, which nobody who never turned Floating Jarvis on
            // should see happen out of nowhere.
            onOpenChatPhrase = {
                if (clientSettings.floatingAvatar.value != com.jarvis.client.data.FloatingAvatarMode.OFF) {
                    val intent = android.content.Intent(app, MainActivity::class.java)
                        .setAction(MainActivity.ACTION_START_VOICE)
                        .addFlags(
                            android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                                android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP,
                        )
                    runCatching { app.startActivity(intent) }
                }
            },
            // Jarvis Live (voice/LiveRules.kt): lowered, not paused, while
            // the PC checks another voice; no tap buttons while a card of
            // THIS session waits (LiveRules.cardInSession - an older card
            // used to hide them for good); every reply that is about Live,
            // not a question; and the first sound of a Live answer.
            liveOn = { liveOnHere() },
            cardShown = { liveCardHolds() },
            onLive = { heard -> onLiveReply(heard) },
            onLiveSound = { liveAnswerSounded() },
            onLiveSideTalk = { liveSideTalk() },
        ) { text, live, onRoute, onStatus, onDelta ->
            // The value `send` returns, not the shared flow read afterwards.
            // There is one `_reply`, so a typed message sent mid-answer would
            // cancel the spoken one and leave its own partial reply in there —
            // and Jarvis would say it aloud as the answer to the question that
            // was spoken. `onDelta` is this same call's own local callback,
            // not a subscription to that shared flow - see ChatSession.send's
            // own doc for why that distinction is the whole point. `onRoute`
            // is the same kind of callback, for the answer's header.
            // Tagged "voice": this is the transcript the PC's speech route
            // gave back (chat history, docs/JARVIS-API.md section 18).
            // `onStatus`: a card this spoken question waits on is said aloud,
            // and then how it ended (voice/CardVoice.kt).
            chatSession.send(
                text, onDelta, onRoute = onRoute, provenance = com.jarvis.client.net.Provenance.VOICE,
                onStatus = onStatus,
                // Said in Jarvis Live: `live: true` on the message.
                live = live,
            )?.takeIf { it.isNotBlank() }
        }

        settings = clientSettings
        appContext = app
        tokens = tokenStore
        api = jarvisApi
        appearance = AppearanceStore(app)
        modelsCacheStore = modelsStore
        // Read once, at startup - so a cold start with Jarvis off has
        // something to paint at once instead of a blank screen while the
        // first live read times out. Never re-read after this except as a
        // side effect of a live read succeeding, in refreshModels().
        _modelsCache.value = modelsStore.load(clientSettings.host.value)
        updates = UpdateChecker(clientSettings)
        chat = chatSession
        voice = voiceSession
        // Jarvis Live: a call ringing or starting while Jarvis talks takes
        // the audio focus - Jarvis stops, and Live pauses for the call.
        voiceSession.speaker.onFocusLost = { liveFocusLost() }
        stream = EventStream(jarvisApi)
        started = true

        // The sun, moon and weather behind the animals (SkySettings): this
        // phone's last copy first, so the sky shows at once and while the PC
        // cannot be reached; then the PC's, every POLL_MS while connected.
        com.jarvis.client.face.SkyNow.stored = com.jarvis.client.net.SkySettings.decode(
            runCatching { app.getSharedPreferences(SKY_PREFS, Context.MODE_PRIVATE).getString(SKY_KEY, null) }
                .getOrNull(),
        )
        scope.launch {
            _link.collectLatest { link ->
                if (link != LinkState.CONNECTED) return@collectLatest
                while (true) {
                    runCatching { sky() }
                    delay(com.jarvis.client.net.SkySettings.POLL_MS)
                }
            }
        }
        // The shared animal switches (AnimalOptions) for the faces: the new
        // behaviours (face.AnimalNow) and the seasonal touches (SeasonNow),
        // whenever they arrive - this phone's copy first, then the PC's. The
        // PC's defaults until either has been heard - not counted as a read
        // (AnimalNow.reads), so a face opened before the real ones arrive
        // still takes them at once.
        scope.launch {
            appearance.animal.collect { shared ->
                val values = (shared ?: com.jarvis.client.net.AnimalOptions.Shared()).values
                com.jarvis.client.face.AnimalNow.apply(values, stored = shared != null)
                com.jarvis.client.face.SeasonNow.on = values["seasonal"] == true
            }
        }

        // Inbox tidy (docs/JARVIS-API.md section 95): the newest tidy still
        // open to Undo, read every POLL_MS while connected - a tiny read of
        // counts and words, never a sender or a subject. The clock ticks even
        // while the link is down, so an Undo whose ten minutes are up goes.
        scope.launch {
            while (true) {
                if (_link.value == LinkState.CONNECTED) {
                    runCatching { refreshInboxTidy() }
                } else {
                    _inboxTidyClock.value = SystemClock.elapsedRealtime()
                }
                delay(InboxTidy.POLL_MS)
            }
        }

        faceJob = scope.launch {
            // `_stale` is in the combine: a stale link is as cut as a dropped
            // one (rule 4 blocks acting on it), and the face has to hear
            // about it and about its end.
            combine(_link, _activity, _power, _pending, _attention) { _, _, _, _, _ -> }
                .combine(voice.phase) { _, _ -> }
                .combine(_stale) { _, _ -> }
                .combine(_powerWhy) { _, _ -> }
                .collectLatest {
                    val wait = publishFace()
                    if (wait > 0L) {
                        // Re-evaluate once the grace is up, so a reconnect that
                        // does not come back does eventually show as offline.
                        // collectLatest cancels this the moment anything
                        // changes, so a reconnect that succeeds never reaches it.
                        delay(wait)
                        publishFace()
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
        // "Jarvis widget" 1-3 (docs/JARVIS-API.md section 86): redrawn - and
        // so read again from the PC - when the link comes or goes stale, when
        // a timer or reminder changes, when the saved widgets change here,
        // when a slot is given another widget, or when App lock or "Hide
        // memory lists" changes (so the words hide, and the buttons turn into
        // "open Jarvis", at once - not up to 30 minutes later). Never on a
        // clock of its own beyond the launcher's half-hourly update.
        boardJob?.cancel()
        boardJob = scope.launch {
            combine(_link, _stale, _scheduleTick, _widgetsTick, settings.homeWidgets) { _, _, _, _, _ -> }
                .combine(settings.security) { _, _ -> }
                .collect { com.jarvis.client.widget.JarvisBoardWidgets.updateAll(app) }
        }
        // "Reading phone notifications": turning it off is immediate, so
        // whenever the switch reads as off - pressed here, or learned from
        // the PC - nothing captured stays on this phone (audit A3). Also
        // runs once at start: an off switch never has rows behind it.
        // Brain -> Model's remembered list belongs to one PC: when the phone is
        // pointed at another, what was kept for the old one stops showing.
        scope.launch {
            settings.host.collect { h -> _modelsCache.value = modelsCacheStore.load(h) }
        }
        scope.launch {
            settings.phoneNotifications.collect { on ->
                if (!on) runCatching { com.jarvis.client.data.CapturedNotifications(app).clear() }
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
                _powerWhy.value = result.value.powerWhy()
                _lockdown.value = com.jarvis.client.net.AsksFirst.lockdownFrom(
                    result.value.detail("lockdown"),
                ) ?: false
                _notice.value = null
                // A new handshake may be a different (or upgraded) server:
                // ask it about the appearance route afresh.
                appearanceRoute = null
            }
            is ApiResult.Failed -> _notice.value = describe(result.error, handshake = true)
        }
        return result
    }

    /**
     * A failure in the plain words both apps use (PlainErrors, from
     * tools/gen_plain_error_cases.py): what happened, then what to do - never
     * a raw error, an exception's text or a status number. The fix button and
     * the scrubbed technical detail are kept in [problem] for Home's notice.
     * [handshake]: `GET /api/version`, where a 404 means "not Jarvis at all".
     */
    private fun describe(e: ApiError, handshake: Boolean = false): String {
        if (e == ApiError.AlreadyHandled) return "Already handled elsewhere."
        val plain = com.jarvis.client.net.PlainErrors.forApiError(e, handshake)
        // A refused key whose 401 said why (docs/PAIRING-DESIGN.md §5.3):
        // that sentence instead of the general one. Otherwise unchanged.
        val why = if (e == ApiError.BadToken) com.jarvis.client.net.KeyRefusal.words() else null
        val shown = if (why != null) plain.copy(says = why, fix = "") else plain
        _problem.value = shown
        return shown.text
    }

    /**
     * The same plain words as [describe], for a screen that shows them itself.
     * It does NOT touch [problem]: a screen reading a failure of its own must
     * not take the button and Details away from the notice on Home.
     */
    fun noticeFor(e: ApiError): String =
        if (e == ApiError.AlreadyHandled) "Already handled elsewhere."
        else com.jarvis.client.net.PlainErrors.forApiError(e).text

    /**
     * A failure already put into plain words (a failed question, from
     * ChatSession): the notice says it, and Home shows its button and Details.
     */
    fun setProblem(shown: com.jarvis.client.net.PlainErrors.Shown) {
        _problem.value = shown
        _notice.value = shown.text
    }

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
     * @param force true only for a reconnect the owner asked for by tapping,
     *   or one of the two automatic cases that replace a connection known to
     *   be dead: coming back to a link that is catching up (MainActivity's
     *   onResume) and a change of network ([reconnectForNetworkChange],
     *   which waits for the network to settle). Every other automatic caller
     *   must leave it false: the early return when a stream is already
     *   running is what stops the retry paths stacking connections.
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

        // A stream that died on its own leaves its watchdog running; without this
        // the next start put a second one beside it (bug audit 2026-09-29).
        watchdog?.cancel()
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

    /** A reconnect waiting for the network to settle ([reconnectForNetworkChange]). */
    @Volatile private var networkReconnect: Job? = null

    /**
     * The phone's network changed - Wi-Fi to mobile data, Tailscale or
     * Meshnet switched on or off - so the connection the stream holds is
     * very likely dead, and replacing it now beats noticing ~70 seconds of
     * silence plus up to 30 seconds of back-off later (phone walk-through,
     * 2026-09-27). Called by [com.jarvis.client.platform.NetworkWatch].
     *
     * Waits [NETWORK_SETTLE_MS] first, and a second change inside that wait
     * starts the wait again: leaving the house hands Wi-Fi to mobile data
     * and the VPN re-attaches a moment later, and one reconnect after the
     * last of those is enough - so a network that flaps cannot turn into a
     * reconnect loop, and the last change is never dropped.
     *
     * Only while the link is meant to be running: a stream that was stopped
     * is never started from here. It approves nothing: a replaced stream
     * starts stale, and acting stays blocked until it is trusted again
     * (rule 4).
     */
    fun reconnectForNetworkChange() {
        if (!started) return
        networkReconnect?.cancel()
        networkReconnect = scope.launch(Dispatchers.Main) {
            delay(NETWORK_SETTLE_MS)
            if (streamJob?.isActive != true) return@launch
            Log.i(TAG, "the phone's network changed; reconnecting now")
            startStream(force = true)
        }
    }

    private val _vpnUp = MutableStateFlow<Boolean?>(null)

    /**
     * Whether this phone's default network is a VPN (Tailscale and NordVPN
     * Meshnet both are): true, false, or null when not known - no network,
     * or the watch is not running. For [LinkWords.vpnOffLine] only; nothing
     * is decided on it.
     */
    val vpnUp: StateFlow<Boolean?> = _vpnUp.asStateFlow()

    fun noteVpn(up: Boolean?) { _vpnUp.value = up }

    fun stopStream() {
        networkReconnect?.cancel(); networkReconnect = null
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

    /**
     * `step` events that said a tool ran, and how many times the stream has
     * (re)opened - read by the voice loop's private-answer rule
     * ([com.jarvis.client.voice.PrivateAloud.Watch]). Counters only.
     */
    @Volatile private var toolRuns = 0L

    /** Of [toolRuns], the ones whose tool is not on PrivateAloud.READ_ALOUD_TOOLS. */
    @Volatile private var privateToolRuns = 0L

    /** Of [toolRuns], the ones that were the screen being read (`read_screen`, owner 2026-09-28). */
    @Volatile private var screenReads = 0L
    @Volatile private var streamOpens = 0L

    /**
     * The newest event id the PC had when this connection opened
     * (`hello.latest`): every event at or below it is the PC replaying what
     * this phone missed (AnimalNow.isReplay), above it is live. -1 until
     * this connection's hello, or from a PC that does not send it. Read so
     * the animal's moments - a fact's nod, a long answer's glow, the focus
     * stretch - play for what happens now, never for a replay after a
     * reconnect or a restart.
     */
    @Volatile private var replayUpTo = -1L

    private suspend fun onOpen(hello: com.jarvis.client.net.HelloPayload?) {
        // The connect (no hello yet) forgets the last connection's replay
        // point; the hello, the first frame, brings this one's.
        replayUpTo = hello?.latest ?: -1L
        // A (re)connect: step events may have been missed since the last one.
        streamOpens += 1
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
            // A focus session's "ended" may be among what was missed: the
            // animal's focus buddy must not stay on for good.
            com.jarvis.client.face.AnimalNow.focusUnknown()
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
        // Part of the PC's replay of what this phone missed (see replayUpTo).
        val replayed = com.jarvis.client.face.AnimalNow.isReplay(event.id, replayUpTo)
        when (event.kind) {
            "approval" -> {
                val phoneCardBefore = com.jarvis.client.net.PhoneNotifications
                    .cardWaiting(_pending.value.map { it.action })
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
                // A setup's step whose card was up: a decided card is the
                // moment it is done (or refused). There is no event for it.
                val hw = _hardware.value
                if (hw is Hardware.Read.Loaded && hw.status.applying != null) {
                    scope.launch { refreshHardware() }
                }
                // And the voice cards: "hey Jarvis" ON and a voice training.
                // Neither has an event of its own either, so without this the
                // Checks screen said "Waiting" over a card already decided.
                if (voice.answered.value && voice.status.value.cardWaiting) {
                    recheckVoiceAfterDecision()
                }
                // A custom-voice card (add, switch, the better voice): the PC
                // rings `voices` when one ends, and this is the belt to that
                // pair of braces - a PC whose event list drops `voices`
                // would otherwise leave "Waiting" on the Voices screen.
                val cv = customVoiceStatus()
                if (cv != null && (cv.pending != null || cv.better.pending)) refreshCustomVoices()
                // "Read phone notifications" has no event of its own either:
                // when its card leaves the queue (decided on the PC or here),
                // the switch is read again, so the listener's cached copy
                // follows it without the settings page being open (audit A2).
                val phoneCardNow = com.jarvis.client.net.PhoneNotifications
                    .cardWaiting(_pending.value.map { it.action })
                if (phoneCardBefore && !phoneCardNow) {
                    scope.launch { runCatching { phoneNotificationsSettings() } }
                }
            }
            // A custom-voice card ended, a voice was deleted, the voice went
            // back to the built-in one, or the better voice went off
            // (`{"what", "outcome"}` - a doorbell, never a name or words).
            // Read again only once the Voices screen has asked.
            "voices" -> if (customVoicesAsked) refreshCustomVoices()
            // A deep question finished (`{"id", "state"}` only - a doorbell,
            // never the question or the answer). The list is re-read for the
            // answer, and the switches for the speed it measured.
            "deep" -> {
                // A long answer ready: the animal's glow (a doorbell only) -
                // not for a replayed one.
                com.jarvis.client.face.AnimalNow.deepEvent(event.data, replayed)
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
                // A chatbot conversation has no event of its own; its progress
                // rides on this line ("Talking to Gemini: message 3 of 5.").
                // Start watching it - even one started on the desktop - so the
                // ongoing notification and Brain's card keep up.
                if (com.jarvis.client.net.Chatbot.isChatbotActivity(_activityDetail.value)) {
                    watchChatbot()
                }
                // A customer-support chat's progress rides on the same line
                // ("Chat with Groupon: message 2 of 15.").
                if (com.jarvis.client.net.Support.isSupportActivity(_activityDetail.value)) {
                    watchSupport()
                }
                refreshStatus()
            }
            "power", "persona" -> {
                refreshStatus()
                // Who put the PC in this mode can change while the mode
                // does not (a focus session's Quiet, then the owner's own).
                if (event.kind == "power") refreshPowerWhy()
            }
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
            // Facts saved WITHOUT a card (automatic learning,
            // docs/JARVIS-API.md section 19): `{"ids": [...]}` only, never
            // the text - a doorbell like the rest. The list on Mind reads
            // itself again, and a quiet line counts them. Never a
            // notification: nothing here reaches ApprovalNotifier.
            com.jarvis.client.net.AutoLearn.EVENT -> onMemorySaved(event.data, replayed)
            // A timer, alarm or reminder went off on the PC, or Coming up
            // changed (`{"id", "kind", "state"}` only - a doorbell, never the
            // words). The list on Mind reads itself again; a job that went
            // off is read by id and shown as a notification.
            com.jarvis.client.net.Schedule.EVENT -> onScheduleEvent(event.data, event.id)
            // "Ring my phone" (2026-09-28): `{"id", "state", "at", "until",
            // "seconds"}` and no words. Rings on the alarm channel, never for
            // a stale or replayed event (net/FindPhone.kt).
            com.jarvis.client.net.FindPhone.EVENT -> onRingPhone(event.data)
            // Lockdown turned on or off (`{"on": bool}`, 2026-09-28): Home's
            // line follows it; "What asks first" reads itself again when shown.
            "lockdown" -> com.jarvis.client.net.AsksFirst.lockdownFrom(event.data as? JsonObject)
                ?.let { _lockdown.value = it }
            // A focus session started, changed (locked on, a drift began or
            // ended, paused...) or ended (`{"state"}` only, or a callout's
            // number - a doorbell, never what was in front). Mind's "Focus
            // session" reads itself again. The spoken line is the PC's
            // alone: the phone is refused it, and does not ask.
            "focus" -> {
                // The animal's focus buddy, and its stretch as a session ends
                // (not for a replayed end).
                com.jarvis.client.face.AnimalNow.focusEvent(event.data, replayed)
                _focusTick.update { it + 1 }
            }
            // The PC started, paused, extended or ended "Watch with me"
            // (the event IS the status: `{on, state, left_s, ...}`, never a
            // word from the screen). Home's sign follows it. An event that
            // is not that shape is a doorbell: the status is read again.
            com.jarvis.client.net.ScreenRules.EVENT -> {
                val status = (event.data as? JsonObject)?.takeIf { it.containsKey("state") }
                if (status != null) _screenWatch.value = status else scope.launch { refreshScreenWatch() }
            }
            // Jarvis Live changed (`{"state", "device", "paused", "muted"...}`
            // only - a doorbell, never anything said): read it again.
            "live" -> liveRead()
            // Face and bindings changed on another device. Each device renders
            // its own face and the server is only the sync channel, so this
            // just re-reads the shared document; nothing here redraws
            // anything directly.
            "appearance" -> refreshAppearance()
            // The sun, moon or weather changed on the PC (a change made on
            // the desktop, or asked of Jarvis; `{"changed": true}` only - a
            // doorbell, never the town or the weather): read them again so
            // the face and Appearance show it now, not at the next poll.
            "sky" -> runCatching { sky() }
            // One step of the tool loop - asking the model, a tool starting,
            // finishing or refused - kept for Mind's "What Jarvis is doing".
            // It used to fall through to "unhandled" below.
            "step" -> {
                // Counted for "private answers stay on screen": an answer a
                // tool helped write is not read aloud (PrivateAloud).
                if (com.jarvis.client.voice.PrivateAloud.isToolRun(event.data)) toolRuns += 1
                // ...unless the tool is web search or home status (owner, 2026-09-27).
                if (com.jarvis.client.voice.PrivateAloud.isPrivateToolRun(event.data)) privateToolRuns += 1
                // ...and an answer about the screen, which "Hey Jarvis" under
                // "Only trust the talk button" keeps on screen (owner, 2026-09-28).
                if (com.jarvis.client.voice.PrivateAloud.isScreenRead(event.data)) screenReads += 1
                // A tool starting during a spoken question: "One moment."
                // (once per question, before the answer makes a sound).
                if (com.jarvis.client.voice.VoiceFlow.isToolStart(event.data) && started) {
                    voice.toolStarted()
                }
                val line = com.jarvis.client.net.Steps.Line(
                    com.jarvis.client.net.Steps.clock(System.currentTimeMillis()),
                    com.jarvis.client.net.Steps.text(event.data),
                )
                _steps.update { com.jarvis.client.net.Steps.append(it, line) }
            }
            // A serious moment starts or ends (section 38.1): one boolean,
            // never a word. A second true while one is open just restarts
            // the safety net.
            "wellbeing" -> {
                // A JSON true or false only - never the string "true", as
                // the desktop (typeof ... === "boolean").
                val serious = ((event.data as? JsonObject)?.get("serious") as? JsonPrimitive)
                    ?.takeIf { !it.isString }?.content?.toBooleanStrictOrNull()
                if (serious != null) onSerious(serious)
            }
            else -> Log.d(TAG, "unhandled event kind '${event.kind}'")
        }
    }

    private fun onSerious(serious: Boolean) {
        seriousNet?.cancel()
        seriousNet = null
        _faceSerious.value = serious
        if (serious) {
            seriousNet = scope.launch {
                delay(SERIOUS_NET_MS)
                _faceSerious.value = false
            }
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
        // The "read phone notifications" switch, so a change made on the PC
        // (or a card approved there) reaches this phone on reconnect, not
        // only when its settings page opens (audit A2). Its own failure,
        // including a PC without the route, changes nothing.
        runCatching { phoneNotificationsSettings() }
        // Whether the PC is watching its own screen, for Home's sign.
        runCatching { refreshScreenWatch() }
    }

    /** Reads whether the PC is watching its screen. A PC without the route changes nothing. */
    suspend fun refreshScreenWatch() {
        api.screenWatch().onOk { _screenWatch.value = it }
    }

    /**
     * "Stop watching" on the sign: ends the PC's Watch with me. **Never held
     * on a stale link and never a card**, like Stop and Stop everything -
     * ending it only ever makes Jarvis look at less. The status is read
     * again afterwards, so the sign follows the PC's own answer.
     */
    suspend fun stopScreenWatch(): String? {
        val result = api.stopScreenWatch()
        refreshScreenWatch()
        // A failed stop says so (the sign stays as the PC last said it), and a
        // success says nothing. The words are ScreenPlateText.STOP_FAILED.
        return if (result is ApiResult.Failed) com.jarvis.client.net.ScreenPlateText.STOP_FAILED else null
    }

    /**
     * Reads only [_powerWhy] again. Not [handshake]: that also forgets the
     * appearance route and clears the notice, which a power change has no
     * business doing. A failed read keeps what was known.
     */
    private suspend fun refreshPowerWhy() {
        api.version().onOk { _powerWhy.value = it.powerWhy() }
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
     *
     * A live success also writes [modelsCache] to disk
     * (`docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`), so the next cold start -
     * or the very next failure - has something to replay. A failure clears
     * [models] rather than leaving the last good answer sitting there
     * unlabelled: `BrainScreen.kt`'s `ModelsPlate` reads [models] together
     * with [modelsCache] through [com.jarvis.client.net.modelsView], and
     * that function's whole contract is that a null [models] means "fall
     * back to the cache, and say plainly it is old" - a stale value left in
     * [models] itself would draw as though it were still live. The on-disk
     * cache is never touched by a failure either way: only a fresh success
     * is ever worth keeping, never re-read specially, per the design doc's
     * "never fetched specially" rule.
     */
    suspend fun refreshModels() {
        if (version.value?.can("models") != true) {
            _models.value = null
            return
        }
        when (val result = api.models()) {
            is ApiResult.Ok -> {
                _models.value = result.value
                val cached = CachedModels.from(result.value, System.currentTimeMillis())
                modelsCacheStore.save(cached, settings.host.value)
                _modelsCache.value = cached
            }
            is ApiResult.Failed -> _models.value = null
        }
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

    /**
     * Moving one of the second card's own switches onto a third, capable
     * graphics card, or moving it back off (2026-09-28). `assign` a feature
     * id raises one approval card (the card should appear in this phone's
     * approvals too, the same as [setSecondCard]'s own ON); `assign = null`
     * unassigns at once.
     */
    suspend fun setThirdCard(assign: String?): String? {
        actionBlocker()?.let { return it }
        val result = api.setThirdCard(assign)
        if (assign != null && result is ApiResult.Ok) refreshPending()
        refreshSecondCard()
        return SecondCard.replyLine(result)
    }

    /**
     * "When to suggest the bigger model" (2026-09-27): one signal on or off.
     * NO approval card either way - it only changes whether Jarvis may
     * OFFER [SecondCard.COMBINED] on its own, never what it may do without
     * a person's yes, so there is no [refreshPending] here, unlike
     * [setSecondCard]. Refused while the link is down or stale
     * ([actionBlocker], rule 4) all the same.
     *
     * @param signal `"struggle"` or `"correction"`.
     * @return a sentence to show, or null when the plate already says it.
     */
    suspend fun setSecondCardSuggest(signal: String, enabled: Boolean): String? {
        actionBlocker()?.let { return it }
        val result = api.setSecondCardSuggest(signal, enabled)
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

    // --------------------------------------------------------- PC help ----

    /**
     * Reads `/api/pc/help` once ([PcHelp]). Nothing is kept here: the answer
     * can name programs on the PC, so the screen that asked holds it and
     * drops it when it closes. A read, so not held on a stale link.
     */
    suspend fun pcHelp(): PcHelp.Read = PcHelp.readOf(api.pcHelp())

    // --------------------------------------------------------- hardware ----

    /** Re-reads `/api/hardware`. Reads only; a failed read is said in words. */
    suspend fun refreshHardware() {
        _hardware.value = Hardware.readOf(api.hardware())
    }

    /**
     * Chooses a setup, or forgets the choice ([preset] null). Choosing changes
     * no model and no setting on the PC: it lists the steps. Choosing is held
     * on a stale link ([actionBlocker], rule 4); forgetting is not - it only
     * narrows what runs.
     */
    suspend fun chooseHardware(preset: String?): String {
        if (preset != null) actionBlocker()?.let { return it }
        val result = api.hardwarePost(Hardware.APPLY_PATH, Hardware.applyBody(preset))
        refreshHardware()
        return Hardware.replyLine(result)
    }

    /**
     * Asks for ONE step of the chosen setup, by its id. The route and body are
     * read from a fresh `GET /api/hardware` ([Hardware.stepRequest]) - never
     * made up here - and the PC raises that step's own approval card, decided
     * on the PC or in this phone's approvals like any other. Only the next
     * step can be asked for; nothing is approved in bulk.
     */
    suspend fun hardwareStep(stepId: String): String {
        actionBlocker()?.let { return it }
        refreshHardware()
        val status = (_hardware.value as? Hardware.Read.Loaded)?.status
            ?: return Hardware.readLine(_hardware.value) ?: Hardware.UPDATE
        return when (val ask = Hardware.stepRequest(status, stepId)) {
            is Hardware.StepAsk.No -> ask.reason
            is Hardware.StepAsk.Post -> {
                val result = api.hardwarePost(ask.route, ask.body)
                // The card should appear in this phone's approvals too.
                if (result is ApiResult.Ok) refreshPending()
                if (ask.route == SecondCard.PATH) refreshSecondCard()
                refreshHardware()
                Hardware.replyLine(result)
            }
        }
    }

    /** Asks the PC to measure the setup's models (it loads each once). */
    suspend fun measureHardware(): String {
        actionBlocker()?.let { return it }
        val result = api.hardwarePost(Hardware.MEASURE_PATH, "{}")
        refreshHardware()
        return Hardware.replyLine(result)
    }

    // ------------------------------------------------------- web search ----
    // The owner's decisions of 2026-09-25 - see [com.jarvis.client.net.WebSearch]
    // and ui/screens/WebSearchPlate.kt. The phone chooses the provider, sets
    // the SearXNG address, turns "Ask before every web search" on or off (off
    // raises ONE approval card on the PC) and runs a test search. It never
    // takes an Exa, Tavily or Brave key: those are typed on the PC only.

    /** `GET /api/search`. A read: never held. */
    suspend fun webSearch(): ApiResult<JsonObject> = api.webSearch()

    // ------------------------------------------------ what Jarvis can reach ----
    // The Muse audit, 2026-09-25 - see [com.jarvis.client.net.Reach] and
    // ui/screens/ReachPlate.kt. Every way Jarvis can reach something outside
    // itself, written by the PC from its settings, never by the model.

    /** `GET /api/reach`. A read: never held. */
    suspend fun reach(): ApiResult<JsonObject> = api.reach()

    // ------------------------------------------------------------- backups -----
    // The owner's decision of 2026-09-27 - see [com.jarvis.client.net.Backup]
    // and ui/screens/BackupPlate.kt. Read-only here on purpose: choosing a
    // folder, backing up and restoring all happen on the PC, in Jarvis
    // Desktop's Settings (docs/ARCHITECTURE.md section 8).

    /** `GET /api/backup`. A read: never held. */
    suspend fun backup(): ApiResult<JsonObject> = api.backup()

    // ------------------------------------------------------ what asks first ----
    // The owner's decisions of 2026-09-26 - see [com.jarvis.client.net.AsksFirst]
    // and ui/screens/AsksFirstPlate.kt. Stricter from the phone; looser on
    // the PC only.

    /** `GET /api/asks_first`. A read: never held. */
    suspend fun asksFirst(): ApiResult<JsonObject> = api.asksFirst()

    /**
     * "Ask me first" ON for ONE action - the desktop's `set_asks_first` with
     * `ask: true`. Never held on a stale link: it only makes Jarvis ask more.
     * @return the sentence to show.
     */
    suspend fun makeAskFirst(action: String): String {
        val r = api.makeAskFirst(action)
        return when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.AsksFirst.said(r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.AsksFirst.missing(r.error)) {
                    com.jarvis.client.net.AsksFirst.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /**
     * Lockdown ON (2026-09-28) - the desktop's `set_asks_first` with the
     * action "lockdown" and `ask: true`. Never held on a stale link: it only
     * makes Jarvis ask more. The phone never turns it off.
     * @return the sentence to show.
     */
    suspend fun turnOnLockdown(): String {
        val r = api.lockdownOn()
        return when (r) {
            is ApiResult.Ok -> {
                if (r.value is com.jarvis.client.net.DesktopWrite.Outcome.Done) _lockdown.value = true
                com.jarvis.client.net.AsksFirst.said(r.value)
            }
            is ApiResult.Failed ->
                if (com.jarvis.client.net.AsksFirst.missing(r.error)) {
                    com.jarvis.client.net.AsksFirst.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /**
     * "Playing on your PC" (2026-09-28): `GET /api/media`, the PC's own
     * sentence ("Paused: ..."), or null when it could not be read. A read:
     * never held. What is playing is only shown - never saved or sent on.
     */
    suspend fun pcMedia(): String? = when (val r = api.pcMedia()) {
        is ApiResult.Ok -> com.jarvis.client.net.PcMedia.said(r.value)
        is ApiResult.Failed ->
            if (com.jarvis.client.net.PcMedia.missing(r.error)) com.jarvis.client.net.PcMedia.MISSING
            else null
    }

    /**
     * ONE media button: play, pause, next or previous on the PC. No card (the
     * owner's decision of 2026-09-27), but held on a stale link (rule 4), like
     * every change. @return the PC's own sentence, or why not.
     */
    suspend fun pcMediaControl(action: String): String {
        actionBlocker()?.let { return it }
        return when (val r = api.pcMediaControl(action)) {
            is ApiResult.Ok -> com.jarvis.client.net.PcMedia.said(r.value) ?: "Done."
            is ApiResult.Failed ->
                if (com.jarvis.client.net.PcMedia.missing(r.error)) com.jarvis.client.net.PcMedia.MISSING
                else noticeFor(r.error)
        }
    }

    /**
     * The 10-minute timer tile (Quick Settings tiles, docs/JARVIS-API.md
     * section 81.2): ONE plain timer, `POST /api/schedule/add {"kind":
     * "timer", "seconds": 600}` - no card (a plain timer needs none), held on
     * a stale link (rule 4) like every change. @return whether it was set,
     * and the sentence to show.
     */
    suspend fun addTileTimer(): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.data.QuickTiles.timerBody()
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> {
                val (ok, words) = com.jarvis.client.net.Schedule.said(r.value)
                if (ok) {
                    _scheduleTick.update { n -> n + 1 }
                    true to com.jarvis.client.data.QuickTiles.TIMER_SET
                } else {
                    false to words
                }
            }
            is ApiResult.Failed -> false to ("Not set. " + describe(r.error))
        }
    }

    /**
     * Runs [block] on the runtime's own long-lived scope rather than a
     * caller's. For a Quick Settings tile: Android may unbind the tile (and
     * cancel its own scope) the moment the panel closes, which would cut a
     * request off half way.
     */
    fun launchDetached(block: suspend () -> Unit): Job = scope.launch { block() }

    /**
     * "Lights, plugs and fans without a card" - the desktop's
     * `set_lights_without_card`. ON is held on a stale link (rule 4) and
     * raises ONE approval card on the PC; OFF is never held.
     * @return the sentence to show.
     */
    suspend fun setLightsWithoutCard(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        val r = writeNoticingCards { api.setLightsWithoutCard(on) }
        return when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.AsksFirst.said(r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.AsksFirst.missing(r.error)) {
                    com.jarvis.client.net.AsksFirst.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /**
     * `GET /api/email/sending` - Mind's "Sending email" line
     * ([com.jarvis.client.net.EmailSending], ui/screens/EmailSendingPlate.kt).
     * A read: never held. There is nothing to change from the phone: the
     * account is set on the PC, and each email is its own approval card.
     */
    suspend fun emailSending(): ApiResult<JsonObject> = api.emailSending()

    /** "Folders Jarvis may look in" - `GET /api/folders` ([com.jarvis.client.net.Folders]). */
    suspend fun folders(): ApiResult<JsonObject> = api.folders()

    /**
     * Take ONE folder off "Folders Jarvis may look in". At once, never held
     * on a stale link: it only lets Jarvis see less (the desktop's
     * `remove_folder`). @return the sentence to show.
     */
    suspend fun removeFolder(path: String): String =
        when (val r = api.removeFolder(path)) {
            is ApiResult.Ok -> com.jarvis.client.net.Folders.said(r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.Folders.missing(r.error)) {
                    com.jarvis.client.net.Folders.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }

    /**
     * ONE web search setting, with [body] from [com.jarvis.client.net.WebSearch]'s
     * providerBody / addressBody / askBody. Held on a stale link ([actionBlocker],
     * rule 4). Turning "Ask before every web search" off raises a card on the PC,
     * which this phone's approvals show too.
     */
    suspend fun setWebSearch(body: String?): String {
        actionBlocker()?.let { return it }
        if (body == null) return "That is not something this screen can change."
        val result = api.webSearchPost(com.jarvis.client.net.WebSearch.SETTINGS_PATH, body)
        if (result is ApiResult.Ok) refreshPending()
        return com.jarvis.client.net.WebSearch.replyLine(result)
    }

    /**
     * One test search for a fixed word through the chosen provider. Held on a
     * stale link. @return whether it worked, and the PC's sentence (with its
     * offer to switch when it did not).
     */
    suspend fun testWebSearch(): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return com.jarvis.client.net.WebSearch.testLine(
            api.webSearchPost(com.jarvis.client.net.WebSearch.TEST_PATH, "{}"),
        )
    }

    // ----------------------------------------------------------- manner ----
    // "How Jarvis talks" (the owner's decision of 2026-09-25) - see
    // [com.jarvis.client.net.Manner] and ui/screens/MannerPlate.kt. Warm and
    // brief, or plain: wording only, so no card either way.

    /** `GET /api/manner`. A read: never held. */
    suspend fun manner(): ApiResult<JsonObject> = api.manner()

    /**
     * ONE change: "warm" or "plain". No approval card either way (it changes
     * only how answers are worded), but held on a stale link like every
     * change sent to the PC ([actionBlocker], rule 4).
     */
    suspend fun setManner(manner: String): String {
        actionBlocker()?.let { return it }
        val body = com.jarvis.client.net.Manner.body(manner)
            ?: return "That is not one of the two choices."
        return com.jarvis.client.net.Manner.replyLine(api.mannerPost(body), manner)
    }

    /**
     * Humour, on or off (the owner's decision, 2026-09-27): "a switch in
     * 'How Jarvis talks', off to start." No approval card either way, but
     * held on a stale link like [setManner] and every other change sent to
     * the PC ([actionBlocker], rule 4). The SAME `/api/manner` route, so
     * setting this never resets the manner choice.
     */
    suspend fun setHumor(on: Boolean): String {
        actionBlocker()?.let { return it }
        val body = com.jarvis.client.net.Manner.humorBody(on)
        return com.jarvis.client.net.Manner.humorReplyLine(api.mannerPost(body), on)
    }

    // ------------------------------------------ sun, moon and weather ----

    /**
     * `GET /api/sky` (the owner's decisions of 2026-09-28). A good answer is
     * also kept for the faces ([com.jarvis.client.face.SkyNow]) and in this
     * phone's own settings - only the rounded position and the weather
     * numbers, never the town's name - so the sky keeps moving while the PC
     * cannot be reached. An older PC means nothing is drawn.
     */
    suspend fun sky(): ApiResult<JsonObject> {
        val r = api.sky()
        when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.SkySettings.parse(r.value)?.let { keepSky(it) }
            is ApiResult.Failed -> if (com.jarvis.client.net.SkySettings.missing(r.error)) keepSky(null)
        }
        return r
    }

    private fun keepSky(v: com.jarvis.client.net.SkySettings.View?) {
        val s = com.jarvis.client.net.SkySettings.storedOf(v)
        com.jarvis.client.face.SkyNow.stored = s
        runCatching {
            appContext?.getSharedPreferences(SKY_PREFS, Context.MODE_PRIVATE)?.edit()
                ?.putString(SKY_KEY, com.jarvis.client.net.SkySettings.encode(s))?.apply()
        }
    }

    /**
     * ONE sky change ([com.jarvis.client.net.SkySettings]'s bodies: show on or
     * off, forget the town, a weather source). Adding something is held on a
     * stale link ([actionBlocker], rule 4); hiding, forgetting and "off" never
     * are - they only make Jarvis do less. Open-Meteo ON approves nothing
     * here: the PC raises ONE approval card.
     */
    suspend fun setSky(body: String): String {
        if (com.jarvis.client.net.SkySettings.adds(body)) actionBlocker()?.let { return it }
        val r = api.skyPost(body)
        if (r is ApiResult.Ok) {
            (r.value["view"] as? JsonObject)?.let { com.jarvis.client.net.SkySettings.parse(it) }?.let { keepSky(it) }
        }
        return com.jarvis.client.net.SkySettings.replyLine(r)
    }

    // ------------------------------------------------- animal options ----

    /**
     * `GET /api/animal` (the owner's decisions of 2026-09-28, "Animal
     * options"): "Keep the animal still" and the behaviour switches, shared
     * with the desktop. A good answer is kept ([AppearanceStore.setAnimal])
     * for the face, and this phone's old Still is moved to the PC once
     * ([moveOldStill]).
     */
    suspend fun animalOptions(): ApiResult<JsonObject> {
        val r = api.animal()
        if (r is ApiResult.Ok) {
            com.jarvis.client.net.AnimalOptions.parse(r.value)?.let {
                appearance.setAnimal(it.shared)
                moveOldStill(it.shared)
            }
        }
        return r
    }

    /**
     * ONE animal switch. No card either way (cosmetic); turning one ON is
     * held on a stale link ([actionBlocker], rule 4, as the sky's switch is),
     * turning one OFF never is. Returns the PC's sentence, or the plain words
     * of a failure.
     */
    suspend fun setAnimalOption(id: String, on: Boolean): String {
        val body = com.jarvis.client.net.AnimalOptions.body(id, on) ?: return "That is not an animal option."
        if (on) actionBlocker()?.let { return it }
        val r = api.animalPost(body)
        if (r is ApiResult.Ok) {
            (r.value["view"] as? JsonObject)?.let { com.jarvis.client.net.AnimalOptions.parse(it) }?.let {
                appearance.setAnimal(it.shared)
            }
        }
        return com.jarvis.client.net.AnimalOptions.replyLine(r)
    }

    /**
     * This phone's old "Keep the animal still" (`Look.stillAnimal`, kept on
     * the phone only before 2026-09-28) goes to the PC ONCE, and only if it
     * was on - "if either device had Still on, keep it on". Until it lands
     * an old "on" still counts on this phone
     * ([com.jarvis.client.net.AnimalOptions.effectiveStill]); a failure (the
     * PC not reachable, the link catching up) is tried again next time.
     */
    private suspend fun moveOldStill(shared: com.jarvis.client.net.AnimalOptions.Shared) {
        if (appearance.animalMigrated.value) return
        if (!appearance.look.value.stillAnimal || shared.still) {
            appearance.markAnimalMigrated()
            return
        }
        if (actionBlocker() != null) return
        // Only while nobody has chosen anything on the PC yet: a switch
        // changed there since (on the desktop, or by asking Jarvis) is newer
        // than this phone's old choice, and wins.
        val now = api.animal()
        if (now !is ApiResult.Ok) return
        if (!com.jarvis.client.net.AnimalOptions.stillMoveNeeded(now.value)) {
            appearance.markAnimalMigrated()
            return
        }
        val r = api.animalPost(com.jarvis.client.net.AnimalOptions.body("still", true) ?: return)
        if (r is ApiResult.Ok) {
            appearance.markAnimalMigrated()
            (r.value["view"] as? JsonObject)?.let { com.jarvis.client.net.AnimalOptions.parse(it) }?.let {
                appearance.setAnimal(it.shared)
            }
        }
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
        // A picture model sees it, or the PC reads the words in it (2026-09-26).
        if (SecondCard.picturesTaken(read)) return null
        val why = com.jarvis.client.net.ChatPicture.notWorkingWhy(read)
        return "The picture was not sent: Pictures on the second graphics card is not " +
            "working right now, and your PC cannot read the words in it" +
            (why?.let { " ($it)" } ?: "") + "."
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

    // ------------------------------- voice: rounds, the two settings, the test

    private val _voiceSent = MutableStateFlow<VoiceRounds.Plan?>(null)

    /**
     * The training plan this phone last FINISHED sending - sentence numbers
     * only, never audio - so the PC's "round 2, clip 5 was left out" can be
     * turned back into the sentence to read again. Memory only: after a
     * restart the phone honestly does not know, and says only how many.
     */
    val voiceSent: StateFlow<VoiceRounds.Plan?> = _voiceSent.asStateFlow()

    /**
     * Sends round [index] of [plan]. Every round but the last is HELD on the
     * PC (no card, nothing changed); the last carries `finish` and raises ONE
     * card for all of them. An older PC's single round goes the old way
     * ([sendVoiceTraining]).
     *
     * Only the round that raises the card ([VoiceRounds.raisesCard]: the
     * last round, or an older PC's one-shot) is held on a stale or dropped
     * link ([actionBlocker], rule 4), like the desktop. The rounds before it
     * are only held in memory on the PC - no card, nothing changed - so they
     * always go; on a dropped link they simply fail to arrive. Nothing here
     * is logged or kept: the caller drops the round's clips once this says
     * accepted.
     */
    suspend fun sendVoiceRound(plan: VoiceRounds.Plan, index: Int, clips: List<ByteArray>): VoiceRounds.Result {
        if (VoiceRounds.raisesCard(plan, index)) {
            actionBlocker()?.let { return VoiceRounds.Result(false, it) }
        }
        if (plan.kind == VoiceRounds.Kind.SINGLE_OLD) {
            val r = sendVoiceTraining(clips)
            if (r.accepted) _voiceSent.value = plan
            return VoiceRounds.Result(r.accepted, r.message, finished = r.accepted)
        }
        if (!voice.strict.value.rounds) {
            return VoiceRounds.Result(false, "Your PC does not take training in rounds yet. Run the patch script on the PC first.")
        }
        val last = VoiceRounds.isLast(plan, index)
        if (index > 0) {
            // The earlier rounds must still be held: the PC drops them 15
            // minutes after the last, and a round sent after that would
            // start a new training with only itself in it.
            voice.refreshStatus()
            if (!voice.answered.value) {
                return VoiceRounds.Result(
                    false,
                    "Could not ask your PC whether it still holds the earlier rounds. Try again.",
                )
            }
            VoiceRounds.lostRounds(plan, index, voice.strict.value.session)?.let {
                return VoiceRounds.Result(false, it)
            }
        }
        return when (val result = api.voiceEnroll(VoiceRounds.body(plan, index, clips, VoiceTraining.MIC))) {
            is ApiResult.Ok -> {
                val a = result.value
                if (a.accepted && last) {
                    _voiceSent.value = plan
                    // The card should appear in this phone's approvals too.
                    refreshPending()
                }
                voice.refreshStatus()
                VoiceRounds.Result(
                    accepted = a.accepted,
                    message = when {
                        !a.accepted -> VoiceRounds.otherSessionLine(a)
                            ?: VoiceRounds.sentence(a.error.ifBlank { a.message.ifBlank { "Your PC did not take that round." } })
                        last -> VoiceRounds.finishedLine(a)
                        else -> VoiceRounds.heldLine(a, plan, index)
                    },
                    finished = a.accepted && last,
                    heldElsewhere = a.session != null,
                )
            }
            is ApiResult.Failed -> VoiceRounds.Result(false, describe(result.error))
        }
    }

    /**
     * Cancel: every round the PC is holding is deleted. Never held back on
     * a stale link - it only deletes (like turning the wake word OFF). If
     * the PC cannot be reached, it deletes what it holds after 15 minutes
     * anyway, and the line says so.
     */
    suspend fun cancelVoiceRounds(): String {
        if (!voice.strict.value.rounds) return VoiceRounds.cancelledLine(null)
        return when (val r = api.voiceEnroll(VoiceStrict.CANCEL_BODY)) {
            is ApiResult.Ok -> {
                voice.refreshStatus()
                VoiceRounds.cancelledLine(r.value)
            }
            is ApiResult.Failed ->
                "Cancelled on this phone. Your PC could not be reached; it deletes the rounds it " +
                    "holds by itself after 15 minutes."
        }
    }

    /**
     * Very strict / balanced, and private answers. LOOSENING raises one
     * approval card on the PC and changes nothing until it is approved, so
     * it is held on a stale link; TIGHTENING applies at once and always goes
     * ([StrictVoice.blocker]). The PC's answer is shown as it is, and the
     * status read again so the screen shows what is TRUE, not what was asked.
     */
    suspend fun setVoiceSetting(setting: String, value: String): String {
        StrictVoice.blocker(setting, value, voice.strict.value, actionBlocker())?.let { return it }
        return when (val r = api.voiceEnroll(VoiceStrict.settingBody(setting, value))) {
            is ApiResult.Ok -> {
                if (r.value.pending) refreshPending()
                voice.refreshStatus()
                StrictVoice.answerLine(r.value)
            }
            is ApiResult.Failed -> describe(r.error)
        }
    }

    /**
     * The guided repeat test: the owner's own sentences, judged on the PC at
     * both settings, then thrown away there. No card and nothing changed, so
     * - like the "someone else" check - it is not held on a stale link. Sent
     * in parts the PC will take (80 seconds each), and the counts added up.
     */
    suspend fun measureVoice(clips: List<ByteArray>, seconds: List<Float>): StrictVoice.Tested {
        val strict = voice.strict.value
        if (!strict.measure) return StrictVoice.Tested(false, listOf(StrictVoice.NO_TEST_ON_THIS_PC))
        val parts = mutableListOf<com.jarvis.client.net.VoiceStrict.Measured?>()
        for (range in StrictVoice.batches(seconds, strict.limits.measureMaxClips, strict.limits.maxTotalSeconds)) {
            val body = com.jarvis.client.net.enrollRequestBody(
                clips.slice(range), mic = VoiceTraining.MIC, mode = "measure",
            )
            when (val r = api.voiceEnroll(body)) {
                is ApiResult.Ok -> {
                    val a = r.value
                    if (a.error.isNotBlank() || a.measured == null) {
                        return StrictVoice.Tested(false, listOf(VoiceRounds.sentence(a.error.ifBlank { "Your PC could not check them." })))
                    }
                    parts += a.measured
                }
                is ApiResult.Failed -> return StrictVoice.Tested(false, listOf(describe(r.error)))
            }
        }
        voice.refreshStatus()
        val all = StrictVoice.combine(parts) ?: return StrictVoice.Tested(false, listOf("Your PC could not check them."))
        return StrictVoice.Tested(true, StrictVoice.measureLines(all))
    }

    // --------------------------------------------------- custom voices ----

    private val _customVoices = MutableStateFlow<CustomVoices.Read>(CustomVoices.Read.Loading)

    /** `GET /api/voice/voices`, read when the Voices screen opens and on the `voices` event. */
    val customVoices: StateFlow<CustomVoices.Read> = _customVoices.asStateFlow()

    /** Set once the Voices screen has asked; the `voices` event only re-reads after that. */
    @Volatile private var customVoicesAsked = false

    suspend fun refreshCustomVoices() {
        customVoicesAsked = true
        _customVoices.value = CustomVoices.read(api.customVoices())
    }

    private fun customVoiceStatus(): CustomVoices.Status? =
        (_customVoices.value as? CustomVoices.Read.Loaded)?.status

    /**
     * Adds a voice: a recording and exactly what is said in it - the
     * sentence the phone showed, or the words the owner typed for a picked
     * file. The phone never turns the recording into words. ONE card on the
     * PC; nothing is kept until it is approved. Held on a stale link.
     */
    suspend fun addCustomVoice(name: String, clip: ByteArray, transcript: String): CustomVoices.Answer? {
        CustomVoices.blocker(raisesCard = true, linkBlocker = actionBlocker(), status = customVoiceStatus())
            ?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.CREATE_PATH, CustomVoices.createBody(name, clip, transcript))
    }

    /** Switches to a custom voice (a card; held on a stale link) or back to the built-in one (at once, always). */
    suspend fun switchCustomVoice(id: String): CustomVoices.Answer? {
        val card = id != CustomVoices.BUILTIN
        CustomVoices.blocker(raisesCard = card, linkBlocker = actionBlocker(), status = customVoiceStatus())
            ?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.ACTIVE_PATH, CustomVoices.activeBody(id))
    }

    /** Deletes a voice. At once, never held: it only takes something away. The screen asks first. */
    suspend fun deleteCustomVoice(id: String): CustomVoices.Answer? =
        postCustomVoice(CustomVoices.DELETE_PATH, CustomVoices.deleteBody(id))

    /** The better voice: ON is a card (held on a stale link), OFF is at once (never held). */
    suspend fun setBetterVoice(on: Boolean): CustomVoices.Answer? {
        CustomVoices.blocker(raisesCard = on, linkBlocker = actionBlocker(), status = null)
            ?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.BETTER_PATH, CustomVoices.betterBody(on))
    }

    /**
     * How fast every voice on the PC speaks - one of the ids the PC offered.
     * No card either way (it trusts nothing more), but held on a stale link
     * like every change sent to the PC (rule 4).
     */
    suspend fun setVoiceSpeed(id: String): CustomVoices.Answer? {
        actionBlocker()?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.SPEED_PATH, CustomVoices.speedBody(id))
    }

    /**
     * Which of Kokoro's own voices the built-in voice uses - one of the ids
     * the PC offered. Same shape as [setVoiceSpeed]: no card either way, but
     * held on a stale link like every change sent to the PC (rule 4).
     */
    suspend fun setVoiceSpeaker(id: String): CustomVoices.Answer? {
        actionBlocker()?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.SPEAKER_PATH, CustomVoices.speakerBody(id))
    }

    /**
     * "Hear it" for one built-in voice (2026-09-29): the PC says one fixed
     * line in the voice named [id] and it plays here ([VoiceSession.hearVoiceSample]).
     * It changes nothing - the voice Jarvis uses stays as it is - so it is not
     * held on a stale link ("Try it"'s rule). Refused while App lock would ask
     * again, and (in [VoiceSession]) while a question, an answer or Jarvis
     * Live has the microphone or the speaker. Returns the words to show.
     */
    suspend fun hearVoice(id: String, label: String, playing: (String) -> Unit): String {
        if (appLockWouldLock(SystemClock.elapsedRealtime(), settings.security.value)) {
            return CustomVoices.HEAR_LOCKED
        }
        return voice.hearVoiceSample(id, label, playing)
    }

    /**
     * "Voice follows the face": with an animal face showing, the built-in
     * voice becomes that animal's. Same shape as [setVoiceSpeaker]: no card
     * either way, but held on a stale link like every change sent to the PC
     * (rule 4), whichever way it is switched.
     */
    suspend fun setVoiceFace(on: Boolean): CustomVoices.Answer? {
        actionBlocker()?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.FACE_PATH, CustomVoices.faceBody(on))
    }

    /**
     * The one-time "The panda has its own voice. Use it?" (owner,
     * 2026-09-28): [use] true is "Use it", false "Keep my voice"; the PC
     * remembers the answer per face. Same shape as [setVoiceFace]: no card,
     * held on a stale link (rule 4). Re-reads the voices afterwards, so the
     * question goes away and the switch shows its new state.
     */
    suspend fun answerFaceVoiceOffer(face: String, use: Boolean): CustomVoices.Answer? {
        actionBlocker()?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.FACE_OFFER_PATH, CustomVoices.faceOfferBody(face, use))
    }

    /**
     * One animal's own voice, pitch and pace, or "Reset to its own voice" -
     * [json] is [CustomVoices.animalBody] or [CustomVoices.animalResetBody].
     * Same shape as [setVoiceFace]: no card either way, held on a stale link
     * (rule 4). ("Try it" changes nothing: VoiceSession.tryAnimalVoice.)
     */
    suspend fun setVoiceAnimal(json: String): CustomVoices.Answer? {
        actionBlocker()?.let { _customVoiceNote.value = it; return null }
        return postCustomVoice(CustomVoices.ANIMAL_PATH, json)
    }

    private val _customVoiceNote = MutableStateFlow<String?>(null)

    /** The last thing a Voices request came to, in words, for the screen to show. */
    val customVoiceNote: StateFlow<String?> = _customVoiceNote.asStateFlow()

    fun clearCustomVoiceNote() { _customVoiceNote.value = null }

    private suspend fun postCustomVoice(path: String, json: String): CustomVoices.Answer? =
        when (val r = api.customVoicePost(path, json)) {
            is ApiResult.Ok -> {
                val a = r.value
                _customVoiceNote.value = CustomVoices.answerLine(a)
                if (a.pending) refreshPending()
                refreshCustomVoices()
                a
            }
            is ApiResult.Failed -> {
                _customVoiceNote.value = when (r.error) {
                    ApiError.NotFound -> "Your PC does not have custom voices yet. Run the patch script on the PC first."
                    else -> describe(r.error)
                }
                null
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
            // The shared animal switches ride along (animal.patch): an old
            // Still of this phone's moves to the PC once they are known.
            appearance.animal.value?.let { moveOldStill(it) }
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
                // A "Forget a time frame" card of this phone's may have been
                // decided (here, or on the PC): the PC's own status says how,
                // and Home leaves a chat that went (the chat audit, 2026-09-28).
                if (forgetRangeChats.isNotEmpty()) {
                    scope.launch { forgetRangeRead(com.jarvis.client.net.ForgetRange.PATH) }
                }
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
            // "Activity" (past approvals): read alongside the other three,
            // never merged with them and never with `pending` - it has its
            // own key on every side of this call.
            val activity = note("activity", api.gateHistoryRead()) { _pastApprovals.value = it.items }
            // Only this function's own keys. It used to assign the whole set,
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
                    activity = activity,
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
                val hardwareRead = async { refreshHardware() }
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
                hardwareRead.await()
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
            // The plain words both apps use for a link that is catching up
            // (PlainErrors "link_stale"): what is happening, then what to do.
            com.jarvis.client.net.PlainErrors.shown("link_stale").text
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
        // Two states, two sentences (LinkWords): "not connected" only when
        // the PC really is out of reach, "catching up" when the link is up
        // but not trusted yet. Both still refuse - rule 4.
        LinkWords.decisionBlocked(_link.value, _stale.value)?.let { return it }
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
    fun decideDetached(
        item: PendingItem,
        approve: Boolean,
        signature: SignedApproval.Signature? = null,
    ) {
        scope.launch { decide(item, approve, signature) }
    }

    /**
     * [signature]: a risky approval from a phone with signed approvals on
     * carries the fingerprint-made signature (docs/PAIRING-DESIGN.md §11).
     */
    suspend fun decide(
        item: PendingItem,
        approve: Boolean,
        signature: SignedApproval.Signature? = null,
    ): ApiResult<Unit> {
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
        if (approve && item.pcOnly) {
            // Loosening "What asks first" (the owner's decision of 2026-09-26):
            // approved on the PC only, with Windows Hello. The PC refuses it
            // from here too; this says so before anything is sent.
            val msg = com.jarvis.client.net.AsksFirst.APPROVE_ON_PC
            _notice.value = msg
            return ApiResult.Failed(ApiError.Unreachable(msg))
        }
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
            val result = if (approve) api.approve(item.id, signature) else api.deny(item.id)
            when (result) {
                is ApiResult.Ok -> {
                    refreshPending()
                    // An inbox tidy approved here: its Undo strip shows at once.
                    if (approve && item.action == "tidy_inbox") watchInboxTidyQuickly()
                }
                is ApiResult.Failed -> {
                    if (result.error == ApiError.AlreadyHandled) {
                        // Routine when the desktop and the phone are both open.
                        _notice.value = "Already handled on the desktop."
                        refreshPending()
                    } else {
                        // A signature refusal the PC explained is its own
                        // sentence - never "your key was refused", which
                        // would send the owner to the pairing screen.
                        val signedWords = if (approve) {
                            SignedApproval.refusalWords(com.jarvis.client.net.ApprovalRefusal.take())
                        } else {
                            null
                        }
                        _notice.value = signedWords ?: describe(result.error)
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

    /**
     * "Stop everything" (the owner's decision of 2026-09-25; the desktop's
     * Alt+Shift+X calls the same route). The phone's own speech stops first,
     * before the PC is asked, so a dead link never keeps Jarvis talking; then
     * `POST /api/stop_all`, and the notice says what the PC stopped, in its
     * own words - see [com.jarvis.client.net.StopEverything].
     *
     * **Never gated on [decisionBlocker] or a stale link**, like Stop and
     * Pause: stopping only ever makes Jarvis do less. It approves nothing and
     * starts nothing, and neither does the route.
     */
    suspend fun stopEverything(): ApiResult<JsonObject> {
        if (::voice.isInitialized) voice.stopSpeaking()
        // A held look at this phone's screen goes too, before the PC is asked
        // (the owner's decision of 2026-09-28: nothing saved, and Stop means stop).
        com.jarvis.client.net.ScreenLook.drop()
        // ...and this phone's own Watch with me, if it is running.
        com.jarvis.client.net.ScreenWatch.requestStop()
        val result = api.stopEverything()
        // A PC that could not be reached: the plain words and their button
        // (Try again, or Check the connection settings), like every failure.
        val problem = (result as? ApiResult.Failed)?.let {
            com.jarvis.client.net.StopEverything.problem(it.error)
        }
        if (problem != null) _problem.value = problem
        _notice.value = when (result) {
            is ApiResult.Ok -> com.jarvis.client.net.StopEverything.describe(result.value, null)
            is ApiResult.Failed -> com.jarvis.client.net.StopEverything.describe(null, result.error)
        }
        return result
    }

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

    /**
     * Read by every notification builder ([com.jarvis.client.service]) to
     * decide `.setLocalOnly(...)` - the cached last-known answer from the
     * PC ([ClientSettings.watchNotifications]), or false (stay on the phone
     * - the safe direction) if [settings] has not been set up yet, which a
     * notification built before [initialize] ever ran should not crash
     * over.
     */
    fun watchNotificationsAllowed(): Boolean =
        if (::settings.isInitialized) settings.watchNotifications.value else false

    // -------------------------------------------- smartwatch notifications ----
    // docs/JARVIS-API.md; see [com.jarvis.client.net.WatchNotify] and
    // ui/screens/WatchNotifyPlate.kt. OFF by default, ON is one approval
    // card. Every successful read or write updates [ClientSettings]'s cache,
    // which the notification builders read - the only reason this route is
    // read at all off the settings screen.

    /**
     * `GET /api/notifications/watch`. Updates the cache on success; leaves
     * it alone on failure (a stale cache is never worse than no cache, and
     * an app briefly offline should not flip every notification local
     * again).
     */
    suspend fun watchNotifySettings(): ApiResult<JsonObject> {
        val r = api.watchNotifySettings()
        if (r is ApiResult.Ok) {
            com.jarvis.client.net.WatchNotify.enabled(r.value)?.let { settings.setWatchNotifications(it) }
        }
        return r
    }

    /**
     * The switch. ON is held on a stale link (rule 4) and raises an
     * approval card on the PC; OFF is never held. @return the sentence to
     * show under the switch.
     */
    suspend fun setWatchNotify(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setWatchNotify(on) }) {
            is ApiResult.Ok -> {
                // Only a real Done (not Waiting) means the PC actually
                // changed it - an ON that is still waiting for its card
                // must not flip the cache early.
                if (r.value is com.jarvis.client.net.DesktopWrite.Outcome.Done) {
                    settings.setWatchNotifications(on)
                }
                com.jarvis.client.net.WatchNotify.said(on, r.value)
            }
            is ApiResult.Failed -> "Not changed. " + describe(r.error)
        }
    }

    // ----------------------------------- picture mode for the screen ----
    // docs/JARVIS-API.md section 96.1; see [com.jarvis.client.net.ScreenPicture]
    // and ui/screens/ScreenPicturePlate.kt. OFF by default, ON is one approval
    // card on the PC. Nothing is cached on this phone: the PC decides, and the
    // phone only shows what the PC says (never a guessed speed).

    /** `GET /api/screen/picture`. */
    suspend fun screenPictureSettings(): ApiResult<JsonObject> = api.screenPictureSettings()

    /**
     * The switch. ON is held on a stale link (rule 4) and raises an approval
     * card on the PC; OFF is never held. @return the sentence to show under
     * the switch.
     */
    suspend fun setScreenPicture(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setScreenPicture(on) }) {
            is ApiResult.Ok -> com.jarvis.client.net.ScreenPicture.said(on, r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.ScreenPicture.missing(r.error)) {
                    com.jarvis.client.net.ScreenPicture.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    // ----------------------------------- the headless browser (Obscura) ----
    // docs/JARVIS-API.md section 97; see [com.jarvis.client.net.BrowserEngine]
    // and ui/screens/BrowserEnginePlate.kt. OFF by default, ON is one approval
    // card on the PC. Nothing is cached on this phone: the PC decides, and the
    // phone only shows what the PC says. It never runs a browser.

    /** `GET /api/browser/engine`. */
    suspend fun browserEngineSettings(): ApiResult<JsonObject> = api.browserEngineSettings()

    /**
     * The switch. ON is held on a stale link (rule 4) and raises an approval
     * card on the PC; OFF is never held. @return the sentence to show under
     * the switch.
     */
    suspend fun setBrowserEngine(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setBrowserEngine(on) }) {
            is ApiResult.Ok -> com.jarvis.client.net.BrowserEngine.said(on, r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.BrowserEngine.missing(r.error)) {
                    com.jarvis.client.net.BrowserEngine.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /**
     * Which browser Jarvis uses by default: "auto", "visible" or "headless".
     * No approval card (both browsers still ask on every plan), but held on a
     * stale link like every change sent to the PC ([actionBlocker], rule 4).
     */
    suspend fun setBrowserEngineMode(mode: String): String {
        actionBlocker()?.let { return it }
        val body = com.jarvis.client.net.BrowserEngine.modeBody(mode)
            ?: return "That is not one of the three choices."
        return when (val r = writeNoticingCards { api.setBrowserEngineMode(body) }) {
            is ApiResult.Ok -> com.jarvis.client.net.BrowserEngine.saidMode(r.value)
            is ApiResult.Failed ->
                if (com.jarvis.client.net.BrowserEngine.missing(r.error)) {
                    com.jarvis.client.net.BrowserEngine.MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /**
     * Read by [com.jarvis.client.service.PhoneNotificationListenerService]
     * to decide whether to store anything at all - the cached last-known
     * answer from the PC ([ClientSettings.phoneNotifications]), or false
     * (read nothing - the safe direction) if [settings] has not been set
     * up yet.
     */
    fun phoneNotificationsAllowed(): Boolean =
        if (::settings.isInitialized) settings.phoneNotifications.value else false

    @Volatile private var phoneNotificationsCheckedAt = 0L

    /**
     * Called by the listener for a notification that passed every gate:
     * asks the PC for the switch again first (at most once every
     * [PHONE_NOTIFICATIONS_RECHECK_MS]), then runs [store] only if it is
     * still on. So turning it off on the PC stops capture at the next
     * notification, not only once this phone's settings page is opened
     * (audit 06-decisions V3). With no link the last answer stands, as
     * [phoneNotificationsSettings] already says.
     */
    fun storeIfPhoneNotificationsStillOn(store: () -> Unit) {
        if (!started) return
        scope.launch {
            val now = System.currentTimeMillis()
            if (isPaired() && now - phoneNotificationsCheckedAt >= PHONE_NOTIFICATIONS_RECHECK_MS) {
                phoneNotificationsCheckedAt = now
                runCatching { phoneNotificationsSettings() }
            }
            if (phoneNotificationsAllowed()) kotlinx.coroutines.withContext(Dispatchers.IO) {
                store()
                // The switch can go off between the check above and the write
                // landing: the switch-off clear may already have run, and this
                // row would then stay behind. Look again after writing, and
                // clear if it is off now (bug audit 2026-09-29).
                if (!phoneNotificationsAllowed()) {
                    appContext?.let { ctx ->
                        runCatching { com.jarvis.client.data.CapturedNotifications(ctx).clear() }
                    }
                }
            }
        }
    }

    // -------------------------------------------- reading phone notifications ----
    // docs/JARVIS-API.md §61; see [com.jarvis.client.net.PhoneNotifications]
    // and ui/screens/PhoneNotificationsPlate.kt. OFF by default, ON is one
    // approval card. Every successful read or write updates
    // [ClientSettings]'s cache, which the listener service reads - the only
    // reason this route is read at all off the settings screen.

    // -------------------------------------------------- pairing and devices ----
    // docs/PAIRING-DESIGN.md: QR-code pairing (net/Pairing.kt,
    // net/PairingFlow.kt) and Settings -> Devices (net/Devices.kt,
    // ui/screens/DevicesPlate.kt).

    /**
     * The one pairing attempt, for the whole process - so turning the phone
     * does not drop it. Its secrets live in memory only (never saved state).
     */
    val pairing: com.jarvis.client.net.PairingFlow by lazy {
        com.jarvis.client.net.PairingFlow(
            scope = scope,
            transport = object : com.jarvis.client.net.PairTransport {
                override suspend fun post(base: String, path: String, json: String) = api.pairPost(base, path, json)
            },
            wordList = { appContext?.let { com.jarvis.client.data.PairWords.load(it) } },
        )
    }

    /** `GET /api/devices`. A read: not held on a stale link. */
    suspend fun devices(): ApiResult<JsonObject> = api.devices()

    /**
     * Remove ONE device (design §6.4). Immediate and never held on a stale
     * link: it only takes access away, like Forget. @return the sentence to
     * show, and whether the device removed was this phone itself.
     */
    suspend fun removeDevice(device: com.jarvis.client.net.Devices.Device): Pair<String, Boolean> =
        when (val r = api.devicesPost(com.jarvis.client.net.Devices.REMOVE_PATH, com.jarvis.client.net.Devices.removeBody(device.id))) {
            is ApiResult.Ok -> {
                val (code, body) = r.value
                val self = code == 200 && (com.jarvis.client.net.Devices.removedThisPhone(body) || device.thisDevice)
                com.jarvis.client.net.Devices.removeSaid(code, body, device.name) to self
            }
            is ApiResult.Failed -> ("Not removed. " + describe(r.error)) to false
        }

    /** "Retire for other devices" - stricter, so immediate (design §6.4). @return the sentence to show. */
    suspend fun retireSharedKey(): String =
        when (val r = api.devicesPost(com.jarvis.client.net.Devices.SHARED_PATH, com.jarvis.client.net.Devices.RETIRE_BODY)) {
            is ApiResult.Ok -> com.jarvis.client.net.Devices.retireSaid(r.value.first, r.value.second)
            is ApiResult.Failed -> "Not changed. " + describe(r.error)
        }

    // ------------------------------------------------ signed approvals ----
    // docs/PAIRING-DESIGN.md §11; the words and rules are in [SignedApproval].

    /** What this phone knows about its signed approvals. [device] is this phone's id on the PC. */
    data class SignedApprovalRead(val state: SignedApproval.State, val device: String?)

    /**
     * Reads `GET /api/devices` and this phone's Keystore, fresh, or null
     * when the PC could not be read (then an approval takes today's way and
     * the PC says `no_approval_key` if it needed one). A read: not held on a
     * stale link.
     */
    suspend fun signedApprovalRead(): SignedApprovalRead? {
        val r = api.devices()
        if (r !is ApiResult.Ok) return null
        val view = com.jarvis.client.net.Devices.parse(r.value)
        val mine = view.devices.firstOrNull { it.thisDevice }
        return SignedApprovalRead(
            state = SignedApproval.stateOf(view.usesOwnKey, mine?.approvalKey, approvalKeyLocal()),
            device = view.you?.takeIf { view.usesOwnKey },
        )
    }

    /** What the Keystore holds, read off the main thread. */
    suspend fun approvalKeyLocal(): SignedApproval.Local =
        kotlinx.coroutines.withContext(Dispatchers.IO) { com.jarvis.client.platform.ApprovalKey.state() }

    /**
     * Step one of a signed approval: asks the PC for a nonce and checks that the
     * card it means is the card this phone showed. Null after putting the reason
     * in the notice.
     */
    suspend fun beginSignedApproval(item: PendingItem): SignedApproval.ChallengeAnswer.Got? {
        decisionBlocker(item)?.let {
            _notice.value = it
            return null
        }
        val post = api.approvalPost(SignedApproval.CHALLENGE_PATH, SignedApproval.challengeBody(item.id))
        if (post !is ApiResult.Ok) {
            _notice.value = describe((post as ApiResult.Failed).error)
            return null
        }
        val (code, body) = post.value
        when (val answer = SignedApproval.challengeAnswer(code, body)) {
            is SignedApproval.ChallengeAnswer.Got -> {
                if (SignedApproval.wordsMatch(item, answer.wordsSha256)) return answer
                _notice.value = SignedApproval.CARD_CHANGED
                refreshPending()
            }
            SignedApproval.ChallengeAnswer.NoApprovalKey -> _notice.value = SignedApproval.OFFER_WORDS
            SignedApproval.ChallengeAnswer.CardGone -> {
                _notice.value = "That request is no longer pending."
                refreshPending()
            }
            is SignedApproval.ChallengeAnswer.Refused -> _notice.value = answer.words
        }
        return null
    }

    /**
     * "Turn on signed approvals": makes the key on this phone and sends its
     * public half; the PC then raises ONE card (Windows Hello). Held on a
     * stale link, like every loosening. @return the sentence to show.
     */
    suspend fun turnOnSignedApprovals(): String {
        actionBlocker()?.let { return it }
        val context = appContext ?: return SignedApproval.KEY_NOT_MADE
        val der = try {
            kotlinx.coroutines.withContext(Dispatchers.IO) { com.jarvis.client.platform.ApprovalKey.create(context) }
        } catch (e: Exception) {
            return SignedApproval.KEY_NOT_MADE
        }
        return when (val r = api.approvalPost(SignedApproval.KEY_PATH, SignedApproval.registerBody(der))) {
            is ApiResult.Ok -> {
                val (ok, words) = SignedApproval.registerAnswer(r.value.first, r.value.second)
                if (!ok) com.jarvis.client.platform.ApprovalKey.delete()
                words
            }
            is ApiResult.Failed -> {
                com.jarvis.client.platform.ApprovalKey.delete()
                "Not turned on. " + describe(r.error)
            }
        }
    }

    /**
     * "Turn off": deletes this phone's key, so risky approvals from this
     * phone are held until it is turned on again. The PC still lists the
     * phone until it is removed there, and the sentence says so.
     */
    suspend fun turnOffSignedApprovals(): String {
        kotlinx.coroutines.withContext(Dispatchers.IO) { com.jarvis.client.platform.ApprovalKey.delete() }
        return SignedApproval.TURNED_OFF
    }

    /**
     * `GET /api/notifications/phone`. Updates the cache on success; leaves
     * it alone on failure (a stale cache is never worse than no cache, and
     * an app briefly offline should not stop reading notifications it was
     * already allowed to read).
     */
    suspend fun phoneNotificationsSettings(): ApiResult<JsonObject> {
        val r = api.phoneNotificationsSettings()
        if (r is ApiResult.Ok) {
            com.jarvis.client.net.PhoneNotifications.enabled(r.value)?.let { settings.setPhoneNotifications(it) }
        }
        return r
    }

    /**
     * The switch. ON is held on a stale link (rule 4) and raises an
     * approval card on the PC; OFF is never held. @return the sentence to
     * show under the switch.
     */
    suspend fun setPhoneNotifications(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setPhoneNotifications(on) }) {
            is ApiResult.Ok -> {
                // Only a real Done (not Waiting) means the PC actually
                // changed it - an ON that is still waiting for its card
                // must not flip the cache early.
                if (r.value is com.jarvis.client.net.DesktopWrite.Outcome.Done) {
                    settings.setPhoneNotifications(on)
                }
                com.jarvis.client.net.PhoneNotifications.said(on, r.value)
            }
            is ApiResult.Failed -> "Not changed. " + describe(r.error)
        }
    }

    // ----------------------------------------------- automatic learning ----
    // docs/JARVIS-API.md section 19 (2026-09-24) - see
    // [com.jarvis.client.net.AutoLearn] and ui/screens/AutoLearnPlate.kt.
    // The phone reads the list from the PC and keeps none of it.

    private val _autoTick = MutableStateFlow(0)

    /**
     * Goes up by one on every `memory_saved` event, so Mind's "Saved
     * automatically" list reads itself again - the event carries ids only.
     */
    val autoTick: StateFlow<Int> = _autoTick.asStateFlow()

    private val _autoRemembered = MutableStateFlow(0)

    /**
     * How many facts the PC has saved automatically since the owner last
     * looked, for Mind's quiet "Jarvis remembered N things" line. A count,
     * never the words: no fact's text reaches a notification or this line.
     */
    val autoRemembered: StateFlow<Int> = _autoRemembered.asStateFlow()

    /** The ids already counted, so an event heard twice is not counted twice. */
    private var autoSeenIds: List<Long> = emptyList()

    private val _autoRememberedIds = MutableStateFlow<List<Long>>(emptyList())

    /**
     * Which facts [autoRemembered] counts, by id - what the line opens
     * (the owner's decision, 2026-09-25): their words are read from the PC
     * only then ([memoryUsed]). Ids only, never the words.
     */
    val autoRememberedIds: StateFlow<List<Long>> = _autoRememberedIds.asStateFlow()

    /** The owner opened the list: the line has said its piece. */
    fun clearAutoRemembered() {
        _autoRemembered.value = 0
        _autoRememberedIds.value = emptyList()
    }

    private fun onMemorySaved(data: kotlinx.serialization.json.JsonElement?, replayed: Boolean = false) {
        val ids = com.jarvis.client.net.AutoLearn.savedIds(data)
        val fresh = synchronized(this) {
            val (added, seen) = com.jarvis.client.net.AutoLearn.fresh(autoSeenIds, ids)
            autoSeenIds = seen
            added
        }
        if (fresh.isNotEmpty()) {
            _autoRemembered.update { it + fresh.size }
            _autoRememberedIds.update { (it + fresh).takeLast(com.jarvis.client.net.MemoryUsed.MAX) }
            // The animal's small nod - never while App lock or "Hide memory
            // lists and chat history" is on (the owner's rule, 2026-09-28),
            // and never for a replayed event.
            val security = settings.security.value
            com.jarvis.client.face.AnimalNow.factSavedIf(security.appLock, security.privateLists, replayed)
        }
        _autoTick.update { it + 1 }
    }

    // --------------------------------- "Used in this answer" (2026-09-25) ----
    // See [com.jarvis.client.net.MemoryUsed]: the words of the few facts an
    // answer used, or that were just saved, read by id when the owner opens
    // the line. Forget beside each is [forgetAutoFact] - one fact, asked
    // first, held on a stale link.

    /** `GET /api/memory/used?ids=` - a read: never held. */
    suspend fun memoryUsed(ids: List<Long>): com.jarvis.client.net.MemoryUsed.Read =
        when (val r = api.memoryUsed(ids)) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryUsed.parse(r.value)
                ?.let { com.jarvis.client.net.MemoryUsed.Read.Shown(it) }
                ?: com.jarvis.client.net.MemoryUsed.Read.Failed(
                    "The desktop sent something this app could not read.",
                )
            is ApiResult.Failed -> if (com.jarvis.client.net.MemoryUsed.missing(r.error)) {
                com.jarvis.client.net.MemoryUsed.Read.Missing
            } else {
                com.jarvis.client.net.MemoryUsed.Read.Failed(describe(r.error))
            }
        }

    // ----------------------------- "Where this came from" (I42/I132, 2026-09-27) ----
    // See [com.jarvis.client.net.ChatSources]: this answer's own reading-tool
    // receipts and its quote check, read by turn_id when the owner opens the
    // line. Fetched once, quietly, as soon as the answer finishes - there is
    // no cheap count to gate it on first (see that object's own docstring).

    /** `GET /api/chat/sources?turn_id=` - a read: never held. */
    suspend fun chatSources(turnId: String?): com.jarvis.client.net.ChatSources.Read =
        when (val r = api.chatSources(turnId)) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatSources.parse(r.value)
                ?.let { com.jarvis.client.net.ChatSources.Read.Shown(it) }
                ?: com.jarvis.client.net.ChatSources.Read.Failed(
                    "The desktop sent something this app could not read.",
                )
            is ApiResult.Failed -> if (com.jarvis.client.net.ChatSources.missing(r.error)) {
                com.jarvis.client.net.ChatSources.Read.Missing
            } else {
                com.jarvis.client.net.ChatSources.Read.Failed(describe(r.error))
            }
        }

    /**
     * `GET /api/chat/table?id=` - the spending table under an answer
     * ([com.jarvis.client.net.Spending]). A read: never held. The result is
     * handed to the screen that draws it and kept nowhere else.
     */
    suspend fun spendingTable(id: String?): com.jarvis.client.net.Spending.Read =
        when (val r = api.chatTable(id)) {
            is ApiResult.Ok -> com.jarvis.client.net.Spending.parseTable(r.value)
                ?.let { com.jarvis.client.net.Spending.Read.Shown(it) }
                ?: com.jarvis.client.net.Spending.Read.Failed(com.jarvis.client.net.Spending.UNREADABLE)
            is ApiResult.Failed -> if (com.jarvis.client.net.Spending.gone(r.error)) {
                com.jarvis.client.net.Spending.Read.Gone(com.jarvis.client.net.Spending.TABLE_GONE)
            } else {
                com.jarvis.client.net.Spending.Read.Failed(describe(r.error))
            }
        }

    /** `GET /api/spending` - the Brain plate's read-only view. A read: never held. */
    suspend fun spendingView(): ApiResult<JsonObject> = api.spending()

    /** `GET /api/retirement/defaults` - the what-if form. A read: never held. */
    suspend fun retirementDefaults(): ApiResult<JsonObject> = api.retirementDefaults()

    /**
     * `POST /api/retirement/run` - works the what-if out on the PC from the
     * typed boxes ([com.jarvis.client.net.Retirement.requestBody]). No card:
     * a calculation on numbers the owner typed. Held on a stale link
     * ([actionBlocker], rule 4) and refused while "Hide memory lists and chat
     * history" is on ([listsHidden]). A busy PC is asked once more after a
     * second. The numbers and the answer are never logged or kept here: the
     * result goes back to the screen and nowhere else.
     */
    suspend fun retirementRun(
        values: Map<String, String>,
        listsHidden: Boolean,
        words: com.jarvis.client.net.Retirement.Words = com.jarvis.client.net.Retirement.Words(),
    ): com.jarvis.client.net.Retirement.Outcome {
        if (com.jarvis.client.net.Retirement.hiddenNow(listsHidden, false)) {
            return com.jarvis.client.net.Retirement.Outcome.Problem(words.hidden)
        }
        actionBlocker()?.let { return com.jarvis.client.net.Retirement.Outcome.Problem(it) }
        val body = com.jarvis.client.net.Retirement.requestBody(values)
        suspend fun once(): com.jarvis.client.net.Retirement.Outcome = when (val r = api.retirementRun(body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Retirement.classify(r.value, words)
            is ApiResult.Failed -> com.jarvis.client.net.Retirement.Outcome.Problem(noticeFor(r.error))
        }
        val first = once()
        if (first is com.jarvis.client.net.Retirement.Outcome.Problem && first.busy) {
            delay(1_000)
            return once()
        }
        return first
    }

    /**
     * Turns a temporary chat on or off on the chat both Home and the voice
     * loop send through ([com.jarvis.client.net.ChatSession.setTemporary]).
     * No card and no hold: it only ever makes Jarvis stricter. ON only when
     * the PC says it has one. @return the sentence to show, or null.
     */
    fun setTemporaryChat(on: Boolean): String? = chat.setTemporary(on)

    /** `GET /api/memory/learning` - the two automatic-learning switches. A read: never held. */
    suspend fun autoLearnSettings(): ApiResult<JsonObject> = api.autoLearnSettings()

    /** `GET /api/memory/auto`, one page, newest first. A read: never held. */
    suspend fun autoFacts(
        before: Double? = null,
        limit: Int = com.jarvis.client.net.AutoLearn.PAGE,
    ): ApiResult<JsonObject> = api.autoFacts(before, limit)

    /**
     * "Learn automatically" or "Also remember sensitive topics
     * automatically" - the same shape as [setLearning]. ON is held on a
     * stale link (rule 4) and raises an approval card on the PC; OFF is never
     * held - it only narrows what Jarvis does. @return the sentence to show.
     */
    suspend fun setAutoLearn(which: com.jarvis.client.net.AutoLearn.Which, on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        // OFF withdraws an ON card still waiting (the PC's own rule): approving
        // it later changes nothing. The card stays in the queue until it is
        // answered, so the ones up now are noted, and no longer make the
        // switch read "waiting" ([autoWithdrawn]).
        val up: Set<String> = if (on) emptySet() else com.jarvis.client.net.AutoLearn.cardIds(
            _pending.value.map { it.id to it.action }, which,
        )
        return when (val r = writeNoticingCards { api.setAutoLearn(which, on) }) {
            is ApiResult.Ok -> {
                if (up.isNotEmpty() && r.value is com.jarvis.client.net.DesktopWrite.Outcome.Done) {
                    _autoWithdrawn.update { (it + up).toList().takeLast(50).toSet() }
                }
                com.jarvis.client.net.AutoLearn.said(which, on, r.value)
            }
            is ApiResult.Failed ->
                com.jarvis.client.net.AutoLearn.switchFailure(r.error) ?: ("Not changed. " + describe(r.error))
        }
    }

    private val _autoWithdrawn = MutableStateFlow<Set<String>>(emptySet())

    /**
     * The approval cards an automatic-learning switch's OFF withdrew while
     * they waited. Still in the queue (the PC cannot take a card back), but
     * approving one changes nothing, so the switch does not read "waiting"
     * for it. Ids only; kept for this run of the app.
     */
    val autoWithdrawn: StateFlow<Set<String>> = _autoWithdrawn.asStateFlow()

    /**
     * Forgets ONE automatically saved fact, after Mind's confirm - or, since
     * 2026-09-25, one fact shown under "Used in this answer" or "Jarvis
     * remembered N things" ([com.jarvis.client.net.MemoryUsed]), after the
     * same confirm. Held on a
     * stale link (rule 4), the same as the desktop's Forget
     * (`brain_memory_forget` requires a live link): it cannot be undone, and
     * it acts on a list read over a link that cannot be confirmed live. No
     * such fact (404) counts as gone. @return whether it is gone now, and the
     * sentence to show.
     */
    suspend fun forgetAutoFact(id: Long): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return when (val r = api.forgetFact(id)) {
            is ApiResult.Ok -> com.jarvis.client.net.AutoLearn.forgetSaid(r.value).also { (gone, _) ->
                // A forgotten fact leaves "Always keep in mind" too.
                if (gone) _profileTick.update { it + 1 }
            }
            is ApiResult.Failed -> if (r.error == ApiError.NotFound) {
                true to com.jarvis.client.net.AutoLearn.ALREADY_GONE
            } else {
                false to (com.jarvis.client.net.AutoLearn.forgetFailure(r.error) ?: ("Not forgotten. " + describe(r.error)))
            }
        }
    }

    /**
     * "Erase the words" of ONE automatically saved fact, after Mind's
     * confirm (the owner's decision, 2026-09-24): its words wiped from the
     * PC for good, its dates kept. Held on a stale link (rule 4), exactly
     * like [forgetAutoFact] and the desktop's `brain_memory_erase`: there is
     * no undo at all, and the list it acts on was read over a link that
     * cannot be confirmed live.
     *
     * `alsoDeleteConversation` (2026-09-27): "Also delete the chat it came
     * from" - the confirm's own checkbox, off by default.
     *
     * @return whether the words are gone now (so the row leaves the list),
     * and the sentence to show.
     */
    suspend fun eraseAutoFact(
        id: Long,
        alsoDeleteConversation: Boolean = false,
        /** The chat named in the confirm (the chat audit, 2026-09-28): Home
         *  starts a new conversation if it was in that chat and it went. */
        chatId: String? = null,
        /** The PC said no chat is on record for this fact: said so after. */
        noChatOnRecord: Boolean = false,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return when (val r = api.eraseFact(id, alsoDeleteConversation)) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryErase
                .said(r.value, askedChat = alsoDeleteConversation || noChatOnRecord)
                .also { (gone, _) ->
                    // An erased fact leaves "Always keep in mind" too.
                    if (gone) _profileTick.update { it + 1 }
                    if (com.jarvis.client.net.MemoryErase.chatDeleted(r.value)) {
                        if (chatId != null) {
                            chatsGone(listOf(chatId))
                        } else {
                            // The phone did not know which chat the PC would delete
                            // (the lookup was slow or an older PC could not say): ask
                            // whether Home's own chat is still there (the second chat
                            // audit, phone B6).
                            homeChatGoneIfMissing()
                        }
                    }
                }
            is ApiResult.Failed -> false to ("Not erased. " + describe(r.error))
        }
    }

    // --------------------------------------------------------- Widgets ----
    // "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
    // version; docs/JARVIS-API.md section 86) - see
    // [com.jarvis.client.net.JarvisWidgets], ui/screens/WidgetsPlate.kt and
    // widget/JarvisBoardWidget.kt. The PC keeps the widgets; this phone keeps
    // only which one each home-screen slot shows.

    private val _widgetsTick = MutableStateFlow(0)

    /** Goes up when a widget is added or deleted here, so the list and the home screen redraw. */
    val widgetsTick: StateFlow<Int> = _widgetsTick.asStateFlow()

    /** `GET /api/widgets`. A read. */
    suspend fun widgets(): ApiResult<JsonObject> = api.widgets()

    /** `GET /api/widgets/show?id=`: one widget, filled in now. A read. */
    suspend fun widgetShow(id: String): ApiResult<JsonObject> = api.widgetShow(id)

    /**
     * A PREVIEW from the owner's typed words - the PC's model makes a small
     * checked description; nothing is added. Not held on a stale link (it
     * adds nothing), like "Photo to reminder". @return whether a preview was
     * made, and the sentence to show.
     */
    suspend fun widgetDraft(words: String): Pair<Boolean, String> {
        val body = com.jarvis.client.net.JarvisWidgets.draftBody(words)
            ?: return false to com.jarvis.client.net.JarvisWidgets.NO_WORDS
        return widgetPost(com.jarvis.client.net.JarvisWidgets.DRAFT_PATH, body, "Not made. ")
    }

    /** Keep ONE preview, exactly as shown. No card. Held on a stale link. */
    suspend fun widgetAdd(draft: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        if (!com.jarvis.client.net.JarvisWidgets.validDraft(draft)) return false to "That preview has expired."
        return widgetPost(
            com.jarvis.client.net.JarvisWidgets.ADD_PATH,
            com.jarvis.client.net.JarvisWidgets.idBody("draft", draft), "Not added. ",
        )
    }

    /** Drop ONE preview. Not held: it only drops. */
    suspend fun widgetDiscard(draft: String): Pair<Boolean, String> {
        if (!com.jarvis.client.net.JarvisWidgets.validDraft(draft)) return true to "Discarded."
        return widgetPost(
            com.jarvis.client.net.JarvisWidgets.DISCARD_PATH,
            com.jarvis.client.net.JarvisWidgets.idBody("draft", draft), "Not discarded. ",
        )
    }

    /** Delete ONE widget, at once. Held on a stale link, like Coming up's Delete. */
    suspend fun widgetDelete(id: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        if (!com.jarvis.client.net.JarvisWidgets.validId(id)) return false to "That widget is not there any more."
        return widgetPost(
            com.jarvis.client.net.JarvisWidgets.DELETE_PATH,
            com.jarvis.client.net.JarvisWidgets.idBody("id", id), "Not deleted. ",
        )
    }

    private suspend fun widgetPost(path: String, body: String, failed: String): Pair<Boolean, String> =
        when (val r = api.widgetPost(path, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.JarvisWidgets.said(r.value.first, r.value.second).also {
                _widgetsTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to (failed + describe(r.error))
        }

    // ------------------------------------------------------- Coming up ----
    // Timers, alarms, reminders and the to-do list (the owner's decisions of
    // 2026-09-25) - see [com.jarvis.client.net.Schedule] and
    // ui/screens/ComingUpPlate.kt. The PC is the clock: everything goes off
    // there, and this phone hears of it while it is connected.

    private val _scheduleTick = MutableStateFlow(0)

    /**
     * Goes up by one on every `schedule` event and after every change made
     * from this phone, so Mind's "Coming up" reads itself again.
     */
    val scheduleTick: StateFlow<Int> = _scheduleTick.asStateFlow()

    /** The jobs already shown as notifications, by id and when they went off. */
    private val scheduleShown = LinkedHashSet<String>()

    /** The "ring my phone" ids already rung here - a replayed event never rings twice. */
    private val ringsHeard = LinkedHashSet<String>()

    /**
     * "Ring my phone" (backend jarvis_find_phone.py, 2026-09-28): ring on the
     * alarm channel, even on silent, with Stop, for at most
     * [com.jarvis.client.net.FindPhone.MAX_SECONDS] - only for a fresh event
     * this phone has not rung for before ([com.jarvis.client.net.FindPhone]).
     * A stop from the PC takes that one ringing notification away. Nothing is
     * sent back: it only rings.
     */
    private fun onRingPhone(data: kotlinx.serialization.json.JsonElement?) {
        val ring = com.jarvis.client.net.FindPhone.parse(data as? JsonObject) ?: return
        val context = appContext ?: return
        val tag = com.jarvis.client.net.FindPhone.tag(ring.id)
        if (ring.stop) {
            runCatching { com.jarvis.client.service.ScheduleNotifier.stopRinging(context, tag) }
            return
        }
        // Written at once: a restart must not replay this event and ring again.
        flushResumePoint()
        val fresh = synchronized(ringsHeard) {
            if (ringsHeard.size > 100) ringsHeard.clear()
            ringsHeard.add(ring.id)
        }
        if (!fresh) return
        if (!com.jarvis.client.net.FindPhone.shouldRing(ring, System.currentTimeMillis() / 1000.0)) {
            Log.i(TAG, "a ring_phone event arrived late, so the phone did not ring")
            return
        }
        com.jarvis.client.service.ScheduleNotifier.post(
            context, ring.id, com.jarvis.client.net.FindPhone.EVENT,
            com.jarvis.client.net.FindPhone.TITLE, com.jarvis.client.net.FindPhone.TEXT,
            com.jarvis.client.net.FindPhone.LOCK_SCREEN,
            ring = true,
            key = tag,
            timeoutMs = com.jarvis.client.net.FindPhone.ringMillis(ring),
        )
    }

    /** `GET /api/schedule`. A read: never held. */
    suspend fun schedule(): ApiResult<JsonObject> = api.schedule()

    /**
     * ONE job: pause, resume, delete or done. No card - none of them can make
     * Jarvis do more - but held on a stale link (rule 4), like every change,
     * and the desktop's `brain_schedule_act`. @return whether it changed, and
     * the sentence to show.
     */
    suspend fun scheduleAct(id: String, action: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Schedule.actBody(id, action)
            ?: return false to "That is not something one job can do."
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ACT_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also { (changed, _) ->
                _scheduleTick.update { n -> n + 1 }
                // Snoozed, deleted or done here: its notification - ringing
                // or not - goes at once (bug audit 2026-09-26, #1). The PC's
                // `changed` event does the same, for a change made anywhere.
                if (changed && action in setOf("snooze", "delete", "done")) {
                    appContext?.let { ctx ->
                        runCatching { com.jarvis.client.service.ScheduleNotifier.cancel(ctx, id) }
                    }
                }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }
    }

    /**
     * One new to-do item, in the owner's words - on a named list when [list]
     * says one ("shopping"). Held on a stale link.
     */
    suspend fun addTodo(text: String, list: String? = null): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Schedule.todoBody(text, list)
            ?: return false to "Type what to add first (up to ${com.jarvis.client.net.Schedule.MAX_TEXT} characters)."
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also {
                _scheduleTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not added. " + describe(r.error))
        }
    }

    /**
     * Every item on ONE named list, after Coming up's "are you sure?" - the
     * desktop's `brain_schedule_clear_list`. [count] is how many items this
     * phone showed: the PC clears nothing when the list changed since. Never
     * the to-do list. Held on a stale link, like every change.
     */
    suspend fun clearList(name: String, count: Int): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Schedule.clearListBody(name, count)
            ?: return false to "That is not one of your lists."
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ACT_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also {
                _scheduleTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not cleared. " + describe(r.error))
        }
    }

    /**
     * The standby schedule: every day from [start] to [end] ("HH:MM"). The PC
     * sets it up at once, with no card (since 2026-09-26; the answer says the
     * next night) - the desktop's `brain_schedule_add_standby`. Held on a stale
     * link, like every change. @return whether the PC took it, and the
     * sentence to show.
     */
    /**
     * "Photo to reminder" (JARVIS-API.md section 83): the PC reads the dates
     * in one picture - already shrunk, in memory only - and PROPOSES a
     * reminder. Sets nothing up, so it is not held on a stale link. The
     * words that come back are outside text: shown, never sent on, never
     * saved by this app.
     */
    suspend fun scanPhotoForDate(dataUri: String): com.jarvis.client.net.PhotoReminder.Outcome {
        val body = com.jarvis.client.net.PhotoReminder.scanBody(dataUri)
            ?: return com.jarvis.client.net.PhotoReminder.Outcome.Failed(
                com.jarvis.client.net.PhotoReminder.NOT_A_PICTURE,
            )
        return when (val r = api.photoScan(body)) {
            is ApiResult.Ok -> com.jarvis.client.net.PhotoReminder.parse(r.value.first, r.value.second)
            is ApiResult.Failed -> com.jarvis.client.net.PhotoReminder.Outcome.Failed(describe(r.error))
        }
    }

    /**
     * The owner's tap on "Add a Jarvis reminder": ONE one-off reminder, no
     * card, the date and time read on the PC's clock. Held on a stale link.
     */
    suspend fun addPhotoReminder(what: String, date: String, time: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.PhotoReminder.reminderBody(what, date, time)
            ?: return false to (com.jarvis.client.net.PhotoReminder.problem(what, date, time) ?: "Not set up.")
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also {
                _scheduleTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not set up. " + describe(r.error))
        }
    }

    suspend fun addStandbySchedule(start: String, end: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Schedule.standbyBody(start, end)
            ?: return false to com.jarvis.client.net.Schedule.STANDBY_BAD_TIMES
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also {
                _scheduleTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not set up. " + describe(r.error))
        }
    }

    /**
     * ONE scheduler job by id - the same read a notification uses to get its
     * words ([com.jarvis.client.net.Schedule.parseOne]). Goals uses this to
     * re-check its own weekly check-in while its card might still be
     * waiting: Goals has no route of its own that hands that state out
     * again once the [acceptGoal] answer that first carried it is gone (see
     * [com.jarvis.client.net.Goals]'s own doc comment). A read: never held.
     */
    suspend fun scheduleJob(id: String): com.jarvis.client.net.Schedule.Job? {
        if (!com.jarvis.client.net.Schedule.validId(id)) return null
        return when (val r = api.scheduleJob(id)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.parseOne(r.value)
            is ApiResult.Failed -> null
        }
    }

    // -------------------------------------------------------------- Goals ----
    // "Goals: a plan the owner edits, one card per acting step" (the
    // owner's "build it now", 2026-09-27) - see [com.jarvis.client.net.Goals]
    // and ui/screens/GoalsPlate.kt.

    private val _goalsTick = MutableStateFlow(0)

    /**
     * Goes up by one after every change made from this phone, so Brain's
     * "Goals" reads itself again - the same shape as [sharedTick]: there is
     * no push event for a goal changing, so the other app's own edit shows
     * on the next read, Refresh.
     */
    val goalsTick: StateFlow<Int> = _goalsTick.asStateFlow()

    /** `GET /api/goals`. A read: never held. */
    suspend fun goals(): ApiResult<JsonObject> = api.goals()

    /**
     * A new draft, in the owner's own words - with their own plan once they
     * have typed one (or asked Jarvis to suggest one first, in ordinary
     * chat, and pasted it in). No card: a draft is content, not action,
     * exactly like an email draft. Held on a stale link (rule 4), like
     * every change. @return whether it was started, the new goal if so, and
     * the sentence to show.
     */
    suspend fun createGoal(
        text: String,
        plan: List<com.jarvis.client.net.Goals.Step>? = null,
    ): Triple<Boolean, com.jarvis.client.net.Goals.Goal?, String> {
        actionBlocker()?.let { return Triple(false, null, it) }
        val result = when (val r = api.goalsWrite(com.jarvis.client.net.Goals.PATH,
            com.jarvis.client.net.Goals.createBody(text, plan))) {
            is ApiResult.Ok -> com.jarvis.client.net.Goals.createdSaid(r.value)
            is ApiResult.Failed -> Triple(false, null, "Not started. " + describe(r.error))
        }
        if (result.first) _goalsTick.update { n -> n + 1 }
        return result
    }

    /**
     * Keeps the owner's edited plan (or the draft exactly as it stood) and
     * starts the weekly check-in - the PC's ONE approval card, the same
     * mechanism a repeating reminder already raises. Held on a stale link;
     * the freshly-raised card is read into [pending] at once, rather than
     * waiting for the next `pending` event, so the Approvals list shows it
     * without a delay. @return whether it was accepted, the accepted goal
     * with its check-in job if so, and the sentence to show.
     */
    suspend fun acceptGoal(
        id: String,
        plan: List<com.jarvis.client.net.Goals.Step>? = null,
    ): Triple<Boolean, com.jarvis.client.net.Goals.Accepted?, String> {
        actionBlocker()?.let { return Triple(false, null, it) }
        if (!com.jarvis.client.net.Goals.validId(id)) return Triple(false, null, "That is not one of your goals.")
        val result = when (val r = api.goalsWrite("/api/goals/$id/accept",
            com.jarvis.client.net.Goals.acceptBody(plan))) {
            is ApiResult.Ok -> com.jarvis.client.net.Goals.acceptedSaid(r.value)
            is ApiResult.Failed -> Triple(false, null, "Not accepted. " + describe(r.error))
        }
        if (result.first) {
            _goalsTick.update { n -> n + 1 }
            refreshPending()
        }
        return result
    }

    /**
     * Marks one step of an active goal done or not - no card, the same
     * shape as ticking off a to-do item. Sent by the step's [stepId] when
     * the PC gave it one, else by [index]. Held on a stale link. @return
     * whether it changed, the updated goal if so, and the sentence to show.
     */
    suspend fun setGoalStep(
        id: String,
        stepId: String,
        index: Int,
        done: Boolean,
    ): Triple<Boolean, com.jarvis.client.net.Goals.Goal?, String> {
        actionBlocker()?.let { return Triple(false, null, it) }
        if (!com.jarvis.client.net.Goals.validId(id)) return Triple(false, null, "That is not one of your goals.")
        val result = when (val r = api.goalsWrite("/api/goals/$id/step",
            com.jarvis.client.net.Goals.stepBody(stepId, index, done))) {
            is ApiResult.Ok -> com.jarvis.client.net.Goals.changedSaid(r.value, doneWord = if (done) "Done." else "Unticked.")
            is ApiResult.Failed -> Triple(false, null, "Not changed. " + describe(r.error))
        }
        if (result.first) _goalsTick.update { n -> n + 1 }
        return result
    }

    /**
     * Stops tracking a goal and deletes its check-in job. No card,
     * immediate - the same rule every "stop tracking this" control in this
     * project follows - and no confirm dialog: the backend's own design
     * requires stopping to be one tap. Held on a stale link, like every
     * change. @return whether it stopped, the stopped goal if so, and the
     * sentence to show.
     */
    suspend fun stopGoal(id: String): Triple<Boolean, com.jarvis.client.net.Goals.Goal?, String> {
        actionBlocker()?.let { return Triple(false, null, it) }
        if (!com.jarvis.client.net.Goals.validId(id)) return Triple(false, null, "That is not one of your goals.")
        val result = when (val r = api.goalsWrite("/api/goals/$id/stop",
            com.jarvis.client.net.Goals.STOP_BODY)) {
            is ApiResult.Ok -> com.jarvis.client.net.Goals.changedSaid(r.value, doneWord = "Stopped.")
            is ApiResult.Failed -> Triple(false, null, "Not changed. " + describe(r.error))
        }
        if (result.first) _goalsTick.update { n -> n + 1 }
        return result
    }

    // --------------------------------------------------------------- Quiz ----
    // "Quiz me on a text" (docs/STUDY-FROM-TEXT-DESIGN.md sections 3 and 11) -
    // see [com.jarvis.client.net.Quiz] and ui/screens/QuizPlate.kt. The open
    // quiz is held HERE, in memory only, so leaving Brain and coming back
    // does not orphan it on the PC. Nothing is written to disk: not the
    // pasted text (it is never kept at all), not the questions, not an
    // answer or a mark.

    private val _quiz = MutableStateFlow<com.jarvis.client.net.Quiz.Session?>(null)

    /** The quiz that is open on the PC, if this phone started one. Process memory only. */
    val quiz: StateFlow<com.jarvis.client.net.Quiz.Session?> = _quiz.asStateFlow()

    /** Drops the open quiz from this phone's memory (it is already gone on the PC, or being stopped). */
    fun forgetQuiz() {
        _quiz.value = null
    }

    private val _spanishSupported = MutableStateFlow<Boolean?>(null)

    /**
     * Whether the PC's quiz knows Spanish practice: null until a quiz reply has
     * been seen, false when a reply had no "mode" (an older PC, contract C2).
     */
    val spanishSupported: StateFlow<Boolean?> = _spanishSupported.asStateFlow()

    private val _spanishNotice = MutableStateFlow<String?>(null)

    /**
     * The PC's own Spanish crisis-words notice, as it last sent it (never a
     * copy written on this phone). Process memory only.
     */
    val spanishNotice: StateFlow<String?> = _spanishNotice.asStateFlow()

    /** Holds [q] as the open quiz and notes what its reply said about Spanish practice. */
    private fun adoptQuiz(q: com.jarvis.client.net.Quiz.Session) {
        _quiz.value = q
        _spanishSupported.value = q.modeKnown
        q.notice?.let { _spanishNotice.value = it }
    }

    /**
     * Finishes the quiz AND keeps the ticked questions in a deck (contract C2/C3).
     * Nothing is sent until the owner taps "Keep and finish". No card: the owner's
     * own tap is the yes, and the Keep sheet listed every word first. Held on a
     * stale link. On success the quiz is gone here; on a crisis phrase in a back
     * nothing is kept and the quiz stays open (its new state is held); on any
     * failure the quiz stays open. @return the outcome, whose `code` is the PC's
     * error code (a `deck_not_found` makes the caller read the decks again).
     */
    suspend fun keepQuiz(
        deck: String?,
        newDeck: String?,
        cards: List<com.jarvis.client.net.Quiz.KeepCard>,
    ): com.jarvis.client.net.Quiz.Outcome<com.jarvis.client.net.Quiz.Finished> {
        actionBlocker()?.let { return com.jarvis.client.net.Quiz.Outcome(false, null, it) }
        val id = _quiz.value?.id
        if (id == null || !com.jarvis.client.net.Quiz.validId(id)) {
            return com.jarvis.client.net.Quiz.Outcome(
                false, null, com.jarvis.client.net.Quiz.messageFor(com.jarvis.client.net.Quiz.E_NOT_FOUND).orEmpty(),
                gone = true,
            )
        }
        val body = com.jarvis.client.net.Quiz.keepBody(deck, newDeck, cards)
            ?: return com.jarvis.client.net.Quiz.Outcome(
                false, null, com.jarvis.client.net.Quiz.keepMessageFor("nothing_to_keep").orEmpty(),
            )
        val out = when (val r = api.quizCall("/api/quiz/$id/finish", body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Quiz.finishedKeepSaid(r.value)
            is ApiResult.Failed -> return com.jarvis.client.net.Quiz.Outcome(false, null, "Not kept. " + describe(r.error))
        }
        val result = out.value
        if (out.ok && result != null) {
            val open = result.quiz
            if (result.crisis != null && open != null) {
                adoptQuiz(open)
            } else {
                _quiz.value = null
                _decksTick.update { n -> n + 1 }
            }
        } else if (out.gone) {
            _quiz.value = null
        }
        return out
    }

    /**
     * Sends the pasted text to the PC and takes the questions it writes. No
     * card: the owner's own words, the local model only. Held on a stale
     * link (rule 4). @return whether it started, and the sentence to show.
     */
    suspend fun startQuiz(
        text: String,
        count: Int = com.jarvis.client.net.Quiz.DEFAULT_COUNT,
        mode: String = com.jarvis.client.net.Quiz.MODE_TEXT,
        level: String = com.jarvis.client.net.Quiz.DEFAULT_LEVEL,
        exercise: String = com.jarvis.client.net.Quiz.DEFAULT_EXERCISE,
        topic: String = "",
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val spanish = mode == com.jarvis.client.net.Quiz.MODE_SPANISH
        // Spanish practice's text is optional: blank means the model writes the sentences.
        val textOk = if (spanish) com.jarvis.client.net.Quiz.validSpanishText(text)
        else com.jarvis.client.net.Quiz.validText(text)
        if (!textOk) {
            return false to (com.jarvis.client.net.Quiz.messageFor(
                if (text.trim().length < com.jarvis.client.net.Quiz.MIN_TEXT) com.jarvis.client.net.Quiz.E_TEXT_SHORT
                else com.jarvis.client.net.Quiz.E_TEXT_LONG,
            ) ?: "That text does not fit.")
        }
        if (!com.jarvis.client.net.Quiz.validCount(count)) {
            return false to (com.jarvis.client.net.Quiz.messageFor(com.jarvis.client.net.Quiz.E_BAD_COUNT) ?: "")
        }
        val body = if (spanish) com.jarvis.client.net.Quiz.startSpanishBody(text, level, exercise, topic, count)
        else com.jarvis.client.net.Quiz.startBody(text, count)
        val out = when (val r = api.quizCall("/api/quiz", body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Quiz.startedSaid(r.value)
            is ApiResult.Failed -> return false to ("Not started. " + describe(r.error))
        }
        val q = out.value
        if (out.ok && q != null) {
            _spanishSupported.value = q.modeKnown
            if (spanish && !q.modeKnown) {
                // An older PC ignored "mode" and opened an ordinary quiz: close it
                // again (best effort) and say so; only Text mode is offered from now on.
                if (com.jarvis.client.net.Quiz.validId(q.id)) {
                    api.quizCall("/api/quiz/${q.id}/stop", com.jarvis.client.net.Quiz.EMPTY_BODY)
                }
                return false to com.jarvis.client.net.Quiz.OLD_PC
            }
            adoptQuiz(q)
            return true to ""
        }
        return false to out.said
    }

    /**
     * Reads the open quiz again from the PC (a read: never held). If the PC
     * no longer has it (60 minutes unused, a restart), it is forgotten here
     * too. @return the sentence to show, or null when all is well.
     */
    suspend fun refreshQuiz(): String? {
        val id = _quiz.value?.id ?: return null
        if (!com.jarvis.client.net.Quiz.validId(id)) return null
        return when (val r = api.quizCall("/api/quiz/$id", null)) {
            is ApiResult.Ok -> {
                val out = com.jarvis.client.net.Quiz.readSaid(r.value)
                val q = out.value
                when {
                    out.ok && q != null -> {
                        adoptQuiz(q)
                        null
                    }
                    out.gone -> {
                        _quiz.value = null
                        out.said
                    }
                    else -> out.said
                }
            }
            is ApiResult.Failed -> noticeFor(r.error)
        }
    }

    /**
     * Sends one typed answer to be marked against the passage. No card. Held
     * on a stale link. @return the answer if it was checked (a mark, or for a crisis
     * answer the PC's own help words and no mark - JARVIS-API 98.4), and the
     * sentence to show when it was not. The quiz held here moves on with it.
     */
    suspend fun answerQuiz(n: Int, answer: String): Pair<com.jarvis.client.net.Quiz.Answer?, String> {
        actionBlocker()?.let { return null to it }
        val id = _quiz.value?.id
        if (id == null || !com.jarvis.client.net.Quiz.validId(id)) {
            return null to (com.jarvis.client.net.Quiz.messageFor(com.jarvis.client.net.Quiz.E_NOT_FOUND) ?: "")
        }
        if (!com.jarvis.client.net.Quiz.validAnswer(answer)) {
            return null to (com.jarvis.client.net.Quiz.messageFor(
                if (answer.trim().isEmpty()) com.jarvis.client.net.Quiz.E_ANSWER_EMPTY
                else com.jarvis.client.net.Quiz.E_ANSWER_LONG,
            ) ?: "")
        }
        val out = when (val r = api.quizCall("/api/quiz/$id/answer",
            com.jarvis.client.net.Quiz.answerBody(n, answer))) {
            is ApiResult.Ok -> com.jarvis.client.net.Quiz.answeredSaid(r.value)
            is ApiResult.Failed -> return null to ("Not checked. " + describe(r.error))
        }
        val result = out.value
        if (out.ok && result != null) {
            adoptQuiz(result.quiz)
            return result to ""
        }
        if (out.gone) _quiz.value = null
        return null to out.said
    }

    /**
     * Ends the quiz and takes the short "look at these again" summary. The PC
     * deletes the session. Held on a stale link. @return the summary if it
     * finished, and the sentence to show when it did not.
     */
    suspend fun finishQuiz(): Pair<com.jarvis.client.net.Quiz.Summary?, String> {
        actionBlocker()?.let { return null to it }
        val id = _quiz.value?.id
        if (id == null || !com.jarvis.client.net.Quiz.validId(id)) {
            return null to (com.jarvis.client.net.Quiz.messageFor(com.jarvis.client.net.Quiz.E_NOT_FOUND) ?: "")
        }
        val out = when (val r = api.quizCall("/api/quiz/$id/finish",
            com.jarvis.client.net.Quiz.EMPTY_BODY)) {
            is ApiResult.Ok -> com.jarvis.client.net.Quiz.finishedSaid(r.value)
            is ApiResult.Failed -> return null to ("Not finished. " + describe(r.error))
        }
        val s = out.value
        if (out.ok && s != null) {
            _quiz.value = null
            return s to ""
        }
        if (out.gone) _quiz.value = null
        return null to out.said
    }

    /**
     * Stops the quiz and forgets it: the PC deletes the session. Held on a
     * stale link. @return whether it stopped, and the sentence to show.
     */
    suspend fun stopQuiz(): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val id = _quiz.value?.id
        if (id == null || !com.jarvis.client.net.Quiz.validId(id)) {
            _quiz.value = null
            return true to "Stopped. Nothing was kept."
        }
        val out = when (val r = api.quizCall("/api/quiz/$id/stop",
            com.jarvis.client.net.Quiz.EMPTY_BODY)) {
            is ApiResult.Ok -> com.jarvis.client.net.Quiz.stoppedSaid(r.value)
            is ApiResult.Failed -> return false to ("Not stopped. " + describe(r.error))
        }
        // "Not found" means it is already gone on the PC: that is what stopping wanted.
        if (out.ok || out.gone) {
            _quiz.value = null
            return true to "Stopped. Nothing was kept."
        }
        return false to out.said
    }

    // ------------------------------------------------------- Study decks ----
    // "My study decks" (docs/QUIZ-DECKS-DESIGN.md, contract C1-C6) - see
    // [com.jarvis.client.net.Decks] and ui/screens/DecksPlate.kt. The PC keeps
    // every deck, sealed; this phone keeps NOTHING: no card text in a file,
    // a preference or a database. Every write is held on a stale link (rule 4);
    // reads are not. No approval card: the owner's own tap is the yes.

    private val _decksTick = MutableStateFlow(0)

    /**
     * Goes up by one after every change made from this phone (and after a
     * quiz's Keep), so "My study decks" reads itself again - the same shape as
     * [goalsTick].
     */
    val decksTick: StateFlow<Int> = _decksTick.asStateFlow()

    private suspend fun <T> decksRead(
        path: String?,
        lead: String,
        said: (com.jarvis.client.net.Decks.Reply) -> com.jarvis.client.net.Decks.Outcome<T>,
    ): com.jarvis.client.net.Decks.Outcome<T> {
        if (path == null) return com.jarvis.client.net.Decks.blocked("$lead That is not one of your decks.")
        return when (val r = api.decksCall(path, null)) {
            is ApiResult.Ok -> said(r.value)
            is ApiResult.Failed -> com.jarvis.client.net.Decks.blocked("$lead " + describe(r.error))
        }
    }

    private suspend fun <T> decksWrite(
        path: String?,
        body: String?,
        lead: String,
        said: (com.jarvis.client.net.Decks.Reply) -> com.jarvis.client.net.Decks.Outcome<T>,
    ): com.jarvis.client.net.Decks.Outcome<T> {
        actionBlocker()?.let { return com.jarvis.client.net.Decks.blocked(it) }
        if (path == null || body == null) {
            return com.jarvis.client.net.Decks.blocked("$lead That does not look right.")
        }
        val out = when (val r = api.decksCall(path, body)) {
            is ApiResult.Ok -> said(r.value)
            is ApiResult.Failed -> com.jarvis.client.net.Decks.blocked("$lead " + describe(r.error))
        }
        if (out.ok) _decksTick.update { n -> n + 1 }
        return out
    }

    /** `GET /api/decks`: the deck list, the day's counts and the `line`. A read: never held. */
    suspend fun decksList(): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.DeckList> =
        decksRead("/api/decks", "Not read.", com.jarvis.client.net.Decks::listSaid)

    /** `POST /api/decks`: a new, empty deck. */
    suspend fun decksCreate(name: String): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Deck> {
        val ok = com.jarvis.client.net.Decks.validName(name)
        return decksWrite("/api/decks", if (ok) com.jarvis.client.net.Decks.createBody(name) else null, "Not made.") {
            com.jarvis.client.net.Decks.deckSaid(it, "Not made.")
        }
    }

    /** `POST /api/decks/settings`: "New cards a day", 0 to 20. */
    suspend fun decksSetPerDay(n: Int): com.jarvis.client.net.Decks.Outcome<Int> =
        decksWrite(
            "/api/decks/settings",
            if (com.jarvis.client.net.Decks.validPerDay(n)) com.jarvis.client.net.Decks.settingsBody(n) else null,
            "Not changed.",
            com.jarvis.client.net.Decks::perDaySaid,
        )

    /** `POST /api/decks/{id}/act`: `pause`, `resume` or `delete` (delete after the owner's "are you sure?"). */
    suspend fun decksAct(id: String, op: String): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Acted> =
        decksWrite(
            com.jarvis.client.net.Decks.deckActPath(id), com.jarvis.client.net.Decks.deckActBody(op), "Not changed.",
        ) { com.jarvis.client.net.Decks.actedSaid(it, "Not changed.") }

    /** `POST /api/decks/{id}/act`, `rename`. The desktop's Edit on a deck row does the same. */
    suspend fun decksRename(id: String, name: String): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Acted> =
        decksWrite(
            com.jarvis.client.net.Decks.deckActPath(id),
            if (com.jarvis.client.net.Decks.validName(name)) com.jarvis.client.net.Decks.renameBody(name) else null,
            "Not changed.",
        ) { com.jarvis.client.net.Decks.actedSaid(it, "Not changed.") }

    /** `GET /api/decks/{id}/cards`. A read. */
    suspend fun decksCards(id: String): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.DeckCards> =
        decksRead(com.jarvis.client.net.Decks.cardsPath(id), "Not read.", com.jarvis.client.net.Decks::cardsSaid)

    /** `POST /api/decks/{id}/cards/{cid}/act`, `edit`. */
    suspend fun decksCardEdit(
        id: String,
        cid: String,
        front: String,
        back: String,
    ): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.CardFull> {
        val ok = com.jarvis.client.net.Decks.validFront(front) && com.jarvis.client.net.Decks.validBack(back)
        return decksWrite(
            com.jarvis.client.net.Decks.cardActPath(id, cid),
            if (ok) com.jarvis.client.net.Decks.cardEditBody(front, back) else null,
            "Not saved.",
        ) { com.jarvis.client.net.Decks.cardSaid(it, "Not saved.") }
    }

    /** `POST /api/decks/{id}/cards/{cid}/act`, `delete` (after the owner's "are you sure?"). */
    suspend fun decksCardDelete(id: String, cid: String): com.jarvis.client.net.Decks.Outcome<Unit> =
        decksWrite(
            com.jarvis.client.net.Decks.cardActPath(id, cid), com.jarvis.client.net.Decks.CARD_DELETE_BODY, "Not deleted.",
        ) { com.jarvis.client.net.Decks.deletedSaid(it, "Not deleted.") }

    /** `GET /api/review[?deck=]`: the next card and the state. A read: never held. */
    suspend fun reviewStart(deck: String?): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Review> =
        decksRead(com.jarvis.client.net.Decks.reviewPath(deck), "Not read.", com.jarvis.client.net.Decks::reviewSaid)

    /** `POST /api/review/reveal`: show the back. Required before a rating. */
    suspend fun reviewReveal(card: String): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Reveal> =
        decksWrite(
            "/api/review/reveal",
            if (com.jarvis.client.net.Decks.validId(card)) com.jarvis.client.net.Decks.revealBody(card) else null,
            "Not shown.",
            com.jarvis.client.net.Decks::revealSaid,
        )

    /** `POST /api/review/rate`: the owner's own rating; the reply carries the next card. */
    suspend fun reviewRate(
        card: String,
        rating: String,
        deck: String?,
    ): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Review> =
        decksWrite(
            "/api/review/rate",
            // [deck]: the scope this screen reviews ("" = every deck), so the PC counts it in that run only.
            if (com.jarvis.client.net.Decks.validId(card)) {
                com.jarvis.client.net.Decks.rateBody(card, rating, deck ?: "")
            } else {
                null
            },
            "Not saved.",
            com.jarvis.client.net.Decks::ratedSaid,
        )

    /** `POST /api/review/more`: "Do 10 more". */
    suspend fun reviewMore(deck: String?): com.jarvis.client.net.Decks.Outcome<com.jarvis.client.net.Decks.Review> =
        decksWrite(
            "/api/review/more",
            if (deck == null || com.jarvis.client.net.Decks.validId(deck)) com.jarvis.client.net.Decks.moreBody(deck) else null,
            "Not changed.",
            com.jarvis.client.net.Decks::reviewSaid,
        )

    /**
     * One Today card (backend jarvis_today.py, 2026-09-28): the owner's own
     * [text], shown from [at] ("HH:MM") on [days] (0 = Monday). The PC sets it
     * up at once, with no card - the desktop's `brain_schedule_add_today`.
     * Held on a stale link, like every change. @return whether the PC took
     * it, and the sentence to show.
     */
    suspend fun addTodayCard(text: String, at: String, days: Set<Int>): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val (body, why) = com.jarvis.client.net.Today.addBody(text, at, days)
        if (body == null) return false to (why ?: com.jarvis.client.net.Today.NO_WORDS)
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Schedule.said(r.value).also {
                _scheduleTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not added. " + describe(r.error))
        }
    }

    private fun onScheduleEvent(data: kotlinx.serialization.json.JsonElement?, eventId: String? = null) {
        _scheduleTick.update { it + 1 }
        val obj = data as? JsonObject
        if (com.jarvis.client.net.Briefing.isAbout(obj)) {
            _briefingTick.update { it + 1 }
            // A briefing is announced when it is READY, never when its time
            // comes: it takes a moment to put together.
            com.jarvis.client.net.Briefing.readyFrom(obj)?.let { onBriefingReady(it, eventId) }
            return
        }
        // A job changed on the PC - snoozed, deleted or done there, by voice
        // or in Coming up: a notification still showing for it, ringing or
        // not, goes (bug audit 2026-09-26, #1). Never a "tell me when"
        // match's: its job ends the moment it matched to tell only once.
        com.jarvis.client.net.Schedule.changedFrom(obj)?.let { (id, kind) ->
            if (com.jarvis.client.net.Schedule.cancelsOnChange(kind)) {
                appContext?.let { ctx ->
                    runCatching { com.jarvis.client.service.ScheduleNotifier.cancel(ctx, id) }
                }
            }
            return
        }
        // A "tell me when" matched: it only tells - the alert is read by id,
        // and an urgent one rings until seen.
        com.jarvis.client.net.Schedule.matchedFrom(obj)?.let { (id, urgent) ->
            onTellMeMatched(id, urgent, eventId)
            return
        }
        // A "tell me when" cannot look (2026-09-28): told once per problem by
        // the PC; an ordinary notification, never ringing.
        com.jarvis.client.net.Schedule.brokenFrom(obj)?.let { id ->
            onTellMeBroken(id, eventId)
            return
        }
        val (id, kind) = com.jarvis.client.net.Schedule.firedFrom(obj) ?: return
        val context = appContext ?: return
        // Written at once, not within two seconds: if the process is killed
        // now, a restart must not replay this event and ring it again.
        flushResumePoint()
        val arrived = System.currentTimeMillis()
        scope.launch {
            val job = when (val r = api.scheduleJob(id)) {
                is ApiResult.Ok -> com.jarvis.client.net.Schedule.parseOne(r.value)
                is ApiResult.Failed -> null
            }
            // Once per job going off: a replayed event after a reconnect
            // must not ring twice. A job that could not be read is told apart
            // by its event, not taken for every other unreadable firing.
            val key = com.jarvis.client.net.Schedule.shownKey(id, job?.firedAt, eventId, arrived)
            val fresh = synchronized(scheduleShown) {
                if (scheduleShown.size > 500) scheduleShown.clear()
                scheduleShown.add(key)
            }
            if (!fresh) return@launch
            val security = settings.security.value
            // A notification is outside the app: a lock that is ON counts,
            // whether or not the lists were shown a moment ago.
            val locked = security.appLock || security.privateLists
            val (title, text) = com.jarvis.client.net.Schedule.notification(kind, job, locked)
            val lockScreen = job?.lockScreen?.takeIf { it.isNotEmpty() }
                ?: com.jarvis.client.net.Schedule.lockScreen(kind)
            // Heard more than ten minutes after it went off (the phone was
            // out of reach, or restarted): a silent "Missed at 07:00." notice,
            // never an alarm ringing as if it were now (the owner, 2026-09-26).
            val late = com.jarvis.client.net.Schedule.heardLate(job?.firedAt, arrived / 1000.0)
            com.jarvis.client.service.ScheduleNotifier.post(
                context, id, kind, title,
                if (late) com.jarvis.client.net.Schedule.missedWords(job?.wentOffAt.orEmpty(), text) else text,
                lockScreen,
                // An alarm keeps ringing until seen (2026-09-25).
                ring = com.jarvis.client.net.Schedule.rings(kind, urgent = false),
                quiet = late,
            )
        }
    }

    /**
     * A "tell me when" matched (backend jarvis_tellme.py): read its alert by
     * id ("An email from Alex arrived." - made on the PC from the owner's own
     * words) and show it; urgent rings until seen. While App lock or "Hide
     * memory lists and chat history" is on, only the generic words. Once per
     * match, even when a reconnect replays the event. It only tells: nothing
     * here acts.
     */
    private fun onTellMeMatched(id: String, urgent: Boolean, eventId: String? = null) {
        val context = appContext ?: return
        val kind = com.jarvis.client.net.Schedule.TELLME
        flushResumePoint()
        val arrived = System.currentTimeMillis()
        scope.launch {
            val job = when (val r = api.scheduleJob(id)) {
                is ApiResult.Ok -> com.jarvis.client.net.Schedule.parseOne(r.value)
                is ApiResult.Failed -> null
            }
            val key = com.jarvis.client.net.Schedule.shownKey(id, job?.alertAt, eventId, arrived, "#match@")
            val fresh = synchronized(scheduleShown) {
                if (scheduleShown.size > 500) scheduleShown.clear()
                scheduleShown.add(key)
            }
            if (!fresh) return@launch
            val security = settings.security.value
            val locked = security.appLock || security.privateLists
            val (title, text) = com.jarvis.client.net.Schedule.notification(kind, job, locked)
            com.jarvis.client.service.ScheduleNotifier.post(
                context, id, kind, title, text, com.jarvis.client.net.Schedule.TELLME_LOCK_SCREEN,
                ring = com.jarvis.client.net.Schedule.rings(kind, urgent),
                key = key,
            )
        }
    }

    // ------------------------------------------------- Jarvis Live ----
    // The owner's decision and answers of 2026-09-28 (docs/LIVE-DESIGN.md):
    // a back-and-forth voice conversation the owner starts and stops. The
    // session is the PC's (GET/POST /api/voice/live); the phone's microphone
    // is service/LiveService.kt, its rules voice/LiveRules.kt, its screen
    // ui/screens/LiveScreen.kt (and a strip on Home). While Live is on here,
    // "hey Jarvis" listening lets go of the microphone (WakeWordService).

    private val _liveStatus = MutableStateFlow<JsonObject?>(null)

    /** The PC's Live session as last read: fixed words and numbers only. */
    val liveStatus: StateFlow<JsonObject?> = _liveStatus.asStateFlow()

    /** "Heard you - thinking" or "Didn't catch that - say a bit more", for a moment. */
    data class LiveFlash(
        val thinking: Boolean = false,
        val short: Boolean = false,
        val trouble: Boolean = false,
        val sideTalk: Boolean = false,
        val until: Long = 0L,
    )

    private val _liveFlash = MutableStateFlow(LiveFlash())
    val liveFlash: StateFlow<LiveFlash> = _liveFlash.asStateFlow()

    private val _liveMove = MutableStateFlow("")

    private val _liveMic = MutableStateFlow<String?>(null)

    /**
     * Which microphone Live listens through on this phone ("Microphone: your
     * Bluetooth headset (Buds)"), set by LiveService each time it opens one;
     * null while Live is not listening here (the Jarvis Live extras).
     */
    val liveMic: StateFlow<String?> = _liveMic.asStateFlow()

    fun liveMicWords(words: String?) {
        _liveMic.value = words
    }

    /** "Live is on your PC - move it here?": the other device's name ("desktop"), or "". */
    val liveMove: StateFlow<String> = _liveMove.asStateFlow()

    /** Why Live could not start, or the microphone stopped - in words - and whether it is "train your voice". */
    data class LiveNotice(val text: String, val needsVoice: Boolean = false)

    private val _liveNotice = MutableStateFlow<LiveNotice?>(null)
    val liveNoticeText: StateFlow<LiveNotice?> = _liveNotice.asStateFlow()

    /** When the status was last read, and how long ago (by the PC) it had ended then. */
    @Volatile private var liveEndedBase: Pair<Long, Int>? = null

    fun liveNotice(text: String?) {
        _liveNotice.value = text?.let { LiveNotice(it, it.startsWith(com.jarvis.client.voice.LiveRules.NEEDS_VOICE)) }
        liveNoticeJob?.cancel()
        if (text != null) {
            // Never lingers (the review's C8): gone after half a minute.
            liveNoticeJob = scope.launch {
                delay(LIVE_NOTICE_MS)
                _liveNotice.value = null
            }
        }
    }

    @Volatile private var liveNoticeJob: Job? = null
    @Volatile private var liveMoveJob: Job? = null
    @Volatile private var liveWatch: Job? = null
    @Volatile private var liveWarnJob: Job? = null
    @Volatile private var liveStopRetry: Job? = null
    @Volatile private var liveCallAsked: Boolean? = null
    @Volatile private var liveCallAskedAt = 0L

    /** The owner pressed "Listen anyway" during a call: not muted again until the call is seen to end. */
    @Volatile private var liveCallOverridden = false

    /** "Resume Live" / "Move it here": the same chat carries on (no new conversation). */
    @Volatile private var liveResuming = false

    /** Is Live on on THIS phone? */
    fun liveOnHere(): Boolean = com.jarvis.client.voice.LiveRules.onHere(_liveStatus.value)

    /**
     * Does a card this phone holds keep Live paused (microphone closed, no
     * tap buttons)? Only one raised in THIS Live session - the PC's own rule
     * (LiveRules.cardInSession; the review's bug 3 and B8: the service never
     * passed it, and every old card hid the tap buttons for good).
     */
    fun liveCardHolds(): Boolean {
        if (!liveOnHere()) return false
        val st = _liveStatus.value
        return _pending.value.any { com.jarvis.client.voice.LiveRules.cardInSession(it.createdAt, st) }
    }

    /** Seconds since Live ended, counted on from the PC's `ended_ago_s`; null when it has not. */
    fun liveEndedAgo(): Int? {
        val base = liveEndedBase ?: return null
        return base.second + ((SystemClock.elapsedRealtime() - base.first) / 1000L).toInt()
    }

    private fun takeLiveStatus(st: JsonObject?) {
        val before = _liveStatus.value
        _liveStatus.value = st
        val ended = (st?.get("state") as? JsonPrimitive)?.content == "ended"
        if (!ended) {
            liveEndedBase = null
            return
        }
        val sameEnd = (before?.get("state") as? JsonPrimitive)?.content == "ended" &&
            before?.get("session") == st?.get("session")
        if (!sameEnd || liveEndedBase == null) {
            val ago = (st?.get("ended_ago_s") as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
            liveEndedBase = SystemClock.elapsedRealtime() to ago
        }
    }

    /** `GET /api/voice/live`. A read: never held. */
    suspend fun liveRead() {
        api.liveStatus().onOk { takeLiveStatus(it) }
    }

    /** The Live screen opened: read the session, and listen again if it is on here. */
    suspend fun liveOpened() {
        liveRead()
        if (liveOnHere()) beginLiveHere()
    }

    /**
     * Start Jarvis Live on this phone. No card - the owner's own act - but
     * held on a stale link (rule 4). The PC refuses it until the owner's
     * voice is trained (the voice check runs on every clip), and says so.
     * Null when it started, or why not in words. [resume]: "Resume Live" or
     * "Move it here" - the same chat carries on; otherwise a new Live session
     * is a new chat (docs/LIVE-DESIGN.md section 3.7; the review's C4).
     */
    suspend fun liveStart(resume: Boolean = false, move: Boolean = false): String? {
        actionBlocker()?.let { return it }
        liveNotice(null)
        // Which chat the session's words go in (the chat audit, 2026-09-28):
        // "Move it here" carries on the OTHER device's chat - the PC's Live
        // status names it - so the same conversation goes on here (it used
        // to carry on whatever chat Home happened to be in); "Resume Live"
        // this phone's own; a new session a new chat. The id goes with Start.
        val rules = com.jarvis.client.voice.LiveRules
        val theirs = if (move) {
            rules.sessionChat((_liveStatus.value?.get("conversation_id") as? JsonPrimitive)?.takeIf { it.isString }?.content)
        } else {
            null
        }
        val cid = when {
            theirs != null -> theirs
            resume && !move -> chat.conversationIdNow()
            else -> com.jarvis.client.net.ChatHistory.newConversationId()
        }
        return when (val r = api.liveWrite(rules.startBody(cid))) {
            is ApiResult.Ok -> {
                val (code, body) = r.value
                if (code !in 200..299 || body?.get("ok")?.let { (it as? JsonPrimitive)?.content } != "true") {
                    liveError(body, code).also { liveNotice(it) }
                } else {
                    when {
                        theirs != null -> carryOnMoved(theirs)
                        // Home's chat goes when a new Live session starts: say where it went.
                        !(resume && !move) -> chat.continueFrom(
                            cid,
                            emptyList(),
                            if (chat.hasKeptChat()) com.jarvis.client.net.ChatHistory.LIVE_STARTED_NOTE else null,
                        )
                    }
                    (body["status"] as? JsonObject)?.let { takeLiveStatus(it) }
                    clearLiveMove()
                    // The start line only once the microphone service is in
                    // the foreground: Android 14 refuses one started from the
                    // background, and "I'm listening." must not be a promise
                    // nobody keeps (the review's B7).
                    if (beginLiveHere() && awaitLiveListening()) {
                        val say = (body["say"] as? JsonPrimitive)?.takeIf { it.isString }?.content.orEmpty()
                        scope.launch { voice.sayLine(say) }
                        null
                    } else {
                        liveStop("owner")
                        LIVE_NOT_ALLOWED.also { liveNotice(it) }
                    }
                }
            }
            is ApiResult.Failed -> liveFailed(r.error).also { liveNotice(it) }
        }
    }

    /** "Hide memory lists and chat history" is hiding them now - set by MainActivity, read here. */
    @Volatile var privateListsHidden: Boolean = false

    /**
     * "Move it here": Home takes over the other device's Live chat - its
     * kept messages read back from History when there are any (history on,
     * an answer kept), else just its id, so what follows is filed with it.
     */
    private suspend fun carryOnMoved(id: String) {
        // Lists hidden: nothing is read back (the id alone carries on, as with history off).
        val t = if (privateListsHidden) {
            null
        } else {
            (api.historyConversation(id) as? ApiResult.Ok)?.let { com.jarvis.client.net.ChatLog.transcript(it.value) }
        }
        val window = if (t != null && t.continuable) {
            com.jarvis.client.net.ChatHistory.continueWindow(t.turns).window
        } else {
            emptyList()
        }
        chat.continueFrom(
            id,
            window,
            com.jarvis.client.net.ChatHistory.MOVED_HERE,
            readOutside = t != null && t.continuable && t.tainted,
        )
    }

    /**
     * End Jarvis Live. Never held, never a card. The microphone closes here
     * first, and the phone shows Live as ended at once; if the PC cannot be
     * reached, the end is sent again in the background until it is (the
     * review's B1 and B2: an End could be lost, and a bad link left the
     * screen saying Live was on).
     */
    suspend fun liveStop(why: String = "owner"): String? {
        endLiveHere()
        voice.endLiveTurn()
        val wasHere = liveOnHere()
        if (wasHere) {
            takeLiveStatus(endedLocally(why))
            // Home says where the session went (the second chat audit).
            chat.noteLiveEnded()
        }
        val body = com.jarvis.client.voice.LiveRules.stopBody(why)
        return when (val r = api.liveWrite(body)) {
            is ApiResult.Ok -> {
                (r.value.second?.get("status") as? JsonObject)?.let { takeLiveStatus(it) }
                null
            }
            is ApiResult.Failed -> {
                liveStopRetry?.cancel()
                liveStopRetry = scope.launch {
                    repeat(LIVE_STOP_RETRIES) {
                        delay(LIVE_STOP_RETRY_MS)
                        val again = api.liveWrite(body)
                        if (again is ApiResult.Ok) {
                            (again.value.second?.get("status") as? JsonObject)?.let { takeLiveStatus(it) }
                            return@launch
                        }
                    }
                }
                "Live has ended on this phone. " + liveFailed(r.error)
            }
        }
    }

    /**
     * Start Live from the Quick Settings tile or "Live ended - Resume"
     * (MainActivity, once the app is unlocked): [liveStart], in the
     * runtime's own scope so a screen change cannot cut it off. Its own
     * rules hold (held on a stale link; the PC refuses it until the owner's
     * voice is trained), and a refusal shows on the Live screen.
     */
    fun liveStartSoon(resume: Boolean = false) {
        scope.launch { liveStart(resume) }
    }

    /** End Live from anywhere that must not wait (the notification, the End Live button): the runtime's own scope. */
    fun liveEndNow(why: String = "owner") {
        scope.launch { liveStop(why) }
    }

    /** What the phone shows while the PC has not yet answered an End. */
    private fun endedLocally(why: String): JsonObject = kotlinx.serialization.json.buildJsonObject {
        put("state", JsonPrimitive("ended"))
        put("on", JsonPrimitive(false))
        put("ended", JsonPrimitive(why))
        put("ended_device", JsonPrimitive(com.jarvis.client.voice.LiveRules.ME))
        put("ended_ago_s", JsonPrimitive(0))
        put("resumable", JsonPrimitive(false))
        _liveStatus.value?.get("session")?.let { put("session", it) }
    }

    /** Mic off / Mic on / Listen anyway: the microphone closes, the session and its time carry on. Never held. */
    suspend fun liveMute(muted: Boolean): String? {
        val st = _liveStatus.value
        if (!muted && (st?.get("muted_why") as? JsonPrimitive)?.content == "call") {
            // "Listen anyway": the owner's word over a call that still reads
            // as on - a stuck in-communication mode must not keep them muted
            // for good (the review's bug 4; the PC's MIC_OVERRIDDEN).
            liveCallOverridden = true
        }
        return livePost(com.jarvis.client.voice.LiveRules.muteBody(muted, "owner"))
    }

    /** "More time". Held on a stale link. */
    suspend fun liveExtend(minutes: Int = 20): String? {
        actionBlocker()?.let { return it }
        val body = com.jarvis.client.voice.LiveRules.extendBody(minutes) ?: return "Say 1 to 120 more minutes."
        return livePost(body)
    }

    /** "Carry on" after a voice pause. Held on a stale link. */
    suspend fun liveCarryOn(): String? {
        actionBlocker()?.let { return it }
        return livePost(com.jarvis.client.voice.LiveRules.RESUME_BODY)
    }

    private suspend fun livePost(body: String): String? =
        when (val r = api.liveWrite(body)) {
            is ApiResult.Ok -> {
                val (code, json) = r.value
                (json?.get("status") as? JsonObject)?.let { takeLiveStatus(it) }
                if (code in 200..299) null else liveError(json, code)
            }
            is ApiResult.Failed -> liveFailed(r.error)
        }

    /** The PC's own words; never a bare status number (the review's C8). */
    private fun liveError(body: JsonObject?, code: Int): String =
        (body?.get("error") as? JsonPrimitive)?.takeIf { it.isString }?.content
            ?: if (code == 404) LIVE_MISSING else "Your PC said no to that. Try again in a moment."

    private fun liveFailed(error: ApiError): String = when (error) {
        ApiError.NotFound -> LIVE_MISSING
        ApiError.BadToken -> "Your PC did not accept this phone's key. Pair it again."
        else -> "Could not reach your PC. Check the link, then try again."
    }

    /**
     * A phone or video call began or ended (LiveService reads the audio
     * mode): Live mutes itself for it, and unmutes after - never undoing the
     * owner's own Mic off, and never muting again after "Listen anyway"
     * until the call is seen to end. Asked once, not every loop.
     */
    fun liveCall(onCall: Boolean) {
        if (!onCall) liveCallOverridden = false
        val change = com.jarvis.client.voice.LiveRules.callMuteChange(_liveStatus.value, onCall, liveCallOverridden)
        if (change == null) {
            liveCallAsked = null
            return
        }
        val now = SystemClock.elapsedRealtime()
        if (liveCallAsked == change && now - liveCallAskedAt < LIVE_CALL_ASK_MS) return
        liveCallAsked = change
        liveCallAskedAt = now
        scope.launch { livePost(com.jarvis.client.voice.LiveRules.muteBody(change, "call")) }
    }

    /**
     * This phone lost the audio focus while Live is on here - a call ringing
     * or starting while Jarvis talks (the review's B6: the audio mode alone
     * was only read between answers). Jarvis stops talking, and Live pauses
     * for the call; the service unmutes it when the call is over.
     */
    private fun liveFocusLost() {
        if (!liveOnHere()) return
        val mode = (appContext?.getSystemService(Context.AUDIO_SERVICE) as? android.media.AudioManager)?.mode ?: return
        val ringing = mode == android.media.AudioManager.MODE_RINGTONE
        if (!ringing && !com.jarvis.client.voice.LiveRules.onCall(mode, voice.speaker.voiceCall)) return
        voice.stopSpeaking()
        liveCall(true)
    }

    /** A Live clip came back: "Heard you - thinking" at once when it was the owner's question. */
    fun liveHeard(heard: com.jarvis.client.net.Heard) {
        if (heard.ok && heard.owner && heard.text.isNotBlank() && heard.live.isNotEmpty()) {
            _liveFlash.value = LiveFlash(thinking = true, until = SystemClock.elapsedRealtime() + LIVE_FLASH_MS)
            voice.heardYou()
        }
    }

    /** Jarvis's first sound for a Live answer: "Heard you - thinking" goes (the review's C9). */
    fun liveAnswerSounded() {
        if (_liveFlash.value.thinking) _liveFlash.value = LiveFlash()
    }

    /** A Live answer that was side talk: "(not for Jarvis)" on the sign for a moment. */
    fun liveSideTalk() {
        _liveFlash.value = LiveFlash(sideTalk = true, until = SystemClock.elapsedRealtime() + LIVE_FLASH_MS)
    }

    /**
     * "Hey Jarvis" to this phone while Live runs on the PC (the review's #2
     * and bug 7: it used to be silently ignored). Said in fixed words, and a
     * notification offers to move Live here; both go after 30 seconds.
     */
    private fun offerLiveMove(device: String) {
        _liveMove.value = device
        val words = com.jarvis.client.voice.LiveRules.SEEN.getValue("elsewhere")
            .replace("{device}", com.jarvis.client.voice.LiveRules.deviceWords(device)) + "."
        scope.launch { voice.sayLine(words) }
        appContext?.let { com.jarvis.client.service.LiveService.showMoveOffer(it, device) }
        liveMoveJob?.cancel()
        liveMoveJob = scope.launch {
            delay(LIVE_MOVE_MS)
            clearLiveMove()
        }
    }

    private fun clearLiveMove() {
        _liveMove.value = ""
        liveMoveJob?.cancel()
        appContext?.let { com.jarvis.client.service.LiveService.clearMoveOffer(it) }
    }

    /**
     * A reply that was about Live, not a question to answer (VoiceSession's
     * `onLive`): "let's talk" started or refused, "that's all", too short,
     * the words could not be made out, a pause, "move it here?". Only fixed
     * lines are said.
     */
    private fun onLiveReply(heard: com.jarvis.client.net.Heard) {
        val rules = com.jarvis.client.voice.LiveRules
        val reply = rules.reply(heard.liveIn())
        val now = SystemClock.elapsedRealtime()
        when (reply.action) {
            com.jarvis.client.voice.LiveRules.Action.START -> {
                // "Hey Jarvis, let's talk" while App lock would lock the app
                // (or, under "End Live when: Only when the phone's screen
                // locks", while the screen is locked): ended again at once,
                // and nothing is said.
                liveLockEnd(now)?.let { why ->
                    scope.launch { api.liveWrite(rules.stopBody(why)) }
                    return
                }
                scope.launch {
                    chat.startLiveConversation()
                    // Started by voice: the session has no chat yet - this
                    // phone names its fresh one, once, so "Move it here" on
                    // the PC carries it on (the chat audit, 2026-09-28).
                    api.liveWrite(rules.activeBody(chat.conversationIdNow()))
                    liveRead()
                    if (beginLiveHere() && awaitLiveListening()) {
                        voice.sayLine(reply.say)
                    } else {
                        // Android would not let the microphone service start
                        // from the background: said, and ended (the review's B7).
                        liveStop("owner")
                        liveNotice(LIVE_NOT_ALLOWED)
                        voice.sayLine(LIVE_NOT_ALLOWED_SAID)
                    }
                }
            }
            com.jarvis.client.voice.LiveRules.Action.REFUSED -> {
                val why = heard.reason.ifBlank { "Jarvis Live could not start." }
                liveNotice(why)
                // Said aloud, in the PC's fixed words (the review's #7).
                scope.launch { voice.sayLine(why) }
            }
            com.jarvis.client.voice.LiveRules.Action.END -> {
                endLiveHere()
                scope.launch {
                    liveRead()
                    voice.sayLine(reply.say)
                }
            }
            com.jarvis.client.voice.LiveRules.Action.MOVE -> offerLiveMove(heard.liveElsewhere)
            com.jarvis.client.voice.LiveRules.Action.STOP ->
                if (settings.interrupt.value != rules.INTERRUPT_OFF) voice.stopSpeaking()
            com.jarvis.client.voice.LiveRules.Action.SHORT -> {
                _liveFlash.value = LiveFlash(short = true, until = now + LIVE_FLASH_MS)
                scope.launch { voice.sayLine(reply.say) }
            }
            com.jarvis.client.voice.LiveRules.Action.TROUBLE ->
                // The owner's voice, but no words could be made of it: Live
                // carries on (the review's bug 2 - it used to stop the mic).
                _liveFlash.value = LiveFlash(trouble = true, until = now + LIVE_FLASH_MS)
            com.jarvis.client.voice.LiveRules.Action.PAUSE,
            com.jarvis.client.voice.LiveRules.Action.LISTEN,
            -> if (reply.say.isNotEmpty()) scope.launch { voice.sayLine(reply.say) }
            com.jarvis.client.voice.LiveRules.Action.ANSWER -> Unit
        }
    }

    /** A tap button: the owner's own words, TYPED - answered on screen, like any typed question. */
    fun liveTap(words: String) {
        voice.clearLiveChips()
        liveType(words)
    }

    /**
     * The Live screen's text box: a typed question, with a typed answer's
     * rules. It keeps Live open. [shared]: text handed over with "Talk about
     * this in Live" (the Share sheet) - sent as its own message, tagged
     * "shared", right before the typed words (or alone): outside text, like
     * any shared item, so the PC treats the chat as having read it.
     */
    fun liveType(words: String, shared: String? = null) {
        val text = words.trim()
        val held = shared?.takeIf { it.isNotBlank() }
        if (text.isEmpty() && held == null) return
        scope.launch {
            // The conversation goes on: the PC's quiet clock starts again
            // (the review's B4 - 90 s of typing used to end Live).
            if (liveOnHere()) api.liveWrite(com.jarvis.client.voice.LiveRules.ACTIVE_BODY)
            chat.send(text, provenance = com.jarvis.client.net.Provenance.TYPED, shared = held)
        }
    }

    /** The microphone service is in the foreground (Android said yes), within a few seconds. */
    private suspend fun awaitLiveListening(): Boolean =
        withTimeoutOrNull(LIVE_LISTEN_WAIT_MS) {
            com.jarvis.client.service.LiveService.listening.first { it }
        } == true

    /** Live is on here: the microphone service and the watcher. False when Android refused the service. */
    private fun beginLiveHere(): Boolean {
        val started = appContext?.let { com.jarvis.client.service.LiveService.start(it) } ?: false
        watchLive()
        return started
    }

    /**
     * Live is over here: the microphone closes, the watcher stops (unless it
     * is the one asking - [cancelWatch] false), and the end tone plays.
     */
    private fun endLiveHere(cancelWatch: Boolean = true) {
        val was = liveOnHere() || liveWatch?.isActive == true
        appContext?.let { com.jarvis.client.service.LiveService.stop(it) }
        voice.clearLiveChips()
        liveCallAsked = null
        liveCallOverridden = false
        liveWarnJob?.cancel()
        if (cancelWatch) liveWatch?.cancel()
        if (was) {
            voice.speaker.playTone(
                com.jarvis.client.voice.HeardSound.samples(com.jarvis.client.voice.LiveRules.END_TONE),
                com.jarvis.client.voice.HeardSound.RATE,
            )
        }
    }

    /**
     * Once a second while Live is on here: the session, the fixed lines when
     * it changed by itself ("Two minutes left...", "Live ended - the time was
     * up."), the link, and App lock. When the link to the PC drops, the phone
     * says so in its own offline voice (the PC's voice cannot reach it); the
     * microphone is closed meanwhile (LiveRules.listen, rule 4). When it
     * comes back with Live still on here, listening starts again and it says
     * "I'm back." (the review's B3); after a long drop it stops trying.
     */
    private fun watchLive() {
        if (liveWatch?.isActive == true) return
        liveWatch = scope.launch {
            var failures = 0
            var wasDown = false
            while (true) {
                delay(if (failures >= LIVE_WATCH_FAILURES) LIVE_WATCH_SLOW_MS else LIVE_WATCH_MS)
                val before = _liveStatus.value
                when (val r = api.liveStatus()) {
                    is ApiResult.Ok -> {
                        failures = 0
                        takeLiveStatus(r.value)
                    }
                    is ApiResult.Failed -> failures += 1
                }
                val now = _liveStatus.value
                val here = com.jarvis.client.voice.LiveRules.onHere(now)
                val down = failures > 0 || _stale.value || _link.value != LinkState.CONNECTED
                if (down && !wasDown && here) {
                    runCatching { voice.speaker.speakOnDevice(com.jarvis.client.voice.LiveRules.LINK_LOST_SAID) }
                }
                if (!down && wasDown && here) {
                    // Back: listening again (the service may have stopped).
                    appContext?.let { com.jarvis.client.service.LiveService.start(it) }
                    voice.sayLine(com.jarvis.client.voice.LiveRules.LINK_BACK_SAID)
                }
                wasDown = down
                if (failures >= LIVE_WATCH_FAILURES) {
                    // Nothing is heard meanwhile; the watcher keeps looking,
                    // more slowly, for a while.
                    appContext?.let { com.jarvis.client.service.LiveService.stop(it) }
                    if (failures >= LIVE_WATCH_GIVE_UP) {
                        endLiveHere(cancelWatch = false)
                        break
                    }
                    continue
                }
                if (!here && failures == 0) {
                    val line = com.jarvis.client.voice.LiveRules.transition(before, now)
                    endLiveHere(cancelWatch = false)
                    // "Live ended - Resume" (the Jarvis Live extras): after an
                    // end here the PC can resume, for the rest of its 10 minutes.
                    com.jarvis.client.voice.LiveExtras.resumeFor(now)?.let { ms ->
                        val words = (now?.get("ended_words") as? JsonPrimitive)?.takeIf { it.isString }?.content.orEmpty()
                        appContext?.let { com.jarvis.client.service.LiveService.showResume(it, words, ms) }
                    }
                    if (line.isNotEmpty()) voice.sayLine(line)
                    break
                }
                if (here) {
                    val line = com.jarvis.client.voice.LiveRules.transition(before, now)
                    if (line.isNotEmpty()) sayLiveLine(line)
                    val lockEnd = liveLockEnd(SystemClock.elapsedRealtime())
                    if (lockEnd != null) {
                        // In its own job: liveStop ends this watcher.
                        scope.launch { liveStop(lockEnd) }
                        break
                    }
                }
            }
        }
    }

    /**
     * Does a lock end Live on this phone now - "app_lock", "screen_lock" or
     * null ([com.jarvis.client.data.SecurityRules.liveEndsNow], the Security
     * screen's "End Live when"; the owner's decision of 2026-09-28).
     */
    private fun liveLockEnd(nowMs: Long): String? {
        val security = settings.security.value
        return com.jarvis.client.data.SecurityRules.liveEndsNow(
            security,
            appLockWouldLock = appLockWouldLock(nowMs, security),
            screenLocked = screenLocked(),
        )
    }

    /** The phone's own screen lock is on (a PIN, pattern or password is needed to get in). */
    private fun screenLocked(): Boolean =
        (appContext?.getSystemService(Context.KEYGUARD_SERVICE) as? android.app.KeyguardManager)
            ?.isDeviceLocked == true

    /**
     * A fixed line while Live runs. "Two minutes left..." used to be skipped
     * when Jarvis was talking (the review's #3): it waits for the answer to
     * end, for up to a minute.
     */
    private suspend fun sayLiveLine(line: String) {
        if (voice.sayLine(line)) return
        liveWarnJob?.cancel()
        liveWarnJob = scope.launch {
            repeat(LIVE_LINE_RETRIES) {
                delay(1000)
                if (!liveOnHere()) return@launch
                if (voice.sayLine(line)) return@launch
            }
        }
    }

    private const val LIVE_MISSING = "This PC's Jarvis does not have Jarvis Live yet. Run " +
        "scripts\\apply-patches.ps1 on the PC to add it."
    private const val LIVE_NOT_ALLOWED = "Android did not let Jarvis Live listen from the background. " +
        "Open Jarvis, then start Live from the Live screen."
    private const val LIVE_NOT_ALLOWED_SAID = "Open Jarvis to start Live."
    private const val LIVE_WATCH_MS = 1000L

    /** How often a captured notification asks the PC for its switch again, at most. */
    private const val PHONE_NOTIFICATIONS_RECHECK_MS = 15_000L
    private const val LIVE_WATCH_SLOW_MS = 5000L
    private const val LIVE_WATCH_FAILURES = 10
    private const val LIVE_WATCH_GIVE_UP = 10 + 120 // about ten more minutes, every 5 s
    private const val LIVE_CALL_ASK_MS = 3000L
    private const val LIVE_FLASH_MS = 6000L
    private const val LIVE_NOTICE_MS = 30_000L
    private const val LIVE_MOVE_MS = 30_000L
    private const val LIVE_STOP_RETRIES = 12
    private const val LIVE_STOP_RETRY_MS = 5000L
    private const val LIVE_LINE_RETRIES = 60
    private const val LIVE_LISTEN_WAIT_MS = 4000L

    /**
     * A "tell me when" cannot look (backend jarvis_tellme.py, 2026-09-28):
     * read its `broken` notice by id and show it - an ordinary notification,
     * never ringing, an urgent watch included (only a real match rings).
     * While App lock or "Hide memory lists and chat history" is on, only the
     * generic words. Once per telling, even when a reconnect replays the event.
     */
    private fun onTellMeBroken(id: String, eventId: String? = null) {
        val context = appContext ?: return
        val kind = com.jarvis.client.net.Schedule.TELLME
        flushResumePoint()
        val arrived = System.currentTimeMillis()
        scope.launch {
            val job = when (val r = api.scheduleJob(id)) {
                is ApiResult.Ok -> com.jarvis.client.net.Schedule.parseOne(r.value)
                is ApiResult.Failed -> null
            }
            val key = com.jarvis.client.net.Schedule.shownKey(id, job?.brokenAt, eventId, arrived, "#broken@")
            val fresh = synchronized(scheduleShown) {
                if (scheduleShown.size > 500) scheduleShown.clear()
                scheduleShown.add(key)
            }
            if (!fresh) return@launch
            val security = settings.security.value
            val locked = security.appLock || security.privateLists
            val (title, text) = com.jarvis.client.net.Schedule.brokenNotification(job, locked)
            com.jarvis.client.service.ScheduleNotifier.post(
                context, id, kind, title, text, com.jarvis.client.net.Schedule.TELLME_BROKEN_LOCK_SCREEN,
                ring = false,
                key = key,
            )
        }
    }

    // ------------------------------------------------- Focus sessions ----
    // The owner's decision of 2026-09-25 - see [com.jarvis.client.net.Focus]
    // and ui/screens/FocusPlate.kt. A timer plus Quiet; the PC watches which
    // app or site is in front and speaks on the PC only. This phone starts and
    // stops a session and shows the countdown, the counts and the report card.

    private val _focusTick = MutableStateFlow(0)

    /** Goes up on every `focus` event and after every change made from this phone. */
    val focusTick: StateFlow<Int> = _focusTick.asStateFlow()

    /** `GET /api/focus`. A read: never held. */
    suspend fun focus(): ApiResult<JsonObject> = api.focus()

    /**
     * Start a session of [minutes], optionally "on" something. Held on a
     * stale link (rule 4): it makes Jarvis watch. No approval card - the
     * owner asked, and the PC reads only which app or site is in front and
     * keeps only counts (docs/JARVIS-API.md section 31).
     */
    suspend fun focusStart(minutes: Int, on: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Focus.startBody(minutes, on)
            ?: return false to com.jarvis.client.net.Focus.BAD_MINUTES
        return focusPost(com.jarvis.client.net.Focus.START_PATH, body)
    }

    /**
     * ONE thing to the running session: pause, resume, extend or stop.
     * Resume and extend are held on a stale link; pause and stop are let
     * through - they only make Jarvis do less.
     */
    suspend fun focusAct(action: String): Pair<Boolean, String> {
        if (action in com.jarvis.client.net.Focus.HELD_WHEN_STALE) {
            actionBlocker()?.let { return false to it }
        }
        val body = com.jarvis.client.net.Focus.actBody(action)
            ?: return false to "That is not something the phone can do to a focus session."
        return focusPost(com.jarvis.client.net.Focus.ACT_PATH, body)
    }

    private suspend fun focusPost(path: String, body: String): Pair<Boolean, String> =
        when (val r = api.focusWrite(path, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Focus.said(r.value).also {
                _focusTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }

    // ------------------------------------------ Talk to a chatbot for me ----
    // The owner's decisions of 2026-09-27 and 2026-09-28 - see
    // [com.jarvis.client.net.Chatbot] and ui/screens/ChatbotPlate.kt. Jarvis
    // asks an AI chatbot about something for the owner, within limits
    // approved on ONE card on the PC. This phone starts one, shows it, pauses,
    // resumes and stops it, asks for new limits, and keeps an ongoing
    // notification while one is going (service/ChatbotNotifier.kt).

    private val _chatbotTick = MutableStateFlow(0)

    /**
     * Goes up while a conversation is going (every [Chatbot.POLL_MS], from
     * [watchChatbot]) and after every change made from this phone, so Brain's
     * "Talk to a chatbot for me" reads itself again.
     */
    val chatbotTick: StateFlow<Int> = _chatbotTick.asStateFlow()

    /** The last conversation this phone showed or started, so its summary stays after it ends. */
    @Volatile var chatbotLastId: String? = null

    /** The last comparison this phone showed or started ("Ask several and compare"), likewise. */
    @Volatile var chatbotLastCompareId: String? = null

    private var chatbotWatcher: kotlinx.coroutines.Job? = null

    /** `GET /api/chatbot/status` - the one [id] names, or the latest still going. A read. */
    suspend fun chatbotStatus(id: String?): ApiResult<JsonObject> =
        api.chatbotStatus(id).onOk { noteHandoff(it) }

    /** `GET /api/chatbot/status?compare=` - the comparison [id] names. A read. */
    suspend fun chatbotCompareStatus(id: String): ApiResult<JsonObject> = api.chatbotStatus(null, id)

    /**
     * "Ask several and compare": the PC raises ONE approval card listing every
     * chatbot, and nothing is sent before a yes. Held on a stale link (rule 4).
     */
    suspend fun chatbotCompareStart(
        chatbots: List<String>,
        goal: String,
        maxMessages: Int?,
        maxMinutes: Int?,
        never: List<String>,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Chatbot.compareBody(chatbots, goal, maxMessages, maxMinutes, never)
            ?: return false to "That cannot be sent: check the chatbots, the goal and the never-send words."
        return when (val r = api.chatbotWrite(com.jarvis.client.net.Chatbot.COMPARE_START_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Chatbot.said(r.value).also { (ok, _) ->
                if (ok) {
                    val id = (r.value.body?.get("compare") as? kotlinx.serialization.json.JsonPrimitive)
                        ?.takeIf { it.isString }?.content
                    if (id != null) chatbotLastCompareId = id
                    watchChatbot()
                }
                _chatbotTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not started. " + describe(r.error))
        }
    }

    /** Stop the whole comparison. Never held, never a card: it only makes Jarvis do less. */
    suspend fun chatbotCompareStop(id: String): Pair<Boolean, String> {
        val body = com.jarvis.client.net.Chatbot.compareStopBody(id)
            ?: return false to "That is not a comparison this phone knows."
        return chatbotPost(com.jarvis.client.net.Chatbot.COMPARE_STOP_PATH, body)
    }

    /**
     * Ask the PC for a conversation: it raises ONE approval card, and nothing
     * is sent before a yes. Held on a stale link (rule 4).
     */
    suspend fun chatbotStart(
        chatbot: String,
        goal: String,
        maxMessages: Int?,
        maxMinutes: Int?,
        never: List<String>,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Chatbot.startBody(chatbot, goal, maxMessages, maxMinutes, never)
            ?: return false to "That cannot be sent: check the goal and the never-send words."
        return when (val r = api.chatbotWrite(com.jarvis.client.net.Chatbot.START_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Chatbot.said(r.value).also { (ok, _) ->
                if (ok) {
                    val id = (r.value.body?.get("session") as? kotlinx.serialization.json.JsonPrimitive)
                        ?.takeIf { it.isString }?.content
                    if (id != null) chatbotLastId = id
                    watchChatbot()
                }
                _chatbotTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not started. " + describe(r.error))
        }
    }

    /** Stop one conversation. Never held, never a card: it only makes Jarvis do less. */
    suspend fun chatbotStop(id: String): Pair<Boolean, String> {
        val body = com.jarvis.client.net.Chatbot.stopBody(id)
            ?: return false to "That is not a conversation this phone knows."
        return chatbotPost(com.jarvis.client.net.Chatbot.STOP_PATH, body)
    }

    /** New limits: a NEW card on the PC. Held on a stale link. */
    suspend fun chatbotLimits(
        id: String,
        maxMessages: Int?,
        maxMinutes: Int?,
        never: List<String>?,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Chatbot.limitsBody(id, maxMessages, maxMinutes, never)
            ?: return false to "That is not a conversation this phone knows."
        return chatbotPost(com.jarvis.client.net.Chatbot.LIMITS_PATH, body)
    }

    /** Pause: the conversation runs as a task, so this is the task's own Pause. Never held. */
    suspend fun chatbotPause(): Pair<Boolean, String> =
        when (val r = pauseTask()) {
            is ApiResult.Ok -> {
                _chatbotTick.update { n -> n + 1 }
                true to "Pausing. The reply on its way is read first, then it stops."
            }
            is ApiResult.Failed -> false to ("Not paused. " + describe(r.error))
        }

    /** Resume: the task's own Resume, which raises its own card on the PC. Held on a stale link. */
    suspend fun chatbotResume(): Pair<Boolean, String> =
        when (val r = resumeTask()) {
            is ApiResult.Ok -> {
                _chatbotTick.update { n -> n + 1 }
                true to com.jarvis.client.net.TaskControl.RESUME_ASKED
            }
            is ApiResult.Failed -> false to ("Not resumed. " + describe(r.error))
        }

    private suspend fun chatbotPost(path: String, body: String): Pair<Boolean, String> =
        when (val r = api.chatbotWrite(path, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Chatbot.said(r.value).also {
                _chatbotTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }

    /**
     * While a conversation is going: read it every [Chatbot.POLL_MS], keep the
     * ongoing notification ("Talking to Gemini, 3 of 5" with Stop) in step,
     * and tick [chatbotTick]. Ends - and takes the notification away - once
     * nothing is going, or after the PC could not be read five times running
     * (a Stop that cannot reach the PC is no use; an activity event or the
     * plate starts it again). One watcher at a time.
     */
    fun watchChatbot() {
        if (chatbotWatcher?.isActive == true) return
        chatbotWatcher = scope.launch {
            var misses = 0
            while (true) {
                val r = api.chatbotStatus(null)
                val ctx = appContext
                if (r is ApiResult.Ok) {
                    misses = 0
                    // "Solve it here": a page waiting for the owner.
                    noteHandoff(r.value)
                    val v = com.jarvis.client.net.Chatbot.parse(r.value)
                    val s = v?.session
                    val c = v?.compare
                    if (s != null && s.live) {
                        chatbotLastId = s.id
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.post(ctx, s)
                    } else if (c != null && c.live) {
                        // "Ask several and compare": the same line, for the whole comparison.
                        chatbotLastCompareId = c.id
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.postCompare(ctx, c)
                    } else {
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.cancel(ctx)
                        _chatbotTick.update { n -> n + 1 }
                        break
                    }
                } else {
                    misses += 1
                    if (misses >= 5) {
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.cancel(ctx)
                        break
                    }
                }
                _chatbotTick.update { n -> n + 1 }
                kotlinx.coroutines.delay(com.jarvis.client.net.Chatbot.POLL_MS)
            }
        }
    }

    // ------------------------------- Chat with customer support for me ----
    // The owner's decisions of 2026-09-28 - see [com.jarvis.client.net.Support]
    // and ui/screens/SupportPlate.kt. Jarvis chats with a company's customer
    // support in the owner's name, on the PC; ONE card lists every detail it
    // may give, and every offer gets its own card. This phone starts one,
    // shows it, takes over, resumes (the task's own card) and stops it, and
    // answers a waiting offer with Decline or "Say something else" - never
    // Accept (that is only ever the offer's card). It keeps an ongoing
    // notification while one is going (service/ChatbotNotifier.postSupport).

    private val _supportTick = MutableStateFlow(0)

    /** Goes up while a support chat is going, and after every change from this phone. */
    val supportTick: StateFlow<Int> = _supportTick.asStateFlow()

    /** The last support chat this phone showed or started, so its end stays on screen. */
    @Volatile var supportLastId: String? = null

    private var supportWatcher: kotlinx.coroutines.Job? = null

    /** `GET /api/chatbot/status?support=` - the one [id] names, or the latest going. A read. */
    suspend fun supportStatus(id: String?): ApiResult<JsonObject> =
        api.supportStatus(id).onOk { noteHandoff(it) }

    /** Ask the PC for a support chat: ONE approval card. Held on a stale link (rule 4). */
    suspend fun supportStart(
        company: String,
        address: String?,
        goal: String,
        rows: List<com.jarvis.client.net.Support.Detail>,
        maxMessages: Int?,
        maxMinutes: Int?,
        maxQueueMinutes: Int?,
    ): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Support.startBody(company, address, goal, rows, maxMessages,
            maxMinutes, maxQueueMinutes)
            ?: return false to "That cannot be sent: check the company, the goal and the details."
        return when (val r = api.supportWrite(com.jarvis.client.net.Support.START_PATH, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Support.said(r.value).also { (ok, _) ->
                if (ok) {
                    val id = (r.value.body?.get("support") as? kotlinx.serialization.json.JsonPrimitive)
                        ?.takeIf { it.isString }?.content
                    if (id != null) supportLastId = id
                    watchSupport()
                }
                _supportTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not started. " + describe(r.error))
        }
    }

    /** Stop a support chat. Never held, never a card: it only makes Jarvis do less. */
    suspend fun supportStop(id: String): Pair<Boolean, String> {
        val body = com.jarvis.client.net.Support.idBody(id)
            ?: return false to "That is not a support chat this phone knows."
        return supportPost(com.jarvis.client.net.Support.STOP_PATH, body)
    }

    /** Take over: Jarvis stops sending. Never held, never a card. */
    suspend fun supportTakeover(id: String): Pair<Boolean, String> {
        val body = com.jarvis.client.net.Support.idBody(id)
            ?: return false to "That is not a support chat this phone knows."
        return supportPost(com.jarvis.client.net.Support.TAKEOVER_PATH, body)
    }

    /**
     * Decline or "Say something else" (both send words: held on a stale link)
     * or Take over (not held) about the waiting offer. Never accept.
     */
    suspend fun supportAnswer(id: String, offer: Int, choice: String, text: String?): Pair<Boolean, String> {
        if (choice != "takeover") actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Support.answerBody(id, offer, choice, text)
            ?: return false to "That cannot be sent."
        return supportPost(com.jarvis.client.net.Support.ANSWER_PATH, body)
    }

    private suspend fun supportPost(path: String, body: String): Pair<Boolean, String> =
        when (val r = api.supportWrite(path, body)) {
            is ApiResult.Ok -> com.jarvis.client.net.Support.said(r.value).also {
                _supportTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }

    /**
     * While a support chat is going: read it every [Support.POLL_MS], keep the
     * ongoing notification ("Chat with Groupon: offer waiting" with Stop) in
     * step, and tick [supportTick]. Ends - and takes the notification away -
     * once nothing is going, or after five failed reads. One watcher at a time.
     */
    fun watchSupport() {
        if (supportWatcher?.isActive == true) return
        supportWatcher = scope.launch {
            var misses = 0
            while (true) {
                val r = api.supportStatus(null)
                val ctx = appContext
                if (r is ApiResult.Ok) {
                    misses = 0
                    noteHandoff(r.value)
                    val c = com.jarvis.client.net.Support.parse(r.value)?.chat
                    if (c != null && c.live) {
                        supportLastId = c.id
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.postSupport(ctx, c)
                    } else {
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.cancelSupport(ctx)
                        _supportTick.update { n -> n + 1 }
                        break
                    }
                } else {
                    misses += 1
                    if (misses >= 5) {
                        if (ctx != null) com.jarvis.client.service.ChatbotNotifier.cancelSupport(ctx)
                        break
                    }
                }
                _supportTick.update { n -> n + 1 }
                kotlinx.coroutines.delay(com.jarvis.client.net.Support.POLL_MS)
            }
        }
    }

    // ----------------------------------------------------- Solve it here ----
    // The owner's decision of 2026-09-28 - see [com.jarvis.client.net.Handoff],
    // service/HandoffNotifier.kt and ui/screens/HandoffScreen.kt. A chatbot
    // website or a support chat paused at a captcha, a sign-in page or an
    // "unusual activity" page: an alert (site and reason only; generic under
    // App lock), and "Solve it here" - a live picture of that one browser
    // window and the owner's own taps and typing to it, only while Jarvis is
    // paused there (the PC checks that on every picture and every input).

    private val _handoffOffer = MutableStateFlow<com.jarvis.client.net.Handoff.Offer?>(null)

    /** The page waiting for the owner, as last read with a chatbot or support status. */
    val handoffOffer: StateFlow<com.jarvis.client.net.Handoff.Offer?> = _handoffOffer.asStateFlow()

    /** The alert already raised, so one pause alerts once. */
    @Volatile private var handoffAlerted: String? = null

    private val _handoffOpen = MutableStateFlow(false)

    /**
     * True when a Brain plate's "Solve it here" was tapped and the screen is
     * not open yet: MainActivity opens it and calls [handoffOpened].
     */
    val handoffOpen: StateFlow<Boolean> = _handoffOpen.asStateFlow()

    fun openHandoff() {
        _handoffOpen.value = true
    }

    fun handoffOpened() {
        _handoffOpen.value = false
    }

    /** The hand-off this phone started and has not ended, so a rotation keeps it. */
    @Volatile var handoffActive: String? = null
        private set

    /**
     * A chatbot or support status was read: alert once for a page newly
     * waiting for the owner, take the alert away once nothing waits.
     */
    private fun noteHandoff(status: JsonObject?) {
        val o = com.jarvis.client.net.Handoff.offer(status)
        _handoffOffer.value = o
        val ctx = appContext ?: return
        if (o == null) {
            if (handoffAlerted != null) com.jarvis.client.service.HandoffNotifier.cancel(ctx)
            handoffAlerted = null
            return
        }
        if (handoffAlerted == o.key) return
        handoffAlerted = o.key
        val security = settings.security.value
        com.jarvis.client.service.HandoffNotifier.post(ctx, o, locked = security.appLock || security.privateLists)
    }

    /**
     * "Solve it here": start passing that one window on. No card - nothing
     * leaves the owner's own devices - but not on a stale link: the picture
     * would be old and every input held anyway. The hand-off id, or why not.
     */
    suspend fun handoffStart(o: com.jarvis.client.net.Handoff.Offer): Pair<String?, String?> {
        actionBlocker()?.let { return null to it }
        val body = com.jarvis.client.net.Handoff.startBody(o)
            ?: return null to "That is not a page this phone knows."
        return when (val r = api.handoffWrite(com.jarvis.client.net.Handoff.START_PATH, body)) {
            is ApiResult.Ok -> {
                val h = (r.value.body?.get("handoff") as? JsonPrimitive)?.takeIf { it.isString }?.content
                if (r.value.code in 200..299 && com.jarvis.client.net.Handoff.validHid(h)) {
                    handoffActive = h
                    h to null
                } else {
                    null to ((r.value.body?.get("error") as? JsonPrimitive)?.content
                        ?: "Your PC did not start it. Try again.")
                }
            }
            is ApiResult.Failed -> null to describe(r.error)
        }
    }

    /** One picture of that window, kept by the screen that asked only. A read: never held. */
    suspend fun handoffFrame(h: String): com.jarvis.client.net.Handoff.Answer =
        when (val r = api.handoffFrame(h)) {
            is ApiResult.Ok -> com.jarvis.client.net.Handoff.answer(r.value.code, r.value.body).also {
                if (it is com.jarvis.client.net.Handoff.Answer.Ended && handoffActive == h) handoffActive = null
            }
            is ApiResult.Failed -> com.jarvis.client.net.Handoff.Answer.Failed(describe(r.error))
        }

    /**
     * One input from the owner (a body made by [com.jarvis.client.net.Handoff]).
     * Held on a stale link (rule 4). Null when it reached the page; else the
     * answer the screen shows.
     */
    suspend fun handoffInput(body: String?): com.jarvis.client.net.Handoff.Answer? {
        com.jarvis.client.net.Handoff.inputHeld(_stale.value || _link.value != LinkState.CONNECTED)?.let {
            return com.jarvis.client.net.Handoff.Answer.Failed(it)
        }
        if (body == null) return com.jarvis.client.net.Handoff.Answer.Failed("That cannot be passed on.")
        return when (val r = api.handoffWrite(com.jarvis.client.net.Handoff.INPUT_PATH, body)) {
            is ApiResult.Ok ->
                if (r.value.code in 200..299) {
                    null
                } else {
                    com.jarvis.client.net.Handoff.answer(r.value.code, r.value.body)
                }
            is ApiResult.Failed -> com.jarvis.client.net.Handoff.Answer.Failed(describe(r.error))
        }
    }

    /**
     * End the hand-off. Never held, never a card; in the runtime's own scope
     * so leaving the screen cannot lose it.
     */
    fun handoffEnd(h: String) {
        if (handoffActive == h) handoffActive = null
        val body = com.jarvis.client.net.Handoff.endBody(h) ?: return
        scope.launch { api.handoffWrite(com.jarvis.client.net.Handoff.END_PATH, body) }
    }

    // ------------------------------------------------ Morning briefing ----
    // The owner's decisions of 2026-09-25 - see [com.jarvis.client.net.Briefing]
    // and ui/screens/BriefingPlate.kt. Put together on the PC without the AI
    // model; this phone shows it, asks for one now, and sets one up.

    private val _briefingTick = MutableStateFlow(0)

    /**
     * Goes up by one on every `schedule` event about a briefing and after
     * every change made from this phone, so Mind's "Morning briefing" reads
     * itself again.
     */
    val briefingTick: StateFlow<Int> = _briefingTick.asStateFlow()

    /** The briefing runs already announced, by id and when they went off. */
    private val briefingShown = LinkedHashSet<String>()

    /** `GET /api/briefing`. A read: never held. */
    suspend fun briefing(): ApiResult<JsonObject> = api.briefing()

    /**
     * "Brief me now": one put together on the PC now. It only reads - no
     * card, nothing changes - so, like every read, it is not held on a stale
     * link (the desktop's `brain_briefing_now` is not either).
     */
    suspend fun briefingNow(): ApiResult<JsonObject> = api.briefingNow()

    /**
     * "What did I miss?" - the briefing's builder on the PC, since the owner
     * last talked to Jarvis on either app. A read, like "Brief me now", so
     * not held on a stale link (the desktop's `brain_briefing_now` with
     * `missed`).
     */
    suspend fun briefingMissed(): ApiResult<JsonObject> = api.briefingNow(missed = true)

    /**
     * Set up ONE briefing that repeats. It approves nothing: the PC raises
     * the scheduler's ONE approval card listing the next three times, and
     * nothing is set up before a yes. Held on a stale link (rule 4), like the
     * desktop's `set_briefing`. @return whether it was asked, and the
     * sentence to show.
     */
    suspend fun setBriefing(every: String, at: String, days: Collection<Int>): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        val body = com.jarvis.client.net.Briefing.setupBody(every, at, days)
            ?: return false to (if (every == "week") "Pick at least one day and a time." else "Pick a time.")
        return when (val r = api.scheduleWrite(com.jarvis.client.net.Schedule.ADD_PATH, body)) {
            is ApiResult.Ok -> {
                _briefingTick.update { n -> n + 1 }
                _scheduleTick.update { n -> n + 1 }
                val (asked, said) = com.jarvis.client.net.Schedule.said(r.value)
                asked to (if (asked) com.jarvis.client.net.Briefing.ASKED else said)
            }
            is ApiResult.Failed -> false to ("Not set up. " + describe(r.error))
        }
    }

    /**
     * "Show who new emails are from" in the morning briefing - the desktop's
     * `set_briefing_senders`. ON is held on a stale link (rule 4) and raises
     * ONE approval card on the PC; OFF is never held - it only shows less.
     * @return the sentence to show.
     */
    suspend fun setBriefingSenders(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        val r = writeNoticingCards { api.setBriefingSenders(on) }
        _briefingTick.update { n -> n + 1 }
        return when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.Briefing.sendersSaid(on, r.value)
            is ApiResult.Failed ->
                if (r.error == ApiError.NotFound) {
                    com.jarvis.client.net.Briefing.SENDERS_MISSING
                } else {
                    "Not changed. " + describe(r.error)
                }
        }
    }

    /** Stop ONE briefing, at once, no card. Held on a stale link, like every change. */
    suspend fun stopBriefing(id: String): Pair<Boolean, String> =
        scheduleAct(id, "delete").also { _briefingTick.update { n -> n + 1 } }

    private fun onBriefingReady(id: String, eventId: String? = null) {
        val context = appContext ?: return
        val arrived = System.currentTimeMillis()
        scope.launch {
            val job = when (val r = api.scheduleJob(id)) {
                is ApiResult.Ok -> com.jarvis.client.net.Schedule.parseOne(r.value)
                is ApiResult.Failed -> null
            }
            // Once per run: a replayed event after a reconnect must not ring
            // twice - and an unreadable job is told apart by its event.
            val key = com.jarvis.client.net.Schedule.shownKey(id, job?.firedAt, eventId, arrived)
            val fresh = synchronized(briefingShown) {
                if (briefingShown.size > 200) briefingShown.clear()
                briefingShown.add(key)
            }
            if (!fresh) return@launch
            // The fixed words only - on the lock screen AND inside it, whatever
            // the privacy settings: the briefing itself is read in the app.
            val words = com.jarvis.client.net.Briefing.LOCK_SCREEN
            com.jarvis.client.service.ScheduleNotifier.post(
                context, id, com.jarvis.client.net.Briefing.KIND,
                com.jarvis.client.net.Briefing.TITLE, words, words, openBriefing = true,
            )
        }
    }

    /**
     * The overnight-tidy card's "Not now" (since 2026-09-25): tell the PC,
     * which keeps the offer quiet for a day, then a week, then a month
     * (jarvis_backoff.py). Not held on a stale link - it only makes Jarvis
     * quieter - and nothing is shown if it fails: the card is dismissed here
     * either way and may simply come back tomorrow, as it did before.
     */
    suspend fun sleepNotNow() {
        if (_link.value != LinkState.CONNECTED) return
        api.setSleepTime(notNow = true)
    }

    // ------------------------------------------ "Always keep in mind" ----
    // The owner's decision of 2026-09-24 - see
    // [com.jarvis.client.net.MemoryProfile] and ui/screens/ProfilePlate.kt.

    private val _profileTick = MutableStateFlow(0)

    /**
     * Goes up by one whenever the list may have changed from this phone - a
     * pin, an unpin, a Forget or an erase - so Mind's "Always keep in mind"
     * reads itself again. There is no event for it (Forget and Erase send
     * none either): the desktop's change shows on the next read, Refresh.
     */
    val profileTick: StateFlow<Int> = _profileTick.asStateFlow()

    private val _pinnedIds = MutableStateFlow<Set<Long>?>(null)

    /**
     * The ids on the list at the last read, or null before one (or on a PC
     * without the list) - what "Saved automatically" reads to say Pin or
     * Unpin. Ids only: the words stay on the PC and in the section drawing
     * them.
     */
    val pinnedIds: StateFlow<Set<Long>?> = _pinnedIds.asStateFlow()

    /** `GET /api/memory/profile`. A read: never held. Notes the ids ([pinnedIds]). */
    suspend fun memoryProfile(): ApiResult<JsonObject> {
        val r = api.memoryProfile()
        _pinnedIds.value = when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryProfile.parse(r.value)?.ids
            is ApiResult.Failed -> if (com.jarvis.client.net.MemoryProfile.missing(r.error)) null else _pinnedIds.value
        }
        return r
    }

    /**
     * Pins (`pinned = true`) or unpins ONE fact on "Always keep in mind". No
     * card and no confirm - the owner's own tap on a fact they can see - but
     * held on a stale link (rule 4), exactly like [forgetAutoFact] and the
     * desktop's `brain_memory_pin`. @return whether the list changed as
     * asked, and the sentence to show.
     */
    suspend fun pinFact(id: Long, pinned: Boolean): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return when (val r = api.pinFact(id, pinned)) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryProfile.said(r.value, pinned).also {
                _profileTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }
    }

    // ------------------------------------------------------- "Between us" ----
    // The owner's decision of 2026-09-27 - see
    // [com.jarvis.client.net.MemoryShared] and ui/screens/SharedPlate.kt.

    private val _sharedTick = MutableStateFlow(0)

    /**
     * Goes up by one whenever the list may have changed from this phone - a
     * tag, an untag or a Forget - so Brain's "Between us" reads itself
     * again. There is no event for it (Forget sends none either): the
     * desktop's change shows on the next read, Refresh.
     */
    val sharedTick: StateFlow<Int> = _sharedTick.asStateFlow()

    private val _sharedIds = MutableStateFlow<Set<Long>?>(null)

    /**
     * The ids on the list at the last read, or null before one (or on a PC
     * without the list) - what "Saved automatically" reads to say "Between
     * us" or "Not between us". Ids only: the words stay on the PC and in
     * the section drawing them.
     */
    val sharedIds: StateFlow<Set<Long>?> = _sharedIds.asStateFlow()

    /** `GET /api/memory/shared`. A read: never held. Notes the ids ([sharedIds]). */
    suspend fun memoryShared(): ApiResult<JsonObject> {
        val r = api.memoryShared()
        _sharedIds.value = when (r) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryShared.parse(r.value)?.ids
            is ApiResult.Failed -> if (com.jarvis.client.net.MemoryShared.missing(r.error)) null else _sharedIds.value
        }
        return r
    }

    /**
     * Tags (`shared = true`) or untags ONE fact "Between us". No card and
     * no confirm - the owner's own tap on a fact they can see - but held
     * on a stale link (rule 4), exactly like [pinFact] and the desktop's
     * `brain_memory_share`. @return whether the list changed as asked, and
     * the sentence to show.
     */
    suspend fun setShared(id: Long, shared: Boolean): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return when (val r = api.setShared(id, shared)) {
            is ApiResult.Ok -> com.jarvis.client.net.MemoryShared.said(r.value, shared).also {
                _sharedTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> false to ("Not changed. " + describe(r.error))
        }
    }

    // -------------------------------------------------------- projects ----
    // docs/JARVIS-API.md section 88 (the owner's decision of 2026-09-28) -
    // see [com.jarvis.client.net.Projects] and ui/screens/ProjectsPlate.kt.
    // The phone reads everything from the PC and keeps none of it.

    private val _projectsTick = MutableStateFlow(0)

    /** Goes up by one after a change from this phone, so Brain's Projects reads itself again. */
    val projectsTick: StateFlow<Int> = _projectsTick.asStateFlow()

    private val _projectsLast = MutableStateFlow<com.jarvis.client.net.Projects.Reply?>(null)

    /** The PC's whole answer to the last Projects change - e.g. a new project's id. */
    val projectsLast: StateFlow<com.jarvis.client.net.Projects.Reply?> = _projectsLast.asStateFlow()

    /** A Projects read (a GET of a [com.jarvis.client.net.Projects] path). Never held. */
    suspend fun projectsRead(path: String): ApiResult<com.jarvis.client.net.Projects.Reply> =
        api.projectsCall(path, null)

    /**
     * ONE change to a project, a benchmark or a number. Held on a stale link
     * (rule 4), like the desktop's `projects_write`, except Shareable OFF
     * ([com.jarvis.client.net.Projects.heldOnStale]). The PC decides what
     * asks first (Shareable ON, taking off Jarvis's own private mark); when
     * it raised a card, the queue is read at once so the card shows here.
     * [quiet] keeps a private number out of the sentence TalkBack reads out.
     */
    suspend fun projectsWrite(
        action: String,
        path: String?,
        json: String,
        done: String,
        quiet: Boolean = false,
        on: Boolean? = null,
    ): com.jarvis.client.net.Projects.Outcome {
        if (com.jarvis.client.net.Projects.heldOnStale(action, on)) {
            actionBlocker()?.let { return com.jarvis.client.net.Projects.Outcome(false, false, it) }
        }
        val target = path ?: return com.jarvis.client.net.Projects.Outcome(false, false, "Not changed.")
        return when (val r = api.projectsCall(target, json)) {
            is ApiResult.Ok -> com.jarvis.client.net.Projects.said(r.value, done, quiet).also {
                if (it.waiting) refreshPending()
                if (it.changed) _projectsTick.update { n -> n + 1 }
                _projectsLast.value = r.value
            }
            is ApiResult.Failed -> com.jarvis.client.net.Projects.Outcome(false, false, "Not changed. " + describe(r.error))
        }
    }

    // ---------------------------------------- activity heatmap and balance ----
    // docs/JARVIS-API.md section 105 (the owner's tick of 2026-09-30) - see
    // [com.jarvis.client.net.Progress] and ui/screens/ProgressPlate.kt. Read
    // when Brain opens and after this phone's own save; nothing is kept, spoken
    // or put in a notification.

    /** The activity heatmap for [weeks] weeks (4..26). A read; never held. */
    suspend fun progressActivity(weeks: Int): ApiResult<com.jarvis.client.net.Progress.Reply> =
        api.progressActivity(weeks)

    /** The balance chart and what can be picked for it. A read; never held. */
    suspend fun progressBalance(): ApiResult<com.jarvis.client.net.Progress.Reply> =
        api.progressBalance()

    /**
     * Saves the balance chart's areas (3 to 8, or none to clear). No card, but
     * held on a stale link (rule 4) and refused while "Hide memory lists and
     * chat history" is on, since the picker's names are hidden then. The PC's
     * own refusal sentence comes back as sent.
     */
    suspend fun progressBalanceSave(json: String): com.jarvis.client.net.Progress.Outcome {
        if (privateListsHidden) {
            return com.jarvis.client.net.Progress.Outcome(false, com.jarvis.client.net.Progress.w("hidden"), null)
        }
        actionBlocker()?.let { return com.jarvis.client.net.Progress.Outcome(false, it, null) }
        return when (val r = api.progressBalanceSave(json)) {
            is ApiResult.Ok -> com.jarvis.client.net.Progress.saved(r.value)
            is ApiResult.Failed -> com.jarvis.client.net.Progress.Outcome(
                false, "Not changed. " + describe(r.error), null,
            )
        }
    }

    // ----------------------------------------------- forget a time frame ----
    // docs/JARVIS-API.md section 64 (the owner's decision of 2026-09-28) -
    // see [com.jarvis.client.net.ForgetRange] and ui/screens/ForgetRangePlate.kt.
    // The phone keeps nothing of the list: it reads it from the PC each time.

    private val _forgetRangeTick = MutableStateFlow(0)

    /** Goes up by one after "Forget these" or Undo from this phone, so the plate reads itself again. */
    val forgetRangeTick: StateFlow<Int> = _forgetRangeTick.asStateFlow()

    /** A read: the status, or the list for some days. Never held. Each read
     *  of the status also tells Home when a card of this phone's was
     *  approved ([forgetRangeSaw]). */
    suspend fun forgetRangeRead(path: String): ApiResult<com.jarvis.client.net.ForgetRange.Reply> =
        api.forgetRangeCall(path, null).also { r ->
            if (r is ApiResult.Ok) forgetRangeSaw(r.value)
        }

    /** The chats on the last card this phone raised, until it is decided. */
    @Volatile private var forgetRangeChats: List<String> = emptyList()

    /** When the PC last ended a "forget" before this card was raised: an ending
     *  no newer than this is not this card's answer. */
    @Volatile private var forgetRangeBase: Double = 0.0

    /**
     * "Forget a time frame" approved: the chats it deleted are gone, and if
     * Home was in one of them its words must stop going to the model (the
     * chat audit, 2026-09-28, phone B2). Read from the PC's own status -
     * `last.outcome` "done" - never guessed from the card leaving the queue.
     */
    private fun forgetRangeSaw(reply: com.jarvis.client.net.ForgetRange.Reply) {
        val pending = forgetRangeChats
        if (pending.isEmpty()) return
        // Null while the card still waits (or this was a list, not a
        // status); once it is decided, only "done" removed anything.
        val outcome = com.jarvis.client.net.ForgetRange.decided(reply, forgetRangeBase) ?: return
        forgetRangeChats = emptyList()
        if (outcome == "done") chatsGone(pending)
    }

    /**
     * "Forget these" (`action` "forget": the PC raises ONE approval card
     * listing every item) or Undo (`action` "undo": no card). "Forget these"
     * is held on a stale link (rule 4), like the desktop's
     * `forget_range_write` - it acts on a list read over a link that cannot
     * be confirmed live. Undo is never held: it only puts back what the
     * owner had a few minutes ago, and holding it could let the ten minutes
     * run out. When a card was raised, the queue is read at once so it
     * shows here.
     */
    suspend fun forgetRangeWrite(action: String, json: String): com.jarvis.client.net.ForgetRange.Outcome {
        val fr = com.jarvis.client.net.ForgetRange
        if (fr.heldOnStale(action)) {
            actionBlocker()?.let { return com.jarvis.client.net.ForgetRange.Outcome(false, false, it) }
        }
        val path = if (action == "undo") fr.UNDO_PATH else fr.PATH
        // Read before the card is raised, so an older ending cannot be mistaken for its answer.
        val before = if (action == "undo") 0.0 else (api.forgetRangeCall(fr.PATH, null) as? ApiResult.Ok)?.let { fr.lastEndedAt(it.value) } ?: 0.0
        return when (val r = api.forgetRangeCall(path, json)) {
            is ApiResult.Ok -> fr.said(r.value, if (action == "undo") "Put back." else fr.w("waiting")).also {
                if (it.waiting) refreshPending()
                // The chats on the card, for Home once it is approved (the
                // chat audit, 2026-09-28): see [forgetRangeSaw].
                if (action != "undo" && it.waiting) {
                    forgetRangeChats = fr.chatsIn(json)
                    forgetRangeBase = before
                }
                _forgetRangeTick.update { n -> n + 1 }
                // Undo put facts back: "Always keep in mind" reads itself again.
                if (action == "undo" && it.done) _profileTick.update { n -> n + 1 }
            }
            is ApiResult.Failed -> com.jarvis.client.net.ForgetRange.Outcome(false, false, "Not done. " + describe(r.error))
        }
    }

    // -------------------------------------------------- inbox tidy ----
    // docs/JARVIS-API.md section 95 (the owner's decision of 2026-09-28) -
    // see [com.jarvis.client.net.InboxTidy] and the Undo strip on Home
    // (ui/screens/HomeScreen.kt, InboxTidyPlate). The tidy itself is asked
    // for in chat and decided on an ordinary approval card; this only shows
    // the ten minutes of Undo the PC keeps, and sends the tap.

    private val _inboxTidy = MutableStateFlow<InboxTidy.Held?>(null)

    /** The PC's last word on the newest tidy still open to Undo, and when it was read. */
    val inboxTidy: StateFlow<InboxTidy.Held?> = _inboxTidy.asStateFlow()

    private val _inboxTidyClock = MutableStateFlow(0L)

    /** Goes up on every poll, so the strip's minutes run down and an Undo that has run out goes. */
    val inboxTidyClock: StateFlow<Long> = _inboxTidyClock.asStateFlow()

    private val _inboxTidyBusy = MutableStateFlow(false)

    /** True while an Undo is on its way, so a second tap cannot send it twice. */
    val inboxTidyBusy: StateFlow<Boolean> = _inboxTidyBusy.asStateFlow()

    /** [inboxTidyUndo], on the runtime's own scope (the screen may go away mid-flight). */
    fun inboxTidyUndoDetached() {
        scope.launch { inboxTidyUndo() }
    }

    /** Re-reads the status. A failed read changes nothing: the last answer keeps aging. */
    suspend fun refreshInboxTidy() {
        when (val r = api.inboxTidyCall(false)) {
            // A 503 from the status route is the PC hitting a passing error, not
            // "no such feature": like a failed read it changes nothing, so an
            // open Undo strip is not wiped for up to 20 seconds (bug audit
            // 2026-09-29; the desktop already keeps it).
            is ApiResult.Ok -> if (r.value.code != 503) {
                _inboxTidy.value = if (InboxTidy.missing(r.value)) {
                    null
                } else {
                    InboxTidy.Held(InboxTidy.parseStatus(r.value.body), SystemClock.elapsedRealtime())
                }
            }
            is ApiResult.Failed -> Unit
        }
        _inboxTidyClock.value = SystemClock.elapsedRealtime()
    }

    /**
     * Undo the newest tidy - one tap, no card. Held on a stale link (rule 4:
     * it acts on the owner's mailbox). The PC's own sentence says what came
     * back; it is shown as the notice, and the strip re-reads itself.
     */
    suspend fun inboxTidyUndo(): InboxTidy.Outcome {
        if (actionBlocker() != null) return InboxTidy.Outcome(false, InboxTidy.w("stale"))
        // While the lists are hidden the strip says only that the inbox was
        // tidied; Undo waits for the unlock (the strip disables the button
        // too - this is the check that does not depend on the screen).
        if (privateListsHidden) return InboxTidy.Outcome(false, InboxTidy.w("locked"))
        if (!_inboxTidyBusy.compareAndSet(false, true)) {
            return InboxTidy.Outcome(false, "Already on its way.")
        }
        try {
            val out = when (val r = api.inboxTidyCall(true)) {
                is ApiResult.Ok -> InboxTidy.undoOutcome(r.value)
                is ApiResult.Failed -> InboxTidy.Outcome(false, "Not undone. " + describe(r.error))
            }
            _notice.value = out.message
            refreshInboxTidy()
            return out
        } finally {
            _inboxTidyBusy.value = false
        }
    }

    /** A few quick reads right after a tidy card was approved on this phone, so the strip shows at once. */
    private fun watchInboxTidyQuickly() {
        scope.launch {
            repeat(6) {
                delay(3_000L)
                runCatching { refreshInboxTidy() }
            }
        }
    }

    // ---------------------------------------------------- chat history ----
    // docs/JARVIS-API.md section 18 (2026-09-24) - see
    // [com.jarvis.client.net.ChatLog] and ui/screens/HistoryScreen.kt. The
    // phone reads all of it from the PC and keeps none of it.

    /** `GET /api/history`, one page, newest first. A read: never held. [kind]:
     *  one kind of conversation ("Live only" and the other filters), or all. */
    suspend fun history(before: Long? = null, kind: String? = null, tag: String? = null): ApiResult<JsonObject> =
        api.history(before, kind, tag)

    // ------------------------------------------------ chat tags ----
    // docs/CHAT-TAGS-DESIGN.md section 10. The tag list and each chat's tag
    // live on the PC; the phone keeps none of it. No approval card.

    /**
     * `GET /api/history/tags`: a read, never held on a stale link. Nothing is
     * asked while the private lists are hidden (tag names are the owner's
     * words, hidden along with titles) - null then, and the screen shows no
     * names. A PC without tags comes back as a NotFound failure.
     */
    suspend fun historyTags(): ApiResult<JsonObject>? {
        if (privateListsHidden) return null
        return api.historyTags()
    }

    /**
     * One change to the tag list (add, rename, style, move, delete): [json] is
     * a body from [com.jarvis.client.net.ChatTags]. Held on a stale link
     * (rule 4), and refused while the lists are hidden.
     */
    suspend fun tagsWrite(json: String): com.jarvis.client.net.ChatTags.Write {
        actionBlocker()?.let { return com.jarvis.client.net.ChatTags.Write(false, it) }
        if (privateListsHidden) return com.jarvis.client.net.ChatTags.Write(false, com.jarvis.client.net.ChatTags.FILED_HIDDEN)
        return tagsPost(com.jarvis.client.net.ChatTags.TAGS_PATH, json)
    }

    /**
     * File ONE chat under a tag, or unfile it with null tag (`POST
     * /api/history/tag`). Held on a stale link; refused while the lists are
     * hidden. Nothing about the chat's words is sent - only its id.
     */
    suspend fun fileChat(chatId: String, tagId: Int?): com.jarvis.client.net.ChatTags.Write {
        actionBlocker()?.let { return com.jarvis.client.net.ChatTags.Write(false, it) }
        if (privateListsHidden) return com.jarvis.client.net.ChatTags.Write(false, com.jarvis.client.net.ChatTags.FILED_HIDDEN)
        if (!com.jarvis.client.net.ChatHistory.validConversationId(chatId)) {
            return com.jarvis.client.net.ChatTags.Write(false, com.jarvis.client.net.ChatTags.errorSentence("not_found"))
        }
        return tagsPost(com.jarvis.client.net.ChatTags.TAG_PATH, com.jarvis.client.net.ChatTags.fileBody(chatId, tagId))
    }

    private suspend fun tagsPost(path: String, json: String): com.jarvis.client.net.ChatTags.Write =
        when (val r = api.tagsPost(path, json)) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatTags.write(r.value.first, r.value.second)
            is ApiResult.Failed -> com.jarvis.client.net.ChatTags.Write(
                false,
                if (r.error == ApiError.NotFound) com.jarvis.client.net.ChatTags.OLD_PC else "Not changed. " + describe(r.error),
            )
        }

    /**
     * "Fork from here" (`POST /api/history/fork`, docs/JARVIS-API.md section
     * 110): a new chat holding turns 0..[upto] of [chatId]. Writes a new chat,
     * so it is held on a stale link (rule 4) and refused while the private
     * lists are hidden. No card. Only the chat's id and the turn's number are
     * sent - none of its words. On success the caller opens the new chat and
     * reads the list again.
     */
    suspend fun forkChat(chatId: String, upto: Int): com.jarvis.client.net.ChatFork.Result {
        actionBlocker()?.let { return com.jarvis.client.net.ChatFork.Result(false, it) }
        if (privateListsHidden) {
            return com.jarvis.client.net.ChatFork.Result(false, com.jarvis.client.net.ChatFork.HIDDEN)
        }
        if (!com.jarvis.client.net.ChatHistory.validConversationId(chatId) || upto < 0) {
            return com.jarvis.client.net.ChatFork.Result(false, com.jarvis.client.net.ChatFork.errorSentence("bad_request"))
        }
        return when (val r = api.forkPost(com.jarvis.client.net.ChatFork.body(chatId, upto))) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatFork.result(r.value.second)
            is ApiResult.Failed -> com.jarvis.client.net.ChatFork.Result(
                false,
                if (r.error == ApiError.NotFound) {
                    com.jarvis.client.net.ChatFork.ERROR_FALLBACK
                } else {
                    "The chat was not forked. " + describe(r.error)
                },
            )
        }
    }

    /** The chat Home is in, when it was kept on the PC (so History can say "this is the one you are in"). */
    fun homeKeptChatId(): String? = if (chat.hasKeptChat()) chat.conversationIdNow() else null

    /** Home's quiet line about the chat itself ([com.jarvis.client.net.ChatSession.chatNote]). */
    val chatNote: StateFlow<String?> get() = chat.chatNote

    /**
     * "Continue this chat" from History (the owner's decision, 2026-09-28):
     * Home carries the conversation on - the same conversation id, the
     * newest kept messages that fit today's re-send limit, its "read outside
     * text" mark carried over by the PC. Null when it was carried on (Home
     * says so), or why not in words. A support record, a chat with another
     * AI or a comparison is never carried on; a temporary chat is never in
     * History to begin with, and turning to a kept chat turns Temporary off.
     */
    suspend fun continueChat(id: String): String? {
        val words = com.jarvis.client.net.ChatHistory
        if (chat.streaming.value) return words.CONTINUE_BUSY
        // A Live session files its words in its own chat: another one cannot be
        // carried on under it.
        if (liveOnHere()) return words.CONTINUE_LIVE
        if (!words.validConversationId(id)) return words.CONTINUE_INVALID
        val t = when (val r = api.historyConversation(id)) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatLog.transcript(r.value)
                ?: return "Your PC sent something this app could not read."
            is ApiResult.Failed -> return com.jarvis.client.net.ChatLog.failure(r.error) ?: noticeFor(r.error)
        }
        if (!t.continuable) return t.continueWhy ?: com.jarvis.client.net.ChatLog.CONTINUE_WHY.getValue("support")
        val got = words.continueWindow(t.turns)
        val window = got.window
        val lines = mutableListOf(words.continuedLine(t.title))
        if (window.isEmpty()) lines += words.CONTINUED_NOTHING
        if (got.skipped > 0 && window.isNotEmpty()) lines += words.continuedSkipped(got.skipped)
        if (got.trimmed) lines += words.continuedTrimmed(got.trimmedCount)
        if (t.tainted) lines += words.CONTINUED_TAINTED
        if (chat.temporary.value) {
            chat.setTemporary(false)
            lines += words.CONTINUED_TEMPORARY_OFF
        }
        // History off (or unable to keep anything): the chat carries on, but
        // what is said now is not kept (the owner, 2026-09-29).
        words.continuedHistoryLine(t.keeping)?.let { lines += it }
        return if (chat.continueFrom(id, window, lines.joinToString(" "), readOutside = t.tainted)) null else words.CHAT_GONE
    }

    /**
     * Chats deleted from this phone (Delete in History, "Erase the words"
     * with its chat, "Forget a time frame" approved): if Home is in one of
     * them, a new conversation starts and Home says so (the chat audit,
     * 2026-09-28, phone B2).
     */
    fun chatsGone(ids: Collection<String>) {
        if (ids.isNotEmpty()) chat.chatsGone(ids)
    }

    /**
     * After something deleted chats the phone could not name (a shorter
     * "keep for" limit, an erase whose chat the phone did not know): if the
     * chat Home is in was kept and the PC no longer has it, Home starts a new
     * conversation and says so. A read; anything but a clear "not found" leaves Home alone.
     */
    private suspend fun homeChatGoneIfMissing() {
        if (!chat.hasKeptChat()) return
        val cid = chat.conversationIdNow()
        val again = api.historyConversation(cid)
        if (again is ApiResult.Failed && again.error == ApiError.NotFound) chatsGone(listOf(cid))
    }

    /**
     * Which chat a fact came from (`GET /api/memory/fact-chat`), for "Also
     * delete the chat it came from": [Pair.first] false from a PC that
     * cannot say (the checkbox then asks as before, without naming one);
     * [Pair.second] the chat, or null when none is on record.
     */
    suspend fun factChat(id: Long): Pair<Boolean, com.jarvis.client.net.ChatLog.FactChat?> {
        val path = com.jarvis.client.net.ChatLog.factChatPath(id) ?: return false to null
        return when (val r = api.factChat(path)) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatLog.factChat(r.value)
            is ApiResult.Failed -> false to null
        }
    }

    /** `GET /api/history/conversation` - one conversation, read-only. */
    suspend fun historyConversation(id: String): ApiResult<JsonObject> = api.historyConversation(id)

    /**
     * "Search what was said" (docs/JARVIS-API.md section 71): a read, never
     * held. The words go to the PC for this one search and are not kept -
     * not here, not there. Null when there is nothing worth sending (fewer
     * than two letters, or too long): the screen then filters titles.
     */
    suspend fun historySearch(query: String, kind: String? = null): ApiResult<JsonObject>? {
        val path = com.jarvis.client.net.ChatLog.searchPath(query, kind = kind) ?: return null
        return api.historySearch(path)
    }

    /**
     * The chat history switch - the same shape as [setLearning]. ON is held
     * on a stale link (rule 4) and raises an approval card on the PC; OFF is
     * never held - it only stops something. @return the sentence to show.
     */
    suspend fun setHistory(on: Boolean): String {
        if (on) actionBlocker()?.let { return it }
        return when (val r = writeNoticingCards { api.setHistory(on) }) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatLog.enableSaid(on, r.value)
            is ApiResult.Failed -> "Not changed. " +
                (com.jarvis.client.net.ChatLog.failure(r.error) ?: describe(r.error))
        }
    }

    /**
     * "Delete conversations older than". Held on a stale link (rule 4), the
     * same as the desktop: a shorter limit deletes at once, cannot be
     * undone, and was chosen from a list this phone may not have seen the
     * latest of. @return the sentence to show.
     */
    suspend fun setHistoryKeepDays(days: Int): String {
        actionBlocker()?.let { return it }
        val body = com.jarvis.client.net.ChatLog.keepDaysBody(days)
            ?: return "Not changed. Pick Never, 30 days, 90 days or 1 year."
        return when (val r = api.setHistoryKeepDays(body)) {
            is ApiResult.Ok -> {
                // A shorter limit deletes at once: if Home's chat was one of them,
                // its words must stop going to the model (the second chat audit).
                val deleted = (r.value["deleted"] as? JsonPrimitive)?.content?.toLongOrNull() ?: 0L
                if (deleted > 0) homeChatGoneIfMissing()
                com.jarvis.client.net.ChatLog.keepSaid(days, r.value)
            }
            is ApiResult.Failed -> "Not changed. " +
                (com.jarvis.client.net.ChatLog.failure(r.error) ?: describe(r.error))
        }
    }

    /**
     * "Facts this chat taught" (docs/JARVIS-API.md section 79): a read, never
     * held - it changes nothing. History, and so this, is not shown while
     * "Hide memory lists and chat history" hides the lists. An older PC
     * (404/501), no link, or anything odd is `available = false`: Delete then
     * asks exactly as it always did. Forgetting a ticked fact is
     * [forgetAutoFact], one fact per call.
     */
    suspend fun chatFacts(conversationId: String): com.jarvis.client.net.ChatLog.Taught {
        val none = com.jarvis.client.net.ChatLog.Taught(available = false, facts = emptyList())
        val path = com.jarvis.client.net.ChatLog.factsPath(conversationId) ?: return none
        return when (val r = api.conversationFacts(path)) {
            is ApiResult.Ok -> com.jarvis.client.net.ChatLog.taught(r.value)
            is ApiResult.Failed -> none
        }
    }

    /**
     * Deletes ONE conversation from the PC, after the History screen's
     * confirm. Held on a stale link (rule 4), the same as the desktop's
     * History and its Forget: it cannot be undone, and it acts on a list read
     * over a link that cannot be confirmed live. One already gone counts as
     * deleted. @return whether it is gone now, and the sentence to show.
     */
    suspend fun deleteHistory(id: String): Pair<Boolean, String> {
        actionBlocker()?.let { return false to it }
        return when (val r = api.deleteHistory(id)) {
            // The chat Home is in, deleted: a new conversation, said on Home.
            is ApiResult.Ok -> com.jarvis.client.net.ChatLog.deleteSaid(r.value).also { (gone, _) ->
                if (gone) chatsGone(listOf(id))
            }
            is ApiResult.Failed -> if (r.error == ApiError.NotFound) {
                true to com.jarvis.client.net.ChatLog.ALREADY_GONE
            } else {
                false to "Not deleted. " + describe(r.error)
            }
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
        LinkWords.decisionBlocked(_link.value, _stale.value)?.let { blocker ->
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
        LinkWords.decisionBlocked(_link.value, _stale.value)?.let { blocker ->
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
        // Turning the overnight tidy OFF only makes Jarvis ask less (no more
        // nightly cards), so, like "Not now", it is not held on a stale link
        // (2026-09-28; the desktop's brain_memory_sleep_time agrees). It
        // still needs the PC to be connected at all.
        val offOnly = enabled == false && remind == null
        (if (offOnly && _link.value == LinkState.CONNECTED) null
        else LinkWords.decisionBlocked(_link.value, _stale.value))?.let { blocker ->
            _notice.value = blocker
            return ApiResult.Failed(ApiError.Unreachable(blocker))
        }
        val result = api.setSleepTime(enabled, remind)
        when (result) {
            is ApiResult.Ok -> {
                // What turning the overnight tidy on says (2026-09-28): it
                // only asks, with review cards - the desktop's toast.
                if (enabled == true) _notice.value = com.jarvis.client.net.MemoryWords.OVERNIGHT_ON_SAID
                refreshBrain()
            }
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

    /**
     * Works out the face and whether Jarvis is out of reach, and publishes
     * both. @return how long until that answer changes by itself (the rest
     * of the reconnect grace), or 0.
     *
     * A cut link - down, or up but stale - shows the STANDBY pose with the
     * offline ring once it has lasted [com.jarvis.client.face.FaceLink.GRACE_MS]
     * (the owner's decision, 2026-09-28; the rules and the reasons are
     * FaceLink's). It used to go to the reversed ERROR motion after the
     * grace and to BANKED after three minutes - which TalkBack read as
     * "notes saved for later", about a PC nobody could hear.
     *
     * The grace itself is kept: a dropped radio on a train is not Jarvis
     * going away, and inside it the face holds whatever it was doing while
     * the link bar says "Reconnecting" in words - except an approval face,
     * which goes at once, since its buttons are already blocked (rule 4).
     * Timed from when the link dropped, not from which enum it is in: the
     * stream reports OFFLINE from the second retry onward and is still
     * retrying.
     */
    private fun publishFace(nowMs: Long = System.currentTimeMillis()): Long {
        val cut = _link.value != LinkState.CONNECTED || _stale.value
        if (!cut) {
            faceCutSince = 0L
        } else if (faceCutSince == 0L) {
            val down = linkDownSince
            faceCutSince = if (down != 0L && down < nowMs) down else nowMs
        }
        val shown = com.jarvis.client.face.FaceLink.shown(resolveFace(), faceCutSince, nowMs)
        _faceOffline.value = shown.offline
        _faceFocusQuiet.value = !shown.offline && shown.state == FaceState.IDLE &&
            com.jarvis.client.face.RestingFace.focusQuiet(_power.value, _powerWhy.value)
        _face.value = shown.state
        return if (shown.offline) 0L else com.jarvis.client.face.FaceLink.graceLeftMs(faceCutSince, nowMs)
    }

    /** The face on a healthy link; [publishFace] decides what a cut one shows. */
    private fun resolveFace(): FaceState {
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
            // machine that would not. Except a focus session's Quiet (owner,
            // 2026-09-29): that shows the focus buddy, awake and working
            // beside the owner - see RestingFace. A Quiet set by hand stays
            // asleep.
            resting && com.jarvis.client.face.RestingFace.asleep(_power.value, _powerWhy.value) ->
                FaceState.STANDBY
            else -> FaceState.IDLE
        }
    }

    private const val TAG = "JarvisRuntime"

    /**
     * The server sends `: keepalive` every ~20s. Three missed is a dead
     * connection the socket has not noticed; below that a single late frame on
     * a dozing radio would flap the indicator for no reason.
     */
    /** The keys refreshInbox owns; it must not touch the rest of the set. */
    private val INBOX_KEYS = setOf("digest", "undo", "jobs", "activity")

    /** How often the coalesced resume point may reach SharedPreferences. */
    private const val RESUME_WRITE_GAP_MS = 2_000L

    private const val KEEPALIVE_GAP_MS = 70_000L
    private const val WATCHDOG_TICK_MS = 10_000L

    /** How long a change of network settles before the reconnect ([reconnectForNetworkChange]). */
    private const val NETWORK_SETTLE_MS = 1_500L

    /** A status line, not a log: anything longer is cut before it is shown. */
    private const val ACTIVITY_DETAIL_MAX = 200

    /** When to re-read the second-card switches after a decision: see [recheckSecondCardAfterDecision]. */
    private val SECOND_CARD_RECHECK_MS = longArrayOf(0L, 1_500L, 5_000L)

    /** When the link was last lost, or 0 while it is up. */
    @Volatile private var linkDownSince = 0L
}
