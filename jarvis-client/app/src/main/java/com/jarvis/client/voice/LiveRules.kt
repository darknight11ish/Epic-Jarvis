package com.jarvis.client.voice

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Jarvis Live's rules on this phone - the same as the PC's
 * (jarvis-desktop/src/live-rules.js), both held to
 * `src/test/resources/contract/live-cases.json`, which
 * tools/gen_live_cases.py writes from backend/jarvis_live.py (LiveRulesTest).
 *
 * Jarvis Live (the owner's decision and answers of 2026-09-28,
 * docs/LIVE-DESIGN.md): a back-and-forth voice conversation the owner starts
 * and stops. The session is the PC's (GET/POST /api/voice/live); these are
 * the few things each app decides for itself:
 *
 *  - [sign]: what the Live screen and the notification say, and their
 *    buttons;
 *  - [listen]: may the next clip be sent, and may the microphone be open at
 *    all - CLOSED while a card waits (cards are decided by tapping only), on
 *    a stale link (rule 4), while muted or on a call, and while App lock has
 *    locked the app; open but CHECK-ONLY through a voice pause, so the
 *    owner's own voice carries on;
 *  - [reply]: what to do with the PC's answer to one clip;
 *  - [transition]: the fixed line to say when the session changed by itself;
 *  - [chips]: the tap buttons after a spoken question (never on a card);
 *  - [isSideTalk] / [couldBeSideTalk]: an answer that is only "[not for me]"
 *    is never spoken, and speech waits while an answer could still be it;
 *  - [barge]: another voice LOWERS Jarvis's voice; it stops only when the PC
 *    says it was the owner;
 *  - [fold]: a second thought before Jarvis's first sound joins the question;
 *  - [cameraShown]: the phone's camera switch, only when the PC says ready.
 *
 * Pure Kotlin: no Android, so the JVM tests run it.
 */
object LiveRules {
    const val ME = "phone"
    const val TITLE = "Jarvis Live"
    const val DOT = " · "
    const val LINK_WORDS = "Paused: link lost"

    /** Said in the phone's own voice when the link to the PC drops during Live. */
    const val LINK_LOST_SAID = "I've lost the link to your PC."
    const val SIDE_TALK_MARK = "[not for me]"
    val VOICE_PAUSES: List<String> = listOf("other_voices", "voice_trouble")
    val CARD_PAUSES: List<String> = listOf("card", "cards_unknown")

    /** Fixed words the apps SHOW (jarvis_live.SEEN). */
    val SEEN: Map<String, String> = linkedMapOf(
        "short" to "Didn't catch that - say a bit more",
        "heard" to "Heard you - thinking",
        "quiet_warn" to "Live ends soon - it's quiet",
        "end_hint" to "To end, say \"Okay Jarvis, that's all for now\", or press End.",
        "call_unknown" to "Jarvis can't tell when you're on a call - use Mute",
        "move" to "Live is on your {device} - move it here?",
        "not_for_me" to "(not for Jarvis)",
    )

    /** Fixed lines Jarvis SAYS (jarvis_live.LINES). */
    val LINES: Map<String, String> = linkedMapOf(
        "started" to "I'm listening.",
        "waking" to "Waking up, a few seconds.",
        "short" to "Say a bit more, so I can tell it's you.",
        "bye" to "Okay. Live ended.",
        "extended" to "Okay, {n} more minutes.",
        "warn" to "Two minutes left. To keep going, say: give me twenty more minutes.",
        "quiet" to "Live ended - it was quiet.",
    )

    /** One choice of "Interrupting Jarvis in Live" - the same words as the PC's. */
    data class Choice(val id: String, val label: String, val recommended: Boolean, val detail: String)

    const val INTERRUPT_TITLE = "Interrupting Jarvis in Live"
    const val INTERRUPT_VOICE = "voice"
    const val INTERRUPT_TAP = "tap"
    val INTERRUPT: List<Choice> = listOf(
        Choice(
            INTERRUPT_VOICE, "Interrupt by voice", true,
            "In Jarvis Live, start talking while Jarvis talks and it stops for your voice.",
        ),
        Choice(
            INTERRUPT_TAP, "Interrupt by tap only", false,
            "In Jarvis Live, talking over Jarvis does not stop it - tap Stop talking instead. Good for a noisy room.",
        ),
    )
    const val STOP_TALKING = "Stop talking"

