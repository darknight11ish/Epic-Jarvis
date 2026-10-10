package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Limits
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Limits and how often Jarvis does things" on the phone ([Limits],
 * ui/screens/LimitsPlate.kt, the PC's own backend/jarvis_limits.py table,
 * 2026-10-08).
 *
 * The fixture below is the shape the PC answers `GET /api/limits` with,
 * including rows the phone must NOT offer: a `pc_only` row (jobs_per_tick,
 * `Limit(..., pc_only=True, app="desktop")` in the real table) and a `float`
 * row, which has no control this app can draw.
 *
 * The source checks at the end are the app's usual kind (SettingsJumpTest,
 * MenuVisibilityTest, TouchTargetAndInsetsTest): a JVM test cannot press a
 * button, so the FACT that the button posts to the limits route and nowhere
 * else is held to the text that does it.
 */
class LimitsTest {

    // ------------------------------------------------------------- fixture --

    private val body: JsonObject = JarvisJson.parseToJsonElement(
        """
        {"ok":true,"available":true,"limits":[
          {"key":"undo_window","title":"How long you can undo","kind":"int","value":24,
           "words":"keep undo for a day","choices":[1,24,168],"low":1,"high":720,
           "unit":"hours","note":"A longer window keeps older copies of your files on this PC.",
           "loosen_up":true,"pc_only":false},
          {"key":"jobs_per_tick","title":"Jobs at once","kind":"int","value":4,
           "words":"4 jobs","choices":[],"low":1,"high":16,"unit":"jobs",
           "note":"How many jobs one tick may start.","loosen_up":false,"pc_only":true},
          {"key":"study_run_cards","title":"Cards in a study run","kind":"int","value":20,
           "words":"20 cards","choices":[],"low":1,"high":1000,"unit":"cards",
           "note":"What one run shows before you can ask for ten more.",
           "loosen_up":false,"pc_only":false},
          {"key":"memory_people","title":"Look for people and things in what you save",
           "kind":"bool","value":false,"words":"no: Look for people and things in what you save",
           "choices":[],"low":0,"high":0,"unit":"",
           "note":"A model reads what you save to find the people and things in it.",
           "loosen_up":true,"pc_only":false},
          {"key":"watch_star_jump","title":"What counts as news: the jump","kind":"float",
           "value":0.5,"words":"0.5 of the count","choices":[],"low":0.05,"high":0.9,
           "unit":"of the count","note":"A repository counts as news when its stars move by this fraction.",
           "loosen_up":false,"pc_only":false},
          "not an object"
        ]}
        """.trimIndent(),
    ) as JsonObject

    private fun row(key: String): Limits.Row =
        requireNotNull(Limits.offered(body).firstOrNull { it.key == key }) { "$key is not offered" }

    // ------------------------------------------------------ what is offered --

    @Test
    fun `the pc_only row is read, and never offered on the phone`() {
        // Read: the row really is in the PC's answer, so the filter below is a
        // decision and not an accident of parsing.
        assertTrue("the fixture must contain the PC-only row", Limits.read(body).any { it.key == "jobs_per_tick" })
        // Offered: the phone may not change it, so it is not drawn and has no
        // control - this is the check that fails if the filter is removed.
        assertFalse("a pc_only limit must never be offered on a phone",
            Limits.offered(body).any { it.key == "jobs_per_tick" })
        assertFalse("no offered row may be pc_only", Limits.offered(body).any { it.pcOnly })
    }

    @Test
    fun `the phone is offered exactly the rows the table gives it`() {
        // undo_window and study_run_cards are app "both"; memory_people is app
        // "phone". jobs_per_tick is pc_only, and the float row has no control
        // here, so neither can appear.
        assertEquals(listOf("undo_window", "study_run_cards", "memory_people"),
            Limits.offered(body).map { it.key })
    }

    @Test
    fun `a row's own value and range are read as the PC sent them`() {
        val undo = row("undo_window")
        assertEquals("int", undo.kind)
        assertEquals(24L, undo.number)
        assertEquals("keep undo for a day", undo.words)
        assertEquals(listOf(1L, 24L, 168L), undo.choices)
        assertTrue("a longer undo window is the loosening", undo.loosenUp)

        val cards = row("study_run_cards")
        assertEquals(20L, cards.number)
        assertEquals("a step down is one less", 19L, cards.down)
        assertEquals("a step up is one more", 21L, cards.up)
        assertFalse("more cards at once is not a loosening", cards.loosenUp)
        assertEquals("Between 1 cards and 1000 cards.", Limits.rangeLine(cards))

        val people = row("memory_people")
        assertEquals("bool", people.kind)
        assertFalse("off, as the PC says", people.on)
        assertNull("a bool row has no step", people.up)
    }

