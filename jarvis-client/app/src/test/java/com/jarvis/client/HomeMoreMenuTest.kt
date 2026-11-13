package com.jarvis.client

import com.jarvis.client.net.HudLayout
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.screens.HUD_SECTION_WORDS
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's two phone asks of 2026-11-10, and the one bug his screenshot
 * showed on the same screen:
 *
 *  1. The five "TOP STRIP" cards took the whole card tray at the top of Home, so
 *     the conversation never got a screen. They are now SPLIT:
 *     - the two SAFETY cards - Waiting for your yes (the approvals queue) and
 *       the Emergency stop - STAY ON HOME, drawn as one compact row, because the
 *       app's promise that a safety control is never hidden is not the owner's
 *       problem, only the strip's height was;
 *     - the three informational cards - Right now, Attention budget and What
 *       Jarvis is doing - open from the app's More menu.
 *  2. Past conversations are easy to reach: a plain History row in the More
 *     menu, opening the ONE existing History screen.
 *  3. The Home HUD's header no longer runs "30 CARDS" into "Rearrange…": the
 *     hint has its own line.
 *
 * SOURCE PINS, the established shape in this project (`ChatMenuTest`,
 * `HomeNavRowTest`, `HudEditScreenTest`): the app has no Compose test harness in
 * this module, so a JVM test cannot draw the screen. These read the shipped
 * files and hold the arrangement still. What they cannot prove is said where it
 * belongs: the PR states that the menu was not driven on a phone, and the
 * field-test row is the CI-built APK.
 *
 * The RULES the split leans on are proved for real where they live:
 * [HudLayoutTest] holds `homeStrip`/`moreStrip` (the safety pair on Home, the
 * informational cards in More, the hide rules still winning) and
 * `HudEditScreenTest` holds the editor.
 */
class HomeMoreMenuTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val words by lazy { SourceFile.read(screens + "MoreMenuWords.kt") }
    private val editor by lazy { SourceFile.read(screens + "EditHudScreen.kt") }
    private val main by lazy {
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
    }

    /** One function's body, cut at the next top-level declaration. */
    private fun fn(marker: String, text: String = home): String =
        code(
            text.substringAfter(marker)
                .substringBefore("\n/**")
                .substringBefore("\n@Composable")
                .substringBefore("\nprivate fun ")
                .substringBefore("\ninternal fun "),
        )

    /** Just the code, with whole-line `//` and block comments blanked. */
    private fun code(text: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in text.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line.substringBefore(" //"))
        }
        return out.joinToString("\n")
    }

    // --------------------------- 1. the strip: safety stays, the rest goes ---

    @Test
    fun `Home draws the safety pair compactly and the informational cards are not on it`() {
        val hud = fn("private fun HomeHud(")
        // Home draws the strip's SAFETY half as its own row, under the header.
        assertTrue(
            "Home no longer draws the strip's safety pair",
            hud.contains("HudLayout.homeStrip(layout, menus)"),
        )
        assertTrue(
            "the safety pair is not drawn as the compact chip",
            hud.contains("SafetyChip("),
        )
        // ...and it is deliberately OUTSIDE the bounded card tray, so a scrolled
        // or hidden layout can never take a safety control off the screen: it is
        // drawn above the Column that carries the tray's height cap.
        val tray = hud.indexOf("heightIn(max = HUD_TRAY_MAX)")
        val safetyRow = hud.indexOf("if (safety.isNotEmpty())")
        assertTrue("the safety row is gone", safetyRow > 0 && tray > 0)
        assertTrue("the safety row sits inside the bounded card tray", safetyRow < tray)
        // The three full-width sections are the model's Home sections only.
        assertTrue(
            "Home no longer draws the model's Home sections",
            hud.contains("for (section in HudLayout.HOME_SECTIONS)"),
        )
        assertFalse(
            "Home draws every section again, so the strip is back on top of it",
            hud.contains("for (section in HudLayout.SECTIONS)"),
        )
        // The header counts the safety pair too, because it draws it.
        assertTrue(
            "the Home header does not count the safety pair it draws",
            hud.contains("safety.size + HudLayout.HOME_SECTIONS.sumOf"),
        )
    }

    @Test
    fun `the More menu draws the strip's informational cards, and only those`() {
        val more = fn("private fun HomeMoreMain(")
        // The one answer to "which strip cards are the menu's": the model's
        // `moreStrip`, over the SAME saved layout and hide rules Home reads.
        assertTrue(
            "the More menu does not read the split strip",
            more.contains("HudLayout.moreStrip(layout, menus)"),
        )
        assertTrue(
            "a strip row is drawn with words of its own",
            more.contains("card.title") && more.contains("card.about"),
        )
        // Every row is a door now: where it opens is `hudCardPlace`'s answer,
        // the same one Home's card used.
        assertTrue(
            "a strip card opens by a place of its own instead of the catalogue's",
            more.contains("actions.onOpenHudCard(id)"),
        )
        // The emergency stop is NOT a menu row - it stays on Home - so the menu
        // holds no action that stops everything behind two taps.
        assertFalse("the More menu can stop everything", more.contains("onStopEverything"))
        assertFalse("the More menu draws a safety card", more.contains("HudLayout.EMERGENCY_STOP"))
    }

    @Test
    fun `the model's split is the three informational cards and the two safety ones`() {
        // Plain behaviour from the pure model, not a source pin: the five cards
        // the owner named, sorted onto the two surfaces.
        val shown = MenuView()
        val defaults = HudLayout.defaults()
        assertEquals(
            listOf(HudLayout.APPROVALS, HudLayout.EMERGENCY_STOP),
            HudLayout.homeStrip(defaults, shown),
        )
        assertEquals(
            listOf("brain.now.right-now", "brain.now.budget", "brain.now.trace"),
            HudLayout.moreStrip(defaults, shown),
        )
        assertEquals("Waiting for your yes", HudLayout.card(HudLayout.APPROVALS)!!.title)
        assertEquals("Emergency stop", HudLayout.card(HudLayout.EMERGENCY_STOP)!!.title)
        assertEquals("Right now", HudLayout.card("brain.now.right-now")!!.title)
        assertEquals("Attention budget", HudLayout.card("brain.now.budget")!!.title)
        assertEquals("What Jarvis is doing", HudLayout.card("brain.now.trace")!!.title)
    }

    @Test
    fun `the safety pair still keeps the app's promise never to be hidden`() {
        // The reason the split is safe: a safety card is never offered from a
        // menu alone and never hidden by a layout. `HudLayoutTest` proves the
        // model; this names the two promises Home's own drawing relies on.
        val hud = fn("private fun HomeHud(")
        assertTrue(
            "the safety row is not drawn from the model's protected-card rule",
            hud.contains("HudLayout.homeStrip("),
        )
        assertTrue(
            "a compact safety chip does not run the same tap the full card ran",
            home.contains("if (isStop) onStop() else onOpen(id)"),
        )
        assertTrue(
            "the compact chip no longer names the card to TalkBack",
            home.contains("contentDescription = \"\${card.title}. \${card.about}\""),
        )
        // The two safety cards themselves stay protected and unremovable.
        for (id in listOf(HudLayout.APPROVALS, HudLayout.EMERGENCY_STOP)) {
            assertTrue("$id is no longer protected", HudLayout.isProtected(id))
        }
    }

    @Test
    fun `the editor says where each half of the strip is drawn`() {
        // The editor still edits all four sections; the one split across two
        // surfaces says so, so moving a card there is not a card vanishing.
        assertTrue(
            "the editor no longer draws every section",
            code(editor).contains("for (section in HudLayout.SECTIONS)"),
        )
        assertTrue(
            "the editor does not say the safety cards stay on Home",
            editor.contains("The safety cards here stay on Home, drawn small."),
        )
        assertTrue(
            "the editor does not say where the other strip cards go",
            editor.contains("The other cards here open from the app's More menu."),
        )
        // The menu and the editor call the section the same thing, so the owner
        // recognises the strip he arranged in Settings.
        assertEquals("Top strip", HUD_SECTION_WORDS.getValue(HudLayout.TOP_STRIP))
        assertTrue(
            "the More menu does not head the strip with the editor's words",
            home.contains("Kicker(HUD_SECTION_WORDS.getValue(HudLayout.TOP_STRIP)"),
        )
    }

    // ------------------------------------------------- 2. the History row -----

    @Test
    fun `History is one More row, opening the one History screen`() {
        val more = fn("private fun HomeMoreMain(")
        assertTrue("the More menu has no History row", more.contains("MoreMenuWords.HISTORY"))
        assertTrue(
            "the History row does not open History through the one action",
            more.contains("actions.onEarlierChats()"),
        )
        // Not a second history surface: the row opens by the SAME action the
        // status line's one-tap "History" link uses, which MainActivity wires to
        // the one History screen. The title link is small (63.7x48dp, the
        // 2026-11-10 audit measured it), so this row is the bigger, easier door
        // the owner asked for - and the screen's own "confirm it is you" gate is
        // untouched, because that is a security decision, not discoverability.
        assertTrue(
            "the status line's own History door is gone",
            home.contains("onClick = actions.onEarlierChats"),
        )
        assertTrue(
            "MainActivity no longer opens History from that action",
            main.contains("onEarlierChats = { nav.go(Screen.HISTORY) }"),
        )
        assertEquals(
            "Home grew a second way into History of its own",
            2,
            home.split("actions.onEarlierChats").size - 1,
        )
        // The words say what the row is, in the app's plain style.
        assertTrue("the row has no label", words.contains("const val HISTORY = \"History\""))
        assertTrue("the row has no detail line", words.contains("const val HISTORY_DETAIL"))
    }

    @Test
    fun `the removed Earlier chats row and its words stay gone`() {
        // The 2026-10-30 decision removed that row, not the screen; the new
        // History row must not bring the old words or a second list back.
        assertFalse("the removed Earlier chats row is back", home.contains("ChatHistory.EARLIER_CHATS"))
        assertFalse(
            "the More menu draws a conversation list of its own",
            fn("private fun HomeMoreMain(").contains("ConversationList("),
        )
    }

    // ------------------------------------------- 3. the header no longer clips --

    @Test
    fun `the Home header gives the rearrange hint its own line`() {
        // The owner's screenshot: "YOUR HOME SCREEN · 30 CARDSRearrange it in
        // Settings, Home s…" - the hint shared a row with the kicker and was
        // ellipsised into it on a narrow phone. It has its own line now.
        val hud = fn("private fun HomeHud(")
        val kickerAt = hud.indexOf("Kicker(if (total == 1)")
        val hintAt = hud.indexOf("Rearrange it in Settings, Home screen")
        assertTrue("the header's rearrange hint is gone", hintAt > 0)
        assertTrue("the hint is not below the card count", kickerAt in 0 until hintAt)
        assertFalse(
            "the kicker and the hint still share one row",
            hud.substring(kickerAt, hintAt).contains("Row("),
        )
        // The kicker still says how many cards Home draws, in the app's words.
        assertTrue(hud.contains("\"Your Home screen · \$total cards\""))
        assertTrue(hud.contains("\"Your Home screen · 1 card\""))
    }

    @Test
    fun `the words still say what the menu is`() {
        // The subtitle names both halves, so a menu that opens with Home cards is
        // not a surprise, and it says the safety cards stayed behind.
        assertTrue(
            "the More subtitle does not mention the Home cards",
            words.contains("The Home cards that are not safety controls"),
        )
        assertTrue(words.contains("what this PC offers is listed."))
    }
}
