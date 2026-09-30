package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * "People and things" - a plain grouped LIST of the people, pets, places,
 * organisations, projects and things Jarvis's saved facts name, and the
 * facts behind each (the owner's decision of 2026-09-30,
 * docs/GALAXY-PANEL-DESIGN.md sections 4 and 7, option B).
 *
 * It is NOT the Galaxy or the memory graph: no picture, no links between
 * names, no merging. The desktop draws the Galaxy; the phone gets this list
 * only, so the standing rule "no memory graph on the phone" stays true in
 * spirit.
 *
 * Two existing reads, no new route, nothing stored on the phone:
 * - `GET /api/memory/entities` - one entry per name, with `fact_ids` (newest
 *   first) and a count; no words. It already leaves out names linked only to
 *   an Off topic's facts.
 * - `GET /api/memory/used?ids=` ([MemoryUsed]) - the words, 20 ids at a time
 *   (never more than [MemoryUsed.MAX]). A fact whose topic is Off comes back
 *   with `left_out: true` and no words; it is dropped here and only counted
 *   ([topicsHiddenLine]).
 *
 * The count on a row is `fact_ids.size`, counted by code. The list is a memory
 * list: it hides under "Hide memory lists and chat history" like the others
 * (the plate does that). Read-only: no Forget, Erase or Pin here.
 *
 * The words are the shared fixture's (`contract/galaxy-cases.json`, written by
 * tools/gen_galaxy_cases.py); `EntitiesTest` holds them equal. Pure Kotlin,
 * no Android types.
 */
object Entities {
    const val PATH = "/api/memory/entities"

    /** The fixture's page size: how many facts one "Show 20 more" reads. */
    const val PAGE_SIZE = 20

    // The section's own words (not in the fixture, which fixes the panel's).
    const val TITLE = "People and things"
    const val UNDER =
        "The people, pets, places and things your saved facts name. Tap a name to read the facts behind it."
    const val EMPTY = "No names yet. They appear as Jarvis saves facts about people and things."
    const val MISSING =
        "Your PC's Jarvis cannot list these names yet - run apply-patches.ps1 on the PC to update it."
    const val BACK = "Back to the list"

    // The panel's words, word for word from the fixture (`words`).
    const val PANEL = "Facts behind this dot ({count})"
    const val MORE = "Show 20 more"
    const val SHOWING = "Showing {n} of {total}"
    const val READING = "Reading the facts..."
    const val ERASED = "Erased. Only the dates are kept."
    const val FORGOTTEN = "Forgotten"
    const val PINNED = "Pinned"
    const val HIDDEN = "Hidden. Show memory lists to see these facts."
    const val NO_FACTS = "No facts to show."
    const val FAILED = "Your PC could not read these facts."
    const val RETRY = "Try again"
    const val OPEN_IN_MEMORY = "Open in Memory"
    const val TOPICS_HIDDEN = "{n} hidden by topic settings"

    /** Every fixture key and its words, so the test can hold them equal. */
    val WORDS: Map<String, String> = mapOf(
        "galaxy_panel" to PANEL,
        "galaxy_panel_more" to MORE,
        "galaxy_panel_showing" to SHOWING,
        "galaxy_panel_reading" to READING,
        "galaxy_panel_erased" to ERASED,
        "galaxy_panel_forgotten" to FORGOTTEN,
        "galaxy_panel_pinned" to PINNED,
        "galaxy_panel_hidden" to HIDDEN,
        "galaxy_panel_empty" to NO_FACTS,
        "galaxy_panel_failed" to FAILED,
        "galaxy_panel_retry" to RETRY,
        "galaxy_panel_open" to OPEN_IN_MEMORY,
        "galaxy_panel_topics_hidden" to TOPICS_HIDDEN,
    )

    fun heading(count: Int): String = PANEL.replace("{count}", count.toString())
    fun showingLine(n: Int, total: Int): String =
        SHOWING.replace("{n}", n.toString()).replace("{total}", total.toString())
    fun topicsHiddenLine(n: Int): String? =
        if (n <= 0) null else TOPICS_HIDDEN.replace("{n}", n.toString())

    /** "1 fact" / "4 facts". */
    fun factCount(n: Int): String = if (n == 1) "1 fact" else "$n facts"

    /** One list row's words: "Priya, 4 facts". */
    fun rowLine(e: Entity): String = e.name + ", " + factCount(e.count)

    // ------------------------------------------------------------ groups ---

    /** The groups, in the order the list shows them: heading, and the `kind`s in it. */
    private val GROUPS: List<Pair<String, Set<String>>> = listOf(
        "People" to setOf("person"),
        "Pets" to setOf("pet"),
        "Places" to setOf("place"),
        "Organisations" to setOf("organisation"),
        "Projects" to setOf("project"),
        "Things" to setOf("thing"),
    )
    const val OTHER = "Other"

    val GROUP_TITLES: List<String> = GROUPS.map { it.first } + OTHER