    @Test
    fun `a step stops at the PC's own floor and ceiling`() {
        val floor = Limits.read(body).first { it.key == "jobs_per_tick" }.let { it.copy(pcOnly = false, value = JsonPrimitive(1)) }
        assertNull("nothing below the PC's low", floor.down)
        val top = floor.copy(value = JsonPrimitive(1000), low = 1, high = 1000)
        assertNull("nothing above the PC's high", top.up)
    }

    // ------------------------------------------------------- what is posted --

    @Test
    fun `the two routes are the only ones, and they are the limits routes`() {
        assertEquals("/api/limits", Limits.PATH)
        assertEquals("/api/limits/settings", Limits.WRITE_PATH)
        // A near miss ("/api/limit", "/api/limits/setting", "/api/attention/
        // settings") fails here rather than at runtime. Quoted literals only:
        // a route named in a doc comment is not a call.
        val inModel = Regex("\"(/api/[A-Za-z0-9_/]*)\"").findAll(source(LIMITS))
            .map { it.groupValues[1] }.toSet()
        assertEquals(setOf("/api/limits", "/api/limits/settings"), inModel)
        // ONE change carries the PC's own key and the new value, nothing else.
        assertEquals("""{"key":"undo_window","value":168}""", Limits.body("undo_window", 168L))
        assertEquals("""{"key":"memory_people","value":true}""", Limits.body("memory_people", true))
    }

    @Test
    fun `the API posts the change to the write route and reads the read route`() {
        val api = source(API)
        assertTrue("the read goes to Limits.PATH",
            api.contains("suspend fun limits(): ApiResult<JsonObject> = probe(Limits.PATH)"))
        assertTrue("the write goes to Limits.WRITE_PATH",
            api.contains("val target = url(Limits.WRITE_PATH)"))
        assertTrue("the write returns the body, so the PC's own sentence can be shown",
            api.contains("Limits.classifyPost(resp.code, obj)"))
        // The write path is used exactly once in the API, by setLimit: a second
        // user would mean a second way to change a limit.
        assertEquals(1, Regex("url\\(Limits\\.WRITE_PATH\\)").findAll(api).count())
    }

    @Test
    fun `the write path is held on a stale link and reports the PC's own failure`() {
        val rt = source(RUNTIME)
        val method = rt.substringAfter("suspend fun setLimit(").take(900)
        assertTrue("the stale-link blocker is checked first, as setManner does:\n$method",
            method.contains("actionBlocker()?.let { return it }"))
        assertTrue("the PC's sentence is read, not invented", method.contains("Limits.answer("))
        assertTrue("a refusal goes into the shared notice too",
            method.contains("_notice.value = answer.sentence"))
    }

    // ----------------------------------------------------------- the answer --

    @Test
    fun `a change shows the PC's sentence, word for word`() {
        val ok = Limits.answer(Limits.classifyPost(200, JarvisJson.parseToJsonElement(
            """{"ok":true,"said":"Cards in a study run is now 21 cards."}""") as JsonObject))
        assertEquals("Cards in a study run is now 21 cards.", ok.sentence)
        assertTrue("it went through", ok.changed)

        // A raise on a loosen_up row: the PC wrote it after its own card was
        // approved, so `said` is the PC's and this app adds nothing.
        val raised = Limits.answer(Limits.classifyPost(200, JarvisJson.parseToJsonElement(
            """{"ok":true,"loosening":true,"approved":true,"said":"How long you can undo is now keep undo for a week."}""") as JsonObject))
        assertEquals("How long you can undo is now keep undo for a week.", raised.sentence)
    }

    @Test
    fun `a refusal is the PC's sentence, and nothing is pretended to have changed`() {
        // 403: a pc_only limit asked for from a phone. The route's own words.
        val pcOnly = Limits.answer(Limits.classifyPost(403, JarvisJson.parseToJsonElement(
            """{"ok":false,"pc_only":true,"error":"That can only be changed on the PC."}""") as JsonObject))
        assertEquals("That can only be changed on the PC.", pcOnly.sentence)
        assertFalse("nothing was written", pcOnly.changed)

        // 400: a value the PC's own range refused.
        val out = Limits.answer(Limits.classifyPost(400, JarvisJson.parseToJsonElement(
            """{"ok":false,"error":"That has to be between 1 and 1000."}""") as JsonObject))
        assertEquals("That has to be between 1 and 1000.", out.sentence)
        assertFalse(out.changed)

        // 409: the card was denied or timed out on the PC.
        val denied = Limits.answer(Limits.classifyPost(409, JarvisJson.parseToJsonElement(
            """{"ok":false,"error":"You said no, so nothing was changed."}""") as JsonObject))
        assertEquals("You said no, so nothing was changed.", denied.sentence)
        assertFalse(denied.changed)
    }

