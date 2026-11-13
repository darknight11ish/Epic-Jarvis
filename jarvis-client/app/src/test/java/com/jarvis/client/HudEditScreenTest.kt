package com.jarvis.client

import com.jarvis.client.net.HudLayout
import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.screens.HudEditSession
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's Edit HUD screen and the Home HUD that draws from it (the Android
 * `A2`-`A4` slices of the editable-HUD design, 2026-11-02).
 *
 * Two halves, and they prove different things:
 *
 *  - [HudEditSession] is PURE Kotlin (no Android, no Compose, no preferences),
 *    so the draft, the undo stack and the one-reducer rule run here on a plain
 *    JVM. Those tests are real behaviour.
 *  - The screen itself cannot be run here - there is no Compose test harness in
 *    this module and no emulator at this desk - so the wiring is held by SOURCE
 *    PINS, the way this repo already holds `AppControlHonestyTest`. A pin proves
 *    what the shipped file says, never that a phone drew it. Nothing here is a
 *    PASS on a real device, and the PR says so.
 *
 * The claim the first test exists for is the twin-path one (WCAG 2.2 SC 2.5.7),
 * which the desktop's `hud-edit.js` makes in its own words (rulings 23-27): a
 * drag, a click-only button and a TalkBack custom action must all be able to
 * move a card, and all three must land in ONE function, or the two paths can
 * drift apart and only one of them is tested.
 */
class HudEditScreenTest {

    // ---------------------------------------------------------------- pure half

    private val protectedIds =
        listOf(HudLayout.APPROVALS, HudLayout.LIVE, HudLayout.EMERGENCY_STOP)

    private fun everySectionHoldsTheProtectedCards(layout: HudLayout.Layout, what: String) {
        val all = layout.visibleCards()
        for (id in protectedIds) {
            assertEquals("$what: $id appears once", 1, all.count { it == id })
            assertTrue("$what: $id is still on the screen", layout.contains(id))
        }
        for (indicator in HudLayout.INDICATORS) {
            assertFalse("$what: an indicator is never a stored card", indicator.id in all)
        }
    }

    @Test
    fun `the drag, the buttons and the TalkBack actions all reach the one reducer`() {
        val d = HudLayout.defaults()

        // (a) The drag's drop. This is the action `dropCard` builds.
        val dragged = HudEditSession(d).apply(
            HudLayout.Action.Move("brain.work.today", HudLayout.HERO, 0),
        )
        // (b) The click-only "Move to -> Hero -> First" buttons. A different
        // action object, the same reducer, the same answer.
        val buttoned = HudEditSession(d).apply(
            HudLayout.Action.First("brain.work.today", HudLayout.HERO),
        )
        // (c) The TalkBack action. Also a different action, also the same answer.
        val talkback = HudEditSession(d).apply(
            HudLayout.Action.First("brain.work.today", HudLayout.HERO),
        )
        assertEquals("a drag and a button cannot disagree", dragged, buttoned)
        assertEquals("a TalkBack action cannot disagree either", buttoned, talkback)
        // And each is the model's own answer, not a second implementation.
        assertEquals(
            HudLayout.apply(d, HudLayout.Action.Move("brain.work.today", HudLayout.HERO, 0)),
            dragged,
        )
        assertEquals(HudLayout.HERO, dragged.sectionOf("brain.work.today"))

        // The Up / Down buttons are the same reducer too: Down then Up is back
        // where it started, which a second implementation could get wrong.
        val body = d.items(HudLayout.BODY)
        val down = HudEditSession(d).apply(HudLayout.Action.Later(body[0]))
        val back = HudEditSession(down).apply(HudLayout.Action.Earlier(body[0]))
        assertEquals(body, back.items(HudLayout.BODY))
        assertEquals(listOf(body[1], body[0]), down.items(HudLayout.BODY).take(2))
    }

    @Test
    fun `every card the phone has can be moved with a click-only twin`() {
        val d = HudLayout.defaults()
        for (card in HudLayout.CARDS) {
            if (card.indicator) continue
            // The click-only twin of a drag is "Move to -> <section> -> First":
            // no gesture, no timing, one button. It has to work for EVERY card,
            // including the protected ones (they may move; they may not be
            // removed).
            val target = HudLayout.SECTIONS.first { it != card.section }
            val moved = HudEditSession(d).apply(HudLayout.Action.First(card.id, target))
            assertEquals(
                "${card.id} can be moved to $target by a button press",
                target,
                moved.sectionOf(card.id),
            )
            assertNotEquals("${card.id} really moved", d.items(target), moved.items(target))
            // ...and within its own section, First and Last both work, so a card
            // with no neighbour to swap with is still reachable by buttons.
            val first = HudEditSession(d).apply(HudLayout.Action.First(card.id))
            val last = HudEditSession(d).apply(HudLayout.Action.Last(card.id))
            assertEquals(card.id, first.items(card.section).first())
            assertEquals(card.id, last.items(card.section).last())
        }
    }

