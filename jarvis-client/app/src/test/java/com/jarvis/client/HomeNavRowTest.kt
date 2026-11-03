package com.jarvis.client

import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuResult
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.FindAnything
import com.jarvis.client.ui.MenuPlaces
import com.jarvis.client.ui.OpenPlace
import com.jarvis.client.ui.Screen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Home's bottom row, after the owner's request of 2026-11-01: *"move appearance
 * to only in settings for the android app and replace the appearance button with
 * a reminders button instead"*.
 *
 * What that has to mean in this app, and what this file holds:
 *
 *  1. **The row draws Reminders, and Reminders opens the phone's own Reminders
 *     screen.** Until the owner's second ask the same day - *"I want a custom
 *     reminders screen ... I also want another option within the reminders that
 *     includes a daily to-do list"* - the button opened Brain -> Coming up. It
 *     now opens `Screen.REMINDERS` (`ui/screens/RemindersScreen.kt`,
 *     `RemindersTest`), and the Coming up plate is unchanged and still
 *     reachable through "open coming up", Find anything's own row and the
 *     Brain's Work section - it is still the way into the named lists, the
 *     standby schedule and a file from the PC. The button is always drawn
 *     rather than gated on a menu switch, because none of those is a hideable
 *     menu.
 *  2. **No Appearance item is in the row** - not the button, not its icon, not
 *     the callback. The id `entry.appearance` is KEPT (ids are never reused or
 *     renamed, and the phone still has Appearance) but it is no longer a
 *     hideable home-surface toggle: a switch over a button that no longer
 *     exists would be a switch that hides nothing. `backend/jarvis_menus.py`
 *     now says `hide=False` with the reason, and the Settings Appearance row
 *     keeps its own id.
 *  3. **Appearance is still reachable from Settings** - the row it always had
 *     there, `settings.appearance-card`, and "open appearance" by voice or chat
 *     still lands on it.
 *  4. **Showing/hiding menus and Find anything still behave** after the move:
 *     hiding `entry.appearance` is refused rather than stored, the
 *     Show-or-hide list no longer offers it, Find has exactly one Appearance
 *     row (the Settings one), and Coming up stays findable.
 *
 * The Compose row itself needs a real Android host, so the arrangement is read
 * from the screen's own source, in the established style (`MenuVisibilityTest`,
 * `FindAnythingTest`, `HomeLinkWordingTest`). Comments are blanked first: the
 * row's own notes explain in words where Appearance went, and a note saying
 * "Appearance" is not a button called Appearance.
 */
class HomeNavRowTest {

    // ------------------------------------------------- the row's own shape ---

    /**
     * `NavRow`'s body, comments blanked, from its declaration to the next
     * composable - the same slice `HomeLinkWordingTest` takes of `Composer`.
     */
    private fun navRow(): String =
        code(
            repoFile(HOME).readText()
                .substringAfter("private fun NavRow(")
                .substringBefore("\n@Composable"),
        )

    @Test
    fun `the Home row draws Reminders in Appearance's old place`() {
        val row = navRow()
        // The six destinations, in the order the row draws them. The labels are
        // words the owner reads; the callbacks are what each one does.
        assertEquals(
            "Home's row must still be these six, in this order - Reminders where " +
                "Appearance's button was, and Settings and Help still after it",
            listOf(
                "onOpenBrain", "onOpenInbox", "onOpenLive",
                "onOpenReminders", "onOpenSettings", "onOpenFaq",
            ),
            Regex("onClick = actions\\.(\\w+)").findAll(row).map { it.groupValues[1] }.toList(),
        )
        assertEquals("six buttons, one each", 6, Regex("\\bNavItem\\(").findAll(row).count())
        assertTrue(
            "the Reminders button is not drawn with the drawn bell",
            row.contains("icon = { RemindersIcon(chrome.textMid) }"),
        )
        assertTrue("the Reminders button has no label", row.contains("label = \"Reminders\""))
        assertTrue(
            "the Reminders button opens the wrong thing",
            row.contains("onClick = actions.onOpenReminders"),
        )
    }

    @Test
    fun `no Appearance button is left in the row`() {
        val row = navRow()
        assertFalse("the row still draws a button labelled Appearance", row.contains("\"Appearance\""))
        assertFalse("the row still draws the eye glyph", row.contains("AppearanceIcon"))
        assertFalse("the row still opens the Appearance screen", row.contains("onOpenAppearance"))
        // Not one item on the row is a hideable menu, so the row reads no
        // `menus.shows(...)` at all. That check existed only for Appearance's
        // button; leaving it behind would be the dead switch this change removes.
        assertFalse("the row still consults the menu list", row.contains("menus.shows"))
    }

