package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Solve it here" (the owner's decision of 2026-09-28, CLAUDE.md "A captcha
 * can be handed to the owner's phone"; JARVIS-API.md section 87.8; the PC's
 * backend/jarvis_handoff.py).
 *
 * When a chatbot website or a customer-support chat pauses at a captcha, a
 * sign-in page or an "unusual activity" page, the PC says so on
 * `GET /api/chatbot/status` (`handoff`: which site and why - never a picture,
 * never a word from the page). This phone then:
 *  - raises an alert that names the site and the reason only, kept on this
 *    phone, and generic while App lock is on (service/HandoffNotifier.kt);
 *  - offers "Solve it here" (ui/screens/HandoffScreen.kt): a live picture of
 *    THAT ONE browser window, asked for about once a second only while the
 *    screen is showing and the app is unlocked, never saved (held in memory
 *    for the screen only; screenshots of Jarvis are blocked meanwhile), and
 *    the owner's own taps, typing, a few keys and scrolls passed back to it.
 *    Input is held on a stale link (rule 4); End never is.
 *
 * The PC refuses every picture and every input unless the session is still
 * paused at that very page, in that window, on the site's own hosts - this
 * phone cannot widen that. Jarvis never solves anything: there is no code
 * here that decides where to tap.
 *
 * Pure Kotlin (no Android), so HandoffTest runs it against the PC's real
 * answers (contract/handoff-cases.json, tools/gen_handoff_cases.py).
 */
object Handoff {
    const val START_PATH = "/api/chatbot/handoff/start"
    const val FRAME_PATH = "/api/chatbot/handoff/frame"
    const val INPUT_PATH = "/api/chatbot/handoff/input"
    const val END_PATH = "/api/chatbot/handoff/end"

    /**
     * How long the hand-off stays on offer (the owner's decision of
     * 2026-10-08: "make this a setting for both options with 1 as the
     * default"; backend/jarvis_handoff_mode.py). Deliberately NOT one of the
     * hand-off's own picture or input routes: it carries one word - which of
     * the two choices - and no picture, no page and no tap.
     */
    const val MODE_PATH = "/api/chatbot/handoff_mode"

    /** The only POST routes the phone sends for the hand-off itself. */
    val WRITE_PATHS: Set<String> = setOf(START_PATH, INPUT_PATH, END_PATH)

    /**
     * The setting's own POST route. Apart from [WRITE_PATHS] on purpose: those
     * three move a picture or the owner's own typing to the PC's browser
     * window, and this one only chooses how long the offer lasts, so a reader
     * (and this app's own rules) can never confuse the two.
     */
    val MODE_PATHS: Set<String> = setOf(MODE_PATH)

    // ---- the words, the PC's own (jarvis_handoff.WORDS) -------------------

    const val TITLE = "Solve it here"
    const val ALERT_TITLE = "{site} needs you"
    const val ALERT_LOCKED = "A website Jarvis is using needs you"
    const val ALERT_TEXT = "Jarvis paused: {reason}. Solve it here, or in the window on the PC."
    const val HERE_BUTTON = "Solve it here"
    const val PC_BUTTON = "Solve it on the PC instead"
    const val DETAIL = "A live picture of that one browser window on your PC, sent only to this " +
        "phone and never saved. Your taps and typing go to that window only, and only while " +
        "Jarvis is paused there. Jarvis never solves it for you."
    const val MAY_REFUSE = "Some captchas refuse taps passed on from a phone this way. If it " +
        "keeps saying no, solve it on the PC instead."
    const val THEN_RESUME = "When it is done, press Resume. Resume asks with a card, as always."
    const val TYPE_LABEL = "Type into the page"
    const val TYPE_SEND = "Type it"
    const val KEYS_LABEL = "Keys"
    const val SCROLL_UP = "Scroll up"
    const val SCROLL_DOWN = "Scroll down"
    const val END = "End"
    const val HELD_STALE = "The link to your PC is catching up, so your taps and typing are " +
        "held until it is back."
    const val LOCKED = "Unlock Jarvis to see the page."
    const val WAITING = "Getting the picture..."
    const val NEW_WINDOW = "If the site opens a new window or tab, finish there on the PC - only " +
        "the first window is passed on."

