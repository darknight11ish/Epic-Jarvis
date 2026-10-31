package com.jarvis.client.data

import com.jarvis.client.FaceState
import com.jarvis.client.net.ChatHistory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * "Picture-in-picture" (Settings -> This app): a small Jarvis window that stays
 * on screen while the owner uses other apps - the next-turn box in Maps, not a
 * shrunken phone screen.
 *
 * The design is settled: `docs/PIP-DESIGN.md` on `main`, every question in it
 * answered by the owner (§9), and this file is built to it. In one paragraph:
 * Jarvis gets a small window that stays on screen when the owner leaves the
 * app - Android's own picture-in-picture. It shows one of three compact things
 * the owner picks in Settings: the face with the first line of the current
 * answer, the last few messages of the conversation, or Jarvis Live continuing
 * while he uses another app. It can never approve anything, never show a hidden
 * list or a locked answer, and never becomes a second place to change a
 * setting. Tapping it brings the real app back.
 *
 * WHY A FOURTH MODE, not a third value inside "Floating Jarvis": the two answer
 * different questions. [FloatingAvatarMode] is "how should the floating face
 * appear?", and its values are two ways to TALK to Jarvis without opening it;
 * this is "what does the window show when I leave the app?" - a way to SEE
 * something. The owner chose separate rows, and both may be on at once
 * (`docs/PIP-DESIGN.md` §2.2): while the PiP window is up, the Floating Jarvis
 * overlay hides its own window rather than drawing a second Jarvis over it
 * ([PipPresence]).
 *
 * Saved on this phone only ([ClientSettings.pipMode]), like every other display
 * setting - nothing about it is sent to the PC and there is no route.
 *
 * NOT a settings surface and NOT an approval surface: nothing in a PiP window
 * decides a card, changes a setting or opens History, and the only action the
 * system chrome carries is [PipWords.EXPAND] (`docs/PIP-DESIGN.md` §5, §9.4).
 *
 * Pure, no Android: `PipTest`.
 */
enum class PipMode(val wire: String, val label: String, val about: String) {
    OFF(
        "off",
        "Off",
        "Nothing appears when you leave Jarvis.",
    ),
    FACE(
        "face",
        "The face and the answer",
        "The face, and the first line of the newest answer.",
    ),
    THREAD(
        "thread",
        "The conversation",
        "The last few messages, the newest at the bottom.",
    ),
    LIVE(
        "live",
        "Jarvis Live",
        "The Live session, if one is running.",
    ),
    ;

    companion object {
        /**
         * Mode 1 is the default - the owner's "1 or 3 by default" with the
         * lead's recorded call for 1 (`docs/PIP-DESIGN.md` §2.1): the face and
         * the answer is always true, where Live needs a session actually
         * running or the window has nothing to show.
         *
         * A value that is missing, empty or unknown to this build reads as
         * [FACE], never as a window that cannot be explained: the setting is
         * what decides the DEFAULT, and "off" is the owner's own value, so a
         * missing preference is not "off" - it is "this phone has never chosen"
         * and the design's default applies.
         */
        val DEFAULT: PipMode = FACE

        fun fromWire(s: String?): PipMode = entries.firstOrNull { it.wire == s } ?: DEFAULT
    }
}

/**
 * What the small window actually draws, decided purely from four inputs - the
 * whole point being that a test can drive the truth table without a phone
 * (`docs/PIP-DESIGN.md` §6.1).
 *
 * The aspect ratio travels with it: mode 1 and mode 3 are about 16:9, mode 2 is
 * taller (9:16 in portrait) because it is a short list (§3).
 */
enum class PipLayout(val aspectW: Int, val aspectH: Int) {
    /** The setting is Off: there is no window at all. Never drawn. */
    OFF(16, 9),

    /**
     * The content is hidden - "Hide memory lists and chat history" or App lock.
     * A neutral face, dimmed, and [PipWords.LOCKED]; never an answer, never a
     * conversation, never an approval's words (§4, §9.1).
     */
    HIDDEN(16, 9),

    /** The face, the state word and the first line of the newest answer. */
    FACE(16, 9),

    /** The last few messages, newest at the bottom, scrollable. */
    THREAD(9, 16),

    /** Jarvis Live at its smallest useful size: is it listening, and mute/end. */
    LIVE(16, 9),

    /**
     * The setting is Live but no Live session is running: the window does NOT
     * close (it is the owner's window, and closing it would look like a crash).
     * It shows the face, the state word, and one plain line above the answer
     * slot - [PipWords.LIVE_OFF] (§2.4).
     */
    LIVE_OFF(16, 9),
    ;

    /** Whether this layout draws the conversation at all. */
    val answerShown: Boolean get() = this == FACE || this == LIVE_OFF

    /** Whether this layout draws the last few messages. */
    val threadShown: Boolean get() = this == THREAD

    /** Whether this layout draws the Live controls. */
    val liveShown: Boolean get() = this == LIVE

