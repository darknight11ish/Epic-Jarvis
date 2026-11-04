package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.OpenPlace
import com.jarvis.client.ui.Screen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F6, 2026-11-03: the SAME closed table in [OpenPlace] now names whole places
 * and menus, not only settings sections.
 *
 * The PC's deterministic "open <a place>" path answers with an id and the
 * phone resolves it here - one table, no second navigation mechanism, no new
 * `Screen` entry. Three things this file holds:
 *
 *  - a place the phone HAS opens its own screen (or the plate/row on it), so
 *    "open live" no longer lands at the top of Settings;
 *  - a place the phone has no screen for says so in one honest sentence - the
 *    Habits, Mood and Plugins screens do not exist in this build, and opening
 *    Reminders (which draws none of them) would be the lie;
 *  - nothing that already worked changed: every settings-registry id keeps
 *    its 2026-09-27 decision, and a newer id still falls back harmlessly.
 */
class OpenPlaceAreasTest {

    // ------------------------------------------------------------- the areas ---

    @Test
    fun `a place the phone has opens its own screen`() {
        for ((id, screen) in listOf(
            "home" to Screen.HOME,
            "chat" to Screen.HOME,
            "brain" to Screen.BRAIN,
            "inbox" to Screen.INBOX,
            "settings" to Screen.SETTINGS,
            "reminders" to Screen.REMINDERS,
            "approvals" to Screen.APPROVALS,
            "history" to Screen.HISTORY,
            "conversations" to Screen.HISTORY,
            "chats" to Screen.HISTORY,
            "live" to Screen.LIVE,
            "pins" to Screen.PINS,
            "features" to Screen.FEATURES,
            "find" to Screen.FIND,
            "checks" to Screen.CHECKS,
            "appearance" to Screen.APPEARANCE,
            "edit-hud" to Screen.EDIT_HUD,
        )) {
            assertEquals(id, OpenPlace.Where.Go(screen, null), OpenPlace.whereFor(id))
        }
    }

    @Test
    fun `a brain plate named as a place opens that plate`() {
        for ((id, key) in listOf(
            "memory" to "memory",
            "memories" to "memory",
            "models" to "models",
            "goals" to "goals",
            "today" to "today",
            "briefing" to "briefing",
            "projects" to "projects",
            "focus" to "focus",
            "pictures" to "pictures",
            "wiki" to "wiki",
            "quiz" to "quiz",
            "decks" to "decks",
            "retirement" to "retirement",
            "skills" to "skills",
            "people-and-things" to "people-and-things",
            "jobs" to "jobs",
            "tasks" to "tasks",
            "progress" to "progress",
        )) {
            assertEquals(id, OpenPlace.Where.Go(Screen.BRAIN, key), OpenPlace.whereFor(id))
        }
    }

    @Test
    fun `a shared menu id lands on the row or plate that draws it`() {
        // The ids backend/jarvis_menus.py exports for BOTH apps. Before F6 an
        // id like this was not a registry section, so the phone opened
        // Settings at a row that does not exist.
        assertEquals(
            OpenPlace.Where.Go(Screen.SETTINGS, "voice"),
            OpenPlace.whereFor("settings.voice"),
        )
        assertEquals(
            OpenPlace.Where.Go(Screen.BRAIN, "spending"),
            OpenPlace.whereFor("settings.spending"),
        )
        assertEquals(
            OpenPlace.Where.Go(Screen.BRAIN, "memory"),
            OpenPlace.whereFor("brain.memory.waiting"),
        )
        assertEquals(
            OpenPlace.Where.Go(Screen.BRAIN, "hardware"),
            OpenPlace.whereFor("settings.hardware"),
        )
    }