    @Test
    fun `a PC without the table, and a lost link, say so without inventing a sentence`() {
        assertEquals(Limits.MISSING, Limits.answer(ApiResult.Failed(ApiError.NotFound)).sentence)
        assertTrue(Limits.missing(ApiError.NotFound))
        assertTrue(Limits.missing(ApiError.NotAvailable))
        // A 401 with no body is a bad token, not a sentence to show as the PC's.
        assertTrue(Limits.classifyPost(401, null) is ApiResult.Failed)
        assertTrue(Limits.classifyPost(200, null) is ApiResult.Failed)
    }

    // -------------------------------------------------------- the screen ----

    @Test
    fun `the plate draws only what Limits offered, and wires every control to setLimit`() {
        val plate = source(PLATE)
        assertTrue("the plate must draw the filtered list",
            plate.contains("rows = Limits.offered(r.value)"))
        assertTrue("every control goes through the runtime's one write",
            plate.contains("said = JarvisRuntime.setLimit(key, value)"))
        assertTrue("the plate never posts to a route itself", !plate.contains("/api/"))
        for (control in listOf("Limits.choiceWords(", "Limits.downWords(", "Limits.upWords(",
                               "Limits.rowWords(", "contentDescription")) {
            assertTrue("$control is missing from LimitsPlate.kt", plate.contains(control))
        }
    }

    @Test
    fun `each kind gets the control it needs`() {
        val plate = source(PLATE)
        // int with choices -> chips; int without -> a step pair; bool -> Toggle.
        assertTrue("the fixed choices are drawn as chips",
            plate.contains("row.kind == \"int\" && row.choices.isNotEmpty()"))
        assertTrue("a number with no fixed set gets a step pair", plate.contains("\"−\""))
        assertTrue("and the value between them", plate.contains("row.words"))
        assertTrue("a bool uses the app's own Toggle", plate.contains("Toggle("))
    }

    @Test
    fun `the Settings row and its jump entry are the same key`() {
        val screen = source(SETTINGS_SCREEN)
        // The row is drawn behind its own menu, like every other hideable row:
        // the menu is declared once (backend/jarvis_menus.py) and generated
        // into MenuCatalog.kt, and MenuVisibilityTest checks the place and the
        // check-in-a-screen. Asserting the WHOLE line is deliberate - a row that
        // lost its `if (menus.shows(...))` would be visible even with the menu
        // hidden, and only this form catches that.
        assertTrue("Settings has no limits row",
            screen.contains("if (menus.shows(\"settings.limits\")) item(key = \"limits\") {"))
        assertTrue("the limits row is not framed by its menu",
            screen.contains("MenuFrame(menus, \"settings.limits\") { LimitsSection(canAct = canAct) }"))
        val jump = source(SETTINGS_JUMP)
        assertTrue("the jump list has no limits entry", jump.contains("Entry(\"Limits and how often Jarvis does things\", \"limits\")"))
        val map = screen.substringAfter("SETTINGS_ITEM_INDEX: Map<String, Int> = mapOf(")
            .substringBefore("\n)")
        // 22, not 21: this branch's own row for what a captcha does about the
        // window it blocks (2026-10-09) sits directly under the hand-off row
        // at position 19, so every section below it moved down by one - the
        // same +1 the rest of that map carries. `SettingsJumpTest` holds every
        // number there to the row the screen really draws.
        assertTrue("the index map has no limits row", map.contains("\"limits\" to 22"))
    }

    // ------------------------------------------------------------- helpers --

    /**
     * Just the code: whole-line `//` comments dropped, so an assertion on what
     * a file DOES is never satisfied by a comment that names the same thing on
     * purpose (the same helper SettingsJumpTest uses).
     */
    private fun source(rel: String): String =
        repoFile(rel).readText().lines()
            .filterNot { it.trimStart().startsWith("//") }
            .joinToString("\n")

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val LIMITS = "jarvis-client/app/src/main/java/com/jarvis/client/net/Limits.kt"
    private val API = "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt"
    private val RUNTIME = "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt"
    private val PLATE = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/LimitsPlate.kt"
    private val SETTINGS_SCREEN = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt"
    private val SETTINGS_JUMP = "jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt"
}
