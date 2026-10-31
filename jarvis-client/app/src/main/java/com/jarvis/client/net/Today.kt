package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import java.time.Instant
import java.time.ZoneId

/**
 * Today cards (the owner's choice of 2026-09-28, the research audit's idea
 * 6; docs/JARVIS-API.md section 82; backend `jarvis_today.py`) - the words,
 * and how to read what the PC sends. The desktop's src/today.js, word for
 * word; its tests/today.mjs checks this file for them.
 *
 * Short notes in the owner's own words ("Gym bag") that show in the Today
 * section of Brain at a time, on chosen days, from that time to the end of
 * the day - plus the briefing's own parts (the weather from the owner's own
 * Home Assistant, the calendar, new email, what is still to come today) from
 * the latest briefing made today. Nothing new is read for it: the cards are
 * jobs of kind "today" on the PC's one scheduler (`GET /api/schedule`, the
 * Coming up read) and the briefing parts come from `GET /api/briefing` (the
 * Morning briefing read).
 *
 * The Today page itself was designed but never built; the feasibility audit
 * said it may only grow out of what is already there, never become a fourth
 * summary. So it is one section on Brain, just above Coming up - the same
 * place the desktop puts it on its Work tab.
 *
 * No approval card: like a plain repeating reminder, only the owner's own
 * words or taps can set one, it acts on nothing, and Delete is immediate.
 * Adding one is held on a stale link ([com.jarvis.client.JarvisRuntime.addTodayCard]).
 * "Hide memory lists and chat history" hides the words ([Schedule.hide]);
 * the times stay.
 *
 * Pure Kotlin, no Android types, so `TodayTest` runs it on a plain JVM.
 */
object Today {
    const val TITLE = "Today"
    const val DETAIL =
        "Your own cards, shown at the times and on the days you choose, and the parts of your " +
            "latest briefing. Kept on your PC; nothing new is read for this page, and adding a card " +
            "needs no approval card."
    const val EMPTY_CARDS = "No cards for today yet."
    const val LATER_TITLE = "Later today"
    const val FROM_BRIEFING = "From your briefing"
    const val NO_BRIEFING_TODAY =
        "No briefing made today yet - \"Brief me now\" under Morning briefing puts one together."
    const val HINT =
        "Or say \"show gym bag on my Today page on Mondays and Wednesdays at 7\". " +
            "Delete removes a card at once; it is also under Coming up, where Pause skips it."

    /** The small form. */
    const val ADD_TITLE = "Add a card"
    const val TEXT_PLACEHOLDER = "What the card says, like Gym bag"
    const val TIME_LABEL = "From"
    const val DAYS_LABEL = "On"
    const val ADD_LABEL = "Add"
    const val DELETE_LABEL = "Delete"
    val DAY_SHORT = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    /** The PC's own words (jarvis_today.py). */
    const val MAX_TEXT = 80
    const val NO_WORDS = "A Today card needs some words: what should it say?"
    const val TOO_LONG = "A Today card is at most $MAX_TEXT characters - say it more briefly."
    const val NO_DAYS = "Pick at least one day."
    const val BAD_TIME = "Write the time as HH:MM, like 07:00."
    const val MISSING = "Your PC's Jarvis cannot do Today cards yet - run apply-patches.ps1 on the PC."

    /** The tag on a card - Coming up's tag for the kind ([Schedule.tag]). */
    const val TAG = "today card"

    /** The briefing parts shown here, in this order - never news. */
    val BRIEFING_PARTS = listOf("weather", "calendar", "email", "today")

    data class Card(
        val id: String,
        val text: String,
        val hidden: Boolean,
        val today: String,
        val showsAt: String,
    )

    /** The owner's cards from the Coming up read. */
    fun cardsOf(v: Schedule.View?): List<Card> =
        v?.jobs?.filter { it.kind == Schedule.TODAY_CARD }?.map {
            Card(
                id = it.id,
                text = it.text,
                hidden = it.hidden,
                today = if (it.today == "showing" || it.today == "later") it.today else "",
                showsAt = it.showsAt,
            )
        } ?: emptyList()

