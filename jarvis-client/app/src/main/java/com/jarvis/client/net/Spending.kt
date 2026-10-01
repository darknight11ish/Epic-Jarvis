package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Spending summaries" (the owner's decision of 2026-09-30, queue item 2;
 * docs/JARVIS-API.md section 100; docs/FINANCE-DESIGN.md part A and its
 * frozen "Slice contract"): a bank export dropped into a folder Jarvis may
 * look in is added up by plain code on the PC and shown as a small table IN
 * THE CHAT. On the phone that is two things and nothing more:
 *
 *  - the table under the answer: the chat stream carries the comment line
 *    `: jarvis-table <32 hex>` right before the answer's sentence
 *    ([tableIdFromLine]); the phone fetches `GET /api/chat/table?id=`
 *    ([tablePath]) and draws what the PC sent ([parseTable]);
 *  - a read-only Brain plate that says "Set up on the PC" ([parseView],
 *    `GET /api/spending`). Column checks, saved layouts and the categories
 *    editor are the PC's alone (ARCHITECTURE section 8, "One-sided on
 *    purpose"): no editing code exists here.
 *
 * What this file never does, on purpose:
 *  - compute, add up, round, sort, re-format, re-word or hide a figure. Every
 *    string in a `cells` list is drawn exactly as the PC sent it. Nothing in
 *    here parses one as a number.
 *  - keep a table. It is held in memory by the screen that draws it and is
 *    never written to disk, saved state, a log, a copy or a share.
 *  - decide what is private: the table says `private: true` and the reading
 *    tool is not on the read-aloud list, so the existing rule keeps a spoken
 *    answer on screen ([com.jarvis.client.voice.PrivateAloud]).
 *
 * Pure Kotlin, no Android types, so [SpendingTest] runs it on a plain JVM
 * against `contract/spending-cases.json` (tools/gen_spending_cases.py, made
 * by the real backend code - byte for byte the file the desktop builds on).
 */
object Spending {
    const val TABLE_PATH = "/api/chat/table"
    const val VIEW_PATH = "/api/spending"

    /** The stream comment that announces a table; the id follows it. */
    const val STREAM_MARK = ": jarvis-table "

    // The shared words, copied from `spending-cases.json` -> `words`;
    // SpendingTest compares every one with the file.
    const val TITLE = "Spending"
    const val DETAIL =
        "Drop a bank export (CSV or Excel) into a folder Jarvis may look in, then ask in chat, for example " +
            "\"how much did I spend on food last month?\". Jarvis adds the numbers up with plain code and shows " +
            "a small table on screen. The table is never read aloud, never remembered and never sent " +
            "anywhere. Account and card numbers in the file are hidden."
    const val PC_ONLY = "Set up on the PC: Settings, Spending. The columns of a new bank file are checked there, once."
    const val NEEDS_SETUP_ON_PC =
        "Open Jarvis on the PC to check the columns of this bank file (Settings, Spending). " +
            "It takes a minute and is remembered."
    const val EMPTY_PROFILES = "No bank layouts saved yet."
    const val STARTER_NOTE = "These are starter categories. Change the words to suit the shops you use."
    const val TABLE_HIDDEN = "Spending table hidden"
    const val TABLE_GONE = "This table is no longer kept. Ask again to see it."

    /** Brain's plate on a PC too old to have the route (the phrase Folders uses). */
    const val MISSING = "Your PC's Jarvis cannot add up spending yet - run apply-patches.ps1 on the PC."

    /** Said when the PC's answer was not a table this app can read. */
    const val UNREADABLE = "The desktop sent something this app could not read."

    /** Said while the table is being fetched. */
    const val READING = "Reading…"

    // ---------------------------------------------------------------- stream

    private val ID = Regex("^[0-9a-f]{32}$")
    private val MARK = Regex("^:\\s*jarvis-table\\s+([0-9a-f]{32})\\s*$")

    /** A table id is exactly 32 lowercase hex characters, nothing else. */
    fun isTableId(id: String?): Boolean = id != null && ID.matches(id)

    /**
     * The id in a `: jarvis-table <id>` comment line, or null for any other
     * line (or an id of the wrong shape - it goes into a URL, so it is
     * checked before it is ever used).
     */
    fun tableIdFromLine(line: String): String? = MARK.find(line.trim())?.groupValues?.get(1)

    /** `/api/chat/table?id=<id>`, or null for an id of the wrong shape. */
    fun tablePath(id: String?): String? = if (isTableId(id)) TABLE_PATH + "?id=" + id else null

