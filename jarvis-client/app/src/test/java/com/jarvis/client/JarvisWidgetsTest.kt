package com.jarvis.client

import com.jarvis.client.data.TileAction
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.JarvisWidgets
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Widgets you describe" (docs/JARVIS-API.md section 86): the phone draws
 * exactly what the desktop and the PC's rule draw, case for case.
 *
 * `contract/widget-cases.json` is written by tools/gen_widget_cases.py -
 * byte for byte the desktop's tests/fixtures/widget-cases.json. It holds real
 * `GET /api/widgets/show` answers and HOSTILE ones (a script block, an
 * "approve" button, a huge list, a missing private flag, control
 * characters), each with the view both apps must draw and the view while
 * private words are hidden.
 */
class JarvisWidgetsTest {

    private val root: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/widget-cases.json")) {
            "contract/widget-cases.json is missing - run tools/gen_widget_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = root["cases"]!!.jsonObject

    /** A view as the fixture writes it, to compare field by field. */
    private fun asJson(view: JarvisWidgets.View?): Any? = view?.let { v ->
        mapOf(
            "name" to v.name,
            "blocks" to v.blocks.map { b ->
                when (b) {
                    is JarvisWidgets.Block.Title -> mapOf("type" to "title", "text" to b.text)
                    is JarvisWidgets.Block.Button -> mapOf("type" to "button", "action" to b.action.wire, "label" to b.label)
                    is JarvisWidgets.Block.Count -> mapOf(
                        "type" to "number", "label" to b.label, "value" to b.value, "note" to b.note,
                        "private" to b.private, "hidden" to b.hidden,
                    )
                    is JarvisWidgets.Block.Items -> mapOf(
                        "type" to "list", "label" to b.label,
                        "items" to b.items.map { mapOf("text" to it.first, "when" to it.second) },
                        "more" to b.more, "empty" to b.empty, "note" to b.note,
                        "private" to b.private, "hidden" to b.hidden,
                    )
                    is JarvisWidgets.Block.Progress -> mapOf(
                        "type" to "progress", "label" to b.label, "fraction" to b.fraction, "value" to b.value,
                        "note" to b.note, "private" to b.private, "hidden" to b.hidden,
                    )
                }
            },
        )
    }

    private fun plain(e: JsonElement?): Any? = when (e) {
        null, JsonNull -> null
        is JsonObject -> e.mapValues { plain(it.value) }
        is JsonArray -> e.map { plain(it) }
        else -> {
            val p = e.jsonPrimitive
            when {
                p.isString -> p.content
                p.content == "true" || p.content == "false" -> p.content == "true"
                p.content.contains('.') -> p.double
                else -> p.int
            }
        }
    }

    /** Numbers compared as numbers: the fixture writes 1.0, a bar's fraction. */
    private fun norm(x: Any?): Any? = when (x) {
        is Map<*, *> -> x.mapValues { (k, v) -> if (k == "fraction") (v as Number).toDouble() else norm(v) }
        is List<*> -> x.map { norm(it) }
        else -> x
    }

    @Test
    fun `every case draws exactly the shared view, and the same hidden`() {
        assertTrue(cases.size >= 6)
        for ((name, el) in cases) {
            val c = el.jsonObject
            val view = JarvisWidgets.viewOf(c["answer"] as? JsonObject)
            assertEquals(name, norm(plain(c["view"])), norm(asJson(view)))
            assertEquals("$name hidden", norm(plain(c["hidden"])), norm(asJson(view?.let { JarvisWidgets.hide(it) })))
        }
    }

    @Test
    fun `the buttons are exactly the Quick Settings tile actions, in their words`() {
        val actions = root["actions"]!!.jsonArray.map {
            it.jsonObject["id"]!!.jsonPrimitive.content to it.jsonObject["label"]!!.jsonPrimitive.content
        }
        assertEquals(actions, TileAction.entries.map { it.wire to it.tileLabel })
    }

    @Test
    fun `an approve button, a script block and an unknown source never get through`() {
        val view = JarvisWidgets.viewOf(cases["hostile"]!!.jsonObject["answer"]!!.jsonObject)!!
        val buttons = view.blocks.filterIsInstance<JarvisWidgets.Block.Button>().map { it.action }
        assertEquals(listOf(TileAction.TIMER), buttons)
        val unknown = view.blocks.filterIsInstance<JarvisWidgets.Block.Count>().single()
        assertTrue("a source this app does not know is private", unknown.private)
        assertFalse(view.name.contains('‮'))
    }

    @Test
    fun `the private sources and the hidden words are the PC's`() {
        assertEquals(
            root["private_sources"]!!.jsonArray.map { it.jsonPrimitive.content },
            JarvisWidgets.PRIVATE_SOURCES.sorted(),
        )
        assertEquals(root["hidden_words"]!!.jsonPrimitive.content, JarvisWidgets.HIDDEN_WORDS)
    }

    @Test
    fun `not ok is nothing to draw`() {
        assertNull(JarvisWidgets.viewOf(cases["not_ok"]!!.jsonObject["answer"]!!.jsonObject))
        assertNull(JarvisWidgets.viewOf(null))
    }

    @Test
    fun `ids, the draft body and the PC's sentences`() {
        assertTrue(JarvisWidgets.validId("w0123456789"))
        assertFalse(JarvisWidgets.validId("d0123456789"))
        assertFalse(JarvisWidgets.validId("../../x"))
        assertTrue(JarvisWidgets.validDraft("dabcdef0123"))
        val body = JarvisJson.parseToJsonElement(JarvisWidgets.draftBody("  my   next reminders ")!!).jsonObject
        assertEquals("my next reminders", body["words"]!!.jsonPrimitive.content)
        assertEquals("typed", body["provenance"]!!.jsonPrimitive.content)
        assertNull(JarvisWidgets.draftBody("   "))
        assertNull(JarvisWidgets.draftBody("x".repeat(JarvisWidgets.MAX_WORDS + 1)))
        val refused = JarvisJson.parseToJsonElement("""{"ok": false, "error": "You already have 12 widgets."}""").jsonObject
        assertEquals(false to "You already have 12 widgets.", JarvisWidgets.said(409, refused))
        assertEquals(false to JarvisWidgets.MISSING, JarvisWidgets.said(404, null))
        val ok = JarvisJson.parseToJsonElement("""{"ok": true, "said": "Added."}""").jsonObject
        assertEquals(true to "Added.", JarvisWidgets.said(200, ok))
    }
}