    /** The cards on today's page, and those later today - each by time. */
    fun todayCards(cards: List<Card>): Pair<List<Card>, List<Card>> =
        cards.filter { it.today == "showing" }.sortedBy { it.showsAt } to
            cards.filter { it.today == "later" }.sortedBy { it.showsAt }

    /** A card's words, or a stand-in while the private lists are hidden. */
    fun cardTitle(c: Card): String = if (c.hidden || c.text.isEmpty()) "(hidden) $TAG" else c.text

    /** "From 07:00" - under a card. */
    fun cardMeta(c: Card): String = if (c.showsAt.isEmpty()) "" else "From ${c.showsAt}"

    /** Is [made] (epoch seconds) today, by this phone's clock? */
    fun madeToday(made: Double?, nowMs: Long = System.currentTimeMillis(),
                  zone: ZoneId = ZoneId.systemDefault()): Boolean {
        if (made == null || !made.isFinite()) return false
        val a = Instant.ofEpochMilli((made * 1000).toLong()).atZone(zone).toLocalDate()
        val b = Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDate()
        return a == b
    }

    /**
     * The latest briefing's parts to show as cards - only a briefing made
     * today, never "What did I miss?"; null when there is none. Lines are
     * already gone while hidden ([Briefing.hide]).
     */
    fun briefingCards(v: Briefing.View?, nowMs: Long = System.currentTimeMillis(),
                      zone: ZoneId = ZoneId.systemDefault()): List<Briefing.Section>? {
        val b = v?.briefing ?: return null
        if (b.source == "missed" || !madeToday(b.made, nowMs, zone)) return null
        return BRIEFING_PARTS.mapNotNull { key -> b.sections.firstOrNull { it.key == key } }
            .map { if (b.hidden) it.copy(items = emptyList()) else it }
    }

    private val HHMM = Regex("([01]?\\d|2[0-3]):([0-5]\\d)")

    /**
     * The body of one new card - `{"kind": "today", "text", "repeat"}` - or
     * the reason it cannot be one, in both apps' words ([String] on the
     * right). All seven days is "every day", Monday to Friday "every
     * weekday", anything else "every week" on those days - the desktop's
     * Rust (brain/schedule.rs today_body) says the same.
     */
    fun addBody(text: String, at: String, days: Set<Int>): Pair<String?, String?> {
        val t = text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        if (t.isEmpty()) return null to NO_WORDS
        if (t.codePointCount(0, t.length) > MAX_TEXT) return null to TOO_LONG
        val m = HHMM.matchEntire(at.trim()) ?: return null to BAD_TIME
        val time = m.groupValues[1].padStart(2, '0') + ":" + m.groupValues[2]
        val d = days.filter { it in 0..6 }.sorted()
        if (d.isEmpty()) return null to NO_DAYS
        val repeat = when (d) {
            listOf(0, 1, 2, 3, 4, 5, 6) -> "{\"every\":\"day\",\"at\":\"$time\"}"
            listOf(0, 1, 2, 3, 4) -> "{\"every\":\"weekday\",\"at\":\"$time\"}"
            else -> "{\"every\":\"week\",\"at\":\"$time\",\"days\":[${d.joinToString(",")}]}"
        }
        val words = JarvisJson.encodeToString(kotlinx.serialization.serializer<String>(), t)
        return "{\"kind\":\"today\",\"text\":$words,\"repeat\":$repeat}" to null
    }

