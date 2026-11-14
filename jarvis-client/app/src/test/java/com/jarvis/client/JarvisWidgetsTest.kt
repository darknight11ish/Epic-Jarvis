package com.jarvis.client

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
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
            "accent" to v.accent,
            "shade" to v.shade,
            "contrast" to v.contrast,
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

    /**
     * The look (2026-11-14): the three closed lists exist on the PC, the
     * desktop and here, and this holds the phone's copy to the shared fixture
     * field for field - every accent's hex, every shade's TWO alphas, every
     * contrast's four colours, and what "absent" means.
     */
    @Test
    fun `the look lists are the PC's, id for id`() {
        assertEquals(
            root["accents"]!!.jsonArray.map {
                val o = it.jsonObject
                JarvisWidgets.Accent(
                    id = o["id"]!!.jsonPrimitive.content,
                    label = o["label"]!!.jsonPrimitive.content,
                    color = o["color"]!!.jsonPrimitive.content,
                )
            },
            JarvisWidgets.ACCENTS,
        )
        assertEquals(
            root["shades"]!!.jsonArray.map {
                val o = it.jsonObject
                JarvisWidgets.Shade(
                    id = o["id"]!!.jsonPrimitive.content,
                    label = o["label"]!!.jsonPrimitive.content,
                    alpha = o["alpha"]!!.jsonPrimitive.int,
                    surfaceAlpha = o["surface_alpha"]!!.jsonPrimitive.int,
                )
            },
            JarvisWidgets.SHADES,
        )
        assertEquals(
            root["contrasts"]!!.jsonArray.map {
                val o = it.jsonObject
                val c = o["colors"]!!.jsonObject
                JarvisWidgets.Contrast(
                    id = o["id"]!!.jsonPrimitive.content,
                    label = o["label"]!!.jsonPrimitive.content,
                    bg = c["bg"]!!.jsonPrimitive.content,
                    surface = c["surface"]!!.jsonPrimitive.content,
                    textHi = c["text_hi"]!!.jsonPrimitive.content,
                    textMuted = c["text_muted"]!!.jsonPrimitive.content,
                )
            },
            JarvisWidgets.CONTRASTS,
        )
        val d = root["look_default"]!!.jsonObject
        assertEquals(
            JarvisWidgets.Look(
                accent = d["accent"]!!.jsonPrimitive.content,
                shade = d["shade"]!!.jsonPrimitive.content,
                contrast = d["contrast"]!!.jsonPrimitive.content,
            ),
            JarvisWidgets.LOOK_DEFAULT,
        )
        assertEquals("eight accents, as the PC has", 8, JarvisWidgets.ACCENTS.size)
        assertEquals("no two accents share an id", 8, JarvisWidgets.ACCENTS.map { it.id }.distinct().size)
        assertEquals("three shades", 3, JarvisWidgets.SHADES.size)
        assertEquals("two contrasts", 2, JarvisWidgets.CONTRASTS.size)
        // The solid look is opaque by definition; anything else would make a
        // widget see-through that the owner chose as solid.
        assertEquals(255, JarvisWidgets.SHADES.first { it.id == "solid" }.alpha)
        assertEquals(255, JarvisWidgets.SHADES.first { it.id == "solid" }.surfaceAlpha)
    }

    /**
     * The read side FALLS BACK (the write side refuses): an absent key, a
     * value off the list, or a word from a newer PC draws that list's default
     * - and only that one key moves, so one strange word cannot lose the other
     * two. `newer_pc_look` and `half_right_look` in the fixture are exactly
     * this, and the one-key-at-a-time cases below prove the keys are
     * independent rather than all-or-nothing.
     */
    @Test
    fun `a look is read whole, defaults when absent, and falls back one key at a time`() {
        // Whole: the fixture's looked widget keeps violet / clear / high.
        val looked = JarvisWidgets.viewOf(cases["looked_widget"]!!.jsonObject["answer"]!!.jsonObject)!!
        assertEquals(JarvisWidgets.Look("violet", "clear", "high"), looked.look)
        // Through hide() too: hiding words is about words, never colour.
        assertEquals(looked.look, JarvisWidgets.hide(looked).look)
        // Absent: every widget saved before 2026-11-14.
        val old = JarvisWidgets.viewOf(cases["morning"]!!.jsonObject["answer"]!!.jsonObject)!!
        assertEquals(JarvisWidgets.LOOK_DEFAULT, old.look)
        // A newer PC's words, all three off the list at once.
        val newer = JarvisWidgets.viewOf(cases["newer_pc_look"]!!.jsonObject["answer"]!!.jsonObject)!!
        assertEquals(JarvisWidgets.LOOK_DEFAULT, newer.look)
        // One off the list, the other two kept.
        val half = JarvisWidgets.viewOf(cases["half_right_look"]!!.jsonObject["answer"]!!.jsonObject)!!
        assertEquals(JarvisWidgets.Look("amber", "solid", "high"), half.look)

        fun answer(accent: String? = null, shade: String? = null, contrast: String? = null): JsonObject {
            val keys = listOfNotNull(
                accent?.let { "\"accent\": \"$it\"" },
                shade?.let { "\"shade\": \"$it\"" },
                contrast?.let { "\"contrast\": \"$it\"" },
            ).joinToString(", ")
            val extra = if (keys.isEmpty()) "" else "$keys,"
            return JarvisJson.parseToJsonElement(
                """{"ok": true, "name": "x", "layout": "stack", $extra
                   "blocks": [{"type": "title", "text": "A"}]}""",
            ).jsonObject
        }
        // ONLY the accent is a word this app does not know.
        assertEquals(
            JarvisWidgets.Look("cyan", "half", "high"),
            JarvisWidgets.viewOf(answer(accent = "chartreuse", shade = "half", contrast = "high"))!!.look,
        )
        // ONLY the shade.
        assertEquals(
            JarvisWidgets.Look("amber", "solid", "high"),
            JarvisWidgets.viewOf(answer(accent = "amber", shade = "frosted", contrast = "high"))!!.look,
        )
        // ONLY the contrast.
        assertEquals(
            JarvisWidgets.Look("amber", "half", "normal"),
            JarvisWidgets.viewOf(answer(accent = "amber", shade = "half", contrast = "ultra"))!!.look,
        )
        // Nothing at all, and each one on its own.
        assertEquals(JarvisWidgets.LOOK_DEFAULT, JarvisWidgets.viewOf(answer())!!.look)
        assertEquals(JarvisWidgets.Look("amber", "solid", "normal"), JarvisWidgets.viewOf(answer(accent = "amber"))!!.look)
        assertEquals(JarvisWidgets.Look("cyan", "half", "normal"), JarvisWidgets.viewOf(answer(shade = "half"))!!.look)
        assertEquals(JarvisWidgets.Look("cyan", "solid", "high"), JarvisWidgets.viewOf(answer(contrast = "high"))!!.look)
        // A non-string is not a value either.
        assertEquals(
            JarvisWidgets.LOOK_DEFAULT,
            JarvisWidgets.lookOf(JarvisJson.parseToJsonElement("""{"accent": 7}""").jsonObject),
        )
    }

    /**
     * Rule 3: the shade moves the card and the panel, never the words. The
     * shade's alphas are in the top byte of the drawn ARGB int (which is what
     * `GlanceModifier.background` hands to `RemoteViews.setBackgroundColor`),
     * and the text colours have no alpha but FF.
     */
    @Test
    fun `the shade is the alpha in the drawn colour, and text never gets one`() {
        val normal = JarvisWidgets.contrastOf("normal")
        val clear = JarvisWidgets.shadeOf("clear")
        val half = JarvisWidgets.shadeOf("half")
        // 128 = 0x80, 102 = 0x66, 191 = 0xBF, 159 = 0x9F.
        assertEquals(0x8004070C.toInt(), JarvisWidgets.argb(normal.bg, clear.alpha))
        assertEquals(0x660E1822.toInt(), JarvisWidgets.argb(normal.surface, clear.surfaceAlpha))
        assertEquals(0xBF04070C.toInt(), JarvisWidgets.argb(normal.bg, half.alpha))
        assertEquals(0x9F0E1822.toInt(), JarvisWidgets.argb(normal.surface, half.surfaceAlpha))
        // The solid look is exactly today's colours.
        assertEquals(0xFF04070C.toInt(), JarvisWidgets.argb(normal.bg, JarvisWidgets.shadeOf("solid").alpha))
        // Text has no shade passed to it anywhere.
        assertEquals(0xFFE6EEF7.toInt(), JarvisWidgets.argb(normal.textHi))
        assertEquals(0xFF93A6BA.toInt(), JarvisWidgets.argb(normal.textMuted))
        for (contrast in JarvisWidgets.CONTRASTS) {
            for (text in listOf(contrast.textHi, contrast.textMuted)) {
                assertEquals("$text must be opaque", 0xFF, (JarvisWidgets.argb(text) ushr 24) and 0xFF)
            }
        }
        // Each accent is drawn as its own hex, opaque.
        for (accent in JarvisWidgets.ACCENTS) {
            assertEquals(accent.id, 0xFF, (JarvisWidgets.argb(accent.color) ushr 24) and 0xFF)
        }
        // Compose's own Color round-trip keeps that alpha. This is the exact
        // value Glance's background modifier converts with Color.toArgb and
        // hands to RemoteViews.setBackgroundColor (see BoardPalette's comment),
        // so a see-through card is not silently drawn opaque here.
        for (shade in JarvisWidgets.SHADES) {
            val drawn = Color(JarvisWidgets.argb(normal.bg, shade.alpha))
            assertEquals(
                "${shade.id}: the drawn colour keeps the shade's alpha",
                JarvisWidgets.argb(normal.bg, shade.alpha),
                drawn.toArgb(),
            )
        }
        assertEquals(
            "the surface keeps its own alpha",
            0x660E1822.toInt(),
            Color(JarvisWidgets.argb(normal.surface, clear.surfaceAlpha)).toArgb(),
        )
        // And text is fully opaque in the drawn colour too.
        assertEquals(0xFFE6EEF7.toInt(), Color(JarvisWidgets.argb(normal.textHi)).toArgb())
    }

    /**
     * The Add body (2026-11-14): the preview plus the look the pickers show.
     * All three keys are always there - the PC refuses an off-list value with
     * 400, so the app has to send only values on its own lists.
     */
    @Test
    fun `the Add body always carries the preview's look`() {
        val body = JarvisJson.parseToJsonElement(
            JarvisWidgets.addBody("dabcdef0123", JarvisWidgets.Look("amber", "clear", "high")),
        ).jsonObject
        assertEquals("dabcdef0123", body["draft"]!!.jsonPrimitive.content)
        assertEquals("amber", body["accent"]!!.jsonPrimitive.content)
        assertEquals("clear", body["shade"]!!.jsonPrimitive.content)
        assertEquals("high", body["contrast"]!!.jsonPrimitive.content)
        assertEquals("exactly the four keys", 4, body.size)

        // A look this app somehow put together off the lists can never leave.
        val safe = JarvisJson.parseToJsonElement(
            JarvisWidgets.addBody("dabcdef0123", JarvisWidgets.Look("chartreuse", "frosted", "ultra")),
        ).jsonObject
        assertEquals("cyan", safe["accent"]!!.jsonPrimitive.content)
        assertEquals("solid", safe["shade"]!!.jsonPrimitive.content)
        assertEquals("normal", safe["contrast"]!!.jsonPrimitive.content)

        // The default look is sent in full too, not omitted as "the draft
        // probably has it".
        val plain = JarvisJson.parseToJsonElement(
            JarvisWidgets.addBody("dabcdef0123", JarvisWidgets.LOOK_DEFAULT),
        ).jsonObject
        assertEquals(setOf("draft", "accent", "shade", "contrast"), plain.keys)
    }

    /**
     * The live preview must draw what the home-screen widget draws. It may not
     * grow its own arrangement: it asks [JarvisWidgets.boardOf], the ONE rule
     * the widget and the desktop share. Pinned by source text, the way this
     * suite already pins the manifest (everySlotHasAReceiver).
     */
    @Test
    fun `the preview arranges with the widget's own rule`() {
        val preview = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/WidgetPreview.kt",
        ).readText()
        assertTrue(
            "the preview must arrange through JarvisWidgets.boardOf, not an arrangement of its own",
            preview.contains("JarvisWidgets.boardOf(view)"),
        )
        assertTrue(
            "the preview must draw the look's colours through the shared parser",
            preview.contains("JarvisWidgets.argb("),
        )
        assertTrue(
            "the preview must read the shade's two alphas",
            preview.contains("shade.alpha") && preview.contains("shade.surfaceAlpha"),
        )
        val plate = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/WidgetsPlate.kt",
        ).readText()
        assertTrue("the draft must draw the preview", plate.contains("WidgetPreview("))
        assertTrue("the draft must offer the look pickers", plate.contains("LookPickers("))
        assertTrue(
            "Add must send the look it is showing",
            plate.contains("JarvisRuntime.widgetAdd(d.id, look)"),
        )
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
        // The list the phone pins through is the same list this test counts:
        // WidgetPin builds a ComponentName from JarvisWidgets.PIN_RECEIVERS, so
        // a slot added there without a manifest receiver (or the other way
        // round) is caught here rather than on the owner's home screen.
        val receivers = JarvisWidgets.PIN_RECEIVERS.map { it.removePrefix(".widget.") }
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

    /**
     * "Put it on my home screen" (the owner, 2026-10-30): the phone asks the
     * launcher itself instead of only telling the owner the touch-and-hold
     * route. Android answers whether the REQUEST was sent, not whether a
     * widget was placed, so the asked sentence must never read as done - and
     * the cannot sentence must give the manual route in words.
     */
    @Test
    fun `the pin sentences say only what the launcher answered`() {
        for (slot in 0 until JarvisWidgets.SLOTS) {
            val n = slot + 1
            val asked = JarvisWidgets.pinSentence(requested = true, alreadyThere = false, slot = slot)
            assertTrue("slot $n must name its widget:\n$asked", asked.contains("Jarvis widget $n"))
            assertTrue("slot $n must say it was ASKED:\n$asked", asked.contains("was asked"))
            assertFalse("slot $n must not claim the widget is there:\n$asked", asked.contains("was added"))

            val already = JarvisWidgets.pinSentence(requested = true, alreadyThere = true, slot = slot)
            assertTrue(already.contains("already"))
            assertTrue(already.contains("Jarvis widget $n"))

            val cannot = JarvisWidgets.pinSentence(requested = false, alreadyThere = false, slot = slot)
            assertTrue("slot $n needs the manual route:\n$cannot", cannot.contains("Touch and hold"))
            assertTrue(cannot.contains("Jarvis widget $n"))
            assertFalse("slot $n must not pretend it asked:\n$cannot", cannot.contains("was asked"))
        }
        assertTrue(
            "the button's words must name the home screen",
            JarvisWidgets.PIN_LABEL.contains("home screen"),
        )
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
        // show reads a saved widget AND, since 2026-11-14, a preview - which
        // is how the phone's preview draws real values; nothing else may pass.
        assertTrue(JarvisWidgets.showableId("w0123456789"))
        assertTrue(JarvisWidgets.showableId("dabcdef0123"))
        assertFalse(JarvisWidgets.showableId("0123456789"))
        assertFalse(JarvisWidgets.showableId("../../x"))
        assertFalse(JarvisWidgets.showableId(null))
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