    @Test
    fun `a place with no screen in this build is said in one sentence`() {
        // features.json: "Neither app has a screen for it yet - the
        // Habits/Mood section on the Reminders screen is the next lane";
        // plugins are chat-only on the phone. None may open another screen.
        for (id in listOf("habits", "mood")) {
            val where = OpenPlace.whereFor(id)
            assertTrue("$id must not open a screen: $where", where is OpenPlace.Where.OnPc)
            val notice = (where as OpenPlace.Where.OnPc).notice
            assertTrue("$id: notice does not name it: $notice", notice.contains("no $id screen"))
            assertTrue("$id: notice does not say where it lives: $notice", notice.contains("PC"))
        }
        val plugins = OpenPlace.whereFor("plugins") as? OpenPlace.Where.OnPc
        assertTrue("plugins must be refused in words", plugins != null)
        assertTrue(plugins!!.notice.contains("asking Jarvis in chat"))
        assertTrue(plugins.notice.contains("no Plugins screen"))
    }

    // --------------------------------------------------- what must not change ---

    @Test
    fun `the settings registry's decisions are unchanged`() {
        // The AREAS step must never shadow a decision this table already made:
        // "voice" still means the Settings row (its own test in
        // OpenPlaceTest), and the desktop-only ids still answer in words.
        assertEquals(OpenPlace.Where.Go(Screen.SETTINGS, "voice"), OpenPlace.whereFor("voice"))
        assertEquals(OpenPlace.Where.Go(Screen.FAQ, null), OpenPlace.whereFor("faq"))
        assertEquals(OpenPlace.Where.Go(Screen.FAQ, "about"), OpenPlace.whereFor("about"))
        assertEquals(OpenPlace.Where.Go(Screen.CHECKS, "connection"), OpenPlace.whereFor("connection"))
        assertEquals(OpenPlace.Where.OnPc(OpenPlace.ON_PC), OpenPlace.whereFor("shortcuts"))
        // A registry section whose phone home is a Brain plate, unchanged.
        assertEquals(OpenPlace.Where.Go(Screen.BRAIN, "hardware"), OpenPlace.whereFor("hardware"))
        // The full calendar screen is NOT opened by the registry's "calendar"
        // section: that id is the switch's row, as decided on 2026-10-29.
        assertEquals(OpenPlace.Where.Go(Screen.SETTINGS, "calendar"), OpenPlace.whereFor("calendar"))
    }

    @Test
    fun `an id newer than this app still just opens Settings`() {
        assertEquals(
            OpenPlace.Where.Go(Screen.SETTINGS, "something-new"),
            OpenPlace.whereFor("something-new"),
        )
        // Whitespace around a real id is tidied rather than making it unknown.
        assertEquals(OpenPlace.Where.Go(Screen.LIVE, null), OpenPlace.whereFor("  live  "))
    }

    // ------------------------------------------------- the route field ---

    @Test
    fun `the route header's place field is read in every spelling it could use`() {
        // One closed table serves one route field; the field's NAME is not
        // pinned on this side yet, so the four reasonable spellings are read
        // rather than dropping the request silently.
        for (field in listOf("open_settings", "open_place", "open_area", "open_screen")) {
            val header = """{"quick":true,"$field":"live"}"""
            assertEquals(field, "live", Schedule.openSettingsFromRoute(header))
        }
        assertNull(Schedule.openSettingsFromRoute("""{"quick":true}"""))
        assertNull(Schedule.openSettingsFromRoute(null))
        assertNull(Schedule.openSettingsFromRoute("not json"))
        verifyEventKindIsNotTheCarrier()
    }

    /**
     * The mechanism is the ANSWER's route field (RESEARCH F3/F5), not a new
     * event kind the phone would have to listen for: an event kind is a
     * two-client change (docs/ARCHITECTURE.md §6), and this slice is the phone
     * half only. Pinned here so a later change cannot quietly add a listener
     * believing this path is not enough.
     */
    private fun verifyEventKindIsNotTheCarrier() {
        val runtime = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt",
        )
        assertFalse(
            "a ui.navigate event listener was added to JarvisRuntime; the route-field path is the contract",
            runtime.contains("\"ui.navigate\"") || runtime.contains("UiNav."),
        )
        val main = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt",
        )
        assertTrue(
            "MainActivity no longer routes answers through OpenPlace.whereFor",
            main.contains("OpenPlace.whereFor(target)"),
        )
    }
}