    // ── The Today board (GTD-2, 2026-10-18; added to the phone 2026-10-31) ──
    //
    // The ONE real phone gap the 2026-10-31 parity audit named (G1), ported
    // here. The desktop draws this board at the bottom of its Today page
    // (`jarvis-desktop/src/today.js`'s own "The Today board" section, and
    // `brain.js`'s `todayBoardNodes`); every sentence below is that file's,
    // quoted, and `TodayBoardTest` reads `today.js` to prove it word for word.
    //
    // The data is ONE route, `GET /api/today/cockpit` (backend
    // `jarvis_today.py`; docs/JARVIS-API.md section 82.7): due reminders, the
    // first open step of each active goal and project work list, and the
    // said-I'd-do proposals with their own opt-in switch. Nothing here creates
    // anything: a proposal's one tap only copies a "Remind me to ..." prompt
    // for the owner to paste into the chat themselves, and NOTHING is read
    // while the private lists are hidden - the board asks with `?hidden=1`
    // and the PC answers with no words at all ([cockpitPath]).
    //
    // It is a READ, so a stale link never blanks it (rule 4 is about acting);
    // the only writes are the switch's POST and a due reminder's Snooze, and
    // both are held on a stale link like every change.

    const val COCKPIT_PATH = "/api/today/cockpit"

    /** How often the switch is re-read while its approval card is up. */
    const val POLL_MS = 2_000L

    /** A little over the PC gate's own 180-second approval timeout. */
    const val GIVE_UP_MS = 200_000L

    /** The board's own GET; the PC withholds every word while [hidden]. */
    fun cockpitPath(hidden: Boolean): String =
        if (hidden) "$COCKPIT_PATH?hidden=1" else COCKPIT_PATH

    /** The board's own switch body: `{"enabled": true|false}`. */
    fun unspokenBody(enabled: Boolean): String = "{\"enabled\":$enabled}"

    /** The sections' words (`today.js`). */
    const val DUE_TITLE = "Due now"
    const val DUE_DETAIL =
        "Reminders, alarms and timers whose time has come, or that went off in the last hour."
    const val NEXT_TITLE = "Next steps"
    const val NEXT_DETAIL =
        "The first step of each goal you are working on, and of each project's work list."
    const val PROPOSALS_TITLE = "You said you would"
    const val PROPOSALS_DETAIL =
        "Things your own words said you would do, that no reminder covers yet. Nothing is " +
            "created until you act on one."
    const val PROPOSALS_OFF =
        "Said-I'd-do suggestions are off. Turning them on asks for your approval first: " +
            "Jarvis reads your own words in recent chats (never an incognito or crisis chat)."
    const val PROPOSALS_EMPTY = "Nothing new you said you would do."
    const val PROPOSALS_ON_LABEL = "Turn on (asks first)"
    const val PROPOSALS_OFF_LABEL = "Turn off"
    const val PROPOSALS_WAITING = "Waiting for your approval. Nothing has changed yet."
    const val PROPOSALS_TURNED_ON = "Said-I'd-do suggestions are on."
    const val PROPOSALS_TURNED_OFF = "Said-I'd-do suggestions are off."

    /** A due reminder's own controls; the copy is a private clipboard write. */
    const val DO_THIS_LABEL = "⚡ Do This With Jarvis"
    const val DO_THIS_COPIED = "Prompt copied - paste it into the Jarvis bar."
    const val BREAK_LABEL = "✨ Break Into 3 Easy Steps"
    const val BREAK_COPIED = "Prompt copied - paste it into the Jarvis bar to break it up."
    const val SNOOZE_LABEL = "⏱ Snooze"
    const val SENSITIVE_NOTE = "Sensitive: Jarvis will not offer to break this into steps."
    const val REMIND_LABEL = "Remind me…"

    /**
     * The board's own read FAILED: never drawn as a clear day (silent-failure
     * audit 2026-10-27, row 5 - the desktop's `BOARD_UNREADABLE`). An empty
     * page would be a claim the phone cannot make.
     */
    const val BOARD_UNREADABLE =
        "Jarvis could not read today's board from your PC. That does not mean nothing is " +
            "due - it means this page could not ask. Try again in a moment."

