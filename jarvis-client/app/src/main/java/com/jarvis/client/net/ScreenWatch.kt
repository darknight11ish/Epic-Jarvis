package com.jarvis.client.net

import com.jarvis.client.data.ScreenNever
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withTimeoutOrNull

/**
 * "Watch with me" on THIS phone (the owner's decision of 2026-09-28,
 * docs/SCREEN-DESIGN.md section 4): the owner starts it, Android asks its own
 * question every time, and while it runs a notification says "Jarvis is
 * watching" with Stop. It ends by itself after [MAX_MINUTES], when the phone
 * locks or the screen goes off, or when Android ends the screen sharing.
 *
 * NOTHING IS STREAMED. A picture is taken only when the owner asks a question
 * ([beforeQuestion], called by `ChatSession.send`), is made small, is held in
 * memory as a look for that ONE question ([ScreenLook.hold] with a picture),
 * goes to the PC only - inside the question, over the private link - and is
 * used up by it. The PC reads the WORDS in it and keeps neither; with one
 * graphics card no model is ever shown the picture (JARVIS-API section 62.6).
 *
 * BEFORE any picture is kept, [decide] runs: the app in front (from Android's
 * Usage access - screen sharing does not say which app it is) against the
 * Never look at list, a locked or dark screen, and a picture that is almost
 * all black (an app that blocks screenshots draws black into screen sharing).
 * Any doubt is a refusal, never a look.
 *
 * No Android in this file: the JVM tests hold every rule
 * ([com.jarvis.client.ScreenWatchTest]); the Android-backed half - the screen
 * sharing, the front-app read and the notification - is
 * `service/ScreenWatchService.kt`, which registers itself here.
 */
object ScreenWatch {
    /** The longest one session runs. */
    const val MAX_MINUTES = 30

    /** The longest side of the picture that is sent, in pixels. */
    const val LONG_EDGE = 1280

    /** JPEG quality: about 150 KB a question at that size. */
    const val JPEG_QUALITY = 70

    /** How long a question waits for the picture before it goes without one. */
    const val GRAB_TIMEOUT_MS = 2_500L

    /** A picture this dark is a secure app (or a black screen): dropped. */
    const val BLACK_LUMA = 12
    const val BLACK_SHARE = 0.995

    // The words, fixed (the sign is the safeguard, so they never vary).
    const val START_LABEL = "Watch this phone with me"
    const val STOP_LABEL = "Stop watching"
    const val SIGN_TITLE = "Jarvis is watching this phone"
    const val NOTIFICATION_TEXT = "Only when you ask a question · Stop ends it"
    const val NEEDS_USAGE = "Watching needs Android's Usage access, so Jarvis can tell which app " +
        "is in front and leave your private apps alone. It shows Jarvis which app is open - " +
        "nothing you do inside it."
    const val OPEN_USAGE = "Open Usage access"
    const val NEEDS_READ_ON = "Turn on \"Let Jarvis read this phone's screen\" in Security first."
    const val HOW =
        "Android will ask you to allow screen sharing, every time. When you then ask a question, " +
            "Jarvis takes ONE picture, sends it only to your PC, and keeps nothing. It stops by " +
            "itself after 30 minutes, when the phone locks, or when you press Stop. Ask by voice " +
            "from another app: a question typed in Jarvis is about Jarvis's own screen, which it " +
            "will not look at."
    const val ENDED_LOCK = "Stopped watching: the phone locked."
    const val ENDED_TIME = "Stopped watching: 30 minutes are up."
    const val ENDED_ANDROID = "Stopped watching: Android ended the screen sharing."
    const val PRIVATE_SCREEN = "That app won't let anything see its screen, so I'm not looking."
    const val DARK_SCREEN = "The screen is off or locked, so I'm not looking."

    // ---------------------------------------------------------------- state