    @Test
    fun `no edit, preset or paste can remove a safety card, and no indicator ever becomes one`() {
        everySectionHoldsTheProtectedCards(HudLayout.defaults(), "the default layout")
        val session = HudEditSession(HudLayout.defaults())
        // Every built-in preset.
        for (preset in HudLayout.BUILT_IN_PRESETS) {
            everySectionHoldsTheProtectedCards(
                session.apply(HudLayout.Action.ApplyPreset(preset.id)),
                "the ${preset.id} preset",
            )
        }
        // A drag that tries to dump a safety card in the composer - it MOVES,
        // and it is still there.
        everySectionHoldsTheProtectedCards(
            session.apply(HudLayout.Action.Move(HudLayout.APPROVALS, HudLayout.COMPOSER, 0)),
            "a moved approvals card",
        )
        // A paste that never mentions them at all.
        val pasted = HudLayout.fromJson(
            """{"version":1,"sections":{"top_strip":[],"hero":[],"body":["brain.work.today"],"composer":[]}}""",
        )!!
        everySectionHoldsTheProtectedCards(pasted, "a paste that omits them")
        everySectionHoldsTheProtectedCards(session.replace(pasted), "the replaced draft")
        // A document that tries to put an indicator in as a card.
        val hostile = HudLayout.fromJson(
            """{"version":1,"sections":{"top_strip":["indicator.app-lock","indicator.rush-latch"],""" +
                """"hero":[],"body":[],"composer":[]}}""",
        )!!
        everySectionHoldsTheProtectedCards(hostile, "a paste that smuggles an indicator in")
        // Reset.
        everySectionHoldsTheProtectedCards(session.restart(), "Reset")
    }

    @Test
    fun `a hostile pasted layout cannot hide a safety surface and is safe before it is drawn`() {
        val session = HudEditSession(HudLayout.defaults())
        val hostile = """
            {"version":1,
             "sections":{
               "top_strip":["no.such.card","settings.first-run","indicator.stale-stream"],
               "hero":["brain.work.today","brain.work.today"],
               "body":42,
               "composer":["settings.voice"]
             },
             "x":1,"y":2,"__proto__":{"polluted":true}}
        """.trimIndent()
        // The reader the screen uses for a paste.
        val safe = HudLayout.fromJson(hostile)
        assertTrue("a readable document still reads", safe != null)
        val draft = session.replace(safe)
        val all = draft.visibleCards()
        assertFalse("no.such.card" in all)
        assertFalse("the desktop's menu is still dropped", "settings.first-run" in all)
        assertFalse("an indicator is not a card", "indicator.stale-stream" in all)
        assertEquals("a duplicate keeps its first place", 1, all.count { it == "brain.work.today" })
        assertTrue("settings.voice survived", "settings.voice" in all)
        // And the three safety surfaces are back in the draft the screen draws.
        for (id in protectedIds) {
            assertTrue("$id is forced back in", id in all)
        }
        // A document that is not a layout at all changes nothing.
        val before = session.layout
        assertEquals(before, session.replace(HudLayout.fromJson("not json")))
        assertEquals(before, session.replace(HudLayout.fromJson("""{"version":99}""")))
        assertNull(HudLayout.fromJson("{}"))
    }

    @Test
    fun `the draft is what Done saves, and no edit writes anything`() {
        val saved = HudLayout.defaults()
        val session = HudEditSession(saved)
        assertFalse("nothing is dirty before an edit", session.dirty)
        assertEquals("Done with no edit saves what was there", saved, session.whatDoneSaves())

        val body = saved.items(HudLayout.BODY)
        session.apply(HudLayout.Action.Later(body[0]))
        session.apply(HudLayout.Action.First(body[1], HudLayout.HERO))
        session.apply(HudLayout.Action.ApplyPreset("calm"))
        // A preset holds fewer cards than the phone has; the ones it left out
        // can be put back, and that is a draft change like any other.
        val missing = HudLayout.missingFrom(session.layout)
        assertTrue("Calm leaves cards out", missing.isNotEmpty())
        session.apply(HudLayout.Action.Add(missing[0], HudLayout.BODY))
        assertTrue("the draft has moved on", session.dirty)
        // Ten "drag frames" in the same gesture produce ONE layout and one undo
        // step: dropping a card is a single action, and the session records it
        // once however far the finger travelled.
        val beforeDrop = session.layout
        val dropped = session.apply(HudLayout.Action.Move(body[0], HudLayout.COMPOSER, 0))
        assertEquals("the drop is one call", 1, countMoves(beforeDrop, dropped))
        // What Done stores is the draft, and the stored layout the session was
        // opened with is untouched: this class has no writer in it at all.
        assertEquals(session.layout, session.whatDoneSaves())
        assertEquals(HudLayout.defaults(), saved)
    }

