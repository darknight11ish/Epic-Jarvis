package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Attention
import com.jarvis.client.net.AttentionSettings
import com.jarvis.client.net.AttentionResponse
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's own control for the interruption budget ([AttentionSettings],
 * BrainScreen.kt's AttentionPlate, the PC's own
 * `POST /api/attention/settings` through `jarvis_arbiter.change` and
 * `jarvis-desktop/src-tauri/src/attention.rs` `set_attention_limits`).
 *
 * The gap this closes: the PC's Brain has had "Speak up" and "Brief at" since
 * 2026-10-08 (`brain.html:307,309`), the phone could only READ them, and
 * `tools/check_parity.py` still classified the route `todo`. These tests hold
 * the write path to four things a JVM cannot press a button to check:
 *
 *  * WHAT IS SENT - the route, the one key, the one number, and NOT a direction
 *    (the PC's `change` reads the direction off the number against the budget in
 *    force; a caller that could send one could hide a raise from the card);
 *  * WHAT IS SHOWN - the PC's own `said`, and its own refusal words, never a
 *    sentence invented here;
 *  * WHAT IS NEVER SENT - a number outside the PC's own range, checked before
 *    the body is built as well as by the buttons' own floor and ceiling;
 *  * WHAT A STALE LINK DOES - the control is disabled and nothing is posted.
 *
 * The source checks are the app's usual kind (LimitsTest, MenuVisibilityTest,
 * TouchTargetAndInsetsTest): the FACT that the plate draws two controls, wires
 * them to the runtime's one write and re-reads afterwards is held to the text
 * that does it.
 */
class AttentionSettingsTest {

    // ------------------------------------------------------------- the route --

    @Test
    fun `the one route is the PC's own settings route, and nothing else`() {
        assertEquals("/api/attention/settings", AttentionSettings.PATH)
        assertEquals("spoken_per_day", AttentionSettings.KEY_COUNT)
        assertEquals("digest_hour", AttentionSettings.KEY_HOUR)
        // Quoted literals only, and the comments are stripped first: a route
        // named in a doc comment is not a call. The budget module owns exactly
        // one route; the API names it as well (and keeps the two mute routes it
        // already had). The runtime goes through the module, so it names none.
        val owned = Regex("\"(/api/attention[A-Za-z0-9_/]*)\"")
            .findAll(source(BUDGET)).map { it.groupValues[1] }.toSet()
        assertEquals("the budget module must own exactly one route",
            setOf(AttentionSettings.PATH), owned)
        // The API reaches it through the module's constant - no second copy of
        // the path, which is what would let the two drift apart. (A KDoc
        // mention is blanked by [source], so this is a real call.)
        assertTrue("the API does not post to the budget route",
            source(API).contains("url(AttentionSettings.PATH)"))
        assertFalse("the runtime must not build a route by hand",
            source(RUNTIME).contains("\"/api/attention"))
        // And the plate never names a route at all: it goes through the runtime.
        assertFalse("BrainScreen must not build a POST by hand",
            source(PLATE).contains("/api/attention"))
    }

    // ----------------------------------------------------------- what is sent --

    @Test
    fun `a change carries the one key and the one number, and never a direction`() {
        assertEquals("""{"spoken_per_day":6}""", AttentionSettings.body(AttentionSettings.KEY_COUNT, 6))
        assertEquals("""{"digest_hour":9}""", AttentionSettings.body(AttentionSettings.KEY_HOUR, 9))
        assertEquals("""{"spoken_per_day":0}""", AttentionSettings.countBody(0))
        assertEquals("""{"digest_hour":23}""", AttentionSettings.hourBody(23))

        // NOT a direction: the PC's `change` decides which way it is from the
        // number against the budget already in force, so a caller cannot call a
        // raise a lowering and skip the card (bug audit finding E2).
        for (body in listOf(AttentionSettings.countBody(9), AttentionSettings.hourBody(9))) {
            for (word in listOf("loosening", "up", "down", "raise", "lower", "direction",
                "approved", "changed")) {
                assertFalse("$word must never be sent: $body", body.contains(word))
            }
        }

        // ONE number at a time - the route answers 400 for two, and a card
        // asking about both at once is a card nobody could answer well.
        assertFalse(AttentionSettings.countBody(6).contains(AttentionSettings.KEY_HOUR))
        assertFalse(AttentionSettings.hourBody(6).contains(AttentionSettings.KEY_COUNT))
    }