    @Test
    fun `the Home screen no longer carries an Appearance callback`() {
        val home = repoFile(HOME).readText()
        assertFalse(
            "HomeActions still carries the removed Appearance callback",
            home.contains("val onOpenAppearance: () -> Unit"),
        )
        assertTrue(
            "HomeActions must carry the Reminders callback instead",
            home.contains("val onOpenReminders: () -> Unit"),
        )
        assertFalse(
            "HomeScreen still imports the removed eye glyph",
            home.contains("ui.parts.AppearanceIcon"),
        )
        assertTrue("HomeScreen must import the drawn bell", home.contains("ui.parts.RemindersIcon"))
    }

    @Test
    fun `Coming up is still the place Find and open coming up use`() {
        assertEquals(
            "the Brain item that holds Coming up",
            "brain.work.coming-up",
            MenuPlaces.menuFor(Screen.BRAIN.name, "coming-up"),
        )
        val row = FindAnything.row("brain.work.coming-up")
        assertNotNull("Coming up must still be findable", row)
        assertEquals("it opens the Brain", Screen.BRAIN, row!!.screen)
        assertEquals("at the Coming up plate", "coming-up", row.section)
        // Coming up is never hideable: a due reminder must stay reachable now
        // that Home's button no longer goes there.
        assertTrue(
            "Coming up must stay in NEVER_HIDE",
            "brain.work.coming-up" in MenuCatalog.NEVER_HIDE,
        )
        assertTrue(
            "nothing can hide Coming up",
            MenuView(MenuState(hidden = setOf("brain.work.coming-up"))).shows("brain.work.coming-up"),
        )
    }

    @Test
    fun `MainActivity lands the button on the phone's own Reminders screen`() {
        val activity = repoFile(ACTIVITY).readText()
        val body = activity.substringAfter("onOpenReminders = {", "").substringBefore("},")
        assertTrue("Home's Reminders callback is not wired up at all", body.isNotBlank())
        val compact = body.replace(Regex("\\s+"), " ")
        assertTrue(
            "the button does not open the phone's own Reminders screen: $compact",
            compact.contains("nav.go(Screen.REMINDERS)"),
        )
        assertFalse(
            "the button still jumps into the Brain: $compact",
            compact.contains("Screen.BRAIN"),
        )
        assertFalse(
            "the button still names the Brain's plate for the visit: $compact",
            compact.contains("pendingSection"),
        )
        // The destination it opens really is that screen, drawn with the same
        // two guards every other phone screen has (rule 4 and the private lists).
        assertTrue(
            "no destination draws RemindersScreen",
            activity.contains("Screen.REMINDERS -> com.jarvis.client.ui.screens.RemindersScreen("),
        )
        // The Home row's old direct jump to the Appearance screen is gone. The
        // one that stays is the SETTINGS screen's own row callback, which is
        // how Appearance is reached now.
        assertFalse(
            "the Home row still jumps straight to the Appearance screen",
            activity.contains("onOpenAppearance = { nav.go(Screen.APPEARANCE) }"),
        )
        assertEquals(
            "Appearance must be opened from exactly one place: its Settings row",
            1,
            Regex("nav\\.go\\(Screen\\.APPEARANCE\\)").findAll(activity).count(),
        )
        assertTrue(
            "the Settings screen's own Appearance row must still open the screen",
            activity.contains("onOpenAppearance = if (paired)"),
        )
    }

    // --------------------------------------------- 3. Appearance in Settings ---

    @Test
    fun `Appearance is still reachable from Settings`() {
        assertEquals(
            "the Settings item key that holds Appearance",
            "settings.appearance-card",
            MenuPlaces.SETTINGS["appearance"],
        )
        assertNotNull(
            "the Appearance id must be a real phone menu",
            MenuLogic.menu("settings.appearance-card"),
        )
        assertEquals(
            "the OpenPlace answer for \"open appearance\"",
            OpenPlace.Where.Go(Screen.SETTINGS, "appearance-card"),
            OpenPlace.whereFor("appearance-card"),
        )
        // The screen really draws that row, behind that menu's own switch - read
        // from the source because a Compose row cannot be composed here.
        val settings = repoFile(SETTINGS_SCREEN).readText()
        assertTrue("Settings no longer draws an Appearance row", settings.contains("item(key = \"appearance\")"))
        assertTrue(
            "the Appearance row is no longer the switch that hides it",
            settings.contains("menus.shows(\"settings.appearance-card\")"),
        )
        assertTrue(
            "Settings' own search still names the row",
            settings.contains("\"appearance-card\""),
        )
    }

    // --------------------------------- 4. menus and Find, after the move -----