    companion object {
        /**
         * Which layout a state draws. THE TRUTH TABLE (§6.1): every combination
         * of the four inputs. It holds TWO promises, and their ORDER is part of
         * the contract:
         *
         *  1. **The SETTING decides whether a window may exist at all.** Mode
         *     [PipMode.OFF] means [OFF], whatever the phone's privacy state is.
         *  2. **Then hidden content outranks everything the window would
         *     otherwise show** - every non-Off mode, and a running Live session
         *     with it - because while the lists are hidden or the app is locked
         *     the window says why it is empty and shows nothing it could
         *     otherwise show (§4, §9.1).
         *
         * THE ORDER IS THE F-13 FIX (2026-10-31). This function used to check
         * privacy FIRST and map the mode second, so `mode = Off` with "Hide
         * memory lists and chat history" on answered [HIDDEN] instead of [OFF];
         * `MainActivity.buildPipParams` then armed auto-enter from that layout
         * and a PiP window appeared after Home - and after a fresh process start
         * - although the owner had chosen Off. With the two rules in this order,
         * and auto-enter keyed on the stored mode rather than the layout, an Off
         * mode can never produce a window. `PipTest` pins both halves in the
         * source, so a future reorder fails the suite instead of the owner's
         * phone.
         */
        fun fromState(
            mode: PipMode,
            liveRunning: Boolean,
            privateHidden: Boolean,
            appLock: Boolean,
        ): PipLayout {
            // (1) The setting first: Off means there is no window, full stop.
            if (mode == PipMode.OFF) return OFF
            // (2) Then privacy: no answer, no conversation, no Live view.
            if (privateHidden || appLock) return HIDDEN
            return when (mode) {
                // Unreachable (Off returned above). Kept so the `when` stays
                // exhaustive and a future edit cannot drop the case silently.
                PipMode.OFF -> OFF
                // §2.4: while a Live session runs, the Live view takes the
                // window and gives it back when Live ends - so "1 or 3" is ONE
                // preference, not two things to keep in sync.
                PipMode.FACE -> if (liveRunning) LIVE else FACE
                PipMode.THREAD -> if (liveRunning) LIVE else THREAD
                PipMode.LIVE -> if (liveRunning) LIVE else LIVE_OFF
            }
        }
    }
}

/**
 * Every fixed word the window says. ONE place, so a test can hold all of them
 * (and no others) and so a second surface cannot quietly invent a different
 * sentence for the same state.
 *
 * Two of these are the owner's own decisions, quoted exactly:
 *  - [LOCKED] - "Hidden while Jarvis is locked." (§9.1). The reason he gave is
 *    the reason it is worded this way: with the content silently gone there is
 *    no way to tell hidden from broken, and this window always says which state
 *    it is in.
 *  - [LIVE_OFF] - "Live is off. Start it and it shows here." (§2.4).
 */
object PipWords {
    /** The Settings row, and the window's title. */
    const val TITLE = "Picture-in-picture"

    /** §9.1, the owner's own words. Shown INSTEAD OF any content. */
    const val LOCKED = "Hidden while Jarvis is locked."

    /** §2.4, the owner's own words. Shown when the Live setting has no session. */
    const val LIVE_OFF = "Live is off. Start it and it shows here."

    /** The one action the window's system chrome carries (§9.4). */
    const val EXPAND = "Expand"

    /** The state word for "cannot reach the PC right now" (Home's own word). */
    const val NOT_CONNECTED = "Not connected"

    /** The state word while the event stream is catching up (Home's own word). */
    const val CATCHING_UP = "Catching up…"

    /** An approval is waiting; the WORDS are the state word only, never the card's. */
    const val WAITING = "Waiting for you"

    const val LISTENING = "Listening"
    const val THINKING = "Thinking"
    const val SPEAKING = "Speaking"

    /** A problem on the PC; never its detail, which could be about anything. */
    const val PROBLEM = "Something is wrong"

    /** The resting word (§2.3's own example list ends at "Not connected"). */
    const val STANDING_BY = "Standing by"

    /** A Live session is running and this phone is listening. */
    const val LIVE_LISTENING = "Live is listening"

    /** A Live session is running on the PC rather than on this phone. */
    const val LIVE_ON_PC = "Live is on your PC"

    /**
     * The ONE word/line the face uses for a state - the app's own vocabulary
     * (Home's status line and `FaceShellRules.FaceWords`), shortened to what a
     * window a third of a screen wide can say. Never an approval's title, body,
     * plan, recipients or search words: a waiting card reads [WAITING] and
     * nothing else (§5).
     *
     * @param offline the link is down or stale - a claim about the PC must not
     *   be made from a phone that cannot hear it
     * @param stale the event stream is catching up
     * @param approval an approval is waiting
     */
    fun state(state: FaceState, offline: Boolean, stale: Boolean, approval: Boolean): String = when {
        offline -> NOT_CONNECTED
        stale -> CATCHING_UP
        approval || state == FaceState.APPROVAL -> WAITING
        state == FaceState.LISTENING -> LISTENING
        state == FaceState.THINKING -> THINKING
        state == FaceState.SPEAKING -> SPEAKING
        state == FaceState.ERROR -> PROBLEM
        else -> STANDING_BY
    }
}

