package com.jarvis.client.voice

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
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
 *  - [sign]: what the Live screen, the Home strip and the notification say,
 *    and their buttons (End Live, Mic off / Mic on / Listen anyway, Carry
 *    on, Resume Live, 20 more minutes, Show the card, Move it here) - and
 *    "Jarvis Live is on your PC" when it runs there;
 *  - [listen]: may the next clip be sent, and may the microphone be open at
 *    all - CLOSED while a card of this session waits (cards are decided by
 *    tapping only), on a stale link (rule 4), while muted or on a call, and
 *    while App lock has locked the app; open but CHECK-ONLY through a voice
 *    pause, so the owner's own voice carries on;
 *  - [reply]: what to do with the PC's answer to one clip;
 *  - [transition]: the fixed line to say when the session changed by itself;
 *  - [chips]: the tap buttons after a spoken question (never on a card,
 *    never garbled);
 *  - [isSideTalk] / [couldBeSideTalk]: an answer that is only "[not for me]"
 *    is never spoken, and speech waits while an answer could still be it;
 *  - [barge]: another voice LOWERS Jarvis's voice; it stops only when the PC
 *    says it was the owner;
 *  - [fold]: a second thought before Jarvis's first sound joins the question;
 *  - [cameraShown]: the phone's camera switch, only when the PC says ready;
 *  - [cardInSession]: only a card raised in THIS session holds Live;
 *  - [interruptChoice]: the ONE "Interrupting Jarvis" setting (the owner's
 *    answer of 2026-09-28 merged "Interrupt Jarvis while it talks" and
 *    "Interrupting Jarvis in Live"), and how an older choice carries over.
 *
 * Pure Kotlin: no Android, so the JVM tests run it.
 */
object LiveRules {
    const val ME = "phone"
    const val TITLE = "Jarvis Live"
    const val DOT = " · "
    const val LINK_WORDS = "Paused: link lost - Live carries on when the link is back"

    /** Said in the phone's own voice when the link to the PC drops during Live. */
    const val LINK_LOST_SAID = "I've lost the link to your PC."

    /** ...and when it comes back and the phone listens again. */
    const val LINK_BACK_SAID = "I'm back."
    const val SIDE_TALK_MARK = "[not for me]"
    val VOICE_PAUSES: List<String> = listOf("other_voices", "voice_trouble")
    val CARD_PAUSES: List<String> = listOf("card", "cards_unknown")

    /** Fixed words the apps SHOW (jarvis_live.SEEN). */
    val SEEN: Map<String, String> = linkedMapOf(
        "short" to "Didn't catch that - say a bit more",
        "heard" to "Heard you - thinking",
        "quiet_warn" to "Live ends soon - it's quiet. Say something to keep going",
        "end_hint" to "To end, say \"Okay Jarvis, that's all for now\", or use End Live.",
        "call_unknown" to "Jarvis can't tell when you're on a call - use Mic off",
        "move" to "Live is on your {device} - move it here?",
        "elsewhere" to "Jarvis Live is on your {device}",
        "not_for_me" to "(not for Jarvis)",
        "trouble" to "Heard you, but the words couldn't be made out - say it again",
        "busy_mic" to "Jarvis Live is already listening - just talk",
    )

    /** How each device is named (jarvis_live.DEVICE_WORDS): never "desktop". */
    val DEVICE_WORDS: Map<String, String> = linkedMapOf("desktop" to "PC", "phone" to "phone")

    /** The card pause line (jarvis_live.PAUSE_WORDS["card"]), also shown for a card on screen. */
    const val CARD_WORDS = "Waiting for the card - approve or deny it, and Live carries on"

    /** How the PC's "no voice trained yet" refusal starts (jarvis_live.NEEDS_VOICE). */
    const val NEEDS_VOICE = "Jarvis Live didn't start: it needs your voice trained first"

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

    /** Said on the device Live left when it moved (jarvis_live.END_SAID). */
    const val MOVED_SAID = "Live moved to your other device."

    /** The buttons, the same words on both apps. */
    const val END_LIVE = "End Live"
    const val MIC_OFF = "Mic off"
    const val MIC_ON = "Mic on"
    const val LISTEN_ANYWAY = "Listen anyway"
    const val MORE_TIME = "20 more minutes"
    const val STOP_TALKING = "Stop talking"

    /** "20 more minutes" shows only in the last few minutes. */
    const val MORE_TIME_WITHIN_MIN = 5

    /** "Jarvis Live ended" shows this long after an end that cannot be resumed. */
    const val ENDED_SHOW_S = 15

    /** "Resume Live" is offered this long - the PC's `limits` win. */
    const val RESUME_S = 600