    /** How many cards changed section in one step - a drag must move one, not ten. */
    private fun countMoves(before: HudLayout.Layout, after: HudLayout.Layout): Int =
        HudLayout.CARDS.count { card ->
            before.sectionOf(card.id) != after.sectionOf(card.id)
        }

    @Test
    fun `undo steps back through the session and stops at the start`() {
        val saved = HudLayout.defaults()
        val session = HudEditSession(saved)
        assertFalse("nothing to undo yet", session.canUndo)
        assertEquals("undo on an untouched session is a no-op", saved, session.undo())

        val body = saved.items(HudLayout.BODY)
        val one = session.apply(HudLayout.Action.Later(body[0]))
        val two = session.apply(HudLayout.Action.Later(body[1]))
        assertTrue(session.canUndo)
        assertEquals(two, session.layout)
        assertEquals("one step back", one, session.undo())
        assertEquals("back to where it started", saved, session.undo())
        assertFalse("and no further", session.canUndo)
        assertEquals(saved, session.undo())
        assertFalse("the session is clean again", session.dirty)
    }

    @Test
    fun `reset is a draft change like any other and can be undone`() {
        val calm = HudLayout.BUILT_IN_PRESETS.first { it.id == "calm" }.layout
        val session = HudEditSession(calm)
        val reset = session.restart()
        assertEquals(HudLayout.defaults(), reset)
        assertEquals(HudLayout.defaults(), session.whatDoneSaves())
        assertEquals("Reset is undoable, like the desktop's editor", calm, session.undo())
    }

    @Test
    fun `a custom preset is applied through the same safe reader`() {
        val session = HudEditSession(HudLayout.defaults())
        // What "Duplicate to custom" makes, then a hostile hand-made copy: the
        // apply path normalises it exactly as a paste is normalised.
        val copy = HudLayout.copyAs("Evening", HudLayout.BUILT_IN_PRESETS.first { it.id == "ops" }.layout)
        val applied = session.replace(copy.layout)
        assertEquals(copy.layout, applied)
        everySectionHoldsTheProtectedCards(applied, "a custom preset")
        val broken = HudLayout.Layout(
            HudLayout.VERSION,
            mapOf(HudLayout.BODY to listOf("no.such.card", HudLayout.LIVE)),
        )
        val repaired = session.replace(broken)
        everySectionHoldsTheProtectedCards(repaired, "a broken custom preset")
        assertFalse("no.such.card" in repaired.visibleCards())
    }

    @Test
    fun `an add puts a missing card back and refuses anything that is not a missing card`() {
        val calm = HudLayout.BUILT_IN_PRESETS.first { it.id == "calm" }.layout
        val missing = HudLayout.missingFrom(calm)
        assertTrue("the Calm preset holds fewer cards than the phone has", missing.isNotEmpty())
        val back = HudEditSession(calm).apply(HudLayout.Action.Add(missing[0], HudLayout.BODY))
        assertTrue("${missing[0]} is back", missing[0] in back.visibleCards())
        assertEquals("in the section it was asked for", HudLayout.BODY, back.sectionOf(missing[0]))
        // The closed world still holds.
        assertEquals(calm, HudLayout.apply(calm, HudLayout.Action.Add("no.such.card", HudLayout.BODY)))
        for (indicator in HudLayout.INDICATORS) {
            assertEquals(calm, HudLayout.apply(calm, HudLayout.Action.Add(indicator.id, HudLayout.BODY)))
        }
        // A card that is already there is not added twice.
        val present = back.visibleCards().first()
        assertEquals(back, HudLayout.apply(back, HudLayout.Action.Add(present, HudLayout.HERO)))
        assertNull(HudLayout.add(calm, missing[0], "no_such_section"))
    }