    /** A 404 from the table route: the PC no longer keeps it (`error: "gone"`). */
    fun gone(error: ApiError): Boolean = error == ApiError.NotFound

    /**
     * Whether the table is drawn or "Spending table hidden" stands in its
     * place, with NO fetch: "Hide memory lists and chat history" is on, or
     * App lock is locked. (On the phone a locked app draws no screen at all,
     * so the second half is a belt on top of that.)
     */
    fun hiddenNow(hideLists: Boolean, locked: Boolean): Boolean = hideLists || locked

    // ----------------------------------------------------------------- table

    data class Column(val key: String, val label: String, val rightAligned: Boolean)

    /** One row: [kind] is only a style hint; [cells] are drawn as they are. */
    data class Line(val kind: String, val cells: List<String>)

    /** One currency's block. Two currencies are two blocks, never merged. */
    data class Block(
        val heading: String,
        val currency: String,
        val rows: List<Line>,
        val totals: List<Line>,
        val also: List<Line>,
    )

    data class Table(
        val title: String,
        val period: String,
        val sources: List<String>,
        val columns: List<Column>,
        val blocks: List<Block>,
        val caveats: List<String>,
    )

    /** What one fetch came to. */
    sealed interface Read {
        data class Shown(val table: Table) : Read

        /** The PC no longer keeps it; [message] is the sentence to show. */
        data class Gone(val message: String) : Read

        data class Failed(val why: String) : Read
    }

    /**
     * `GET /api/chat/table` -> the table, or null when it is not one this app
     * knows how to draw. STRICT, exactly like the desktop's `readTable`
     * (audit 2026-09-30): `kind` "spending" and `version` the number 1 (no
     * version, "1" or 2 is not read); `title` and `period` text; `sources` and
     * `caveats` lists of text; at least one column, each with a text `key` and
     * `label` and an `align` of "left" or "right"; every section a
     * JSON object with text `heading` and `currency` and the three lists
     * `rows`, `totals` and `also`; every row an object with a text `kind` and
     * a `cells` list of TEXT (a number or null in a cell is not text) with
     * exactly one cell per column. Anything else is null: money drawn in the
     * wrong column, or a figure this app had to guess at, is worse than
     * nothing. Unknown extra fields are ignored.
     */
    fun parseTable(body: JsonObject): Table? {
        val t = body["table"] as? JsonObject ?: return null
        if (t.strictText("kind") != "spending") return null
        val v = t["version"] as? JsonPrimitive ?: return null
        if (v is JsonNull || v.isString || v.intOrNull != 1) return null
        val title = t.strictText("title") ?: return null
        val period = t.strictText("period") ?: return null
        val sources = strictStrings(t["sources"]) ?: return null
        val caveats = strictStrings(t["caveats"]) ?: return null

        val colArray = t["columns"] as? JsonArray ?: return null
        if (colArray.isEmpty()) return null
        val cols = mutableListOf<Column>()
        for (e in colArray) {
            val o = e as? JsonObject ?: return null
            val key = o.strictText("key") ?: return null
            val label = o.strictText("label") ?: return null
            val align = o.strictText("align") ?: return null
            if (align != "left" && align != "right") return null
            cols += Column(key = key, label = label, rightAligned = align == "right")
        }

        val sectionArray = t["sections"] as? JsonArray ?: return null
        val blocks = mutableListOf<Block>()
        for (s in sectionArray) {
            val o = s as? JsonObject ?: return null
            val heading = o.strictText("heading") ?: return null
            val currency = o.strictText("currency") ?: return null
            val rows = lines(o["rows"], cols.size) ?: return null
            val totals = lines(o["totals"], cols.size) ?: return null
            val also = lines(o["also"], cols.size) ?: return null
            blocks += Block(heading, currency, rows, totals, also)
        }
        return Table(
            title = title,
            period = period,
            sources = sources,
            columns = cols,
            blocks = blocks,
            caveats = caveats,
        )
    }

    /** Null when the list is missing, a row is not an object with text `kind`, its cells
     *  are not all text, or it has the wrong number of cells. */
    private fun lines(e: JsonElement?, columns: Int): List<Line>? {
        val list = e as? JsonArray ?: return null
        val out = mutableListOf<Line>()
        for (x in list) {
            val o = x as? JsonObject ?: return null
            val kind = o.strictText("kind") ?: return null
            val cells = strictStrings(o["cells"]) ?: return null
            if (cells.size != columns) return null
            out += Line(kind, cells)
        }
        return out
    }