    /** A card raised this long before Live started still counts (jarvis_live.CARD_SLACK_S). */
    const val CARD_SLACK_S = 2.0

    /** The short sound when Live ends here: (hz, ms), made like [HeardSound]. */
    val END_TONE: List<Pair<Int, Int>> = listOf(990 to 75, 660 to 90)

    /** One choice of "Interrupting Jarvis" - the same words as the PC's. */
    data class Choice(val id: String, val label: String, val recommended: Boolean, val detail: String)

    const val INTERRUPT_TITLE = "Interrupting Jarvis"
    const val INTERRUPT_VOICE = "voice"
    const val INTERRUPT_TAP = "tap"
    const val INTERRUPT_OFF = "off"
    val INTERRUPT: List<Choice> = listOf(
        Choice(
            INTERRUPT_VOICE, "Interrupt by voice", true,
            "While Jarvis talks, say \"stop\" or just start talking, and it stops for your voice. " +
                "The Stop talking button works too.",
        ),
        Choice(
            INTERRUPT_TAP, "By button only", false,
            "Talking over Jarvis doesn't stop it - use the Stop talking button instead. Good for a " +
                "noisy room. In Jarvis Live the microphone closes while Jarvis talks.",
        ),
        Choice(
            INTERRUPT_OFF, "Don't interrupt", false,
            "Jarvis finishes what it is saying: talking over it doesn't stop it, and there is no " +
                "Stop talking button. End Live and Stop everything still stop it.",
        ),
    )

    private val INTERRUPT_IDS = setOf(INTERRUPT_VOICE, INTERRUPT_TAP, INTERRUPT_OFF)

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
    private val WH_START = setOf("which", "what", "who", "where", "when", "how", "why")
    private val DETERMINERS = setOf("the", "a", "an", "my", "your", "this", "that", "these", "those", "some")
    private val TRIM = Regex("^[\\s,;:\"'.\\-–—]+|[\\s,;:\"'.\\-–—]+$")

    // -- reading a status --------------------------------------------------

