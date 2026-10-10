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

    /**
     * The seven rows the owner's decision of 2026-10-08 added to the PC's table:
     * THIS PC's own notification choices, which the phone may change too. Two of
     * them are the third kind, `time` - the quiet hours' two ends, carried as the
     * clock STRING the owner reads ("22:00"), never a number of minutes - and
     * every row carries the PC's additive `quiet_on`.
     */
    private val notifyBody: JsonObject = JarvisJson.parseToJsonElement(
        """
        {"ok":true,"available":true,"limits":[
          {"key":"notif_alarms","title":"Speak up when an alarm rings (on your PC)","kind":"bool",
           "value":true,"words":"Speak up when an alarm rings (on your PC)","choices":[],"low":0,
           "high":0,"unit":"","note":"An alarm rings until you dismiss it.","loosen_up":false,
           "pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_quiet_enabled","title":"Be quiet during quiet hours (on your PC)","kind":"bool",
           "value":true,"words":"Be quiet during quiet hours (on your PC)","choices":[],"low":0,
           "high":0,"unit":"","note":"Silences the PC's non-urgent notifications.","loosen_up":false,
           "pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_quiet_start","title":"Quiet hours start (on your PC)","kind":"time",
           "value":"22:00","words":"22:00","choices":[],"low":0,"high":0,"unit":"",
           "note":"The hour the PC's quiet window begins, on the PC's own clock.","loosen_up":false,
           "pc_only":false,"app":"both","quiet_on":true},
          {"key":"notif_quiet_end","title":"Quiet hours end (on your PC)","kind":"time",
           "value":"07:00","words":"07:00","choices":[],"low":0,"high":0,"unit":"",
           "note":"The hour the PC's quiet window ends, on the PC's own clock.","loosen_up":false,
           "pc_only":false,"app":"both","quiet_on":true}
        ]}
        """.trimIndent(),
    ) as JsonObject

    private fun notifyRow(key: String): Limits.Row =
        requireNotNull(Limits.offered(notifyBody).firstOrNull { it.key == key }) { "$key is not offered" }

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
        val method = rt.substringAfter("suspend fun setLimit(").take(1100)
        assertTrue("the stale-link blocker is checked first, as setManner does:\n$method",
            method.contains("actionBlocker()?.let { return com.jarvis.client.net.Limits.Answer(it, changed = false) }"))
        assertTrue("the PC's sentence is read, not invented", method.contains("Limits.answer("))
        assertTrue("a refusal goes into the shared notice too",
            method.contains("_notice.value = answer.sentence"))
        // Both halves of the answer come back, so the plate can say a save did
        // not happen (item 9, 2026-10-10) - the sentence alone was drawn the
        // same way whether it worked or not.
        assertTrue("the whole answer comes back, not just its words",
            method.contains(": com.jarvis.client.net.Limits.Answer {"))
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

    @Test
    fun `a save that never happened says so instead of closing as if it worked`() {
        // THE BUG THIS EXISTS FOR (item 9, found on the owner's phone
        // 2026-10-10). The PC's own `POST /api/limits/settings` is NOT there on
        // this install - `jarvis_hud.py`'s dispatcher never reaches
        // `_desktop_action` for that route, so it answers 404 with the
        // server's own `{"error": "not found"}` (measured on the owner's PC:
        // 404, that body; `GET /api/limits` answers 200). That body's `error`
        // matched the branch below that keeps the PC's own sentence, so the
        // 404 was read as a SUCCESSFUL answer whose sentence was the literal
        // text "not found" - `changed` came out true, nothing went into the
        // shared notice, and choosing a new time closed the picker as if it
        // had saved.
        val notFound = JarvisJson.parseToJsonElement("""{"error":"not found"}""") as JsonObject
        val missingRoute = Limits.classifyPost(404, notFound)
        assertTrue("a 404 is not an answer about the change: $missingRoute",
            missingRoute is ApiResult.Failed)
        val answer = Limits.answer(missingRoute)
        assertEquals("the owner reads the plain sentence, not the server's",
            Limits.MISSING, answer.sentence)
        assertFalse("and nothing is pretended to have changed", answer.changed)

        // The PC's own refusals still arrive in the PC's own words, unchanged:
        // this fix may not swallow a real sentence.
        val refused = Limits.answer(Limits.classifyPost(403, JarvisJson.parseToJsonElement(
            """{"ok":false,"pc_only":true,"error":"That can only be changed on the PC."}""") as JsonObject))
        assertEquals("That can only be changed on the PC.", refused.sentence)
        assertFalse(refused.changed)
    }

    @Test
    fun `the plate says a failed save on the row it was asked for`() {
        val plate = source(PLATE)
        // WHERE, not only WHAT. The answer used to be drawn once for the whole
        // card, under a dozen rows - off the bottom of the screen for a change
        // made near the top, and off the top for one made near the bottom (the
        // quiet-hours clock, measured on the owner's phone 2026-10-10). It is
        // drawn per row now, under that row's own control.
        val rowCall = plate.substringAfter("else -> v.forEach").take(600)
        assertTrue("the answer is passed to the row it belongs to:\n$rowCall",
            rowCall.contains("said = if (saidFor == r.key) said else null"))
        // ...and the row draws it after its control, never before it.
        val rowFn = plate.substringAfter("private fun LimitRow(")
        val control = rowFn.indexOf("Toggle(")
        val answer = rowFn.indexOf("said?.let")
        assertTrue("the answer is drawn under the row's control (control=$control, answer=$answer)",
            control in 0 until answer)
        assertTrue("a save that changed nothing is drawn as a warning",
            plate.contains("if (saidFailed) chrome.warnInk"))
        assertTrue("the plate knows whether anything was written",
            plate.contains("saidFailed = !a.changed"))
        assertTrue("and both halves come from the one write",
            plate.contains("val a = JarvisRuntime.setLimit(key, value)"))
        assertTrue("the sentence remembers which row asked for it",
            plate.contains("saidFor = key"))
        // Cleared before every change, so an old answer can never stand in for
        // this one's - on the row itself or on any other.
        assertTrue(plate.contains("saidFor = null"))
        assertTrue(plate.contains("saidFailed = false"))
    }

    // -------------------------------------------------------- the screen ----

    @Test
    fun `the plate draws only what Limits offered, and wires every control to setLimit`() {
        val plate = source(PLATE)
        assertTrue("the plate must draw the filtered list",
            plate.contains("rows = Limits.offered(r.value)"))
        assertTrue("every control goes through the runtime's one write",
            plate.contains("val a = JarvisRuntime.setLimit(key, value)"))
        assertTrue("the plate never posts to a route itself", !plate.contains("/api/"))
        for (control in listOf("Limits.choiceWords(", "Limits.downWords(", "Limits.upWords(",
                               "Limits.rowWords(", "contentDescription")) {
            assertTrue("$control is missing from LimitsPlate.kt", plate.contains(control))
        }
    }

    @Test
    fun `the line above the rows promises no direction`() {
        // THE BUG THIS EXISTS FOR (found 2026-10-09). `Limits.LOOSEN_NOTE` is
        // drawn ONCE, above every row, and it used to end "Turning something
        // down applies at once." That is FALSE for a row whose loosening goes
        // DOWN - the voice check's bar, where a lower bar means more clips
        // count as the owner's voice, so going lower is the direction that
        // raises ONE card on the PC. The plate therefore told the owner the
        // opposite of what the row immediately under that line does, and the
        // row's own note said so in the very next line.
        //
        // Which direction asks is the ROW's business (the PC sends it in the
        // row's own `note`), so the general line may not name one. This checks
        // the constant AND the plate's own doc comment, because the comment is
        // what a later editor reads before changing the sentence.
        val claimsDownIsInstant = Regex(
            """\bdown\s+(?:changes|applies|takes effect|is applied|goes through)\b""" +
                """|\bdown\s+(?:\w+\s+){0,3}at once\b""",
            RegexOption.IGNORE_CASE,
        )
        assertTrue(
            "Limits.LOOSEN_NOTE tells the owner a smaller number always applies at once",
            !claimsDownIsInstant.containsMatchIn(Limits.LOOSEN_NOTE),
        )
        assertTrue(
            "the plate tells the owner a smaller number always applies at once",
            !claimsDownIsInstant.containsMatchIn(source(PLATE)),
        )
        // ...and it still says the thing that IS true of every row under it:
        // the PC decides, and the row's own sentence says which way this one
        // goes.
        assertTrue(
            "the note no longer says the row's own line carries the direction",
            Limits.LOOSEN_NOTE.contains("line under each one says which"),
        )
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
        // 25, not 21: four insertions above it have moved it four times on
        // 2026-10-09 - the phone's search box (position 0, above the jump list,
        // so every section below it moved down by one), "Notifications from
        // Jarvis" (the owner's decision of that day, at position 17), what a
        // captcha does about the window it blocks (position 21, directly under
        // the hand-off row) and the phone's own "Screen refresh rate" (position
        // 24, immediately above this row). Each carries the same +1 through the
        // map below them, and `SettingsJumpTest` holds every number there to the
        // row the screen really draws.
        assertTrue("the index map has no limits row", map.contains("\"limits\" to 25"))
    }

    // ------------------------------------------- a time of day, and the PC's
    //                                              own notifications (2026-10-08)

    @Test
    fun `this PC's own notification rows reach the phone, and say whose they are`() {
        // Every one of them is offered here, and every title says the setting is
        // the PC's - the phone's OWN notification settings are a different screen.
        assertEquals(listOf("notif_alarms", "notif_quiet_enabled", "notif_quiet_start",
            "notif_quiet_end"), Limits.offered(notifyBody).map { it.key })
        for (r in Limits.offered(notifyBody)) {
            assertTrue("${r.key} must say the setting is the PC's own", r.title.contains("(on your PC)"))
            assertFalse("${r.key} is not a loosening either way", r.loosenUp)
            assertEquals("both", r.app)
        }
    }

    @Test
    fun `a clock time is a clock string, never a number of minutes`() {
        val start = notifyRow("notif_quiet_start")
        assertEquals("time", start.kind)
        assertTrue(start.isTime)
        assertEquals("the string the PC sent, unchanged", "22:00", start.clock)
        assertEquals("the PC's own words for the row", "22:00", start.words)
        // No step and no shape a number could take.
        assertNull("a clock has no step up", start.up)
        assertNull("and none down", start.down)
        assertEquals("and no range line either", "", Limits.rangeLine(start))

        // What ONE change posts: the clock STRING, quoted on the wire. This is
        // the assertion that fails if a time is ever sent as 1320 minutes.
        assertEquals("""{"key":"notif_quiet_start","value":"22:00"}""",
            Limits.body("notif_quiet_start", Limits.timeJson("22:00")))
        assertTrue("never a bare number",
            !Limits.body("notif_quiet_start", Limits.timeJson("22:00")).contains("1320"))
    }

    @Test
    fun `the phone checks the clock's shape before anything is sent`() {
        assertEquals("the PC's own shape, normalised", "07:05", Limits.validTime("7:05"))
        assertEquals("already normal", "22:00", Limits.validTime(" 22:00 "))
        for (junk in listOf("1320", "25:00", "22:60", "7:5", "", "half past ten")) {
            assertNull("$junk is not a time of day", Limits.validTime(junk))
        }
        // The picker starts where the value in force is - and a value it cannot
        // read starts at the PC's own default rather than at midnight.
        assertEquals(Pair(22, 0), Limits.hourMinute("22:00"))
        assertEquals(Pair(7, 5), Limits.hourMinute("7:05"))
        assertEquals(Pair(22, 0), Limits.hourMinute("nonsense"))
    }

    @Test
    fun `quiet_on says whether the two hours decide anything`() {
        assertTrue("quiet hours are on, so the times matter", notifyRow("notif_quiet_start").quietOn)
        // The PC sends the SAME answer on every row; with quiet hours off the two
        // clock rows say so and the plate offers no clock.
        val off = notifyRow("notif_quiet_end").copy(quietOn = false)
        assertFalse("the PC says quiet hours are off", off.quietOn)
        assertTrue("the off row's words say the hour decides nothing",
            Limits.timeWords(off).contains(Limits.TIME_QUIET_OFF))
        // A PC that does not send the field at all is read as "they do", so an
        // unknown field never hides a control from the owner.
        val silent = JarvisJson.parseToJsonElement(
            """{"limits":[{"key":"t","title":"Quiet hours start (on your PC)","kind":"time",
                "value":"22:00","words":"22:00","choices":[],"low":0,"high":0,"unit":"","note":""}]}""",
        ) as JsonObject
        assertTrue("a row that does not say is drawn", Limits.offered(silent).single().quietOn)
    }

    @Test
    fun `a row whose value is not a clock string is not offered at all`() {
        // A PC sending a number of minutes (the exact mistake this kind exists to
        // prevent) leaves the row out rather than drawing "1320" as if it were a
        // time - and a kind this app has no control for is left out as before.
        val bad = JarvisJson.parseToJsonElement(
            """{"limits":[
              {"key":"t1","title":"Quiet hours start (on your PC)","kind":"time","value":1320,
               "words":"1320","choices":[],"low":0,"high":0,"unit":"","note":""},
              {"key":"t2","title":"Quiet hours end (on your PC)","kind":"time","value":"07:00",
               "words":"07:00","choices":[],"low":0,"high":0,"unit":"","note":""}
            ]}""",
        ) as JsonObject
        assertEquals("only the real clock string is drawn", listOf("t2"), Limits.read(bad).map { it.key })
    }

    @Test
    fun `the clock row's control carries the owner's words for TalkBack`() {
        val words = Limits.timeWords(notifyRow("notif_quiet_start"))
        assertTrue("the button names the row:\n$words", words.contains("Quiet hours start (on your PC)"))
        assertTrue("and the value in force:\n$words", words.contains("22:00"))
        assertEquals("Change", Limits.CHANGE_TIME)
        // With quiet hours off the row says the hour decides nothing instead.
        val off = Limits.timeWords(notifyRow("notif_quiet_end").copy(quietOn = false))
        assertTrue("the off row says so:\n$off", off.contains(Limits.TIME_QUIET_OFF))
    }

    @Test
    fun `the plate draws the app's own clock, and sends only what it shows`() {
        val plate = source(PLATE)
        assertTrue("the plate must draw the app's own time picker",
            plate.contains("TimePicker(state = state)"))
        assertTrue("started where the value in force is",
            plate.contains("Limits.hourMinute(row.clock.orEmpty())"))
        assertTrue("24-hour, like the value the PC holds",
            plate.contains("is24Hour = true"))
        assertTrue("the shape is checked before anything is sent",
            plate.contains("Limits.validTime(\"%02d:%02d\".format(state.hour, state.minute))"))
        assertTrue("the picked time is sent as the clock string",
            plate.contains("change(open.key, Limits.timeJson(text))"))
        assertTrue("the clock row's own branch exists", plate.contains("row.isTime ->"))
        assertTrue("and the off row is told apart",
            plate.contains("if (!row.quietOn)"))
        assertTrue("TalkBack words on the clock's control",
            plate.contains("Limits.timeWords(row)"))
        assertTrue("the plate never posts to a route itself", !plate.contains("/api/"))
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
