package com.jarvis.client.net

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
}