    /** "From: a.csv, b.csv" under the table, or null with no sources. */
    fun sourcesLine(t: Table): String? =
        t.sources.takeIf { it.isNotEmpty() }?.let { "From: " + it.joinToString(", ") }

    // -------------------------------------------------------- screen reader

    /**
     * One row for TalkBack: its cells joined by commas, each figure after
     * its column's label ("Food and groceries, Spent 70.40, Rows 2"); a
     * totals row says "Total" first (the PC's own first cell is already
     * "Total spent", so it is not said twice). Only the cells as sent.
     */
    fun rowReading(t: Table, line: Line, isTotal: Boolean = false): String {
        val parts = line.cells.mapIndexed { i, c ->
            val label = if (i == 0) "" else t.columns.getOrNull(i)?.label.orEmpty()
            if (label.isEmpty()) c else "$label $c"
        }
        val said = parts.joinToString(", ")
        return if (isTotal && !line.cells.firstOrNull().orEmpty().startsWith("Total", ignoreCase = true)) {
            "Total, $said"
        } else {
            said
        }
    }

    /** The one line that stands for the whole table before its rows. */
    fun summary(t: Table): String {
        val rows = t.blocks.sumOf { it.rows.size + it.totals.size + it.also.size }
        return listOf(t.title, t.period).filter { it.isNotBlank() }.joinToString(". ") +
            ". Table with ${t.columns.size} columns and $rows rows."
    }

    // ------------------------------------------------------------ the plate

    data class Layout(val label: String, val columns: List<String>, val signSentence: String)

    data class Category(val name: String, val words: List<String>)

    /** `GET /api/spending`, read-only on the phone. */
    data class View(
        val title: String,
        val detail: String,
        val pcOnly: String,
        val layouts: List<Layout>,
        val emptyProfiles: String,
        val categories: List<Category>,
        val starterNote: String?,
        val waiting: List<String>,
        val needsSetup: String,
    )

    /** `GET /api/spending` -> the plate's words, or null when the module is not there. */
    fun parseView(body: JsonObject): View? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.booleanOrNull == false) return null
        val layouts = (body["profiles"] as? JsonArray)?.mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            Layout(o.text("label"), strings(o["columns"]), o.text("sign_sentence"))
        }.orEmpty()
        val cats = (body["categories"] as? JsonArray)?.mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val name = o.text("category")
            if (name.isEmpty()) null else Category(name, strings(o["words"]))
        }.orEmpty()
        val starter = (body["categories_are_starter"] as? JsonPrimitive)
            ?.takeIf { it !is JsonNull }?.booleanOrNull == true
        val waiting = (body["waiting"] as? JsonArray)?.mapNotNull { e ->
            (e as? JsonObject)?.text("name")?.takeIf { it.isNotEmpty() }
        }.orEmpty()
        return View(
            title = body.text("title").ifEmpty { TITLE },
            detail = body.text("detail").ifEmpty { DETAIL },
            pcOnly = body.text("pc_only").ifEmpty { PC_ONLY },
            layouts = layouts,
            emptyProfiles = body.text("empty_profiles").ifEmpty { EMPTY_PROFILES },
            categories = cats,
            starterNote = if (starter) body.text("starter_note").ifEmpty { STARTER_NOTE } else null,
            waiting = waiting,
            needsSetup = body.text("needs_setup").ifEmpty { NEEDS_SETUP_ON_PC },
        )
    }

    /** A PC without the route: an older backend, or the module missing (503). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 503))

    // --------------------------------------------------------------- helpers

    /** A string exactly as sent (no trimming - a figure is never touched). */
    private fun JsonObject.text(key: String): String = this[key].cell()

    private fun JsonElement?.cell(): String =
        (this as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content.orEmpty()

    /** A string that IS a JSON string (a number, a boolean, null or a missing key is not text). */
    private fun JsonObject.strictText(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && it.isString }?.content

    /** A list whose every element is a JSON string, else null. */
    private fun strictStrings(e: JsonElement?): List<String>? {
        val list = e as? JsonArray ?: return null
        val out = mutableListOf<String>()
        for (x in list) {
            val p = x as? JsonPrimitive ?: return null
            if (p is JsonNull || !p.isString) return null
            out += p.content
        }
        return out
    }

    private fun strings(e: JsonElement?): List<String> =
        (e as? JsonArray)?.mapNotNull { x ->
            (x as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
        }.orEmpty()
}