    @Test
    fun `the API posts to the budget route and returns the body, so the PC's words can be shown`() {
        val api = source(API)
        val method = api.substringAfter("suspend fun setAttentionLimit(").take(900)
        assertTrue("the write does not go to AttentionSettings.PATH:\n$method",
            method.contains("url(AttentionSettings.PATH)"))
        assertTrue("the body comes back, not a bare status:\n$method",
            method.contains("AttentionSettings.classifyPost(resp.code, obj)"))
        assertTrue("the write is authed, so X-Jarvis-Client rides along:\n$method",
            method.contains(".authed()"))
        // The short call: an arbiter on the same machine either answers at once
        // or is not there, exactly as the limits write reasons.
        assertTrue("the write must use the short call:\n$method",
            method.contains("shortCall.newCall(req)"))
        // Never the token in a log line, and no URL built by hand.
        assertFalse("the token must never be logged", method.contains("X-Jarvis-Token"))
        assertEquals("the budget route is used exactly once in the API",
            1, Regex("url\\(AttentionSettings\\.PATH\\)").findAll(api).count())
    }

    // ------------------------------------------------------- what is refused --

    @Test
    fun `the hour and the count are checked against the PC's own range before they are sent`() {
        // The PC's own numbers (jarvis_arbiter.SPOKEN_PER_DAY_MIN/MAX 0..24,
        // DIGEST_HOUR_MIN/MAX 0..23) - held here so a control cannot offer a
        // number the backend would refuse.
        assertEquals(0, AttentionSettings.COUNT_LOW)
        assertEquals(24, AttentionSettings.COUNT_HIGH)
        assertEquals(0, AttentionSettings.HOUR_LOW)
        assertEquals(23, AttentionSettings.HOUR_HIGH)

        for (n in 0..24) assertTrue("$n a day is in range", AttentionSettings.countToSend(n) == n)
        for (n in listOf(-1, 25, 99, Int.MIN_VALUE, Int.MAX_VALUE)) {
            assertNull("$n a day must not be sent as-is", AttentionSettings.countToSend(n))
            assertFalse("$n a day is out of range", AttentionSettings.countInRange(n))
        }
        for (h in 0..23) assertTrue("$h o'clock is in range", AttentionSettings.hourToSend(h) == h)
        for (h in listOf(-1, 24, 100, Int.MIN_VALUE, Int.MAX_VALUE)) {
            assertNull("$h o'clock must not be sent as-is", AttentionSettings.hourToSend(h))
            assertFalse("$h o'clock is out of range", AttentionSettings.hourInRange(h))
        }
    }

    @Test
    fun `the hour reads as a clock, in the PC's own words`() {
        // The same strings the PC's picker builds (brain.js budgetHourWords),
        // so the two screens say one thing.
        assertEquals("midnight (00:00)", AttentionSettings.hourWords(0))
        assertEquals("1 am (01:00)", AttentionSettings.hourWords(1))
        assertEquals("8 am (08:00)", AttentionSettings.hourWords(8))
        assertEquals("noon (12:00)", AttentionSettings.hourWords(12))
        assertEquals("1 pm (13:00)", AttentionSettings.hourWords(13))
        assertEquals("8 pm (20:00)", AttentionSettings.hourWords(20))
        assertEquals("11 pm (23:00)", AttentionSettings.hourWords(23))
        // The count, in the PC's picker words.
        assertEquals("not at all", AttentionSettings.countWords(0))
        assertEquals("once a day", AttentionSettings.countWords(1))
        assertEquals("6 times a day", AttentionSettings.countWords(6))
    }