    /** What the phone's sign and the Home plate show. */
    data class State(
        val on: Boolean = false,
        /** Milliseconds (the phone's monotonic clock) when it ends by itself; 0 when off. */
        val endsAt: Long = 0L,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    @Volatile var clock: () -> Long = { System.nanoTime() / 1_000_000L }

    /** The service says a session began. */
    fun started(minutes: Int = MAX_MINUTES) {
        _state.value = State(true, clock() + minutes.coerceIn(1, MAX_MINUTES) * 60_000L)
    }

    /** The service says the session is over (whatever the reason). */
    fun ended() {
        _state.value = State()
    }

    /** The sign's minutes-left line: "24 min left", or "under a minute left". */
    fun leftLine(now: Long = clock(), s: State = _state.value): String {
        if (!s.on) return ""
        val leftS = ((s.endsAt - now) / 1000.0).coerceAtLeast(0.0)
        return ScreenRules.minutesLeft(leftS)
    }

    /**
     * The sign, in [ScreenRules.Sign]'s shape, so Home shows it with the same
     * plate as the PC's. Null while nothing is being watched.
     */
    fun sign(now: Long = clock(), s: State = _state.value): ScreenRules.Sign? {
        if (!s.on) return null
        return ScreenRules.Sign(
            show = true,
            on = true,
            title = SIGN_TITLE,
            detail = leftLine(now, s),
            stop = STOP_LABEL,
            more = "",
            tone = "watching",
        )
    }

    // -------------------------------------------------------------- deciding

    /** One front-app event from Android's usage log. [type] is `UsageEvents.Event`'s. */
    data class UsageEvent(val at: Long, val type: Int, val pkg: String)

    /** `UsageEvents.Event.ACTIVITY_RESUMED` (`MOVE_TO_FOREGROUND` before Android 10 is 1 too). */
    const val EVENT_RESUMED = 1
    /** `ACTIVITY_PAUSED` and `ACTIVITY_STOPPED`. */
    const val EVENT_PAUSED = 2
    const val EVENT_STOPPED = 23

    /**
     * The app in front, from the usage events in time order: the last app that
     * came forward and has not since gone back. Null when the log says nothing
     * (Usage access not given, or a log too short) - "cannot tell" is a
     * refusal, never a guess.
     */
    fun frontApp(events: List<UsageEvent>): String? {
        var front: String? = null
        for (e in events.sortedBy { it.at }) {
            when (e.type) {
                EVENT_RESUMED -> if (e.pkg.isNotBlank()) front = e.pkg
                EVENT_PAUSED, EVENT_STOPPED -> if (e.pkg == front) front = null
            }
        }
        return front
    }

    /**
     * Is [luma] (one 0..255 brightness per sampled pixel) so dark it must be a
     * secure app or a black screen? An empty sample counts as dark.
     */
    fun looksBlack(luma: IntArray): Boolean {
        if (luma.isEmpty()) return true
        var dark = 0
        for (v in luma) if (v < BLACK_LUMA) dark++
        return dark.toDouble() / luma.size >= BLACK_SHARE
    }

    /** The brightness (0..255) of one ARGB pixel, without any Android. */
    fun lumaOf(argb: Int): Int {
        val r = (argb shr 16) and 0xFF
        val g = (argb shr 8) and 0xFF
        val b = argb and 0xFF
        return (r * 299 + g * 587 + b * 114) / 1000
    }

    /** The picture's size after it is made small: the long side at most [LONG_EDGE]. */
    fun scaledSize(width: Int, height: Int): Pair<Int, Int> {
        if (width <= 0 || height <= 0) return 0 to 0
        val long = maxOf(width, height)
        if (long <= LONG_EDGE) return width to height
        // Whole-number maths, so 1080 x 2400 is exactly 576 x 1280.
        return maxOf(1, (width.toLong() * LONG_EDGE / long).toInt()) to
            maxOf(1, (height.toLong() * LONG_EDGE / long).toInt())
    }

    /** What to do with one moment's screen. */
    sealed class Verdict {
        object Take : Verdict()
        data class Refuse(val said: String) : Verdict()
    }

    /**
     * May this screen be kept? [front] is the app in front ([frontApp]);
     * [never] the owner's own list; [category] the app's Play Store category;
     * [screenOn] is false when the phone is locked or dark; [black] is
     * [looksBlack] of the picture (null before a picture exists - asked twice:
     * once before any is taken, once after).
     */
    fun decide(
        front: String?,
        never: Set<String>,
        category: Int?,
        screenOn: Boolean,
        black: Boolean?,
    ): Verdict {
        if (!screenOn) return Verdict.Refuse(DARK_SCREEN)
        ScreenNever.blocked(front, never, category)?.let { return Verdict.Refuse(ScreenNever.said(it)) }
        if (black == true) return Verdict.Refuse(PRIVATE_SCREEN)
        return Verdict.Take
    }

    // ------------------------------------------------------------ the question

    /** One picture, or the reason there is none. */
    data class Grab(val app: String, val dataUrl: String?, val said: String?)

    /**
     * Set by the running service; cleared when it ends. Takes the picture NOW
     * (or says why not) - checked against [decide] inside, before and after.
     */
    @Volatile var grabber: (suspend () -> Grab)? = null

    /** Where a refusal is said (the app's notice line); set by the runtime. */
    @Volatile var say: (String) -> Unit = {}

    /** Set by the running service: ends the session. */
    @Volatile var stopHook: (() -> Unit)? = null

    /** "Stop everything" and the Stop button: ends a session that is running. Never held. */
    fun requestStop() {
        stopHook?.invoke()
    }

    /**
     * Called by `ChatSession.send` for every question that is not Live: while
     * a session runs, one picture is taken and held for THIS question
     * ([ScreenLook.hold], used up by it). Not running: nothing happens. A
     * picture that takes too long, or any failure, is a question without one.
     */
    suspend fun beforeQuestion() {
        val grab = grabber ?: return
        if (!_state.value.on) return
        val got = try {
            withTimeoutOrNull(GRAB_TIMEOUT_MS) { grab() }
        } catch (e: CancellationException) {
            throw e // the question itself was cancelled: not ours to swallow
        } catch (e: Exception) {
            null
        } ?: return
        val url = got.dataUrl
        if (url == null) {
            got.said?.let(say)
            return
        }
        ScreenLook.hold(app = got.app, words = "", picture = url, shown = true, consume = true)
    }

    /** For the tests: everything back to the start. */
    fun resetForTests() {
        _state.value = State()
        clock = { System.nanoTime() / 1_000_000L }
        grabber = null
        say = {}
        stopHook = null
    }
}
