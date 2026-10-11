package com.jarvis.client.net

import com.jarvis.client.SectionRead
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * The desktop's Content risk panel, read-only, as the phone draws it
 * (`brain.html`:901's card, `brain.js`'s `renderContentRisk`).
 *
 * WHY THIS EXISTS. `/api/content-risk` has been read by this app since the
 * Brain screen got its rush banner, and [com.jarvis.client.BrainSnapshot]
 * carries the whole answer - but until now the phone drew only the LATCH (the
 * banner) and threw the rest away, so the list of text the scanner flagged
 * could not be read anywhere on the phone. The parity audit of 2026-10-10
 * found exactly that (GAP 7).
 *
 * WHAT THE ROUTE CARRIES (`jarvis_content_risk.status`, the same answer the
 * PC's card reads):
 *
 * ```
 * {"rush": {"until", "source", "phrase", "context", "count_today", "set"} | null,
 *  "pins": [{"kind", "key", "sha", "first", "last", "approvals",
 *            "cumulative_drift"}],
 *  "config": {...}}
 * ```
 *
 * A pin is a skill or an MCP tool description whose full current text a person
 * has read and approved; it is the record that lets the scanner notice the
 * text drifting afterwards. It is the INSTRUCTIONS' text, never the owner's own
 * data - but the list is still the owner's own record of what Jarvis has been
 * told to do, so it hides under "Hide memory lists and chat history" with every
 * other list of that kind ([body]'s `hidden`).
 *
 * UNTYPED ON PURPOSE, like [com.jarvis.client.BrainSnapshot]: the API doc says
 * the route exists and what it is for, not what its fields are called, so a
 * data class here would be invented keys - and invented keys fail silently as
 * an empty panel. Every field is therefore read by the name the PC's own code
 * uses, and the two names the DESKTOP reads (`name`, `source`, `at`, `digest`)
 * are accepted beside the ones `pinned()` really sends, because the PC and this
 * phone ship on different schedules and neither may go blank while they differ.
 *
 * Pure Kotlin, no Android types, so a plain JVM test can hold every branch of
 * [body] - including the two the audit asked about by name: the list draws when
 * there is one, and an empty list says so instead of drawing a blank block.
 */
object ContentRisk {

    /** `GET /api/content-risk` - read-only by design, on both apps. */
    const val PATH = "/api/content-risk"

    /** The card's own title, the desktop's word for it (`brain.html`). */
    const val TITLE = "Content risk"

    /**
     * The desktop's own note, word for word (`brain.html`:903-908). It is the
     * whole design of the panel in three lines, so it is not paraphrased here:
     * nothing on this card approves anything or clears a latch.
     */
    const val NOTE =
        "Read-only, deliberately. Nothing here approves a tool description or clears a rush " +
            "latch: approving means a person read the full current text, and that happens " +
            "where the scanner runs."

    /** The desktop's line for a latch that is set (`renderContentRisk`). */
    const val RUSH_ON = "A rush latch is active — outside text tried to hurry a decision."

    /** ...and for one that is not. */
    const val RUSH_OFF = "No rush latch active."

    /** The desktop's closing line about the latch, word for word. */
    const val RUSH_TAIL = "It expires on its own. There is deliberately no control here that clears it."

    /** The heading over the list, and the line that replaces it when it is empty. */
    const val PINNED_HEADING = "Pinned text"
    const val NOTHING_PINNED =
        "Nothing pinned. A skill or MCP tool description is pinned when a person has read its " +
            "full current text."

    const val READING = "Reading…"

    /** 404 or 503: a PC whose Jarvis has no scanner. A fact about the PC, not a fault. */
    const val NOT_HERE = "Your PC's Jarvis does not have the content-risk scanner yet."

    /** Anything else, in the app's own shape: what failed, and a Retry beside it. */
    fun failed(reason: String): String = "Couldn't read the content risk list: $reason"

    /**
     * The rush latch, in the four things the card shows about it. `text` and
     * `quote` are read beside `phrase` for the same reason the Brain banner
     * reads both: `jarvis_content_risk` lives only on the owner's PC, the
     * desktop read `phrase` while the phone's banner read `quote`, and nothing
     * on this side can say which one a given PC sends.
     */
    data class Rush(
        /** The latch's own sentence when the PC sends one, else [RUSH_ON]. */
        val text: String,
        /** The attacker's own words, quoted on screen. Null when the PC sent none. */
        val phrase: String?,
        /** Named, never quoted - a source string is attacker-controlled. */
        val source: String?,
        /** How many times this source tripped the rule today, or 0 when unknown. */
        val countToday: Int,
    )

    /**
     * One pinned text: identified by name, with how long ago it was approved and
     * the start of its digest. `atMs` is 0 when the PC sent no time, and the
     * plate then shows no time rather than inventing "just now".
     */
    data class Pin(
        val title: String,
        val kind: String,
        val atMs: Long,
        val digest: String,
        val approvals: Int,
    )

    /**
     * What the plate draws, decided here so a JVM test can hold it: hidden by
     * the owner's own setting, still reading, not on this PC, a failed read with
     * its reason, or the list itself.
     */
    sealed interface Body {
        /** "Hide memory lists and chat history" is on: nothing of it is drawn. */
        data object Hidden : Body
        data object Reading : Body
        data object NotHere : Body
        data class Failed(val reason: String) : Body
        data class Ready(val rush: Rush?, val pins: List<Pin>) : Body
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    /**
     * A number, read the way [Limits] reads one: through the primitive's own
     * text rather than a typed accessor. The PC sends real JSON numbers, but a
     * route that quoted one (or a build of kotlinx-serialization that refuses a
     * numeric string) must not turn a time or a count into a silent zero.
     */
    private fun JsonObject.num(key: String): Long? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()?.toLong()

    /**
     * The latch, or null when none is set. `rush` arrives as JSON `null` when
     * no latch is active, which lands in the same branch as a missing field -
     * a latch that is not an object is not a latch.
     */
    fun rush(snapshot: JsonObject?): Rush? {
        val latch = snapshot?.get("rush") as? JsonObject ?: return null
        val count = latch.num("count_today")?.toInt() ?: 0
        return Rush(
            text = latch.str("text") ?: RUSH_ON,
            phrase = latch.str("phrase") ?: latch.str("quote"),
            source = latch.str("source"),
            countToday = count.coerceAtLeast(0),
        )
    }

    /**
     * Every pinned text the PC sent, in the PC's own order and never sorted
     * here: the route sorts by key, and re-sorting on the phone would be a
     * second opinion about an order the PC already decided.
     */
    fun pins(snapshot: JsonObject?): List<Pin> {
        val rows = snapshot?.get("pins") as? JsonArray ?: return emptyList()
        return rows.mapNotNull { element ->
            val p = element as? JsonObject ?: return@mapNotNull null
            // `key` is what `pinned()` really sends ("fake/inject" for
            // "mcp:fake/inject"); `name` and `source` are the two names the
            // desktop's renderer reads. A row with none of the three is still a
            // pin, so it is drawn as "(pinned)" rather than dropped - a pin that
            // vanished from a read-only list would be a lie about what is pinned.
            val title = p.str("name") ?: p.str("source") ?: p.str("key") ?: "(pinned)"
            val kind = p.str("kind").orEmpty()
            // Seconds since the epoch in both shapes (`last`, or the desktop's
            // `at`); 0 when neither is there.
            val at = p.num("last") ?: p.num("at") ?: 0L
            val digest = (p.str("sha") ?: p.str("digest")).orEmpty().take(12)
            Pin(
                title = title,
                kind = kind,
                atMs = if (at > 0L) at * 1000L else 0L,
                digest = digest,
                approvals = (p.num("approvals") ?: 0L).toInt().coerceAtLeast(0),
            )
        }
    }

    /**
     * What the plate draws. [hidden] wins over everything: the owner's "Hide
     * memory lists and chat history" is the reason this list exists in a hidden
     * form at all, and a read that has not happened yet must not leak it either.
     */
    fun body(
        snapshot: JsonObject?,
        read: SectionRead,
        hidden: Boolean,
    ): Body = when {
        hidden -> Body.Hidden
        read is SectionRead.Failed -> Body.Failed(read.reason)
        read == SectionRead.Absent -> Body.NotHere
        read == SectionRead.Reading -> Body.Reading
        else -> Body.Ready(rush = rush(snapshot), pins = pins(snapshot))
    }

    /**
     * The one line under [PINNED_HEADING]: [NOTHING_PINNED] when the PC has
     * pinned nothing, and null when the rows themselves are what is drawn.
     *
     * It is a function rather than a branch inside the plate so that "an empty
     * list says so" is a fact a JVM test can fail on - the blank block the audit
     * complained about was exactly a missing branch that no test could see.
     */
    fun pinnedSummary(pins: List<Pin>): String? = if (pins.isEmpty()) NOTHING_PINNED else null

    /**
     * One row's own line, under its title: what kind of thing it is, how long
     * ago it was approved (the plate adds the age words), and the start of its
     * digest - the desktop's own three fields, in its own order
     * (`renderContentRisk`).
     */
    fun pinLine(pin: Pin): String = buildString {
        if (pin.kind.isNotBlank()) append(pin.kind)
        if (pin.approvals > 1) {
            if (isNotEmpty()) append(" · ")
            append("approved ${pin.approvals} times")
        }
        if (pin.digest.isNotBlank()) {
            if (isNotEmpty()) append(" · ")
            append("digest ${pin.digest}")
        }
    }

    /** The latch's second line: who tripped it, and how often today. */
    fun rushSourceLine(rush: Rush): String? {
        val source = rush.source ?: return null
        val times = if (rush.countToday > 1) " · ${rush.countToday} times today" else ""
        return "from $source$times"
    }
}
