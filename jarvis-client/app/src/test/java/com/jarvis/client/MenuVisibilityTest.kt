package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuResult
import com.jarvis.client.net.MenuRoute
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import com.jarvis.client.net.MenuWords
import com.jarvis.client.ui.MenuPlaces
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Show or hide menus" (docs/MENU-VISIBILITY-DESIGN.md, docs/JARVIS-API.md section 109) - the
 * phone's copy of the list and its rules, held to `src/test/resources/contract/menu-cases.json`
 * that tools/gen_menu_cases.py makes from backend/jarvis_menus.py (the desktop's
 * tests/menu-visibility.mjs reads the same file), and to the real screens' text.
 *
 * Pure JVM: [MenuLogic] has no Android in it. The Android holder (data/MenuPrefs.kt) and the
 * Compose screens are read by eye; CI's Gradle build is the only compiler for them.
 */
class MenuVisibilityTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/menu-cases.json")) {
            "contract/menu-cases.json is missing - run python3 tools/gen_menu_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun JsonElement.str(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
    private fun JsonObject.s(k: String): String = this[k]!!.jsonPrimitive.content
    private fun JsonObject.opt(k: String): String? = this[k]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content
    private fun JsonObject.strings(k: String): List<String> = this[k]!!.jsonArray.map { it.jsonPrimitive.content }
    private fun JsonObject.state(): MenuState = MenuState(strings("hidden").toSet(), strings("collapsed").toSet())

    // ---------------------------------------------------------------- the list itself

    @Test
    fun `the phone's list is the PC's list, menu for menu`() {
        val menus = doc["menus"]!!.jsonArray.map { it.jsonObject }
        assertEquals(menus.map { it.s("id") }, MenuCatalog.MENUS.map { it.id })
        for ((json, m) in menus.zip(MenuCatalog.MENUS)) {
            val id = m.id
            assertEquals(id, json.s("title"), m.title)
            assertEquals(id, json.s("about"), m.about)
            val apps = json.strings("apps")
            assertEquals(id, "desktop" in apps, m.desktop)
            assertEquals(id, "phone" in apps, m.phone)
            assertEquals(id, json.s("area"), m.area)
            assertEquals(id, json.s("view"), m.view)
            assertEquals(id, json.s("kind"), m.kind)
            assertEquals(id, json.opt("group"), m.group)
            assertEquals(id, json.opt("parent"), m.parent)
            assertEquals(id, json["hide"]!!.jsonPrimitive.boolean, m.hide)
            assertEquals(id, json["collapse"]!!.jsonPrimitive.boolean, m.collapse)
            assertEquals(id, json.s("why"), m.why)
        }
    }

    @Test
    fun `the groups and the never-hideable list are the PC's`() {
        val groups = doc["groups"]!!.jsonArray.map { it.jsonObject }
        assertEquals(groups.map { it.s("id") }, MenuCatalog.GROUPS.map { it.id })
        for ((json, g) in groups.zip(MenuCatalog.GROUPS)) {
            assertEquals(json.s("title"), g.title)
            assertEquals(json.s("about"), g.about)
            val listed = json["listed"]!!.jsonObject["phone"]!!.jsonPrimitive.boolean
            assertEquals("${g.id} listed on the phone", listed, MenuLogic.members(g.id).isNotEmpty())
            assertEquals(g.id, json["members"]!!.jsonObject.strings("phone"), MenuLogic.members(g.id))
            assertEquals(g.id, json["members"]!!.jsonObject.strings("desktop"), MenuLogic.members(g.id, MenuLogic.DESKTOP))
        }
        assertEquals(doc["never_hide"]!!.jsonArray.map { it.jsonObject.s("id") }, MenuCatalog.NEVER_HIDE)
        assertEquals(doc["version"]!!.jsonPrimitive.int, MenuCatalog.VERSION)
        assertEquals(doc.s("group_prefix"), MenuCatalog.GROUP_PREFIX)
        assertEquals(doc.strings("actions"), MenuLogic.ACTIONS)
    }

    @Test
    fun `every word both apps show is the PC's word`() {
        val words = doc["words"]!!.jsonObject
        assertTrue(words.size > 10)
        for ((key, value) in words) {
            val field = MenuWords::class.java.getField(key.uppercase())
            assertEquals(key, value.jsonPrimitive.content, field.get(null))
        }
    }

    // ---------------------------------------------------------------- the never-hideable list

    @Test
    fun `no never-hideable id is hideable, anywhere`() {
        val never = MenuCatalog.NEVER_HIDE.toSet()
        assertEquals("NEVER_HIDE is exactly the menus that cannot be hidden",
            MenuCatalog.MENUS.filter { !it.hide }.map { it.id }.toSet(), never)
        // The design's fixed list (section 5), by id.
        for (id in listOf(
            "settings.security", "settings.asks-first", "settings.connection", "settings.menu-visibility",
            "brain.tab.trust", "brain.tab.watch", "entry.help", "entry.settings", "safety.approvals",
            "safety.stale-link", "safety.crisis-help", "safety.stop-everything", "safety.live-stop",
            "entry.checks", "brain.now.budget", "brain.trust.rush-latch", "settings.devices",
            "brain.work.undo", "brain.work.coming-up", "brain.memory.waiting",
        )) {
            assertTrue("$id must be in NEVER_HIDE", id in never)
        }
        for (m in MenuCatalog.MENUS.filter { !it.hide }) assertTrue("${m.id} has a reason", m.why.isNotBlank())
        // No group has one as a member; nothing that cannot be hidden is on a hideable list.
        for (g in MenuCatalog.GROUPS) {
            assertTrue(g.id, MenuLogic.members(g.id, null).none { it in never })
        }
        for (id in never) {
            val (state, result) = MenuLogic.hide(MenuState(), id, MenuLogic.PHONE)
            assertTrue("$id refused", result != MenuResult.OK)
            assertTrue("$id not stored", id !in state.hidden)
            // Even if a stored file lists it, it is never hidden, and cleaning drops it.
            val bad = MenuState(hidden = setOf(id))
            assertFalse("$id visible", MenuLogic.isHidden(bad, id))
            assertTrue("$id dropped", id !in MenuLogic.sanitize(bad).hidden)
        }
    }

    @Test
    fun `thousands of random changes never hide a never-hideable menu`() {
        val ids = MenuCatalog.MENUS.map { it.id } + MenuCatalog.GROUPS.map { it.id } + listOf("nope", "group.nope")
        var seed = 20260930L
        fun next(n: Int): Int {
            seed = (seed * 6364136223846793005L + 1442695040888963407L)
            return ((seed ushr 33) % n).toInt()
        }
        var state = MenuState()
        repeat(6000) {
            val app = listOf(MenuLogic.PHONE, MenuLogic.DESKTOP, null)[next(3)]
            state = MenuLogic.apply(state, MenuLogic.ACTIONS[next(5)], ids[next(ids.size)], app).first
            if (next(10) == 0) state = MenuLogic.sanitize(state, app)
            for (id in MenuCatalog.NEVER_HIDE) assertFalse(id, MenuLogic.isHidden(state, id))
            assertTrue(state.hidden.none { it in MenuCatalog.NEVER_HIDE })
        }
    }

    // ---------------------------------------------------------------- the worked cases

    @Test
    fun `every worked case of the state machine gives the PC's answer`() {
        val cases = doc["state_cases"]!!.jsonArray.map { it.jsonObject }
        assertTrue(cases.size >= 15)
        for (c in cases) {
            val name = c.s("name")
            val app = c.s("app")
            var state = c["start"]!!.jsonObject.state()
            for (step in c["steps"]!!.jsonArray.map { it.jsonObject }) {
                val (next, result) = MenuLogic.apply(state, step.s("op"), step.s("id"), app)
                assertEquals("$name: ${step.s("op")} ${step.s("id")}", step.s("result"), result.word)
                state = next
            }
            assertEquals("$name: end", c["end"]!!.jsonObject.state(), state)
            val visit = c.s("visit").let { if (it.isEmpty()) emptySet() else MenuLogic.visitSet(it) }
            for ((id, expect) in c["hidden"]!!.jsonObject) {
                assertEquals("$name: hidden $id", expect.jsonPrimitive.boolean, MenuLogic.isHidden(state, id, visit))
            }
            for ((id, expect) in c["collapsed"]!!.jsonObject) {
                assertEquals("$name: folded $id", expect.jsonPrimitive.boolean, MenuLogic.isCollapsed(state, id, visit))
            }
            assertEquals("$name: count", c["hidden_count"]!!.jsonPrimitive.int, MenuLogic.hiddenCount(state, app))
        }
    }

    @Test
    fun `stored data is cleaned the same way the PC cleans it`() {
        for (c in doc["sanitize_cases"]!!.jsonArray.map { it.jsonObject }) {
            val got = MenuLogic.sanitize(c["start"]!!.jsonObject.state(), c.s("app"))
            assertEquals(c["end"]!!.jsonObject.state(), got)
            assertEquals("idempotent", got, MenuLogic.sanitize(got, c.s("app")))
        }
    }

    @Test
    fun `a header names a change only when it is well formed`() {
        val cases = doc["route_cases"]!!.jsonArray.map { it.jsonObject }
        assertTrue(cases.size >= 10)
        for (c in cases) {
            val parsed = MenuRoute.fromRoute(c.s("header"))
            val want = c["parsed"]
            if (want == null || want is JsonNull) {
                assertNull(c.s("header"), parsed)
            } else {
                val o = want.jsonObject
                assertEquals(c.s("header"), MenuRoute(o.s("action"), o.s("target")), parsed)
            }
        }
        assertNull(MenuRoute.fromRoute(null))
    }

    @Test
    fun `a route change is applied by the same rules as a tap`() {
        // "hide the finance menu" -> group.finance, both members hidden, counted once.
        var state = MenuLogic.apply(MenuState(), "hide", "group.finance", MenuLogic.PHONE).first
        val view = MenuView(state)
        assertFalse(view.shows("brain.work.retirement"))
        assertFalse(view.shows("settings.spending"))
        assertEquals(1, view.hiddenCount)
        // ...the desktop-only id in the same header is ignored on the phone.
        val (same, result) = MenuLogic.apply(state, "hide", "brain.tab.galaxy", MenuLogic.PHONE)
        assertEquals(MenuResult.UNKNOWN, result)
        assertEquals(state, same)
        // "show everything".
        state = MenuLogic.apply(state, "reset", "all", MenuLogic.PHONE).first
        assertEquals(MenuState(), state)
    }

    @Test
    fun `a link opens a hidden menu for the visit and nothing is stored`() {
        val state = MenuState(hidden = setOf("group.study"), collapsed = setOf("brain.work.quiz"))
        val visit = MenuLogic.visitSet("brain.work.quiz")
        val view = MenuView(state, visit)
        assertTrue(view.shows("brain.work.quiz"))
        assertFalse(view.folded("brain.work.quiz"))
        assertTrue(view.onVisit("brain.work.quiz"))
        assertFalse("its group stays hidden", view.shows("brain.work.decks"))
        assertFalse(MenuView(state).shows("brain.work.quiz"))
        assertTrue(MenuView(state).folded("brain.work.quiz"))
        // "Keep it visible": the change becomes real, the rest of the group stays hidden.
        val kept = MenuLogic.show(state, "brain.work.quiz", MenuLogic.PHONE).first
        assertTrue(MenuView(kept).shows("brain.work.quiz"))
        assertFalse(MenuView(kept).shows("brain.work.decks"))
    }

    @Test
    fun `defaults are everything visible and unfolded`() {
        val d = doc["defaults"]!!.jsonObject
        assertEquals(emptyList<String>(), d.strings("hidden"))
        assertEquals(emptyList<String>(), d.strings("collapsed"))
        val view = MenuView()
        for (m in MenuCatalog.MENUS) {
            assertTrue(m.id, view.shows(m.id))
            assertFalse(m.id, view.folded(m.id))
        }
        assertEquals(0, view.hiddenCount)
        assertTrue(doc["migration"]!!.jsonArray.map { it.jsonObject.s("rule") }.containsAll(
            listOf("first_run", "stale_ids", "never_ids", "unknown_version", "storage_failure"),
        ))
        assertEquals("jarvis_menus", d["storage"]!!.jsonObject["phone"]!!.jsonObject.s("prefs_file"))
    }

    @Test
    fun `finance is listed, home is not`() {
        assertTrue(MenuLogic.members("group.finance").containsAll(listOf("settings.spending", "brain.work.retirement")))
        assertTrue(MenuLogic.members("group.home").isEmpty())
        // Hiding an empty group is a no-op with nothing to show.
        assertEquals(MenuResult.UNKNOWN, MenuLogic.hide(MenuState(), "group.home").second)
    }

    // ---------------------------------------------------------------- the screens

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun uiSources(): Map<String, String> =
        listOf(
            "screens/BrainScreen.kt", "screens/SettingsScreen.kt", "screens/HomeScreen.kt",
            "screens/HistoryTags.kt", "screens/SecondCardPlate.kt", "screens/QuizPlate.kt",
        ).associateWith { repoFile(screens + it).readText() }

    @Test
    fun `every menu the phone can hide has a place and a check in a real screen`() {
        val phoneHideable = MenuCatalog.MENUS.filter { it.phone && it.hide }.map { it.id }.toSet()
        val placed = MenuPlaces.SETTINGS.values + MenuPlaces.BRAIN.values + MenuPlaces.INSIDE.keys
        assertTrue("no place in MenuPlaces for: ${phoneHideable - placed.toSet()}", placed.toSet().containsAll(phoneHideable))
        // Every place names a menu this phone has.
        for (id in placed) {
            val m = MenuLogic.menu(id)
            assertNotNull("$id is not in the menu list", m)
            assertTrue("$id is not a phone menu", m!!.phone)
        }
        // Every hideable menu is really drawn behind a check: a `menus.shows("<id>")` in a screen.
        val text = uiSources().values.joinToString("\n")
        val checked = Regex("menus\\.shows\\(\"([\\w.-]+)\"\\)").findAll(text).map { it.groupValues[1] }.toSet()
        assertTrue("no menus.shows(...) check for: ${phoneHideable - checked}", checked.containsAll(phoneHideable))
        for (id in checked) assertNotNull("menus.shows(\"$id\") names no menu", MenuLogic.menu(id))
        // ...and every menu that can be folded, on a card or plate item, is wrapped in a MenuFrame.
        val framed = Regex("MenuFrame\\(menus, \"([\\w.-]+)\"\\)").findAll(text).map { it.groupValues[1] }.toSet()
        for (id in framed) {
            assertNotNull(id, MenuLogic.menu(id))
            assertTrue("$id is framed but cannot be folded or hidden", MenuLogic.menu(id)!!.let { it.collapse || it.hide })
        }
        for (m in MenuCatalog.MENUS.filter { it.phone && it.hide && it.collapse && it.id !in MenuPlaces.INSIDE }) {
            assertTrue("${m.id} can be folded but no screen wraps it in a MenuFrame", m.id in framed)
        }
    }

    @Test
    fun `every item key in MenuPlaces is a real item on its screen`() {
        val settings = repoFile(screens + "screens/SettingsScreen.kt").readText()
        val brain = repoFile(screens + "screens/BrainScreen.kt").readText()
        for (key in MenuPlaces.SETTINGS.keys) {
            assertTrue("SettingsScreen has no item(key = \"$key\")", settings.contains("item(key = \"$key\")"))
        }
        for (key in MenuPlaces.BRAIN.keys) {
            assertTrue("BrainScreen has no item(key = \"$key\")", brain.contains("item(key = \"$key\")"))
        }
        // The other way: no item on either screen is a menu without a place (a plate added to
        // Brain or Settings must be decided - listed here, or one of the fixed ones below).
        val fixed = setOf("rush", "freshness", "notice", "group-now", "group-memory", "group-model-pc",
            "menus-hidden", "tail", "memory-hidden", "wiki-hidden", "memory-as-of-hidden",
            "deep-questions-hidden")
        val brainKeys = Regex("item\\(key = \"([\\w-]+)\"\\)").findAll(brain).map { it.groupValues[1] }.toSet()
        val undecided = brainKeys - MenuPlaces.BRAIN.keys - fixed
        assertTrue("Brain items with no decision in MenuPlaces: $undecided", undecided.isEmpty())
        val settingsKeys = Regex("item\\(key = \"([\\w-]+)\"\\)").findAll(settings).map { it.groupValues[1] }.toSet()
        // Every Settings row is a menu with a place, or one of these: the rows
        // that are deliberately NOT menus. "limits" joined them on 2026-10-08
        // (LimitsPlate.kt): a menu id is generated into the desktop's own
        // catalogue by tools/gen_menu_cases.py, and that row is visible always -
        // like Security and What asks first, which are never hideable either.
        // The assertion is unchanged: any OTHER undecided key still fails it.
        val undecidedS = settingsKeys - MenuPlaces.SETTINGS.keys -
            setOf("menus-hidden", "tail", "jump-list", "limits")
        assertTrue("Settings items with no decision in MenuPlaces: $undecidedS", undecidedS.isEmpty())
    }

    @Test
    fun `the words a screen quotes are the PC's`() {
        val plate = repoFile(screens + "screens/MenuVisibilityPlate.kt").readText()
        for (w in listOf("TITLE", "DEVICE_NOTE", "HELP", "NEVER_NOTE", "SHOW_EVERYTHING", "VISIT_BANNER",
            "VISIT_KEEP", "VISIT_AGAIN", "HIDDEN_LINE_ONE", "HIDDEN_LINE_MANY", "NONE_HIDDEN")) {
            assertTrue("MenuVisibilityPlate does not use MenuWords.$w", plate.contains("MenuWords.$w"))
        }
        assertEquals("Show or hide menus", MenuWords.TITLE)
        assertEquals("This hides menus on this device only.", MenuWords.DEVICE_NOTE)
        assertEquals("Keep it visible", MenuWords.VISIT_KEEP)
        assertEquals("Hide again", MenuWords.VISIT_AGAIN)
        // The phone has no tray, so the tray sentence is the desktop's alone.
        assertFalse(plate.contains("TRAY_NOTE"))
    }

    @Test
    fun `hiding never asks anything or reaches the network`() {
        // Hiding only tidies: the store and the rules must not import the gate, the api or a card.
        val prefs = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/data/MenuPrefs.kt").readText()
        val logic = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/MenuState.kt").readText()
        for (src in listOf(prefs, logic)) {
            for (bad in listOf("JarvisApi", "okhttp", "Approval", "BiometricGate", "Security")) {
                assertFalse("uses $bad", Regex("^import .*$bad", RegexOption.MULTILINE).containsMatchIn(src))
            }
        }
    }
}