    val WORDS: Map<String, String> = linkedMapOf(
        "title" to TITLE,
        "alert_title" to ALERT_TITLE,
        "alert_locked" to ALERT_LOCKED,
        "alert_text" to ALERT_TEXT,
        "reason_captcha" to "a captcha (a \"prove you are a person\" check)",
        "reason_login" to "a sign-in page",
        "reason_unusual" to "an \"unusual activity\" page",
        "here_button" to HERE_BUTTON,
        "pc_button" to PC_BUTTON,
        "detail" to DETAIL,
        "may_refuse" to MAY_REFUSE,
        "then_resume" to THEN_RESUME,
        "type_label" to TYPE_LABEL,
        "type_send" to TYPE_SEND,
        "keys_label" to KEYS_LABEL,
        "scroll_up" to SCROLL_UP,
        "scroll_down" to SCROLL_DOWN,
        "end" to END,
        "held_stale" to HELD_STALE,
        "locked" to LOCKED,
        "waiting" to WAITING,
        "pc_title" to "{site} needs you on this PC",
        "pc_text" to "Jarvis paused: {reason}. Deal with it in the browser window, then press " +
            "Resume. Your phone can do it too (Solve it here).",
        "new_window" to NEW_WINDOW,
    )

    // ---- how long it stays on offer (the owner's setting, 2026-10-08) -------
    // The setting itself lives in its own file, [HandoffMode]: its one route,
    // its two values, its default and every sentence it shows. This object keeps
    // only the one thing the hand-off's own screen needs from it: the `stuck`
    // line that rides on the status (below), plus the `patient` flag.

    /**
     * The PC's own line for the window it is stuck on, from `handoff.stuck` in
     * `GET /api/chatbot/status` - or null when the hand-off ended some other way
     * (or is still on offer). "Stop early" (the default) is the moment this
     * appears. Anything not in the PC's exact shape is null.
     */
    fun stuck(status: JsonObject?): Pair<String, String>? {
        val o = (status?.get("handoff") as? JsonObject)
            ?: status?.takeIf { it.containsKey("stuck") } ?: return null
        val s = o["stuck"] as? JsonObject ?: return null
        val title = s.text("title")?.takeIf { it.isNotBlank() } ?: return null
        val text = s.text("text")?.takeIf { it.isNotBlank() } ?: return null
        return title to text
    }

