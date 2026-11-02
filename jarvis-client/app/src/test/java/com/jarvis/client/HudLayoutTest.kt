package com.jarvis.client

import com.jarvis.client.net.HudLayout
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's editable Home HUD, A1: the layout model, the ONE reducer, the
 * five built-in presets and the closed-world sanitizer - on a plain JVM, so
 * every rule the edit screen, a drag, a button, a TalkBack custom action and a
 * pasted document rely on is tested here rather than only on a device.
 *
 * The desktop equivalent is jarvis-desktop/src/hud-layout.js (H1) and its
 * hud-layout.mjs checks; this file is the phone's half, with the phone's own
 * ids, and deliberately does NOT read contract/hud-presets.json (desktop-only
 * data, docs/ARCHITECTURE.md section 8).
 */
class HudLayoutTest {

    private fun sections(layout: HudLayout.Layout): Map<String, List<String>> =
        HudLayout.SECTIONS.associateWith { layout.items(it) }

    @Test
    fun `the default layout holds every card once and every protected card is in it`() {
        val d = HudLayout.defaults()
        val all = d.visibleCards()
        assertEquals("a card appears exactly once", all.size, all.toSet().size)
        for (card in HudLayout.CARDS) {
            if (card.indicator) continue
            assertTrue("${card.id} is missing", card.id in all)
            assertEquals("${card.id} is in its own section", card.section, d.sectionOf(card.id))
        }
        for (id in listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)) {
            assertTrue("$id is protected", HudLayout.isProtected(id))
            assertTrue("$id is in the default layout", id in all)
        }
        for (indicator in HudLayout.INDICATORS) {
            assertFalse("${indicator.id} is not a stored card", indicator.id in all)
        }
    }

    @Test
    fun `the sanitizer is a closed world - unknown ids, other-app menus and indicators are dropped`() {
        val hostile = HudLayout.Layout(
            HudLayout.VERSION,
            mapOf(
                HudLayout.TOP_STRIP to listOf("no.such.card", "indicator.app-lock",
                    "brain.now.right-now", "brain.now.right-now"),
                // A desktop-only menu must not become a phone home card.
                HudLayout.HERO to listOf("settings.first-run"),
                HudLayout.BODY to listOf("brain.work.today", "brain.work.today"),
                HudLayout.COMPOSER to emptyList(),
            ),
        )
        val safe = HudLayout.normalize(hostile)
        val all = safe.visibleCards()
        assertFalse("a made-up id is dropped", "no.such.card" in all)
        assertFalse("an indicator is not a card", "indicator.app-lock" in all)
        assertFalse("the desktop's menu is dropped", "settings.first-run" in all)
        assertEquals("a duplicate keeps its first place", 1, all.count { it == "brain.now.right-now" })
        assertEquals("two ordinary cards survived", 2, all.count { it in setOf("brain.now.right-now", "brain.work.today") })
        for (id in listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)) {
            assertTrue("$id is forced back in", id in all)
        }
    }

    @Test
    fun `a layout with an unknown version reads as the default and never as an edit`() {
        val old = HudLayout.Layout(99, mapOf(HudLayout.BODY to listOf("brain.work.today")))
        assertEquals(HudLayout.defaults(), HudLayout.normalize(old))
        assertEquals(HudLayout.defaults(), HudLayout.fromJson("""{"version":99,"sections":{}}"""))
    }

    @Test
    fun `the ONE reducer moves a card, and drag and buttons are the same action`() {
        val d = HudLayout.defaults()
        val moved = HudLayout.apply(d, HudLayout.Action.Move("brain.work.today", HudLayout.HERO, 1))
        assertEquals(HudLayout.HERO, moved.sectionOf("brain.work.today"))
        assertEquals("brain.work.today", moved.items(HudLayout.HERO)[1])
        assertFalse("it left the body", HudLayout.BODY == moved.sectionOf("brain.work.today"))
        // The drag path and the button path are the SAME reducer call.
        val viaButton = HudLayout.apply(d, HudLayout.Action.Move("brain.work.today", HudLayout.HERO, 1))
        assertEquals("drag and buttons cannot disagree", moved, viaButton)
        // A no-op drop is not an edit.
        assertEquals(d, HudLayout.apply(d, HudLayout.Action.Move("brain.work.today",
            d.sectionOf("brain.work.today")!!, d.items(d.sectionOf("brain.work.today")!!).indexOf("brain.work.today"))))
        // Unlisted and unknown moves are refused, not guessed at.
        assertNull(HudLayout.move(d, "no.such.card", HudLayout.BODY, 0))
        assertNull(HudLayout.move(d, "brain.work.today", "no_such_section", 0))
    }

    @Test
    fun `earlier, later, first and last all go through the same reducer`() {
        val d = HudLayout.defaults()
        val body = d.items(HudLayout.BODY)
        val later = HudLayout.apply(d, HudLayout.Action.Later(body[0]))
        assertEquals(listOf(body[1], body[0]), later.items(HudLayout.BODY).take(2))
        val earlier = HudLayout.apply(later, HudLayout.Action.Earlier(body[0]))
        assertEquals(body.take(2), earlier.items(HudLayout.BODY).take(2))
        val first = HudLayout.apply(d, HudLayout.Action.First(body[2]))
        assertEquals(body[2], first.items(HudLayout.BODY).first())
        val last = HudLayout.apply(d, HudLayout.Action.Last(body[0]))
        assertEquals(body[0], last.items(HudLayout.BODY).last())
        // Last in another section is a cross-section move.
        val heroLast = HudLayout.apply(d, HudLayout.Action.Last("brain.work.today", HudLayout.HERO))
        assertEquals("brain.work.today", heroLast.items(HudLayout.HERO).last())
        // The first card cannot move earlier; nothing changes instead of a jump.
        assertEquals(d, HudLayout.apply(d, HudLayout.Action.Earlier(body.first())))
    }

    @Test
    fun `the five built-in presets are read-only data, each safe, each with the protected cards`() {
        val presets = HudLayout.BUILT_IN_PRESETS
        assertEquals(5, presets.size)
        assertEquals(listOf("default", "live", "brain", "ops", "calm"), presets.map { it.id })
        val titles = presets.map { it.title }
        assertEquals(listOf("Default", "Live & Voice", "Brain & Learning",
            "Everyday Ops", "Calm"), titles)
        assertEquals("the ids are distinct", 5, presets.map { it.layout }.toSet().size)
        for (p in presets) {
            assertTrue("${p.id} is built in", p.builtIn)
            val norm = HudLayout.normalize(p.layout)
            for (id in listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)) {
                assertTrue("${p.id} keeps $id", id in norm.visibleCards())
            }
            for (id in norm.visibleCards()) {
                assertNotNull("${p.id} names a real card: $id", HudLayout.card(id))
            }
        }
        // Applying one is the reducer too, and an unknown preset changes nothing.
        val d = HudLayout.defaults()
        assertEquals(HudLayout.BUILT_IN_PRESETS[1].layout,
            HudLayout.apply(d, HudLayout.Action.ApplyPreset("live")))
        assertEquals(d, HudLayout.apply(d, HudLayout.Action.ApplyPreset("no-such-preset")))
        assertEquals(HudLayout.defaults(), HudLayout.apply(d, HudLayout.Action.Reset))
    }

    @Test
    fun `a copy for the owner is normalized and the built-in itself never changes`() {
        val d = HudLayout.defaults()
        // The Default PRESET is its own arrangement, not HudLayout.defaults();
        // the rule is that the built-in data does not change when a copy is made.
        val builtInDefault = HudLayout.BUILT_IN_PRESETS.first { it.id == "default" }.layout
        val copy = HudLayout.copyAs("  My   evening  ", d)
        assertFalse(copy.builtIn)
        assertTrue(copy.id.startsWith("custom."))
        assertEquals("My evening", copy.title)
        assertEquals(HudLayout.defaults(), copy.layout)
        val changed = HudLayout.apply(copy.layout, HudLayout.Action.Reset)
        assertEquals(HudLayout.defaults(), changed)
        assertEquals("the built-in preset is untouched by a copy", builtInDefault,
            HudLayout.BUILT_IN_PRESETS.first { it.id == "default" }.layout)
        // A title that cannot be an id still gets a safe one.
        val odd = HudLayout.copyAs("!!!", d)
        assertEquals("My layout", odd.title)
        assertTrue(odd.id.startsWith("custom."))
    }

    @Test
    fun `JSON round-trips the layout and a pasted document cannot smuggle anything in`() {
        val custom = HudLayout.apply(HudLayout.defaults(),
            HudLayout.Action.Move("brain.work.today", HudLayout.HERO, 0))
        val json = HudLayout.toJson(custom)
        assertEquals(custom, HudLayout.fromJson(json))
        assertFalse("x and y are never written", "x" in json || "\"y\"" in json)

        // A hand-edited / imported document: unknown ids, an indicator, a
        // desktop-only menu, a duplicate, and a section with a wrong shape.
        val pasted = """
            {"version":1,
             "sections":{
               "top_strip":["brain.now.trace","no.such.card","indicator.rush-latch","brain.now.trace"],
               "hero":["settings.first-run", 42],
               "body":"not-a-list",
               "composer":["settings.voice"]
             },
             "x":10, "y":20, "__proto__":{"polluted":true}}
        """.trimIndent()
        val safe = HudLayout.fromJson(pasted)!!
        val all = safe.visibleCards()
        assertFalse("no.such.card" in all)
        assertFalse("indicator.rush-latch" in all)
        assertFalse("settings.first-run" in all)
        assertEquals(1, all.count { it == "brain.now.trace" })
        assertTrue("settings.voice" in all)
        for (id in listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)) {
            assertTrue("$id survived the import", id in all)
        }
        assertNull("not JSON at all", HudLayout.fromJson("not json"))
        assertNull("no version", HudLayout.fromJson("""{"sections":{}}"""))
        assertNull("no sections", HudLayout.fromJson("""{"version":1}"""))
    }

    @Test
    fun `hiding a menu empties its card, but a protected card ignores hiding`() {
        val d = HudLayout.defaults()
        val hidden = MenuView(MenuState(hidden = setOf("brain.work.today", "entry.appearance")))
        val visible = HudLayout.visible(d, hidden)
        assertFalse("brain.work.today" in visible.getValue(HudLayout.BODY))
        assertFalse("entry.appearance" in visible.getValue(HudLayout.HERO))
        assertTrue("the approvals card is not hideable", HudLayout.APPROVALS in
            visible.getValue(HudLayout.TOP_STRIP))
        assertTrue("the Live card is not hideable", HudLayout.LIVE in
            visible.getValue(HudLayout.HERO))
    }

    @Test
    fun `two window sizes choose the body column count`() {
        assertEquals(1, HudLayout.columnsAt(360))
        assertEquals(1, HudLayout.columnsAt(HudLayout.TWO_COLUMN_DP - 1))
        assertEquals(2, HudLayout.columnsAt(HudLayout.TWO_COLUMN_DP))
        assertEquals(2, HudLayout.columnsAt(1280))
    }

    @Test
    fun `an action that would touch a protected card's place is refused, never guessed`() {
        // There is no hide action in the model at all; a protected card cannot
        // be removed by an ordinary move either, and its section order is
        // restored by normalize after any edit.
        val d = HudLayout.defaults()
        val movedAway = HudLayout.apply(d, HudLayout.Action.Move(HudLayout.APPROVALS, HudLayout.BODY, 0))
        assertTrue("a move still shows the approvals card",
            HudLayout.APPROVALS in movedAway.visibleCards())
        assertFalse("an indicator is not a movable card",
            HudLayout.INDICATORS.any { it.id in movedAway.visibleCards() })
        for (id in HudLayout.INDICATORS.map { it.id }) {
            assertNull("an indicator cannot be moved", HudLayout.move(d, id, HudLayout.BODY, 0))
        }
    }

    @Test
    fun `the reducer adds a card the layout does not hold, and nothing else`() {
        // The edit screen's "Add" (2026-11-02): a card a preset left out can be
        // put back - through the SAME reducer a move goes through, so there is
        // no second way into a layout.
        val calm = HudLayout.BUILT_IN_PRESETS.first { it.id == "calm" }.layout
        val missing = HudLayout.missingFrom(calm)
        assertTrue("Calm holds fewer cards than the phone has", missing.isNotEmpty())
        val added = HudLayout.apply(calm, HudLayout.Action.Add(missing[0], HudLayout.BODY))
        assertTrue("${missing[0]} is back", missing[0] in added.visibleCards())
        assertEquals("in the section it was asked for", HudLayout.BODY, added.sectionOf(missing[0]))
        assertEquals("at the end when no place is given", missing[0], added.items(HudLayout.BODY).last())
        val atStart = HudLayout.apply(calm, HudLayout.Action.Add(missing[0], HudLayout.BODY, 0))
        assertEquals(missing[0], atStart.items(HudLayout.BODY).first())
        // The closed world still holds: no invented id, no indicator, no
        // duplicate, no section that does not exist.
        assertEquals(calm, HudLayout.apply(calm, HudLayout.Action.Add("no.such.card", HudLayout.BODY)))
        for (indicator in HudLayout.INDICATORS) {
            assertEquals(calm, HudLayout.apply(calm, HudLayout.Action.Add(indicator.id, HudLayout.BODY)))
        }
        val present = added.visibleCards().first()
        assertEquals(added, HudLayout.apply(added, HudLayout.Action.Add(present, HudLayout.HERO)))
        assertNull(HudLayout.add(calm, missing[0], "no_such_section"))
        // And it answers the same layout, not a crash, for a card the layout
        // already holds.
        assertEquals(calm, HudLayout.apply(calm, HudLayout.Action.Add(HudLayout.LIVE, HudLayout.BODY)))
    }

    @Test
    fun `every action leaves the three safety cards present exactly once`() {
        // The invariant an editor, a drag and a paste all lean on: whatever the
        // action, [HudLayout.normalize] has already run, so a safety surface is
        // in the answer once and an indicator never is.
        val d = HudLayout.defaults()
        val body = d.items(HudLayout.BODY)
        val actions = listOf(
            HudLayout.Action.Move(HudLayout.APPROVALS, HudLayout.COMPOSER, 0),
            HudLayout.Action.Move(HudLayout.EMERGENCY_STOP, HudLayout.BODY, 1),
            HudLayout.Action.Move(HudLayout.LIVE, HudLayout.TOP_STRIP, 0),
            HudLayout.Action.Earlier(HudLayout.LIVE),
            HudLayout.Action.Later(HudLayout.APPROVALS),
            HudLayout.Action.First(HudLayout.LIVE, HudLayout.COMPOSER),
            HudLayout.Action.Last(HudLayout.APPROVALS),
            HudLayout.Action.Add(body[0], HudLayout.TOP_STRIP),
            HudLayout.Action.Move(body[0], HudLayout.HERO, 0),
            HudLayout.Action.Reset,
        ) + HudLayout.BUILT_IN_PRESETS.map { HudLayout.Action.ApplyPreset(it.id) } +
            HudLayout.BUILT_IN_PRESETS.map { HudLayout.Action.Last(HudLayout.LIVE, it.layout.sectionOf(HudLayout.LIVE)) }
        for (action in actions) {
            val out = HudLayout.apply(d, action)
            val all = out.visibleCards()
            for (id in listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)) {
                assertEquals("$action keeps $id once", 1, all.count { it == id })
            }
            assertFalse("$action never stores an indicator",
                HudLayout.INDICATORS.any { it.id in all })
        }
    }
}