    /** One due reminder, as `due_reminders` sends it. */
    data class Due(
        val id: String,
        val kind: String,
        val text: String,
        val whenShown: String,
        val wentOff: Boolean,
        val overdue: Boolean,
        val sensitive: Boolean,
        val stuckHint: Boolean,
        val suggestedPrompt: String,
    ) {
        /** A card whose words the PC withheld (or an empty one) says so. */
        val hidden: Boolean get() = text.isEmpty()

        /** The row's tag: the job's kind, or "reminder" when it says none. */
        val tag: String get() = kind.ifEmpty { "reminder" }

        val title: String get() = if (hidden) "(hidden) reminder" else text

        /** "Went off (07:00)" / "Overdue - 07:00" / "07:00" - in this order. */
        val meta: List<String>
            get() = when {
                wentOff -> listOf(if (whenShown.isEmpty()) "Went off" else "Went off ($whenShown)")
                overdue -> listOf(if (whenShown.isEmpty()) "Overdue" else "Overdue - $whenShown")
                whenShown.isNotEmpty() -> listOf(whenShown)
                else -> emptyList()
            }

        /** The prompt behind "Do This" - the PC's own, else the fixed one. */
        fun prompt(): String =
            if (!hidden && suggestedPrompt.isNotBlank()) suggestedPrompt else doThisPrompt(text)

        /** The prompt behind Break, only when the PC said it may show. */
        fun breakPrompt(): String? =
            if (!hidden && stuckHint && !sensitive) breakStepsPrompt(text) else null
    }

    /** The first open step of one active goal or project work list. */
    data class Step(
        val id: String,
        val kind: String,
        val name: String,
        val step: String,
        val by: String,
    ) {
        val tag: String get() = if (kind == "project") "project" else "goal"
        val title: String get() = step
        /** The project's "work list" first, then its name, then the date. */
        val meta: List<String>
            get() = buildList {
                if (kind == "project") add("work list")
                if (name.isNotEmpty()) add(name)
                if (by.isNotEmpty()) add(by)
            }
    }

    /** A "you said you would" proposal: words, and a good day for it. */
    data class Proposal(val text: String, val suggestedDue: String) {
        val meta: List<String>
            get() = if (suggestedDue.isEmpty()) emptyList() else listOf("a good day: $suggestedDue")
        fun prompt(): String = remindPrompt(this)
    }

    /** `GET /api/today/cockpit`'s answer, read into what the board draws. */
    data class Cockpit(
        val available: Boolean,
        val hidden: Boolean,
        val unspokenEnabled: Boolean,
        val due: List<Due>,
        val steps: List<Step>,
        val proposals: List<Proposal>,
    )

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.flag(key: String): Boolean =
        (this[key] as? JsonPrimitive)?.booleanOrNull == true

    private fun JsonArray.objects(): List<JsonObject> = mapNotNull { it as? JsonObject }

    /** The board answer, or null when the body is not the board at all. */
    fun cockpit(answer: JsonObject): Cockpit? {
        val available = answer["available"]?.let { (it as? JsonPrimitive)?.booleanOrNull } ?: true
        if (!available) return Cockpit(false, false, false, emptyList(), emptyList(), emptyList())
        val hidden = answer.flag("hidden")
        val due = (answer["due_reminders"] as? JsonArray)?.objects().orEmpty().map {
            Due(
                id = it.str("id").orEmpty(),
                kind = it.str("kind").orEmpty(),
                text = it.str("text").orEmpty(),
                whenShown = it.str("when").orEmpty(),
                wentOff = it.flag("went_off"),
                overdue = it.flag("overdue"),
                sensitive = it.flag("sensitive"),
                stuckHint = it.flag("stuck_hint"),
                suggestedPrompt = it.str("suggested_prompt").orEmpty(),
            )
        }
        val steps = (answer["active_next_steps"] as? JsonArray)?.objects().orEmpty()
            .filter { !it.str("step").isNullOrBlank() }
            .map {
                Step(
                    id = it.str("id").orEmpty(),
                    kind = it.str("kind").orEmpty(),
                    name = it.str("name").orEmpty(),
                    step = it.str("step").orEmpty(),
                    by = it.str("by").orEmpty(),
                )
            }
        val proposals = (answer["proposals"] as? JsonArray)?.objects().orEmpty()
            .filter { !it.str("text").isNullOrBlank() }
            .map { Proposal(text = it.str("text").orEmpty(), suggestedDue = it.str("suggested_due").orEmpty()) }
        return Cockpit(
            available = true,
            hidden = hidden,
            unspokenEnabled = answer.flag("unspoken_commitments_enabled"),
            due = due,
            steps = steps,
            proposals = proposals,
        )
    }

