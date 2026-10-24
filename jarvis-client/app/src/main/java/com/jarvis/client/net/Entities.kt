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
 * organisations, projects and things Jarvis's saved facts name, the facts
 * behind each, and the other names those same facts mention (the owner's
 * decision of 2026-09-30, docs/GALAXY-PANEL-DESIGN.md sections 4 and 7,
 * option B; the connections added 2026-10-11, see below).
 *
 * It is NOT the Galaxy's picture: no canvas, no force layout, no draggable
 * dots, no positions, no merging. The desktop draws the map; the phone draws
 * words.
 *
 * ## Why the phone shows connections but not a map (owner, 2026-10-11)
 *
 * The owner asked to see the Galaxy on the phone - "can i see the galaxy on
 * the android phone? I should be able to see it" - and, offered a choice,
 * picked "a light, read-only version built for the phone". What he wanted to
 * see is the same information the desktop's map carries: which people and
 * things Jarvis knows, how many facts each is in, and **who appears
 * alongside whom**. That last part is the map's edges, and it is the half a
 * plain list was missing.
 *
 * So the phone gets the map's *information* and not its *drawing*:
 * [connections] turns the same list into "the other names these facts
 * mention", which is what a desktop line between two dots means, said in
 * words that fit a thumb-width column and a screen reader.
 *
 * **Read-only, and that is the owner's decision, not an oversight.** He
 * narrowed CLAUDE.md's "do not build ... the memory graph ... on the phone"
 * for this one screen: it shows, and that is all. There is no Forget, no
 * Erase, no Pin, no merge ("are these the same?"), no rename and no drag
 * here, and no way to make one - the plate has no write to call. A future
 * reader wondering why the app that offers Forget everywhere else offers
 * none here should read this paragraph first. The order to change it would
 * have to come from the owner; it is not a gap to fill.
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

    /**
     * A fact naming more names than this joins nothing: such a fact is a list,
     * and joining everything in it says nothing. The desktop's own number
     * (`galaxy-view.js` `MAX_NAMES_PER_FACT`), kept equal on purpose - two
     * apps drawing "who is connected to whom" must not disagree.
     */
    const val MAX_NAMES_PER_FACT = 12

    // The section's own words (not in the fixture, which fixes the panel's).
    const val TITLE = "People and things"
    const val UNDER =
        "The people, pets, places and things your saved facts name. Tap a name to read the facts behind it, and the other names those facts mention."
    /**
     * A fresh Jarvis has nothing to draw here, and the screen says so rather
     * than showing an empty list that reads like a fault. Deliberately NOT
     * "you have no memories": this list holds only the names that saved facts
     * mention, so a Jarvis that knows plenty about the owner but has never
     * saved a fact naming a person or thing is empty here too, and the words
     * must not claim otherwise.
     */
    const val EMPTY =
        "Nothing here yet. When a saved fact mentions a person, pet, place or thing, it appears here by name - and two names appear together when one fact mentions both."
    const val MISSING =
        "Your PC's Jarvis cannot list these names yet - run apply-patches.ps1 on the PC to update it."
    const val BACK = "Back to the list"

    // The connections' own words (2026-10-11). Phone-only, like TITLE and
    // UNDER above: the shared fixture holds the words BOTH apps say, and the
    // desktop's map draws its edges as lines rather than in words.
    const val WITH = "Shares facts with"
    const val ALONE = "No other name appears in this one's facts yet."
    const val ALONE_WHY =
        "The Galaxy joins two names when one saved fact mentions both, so this fills in as Jarvis learns."

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

    /**
     * Every line of text the list itself draws, top to bottom: each group's
     * heading followed by its rows. The plate draws exactly these strings, so a
     * test can hold what the owner sees without a Compose host - the same
     * trick `MemoryWords.statusRows` uses. The empty case and the section's own
     * words are not here: they are not rows.
     */
    fun drawnLines(entities: List<Entity>): List<String> =
        groups(entities).flatMap { g -> listOf(g.title) + g.entities.map { rowLine(it) } }

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

    // ------------------------------------------------------ connections ---

    /**
     * How many names each fact id is linked to, over the whole [entities]
     * list. Worked out once for all names rather than once per name: the panel
     * asks for one name's connections at a time, and rebuilding this from
     * scratch on each of them would walk the whole list every time.
     */
    fun namesPerFact(entities: List<Entity>): Map<Long, Int> {
        val out = HashMap<Long, Int>()
        for (e in entities) for (f in e.factIds) out[f] = (out[f] ?: 0) + 1
        return out
    }

    /**
     * The other names that appear in [one]'s facts, most shared facts first.
     * [perFact] is [namesPerFact]'s map for the same list.
     *
     * This is the desktop Galaxy's edge, in words: `galaxy-view.js`
     * `buildEntityGraph` joins two dots when one fact names both, and the line
     * is as strong as how many facts they share. Here, for one name, that is
     * "Priya, 4 shared facts".
     *
     * Worked out from the [entities] list ALONE, by intersecting `factIds` -
     * no fact's words, no third read, no `/api/graph`. `factIds` are already
     * de-duplicated by [parse], so the size of an intersection is a real count
     * of facts mentioning both names and never a repeated id.
     *
     * A fact naming more than [MAX_NAMES_PER_FACT] names is a list rather than
     * a connection ("shopping: milk, eggs, bread"), so it joins nothing - the
     * desktop's own rule, kept here so the two apps agree on what an edge is.
     * Ties are broken by name, so the order never depends on the order the PC
     * happened to send.
     */
    fun connections(
        one: Entity,
        entities: List<Entity>,
        perFact: Map<Long, Int> = namesPerFact(entities),
    ): List<Connection> {
        if (one.factIds.isEmpty()) return emptyList()
        val mine = one.factIds.toHashSet()
        return entities.asSequence()
            .filter { it.id != one.id }
            .mapNotNull { other ->
                val shared = other.factIds.count { it in mine && (perFact[it] ?: 0) <= MAX_NAMES_PER_FACT }
                if (shared > 0) Connection(other, shared) else null
            }
            .sortedWith(
                compareByDescending<Connection> { it.shared }
                    .thenBy { it.entity.name.lowercase(Locale.ROOT) },
            )
            .toList()
    }

    /** One name that shares facts with the name on screen, and how many. */
    data class Connection(val entity: Entity, val shared: Int)

    /** "4 shared facts" / "1 shared fact" - the desktop's `sharedWords`, for one row. */
    fun sharedWords(n: Int): String = if (n == 1) "1 shared fact" else "$n shared facts"

    /** One connection's row: "Priya, 4 shared facts". */
    fun connectionLine(c: Connection): String = c.entity.name + ", " + sharedWords(c.shared)

    // ------------------------------------------- the phone's list tools ---
    // A1 (2026-10-21): kind filter chips, a search over names, the
    // shared-facts count on a row, and the as-of chips. Phone-only words, for
    // the same reason TITLE, UNDER and WITH above are: the shared fixture holds
    // the words BOTH apps say, and the desktop's map draws no chips.

    const val ALL = "All"
    const val SEARCH = "Search names"
    const val AS_OF = "Facts as of"
    const val NOW = "Now"
    const val WEEK = "7d"
    const val MONTH = "30d"
    const val PICK_DATE = "Pick date…"
    const val DATE_HINT = "YYYY-MM-DD"
    const val DATE_BAD = "Use a real date, on or before today, like 2026-10-21."
    const val NO_MATCH = "No names match that search."
    const val AS_OF_NONE = "No active facts on {date}."
    const val AS_OF_ROW = "{name}, {n} on {date}"
    const val RETIRED = "No longer true then"
    const val SHARES = "Shares facts with {n} names"
    const val SHARES_ONE = "Shares facts with 1 name"
    const val AS_OF_READING = "Reading the facts for that date..."
    const val USE_DATE = "Use this date"
    const val CANCEL = "Cancel"

    /** The chips under the search box: All, then each known kind, then Other
     * only when the list really holds a name whose kind is unknown. */
    fun filterLabels(entities: List<Entity>): List<String> {
        val known = GROUPS.map { it.first }
        return listOf(ALL) + known +
            (if (entities.any { it.kind == null || it.kind !in KNOWN_KINDS }) listOf(OTHER) else emptyList())
    }

    private val KNOWN_KINDS: Set<String> = GROUPS.flatMap { it.second }.toSet()

    private fun kindsOf(label: String): Set<String>? = when (label) {
        ALL, "" -> null
        OTHER -> null
        else -> GROUPS.firstOrNull { it.first == label }?.second
    }

    /**
     * The names a chip and a search leave on screen: the same list, filtered by
     * kind (the chip) and by name (the search, case-insensitive, and only the
     * NAME - never the facts' words). A blank chip and a blank search means
     * every entity, so the untouched list is what it was before A1.
     */
    fun visible(entities: List<Entity>, kind: String, query: String): List<Entity> {
        val q = query.trim()
        val wanted = kindsOf(kind)
        val other = kind == OTHER
        return entities.filter { e ->
            val kindOk = when {
                wanted != null -> e.kind != null && e.kind in wanted
                other -> e.kind == null || e.kind !in KNOWN_KINDS
                else -> true
            }
            kindOk && (q.isEmpty() || e.name.contains(q, ignoreCase = true))
        }
    }

    /**
     * How many OTHER names each name shares at least one fact with, by entity
     * id - the same rule [connections] uses (a fact naming more than
     * [MAX_NAMES_PER_FACT] names is a list, not an edge), computed once for the
     * whole list instead of once per row. A row's second line says "Shares facts
     * with 2 names"; zero draws nothing.
     */
    fun sharedPartners(entities: List<Entity>): Map<String, Int> {
        val perFact = namesPerFact(entities)
        val namesByFact = HashMap<Long, MutableList<String>>()
        for (e in entities) for (f in e.factIds) {
            if ((perFact[f] ?: 0) > MAX_NAMES_PER_FACT) continue
            namesByFact.getOrPut(f) { ArrayList() }.add(e.id)
        }
        val out = HashMap<String, Int>(entities.size)
        for (e in entities) {
            val partners = HashSet<String>()
            for (f in e.factIds) namesByFact[f]?.forEach { id -> if (id != e.id) partners.add(id) }
            out[e.id] = partners.size
        }
        return out
    }

    /** "Shares facts with 2 names" / the singular; null for zero (no dead line). */
    fun sharesLine(n: Int): String? = when {
        n <= 0 -> null
        n == 1 -> SHARES_ONE
        else -> SHARES.replace("{n}", n.toString())
    }

    // --------------------------------------- the Galaxy band (2026-10-23) ---
    // The owner's choice for the phone's Galaxy (2026-10-23): a read-only
    // "Galaxy at a glance" band above this list, instead of a canvas. It reads
    // nothing new: the names and their facts are the two reads the plate
    // already makes, and the connections are the same [sharedPartners] rule
    // the rows already say in words. Phone-only words, like the A1 chips.
    const val GALAXY_TITLE = "Galaxy at a glance"
    const val GALAXY_TOP = "Most connected"

    /** "32 names, 118 facts" - the band's one-line summary. */
    fun galaxySummary(names: Int, facts: Int): String {
        val n = if (names == 1) "1 name" else "$names names"
        return n + ", " + factCount(facts)
    }

    /**
     * Every DISTINCT fact the plate holds - one number, no double counting.
     *
     * One fact can name more than one person or thing ("Priya and Dan live in
     * Portugal" is one fact behind two names), so adding each name's own count
     * would count that fact once per name. The headline would then be
     * "name-fact links", which cannot be reconciled with what Jarvis holds
     * whenever two names share a fact - exactly the case the Galaxy exists to
     * show (AND-2, found 2026-10-24). The per-name count on a row is left as it
     * was, because "Priya, 2 facts" is true on its own.
     */
    fun totalFacts(entities: List<Entity>): Int =
        entities.flatMap { it.factIds }.toHashSet().size

    /**
     * Up to [limit] names with the most shared names, best first: the same
     * [sharedPartners] rule the rows already use. Ties go to the name with more
     * facts, then by name, so the order never depends on the order the PC sent.
     * A name that shares no fact is not in the band - there would be nothing to
     * connect it to. Empty list when there are no names.
     */
    fun mostConnected(entities: List<Entity>, limit: Int = 8): List<Entity> {
        if (limit <= 0) return emptyList()
        val partners = sharedPartners(entities)
        return entities
            .filter { (partners[it.id] ?: 0) > 0 }
            .sortedWith(
                compareByDescending<Entity> { partners[it.id] ?: 0 }
                    .thenByDescending { it.count }
                    .thenBy { it.name.lowercase(Locale.ROOT) },
            )
            .take(limit)
    }

    /**
     * What the band says for one name, for the screen reader and the label:
     * "Priya, 4 facts, shares facts with 2 names". The shares half is left out
     * when [shared] is zero, so a label never promises an edge that is not there.
     */
    fun galaxyNameLine(e: Entity, shared: Int): String {
        val base = rowLine(e)
        if (shared <= 0) return base
        val shares = if (shared == 1) "shares facts with 1 name"
        else "shares facts with $shared names"
        return "$base, $shares"
    }

    // ------------------------------------------------------------- as of ---

    /** "Facts as of 12 Oct 2026" for the chip row's own heading. */
    fun asOfLine(date: String): String = "$AS_OF $date"

    /** "Priya, 2 on 12 Oct 2026" - a row's count as of a date. */
    fun asOfRowLine(e: Entity, date: String): String =
        AS_OF_ROW.replace("{name}", e.name)
            .replace("{n}", factCount(e.count))
            .replace("{date}", date)

    /** The plain line when no name had an active fact on that date. */
    fun asOfNone(date: String): String = AS_OF_NONE.replace("{date}", date)

    /**
     * The SAME list, with each name's fact ids narrowed to the facts the PC says
     * were active on that date (`current = true` as of that moment). This is the
     * client-side filter the A1 slice promises: no second entity route, no new
     * server query, and a name with no active fact on the date drops out. A
     * retired fact (`current = false`) is not counted here; [asOfRows] shows it
     * muted when the name is opened.
     */
    fun asOfEntities(entities: List<Entity>, facts: List<MemoryAsOf.RawFact>): List<Entity> {
        val active = facts.asSequence().filter { it.trueThen == true }.map { it.id }.toHashSet()
        if (active.isEmpty()) return emptyList()
        return entities.mapNotNull { e ->
            val ids = e.factIds.filter { it in active }
            if (ids.isEmpty()) null else e.copy(factIds = ids)
        }
    }

    /**
     * The as-of rows the plate may draw for [epoch], or null while it has none
     * for THAT date: [rows] is returned only when [rowsEpoch] says they were
     * read for exactly that epoch.
     *
     * A date chip changes the heading at once, but the facts are a second read
     * that can be slow or can fail. Keeping the rows apart from the date they
     * belong to is what let "7d"'s facts sit under "30d"'s label (AND-1, found
     * 2026-10-24); this gate is the one rule that makes that impossible - on
     * the frame before the new read starts, and when the read fails too.
     */
    fun asOfFactsFor(
        epoch: Long?,
        rows: List<MemoryAsOf.RawFact>?,
        rowsEpoch: Long?,
    ): List<MemoryAsOf.RawFact>? = if (epoch != null && rowsEpoch == epoch) rows else null

    /** What one name's as-of facts came to: the ones that were true then, and
     * the retired ones (drawn muted under [RETIRED]), in the PC's newest-first
     * order from the name's own fact ids. */
    data class AsOfRows(val active: List<Row>, val retired: List<Row>)

    fun asOfRows(
        entity: Entity,
        facts: List<MemoryAsOf.RawFact>,
        zone: ZoneId = ZoneId.systemDefault(),
    ): AsOfRows {
        val byId = facts.associateBy { it.id }
        val active = ArrayList<Row>()
        val retired = ArrayList<Row>()
        for (id in entity.factIds) {
            val f = byId[id] ?: continue
            val erased = f.erasedAt != null
            val row = Row(
                id = id,
                text = if (erased) "" else f.text,
                erased = erased,
                forgotten = false,
                pinned = false,
                saved = dateText(f.created, zone),
            )
            if (f.trueThen == false) retired.add(row) else active.add(row)
        }
        return AsOfRows(active, retired)
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