    /** A name, its kind (null when the PC has none) and the facts that name it. */
    data class Entity(
        val id: String,
        val name: String,
        val kind: String?,
        /** The fact ids, newest first, as the PC sent them. */
        val factIds: List<Long>,
    ) {
        /** Counted here from the ids, never from anything a model said. */
        val count: Int get() = factIds.size
    }

    data class Group(val title: String, val entities: List<Entity>)

    /**
     * `GET /api/memory/entities`, read - or null when it is not that answer
     * (no `entities` array). An entry without a name or without any whole-number
     * fact id is dropped (nothing to show behind it); ids are kept once each, in
     * the order sent. A PC that predates `kind` puts every name under "Other".
     */
    fun parse(body: JsonObject): List<Entity>? {
        val raw = body["entities"] as? JsonArray ?: return null
        return raw.mapIndexedNotNull { i, el ->
            val o = el as? JsonObject ?: return@mapIndexedNotNull null
            val name = o.text("name")?.trim().orEmpty()
            if (name.isEmpty()) return@mapIndexedNotNull null
            val ids = LinkedHashSet<Long>()
            (o["fact_ids"] as? JsonArray).orEmpty().forEach { v ->
                val n = (v as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.longOrNull
                if (n != null && n > 0) ids.add(n)
            }
            if (ids.isEmpty()) return@mapIndexedNotNull null
            val idText = (o["id"] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull ?: "#$i"
            Entity(idText, name, o.text("kind")?.lowercase(), ids.toList())
        }
    }

    /**
     * The list, grouped by kind: People, Pets, Places, Organisations, Projects,
     * Things, then Other (a null or unknown kind). Within a group the name with
     * the most facts comes first, then by name. A group with no names is left out.
     */
    fun groups(entities: List<Entity>): List<Group> {
        val known = GROUPS.flatMap { it.second }.toSet()
        val order = compareByDescending<Entity> { it.count }.thenBy { it.name.lowercase(Locale.ROOT) }
        val out = GROUPS.mapNotNull { (title, kinds) ->
            entities.filter { it.kind in kinds }.sortedWith(order).takeIf { it.isNotEmpty() }
                ?.let { Group(title, it) }
        }.toMutableList()
        entities.filter { it.kind == null || it.kind !in known }.sortedWith(order)
            .takeIf { it.isNotEmpty() }?.let { out.add(Group(OTHER, it)) }
        return out
    }

    // ------------------------------------------------------------ facts ----

    /** The next page of ids to read: after the [shown] already consumed, at most [size]. */
    fun pageIds(e: Entity, shown: Int, size: Int = PAGE_SIZE): List<Long> =
        e.factIds.drop(shown.coerceAtLeast(0)).take(size.coerceIn(1, MemoryUsed.MAX))

    /** True while [shown] of the ids have been consumed and more remain. */
    fun hasMore(e: Entity, shown: Int): Boolean = shown < e.factIds.size

    /** One fact's row. [text] is "" for an erased fact ([erased]); the words are never shown then. */
    data class Row(
        val id: Long,
        val text: String,
        val erased: Boolean,
        val forgotten: Boolean,
        val pinned: Boolean,
        /** "12 Mar 2026" - when it was saved; null when the PC sent no date. */
        val saved: String?,
    )

    /** What one page of [MemoryUsed] facts came to: the rows, and how many Off-topic facts were dropped. */
    data class Page(val rows: List<Row>, val hiddenByTopic: Int)

    fun page(view: MemoryUsed.View, zone: ZoneId = ZoneId.systemDefault()): Page {
        val rows = view.facts.filterNot { it.leftOut }.map { f ->
            val erased = f.erasedAt != null
            Row(
                id = f.id,
                text = if (erased) "" else f.text,
                erased = erased,
                forgotten = !f.current && !erased,
                pinned = f.pinned,
                saved = dateText(f.created, zone),
            )
        }
        return Page(rows, view.facts.count { it.leftOut })
    }

    /** Current facts first, then forgotten and erased ones; each keeps its newest-first order. */
    fun arrange(rows: List<Row>): List<Row> = rows.filter { !it.forgotten && !it.erased } +
        rows.filter { it.forgotten || it.erased }

    /** Seconds since 1970 as "12 Mar 2026", or null for none. */
    fun dateText(epochSeconds: Double?, zone: ZoneId = ZoneId.systemDefault()): String? {
        if (epochSeconds == null || !epochSeconds.isFinite() || epochSeconds <= 0) return null
        return runCatching {
            DateTimeFormatter.ofPattern("d MMM yyyy", Locale.ENGLISH)
                .format(Instant.ofEpochSecond(epochSeconds.toLong()).atZone(zone))
        }.getOrNull()
    }

    /** A read that failed because this PC has no such route: a 404 or a 501. */
    fun missing(error: ApiError): Boolean = MemoryUsed.missing(error)

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