/**
 * What the window's text formatters may produce: one answer line, or the last
 * few messages. Pure (`docs/PIP-DESIGN.md` §6.2, §6.3) so the forbidden-words
 * test can drive the VALUE that comes out, not just that a function ran.
 *
 * The window is handed CHAT TEXT and the fixed words in [PipWords] - never an
 * approval card, its title, its body, its plan, its recipients, its search
 * words, its file names, the pairing token, the server address or a key
 * (§4.3, §4.5). There is no formatter here that could take one: the only inputs
 * are the strings the chat already shows on Home, and an empty reply stays
 * empty rather than being filled from somewhere else.
 */
object PipText {

    /** The widest one answer line may be before it is ellipsised. */
    const val MAX_LINE = 100

    /** The widest one conversation line may be (a couple of lines' worth). */
    const val MAX_THREAD_LINE = 140

    /** One row of the conversation layout: the owner's words, or Jarvis's. */
    data class Row(val text: String, val fromOwner: Boolean)

    /**
     * The FIRST LINE of an answer, and only the first line (§2.3): no second
     * line, no markdown, ellipsised when it is long. An empty reply is the
     * empty string - the window shows no answer rather than a guess.
     */
    fun firstLine(reply: String): String {
        val first = reply.lineSequence().map { plain(it) }.firstOrNull { it.isNotEmpty() } ?: return ""
        return ellipsise(first, MAX_LINE)
    }

    /**
     * The conversation layout's rows: the last [max] exchanges, oldest first
     * (the newest at the bottom), the owner's question and Jarvis's answer. The
     * answer is clipped to a couple of lines because the window is a short list,
     * not a transcript (§2.3). No input box, no send button, no card.
     */
    fun threadRows(thread: List<ChatHistory.Exchange>, max: Int = 4): List<Row> {
        if (max <= 0) return emptyList()
        return thread.takeLast(max).flatMap { exchange ->
            val rows = mutableListOf<Row>()
            plain(exchange.asked.lastOrNull()?.text.orEmpty()).takeIf { it.isNotEmpty() }
                ?.let { rows += Row(ellipsise(it, MAX_THREAD_LINE), fromOwner = true) }
            clipLines(exchange.answer, 2).takeIf { it.isNotEmpty() }
                ?.let { rows += Row(ellipsise(it, MAX_THREAD_LINE), fromOwner = false) }
            rows
        }
    }

    /** Up to [lines] non-empty lines of [text], joined by " ", markdown removed. */
    private fun clipLines(text: String, lines: Int): String =
        text.lineSequence().map { plain(it) }.filter { it.isNotEmpty() }.take(lines).joinToString(" ")

    /**
     * One line of chat text as the window may draw it: markdown removed (a PiP
     * window has no room for it and the design says the text carries none), a
     * leading bullet or heading marker dropped, whitespace collapsed. This
     * never adds or invents words.
     */
    private fun plain(line: String): String =
        line
            .replace(Regex("\\[([^\\]]*)]\\([^)]*\\)"), "$1")   // a link: its words, not its address
            .replace(Regex("`{1,3}"), "")
            .replace(Regex("^\\s{0,3}(#{1,6}|>|[-*+]\\s+|\\d+[.)]\\s+)\\s*"), "")
            .replace(Regex("[*_]{1,3}"), "")
            .replace(Regex("\\s+"), " ")
            .trim()

    /** [text] cut at [max] characters, ending in an ellipsis when it was cut. */
    private fun ellipsise(text: String, max: Int): String =
        if (text.length <= max) text else text.take(max - 1).trimEnd() + "…"
}

/**
 * Whether a PiP window is up RIGHT NOW, process-wide (2026-10-30).
 *
 * It exists for one thing: the Floating Jarvis overlay is the one that yields
 * while the window is up (`docs/PIP-DESIGN.md` §2.2) - it hides its own view
 * with `View.GONE` rather than stopping, so the setting is untouched and the
 * face comes back when PiP ends. One Jarvis on screen, and the one showing real
 * content is the one that stays.
 *
 * Set by [com.jarvis.client.MainActivity]'s `onPictureInPictureModeChanged`,
 * read by [com.jarvis.client.service.AvatarOverlayService]. Nothing here is
 * saved; a process that restarts has no PiP window either.
 */
object PipPresence {
    private val _up = MutableStateFlow(false)

    /** Whether a picture-in-picture window is on screen. */
    val up: StateFlow<Boolean> = _up.asStateFlow()

    fun setUp(value: Boolean) {
        _up.value = value
    }
}
