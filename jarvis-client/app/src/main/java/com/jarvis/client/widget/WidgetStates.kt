package com.jarvis.client.widget

import com.jarvis.client.net.Calendar
import com.jarvis.client.net.JarvisWidgets
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * The ONE place a home-screen widget's outcome is decided, and the ONE rule
 * every draw follows: **a draw always ends in a state that says something.**
 *
 * Why this file exists (the owner's bug, 2026-10-27). Every Jarvis widget sat
 * on a bare spinner for ever, on a Pixel and on a OnePlus, while the app
 * itself was connected and drawing live PC data. The spinner was not this
 * app's: it was Glance's `glance_default_loading_layout`, the static
 * `initialLayout` the launcher shows until the first update arrives. No
 * update ever arrived because Glance composes a widget inside a WorkManager
 * job and WorkManager could not start one in the release APK (a stripped
 * reflective constructor; see proguard-rules.pro). The app was fine because
 * the app never uses WorkManager.
 *
 * Two lessons are baked into this file rather than left in a comment:
 *
 *  1. **Nothing here can return "loading".** There is no such state. Every
 *     function returns one of a small set of outcomes, and every outcome has
 *     words or real content - so a widget that runs at all cannot show a
 *     spinner, and a widget that never runs shows the launcher layout's own
 *     sentence instead of a ProgressBar.
 *  2. **Every wait has a ceiling.** [bounded] is the only way the widget code
 *     waits for anything - the runtime starting up or the PC answering. A
 *     slow Keystore, a wedged desktop or a dead link ends as an error state
 *     ("Could not reach your PC"), never as an open-ended suspension.
 *
 * Pure Kotlin (no Android types, no Compose, no Glance) so JVM tests execute
 * every branch of it: `WidgetStatesTest`. The widgets then do no deciding of
 * their own - see [ApprovalWidget], [JarvisBoardWidget] and [QuickLinkWidget].
 */
object WidgetStates {

    /**
     * How long a widget waits for the app's runtime to start before saying it
     * could not. Generous next to the real work (object construction, a
     * Keystore read and a small JSON cache file - milliseconds, not seconds),
     * and short enough that a wedged one is a message rather than a spinner.
     */
    const val INIT_TIMEOUT_MS = 4_000L

    /**
     * How long a "Jarvis widget" 1-3 waits for the PC's `GET /api/widgets/show`
     * answer. The general HTTP client's read timeout is 120 s (deliberately,
     * for chat streams), which is far longer than a home screen should be
     * allowed to say nothing.
     */
    const val READ_TIMEOUT_MS = 8_000L

    /**
     * Runs [block], but the CALLER never waits longer than [timeoutMs].
     * `null` means the budget ran out - the caller MUST render its timeout
     * state.
     *
     * The subtle part, and the reason this is not a one-line
     * `withTimeoutOrNull { block() }`: **a timeout cannot cancel a call that is
     * blocked, only a coroutine that is suspended.** `withTimeoutOrNull {
     * withContext(Dispatchers.IO) { blocking() } }` looks bounded and is not -
     * `withContext` does not return until its block finishes, so the timeout
     * only takes effect once the slow thing has already taken however long it
     * wanted. (That shape was written first and `WidgetStatesTest` caught it
     * taking the full 1.5 s of a "blocked" block against a 150 ms budget.)
     *
     * So the work is started on its own dispatcher, handed back through a
     * [CompletableDeferred], and the caller awaits THAT with a timeout. When
     * the budget expires the caller gets `null` immediately and the abandoned
     * work finishes in the background, which is harmless here: the runtime's
     * `initialize` is idempotent, and an OkHttp call is bounded by its own
     * 120 s read timeout.
     */
    suspend fun <T> bounded(timeoutMs: Long, block: suspend () -> T): T? {
        val answer = CompletableDeferred<Result<T>>()
        worker.launch { answer.complete(runCatching { block() }) }
        val finished = withTimeoutOrNull(timeoutMs) { answer.await() } ?: return null
        return finished.getOrThrow()
    }

    /**
     * Where a bounded block actually runs. [Dispatchers.Default] because the
     * work is object construction, preferences and a small JSON file - plus,
     * for the board widgets, a network call that already moves itself to
     * `Dispatchers.IO`. A supervisor job, so one widget's failed draw can
     * never cancel another's.
     */
    private val worker = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    // -------------------------------------------------------- approvals ----

    /** Every outcome of an approvals-widget draw. [CARD] is the only real content. */
    enum class Approval { NOT_STARTED, NOT_PAIRED, NOT_CHECKED, EMPTY, UNREACHABLE, CARD }

    /**
     * The approvals widget's outcome from the snapshot its class already reads.
     *
     * The order is the old `provideGlance` `when` order, unchanged, because
     * each step is a different question and the wording says which:
     *
     *  - nothing could start          -> [Approval.NOT_STARTED]
     *  - started, but not paired      -> [Approval.NOT_PAIRED]
     *  - paired, link down or stale, and the queue was never read
     *                                 -> [Approval.NOT_CHECKED] (not "nothing waiting"!
     *                                    an empty list there means "not looked")
     *  - live and the queue is empty  -> [Approval.EMPTY]
     *  - a card is waiting but nothing can be delivered
     *                                 -> [Approval.UNREACHABLE]
     *  - otherwise                    -> [Approval.CARD]
     *
     * [waiting] is `pending.size`. `stale` is only consulted when the queue is
     * empty: a last-known card on a stale-but-connected link is still shown
     * (with Deny reachable), which is page 7's "refusing is never held" rule.
     */
    fun approval(
        ready: Boolean,
        paired: Boolean,
        connected: Boolean,
        stale: Boolean,
        waiting: Int,
    ): Approval = when {
        !ready -> Approval.NOT_STARTED
        !paired -> Approval.NOT_PAIRED
        waiting <= 0 && (stale || !connected) -> Approval.NOT_CHECKED
        waiting <= 0 -> Approval.EMPTY
        !ApprovalWidgetRules.denyReachable(ready = ready, connected = connected) -> Approval.UNREACHABLE
        else -> Approval.CARD
    }

    /**
     * The two lines an approvals message state shows. `"" to ""` for
     * [Approval.EMPTY] and [Approval.CARD], which draw real content instead -
     * the widget's `when` branches on those two first, so these are never
     * asked for words.
     */
    fun approvalWords(state: Approval): Pair<String, String> = when (state) {
        Approval.NOT_STARTED -> "Jarvis could not start" to "Tap to open and see why"
        Approval.NOT_PAIRED -> "Approvals need a pairing token" to "Tap to open Jarvis and pair"
        Approval.NOT_CHECKED -> "Not checked yet" to "Tap to open Jarvis and connect"
        Approval.UNREACHABLE ->
            "Approvals pending — desktop unreachable" to "Tap to open Jarvis and reconnect"
        Approval.EMPTY, Approval.CARD -> "" to ""
    }

    // ------------------------------------------------------------ board ----

    /** Every outcome of a "Jarvis widget" 1-3 draw. [CONTENT] is the only real content. */
    enum class Board { NOT_STARTED, NOT_PAIRED, NO_WIDGET, STALE, GONE, FAILED, TIMED_OUT, CONTENT }

    /** What the PC's `GET /api/widgets/show` produced, in the shapes a draw can end in. */
    enum class Read { CONTENT, GONE, FAILED, TIMED_OUT }

    /**
     * The board widget's outcome. The pre-read checks are the old `when`,
     * unchanged: not started, not paired, no widget chosen, then not live.
     * Only a live, paired, chosen widget asks the PC, and [read] says how that
     * went. [Board.GONE] is a 404 ("this widget was deleted on the PC"), which
     * needs different words from a failure that might work on the next tap.
     */
    fun board(
        ready: Boolean,
        paired: Boolean,
        chosen: Boolean,
        live: Boolean,
        read: Read,
    ): Board = when {
        !ready -> Board.NOT_STARTED
        !paired -> Board.NOT_PAIRED
        !chosen -> Board.NO_WIDGET
        !live -> Board.STALE
        read == Read.CONTENT -> Board.CONTENT
        read == Read.GONE -> Board.GONE
        read == Read.TIMED_OUT -> Board.TIMED_OUT
        else -> Board.FAILED
    }

    /**
     * The two lines a board message state shows; `"" to ""` for [Board.CONTENT].
     *
     * The four words for states the widget already had are the shared
     * [JarvisWidgets] constants, deliberately not re-typed here: the desktop
     * and the phone draw the same sentences (contract/widget-cases.json), and
     * a second copy is how they drift.
     */
    fun boardWords(state: Board): Pair<String, String> = when (state) {
        Board.NOT_STARTED -> JarvisWidgets.W_NOT_STARTED to JarvisWidgets.W_NOT_STARTED_SUB
        Board.NOT_PAIRED -> JarvisWidgets.W_NOT_PAIRED to JarvisWidgets.W_NOT_PAIRED_SUB
        Board.NO_WIDGET -> JarvisWidgets.W_NONE to JarvisWidgets.W_NONE_SUB
        Board.STALE -> JarvisWidgets.W_STALE to JarvisWidgets.W_STALE_SUB
        Board.GONE -> JarvisWidgets.W_GONE to JarvisWidgets.W_NONE_SUB
        Board.FAILED -> JarvisWidgets.W_FAILED to JarvisWidgets.W_STALE_SUB
        // New, and the one the owner asked for by name: an error a reader can
        // act on, not "not up to date" (which sounds like the PC's fault).
        Board.TIMED_OUT -> "Could not reach your PC" to "Tap to open Jarvis and reconnect"
        Board.CONTENT -> "" to ""
    }

    // -------------------------------------------------------- quick link ----

    /** Every outcome of the quick-link draw. There is no "loading" one. */
    enum class Link { NOT_STARTED, NOT_PAIRED, OFFLINE, RECONNECTING, CONNECTED }

    /**
     * The quick-link widget's outcome. It used to draw the raw [LinkState],
     * which meant a process the launcher woke only to draw this said
     * "Offline" even when the truth was "Jarvis is not running here, and this
     * phone may not even be paired". Both of those are worth opening the app
     * for, and neither is "Offline".
     */
    fun link(
        ready: Boolean,
        paired: Boolean,
        connected: Boolean,
        reconnecting: Boolean,
    ): Link = when {
        !ready -> Link.NOT_STARTED
        !paired -> Link.NOT_PAIRED
        connected -> Link.CONNECTED
        reconnecting -> Link.RECONNECTING
        else -> Link.OFFLINE
    }

    fun linkWords(state: Link): String = when (state) {
        Link.NOT_STARTED -> "Open Jarvis"
        Link.NOT_PAIRED -> "Not paired"
        Link.OFFLINE -> "Offline"
        Link.RECONNECTING -> "Reconnecting"
        Link.CONNECTED -> "Connected"
    }

    // -------------------------------------------------------- calendar ----

    /**
     * Every outcome of a calendar-widget draw. [CONTENT] is the only one that
     * draws real events; every other one has words, because the whole rule of
     * this file is that a draw always ends in a state that says something.
     */
    enum class Cal {
        NOT_STARTED,
        NOT_PAIRED,
        /** The PC's own switch is off (design decision D5: the widget STAYS). */
        OFF,
        /** The link is down or catching up: nothing has been checked. */
        STALE,
        /** The read ran out of its budget. */
        TIMED_OUT,
        /** The route answered something this app cannot draw. */
        FAILED,
        /**
         * App lock or "Hide memory lists and chat history" is on. The home
         * screen is PUBLIC, so this is its own state rather than a redacted
         * [CONTENT]: there is no title to draw, and the widget says one
         * sentence instead.
         */
        HIDDEN,
        CONTENT,
    }

    /**
     * The calendar widget's outcome, in the order the questions are asked.
     *
     * [off] is checked before the link on purpose: the feature being switched
     * off at the PC is the most useful thing to say, and it needs no read at
     * all. [hidden] comes before the read and before [Cal.STALE] - a locked
     * phone has no titles to draw whatever else is wrong, so it says the one
     * reason that is the owner's, and it never draws a word it has already
     * read. [off] still wins over [hidden]: that one needs a tap to Settings,
     * and Settings is where the owner fixes it.
     *
     * A widget with real events and a live link is [CONTENT] even while the
     * list is empty: "Nothing today" is content (a true sentence), not a
     * failure, and drawing it as an error state would be a lie.
     */
    fun calendar(
        ready: Boolean,
        paired: Boolean,
        off: Boolean,
        hidden: Boolean,
        live: Boolean,
        read: Read,
    ): Cal = when {
        !ready -> Cal.NOT_STARTED
        !paired -> Cal.NOT_PAIRED
        off -> Cal.OFF
        hidden -> Cal.HIDDEN
        read == Read.TIMED_OUT -> Cal.TIMED_OUT
        !live -> Cal.STALE
        read == Read.CONTENT -> Cal.CONTENT
        else -> Cal.FAILED
    }

    /**
     * The headline and the sub-line a message state shows; `"" to ""` for
     * [Cal.CONTENT], which draws the date and today's events instead.
     *
     * The four sentences the feature's own words module owns ([Calendar.OFF_WIDGET],
     * [Calendar.HIDDEN], [Calendar.STALE]) are taken from there rather than
     * re-typed, so the widget, the screen and the Brain row cannot drift apart.
     */
    fun calendarWords(state: Cal): Pair<String, String> = when (state) {
        Cal.NOT_STARTED -> "Jarvis could not start" to "Tap to open and see why"
        Cal.NOT_PAIRED -> "Calendar needs a pairing token" to "Tap to open Jarvis and pair"
        Cal.OFF -> Calendar.OFF_WIDGET to Calendar.OFF_WIDGET_SUB
        Cal.STALE -> Calendar.STALE to Calendar.STALE_SUB
        Cal.TIMED_OUT -> "Could not reach your PC" to Calendar.STALE_SUB
        Cal.FAILED -> "Could not read your calendar" to Calendar.STALE_SUB
        Cal.HIDDEN -> Calendar.HIDDEN to Calendar.HIDDEN_SUB
        Cal.CONTENT -> "" to ""
    }
}
