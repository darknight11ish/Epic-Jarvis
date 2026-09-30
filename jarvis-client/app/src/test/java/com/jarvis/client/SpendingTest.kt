package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Spending
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Spending summaries on the phone ([Spending]; docs/JARVIS-API.md section
 * 100; docs/FINANCE-DESIGN.md part A and its frozen "Slice contract").
 *
 * `contract/spending-cases.json` is written by the real backend code
 * (tools/gen_spending_cases.py) and is byte for byte the file the desktop
 * builds against. Every word, every table shape and every figure below comes
 * from it; nothing in this file works a total out. The one rule these tests
 * keep coming back to: the app draws the strings it is given and computes
 * nothing.
 */
class SpendingTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/spending-cases.json")) {
            "contract/spending-cases.json is missing - run tools/gen_spending_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val words = doc["words"]!!.jsonObject
    private val tables = doc["tables"]!!.jsonObject

    private fun word(key: String): String = words[key]!!.jsonPrimitive.content

    private fun tableBody(name: String): JsonObject =
        JsonObject(mapOf("ok" to kotlinx.serialization.json.JsonPrimitive(true), "table" to tables[name]!!))

    private fun parsed(name: String): Spending.Table =
        requireNotNull(Spending.parseTable(tableBody(name))) { "$name did not parse" }

    private fun cellsOf(rows: JsonArray): List<List<String>> =
        rows.map { r -> r.jsonObject["cells"]!!.jsonArray.map { it.jsonPrimitive.content } }

    // ------------------------------------------------------------- words ---

    @Test
    fun `every shared word is the PC's word`() {
        assertEquals(word("TITLE"), Spending.TITLE)
        assertEquals(word("DETAIL"), Spending.DETAIL)
        assertEquals(word("PC_ONLY"), Spending.PC_ONLY)
        assertEquals(word("NEEDS_SETUP_ON_PC"), Spending.NEEDS_SETUP_ON_PC)
        assertEquals(word("EMPTY_PROFILES"), Spending.EMPTY_PROFILES)
        assertEquals(word("STARTER_NOTE"), Spending.STARTER_NOTE)
        assertEquals(word("TABLE_HIDDEN"), Spending.TABLE_HIDDEN)
        assertEquals(word("TABLE_GONE"), Spending.TABLE_GONE)
        assertEquals(word("STREAM_MARK"), Spending.STREAM_MARK)
        assertEquals("Spending table hidden", Spending.TABLE_HIDDEN)
    }

    @Test
    fun `the hidden line is the one every table carries`() {
        for ((name, t) in tables) {
            assertEquals(name, Spending.TABLE_HIDDEN, t.jsonObject["words"]!!.jsonObject["hidden"]!!.jsonPrimitive.content)
            assertEquals(name, "true", t.jsonObject["private"]!!.jsonPrimitive.content)
            assertEquals(name, "false", t.jsonObject["read_aloud"]!!.jsonPrimitive.content)
            assertEquals(name, "false", t.jsonObject["remember"]!!.jsonPrimitive.content)
        }
    }

    // ------------------------------------------------------------ tables ---

    @Test
    fun `all six real tables are read`() {
        assertEquals(
            setOf("by_category", "by_month", "by_category_and_month", "two_files_overlapping", "two_currencies", "one_category"),
            tables.keys,
        )
        for (name in tables.keys) parsed(name)
    }

    @Test
    fun `every string is drawn exactly as the PC sent it`() {
        for ((name, raw) in tables) {
            val json = raw.jsonObject
            val t = parsed(name)
            assertEquals(name, json["title"]!!.jsonPrimitive.content, t.title)
            assertEquals(name, json["period"]!!.jsonPrimitive.content, t.period)
            assertEquals(name, json["sources"]!!.jsonArray.map { it.jsonPrimitive.content }, t.sources)
            assertEquals(name, json["caveats"]!!.jsonArray.map { it.jsonPrimitive.content }, t.caveats)
            assertEquals(name, json["columns"]!!.jsonArray.map { it.jsonObject["label"]!!.jsonPrimitive.content },
                t.columns.map { it.label })
            val sections = json["sections"]!!.jsonArray.map { it.jsonObject }
            assertEquals(name, sections.size, t.blocks.size)
            sections.forEachIndexed { i, s ->
                assertEquals(name, s["heading"]!!.jsonPrimitive.content, t.blocks[i].heading)
                assertEquals(name, s["currency"]!!.jsonPrimitive.content, t.blocks[i].currency)
                assertEquals(name, cellsOf(s["rows"]!!.jsonArray), t.blocks[i].rows.map { it.cells })
                assertEquals(name, cellsOf(s["totals"]!!.jsonArray), t.blocks[i].totals.map { it.cells })
                assertEquals(name, cellsOf(s["also"]!!.jsonArray), t.blocks[i].also.map { it.cells })
                // The row kinds ride along untouched (a style hint only).
                assertEquals(
                    name,
                    s["rows"]!!.jsonArray.map { it.jsonObject["kind"]!!.jsonPrimitive.content },
                    t.blocks[i].rows.map { it.kind },
                )
            }
        }
    }

    @Test
    fun `every row has one cell per column, in every group`() {
        for (name in tables.keys) {
            val t = parsed(name)
            for (b in t.blocks) for (l in b.rows + b.totals + b.also) {
                assertEquals("$name: ${l.cells}", t.columns.size, l.cells.size)
            }
        }
    }

    @Test
    fun `worked table by category, figures exactly as sent`() {
        val t = parsed("by_category")
        assertEquals("Spending by category, March 2026", t.title)
        assertEquals("March 2026", t.period)
        assertEquals(listOf("Category", "Spent", "Rows"), t.columns.map { it.label })
        assertEquals(listOf(false, true, true), t.columns.map { it.rightAligned })
        val b = t.blocks.single()
        assertEquals("", b.heading)
        assertEquals(
            listOf(
                listOf("Food and groceries", "40.00", "1"),
                listOf("Transport", "12.25", "1"),
                listOf("Subscriptions", "9.99", "1"),
                listOf("Eating out", "7.00", "2"),
                listOf("Uncategorised", "20.00", "1"),
            ),
            b.rows.map { it.cells },
        )
        // "Uncategorised" is an ordinary row (a neutral style), always present.
        assertEquals("uncategorised", b.rows.last().kind)
        assertEquals(listOf(listOf("Total spent", "89.24", "6")), b.totals.map { it.cells })
        // Refunds and income are shown apart, not netted.
        assertEquals(
            listOf(
                listOf(word("ROW_REFUNDS"), "5.10", "1"),
                listOf(word("ROW_INCOME"), "2,000.00", "1"),
            ),
            b.also.map { it.cells },
        )
        assertEquals("From: a_signed.csv", Spending.sourcesLine(t))
    }

    @Test
    fun `worked table with one column per month scrolls sideways`() {
        val t = parsed("by_category_and_month")
        assertEquals(listOf("Category", "March 2026", "April 2026", "Total"), t.columns.map { it.label })
        assertEquals(listOf(false, true, true, true), t.columns.map { it.rightAligned })
        assertEquals(5, t.blocks.single().rows.size)
    }

    @Test
    fun `two currencies are two blocks and are never merged`() {
        val t = parsed("two_currencies")
        assertEquals(2, t.blocks.size)
        assertTrue(t.blocks.all { it.heading.isNotEmpty() && it.heading == it.currency })
        assertEquals(2, t.blocks.map { it.heading }.toSet().size)
        assertTrue(t.caveats.contains(word("CAV_CURRENCIES")))
        // Each block keeps its own total.
        assertTrue(t.blocks.all { it.totals.size == 1 })
    }

    @Test
    fun `caveats and sources are the PC's sentences, one each, not joined`() {
        val t = parsed("two_files_overlapping")
        assertEquals(4, t.sources.size)
        assertEquals(
            tables["two_files_overlapping"]!!.jsonObject["caveats"]!!.jsonArray.map { it.jsonPrimitive.content },
            t.caveats,
        )
        assertTrue(t.caveats.size > 1)
        assertTrue(t.caveats.contains(word("CAV_ONCE").replace("{n}", "2")))
        assertEquals("From: " + t.sources.joinToString(", "), Spending.sourcesLine(t))
        assertNull(Spending.sourcesLine(t.copy(sources = emptyList())))
    }

    // ---------------------------------------------------- screen reader ---

    @Test
    fun `a row is read by its cells with their column labels`() {
        val t = parsed("by_category")
        val food = t.blocks.single().rows.first()
        assertEquals("Food and groceries, Spent 40.00, Rows 1", Spending.rowReading(t, food))
        // Built only from the cells as sent: no number is worked out.
        val (c0, c1, c2) = food.cells
        assertEquals("$c0, ${t.columns[1].label} $c1, ${t.columns[2].label} $c2", Spending.rowReading(t, food))
    }

    @Test
    fun `a totals row says Total first, once`() {
        val t = parsed("by_category")
        val total = t.blocks.single().totals.single()
        assertEquals("Total spent, Spent 89.24, Rows 6", Spending.rowReading(t, total, isTotal = true))
        // A totals row whose first cell does not say it gets the word.
        val plain = Spending.Line("total", listOf("All", "1.00", "1"))
        assertEquals("Total, All, Spent 1.00, Rows 1", Spending.rowReading(t, plain, isTotal = true))
    }

    @Test
    fun `the summary names the table and counts columns and rows only`() {
        val t = parsed("by_category")
        val s = Spending.summary(t)
        assertTrue(s.startsWith("Spending by category, March 2026. March 2026."))
        assertTrue(s.contains("3 columns"))
        // 5 rows + 1 total + 2 also lines, counted, not added up.
        assertTrue(s.contains("8 rows"))
    }

    // ------------------------------------------------------- robustness ---

    private fun withTable(edit: (Map<String, kotlinx.serialization.json.JsonElement>) -> Map<String, kotlinx.serialization.json.JsonElement>): JsonObject {
        val t = tables["by_category"]!!.jsonObject
        return JsonObject(mapOf("table" to JsonObject(edit(t))))
    }

    @Test
    fun `unknown extra fields are ignored and missing text fields read as empty`() {
        val extra = withTable { it + ("future_field" to kotlinx.serialization.json.JsonPrimitive("x")) }
        assertNotNull(Spending.parseTable(extra))
        val bare = withTable { it - "sources" - "caveats" - "period" - "words" - "private" }
        val t = requireNotNull(Spending.parseTable(bare))
        assertEquals(emptyList<String>(), t.sources)
        assertEquals(emptyList<String>(), t.caveats)
        assertEquals("", t.period)
        // A missing `align` is left, not right.
        val noAlign = JsonObject(
            mapOf(
                "table" to JsonObject(
                    tables["by_category"]!!.jsonObject + ("columns" to JsonArray(
                        listOf(JsonObject(mapOf("key" to kotlinx.serialization.json.JsonPrimitive("a"),
                            "label" to kotlinx.serialization.json.JsonPrimitive("A")))),
                    )) + ("sections" to JsonArray(emptyList())),
                ),
            ),
        )
        assertEquals(false, Spending.parseTable(noAlign)!!.columns.single().rightAligned)
    }

    @Test
    fun `a table the app cannot draw faithfully is not drawn`() {
        assertNull(Spending.parseTable(JsonObject(emptyMap())))
        assertNull(Spending.parseTable(withTable { it + ("kind" to kotlinx.serialization.json.JsonPrimitive("retirement")) }))
        assertNull(Spending.parseTable(withTable { it + ("version" to kotlinx.serialization.json.JsonPrimitive(2)) }))
        assertNull(Spending.parseTable(withTable { it + ("columns" to JsonArray(emptyList())) }))
        // A row with a cell missing would put money in the wrong column.
        val bad = tables["by_category"]!!.jsonObject["sections"]!!.jsonArray.map { s ->
            val o = s.jsonObject
            val rows = o["rows"]!!.jsonArray.mapIndexed { i, r ->
                if (i != 0) r else JsonObject(
                    r.jsonObject + ("cells" to JsonArray(r.jsonObject["cells"]!!.jsonArray.dropLast(1))),
                )
            }
            JsonObject(o + ("rows" to JsonArray(rows)))
        }
        assertNull(Spending.parseTable(withTable { it + ("sections" to JsonArray(bad)) }))
    }

    // ----------------------------------------------------- ids and paths ---

    private val id = "3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f6"

    @Test
    fun `a table id is exactly 32 lowercase hex characters`() {
        assertTrue(Spending.isTableId(id))
        assertFalse(Spending.isTableId(null))
        assertFalse(Spending.isTableId(""))
        assertFalse(Spending.isTableId(id.take(31)))
        assertFalse(Spending.isTableId(id + "0"))
        assertFalse(Spending.isTableId(id.uppercase()))
        assertFalse(Spending.isTableId("../../api/pending" + id.take(15)))
        assertFalse(Spending.isTableId("$id\n"))
    }

    @Test
    fun `the path carries only a checked id`() {
        assertEquals("/api/chat/table?id=$id", Spending.tablePath(id))
        assertNull(Spending.tablePath("abc"))
        assertNull(Spending.tablePath(null))
        assertNull(Spending.tablePath("$id&x=1"))
    }

    @Test
    fun `the stream line is read by its mark`() {
        assertEquals(id, Spending.tableIdFromLine(word("STREAM_MARK") + id))
        assertEquals(id, Spending.tableIdFromLine(": jarvis-table $id  "))
        assertNull(Spending.tableIdFromLine(": jarvis-status approval"))
        assertNull(Spending.tableIdFromLine("data: {}"))
        assertNull(Spending.tableIdFromLine(": jarvis-table ${id.uppercase()}"))
    }

    // -------------------------------------------------------- hide states ---

    @Test
    fun `hidden lists or a locked app draw the fixed line and fetch nothing`() {
        assertTrue(Spending.hiddenNow(hideLists = true, locked = false))
        assertTrue(Spending.hiddenNow(hideLists = false, locked = true))
        assertTrue(Spending.hiddenNow(hideLists = true, locked = true))
        assertFalse(Spending.hiddenNow(hideLists = false, locked = false))
    }

    @Test
    fun `a 404 is gone and shows the PC's sentence`() {
        assertTrue(Spending.gone(ApiError.NotFound))
        assertFalse(Spending.gone(ApiError.NotAvailable))
        assertFalse(Spending.gone(ApiError.BadToken))
        assertEquals(word("TABLE_GONE"), Spending.Read.Gone(Spending.TABLE_GONE).message)
    }

    // -------------------------------------------------------- the plate ---

    @Test
    fun `the phone plate says set up on the PC and edits nothing`() {
        for (name in listOf("view_phone_nothing_saved", "view_phone_file_waiting", "view_phone_one_layout")) {
            val body = doc[name]!!.jsonObject
            val v = requireNotNull(Spending.parseView(body)) { "$name did not parse" }
            assertEquals(name, word("TITLE"), v.title)
            assertEquals(name, word("PC_ONLY"), v.pcOnly)
            assertEquals(name, word("DETAIL"), v.detail)
            assertEquals(name, "false", body["can_edit"]!!.jsonPrimitive.content)
            // A phone answer never carries the PC's file path.
            assertTrue(name, body["waiting"]!!.jsonArray.all { !it.jsonObject.containsKey("path") })
        }
    }

    @Test
    fun `layouts, waiting files and starter categories are read as sent`() {
        val none = Spending.parseView(doc["view_phone_nothing_saved"]!!.jsonObject)!!
        assertTrue(none.layouts.isEmpty())
        assertEquals(word("EMPTY_PROFILES"), none.emptyProfiles)
        assertEquals(12, none.categories.size)
        assertEquals("Food and groceries", none.categories.first().name)
        assertTrue(none.categories.first().words.contains("tesco"))
        assertEquals(word("STARTER_NOTE"), none.starterNote)

        val waiting = Spending.parseView(doc["view_phone_file_waiting"]!!.jsonObject)!!
        assertEquals(listOf("b_debit_credit.csv"), waiting.waiting)
        assertEquals(word("NEEDS_SETUP_ON_PC"), waiting.needsSetup)

        val one = Spending.parseView(doc["view_phone_one_layout"]!!.jsonObject)!!
        val l = one.layouts.single()
        assertEquals("a_signed.csv", l.label)
        assertEquals(listOf("Date", "Description", "Amount", "Balance"), l.columns)
        assertEquals(doc["sign_sentences"]!!.jsonObject["negative_out"]!!.jsonPrimitive.content, l.signSentence)
    }

    @Test
    fun `the PC's own view parses too, and never asks for its file paths`() {
        val v = Spending.parseView(doc["view_pc_file_waiting"]!!.jsonObject)!!
        assertEquals(listOf("b_debit_credit.csv"), v.waiting)
    }

    @Test
    fun `a module that is not there reads as missing, not as an empty plate`() {
        val off = JsonObject(mapOf("available" to kotlinx.serialization.json.JsonPrimitive(false)))
        assertNull(Spending.parseView(off))
        assertTrue(Spending.missing(ApiError.NotFound))
        assertTrue(Spending.missing(ApiError.NotAvailable))
        assertFalse(Spending.missing(ApiError.BadToken))
    }

    @Test
    fun `every answer error the PC words is a sentence the phone can show as it is`() {
        val errors = doc["errors"]!!.jsonObject
        assertEquals(word("NEEDS_SETUP_ON_PC"), errors["needs_setup"]!!.jsonPrimitive.content)
        assertEquals(word("PC_ONLY"), errors["pc_only"]!!.jsonPrimitive.content)
    }
}