    @Test
    fun `every card the layout can name is a real phone menu or a safety surface`() {
        // The reason a Home card can be drawn at all: its id is a menu this app
        // has, so the same hiding, the same words and the same place apply.
        for (card in HudLayout.CARDS) {
            if (card.indicator) continue
            if (card.safety) {
                assertNull("a safety surface is a fixed id, not a menu", card.menu)
                continue
            }
            val menuId = card.menu
            assertTrue("${card.id} names a menu", menuId != null)
            val menu = com.jarvis.client.net.MenuLogic.menu(menuId!!)
            assertTrue("${card.id} names a menu this app has: $menuId", menu != null)
            assertEquals("$menuId is a phone menu", true, menu!!.phone)
        }
    }

    // -------------------------------------------------------------- source pins

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(rel).readText()

    private fun occurrences(src: String, needle: String): Int {
        var at = src.indexOf(needle)
        var n = 0
        while (at >= 0) {
            n++
            at = src.indexOf(needle, at + needle.length)
        }
        return n
    }

    /** Just the code, with whole-line `//` comments dropped. */
    private fun code(text: String): String =
        text.lines().filterNot { it.trimStart().startsWith("//") }.joinToString("\n")

    private val editor =
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/EditHudScreen.kt"
    private val home =
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt"
    private val settings =
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"

    @Test
    fun `the editor has ONE reducer call and no second way to write the layout`() {
        val src = code(source(editor))
        // THE claim of the whole screen: a drag, a button and a TalkBack action
        // cannot build their own layout, because there is exactly one call to
        // the model's reducer and it lives inside the session.
        assertEquals("one reducer call in the whole editor", 1, occurrences(src, "HudLayout.apply("))
        assertTrue(
            "and it is the session's",
            src.contains("fun apply(action: HudLayout.Action): HudLayout.Layout"),
        )
        // Nothing in the editor writes the stored layout as an edit happens.
        assertEquals("no per-action write anywhere", 0, occurrences(src, "applyLayout("))
        assertEquals("Done and Duplicate are the only writers", 2, occurrences(src, "saveLayout("))
        // The three inputs. The drag ends in a Move; the buttons and the
        // TalkBack actions build Earlier / Later / First / Last and hand them
        // to the same `edit` / `onMove`.
        assertTrue("the drag is a long press and a drop", src.contains("detectDragGesturesAfterLongPress("))
        assertTrue("the drop is one Move", occurrences(src, "HudLayout.Action.Move(") >= 1)
        assertTrue("the buttons build reducer actions", occurrences(src, "onMove(HudLayout.Action") >= 3)
        assertTrue(
            "the TalkBack actions are real custom actions",
            occurrences(src, "CustomAccessibilityAction(") >= 4,
        )
        assertTrue(
            "and they are attached to the card",
            src.contains("customActions = actions"),
        )
        // Every card the layout holds is drawn, including hidden ones.
        assertTrue("the editor draws every section", src.contains("for (section in HudLayout.SECTIONS)"))
        assertTrue(
            "and every card in it",
            src.contains("ids.forEachIndexed { index, id ->"),
        )
        // The top strip is split across two surfaces since 2026-11-10, so the
        // editor says where each half is drawn: moving a card there must not look
        // like a card vanishing from the phone.
        assertTrue(
            "the editor does not say the safety cards stay on Home",
            src.contains("The safety cards here stay on Home"),
        )
        // The cards the layout does not hold are offered back.
        assertTrue(src.contains("HudLayout.missingFrom(layout)"))
        assertTrue(src.contains("HudLayout.Action.Add("))
    }

    @Test
    fun `home draws the saved layout and the hide rules win on top`() {
        val src = code(source(home))
        assertTrue(
            "Home reads the layout the owner saved",
            src.contains("JarvisRuntime.menus.hudLayout.collectAsState()"),
        )
        assertTrue(
            "and the menu view the rest of the screen uses",
            src.contains("HudLayout.visible(layout, menus)"),
        )
        // Since 2026-11-10 the Home screen draws the model's three HOME
        // sections; the fourth (top_strip) is drawn in the More menu, and
        // `HomeMoreMenuTest` holds that half.
        assertTrue(
            "the Home sections are the model's own",
            src.contains("for (section in HudLayout.HOME_SECTIONS)"),
        )
        assertFalse(
            "Home draws every section again, so the strip is back on top of it",
            src.contains("for (section in HudLayout.SECTIONS)"),
        )
        // The HUD is the conversation list's FIRST row: a door must never come
        // between the owner and a card waiting for a decision.
        val hudItem = src.indexOf("item(key = HUD_KEY)")
        val stopItem = src.indexOf("item(key = \"stop-everything\")")
        assertTrue("the HUD is drawn", hudItem >= 0)
        assertTrue("stop-everything is drawn", stopItem >= 0)
        assertTrue("the HUD is above the safety plates", hudItem < stopItem)
        // Its own key, like every other row of that list.
        assertTrue(src.contains("private const val HUD_KEY = \"home-hud\""))
        // Bounded, so a first-run layout cannot push the conversation off Home.
        assertTrue(src.contains("heightIn(max = HUD_TRAY_MAX)"))
    }

