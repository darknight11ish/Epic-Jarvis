package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Retirement
import kotlinx.serialization.json.JsonObject
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
 * Retirement what-if on the phone ([Retirement]; docs/JARVIS-API.md section
 * 103; docs/FINANCE-DESIGN.md part B and its frozen "Retirement contract").
 *
 * The fixtures (`contract/retirement-cases.json`, written by
 * `tools/gen_retirement_cases.py` from the real backend code, and read by the
 * desktop's tests too) are `jarvis_retirement.defaults()` and `.run()` for: 40
 * now, stop at 65, 100,000 saved, 12,000 a year, spend 30,000, all else the
 * placeholders - and three other states. Nothing in this file works a figure
 * out or holds a copy of the PC's words; the rule these tests keep coming back
 * to is that the app draws the strings it is given and computes nothing.
 */
class RetirementTest {

    private fun obj(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    private val defaults: Retirement.Defaults = requireNotNull(Retirement.parseDefaults(obj(DEFAULTS_JSON)))

    private fun result(json: String): Retirement.Result {
        val out = Retirement.classify(Retirement.Reply(200, obj(json)))
        return (out as Retirement.Outcome.Done).result
    }

    private fun field(key: String) = defaults.fields.first { it.key == key }

    private val typed = mapOf(
        "current_age" to "40", "retirement_age" to "65", "savings" to "100,000",
        "yearly_saving" to "12000", "yearly_spending" to "30000",
    )

    // ------------------------------------------------------------- words ---

    @Test
    fun `the fixed words are the contract's`() {
        assertEquals("Retirement what-if", Retirement.TITLE)
        assertEquals("Work it out", Retirement.RUN)
        assertEquals("Working it out", Retirement.WORKING)
        assertEquals("assumed", Retirement.ASSUMED)
        assertEquals("What I used", Retirement.USED_HEADING)
        assertEquals("Retirement what-if hidden", Retirement.HIDDEN)
        assertEquals("This is a simplified what-if, not financial advice.", Retirement.DISCLAIMER)
        assertEquals(defaults.words.hidden, Retirement.HIDDEN)
        assertEquals(defaults.words.busy, Retirement.BUSY)
        assertEquals(defaults.words.tooSlow, Retirement.TOO_SLOW)
        assertEquals(defaults.disclaimer, Retirement.DISCLAIMER)
        assertEquals(defaults.title, Retirement.TITLE)
    }

    @Test
    fun `the routes are the literal contract strings`() {
        assertEquals("/api/retirement/defaults", Retirement.DEFAULTS_PATH)
        assertEquals("/api/retirement/run", Retirement.RUN_PATH)
    }

    // -------------------------------------------------------------- form ---

    @Test
    fun `the form has the eleven boxes in the contract's order`() {
        assertEquals(Retirement.KEYS, defaults.fields.map { it.key })
        assertEquals(11, defaults.fields.size)
        assertEquals(90, defaults.maxYears)
    }

    @Test
    fun `required boxes have no default and the made-up ones are marked`() {
        val required = defaults.fields.filter { it.required }.map { it.key }
        assertEquals(
            listOf("current_age", "retirement_age", "savings", "yearly_saving", "yearly_spending"),
            required,
        )
        val placeholders = defaults.fields.filter { it.placeholder }.map { it.key }
        assertEquals(
            listOf("plan_to_age", "expected_return_percent", "volatility_percent", "inflation_percent"),
            placeholders,
        )
        assertNull(field("current_age").default)
        assertNull(field("other_income_start_age").default)
        assertEquals("95", field("plan_to_age").default)
        assertEquals("6", field("expected_return_percent").default)
        assertEquals("2.5", field("inflation_percent").default)
    }

    @Test
    fun `the boxes start with the placeholders filled in and nothing else`() {
        assertEquals(
            mapOf(
                "plan_to_age" to "95", "expected_return_percent" to "6",
                "volatility_percent" to "12", "inflation_percent" to "2.5",
            ),
            Retirement.startingValues(defaults),
        )
    }

    @Test
    fun `limits are shown from the PC's numbers`() {
        assertEquals("18 to 100", Retirement.limitsText(field("current_age")))
        assertEquals("18 to 110", Retirement.limitsText(field("plan_to_age")))
        assertEquals("0 to 1,000,000,000", Retirement.limitsText(field("savings")))
        assertEquals("-5 to 15", Retirement.limitsText(field("expected_return_percent")))
        assertEquals("0 to 40", Retirement.limitsText(field("volatility_percent")))
        assertEquals("years", Retirement.unitText(field("current_age")))
        assertEquals("money per year", Retirement.unitText(field("yearly_saving")))
    }

    @Test
    fun `a form that is not a form is null and a missing extra field is fine`() {
        assertNull(Retirement.parseDefaults(obj("""{"ok":true}""")))
        assertNull(Retirement.parseDefaults(obj("""{"available":false,"fields":[]}""")))
        val bare = Retirement.parseDefaults(
            obj("""{"fields":[{"key":"savings","kind":"money","min":0,"max":5,"surprise":1}]}"""),
        )
        assertNotNull(bare)
        assertEquals(Retirement.TITLE, bare!!.title)
        assertEquals(Retirement.DISCLAIMER, bare.disclaimer)
        assertEquals("savings", bare.fields[0].label)
        assertFalse(bare.fields[0].required)
    }

    // ------------------------------------------------------- request body ---

    @Test
    fun `the request body carries the typed boxes as typed and leaves blanks out`() {
        val body = obj(Retirement.requestBody(typed + mapOf("plan_to_age" to " 95 ", "other_income" to "  ")))
        assertEquals("40", body["current_age"]!!.toString().trim('"'))
        assertEquals("100,000", body["savings"]!!.toString().trim('"'))
        assertEquals("95", body["plan_to_age"]!!.toString().trim('"'))
        assertFalse(body.containsKey("other_income"))
        assertFalse(body.containsKey("inflation_percent"))
    }

    @Test
    fun `only the eleven known keys can be sent`() {
        val body = obj(Retirement.requestBody(typed + mapOf("token" to "x", "note" to "y")))
        assertTrue(body.keys.all { it in Retirement.KEYS })
        assertEquals("{}", Retirement.requestBody(emptyMap()))
    }

    // ---------------------------------------------------- local bounds mirror ---

    @Test
    fun `a valid form has no slips`() {
        assertTrue(Retirement.check(defaults, typed + Retirement.startingValues(defaults)).isEmpty())
        // Commas, a percent sign and a leading plus are what the PC accepts too.
        assertTrue(
            Retirement.check(
                defaults,
                typed + mapOf("savings" to "1,250,000", "expected_return_percent" to "6.5%", "inflation_percent" to "+2"),
            ).isEmpty(),
        )
    }

    @Test
    fun `an empty required box asks in the PC's words`() {
        val slips = Retirement.check(defaults, emptyMap())
        assertEquals("Please type in \"Your age now\". I will not guess it.", slips["current_age"])
        assertEquals(
            "Please type in \"You spend each year in retirement\". I will not guess it.",
            slips["yearly_spending"],
        )
        // Optional boxes are never asked for.
        assertFalse(slips.containsKey("other_income"))
        assertFalse(slips.containsKey("plan_to_age"))
        // Zero is a real answer, not a missing one.
        assertTrue(Retirement.check(defaults, typed + mapOf("savings" to "0", "yearly_saving" to "0")).isEmpty())
    }

    @Test
    fun `numbers outside the limits use the PC's sentences`() {
        assertEquals(
            "Your age now must be a whole number from 18 to 100.",
            Retirement.problemFor(field("current_age"), "17"),
        )
        assertEquals(
            "Your age now must be a whole number from 18 to 100.",
            Retirement.problemFor(field("current_age"), "40.5"),
        )
        assertEquals(
            "Your age now must be a whole number from 18 to 100.",
            Retirement.problemFor(field("current_age"), "forty"),
        )
        assertEquals(
            "Savings you have now must be an amount from 0 to 1,000,000,000.",
            Retirement.problemFor(field("savings"), "1,000,000,001"),
        )
        assertEquals(
            "Savings you have now cannot be negative.",
            Retirement.problemFor(field("savings"), "-5"),
        )
        assertEquals(
            "Expected yearly return before inflation must be a number from -5 to 15.",
            Retirement.problemFor(field("expected_return_percent"), "15.1"),
        )
        assertEquals(
            "How much yearly returns swing must be a number from 0 to 40.",
            Retirement.problemFor(field("volatility_percent"), "-1"),
        )
        assertNull(Retirement.problemFor(field("expected_return_percent"), "-5"))
        assertNull(Retirement.problemFor(field("volatility_percent"), "40%"))
        assertNull(Retirement.problemFor(field("savings"), "1000000000"))
    }

    @Test
    fun `a money style the app cannot judge is left to the PC`() {
        assertNull(Retirement.problemFor(field("savings"), "12k"))
        assertNull(Retirement.problemFor(field("savings"), "1 250 000"))
    }

    @Test
    fun `the message never repeats what was typed`() {
        for (t in listOf("999999", "abc", "-77", "12.34.56")) {
            for (f in defaults.fields) {
                val m = Retirement.problemFor(f, t) ?: continue
                assertFalse("$t leaked into: $m", m.contains(t))
            }
        }
    }

    @Test
    fun `the plan-to age must be after both ages and within the years limit`() {
        val early = Retirement.check(defaults, typed + mapOf("plan_to_age" to "65"))
        assertEquals(
            "The age to plan the money to must be after the age you stop working (and after your age now).",
            early["plan_to_age"],
        )
        val already = Retirement.check(defaults, typed + mapOf("current_age" to "70", "retirement_age" to "60", "plan_to_age" to "70"))
        assertNotNull(already["plan_to_age"])
        val far = Retirement.check(defaults, typed + mapOf("current_age" to "18", "retirement_age" to "60", "plan_to_age" to "110"))
        assertEquals("That is more than 90 years from your age now. Pick a nearer age.", far["plan_to_age"])
        // Exactly 90 years is allowed.
        assertNull(Retirement.check(defaults, typed + mapOf("current_age" to "20", "retirement_age" to "60", "plan_to_age" to "110"))["plan_to_age"])
        // The default 95 is used when the box is empty.
        assertNotNull(Retirement.check(defaults, typed + mapOf("retirement_age" to "96", "plan_to_age" to ""))["plan_to_age"])
    }

    // ------------------------------------------------------------ results ---

    /** The PC's own `result` object for the mixed case, to compare what the app read against. */
    private fun raw(json: String): JsonObject = obj(json).getValue("result").jsonObject

    private fun JsonObject.str(key: String) = getValue(key).jsonPrimitive.content
    private fun JsonObject.sub(key: String) = getValue(key).jsonObject

    @Test
    fun `the contract's example is read as sent`() {
        val r = result(MIXED_JSON)
        val want = raw(MIXED_JSON)
        assertEquals("mixed", r.state)
        assertNull(r.reason)
        assertEquals(want.sub("share").str("label"), r.share!!.label)
        assertEquals(want.sub("share").getValue("per_100").jsonPrimitive.int, r.share!!.per100)
        assertTrue(r.share!!.label.matches(Regex("about \\d+ of 100")))
        assertFalse(r.share!!.all)
        assertFalse(r.share!!.none)
        assertEquals(want.sub("bands").sub("lower").str("label"), r.lower!!.share.label)
        assertEquals(want.sub("bands").sub("higher").str("label"), r.higher!!.share.label)
        assertEquals(-1.0, r.lower!!.points, 0.0)
        assertEquals(1.0, r.higher!!.points, 0.0)
        assertEquals(95, r.endBalance!!.age)
        val text = want.sub("end_balance").sub("text")
        assertEquals(text.str("p10"), r.endBalance!!.p10)
        assertEquals(text.str("p50"), r.endBalance!!.p50)
        assertEquals(text.str("p90"), r.endBalance!!.p90)
        assertEquals(want.sub("poor_case").getValue("lasts").jsonPrimitive.content == "true", r.poorCase!!.lasts)
        assertEquals(
            want.getValue("runs_out_between").jsonArray.map { it.jsonPrimitive.int },
            r.runsOutBetween!!.toList(),
        )
        assertEquals(want.getValue("middle_lasts_to").jsonPrimitive.int, r.middleLastsTo)
        // Every sentence exactly as sent, in order.
        assertEquals(want.getValue("summary").jsonArray.map { it.jsonPrimitive.content }, r.summary)
        assertTrue(r.summary[0].startsWith("In ${r.share!!.label} simulated futures your money lasts to age 95."))
        assertEquals(Retirement.DISCLAIMER, r.disclaimer)
        assertEquals(defaults.placeholderNote, r.placeholderNote)
        assertEquals(defaults.todaysMoney, r.todaysMoney)
    }

    @Test
    fun `the placeholders are labelled as placeholders for a mix of stocks and bonds`() {
        assertTrue(defaults.placeholderNote.contains("placeholders for a mix of stocks and bonds, not a forecast"))
        for (key in listOf("expected_return_percent", "volatility_percent")) {
            assertTrue(field(key).help.contains("placeholder for a mix of stocks and bonds, not a forecast"))
        }
        assertEquals("6%", result(MIXED_JSON).used.first { it.key == "expected_return_percent" }.value)
    }

    @Test
    fun `an empty box with a default that does not start filled shows it as a hint`() {
        assertEquals("0", Retirement.hintFor(field("other_income")))
        assertNull(Retirement.hintFor(field("expected_return_percent")))
        assertNull(Retirement.hintFor(field("current_age")))
        assertNull(Retirement.hintFor(field("other_income_start_age")))
    }

    @Test
    fun `the stale-link line is the desktop's`() {
        assertEquals("Waiting for the link to catch up. Nothing can be sent until it does.", Retirement.STALE_LINE)
    }

    @Test
    fun `the local check leaves to the PC what only it can judge`() {
        val f = field("expected_return_percent")
        // ".5", "5." and "7%%" are read by the PC, so the phone must not refuse them.
        for (ok in listOf(".5", "5.", "+.5%", "7%%", "\uFF17")) {
            assertNull("\"$ok\" was refused", Retirement.problemFor(f, ok))
        }
        for (bad in listOf(".", "5.5.5", "1e1", "abc")) {
            assertNotNull("\"$bad\" was accepted", Retirement.problemFor(f, bad))
        }
    }

    @Test
    fun `what I used keeps the assumed marks`() {
        val r = result(MIXED_JSON)
        assertEquals(11, r.used.size)
        val assumed = r.used.filter { it.assumed }.map { it.key }
        assertEquals(listOf("plan_to_age", "expected_return_percent", "volatility_percent", "inflation_percent"), assumed)
        assertEquals("100,000", r.used.first { it.key == "savings" }.value)
        assertEquals("Plan the money to age, 95, assumed", Retirement.usedReading(r.used.first { it.key == "plan_to_age" }))
        assertEquals("Your age now, 40", Retirement.usedReading(r.used.first { it.key == "current_age" }))
    }

    @Test
    fun `the spoken summary is the sentences then the disclaimer`() {
        val r = result(MIXED_JSON)
        assertEquals(r.summary.joinToString(" ") + " " + Retirement.DISCLAIMER, Retirement.spoken(r))
    }

    @Test
    fun `never runs out has no run-out age`() {
        val r = result(NEVER_JSON)
        assertEquals("never_runs_out", r.state)
        assertEquals("more than 99 of 100", r.share!!.label)
        assertTrue(r.share!!.all)
        assertNull(r.runsOutBetween)
        assertEquals(true, r.poorCase!!.lasts)
        assertNull(r.poorCase!!.age)
        assertTrue(r.summary[0].startsWith("In all 10,000 simulated futures your money lasts to age 95."))
    }

    @Test
    fun `always runs out reads fewer than 1 of 100`() {
        val r = result(ALWAYS_JSON)
        assertEquals("always_runs_out", r.state)
        assertEquals("fewer than 1 of 100", r.share!!.label)
        assertTrue(r.share!!.none)
        assertEquals(0, r.share!!.per100)
    }

    @Test
    fun `not enough to say has no share, bands or balances`() {
        val r = result(NOT_ENOUGH_JSON)
        assertEquals("not_enough_to_say", r.state)
        assertEquals("no_spending", r.reason)
        assertNull(r.share)
        assertNull(r.lower)
        assertNull(r.higher)
        assertNull(r.endBalance)
        assertNull(r.poorCase)
        assertNull(r.runsOutBetween)
        assertNull(r.middleLastsTo)
        assertEquals(1, r.summary.size)
        assertTrue(Retirement.shareRows(r).isEmpty())
        assertTrue(Retirement.balanceRows(r).isEmpty())
        assertNull(Retirement.balanceHeading(r))
        // The disclaimer still comes with it.
        assertEquals(Retirement.DISCLAIMER, r.disclaimer)
    }

    @Test
    fun `an unknown state still shows the sentences and the disclaimer`() {
        val r = result("""{"result":{"state":"something_new","summary":["A new sentence."],"extra":{"a":1}}}""")
        assertEquals("something_new", r.state)
        assertEquals(listOf("A new sentence."), r.summary)
        assertEquals(Retirement.DISCLAIMER, r.disclaimer)
    }

    @Test
    fun `bars and balances come only from the PC's numbers`() {
        val r = result(MIXED_JSON)
        val want = raw(MIXED_JSON)
        val rows = Retirement.shareRows(r)
        assertEquals(listOf("Returns 1 point lower", "As typed", "Returns 1 point higher"), rows.map { it.first })
        assertEquals(
            listOf(
                want.sub("bands").sub("lower").getValue("per_100").jsonPrimitive.int,
                want.sub("share").getValue("per_100").jsonPrimitive.int,
                want.sub("bands").sub("higher").getValue("per_100").jsonPrimitive.int,
            ),
            rows.map { it.second.per100 },
        )
        assertEquals("Money left at age 95", Retirement.balanceHeading(r))
        val text = want.sub("end_balance").sub("text")
        assertEquals(
            listOf(
                "Poor case (1 in 10)" to text.str("p10"),
                "Middle case" to text.str("p50"),
                "Good case (1 in 10)" to text.str("p90"),
            ),
            Retirement.balanceRows(r),
        )
        assertEquals("1 point", Retirement.pointsText(-1.0))
        assertEquals("2 points", Retirement.pointsText(2.0))
    }

    // ------------------------------------------------------------- errors ---

    @Test
    fun `a field error is pinned to its box with the PC's message`() {
        val out = Retirement.classify(
            Retirement.Reply(
                400,
                obj("""{"ok":false,"error":"missing","field":"savings","message":"Please type in \"Savings you have now\". I will not guess it."}"""),
            ),
        )
        assertEquals(
            Retirement.Outcome.FieldProblem("savings", "Please type in \"Savings you have now\". I will not guess it."),
            out,
        )
    }

    @Test
    fun `every error code in the table maps to the right place`() {
        val codes = mapOf(
            "missing" to "current_age", "bad_number" to "savings", "negative" to "savings",
            "out_of_range" to "current_age", "plan_not_after" to "plan_to_age",
            "too_many_years" to "plan_to_age",
        )
        for ((code, key) in codes) {
            val out = Retirement.classify(
                Retirement.Reply(400, obj("""{"ok":false,"error":"$code","field":"$key","message":"M"}""")),
            )
            assertEquals(code, Retirement.Outcome.FieldProblem(key, "M"), out)
        }
    }

    @Test
    fun `unknown_field and bad_request are general problems, not a box's`() {
        assertEquals(
            Retirement.Outcome.Problem("That is not one of the what-if's fields."),
            Retirement.classify(
                Retirement.Reply(
                    400,
                    obj("""{"ok":false,"error":"unknown_field","field":"token","message":"That is not one of the what-if's fields."}"""),
                ),
            ),
        )
        assertEquals(
            Retirement.Outcome.Problem("Send the numbers as a set of named fields."),
            Retirement.classify(
                Retirement.Reply(
                    400,
                    obj("""{"ok":false,"error":"bad_request","field":"","message":"Send the numbers as a set of named fields."}"""),
                ),
            ),
        )
    }

    @Test
    fun `busy is retried by the caller and too slow is a plain problem`() {
        val busy = Retirement.classify(Retirement.Reply(429, obj("""{"error":"busy","message":"${Retirement.BUSY}"}""")))
        assertEquals(Retirement.Outcome.Problem(Retirement.BUSY, busy = true), busy)
        val busyNoBody = Retirement.classify(Retirement.Reply(429, null))
        assertEquals(Retirement.Outcome.Problem(Retirement.BUSY, busy = true), busyNoBody)
        val slow = Retirement.classify(Retirement.Reply(503, obj("""{"error":"too_slow","message":"${Retirement.TOO_SLOW}"}""")))
        assertEquals(Retirement.Outcome.Problem(Retirement.TOO_SLOW), slow)
        assertEquals(Retirement.Outcome.Problem(Retirement.TOO_SLOW), Retirement.classify(Retirement.Reply(503, obj("""{"error":"too_slow"}"""))))
    }

    @Test
    fun `a PC without the route reads as missing`() {
        assertEquals(Retirement.Outcome.Missing, Retirement.classify(Retirement.Reply(404, obj("""{"ok":false,"error":"not_found"}"""))))
        assertEquals(Retirement.Outcome.Missing, Retirement.classify(Retirement.Reply(503, null)))
        assertTrue(Retirement.missing(ApiError.NotFound))
        assertTrue(Retirement.missing(ApiError.NotAvailable))
        assertFalse(Retirement.missing(ApiError.BadToken))
    }

    @Test
    fun `an answer that is not a result is unreadable, not a crash`() {
        assertEquals(Retirement.Outcome.Problem(Retirement.UNREADABLE), Retirement.classify(Retirement.Reply(200, null)))
        assertEquals(Retirement.Outcome.Problem(Retirement.UNREADABLE), Retirement.classify(Retirement.Reply(200, obj("""{"ok":true,"result":{"state":"mixed"}}"""))))
        assertTrue(Retirement.classify(Retirement.Reply(500, null)) is Retirement.Outcome.Problem)
    }

    // ------------------------------------------------------------- hidden ---

    @Test
    fun `hidden lists or a locked app hide the form and the answer`() {
        assertTrue(Retirement.hiddenNow(hideLists = true, locked = false))
        assertTrue(Retirement.hiddenNow(hideLists = false, locked = true))
        assertFalse(Retirement.hiddenNow(hideLists = false, locked = false))
    }

    // ------------------------------------------------- what the app never does ---

    @Test
    fun `nothing the app writes says streak, praise or guilt`() {
        val ours = listOf(
            Retirement.TITLE, Retirement.RUN, Retirement.WORKING, Retirement.ASSUMED, Retirement.USED_HEADING,
            Retirement.HIDDEN, Retirement.MISSING, Retirement.UNREADABLE, Retirement.READING, Retirement.GENERIC,
            Retirement.CHECK_BOXES,
        ) + Retirement.shareRows(result(MIXED_JSON)).map { it.first } +
            Retirement.balanceRows(result(MIXED_JSON)).map { it.first } +
            listOfNotNull(Retirement.balanceHeading(result(MIXED_JSON)))
        val banned = listOf(
            "streak", "congrat", "well done", "great", "keep it up", "on track", "off track", "behind",
            "fail", "worry", "sorry", "warning", "days in a row", "don't give up",
        )
        for (w in ours) for (b in banned) {
            assertFalse("\"$w\" says \"$b\"", w.lowercase().contains(b))
        }
    }

    @Test
    fun `the screen and the parser keep nothing anywhere`() {
        val dir = "jarvis-client/app/src/main/java/com/jarvis/client/"
        for (rel in listOf("ui/screens/RetirementPlate.kt", "net/Retirement.kt")) {
            val src = repoFile(dir + rel).readText()
            // Comments may name what is refused; only code is scanned.
            val code = src.lineSequence().filterNot {
                val t = it.trim()
                t.startsWith("*") || t.startsWith("/*") || t.startsWith("//")
            }.joinToString("\n")
            for (bad in listOf(
                "rememberSaveable", "SharedPreferences", "DataStore", "openFileOutput", "File(", "Log.", "println(",
                "ClipboardManager", "LocalClipboard", "SelectionContainer", "Intent.ACTION_SEND", "TextToSpeech",
            )) {
                assertFalse("$rel uses $bad", code.contains(bad))
            }
        }
    }

    @Test
    fun `the plate is reachable from Brain by its literal key`() {
        val src = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt").readText()
        assertTrue(src.contains("item(key = \"retirement\")"))
        assertTrue(src.contains("RetirementSection("))
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
}

// What the real backend answered, from contract/retirement-cases.json (written by
// tools/gen_retirement_cases.py; the desktop's tests read the same file). Nothing in
// this test file holds a copy of it.
private val CASES: JsonObject = JarvisJson.parseToJsonElement(
    requireNotNull(RetirementTest::class.java.classLoader?.getResource("contract/retirement-cases.json")) {
        "contract/retirement-cases.json is missing - run tools/gen_retirement_cases.py"
    }.readText(),
).jsonObject

private fun caseBody(name: String): String = CASES.getValue(name).jsonObject.getValue("body").toString()

private val DEFAULTS_JSON = caseBody("defaults")
private val MIXED_JSON = caseBody("mixed")
private val NEVER_JSON = caseBody("never_runs_out")
private val ALWAYS_JSON = caseBody("always_runs_out")
private val NOT_ENOUGH_JSON = caseBody("not_enough_to_say")