    /** Smart Turn in Live: an unfinished-sounding sentence may pause this long. */
    const val TURN_ASK_AFTER_MS = 200L
    const val TURN_MAX_PAUSE_MS = 3000L

    /** How far Jarvis's voice drops while another voice is being checked. */
    const val DUCK_VOLUME = 0.3f
    const val MAX_CHIPS = 3

    private val YES_NO_START = setOf(
        "do", "does", "did", "is", "are", "was", "were", "should", "shall",
        "can", "could", "will", "would", "have", "has", "want", "may", "am",
    )

    // -- reading a status --------------------------------------------------

    private fun JsonObject?.str(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject?.flag(key: String): Boolean =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject?.int(key: String): Int? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject?.any(key: String): JsonElement? = this?.get(key)?.takeIf { it !is JsonNull }

    /** Is [status] a session on [me] ("phone" or "desktop")? */
    fun onHere(status: JsonObject?, me: String = ME): Boolean =
        status.flag("on") && status.str("device") == me

    // -- the sign ----------------------------------------------------------

    data class Sign(
        val show: Boolean = false,
        val title: String = "",
        val detail: String = "",
        val stop: String = "",
        val mute: String = "",
        val carryOn: Boolean = false,
        val resume: Boolean = false,
    )

    /**
     * The sign on [me]. [thinking]: the PC heard the owner and the answer
     * has not started; [short]: the last clip was probably the owner, but
     * too short.
     */
    fun sign(
        status: JsonObject?,
        me: String = ME,
        stale: Boolean = false,
        thinking: Boolean = false,
        short: Boolean = false,
    ): Sign {
        if (status.str("state") == "ended" && status.str("ended_device") == me) {
            val words = status.str("ended_words").orEmpty()
            return Sign(
                show = true,
                title = "$TITLE ended",
                detail = if (words.isNotEmpty()) "It ended: $words." else "",
                resume = status.flag("resumable"),
            )
        }
        if (!onHere(status, me)) return Sign()
        val minutes = status.int("minutes_left")
        val title = TITLE + (if (minutes != null) "$DOT$minutes min left" else "")
        val paused = status.str("paused").orEmpty()
        val detail = when {
            stale -> LINK_WORDS
            status.flag("muted") -> status.str("muted_words").orEmpty()
            paused.isNotEmpty() -> status.str("pause_words").orEmpty()
            status.flag("quiet_warn") -> SEEN.getValue("quiet_warn")
            thinking -> SEEN.getValue("heard")
            short -> SEEN.getValue("short")
            !status.str("hint").isNullOrEmpty() -> status.str("hint_words").orEmpty()
            else -> ""
        }
        return Sign(
            show = true,
            title = title,
            detail = detail,
            stop = if (me == "phone") "End" else "Stop",
            mute = if (status.flag("muted")) "Unmute" else "Mute",
            carryOn = paused in VOICE_PAUSES,
        )
    }

    // -- may it listen -----------------------------------------------------

    data class Listen(val listen: Boolean, val mic: Boolean, val why: String)

    fun listen(
        status: JsonObject?,
        me: String = ME,
        stale: Boolean = false,
        cardShown: Boolean = false,
        answering: Boolean = false,
        appLocked: Boolean = false,
        interrupt: String = INTERRUPT_VOICE,
    ): Listen {
        if (!onHere(status, me)) return Listen(false, false, "off")
        if (appLocked) return Listen(false, false, "locked")
        if (stale) return Listen(false, false, "link")
        if (status.flag("muted")) return Listen(false, false, "muted")
        val paused = status.str("paused")
        if (cardShown || paused in CARD_PAUSES) return Listen(false, false, "card")
        if (paused in VOICE_PAUSES) return Listen(true, true, "check")
        if (answering) return Listen(false, interrupt == INTERRUPT_VOICE, "answering")
        return Listen(true, true, "")
    }

    // -- the PC's answer to one clip ---------------------------------------

    /** The fields of one utterance reply these rules read (Heard's). */
    data class ReplyIn(
        val ok: Boolean = false,
        val owner: Boolean = false,
        val available: Boolean = true,
        val text: String = "",
        val live: String = "",
        val liveSay: String = "",
        val liveShort: String = "",
        val liveElsewhere: String = "",
        val stop: Boolean = false,
        val tooShort: Boolean = false,
    ) {
        companion object {
            /** The PC's own JSON (the shared table's `heard`). */
            fun of(h: JsonObject): ReplyIn = ReplyIn(
                ok = h.flag("ok"),
                owner = h.flag("owner"),
                available = (h["available"] as? JsonPrimitive)?.booleanOrNull ?: true,
                text = h.str("text").orEmpty(),
                live = h.str("live").orEmpty(),
                liveSay = h.str("live_say").orEmpty(),
                liveShort = h.str("live_short").orEmpty(),
                liveElsewhere = h.str("live_elsewhere").orEmpty(),
                stop = h.flag("stop"),
                tooShort = h.flag("too_short"),
            )
        }
    }

    enum class Action { END, REFUSED, START, MOVE, STOP, PAUSE, ANSWER, SHORT, LISTEN }

    data class Reply(val action: Action, val say: String = "")

    fun reply(h: ReplyIn): Reply = when {
        h.live == "ended" -> Reply(Action.END, h.liveSay)
        h.live == "refused" -> Reply(Action.REFUSED)
        h.live == "started" -> Reply(Action.START, h.liveSay)
        h.liveElsewhere.isNotEmpty() -> Reply(Action.MOVE)
        h.live == "off" || !h.available -> Reply(Action.END)
        h.stop -> Reply(Action.STOP)
        h.live == "paused" -> Reply(Action.PAUSE, h.liveSay)
        h.ok && h.text.isNotBlank() -> Reply(Action.ANSWER)
        h.tooShort && h.liveShort == "owner" -> Reply(Action.SHORT, h.liveSay)
        else -> Reply(Action.LISTEN, h.liveSay)
    }

    // -- the fixed line when the status changed by itself ------------------

    fun transition(before: JsonObject?, after: JsonObject?, me: String = ME): String {
        if (after.str("state") == "ended" && after.str("ended") == "quiet" &&
            after.str("ended_device") == me && onHere(before, me)
        ) {
            return LINES.getValue("quiet")
        }
        if (onHere(after, me) && after.flag("ending_soon") && !before.flag("ending_soon") &&
            before.any("session") != null && before.any("session") == after.any("session")
        ) {
            return LINES.getValue("warn")
        }
        return ""
    }

    // -- tap buttons -------------------------------------------------------

    private fun cap(s: String): String = s.trim().replaceFirstChar { it.uppercaseChar() }

    private fun words(s: String): List<String> = s.split(" ").filter { it.isNotEmpty() }

    /**
     * The tap buttons after a spoken answer that ends with a question. Each
     * is sent as the owner's typed words. Never while a card is on screen.
     */
    fun chips(answer: String?, cardShown: Boolean = false): List<String> {
        if (cardShown) return emptyList()
        val text = answer.orEmpty().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (!text.endsWith("?")) return emptyList()
        val parts = text.split(Regex("(?<=[.!?])\\s+"))
        val q = parts.last().replace(Regex("\\?+$"), "").trim()
        val lower = words(q.lowercase())
        val at = q.lastIndexOf(" or ")
        if (at >= 0) {
            val left = q.substring(0, at)
            val right = q.substring(at + 4).replace(Regex("^[\\s,]+|[\\s,]+$"), "")
            val rwords = words(right)
            if (rwords.size in 1..4) {
                val n = rwords.size
                val segs = left.split(",").map { it.trim() }
                val first = words(segs[0])
                val options = mutableListOf<String>()
                if (first.size >= n) options += first.takeLast(n).joinToString(" ")
                options += segs.drop(1).filter { it.isNotEmpty() && words(it).size <= 4 }
                val all = options.filter { it.isNotEmpty() } + right
                if (all.size in 2..MAX_CHIPS) return all.map(::cap)
            }
            // An either-or whose options are too long for a button: no chips.
            return emptyList()
        }
        if (lower.isNotEmpty() && lower[0] in YES_NO_START) return listOf("Yes", "No")
        return emptyList()
    }

    // -- side talk, interrupting, a second thought -------------------------

    /** Is this whole answer the side-talk marker? (jarvis_live.is_side_talk) */
    fun isSideTalk(answer: String?): Boolean =
        answer.orEmpty().trim().lowercase().replace(Regex("\\.+$"), "").trim() == SIDE_TALK_MARK

    /** Hold speech while the answer so far could still turn out to be the marker. */
    fun couldBeSideTalk(partial: String?): Boolean {
        val p = partial.orEmpty().trim().lowercase()
        return p.isNotEmpty() && (SIDE_TALK_MARK.startsWith(p) || isSideTalk(p))
    }

    /** "onset" -> "duck"; "owner" -> "stop"; anything else -> "restore". */
    fun barge(event: String): String = when (event) {
        "onset" -> "duck"
        "owner" -> "stop"
        else -> "restore"
    }

    /** A second thought before Jarvis's first sound joins the question. */
    fun fold(previous: String?, next: String?, sounded: Boolean): String {
        val prev = previous.orEmpty().trim()
        val now = next.orEmpty().trim()
        if (sounded || prev.isEmpty()) return now
        return "$prev $now".trim()
    }

    // -- what the phone sends (POST /api/voice/live) ------------------------

    /** Only these fixed words go out; nothing heard ever does. */
    fun startBody(): String = "{\"do\":\"start\",\"device\":\"$ME\",\"by\":\"button\"}"

    /** Why the phone ends Live: the owner (End), or App lock would lock the app. */
    val END_REASONS: List<String> = listOf("owner", "app_lock")

    fun stopBody(why: String = "owner"): String =
        "{\"do\":\"stop\",\"why\":\"${if (why in END_REASONS) why else "owner"}\",\"device\":\"$ME\"}"

    /** "More time": 1 to 120 minutes, or null. */
    fun extendBody(minutes: Int = 20): String? =
        if (minutes in 1..120) "{\"do\":\"extend\",\"minutes\":$minutes}" else null

    const val RESUME_BODY = "{\"do\":\"resume\"}"

    /** Why the phone mutes: the owner's Mute, or a phone or video call. */
    val MUTE_WHYS: List<String> = listOf("owner", "call")

    fun muteBody(muted: Boolean, why: String = "owner"): String =
        "{\"do\":\"${if (muted) "mute" else "unmute"}\",\"why\":\"${if (why in MUTE_WHYS) why else "owner"}\"," +
            "\"device\":\"$ME\"}"

    /**
     * Android's audio modes that mean a phone or video call is going on
     * (AudioManager: IN_CALL 2, IN_COMMUNICATION 3, CALL_SCREENING 4,
     * CALL_REDIRECT 5, COMMUNICATION_REDIRECT 6). Read from the audio mode -
     * no phone-state permission is needed for it.
     */
    val CALL_MODES: Set<Int> = setOf(2, 3, 4, 5, 6)

    /**
     * Is the phone on a call? [ownVoiceCall]: Jarvis itself put the phone in
     * communication mode to cancel its own echo (Speaker.voiceCall) - that is
     * not a call.
     */
    fun onCall(mode: Int, ownVoiceCall: Boolean): Boolean = !ownVoiceCall && mode in CALL_MODES

    /** A call began or ended: what to tell the PC, or null. Never undoes the owner's own Mute. */
    fun callMuteChange(status: JsonObject?, onCall: Boolean): Boolean? {
        val muted = status.flag("muted")
        val why = status.str("muted_why").orEmpty()
        return when {
            onCall && !muted -> true
            !onCall && muted && why == "call" -> false
            else -> null
        }
    }

    /** The camera switch: the phone's only, and only when the PC says ready. */
    fun cameraShown(status: JsonObject?, me: String = ME): Boolean =
        me == "phone" && onHere(status, me) && (status?.get("camera") as? JsonObject).flag("ready")
}