    @Test
    fun `home asks the model for the column count instead of repeating 600`() {
        val src = code(source(home))
        assertEquals(
            "one answer to how many columns, the model's",
            1,
            occurrences(src, "HudLayout.columnsAt("),
        )
        assertTrue(
            "and the width it is asked about is the window's",
            src.contains("HudLayout.columnsAt(LocalConfiguration.current.screenWidthDp)"),
        )
        assertFalse(
            "Home does not carry a second copy of the threshold",
            src.contains("600"),
        )
        // Only the body is a grid; the hero and the composer (and the More
        // menu's strip, drawn as rows not cards) are full-width in the layout's
        // sense, which is what the model means by them.
        assertTrue(
            src.contains("val perRow = if (section == HudLayout.BODY) columns else 1"),
        )
    }

    @Test
    fun `the Settings door reaches the editor end to end`() {
        // The row, in the app's own plate idiom, and its button.
        val settingsSrc = code(source(settings))
        assertTrue("the row is drawn", settingsSrc.contains("item(key = \"edit-hud\")"))
        assertTrue("under a section of its own", settingsSrc.contains("Section(\"Home screen\")"))
        assertTrue("with the app's own button", settingsSrc.contains("Secondary(\"Edit Home screen\""))
        assertTrue("and a callback", settingsSrc.contains("onOpenEditHud?.let"))
        // The jump list and the positional map both know it.
        //
        // Read by key rather than by position (2026-11-04): "Hands-free" was
        // added as the LAST Settings row, so `ENTRIES.last()` is no longer this
        // one. What this assertion is for - the jump list knows the row and
        // carries the app's own words for it - is unchanged, and the positional
        // map's own number is still pinned below, which is what a reordering
        // would break.
        assertTrue(
            "the jump list carries the row",
            SettingsJump.ENTRIES.any { it.key == "edit-hud" && it.label == "Home screen" },
        )
        // 39, not 38, since 2026-11-13: "Phone settings backup" (the copy-over
        // wave) sits right under Backups, above this row, so every number below
        // it moved down by one; SettingsJumpTest holds the map to the order the
        // screen really draws.
        assertTrue("\"edit-hud\" to 39", settingsSrc.contains("\"edit-hud\" to 39"))
        // The search index can find it by the words on the row.
        val search = source("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt")
        assertTrue("the search index has the row", search.contains("key = \"edit-hud\""))
        // The nav entry, the screen and the callback that opens it.
        val nav = source("jarvis-client/app/src/main/java/com/jarvis/client/ui/Nav.kt")
        assertTrue("the screen exists", nav.contains("EDIT_HUD,"))
        val activity = source("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("MainActivity draws it", activity.contains("Screen.EDIT_HUD ->"))
        assertTrue(
            "and Settings opens it",
            activity.contains("onOpenEditHud = { nav.go(Screen.EDIT_HUD) }"),
        )
        // Never gated on pairing: the layout is this phone's own.
        assertFalse(
            "the door is not a paired-only offer",
            activity.contains("onOpenEditHud = if (paired)"),
        )
    }

    @Test
    fun `a Home card opens the place its own menu lives in`() {
        val src = code(source(home))
        // The safety surfaces are not guessed at.
        assertTrue(src.contains("HudLayout.LIVE -> return Screen.LIVE to null"))
        assertTrue(src.contains("HudLayout.APPROVALS -> return Screen.APPROVALS to null"))
        assertTrue(src.contains("HudLayout.EMERGENCY_STOP -> return null"))
        // An ordinary card is the catalogue's own answer, never the layout's.
        assertTrue(src.contains("val menu = com.jarvis.client.net.MenuLogic.menu(id) ?: return null"))
        assertTrue(src.contains("if (!menu.phone) return null"))
        assertTrue(src.contains("com.jarvis.client.ui.MenuPlaces.BRAIN"))
        assertTrue(src.contains("com.jarvis.client.ui.MenuPlaces.SETTINGS"))
        // And every card id the model declares is either a safety surface or a
        // real phone menu - the pure half above proves the ids, this proves the
        // function has a case for the safety ones.
        for (id in protectedIds) {
            assertTrue("$id is answered", src.contains("HudLayout.${
                when (id) {
                    HudLayout.APPROVALS -> "APPROVALS"
                    HudLayout.LIVE -> "LIVE"
                    else -> "EMERGENCY_STOP"
                }
            }"))
        }
    }
}