    /** The board's proposals, as rows - none at all while the shelf is OFF. */
    fun proposalRows(cockpit: Cockpit): List<Proposal> =
        if (cockpit.unspokenEnabled) cockpit.proposals else emptyList()

    /** "Help me with this reminder: ..." - today.js's own fallback. */
    fun doThisPrompt(text: String): String {
        val t = text.trim()
        return if (t.isEmpty()) "Help me with a reminder that is due." else "Help me with this reminder: $t."
    }

    /** "Help me break this into 3 easy steps: ..." */
    fun breakStepsPrompt(text: String): String {
        val t = text.trim()
        return if (t.isEmpty()) {
            "Help me break a reminder down into 3 easy steps."
        } else {
            "Help me break this into 3 easy steps: $t."
        }
    }

    /** "Remind me to ..." for a proposal; the owner still sends it themselves. */
    fun remindPrompt(proposal: Proposal): String {
        val text = proposal.text.trim()
        val due = proposal.suggestedDue.trim()
        if (text.isEmpty()) return "Remind me to do the thing I mentioned."
        return if (due.isEmpty()) "Remind me to $text." else "Remind me to $text ($due)."
    }

    /**
     * What the switch's answer means. [waiting] means ONE approval card is up
     * and nothing has changed; [enabled] is what the PC says the switch now is.
     */
    data class SwitchSaid(val text: String, val waiting: Boolean, val enabled: Boolean)

    fun switchSaid(answer: JsonObject): SwitchSaid {
        val message = answer.str("message")
        val waiting = answer.flag("waiting")
        val enabled = answer.flag("enabled")
        val text = message ?: when {
            waiting -> PROPOSALS_WAITING
            enabled -> PROPOSALS_TURNED_ON
            else -> PROPOSALS_TURNED_OFF
        }
        return SwitchSaid(text = text, waiting = waiting, enabled = enabled)
    }

    /** A 503's own sentence from its body (`{"available": false, "why": ...}`), if any. */
    fun whySentence(body: String): String? =
        runCatching {
            val obj = JarvisJson.parseToJsonElement(body) as? JsonObject ?: return@runCatching null
            obj.str("why") ?: obj.str("error")
        }.getOrNull()

    /**
     * Why the board is not drawn, in a plain sentence - or null when there is
     * nothing to say because this PC simply has no board (an older install:
     * the desktop draws nothing for that either, and a sentence would be a
     * claim about an answer nobody gave).
     */
    fun boardFailure(error: ApiError): String? = when (error) {
        ApiError.NotFound, ApiError.NotAvailable -> null
        is ApiError.Server ->
            if (error.code == 501) null
            else if (error.code == 503) whySentence(error.body) ?: BOARD_UNREADABLE
            else BOARD_UNREADABLE
        else -> BOARD_UNREADABLE
    }

    /** `{"enabled": true}` is a real answer; anything else is not. */
    fun switchAnswer(answer: JsonObject): Boolean =
        (answer["ok"] as? JsonPrimitive)?.booleanOrNull != false
}