    private fun JsonObject?.str(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject?.flag(key: String): Boolean =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    private fun JsonObject?.int(key: String): Int? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private fun JsonObject?.num(key: String): Double? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

    private fun JsonObject?.any(key: String): JsonElement? = this?.get(key)?.takeIf { it !is JsonNull }

    /** Is [status] a session on [me] ("phone" or "desktop")? */
    fun onHere(status: JsonObject?, me: String = ME): Boolean =
        status.flag("on") && status.str("device") == me

    /** "PC" / "phone" / "other device". */
    fun deviceWords(device: String?): String = DEVICE_WORDS[device] ?: "other device"

    /** "Live is on your PC - move it here?" */
    fun moveWords(device: String?): String = SEEN.getValue("move").replace("{device}", deviceWords(device))

    private fun limit(status: JsonObject?, key: String, fallback: Int): Int =
        (status?.get("limits") as? JsonObject).int(key) ?: fallback

    // -- the sign ----------------------------------------------------------

    data class Sign(
        val show: Boolean = false,
        val title: String = "",
        val detail: String = "",
        val stop: String = "",
        val mute: String = "",
        val carryOn: Boolean = false,
        val resume: Boolean = false,
        val moreTime: Boolean = false,
        val showCard: Boolean = false,
        val move: Boolean = false,
    )

    /**
     * The sign on [me]. [thinking]: the PC heard the owner and the answer
     * has not started; [short]: the last clip was probably the owner, but
     * too short; [cardShown]: this app holds a card raised in this session;
     * [endedAgo]: seconds since it ended, as this app counts them on from
     * the PC's `ended_ago_s`.
     */
    fun sign(
        status: JsonObject?,
        me: String = ME,
        stale: Boolean = false,
        thinking: Boolean = false,
        short: Boolean = false,
        cardShown: Boolean = false,
        endedAgo: Int? = null,
    ): Sign {
        if (status.str("state") == "ended" && status.str("ended_device") == me) {
            val ago = endedAgo ?: status.int("ended_ago_s") ?: 0
            val resume = status.flag("resumable") && ago <= limit(status, "resume_s", RESUME_S)
            if (!resume && ago > limit(status, "ended_show_s", ENDED_SHOW_S)) return Sign()
            return Sign(
                show = true,
                title = "$TITLE ended",
                detail = status.str("ended_words").orEmpty(),
                resume = resume,
            )
        }
        val device = status.str("device")
        if (status.flag("on") && device != null && device in DEVICE_WORDS && device != me) {
            return Sign(
                show = true,
                title = SEEN.getValue("elsewhere").replace("{device}", deviceWords(device)),
                move = true,
            )
        }
        if (!onHere(status, me)) return Sign()
        val minutes = status.int("minutes_left")
        val title = TITLE + (if (minutes != null) "$DOT$minutes min left" else "")
        val paused = status.str("paused").orEmpty()
        val muted = status.flag("muted")
        val detail = when {
            stale -> LINK_WORDS
            muted -> status.str("muted_words").orEmpty()
            paused.isNotEmpty() -> status.str("pause_words").orEmpty()
            cardShown -> CARD_WORDS
            status.flag("quiet_warn") -> SEEN.getValue("quiet_warn")
            thinking -> SEEN.getValue("heard")
            short -> SEEN.getValue("short")
            !status.str("hint").isNullOrEmpty() -> status.str("hint_words").orEmpty()
            else -> ""
        }
        val why = status.str("muted_why")
        val mute = when {
            !muted -> MIC_OFF
            why == "call" || why == "mic_in_use" -> LISTEN_ANYWAY
            else -> MIC_ON
        }
        return Sign(
            show = true,
            title = title,
            detail = detail,
            stop = END_LIVE,
            mute = mute,
            carryOn = paused in VOICE_PAUSES,
            moreTime = minutes != null && minutes <= MORE_TIME_WITHIN_MIN,
            showCard = paused == "card" || cardShown,
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

    enum class Action { END, REFUSED, START, MOVE, TROUBLE, STOP, PAUSE, ANSWER, SHORT, LISTEN }

    data class Reply(val action: Action, val say: String = "")

    fun reply(h: ReplyIn): Reply = when {
        h.live == "ended" -> Reply(Action.END, h.liveSay)
        h.live == "refused" -> Reply(Action.REFUSED)
        h.live == "started" -> Reply(Action.START, h.liveSay)
        h.liveElsewhere.isNotEmpty() -> Reply(Action.MOVE)
        h.live == "off" -> Reply(Action.END)
        // The owner's voice, but no words could be made of it: Live carries on.
        !h.available -> Reply(Action.TROUBLE)
        h.stop -> Reply(Action.STOP)
        h.live == "paused" -> Reply(Action.PAUSE, h.liveSay)
        h.ok && h.text.isNotBlank() -> Reply(Action.ANSWER)
        h.tooShort && h.liveShort == "owner" -> Reply(Action.SHORT, h.liveSay)
        else -> Reply(Action.LISTEN, h.liveSay)
    }

    // -- the fixed line when the status changed by itself ------------------

    fun transition(before: JsonObject?, after: JsonObject?, me: String = ME): String {
        if (after.str("state") == "ended" && after.str("ended_device") == me && onHere(before, me)) {
            return after.str("ended_say").orEmpty()
        }
        val device = after.str("device")
        if (onHere(before, me) && after.flag("on") && device != null && device != me) return MOVED_SAID
        if (onHere(after, me) && after.flag("ending_soon") && !before.flag("ending_soon") &&
            before.any("session") != null && before.any("session") == after.any("session")
        ) {
            return LINES.getValue("warn")
        }
        return ""
    }

    // -- tap buttons -------------------------------------------------------

    private fun cap(s: String): String = s.trim().replaceFirstChar { it.uppercaseChar() }

    private fun trim(s: String): String = s.replace(TRIM, "")

    private fun words(s: String): List<String> = s.split(" ").filter { it.isNotEmpty() }

    /**
     * The tap buttons after a spoken answer that ends with a question. Each
     * is sent as the owner's typed words. Never while a card is on screen,
     * and never a garbled one: no buttons rather than wrong ones
     * (tools/gen_live_cases.py `chips` says the rule in words).
     */
    fun chips(answer: String?, cardShown: Boolean = false): List<String> {
        if (cardShown) return emptyList()
        val text = answer.orEmpty().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (!text.endsWith("?")) return emptyList()
        val parts = text.split(Regex("(?<=[.!?])\\s+"))
        val q = parts.last().replace(Regex("\\?+$"), "").trim()
        val lower = words(q.lowercase())
        val at = q.lastIndexOf(" or ")
        if (at < 0) {
            return if (lower.isNotEmpty() && lower[0] in YES_NO_START) listOf("Yes", "No") else emptyList()
        }
        var left = q.substring(0, at)
        val right = trim(q.substring(at + 4))
        var cut = -1
        var cutLen = 0
        for (sep in listOf(": ", " - ", " – ", " — ")) {
            val i = left.lastIndexOf(sep)
            if (i > cut) {
                cut = i
                cutLen = sep.length
            }
        }
        if (cut >= 0) left = left.substring(cut + cutLen)
        val rwords = words(right)
        if (rwords.size !in 1..4) return emptyList()
        val segs = left.split(",").map { trim(it) }.filter { it.isNotEmpty() }
        if (segs.isEmpty()) return emptyList()
        val lead = words(segs[0])[0].lowercase()
        val options: List<String> = when {
            lead in WH_START && segs.size >= 2 -> segs.drop(1)
            lead in WH_START || lead in YES_NO_START -> {
                val first = words(segs[0])
                val n = if (segs.size >= 2) words(segs[1]).size else rwords.size
                if (first.size <= n) return emptyList()
                val tail = first.takeLast(n)
                val head = tail[0].lowercase()
                if (n > 1 && head !in DETERMINERS) return emptyList()
                if (head in YES_NO_START || head in WH_START) return emptyList()
                listOf(tail.joinToString(" ")) + segs.drop(1)
            }
            else -> segs
        }
        val all = options.filter { it.isNotEmpty() } + right
        if (all.any { words(it).size > 4 }) return emptyList()
        return if (all.size in 2..MAX_CHIPS) all.map(::cap) else emptyList()
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

    /**
     * Does a card this app shows hold Live? Only one raised in THIS session
     * (the design's C8, the PC's own rule): a card that was already waiting
     * before Live started does not (the review's B8). A card whose time
     * cannot be read, or a status without `started_at`, counts - fail closed.
     * [created] and `started_at` are both the PC's clock, in seconds.
     */
    fun cardInSession(created: Double?, status: JsonObject?): Boolean {
        if (created == null || !created.isFinite()) return true
        val started = status.num("started_at") ?: return true
        if (!started.isFinite()) return true
        return created >= started - CARD_SLACK_S
    }

    /**
     * The ONE interrupt setting, from what is stored: the new one when
     * chosen, else the older ones carried over - "Interrupt Jarvis while it
     * talks" turned OFF becomes "Don't interrupt", Live's "tap only" becomes
     * "By button only"; never chosen, "Interrupt by voice" only where this
     * phone has an echo canceller.
     */
    fun interruptChoice(saved: String?, oldBargeIn: Boolean?, oldLive: String?, echo: Boolean): String = when {
        saved != null && saved in INTERRUPT_IDS -> saved
        oldBargeIn == false -> INTERRUPT_OFF
        oldLive == INTERRUPT_TAP -> INTERRUPT_TAP
        oldBargeIn == true -> INTERRUPT_VOICE
        echo -> INTERRUPT_VOICE
        else -> INTERRUPT_TAP
    }

    // -- what the phone sends (POST /api/voice/live) ------------------------

    /** Only these fixed words go out; nothing heard ever does. */
    fun startBody(): String = "{\"do\":\"start\",\"device\":\"$ME\",\"by\":\"button\"}"

    /** Why the phone ends Live: the owner (End Live), or App lock would lock the app. */
    val END_REASONS: List<String> = listOf("owner", "app_lock")

    fun stopBody(why: String = "owner"): String =
        "{\"do\":\"stop\",\"why\":\"${if (why in END_REASONS) why else "owner"}\",\"device\":\"$ME\"}"

    /** "More time": 1 to 120 minutes, or null. */
    fun extendBody(minutes: Int = 20): String? =
        if (minutes in 1..120) "{\"do\":\"extend\",\"minutes\":$minutes}" else null

    const val RESUME_BODY = "{\"do\":\"resume\"}"

    /** The owner typed or tapped in Live: the PC's quiet clock starts again. */
    const val ACTIVE_BODY = "{\"do\":\"active\",\"device\":\"$ME\"}"

    /** Why the phone mutes: the owner's Mic off, or a phone or video call. */
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

    /**
     * A call began or ended: what to tell the PC, or null. Never undoes the
     * owner's own Mute; and after the owner pressed "Listen anyway" during a
     * call ([overridden]), a call that still reads as on does not mute it
     * again - until the audio mode has been seen out of the call once (a
     * stuck IN_COMMUNICATION would otherwise keep the owner muted for good;
     * the review's bug 4, the desktop's MIC_OVERRIDDEN).
     */
    fun callMuteChange(status: JsonObject?, onCall: Boolean, overridden: Boolean = false): Boolean? {
        val muted = status.flag("muted")
        val why = status.str("muted_why").orEmpty()
        return when {
            onCall && !muted && !overridden -> true
            !onCall && muted && why == "call" -> false
            else -> null
        }
    }

    /** The camera switch: the phone's only, and only when the PC says ready. */
    fun cameraShown(status: JsonObject?, me: String = ME): Boolean =
        me == "phone" && onHere(status, me) && (status?.get("camera") as? JsonObject).flag("ready")
}