    @Test
    fun `entry appearance is no longer a home-surface toggle, and hiding it is refused`() {
        val entry = MenuLogic.menu("entry.appearance")
        assertNotNull("the id must be kept: ids are never reused or renamed", entry)
        assertTrue("the phone still has Appearance, in Settings", entry!!.phone)
        assertFalse(
            "entry.appearance must no longer be a switch over a button that is gone",
            entry.hide,
        )
        assertTrue(
            "a menu that cannot be hidden needs a written reason",
            entry.why.isNotBlank(),
        )
        assertTrue(
            "it must be in NEVER_HIDE, or a stored file could still hide it",
            "entry.appearance" in MenuCatalog.NEVER_HIDE,
        )
        assertEquals(
            "hiding it must be refused, not stored as a switch that does nothing",
            MenuResult.NEVER,
            MenuLogic.hide(MenuState(), "entry.appearance", MenuLogic.PHONE).second,
        )
        assertTrue(
            "a stored hidden entry.appearance must be cleaned away",
            "entry.appearance" !in
                MenuLogic.sanitize(MenuState(hidden = setOf("entry.appearance")), MenuLogic.PHONE).hidden,
        )
        // ...and the phone's own record still says where it went, so Find
        // anything and MenuVisibilityTest see a decided menu, not a lost one.
        assertTrue(
            "MenuPlaces.INSIDE must still write down where entry.appearance is",
            "entry.appearance" in MenuPlaces.INSIDE,
        )
    }

    @Test
    fun `the Show-or-hide list no longer offers an Appearance button on Home`() {
        // The list draws the rows the owner may hide, and nothing else - read
        // from the plate's own filter.
        val plate = repoFile(MENU_PLATE).readText()
        assertTrue(
            "the plate no longer filters to hideable phone menus, so this check would be vacuous",
            plate.contains("it.phone && it.hide"),
        )
        val offered = MenuCatalog.MENUS.filter { it.phone && it.hide }.map { it.id }.toSet()
        assertFalse(
            "entry.appearance is still offered as a hideable button",
            "entry.appearance" in offered,
        )
        // What the owner can still hide is the Appearance CARD in Settings,
        // which is the surface that is really there.
        assertTrue("the Settings Appearance row must stay hideable", "settings.appearance-card" in offered)
    }

    @Test
    fun `Find anything finds one Appearance, and it is the Settings row`() {
        assertNull(
            "entry.appearance must not be a Find row: its Home place is gone",
            FindAnything.row("entry.appearance"),
        )
        val results = FindAnything.results("appearance", MenuView(), privateHidden = false)
        assertTrue(
            "typing \"appearance\" must still find where it lives",
            results.any { it.id == "settings.appearance-card" },
        )
        assertEquals(
            "there must be exactly one Appearance place to offer, and it is the Settings row",
            1,
            FindAnything.ROWS.count { it.section == "appearance" && it.screen == Screen.SETTINGS },
        )
        val row = results.first { it.id == "settings.appearance-card" }
        assertEquals(Screen.SETTINGS, row.screen)
        assertEquals("appearance", row.section)
        // A menu nobody can open a place for is written down, never silently
        // dropped - the rule FindAnythingTest enforces, kept true here too.
        assertTrue(
            "a phone menu with no place of its own must stay in MenuPlaces.INSIDE",
            "entry.appearance" in MenuPlaces.INSIDE,
        )
    }

    // ------------------------------------------------------------- the glyph --

    @Test
    fun `the bell is drawn in-app to the same rules as the other glyphs`() {
        val icons = repoFile(NAV_ICONS).readText()
        assertTrue("RemindersIcon is not defined", icons.contains("fun RemindersIcon("))
        assertFalse(
            "the unused eye glyph is still defined",
            icons.contains("fun AppearanceIcon("),
        )
        assertTrue("the header no longer lists the row's glyphs", icons.contains("Mind, Inbox, Reminders"))
        // Drawn on the shared 24-unit Canvas with the tint handed in: no icon
        // font, no vector asset, no image file, no new dependency.
        val body = icons.substringAfter("fun RemindersIcon(").substringBefore("\n}\n")
        assertTrue("the bell is not drawn through the shared Glyph helper", body.contains("Glyph(modifier)"))
        assertTrue("the bell does not use the tint it is handed", body.contains("tint"))
        for (bad in listOf("painterResource", "ImageVector", "R.drawable", "Icons.Default", "Icons.Filled")) {
            assertFalse("the bell uses $bad, which the glyph rules forbid", body.contains(bad))
        }
    }

    // ------------------------------------------------------------------ kit --

    /** [src] with whole-line `//` comments and block comments blanked, not dropped. */
    private fun code(src: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in src.lines()) {
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

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val CLIENT = "jarvis-client/app/src/main/java/com/jarvis/client/"
        const val HOME = CLIENT + "ui/screens/HomeScreen.kt"
        const val SETTINGS_SCREEN = CLIENT + "ui/screens/SettingsScreen.kt"
        const val MENU_PLATE = CLIENT + "ui/screens/MenuVisibilityPlate.kt"
        const val NAV_ICONS = CLIENT + "ui/parts/NavIcons.kt"
        const val ACTIVITY = CLIENT + "MainActivity.kt"
    }
}
