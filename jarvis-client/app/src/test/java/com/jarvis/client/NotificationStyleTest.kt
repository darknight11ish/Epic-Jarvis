package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.NotificationStyle
import com.jarvis.client.net.NotificationStyle.Figure
import com.jarvis.client.net.NotificationStyle.Kind
import com.jarvis.client.net.NotificationStyle.Motion
import com.jarvis.client.net.NotificationStyle.Speed
import com.jarvis.client.net.NotificationStyle.Theme
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Notification styles you describe" (docs/JARVIS-API.md section 167; the
 * owner's ask of 2026-10-30).
 *
 * Everything here is the PURE decision layer: the wire enums, the strict
 * second check, and [NotificationStyle.plan] - the one function that says
 * whether a notification may use a style and exactly what it should draw.
 * `NotificationStyle` has no Android types, so these run on a plain JVM.
 *
 * What this file CANNOT prove, and says so in the report: that a device draws
 * the layout. There is no emulator here. The layout's own constraints are
 * pinned from its file instead (only RemoteViews-allowed classes, autoStart on
 * the flipper), and the app builds - which is the strongest claim available
 * from this desk.
 */
class NotificationStyleTest {

    private fun spec(
        name: String = "Ember pulse",
        theme: Theme = Theme.EMBER,
        figure: Figure = Figure.SPARK,
        motion: Motion = Motion.PULSE,
        speed: Speed = Speed.NORMAL,
        kinds: List<Kind> = listOf(Kind.APPROVAL, Kind.REMINDER),
    ) = NotificationStyle.Spec(name, theme, figure, motion, speed, kinds)

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json) as JsonObject

    // ------------------------------------------------------------ the decision

    @Test
    fun `no style means the plain notification`() {
        assertNull("nothing saved for this kind", NotificationStyle.plan(null, Kind.APPROVAL, false))
    }

    @Test
    fun `a locked phone never gets the fancy layout`() {
        val s = spec()
        assertNull("App lock / private lists / no secure lock", NotificationStyle.plan(s, Kind.APPROVAL, true))
        assertNotNull("the same style, unlocked", NotificationStyle.plan(s, Kind.APPROVAL, false))
    }

    @Test
    fun `a style only applies to the kinds it claims`() {
        val onlyReminders = spec(kinds = listOf(Kind.REMINDER))
        assertNotNull(NotificationStyle.plan(onlyReminders, Kind.REMINDER, false))
        assertNull(NotificationStyle.plan(onlyReminders, Kind.APPROVAL, false))
    }

    @Test
    fun `a pulse draws two frames of the figure`() {
        val plan = NotificationStyle.plan(spec(figure = Figure.STAR), Kind.APPROVAL, false)!!
        assertEquals("two frames", 2, plan.frames.size)
        assertEquals(Figure.STAR.glyph, plan.frames[0].glyph)
        assertEquals(Figure.STAR.glyph, plan.frames[1].glyph)
        assertNotEquals("the second frame is dimmer", plan.frames[0].colour, plan.frames[1].colour)
        assertFalse(plan.spinner)
        assertNull("nothing still", plan.stillGlyph)
    }

    @Test
    fun `a flip swaps the figure for a dot`() {
        val plan = NotificationStyle.plan(spec(motion = Motion.FLIP, figure = Figure.RING), Kind.APPROVAL, false)!!
        assertEquals(2, plan.frames.size)
        assertEquals(Figure.RING.glyph, plan.frames[0].glyph)
        assertEquals(Figure.DOT.glyph, plan.frames[1].glyph)
    }

    @Test
    fun `a spinner spins and keeps the figure still`() {
        val plan = NotificationStyle.plan(spec(motion = Motion.SPINNER, figure = Figure.ARROW), Kind.APPROVAL, false)!!
        assertTrue(plan.spinner)
        assertTrue("no flipping frames", plan.frames.isEmpty())
        assertEquals("the figure is still shown", Figure.ARROW.glyph, plan.stillGlyph)
    }

    @Test
    fun `nothing moving gets one still frame and no timer`() {
        val plan = NotificationStyle.plan(spec(motion = Motion.NONE, figure = Figure.SPARK), Kind.APPROVAL, false)!!
        assertTrue(plan.frames.isEmpty())
        assertFalse(plan.spinner)
        assertEquals(Figure.SPARK.glyph, plan.stillGlyph)
        assertTrue("a still style asks SystemUI for no timer", plan.intervalMs >= 60_000)
    }

    @Test
    fun `the speed buckets are the only speeds`() {
        assertEquals(600_000, NotificationStyle.plan(spec(motion = Motion.NONE), Kind.APPROVAL, false)!!.intervalMs)
        for ((speed, ms) in listOf(Speed.SLOW to 1800, Speed.NORMAL to 900, Speed.FAST to 450)) {
            assertEquals(ms, NotificationStyle.plan(spec(speed = speed), Kind.APPROVAL, false)!!.intervalMs)
        }
    }

    @Test
    fun `the chip is dark and the glyph bright in every theme`() {
        for (t in Theme.entries) {
            val plan = NotificationStyle.plan(spec(theme = t), Kind.APPROVAL, false)!!
            assertEquals(t.chip, plan.chip)
            assertEquals(t.accent, plan.frames[0].colour)
            // Every -2 step is darker than its -4 step: the pairing the layout
            // relies on so the figure is readable on any shade background.
            assertTrue("${t.wire}: chip darker than accent", lum(t.chip) < lum(t.accent))
        }
    }

    private fun lum(c: Int): Int {
        fun ch(shift: Int) = (c shr shift) and 0xFF
        return ch(16) * 299 + ch(8) * 587 + ch(0) * 114
    }

    // ------------------------------------------------------------ the wire

    @Test
    fun `a checked style reads back exactly`() {
        val s = NotificationStyle.fromJson(
            obj(
                """{"name":"Ember pulse","theme":"ember","figure":"spark","motion":"pulse",
                   "speed":"normal","kinds":["approval","reminder"]}""",
            ),
        )!!
        assertEquals("Ember pulse", s.name)
        assertEquals(Theme.EMBER, s.theme)
        assertEquals(Figure.SPARK, s.figure)
        assertEquals(Motion.PULSE, s.motion)
        assertEquals(Speed.NORMAL, s.speed)
        assertEquals(listOf(Kind.APPROVAL, Kind.REMINDER), s.kinds)
    }

    @Test
    fun `anything off the menu is unusable, not close enough`() {
        val bad = listOf(
            """{"name":"x","theme":"rainbow","figure":"spark","motion":"pulse","speed":"normal","kinds":["approval"]}""",
            """{"name":"x","theme":"ember","figure":"dragon","motion":"pulse","speed":"normal","kinds":["approval"]}""",
            """{"name":"x","theme":"ember","figure":"spark","motion":"lottie","speed":"normal","kinds":["approval"]}""",
            """{"name":"x","theme":"ember","figure":"spark","motion":"pulse","speed":"instant","kinds":["approval"]}""",
            """{"name":"x","theme":"ember","figure":"spark","motion":"pulse","speed":"normal","kinds":["chatbot"]}""",
            """{"name":"x","theme":"ember","figure":"spark","motion":"pulse","speed":"normal","kinds":[]}""",
            """{"name":"","theme":"ember","figure":"spark","motion":"pulse","speed":"normal","kinds":["approval"]}""",
            """{"name":"x","figure":"spark","motion":"pulse","speed":"normal","kinds":["approval"]}""",
            """{"name":"x","theme":"ember","figure":"spark","motion":"pulse","speed":"normal"}""",
            // a colour value where a NAME belongs: the PC can never send one
            """{"name":"x","theme":"#ff0000","figure":"spark","motion":"pulse","speed":"normal","kinds":["approval"]}""",
            // a kind named twice is a broken message, not a style
            """{"name":"x","theme":"ember","figure":"spark","motion":"pulse","speed":"normal","kinds":["approval","approval"]}""",
            // an empty object is not a style either (no key at all)
            """{}""",
        )
        for (raw in bad) {
            assertNull("must be refused: $raw", NotificationStyle.fromJson(obj(raw)))
        }
        assertNull("null is not a style", NotificationStyle.fromJson(null))
    }

    @Test
    fun `the book keeps only what this app knows`() {
        val book = NotificationStyle.bookOf(
            obj(
                """{"ok":true,
                    "styles":[{"id":"s0123456789","name":"Ember pulse","said":"A style.",
                               "parts":["Colour: warm orange"]}],
                    "drafts":[],
                    "active":{"approval":{"name":"Ember pulse","theme":"ember","figure":"spark",
                                          "motion":"pulse","speed":"normal","kinds":["approval"]},
                              "chatbot":{"name":"nope","theme":"ember","figure":"spark",
                                         "motion":"pulse","speed":"normal","kinds":["approval"]}},
                    "live":["approval","chatbot"],
                    "nothing_on":"No style is live."}""",
            ),
        )
        assertEquals(1, book.active.size)
        assertEquals("Ember pulse", book.active[Kind.APPROVAL]?.name)
        assertEquals("a kind this app does not know is dropped", listOf("approval"), book.live)
        assertEquals(1, book.styles.size)
        assertEquals("s0123456789", book.styles[0].id)
        assertEquals("No style is live.", book.nothingOn)
    }

    @Test
    fun `an unreachable PC is an empty book, not an exception`() {
        assertEquals(NotificationStyle.Book.EMPTY, NotificationStyle.bookOf(null))
        assertEquals(
            NotificationStyle.Book.EMPTY,
            NotificationStyle.bookOf(obj("""{"ok":true}""")),
        )
    }

    @Test
    fun `ids and drafts are the shapes the PC makes`() {
        assertTrue(NotificationStyle.validId("s0123456789"))
        assertFalse(NotificationStyle.validId("sxyz"))
        assertFalse(NotificationStyle.validId(null))
        assertTrue(NotificationStyle.validDraft("d0123456789"))
        assertFalse(NotificationStyle.validDraft("s0123456789"))
    }

    @Test
    fun `typed words become a typed draft and nothing else`() {
        assertEquals(
            """{"words":"warm orange, a spark","provenance":"typed"}""",
            NotificationStyle.draftBody("  warm   orange,  a spark\n"),
        )
        assertNull("empty", NotificationStyle.draftBody("   "))
        assertNull("too long", NotificationStyle.draftBody("x".repeat(NotificationStyle.MAX_WORDS + 1)))
    }

    @Test
    fun `a post's answer is the PC's sentence`() {
        assertEquals(true to "Added.", NotificationStyle.said(200, obj("""{"ok":true,"said":"Added."}""")))
        assertEquals(false to "No model.", NotificationStyle.said(503, obj("""{"ok":false,"error":"No model."}""")))
        assertEquals(false to NotificationStyle.MISSING, NotificationStyle.said(404, null))
    }

    @Test
    fun `the live line names the kind and the style`() {
        val s = spec()
        val book = NotificationStyle.Book(
            active = mapOf(Kind.REMINDER to s),
            live = listOf("reminder"),
            styles = emptyList(), drafts = emptyList(),
            noCard = "", nothingOn = "No style is live.",
        )
        val line = NotificationStyle.liveLine(book)
        assertTrue(line, line.contains("reminders") && line.contains("Ember pulse"))
        assertEquals(
            "nothing live is said plainly",
            "No style is live.",
            NotificationStyle.liveLine(NotificationStyle.Book.EMPTY),
        )
    }

    // ------------------------------------------------------------ the layout

    /**
     * The custom layout may contain ONLY classes RemoteViews allows, because
     * SystemUI refuses any other class when it inflates the notification. This
     * is the check that keeps a future edit from adding a Lottie view or a
     * ComposeView "because it looks nicer": that would not be a style, it
     * would be a notification that fails to draw.
     */
    @Test
    fun `the styled layout uses only views a notification can inflate`() {
        val allowed = setOf(
            "LinearLayout", "FrameLayout", "RelativeLayout", "GridLayout",
            "ViewFlipper", "TextView", "ImageView", "Button", "ImageButton",
            "ProgressBar", "Chronometer", "AnalogClock", "TextClock",
        )
        for (rel in listOf(
            "jarvis-client/app/src/main/res/layout/notification_styled.xml",
            "jarvis-client/app/src/main/res/layout/notification_styled_expanded.xml",
            "jarvis-client/app/src/main/res/layout/notification_style_frame.xml",
        )) {
            val text = SourceFile.read(rel)
            val tags = Regex("<([A-Z][A-Za-z]+)[\\s/>]").findAll(text).map { it.groupValues[1] }.toSet()
            assertTrue("$rel must not be empty", tags.isNotEmpty())
            for (tag in tags) {
                assertTrue("$rel uses <$tag>, which RemoteViews does not allow", tag in allowed)
            }
        }
    }

    @Test
    fun `the flipper starts itself, because setAutoStart is not remote-callable`() {
        for (rel in listOf(
            "jarvis-client/app/src/main/res/layout/notification_styled.xml",
            "jarvis-client/app/src/main/res/layout/notification_styled_expanded.xml",
        )) {
            val text = SourceFile.read(rel)
            assertTrue("$rel: autoStart must be a layout attribute", text.contains("android:autoStart=\"true\""))
            assertTrue("$rel: the flip fades in", text.contains("@anim/notification_frame_in"))
        }
    }

    @Test
    fun `both notifiers ask the style layer, and only with a lock flag`() {
        val approval = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/ApprovalNotifier.kt",
        )
        val schedule = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/ScheduleNotifier.kt",
        )
        assertTrue("the approval card is styled", approval.contains("StyledNotification.apply("))
        assertTrue("the reminder is styled", schedule.contains("StyledNotification.apply("))
        assertTrue("the approval card passes its lock flag",
            approval.contains("NotificationStyle.Kind.APPROVAL, title, body, locked"))
        assertTrue("the reminder passes its lock flag",
            schedule.contains("NotificationStyle.Kind.REMINDER, title, text, locked"))
        // The two rules that must survive any restyling.
        assertFalse("an approval is never approvable from a notification",
            approval.contains("approval_approve_action"))
        assertTrue("Deny is still the only action offered",
            approval.contains("approval_deny_action"))
        assertTrue("the quiet/late notice is never styled",
            schedule.contains("if (!quiet && !openBriefing && scheduleKind.isNotEmpty())"))
    }
}