    // --------------------------------------------------------- what is shown --

    @Test
    fun `a change shows the PC's sentence, word for word`() {
        // A lowering: written at once.
        val down = AttentionSettings.answer(AttentionSettings.classifyPost(200, obj(
            """{"ok":true,"changed":true,"loosening":false,"from":6,"to":2,
                "said":"Jarvis may speak up to 2 times a day."}""")))
        assertEquals("Jarvis may speak up to 2 times a day.", down.sentence)
        assertTrue("the PC says it wrote it", down.changed)

        // The hour: never a card, and its own sentence.
        val hour = AttentionSettings.answer(AttentionSettings.classifyPost(200, obj(
            """{"ok":true,"changed":true,"loosening":false,"from":18,"to":8,
                "said":"The morning brief arrives at 08:00 now."}""")))
        assertEquals("The morning brief arrives at 08:00 now.", hour.sentence)

        // A RAISE: the PC's card was approved there, and `said` says so. This
        // app adds nothing and never says "a card is waiting" itself.
        val raise = AttentionSettings.answer(AttentionSettings.classifyPost(200, obj(
            """{"ok":true,"loosening":true,"approved":true,"from":2,"to":6,
                "said":"Jarvis may now speak up to 6 times a day."}""")))
        assertEquals("Jarvis may now speak up to 6 times a day.", raise.sentence)

        // Zero is a real setting, not a missing one.
        val none = AttentionSettings.answer(AttentionSettings.classifyPost(200, obj(
            """{"ok":true,"changed":true,"from":3,"to":0,
                "said":"Jarvis will not speak up on its own today."}""")))
        assertEquals("Jarvis will not speak up on its own today.", none.sentence)
    }

    @Test
    fun `a refusal is the PC's own words, and nothing is pretended to have changed`() {
        // 409: the raise's card was denied on the PC. The PC's own sentence.
        val denied = AttentionSettings.answer(AttentionSettings.classifyPost(409, obj(
            """{"ok":false,"error":"You said no, so Jarvis still speaks up to 2 times a day."}""")))
        assertEquals("You said no, so Jarvis still speaks up to 2 times a day.", denied.sentence)
        assertFalse("nothing was written", denied.changed)

        // 409: the card timed out.
        val timedOut = AttentionSettings.answer(AttentionSettings.classifyPost(409, obj(
            """{"ok":false,"error":"The card was not answered in time, so Jarvis still speaks up to 2 times a day."}""")))
        assertTrue(timedOut.sentence.startsWith("The card was not answered in time"))
        assertFalse(timedOut.changed)

        // 400: a value the route's own range refused.
        val out = AttentionSettings.answer(AttentionSettings.classifyPost(400, obj(
            """{"ok":false,"error":"That has to be a whole number between 0 and 24."}""")))
        assertEquals("That has to be a whole number between 0 and 24.", out.sentence)
        assertFalse(out.changed)

        // 503: the PC's Jarvis cannot ask about it at all.
        val cannot = AttentionSettings.answer(AttentionSettings.classifyPost(503, obj(
            """{"ok":false,"error":"Your PC's Jarvis cannot ask you about that yet, so nothing was changed."}""")))
        assertTrue(cannot.sentence.startsWith("Your PC's Jarvis cannot ask"))
        assertFalse(cannot.changed)
    }

