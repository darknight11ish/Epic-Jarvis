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
            "layout" to v.layout,
            "blocks" to v.blocks.map { blockJson(it) },
        )
    }

    /** One block as the fixture writes it - the view's and a board's are the
     *  same shape, because a board only reorders or picks them. */
    private fun blockJson(b: JarvisWidgets.Block): Map<String, Any?> = when (b) {
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

    /** A board as the fixture writes it: the big block, the blocks, the buttons. */
    private fun asJson(board: JarvisWidgets.Board?): Any? = board?.let { b ->
        mapOf(
            "big" to b.big?.let { blockJson(it) },
            "blocks" to b.blocks.map { blockJson(it) },
            "buttons" to b.buttons.map { blockJson(it) },
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
    fun `the four arrangements are the PC's, and every case draws what the fixture says`() {
        assertEquals(
            root["layouts"]!!.jsonArray.map { it.jsonPrimitive.content },
            JarvisWidgets.LAYOUTS,
        )
        for ((name, el) in cases) {
            val c = el.jsonObject
            val view = JarvisWidgets.viewOf(c["answer"] as? JsonObject)
            val boards = c["boards"]!!.jsonObject
            for (layout in JarvisWidgets.LAYOUTS) {
                val arranged = view?.let { JarvisWidgets.boardOf(it.copy(layout = layout)) }
                assertEquals(
                    "board $layout: $name",
                    norm(plain(boards[layout])),
                    norm(asJson(arranged)),
                )
            }
            // boardOf uses the view's OWN layout: what the PC sent is what is drawn.
            if (view != null) {
                assertEquals("own layout: $name", norm(plain(boards[view.layout])), norm(asJson(JarvisWidgets.boardOf(view))))
            }
        }
    }

    @Test
    fun `an arrangement this app does not know is drawn as stack, never dropped`() {
        val answer = JarvisJson.parseToJsonElement(
            """{"ok": true, "name": "From the future", "layout": "grid",
               "blocks": [{"type": "title", "text": "Ahead"},
                          {"type": "button", "action": "timer"}]}""",
        ).jsonObject
        val view = JarvisWidgets.viewOf(answer)!!
        assertEquals(JarvisWidgets.LAYOUT_STACK, view.layout)
        // Missing means "stack" too: every widget saved before 2026-10-30.
        val old = JarvisJson.parseToJsonElement(
            """{"ok": true, "name": "Old", "blocks": [{"type": "title", "text": "Still here"}]}""",
        ).jsonObject
        assertEquals(JarvisWidgets.LAYOUT_STACK, JarvisWidgets.viewOf(old)!!.layout)
        // A hostile value is not passed on, and the widget still draws.
        val hostile = JarvisJson.parseToJsonElement(
            """{"ok": true, "name": "x", "layout": "<script>alert(1)</script>",
               "blocks": [{"type": "title", "text": "A"}]}""",
        ).jsonObject
        assertEquals(JarvisWidgets.LAYOUT_STACK, JarvisWidgets.viewOf(hostile)!!.layout)
        // "big" with no number is the stack order, not an empty widget.
        val noNumber = JarvisJson.parseToJsonElement(
            """{"ok": true, "name": "x", "layout": "big",
               "blocks": [{"type": "list", "source": "todo"}]}""",
        ).jsonObject
        val v = JarvisWidgets.viewOf(noNumber)!!
        val board = JarvisWidgets.boardOf(v)
        assertNull(board.big)
        assertEquals(1, board.blocks.size)
    }

    /**
     * Every slot the "On your home screen" picker offers must be drawable. The
     * picker loops `0 until JarvisWidgets.SLOTS`, and a slot is a widget class
     * plus a `<receiver>` in the manifest, so the count and the declarations
     * have to agree. They did not until 2026-10-30: SLOTS was 5 and the
     * manifest declared three, so slots 4 and 5 could be assigned and never
     * drawn. This is the same pin QuickTilesTest puts on the tile slots.
     */
    @Test
    fun `every home-screen slot has a receiver`() {
        val receivers = listOf(
            "JarvisBoardWidgetOneReceiver",
            "JarvisBoardWidgetTwoReceiver",
            "JarvisBoardWidgetThreeReceiver",
        )
        assertEquals("the picker offers this many slots", JarvisWidgets.SLOTS, receivers.size)
        val manifest = repoFile("jarvis-client/app/src/main/AndroidManifest.xml").readText()
        val source = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/widget/JarvisBoardWidget.kt",
        ).readText()
        for ((index, name) in receivers.withIndex()) {
            val at = manifest.indexOf(".widget.$name\"")
            assertTrue("$name is declared in the manifest", at >= 0)
            val block = manifest.substring(at, manifest.indexOf("</receiver>", at))
            assertTrue(
                "slot ${index + 1} carries the widget's own label:\n$block",
                block.contains("android:label=\"@string/widget_board_name_${index + 1}\""),
            )
            assertTrue(
                "slot ${index + 1} points at the board's provider info",
                block.contains("android:resource=\"@xml/widget_board_info\""),
            )
            assertTrue(
                "$name exists as a GlanceAppWidgetReceiver",
                source.contains("class $name : GlanceAppWidgetReceiver()"),
            )
        }
        // The hint the owner reads must not promise a slot that does not
        // exist either - that is how "5" was found in the first place.
        assertTrue(JarvisWidgets.PHONE_HINT.contains("\"Jarvis widget 1\""))
        for (n in (JarvisWidgets.SLOTS + 1)..8) {
            assertFalse(
                "the hint must not name slot $n",
                JarvisWidgets.PHONE_HINT.contains("Jarvis widget $n"),
            )
            assertFalse("the hint must not quote slot $n", JarvisWidgets.PHONE_HINT.contains("\"$n\""))
        }
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the
     *  repository, the way QuickTilesTest does. */
    private fun repoFile(rel: String): java.io.File {
        var d: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = java.io.File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
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
