package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.TagSuggest
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Suggest tags overnight" on the phone (docs/JARVIS-API.md section 104; the
 * frozen slice contract, section 9A of docs/OVERNIGHT-TAGS-DESIGN.md), held to
 * contract/history-cases.json - byte for byte the file the desktop reads.
 */
class TagSuggestTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/history-cases.json")) {
            "contract/history-cases.json is missing - run tools/gen_history_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }
    private val words = doc["words"]!!.jsonObject
    private fun w(key: String): String = words[key]!!.jsonPrimitive.content

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun `the words are the fixture's, word for word`() {
        assertEquals(w("tag_suggest_label"), TagSuggest.LABEL)
        assertEquals(w("tag_suggest_off"), TagSuggest.OFF)
        assertEquals(w("tag_suggest_on"), TagSuggest.ON)
        assertEquals(w("tag_suggest_paused"), TagSuggest.PAUSED)
        assertEquals(w("tag_suggest_pending"), TagSuggest.PENDING)
        assertEquals(w("tag_suggest_waiting_one"), TagSuggest.WAITING_ONE)
        assertEquals(w("tag_suggest_waiting_other"), TagSuggest.WAITING_OTHER)
        assertEquals(w("tag_suggest_card_title"), TagSuggest.CARD_TITLE)
        assertEquals(w("tag_suggest_card_body"), TagSuggest.CARD_BODY)
        assertEquals(w("tag_suggest_chat_hidden"), TagSuggest.CHAT_HIDDEN)
        assertEquals(w("tag_suggest_error_fallback"), TagSuggest.ERROR_FALLBACK)
        val errors = words["tag_suggest_errors"]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }
        assertEquals(errors, TagSuggest.ERRORS)
        val codes = doc["tag_suggest_error_codes"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        assertEquals(codes, TagSuggest.ERRORS.keys)
    }

    @Test
    fun `every worked state case gives the fixture's two lines`() {
        val cases = doc["tag_suggest_state_cases"]!!.jsonArray
        assertTrue(cases.isNotEmpty())
        for (c in cases) {
            val o = c.jsonObject
            val waitingText = o["waiting"]!!.jsonPrimitive.content
            val n = Regex("^(\\d+) suggestion").find(waitingText)?.groupValues?.get(1)?.toInt() ?: 0
            val s = TagSuggest.State(
                enabled = o["enabled"]!!.jsonPrimitive.content.toBoolean(),
                paused = o["paused"]!!.jsonPrimitive.content.toBoolean(),
                waiting = n,
                lastDay = "",
            )
            assertEquals("case $o", o["state"]!!.jsonPrimitive.content, TagSuggest.stateLine(s))
            assertEquals("case $o", waitingText, TagSuggest.waitingLine(s.waiting).orEmpty())
        }
    }

    @Test
    fun `the state is read from the GET answer`() {
        val s = TagSuggest.state(obj("""{"ok":true,"enabled":true,"paused":false,"waiting":2,"last_day":"2026-09-30"}"""))!!
        assertTrue(s.enabled)
        assertFalse(s.paused)
        assertEquals(2, s.waiting)
        assertEquals("2026-09-30", s.lastDay)
        val p = TagSuggest.state(obj("""{"ok":true,"enabled":false,"paused":true,"waiting":0,"last_day":""}"""))!!
        assertTrue(p.paused)
        assertFalse(p.enabled)
        // Both true is impossible; if it happens the safer way wins: paused, switch off.
        val both = TagSuggest.state(obj("""{"ok":true,"enabled":true,"paused":true}"""))!!
        assertFalse(both.enabled)
        assertEquals(w("tag_suggest_paused"), TagSuggest.stateLine(both))
        // Not a state: no boolean `enabled`, or ok:false.
        assertNull(TagSuggest.state(obj("""{"ok":true}""")))
        assertNull(TagSuggest.state(obj("""{"ok":false,"enabled":true}""")))
        assertNull(TagSuggest.state(obj("""{"ok":true,"enabled":"yes"}""")))
    }

    @Test
    fun `the request is exactly enabled`() {
        val on = obj(TagSuggest.body(true))
        assertEquals(setOf("enabled"), on.keys)
        assertEquals("true", on["enabled"]!!.jsonPrimitive.content)
        assertEquals("false", obj(TagSuggest.body(false))["enabled"]!!.jsonPrimitive.content)
    }

    @Test
    fun `turning on waits for a card, the switch does not flip`() {
        val w202 = TagSuggest.write(202, obj("""{"ok":true,"pending":true}"""))
        assertTrue(w202.ok)
        assertTrue(w202.pending)
        assertNull(w202.enabled)
        assertEquals(w("tag_suggest_pending"), w202.said)
        val already = TagSuggest.write(200, obj("""{"ok":true,"enabled":true}"""))
        assertTrue(already.ok)
        assertFalse(already.pending)
        assertEquals(true, already.enabled)
        val off = TagSuggest.write(200, obj("""{"ok":true,"enabled":false}"""))
        assertEquals(false, off.enabled)
    }

    @Test
    fun `an error shows the PC's sentence, else the code's, else the fallback`() {
        val pc = TagSuggest.write(409, obj("""{"ok":false,"error":"no_tags","message":"Make a tag first, please."}"""))
        assertFalse(pc.ok)
        assertEquals("Make a tag first, please.", pc.said)
        assertEquals(
            TagSuggest.ERRORS["no_local_model"],
            TagSuggest.write(409, obj("""{"ok":false,"error":"no_local_model","message":"  "}""")).said,
        )
        assertEquals(TagSuggest.ERRORS["bad_request"], TagSuggest.errorSentence("bad_request"))
        assertEquals(w("tag_suggest_error_fallback"), TagSuggest.errorSentence("new_code"))
        assertEquals(w("tag_suggest_error_fallback"), TagSuggest.write(500, null).said)
        assertEquals(w("tag_suggest_error_fallback"), TagSuggest.errorSentence(null, null))
    }

    @Test
    fun `the card words rebuild the fixture's cards exactly`() {
        val cases = doc["tag_suggest_card_cases"]!!.jsonArray
        assertTrue(cases.isNotEmpty())
        for (c in cases) {
            val o = c.jsonObject
            assertEquals(
                "case $o",
                o["expect"]!!.jsonPrimitive.content,
                TagSuggest.cardWords(
                    o["title"]!!.jsonPrimitive.content,
                    o["when"]!!.jsonPrimitive.content,
                    o["tag"]!!.jsonPrimitive.content,
                    o["hidden"]!!.jsonPrimitive.content.toBoolean(),
                ),
            )
        }
    }

    @Test
    fun `hidden lists show the PC's hidden text, or nothing`() {
        val open = "Suggested tag\n\nChat: \"Roof repair budget\" (last updated 28 Sep, 14:05)"
        val hid = "Suggested tag\n\nChat: A chat from 28 Sep, 14:05"
        assertEquals(open, TagSuggest.cardText(open, hid, hide = false))
        assertEquals(hid, TagSuggest.cardText(open, hid, hide = true))
        // The PC sent no hidden text: nothing is shown rather than the title.
        assertEquals("", TagSuggest.cardText(open, null, hide = true))
        assertFalse(TagSuggest.cardText(open, null, hide = true).contains("Roof"))
        // No whole text: the hidden one is better than a blank card when nothing is hidden.
        assertEquals(hid, TagSuggest.cardText(null, hid, hide = false))
    }

    // A suggestion card as the gate sends it: `detail` carries `text` (with the chat's
    // title), `text_hidden` (without it), `what` and `leaves_this_pc`. These read it
    // the way the phone does; written by eye against PendingRows.kt (no local Android build).
    private val open = "Suggested tag for a chat\n\nChat: \"Roof repair budget\" (last updated 28 Sep, 14:05)\nTag: Projects"
    private val hid = "Suggested tag for a chat\n\nChat: A chat from 28 Sep, 14:05\nTag: Projects"
    private fun cardRow(withHidden: Boolean = true): JsonObject = buildJsonObject {
        put("id", "s1")
        put("action", "chat_tag_suggest")
        put("tier", "ask")
        put(
            "detail",
            buildJsonObject {
                put("text", open)
                if (withHidden) put("text_hidden", hid)
                put("what", "file one chat under a tag")
                put("leaves_this_pc", false)
            },
        )
    }

    @Test
    fun `a suggestion card shows the whole text, or the hidden one under hidden lists`() {
        val item = decodePendingRows(listOf(cardRow()), 0L).items.single()
        assertEquals(open, item.shownSummary(hideLists = false))
        assertEquals(hid, item.shownSummary(hideLists = true))
        assertFalse(item.shownSummary(hideLists = true).contains("Roof"))
        // The raw detail (both texts, the title in one) is never shown for this card.
        assertNull(item.detail)
    }

    @Test
    fun `a suggestion card with no hidden text shows nothing under hidden lists`() {
        val item = decodePendingRows(listOf(cardRow(withHidden = false)), 0L).items.single()
        assertEquals("", item.shownSummary(hideLists = true))
        assertEquals(open, item.shownSummary(hideLists = false))
    }

    @Test
    fun `every other card ignores the hidden-lists switch`() {
        val row = obj("""{"id":"o1","action":"send_email","detail":{"text":"Send it?","text_hidden":"x"}}""")
        val item = decodePendingRows(listOf(row), 0L).items.single()
        assertEquals("Send it?", item.shownSummary(hideLists = true))
        assertNull(item.summaryHidden)
    }
}