    @Test
    fun `a PC without the route, and a lost link, say so without inventing a sentence`() {
        // An unpatched PC answers 404 - the owner's words, not an HTTP line.
        assertEquals(AttentionSettings.MISSING,
            AttentionSettings.answer(ApiResult.Failed(ApiError.NotFound)).sentence)
        assertTrue(AttentionSettings.missing(ApiError.NotFound))
        assertTrue(AttentionSettings.missing(ApiError.NotAvailable))
        assertTrue(AttentionSettings.missing(ApiError.Server(501, "")))
        assertFalse("a 500 is not 'the route is missing'", AttentionSettings.missing(ApiError.Server(500, "")))
        // A 401 with no body is a bad token, not a sentence to show as the PC's.
        assertTrue(AttentionSettings.classifyPost(401, null) is ApiResult.Failed)
        assertTrue(AttentionSettings.classifyPost(200, null) is ApiResult.Failed)
    }

    // ------------------------------------------------------ what the app owns --

    @Test
    fun `the write is held on a stale link, refuses to invent words, and re-reads`() {
        val rt = source(RUNTIME)
        val method = rt.substringAfter("suspend fun setAttentionSettings(").take(900)
        assertTrue("the stale-link blocker is checked first, as setLimit does:\n$method",
            method.contains("actionBlocker()?.let { return it }"))
        assertTrue("the PC's sentence is read, not invented", method.contains("AttentionSettings.answer("))
        assertTrue("the body is built by AttentionSettings, so no route or key is written here",
            method.contains("AttentionSettings.body(key, value)"))
        assertTrue("a refusal goes into the shared notice too",
            method.contains("_notice.value = answer.sentence"))
        assertTrue("the read is refreshed after the attempt - a 2xx can mean " +
            "'a card is waiting', never 'it is on'", method.contains("refreshAttention()"))
    }

    // -------------------------------------------------------------- the read --

    @Test
    fun `the card's hour comes from the same read as its count`() {
        // The wire shape `GET /api/attention` answers (jarvis_arbiter.status):
        // the budget one level down, the hour and the pending count flat.
        val body = JarvisJson.parseToJsonElement(
            """{"available":true,
                "budget":{"limit":6,"spent":1,"remaining":5,"blocked_by":null,"muted":false},
                "pending":2,"banked":false,"digest_hour":8,"digest_due":false}""",
        ) as JsonObject
        val flat: Attention = (JarvisJson.decodeFromJsonElement(
            AttentionResponse.serializer(), body)).flatten()
        assertEquals("the count the 'Speak up' stepper steps from", 6, flat.limit)
        assertEquals("the hour the 'Brief at' stepper steps from", 8, flat.digestHour)
        assertEquals(5, flat.remaining)
        assertEquals(2, flat.pending)

        // An older PC that omits the hour gets the PC's own fallback (18), not 0
        // - 0 would read as "midnight" and be a setting nobody chose.
        val old = (JarvisJson.decodeFromJsonElement(AttentionResponse.serializer(),
            JarvisJson.parseToJsonElement(
                """{"budget":{"limit":3,"spent":0,"remaining":3}}""") as JsonObject)).flatten()
        assertEquals(18, old.digestHour)
    }

    // ------------------------------------------------------------ the screen --