    /** Is the PC keeping the offer for the full ceiling? (an older PC: no) */
    fun patient(o: JsonObject?): Boolean =
        (o?.get("patient") as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true

    /** Why a hand-off ended, the PC's own sentences (jarvis_handoff.ENDED). */
    val ENDED: Map<String, String> = linkedMapOf(
        "owner" to "You ended it.",
        "resumed" to "The page is no longer waiting for you - the conversation carried on or was resumed.",
        "stopped" to "The conversation stopped.",
        "left" to "The window went to another site, so the hand-off ended. Nothing more is passed " +
            "on - look at the window on the PC.",
        "closed" to "The browser window closed.",
        "idle" to "Nobody was looking at the picture for a while, so the hand-off ended.",
        "time" to "The hand-off ended after 15 minutes.",
        "stop_all" to "Stop everything ended it.",
        "replaced" to "A new hand-off started.",
    )

    /**
     * The PC's own line for a window Jarvis is stuck on, word for word
     * (jarvis_handoff.STUCK): shown when the hand-off ended the "Stop early"
     * way, naming the site and the reason, so the owner knows exactly which
     * browser window on the PC to solve it in.
     */
    val STUCK: Map<String, String> = linkedMapOf(
        "title" to "{site} is waiting on this PC",
        "text" to "Jarvis is stuck on {reason} in that window, so the hand-off to your phone has " +
            "ended. Solve it in the browser window on this PC, then press Resume. Your phone " +
            "can start it again (Solve it here) if you need it.",
    )

    /** That line for one site and reason, exactly as the PC writes it. */
    fun stuckLine(site: String, reason: String): Pair<String, String> =
        (STUCK.getValue("title").replace("{site}", site)) to
            STUCK.getValue("text").replace("{reason}", reasonWords(reason))

    /** The keys the phone may send by name (jarvis_handoff.KEYS). */
    val KEYS: List<String> = listOf(
        "Enter", "Backspace", "Delete", "Tab", "Escape", "Space",
        "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    )

    /** The keys the screen shows as buttons, in this order. */
    val SHOWN_KEYS: List<String> = listOf("Enter", "Backspace", "Tab", "Space")

    val OWNER_CODES: Set<String> = setOf("captcha", "login", "unusual")

    /** Typed characters in one input (jarvis_handoff.TEXT_MOST). */
    const val TEXT_MOST = 200

    /** How far one Scroll button moves the page, in page pixels. */
    const val SCROLL_STEP = 300

    /**
     * How often the screen asks for a picture. The PC allows two a second;
     * one is enough to see a captcha change and light on the link.
     */
    const val FRAME_EVERY_MS = 1000L

    private val HID = Regex("^ho_[0-9a-f]{16}$")
    private val CHAT_ID = Regex("^chat_[0-9a-f]{12}$")
    private val SUPPORT_ID = Regex("^sup_[0-9a-f]{12}$")

    fun validHid(h: String?): Boolean = h != null && HID.matches(h)

    private fun JsonObject?.text(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.content

    // ---- what is waiting ---------------------------------------------------

    /** A page waiting for the owner: which session, which site, why. */
    data class Offer(
        val kind: String,
        val id: String,
        val reason: String,
        val site: String,
        /** The hand-off going on now for it, or "". */
        val active: String = "",
    ) {
        /** One alert per session and reason: a new captcha on the same session alerts again. */
        val key: String get() = "$kind:$id:$reason"
    }

    /**
     * `handoff` from `GET /api/chatbot/status` (the whole answer, or the
     * field itself), or null when nothing waits - or the PC is older and
     * sends none. Anything not in the PC's exact shape is null.
     */
    fun offer(status: JsonObject?): Offer? {
        val o = (status?.get("handoff") as? JsonObject) ?: status?.takeIf { it.containsKey("available") }
            ?: return null
        val available = (o["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true
        if (!available) return null
        val kind = o.text("kind") ?: return null
        val id = o.text("id") ?: return null
        val reason = o.text("reason") ?: return null
        if (reason !in OWNER_CODES) return null
        val idOk = when (kind) {
            "chatbot" -> CHAT_ID.matches(id)
            "support" -> SUPPORT_ID.matches(id)
            else -> false
        }
        if (!idOk) return null
        val active = o.text("active").orEmpty().takeIf { validHid(it) }.orEmpty()
        return Offer(kind, id, reason, o.text("site")?.takeIf { it.isNotBlank() } ?: "The website", active)
    }

    fun reasonWords(reason: String): String =
        WORDS["reason_$reason"] ?: WORDS.getValue("reason_captcha")

    /**
     * The alert's title and text. [locked]: App lock (or "Hide memory lists
     * and chat history") is on - the words name nothing, not even the site.
     */
    fun alert(o: Offer, locked: Boolean): Pair<String, String> =
        if (locked) {
            ALERT_LOCKED to TITLE
        } else {
            ALERT_TITLE.replace("{site}", o.site) to ALERT_TEXT.replace("{reason}", reasonWords(o.reason))
        }

    // ---- what goes to the PC ----------------------------------------------

    /** `{"kind", "id"}`, or null for anything that is not a real session of the PC's shape. */
    fun startBody(o: Offer): String? {
        val ok = (o.kind == "chatbot" && CHAT_ID.matches(o.id)) || (o.kind == "support" && SUPPORT_ID.matches(o.id))
        return if (ok) "{\"kind\":\"${o.kind}\",\"id\":\"${o.id}\"}" else null
    }

    /** One tap, as fractions of the picture (0..1), or null outside it. */
    fun tapBody(h: String, x: Float, y: Float): String? {
        if (!validHid(h) || x !in 0f..1f || y !in 0f..1f) return null
        return "{\"h\":\"$h\",\"type\":\"tap\",\"x\":${round4(x)},\"y\":${round4(y)}}"
    }

    /** Typed characters: 1 to [TEXT_MOST], no control characters (use the keys). */
    fun textBody(h: String, text: String): String? {
        if (!validHid(h) || text.isEmpty() || text.length > TEXT_MOST) return null
        if (text.any { it.code < 32 || it.code == 127 }) return null
        return "{\"h\":\"$h\",\"type\":\"text\",\"text\":${JsonPrimitive(text)}}"
    }

    /** One key from [KEYS], or null. */
    fun keyBody(h: String, key: String): String? =
        if (validHid(h) && key in KEYS) "{\"h\":\"$h\",\"type\":\"key\",\"key\":\"$key\"}" else null

    fun scrollBody(h: String, dy: Int): String? =
        if (validHid(h)) "{\"h\":\"$h\",\"type\":\"scroll\",\"dy\":${dy.coerceIn(-1500, 1500)}}" else null

    fun endBody(h: String): String? = if (validHid(h)) "{\"h\":\"$h\"}" else null

    /** Input waits on a stale link (rule 4): the sentence, or null to send. End never waits. */
    fun inputHeld(stale: Boolean): String? = if (stale) HELD_STALE else null

    private fun round4(v: Float): String = String.format(java.util.Locale.ROOT, "%.4f", v)

    // ---- what comes back -------------------------------------------------

    sealed interface Answer {
        /** One picture: base64 JPEG and its size in page pixels. */
        data class Picture(val jpeg: String, val width: Int, val height: Int, val seq: Int) : Answer

        /** Too soon for another picture: ask again after [retryMs]. */
        data class TooSoon(val retryMs: Long) : Answer

        /** The hand-off ended ([why] is the PC's code; [words] its sentence). */
        data class Ended(val why: String, val words: String) : Answer

        /** Something else went wrong, in words; the screen tries again. */
        data class Failed(val words: String) : Answer
    }

    /** A picture or input answer (status code and body, as the PC sent them). */
    fun answer(code: Int, body: JsonObject?): Answer {
        if (code == 410) {
            val why = body.text("ended").orEmpty()
            return Answer.Ended(why, body.text("error") ?: ENDED[why] ?: ENDED.getValue("owner"))
        }
        if (code == 429) {
            val ms = (body?.get("retry_ms") as? JsonPrimitive)?.intOrNull?.toLong() ?: 500L
            return Answer.TooSoon(ms.coerceIn(50L, 5000L))
        }
        if (code in 200..299) {
            val jpeg = body.text("jpeg")
            val w = (body?.get("width") as? JsonPrimitive)?.intOrNull ?: 0
            val h = (body?.get("height") as? JsonPrimitive)?.intOrNull ?: 0
            val seq = (body?.get("seq") as? JsonPrimitive)?.intOrNull ?: 0
            return if (jpeg != null && w > 0 && h > 0) Answer.Picture(jpeg, w, h, seq) else Answer.Failed("")
        }
        return Answer.Failed(body.text("error") ?: "Your PC did not answer that. Try again.")
    }

    /**
     * Where a tap at ([x], [y]) inside a [boxW] x [boxH] area lands on a
     * [imgW] x [imgH] picture drawn to fit it (ContentScale.Fit, centred), as
     * fractions 0..1 - or null for a tap on the empty margin beside it.
     */
    fun fractions(x: Float, y: Float, boxW: Float, boxH: Float, imgW: Int, imgH: Int): Pair<Float, Float>? {
        if (boxW <= 0f || boxH <= 0f || imgW <= 0 || imgH <= 0) return null
        val scale = minOf(boxW / imgW, boxH / imgH)
        val drawnW = imgW * scale
        val drawnH = imgH * scale
        val fx = (x - (boxW - drawnW) / 2f) / drawnW
        val fy = (y - (boxH - drawnH) / 2f) / drawnH
        if (fx < 0f || fx > 1f || fy < 0f || fy > 1f) return null
        return fx to fy
    }
}