    @Test
    fun `the plate draws both controls, the owner's words for TalkBack, and re-reads`() {
        val plate = source(PLATE)
        assertTrue("the plate never posts to a route itself", !plate.contains("/api/"))
        assertTrue("every change goes through the runtime's one write",
            plate.contains("JarvisRuntime.setAttentionSettings(key, value)"))
        assertTrue("the count comes from the budget read", plate.contains("attention.limit"))
        assertTrue("the hour comes from the same read", plate.contains("attention.digestHour"))
        assertTrue("the two keys are the module's own constants",
            plate.contains("AttentionSettings.KEY_COUNT") && plate.contains("AttentionSettings.KEY_HOUR"))
        // TalkBack: the value and BOTH steps of each control carry words, so a
        // step is never a bare "-" - the same habit LimitsPlate has.
        for (words in listOf("AttentionSettings.countValueWords(", "AttentionSettings.countDownWords(",
            "AttentionSettings.countUpWords(", "AttentionSettings.hourValueWords(",
            "AttentionSettings.hourDownWords(", "AttentionSettings.hourUpWords(", "contentDescription")) {
            assertTrue("$words is missing from BrainScreen.kt", plate.contains(words))
        }
        // An out-of-range number is never posted as-is.
        assertTrue("the count's step is checked before it is sent",
            plate.contains("AttentionSettings.countToSend(limit - 1)?.let"))
        assertTrue("the hour's step is checked before it is sent",
            plate.contains("AttentionSettings.hourToSend(attention.digestHour - 1)"))
        // A stale link disables both, in words as well.
        assertTrue("the controls are disabled when the link cannot act",
            plate.contains("canAct && !busy"))
        assertTrue("and the plate says why", plate.contains("Not connected to the desktop"))
        // The plate re-reads after every change: `JarvisRuntime.setAttentionSettings`
        // reads it once itself, and the plate asks for its own read in the
        // `finally`, so a card that went through on the PC and a card still
        // waiting there both leave the count, the hour and the meter agreeing
        // with the PC.
        assertTrue("the plate must re-read after a change",
            plate.contains("onRefreshAttention()"))
        assertTrue("and it must be in the finally, so a refusal re-reads too",
            plate.substringAfter("fun change(").take(700).contains("finally"))
    }

    @Test
    fun `the Attention card keeps its place and its menu check`() {
        val screen = source(PLATE)
        assertTrue("the card lost its item key",
            screen.contains("item(key = \"attention\")"))
        assertTrue("the card lost its section title",
            screen.contains("Section(\"Attention budget\")"))
        // The first two rows are untouched: the count and the meter.
        assertTrue(screen.contains("of \$limit spoken interruptions left today"))
        assertTrue(screen.contains("Meter("))
        // `brain.now.budget` is never hideable (MenuVisibilityTest holds the id),
        // and the card is drawn without a `menus.shows` check - so the check that
        // must survive this work is that it still has none, and that its place is
        // still declared.
        assertFalse("the never-hideable card must not be put behind a hideable check",
            screen.contains("menus.shows(\"brain.now.budget\")"))
        assertTrue("the menu's place is gone",
            source(MENU_PLACES).contains("\"attention\" to \"brain.now.budget\""))
    }

    @Test
    fun `both controls use the app's own 48dp quiet action`() {
        val screen = source(PLATE)
        // Quiet carries `heightIn(min = 48.dp)` itself (Parts.kt), so the two
        // steps are 48dp tall whatever the glyph looks like.
        assertTrue("the count's steps are Quiet actions",
            screen.contains("private fun NumberStepper("))
        val parts = source(PARTS)
        val quiet = parts.substringAfter("fun Quiet(").take(500)
        assertTrue("Quiet no longer carries the 48dp minimum:\n$quiet",
            quiet.contains("heightIn(min = 48.dp)") || quiet.contains("pressable("))
    }

    // ------------------------------------------------------------- helpers --

    /**
     * Just the code. Whole-line `//` comments AND block comments are blanked
     * (the `TouchTargetAndInsetsTest.code` habit, kept line for line), so a
     * route named in a KDoc block - "/api/attention/settings, the route the
     * PC's Brain writes through" - is never mistaken for a call this file
     * makes. Dropping the lines instead of blanking them would also delete the
     * explanations the assertions above ask for.
     */
    private fun source(rel: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in repoFile(rel).readText().lines()) {
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
            out.add(line)
        }
        return out.joinToString("\n")
    }

    private fun obj(json: String): JsonObject =
        JarvisJson.parseToJsonElement(json.trimIndent()) as JsonObject

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

    private val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/"
    private val BUDGET = BASE + "net/AttentionSettings.kt"
    private val API = BASE + "net/JarvisApi.kt"
    private val RUNTIME = BASE + "JarvisRuntime.kt"
    private val PLATE = BASE + "ui/screens/BrainScreen.kt"
    private val MENU_PLACES = BASE + "ui/MenuPlaces.kt"
    private val PARTS = BASE + "ui/parts/Parts.kt"
}
