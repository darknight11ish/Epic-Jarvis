package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.WorkSetups
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's "Work setups" screen, read from what the PC REALLY answers.
 *
 * `contract/work-setups-cases.json` is the real `GET /api/work` answer
 * (`jarvis_work.status()`) and the real answers of the three POSTs, written by
 * `tools/gen_work_cases.py` - the same shape `backend/test_work.py` holds the
 * Python half to. Nothing here is a shape typed to suit this client.
 *
 * The two checks that matter most, and are named so they cannot be skimmed:
 *
 *  - `a recommendation never switches a model on its own` - the offer the PC
 *    sends is a suggestion with a step the OWNER has to ask for, and the answer
 *    says outright that nothing was switched;
 *  - `the explanation is on screen before the choice is applied` - the words a
 *    person reads before pressing anything (what it is for, what it costs, what
 *    it is worse at) are all present in the PC's answer for every setup, and
 *    the step that changes a model is only ever offered for the one setup that
 *    was chosen.
 */
class WorkSetupsContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(
            javaClass.classLoader?.getResource("contract/work-setups-cases.json"),
        ) {
            "contract/work-setups-cases.json is missing - run tools/gen_work_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    private fun status(case: String = "today"): WorkSetups.Status =
        requireNotNull(WorkSetups.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun offer(case: String): WorkSetups.Offer =
        WorkSetups.parseOffer(cases[case]!!.jsonObject["answer"]!!.jsonObject)

    private fun post(case: String): ApiResult<JsonObject> {
        val c = cases[case]!!.jsonObject
        return WorkSetups.classifyPost(c["status"]!!.jsonPrimitive.int, c["body"]!!.jsonObject)
    }

    @Test
    fun `every setup case is read, in the PC's order`() {
        for (name in listOf("today", "fresh_pc", "chosen_coding", "chosen_admin_already_running",
            "ollama_unreachable")) {
            val s = status(name)
            assertEquals(name, WorkSetups.IDS, s.setups.map { it.id })
            assertTrue(name, s.found.isNotBlank())
            assertTrue(name, s.howTo.isNotBlank())
        }
    }

    @Test
    fun `the explanation is on screen before the choice is applied`() {
        // Every setup the PC sends must explain itself in full. These are the
        // strings the screen draws, and a setup missing one of them would be a
        // setup the owner could choose without being told what it does.
        val s = status()
        for (setup in s.setups) {
            val where = setup.id
            assertTrue("$where: what it is for", setup.what.length > 40)
            assertTrue("$where: what it costs", setup.cost.length > 40)
            assertTrue("$where: what it is worse at", setup.worse.length > 30)
            assertTrue("$where: why this one", setup.why.length > 40)
            assertTrue("$where: whether both cards work", setup.uses.isNotBlank())
            assertTrue("$where: the models and cards", setup.places.size == 2)
            assertTrue("$where: the one-line summary", setup.summary.contains(setup.mainModel))
            assertTrue("$where: a step is described", setup.step.words.isNotBlank())
            assertTrue("$where: the switch card's own words", setup.cardWords.isNotBlank())
            assertEquals("$where: both cards named", 2, setup.places.map { it.card }.toSet().size)
            assertTrue("$where: no place spills to the processor",
                setup.places.none { it.spills })
            assertTrue("$where: every place has a speed", setup.places.all { it.speed != null })
            assertTrue("$where: every place says what it is doing",
                setup.places.all { it.words.isNotBlank() })
        }
        // ... and the four kinds of work the owner asked about are all here.
        val work = s.setups.joinToString(" ") { it.work + " " + it.name }.lowercase()
        assertTrue(work, work.contains("coding"))
        assertTrue(work, work.contains("admin") || work.contains("paperwork"))
        assertTrue(work, work.contains("long"))
        assertTrue(work, work.contains("everyday") || work.contains("quick"))
    }

    @Test
    fun `the awkward facts are on the label, not in a tooltip`() {
        val s = status()
        val specialist = requireNotNull(s.setup("specialist"))
        assertTrue(specialist.cost, specialist.cost.contains("8/10"))
        assertTrue(specialist.worse, specialist.worse.contains("8/10"))
        assertTrue(specialist.cost, specialist.cost.contains("10/10"))
        val long = requireNotNull(s.setup("long"))
        assertTrue(long.worse, long.worse.contains("WRONG"))
        val admin = requireNotNull(s.setup("admin"))
        assertTrue(admin.worse, admin.worse.contains("not a measurement"))
        val coding = requireNotNull(s.setup("coding"))
        assertTrue(coding.thinking, coding.thinking.contains("EMPTY"))
        assertTrue(coding.worse.plus(coding.why).contains("196,608"))
    }

    @Test
    fun `a recommendation never switches a model on its own`() {
        // The offer the PC sends is a suggestion. It says so, it carries a step
        // the OWNER has to ask for, and the answer says outright that no model
        // was switched. Nothing in this client may act on it: the only way a
        // model changes is [WorkSetups.stepRequest] on a CHOSEN setup, posted
        // through the existing switch card.
        val o = offer("words_android_app")
        assertTrue(o.offered)
        assertEquals("coding", o.id)
        assertFalse("an offer must never claim a model was switched", o.switched)
        assertTrue(o.words, o.words.contains("Nothing has changed"))
        val step = requireNotNull(o.step)
        assertEquals("switch", step.kind)
        assertEquals(WorkSetups.SWITCH_PATH, step.route)
        assertEquals("qwen3.5:9b", step.body!!["ref"]!!.jsonPrimitive.content)

        // ... and the sentence a person reads never claims it happened.
        val words = o.words.lowercase()
        for (claim in listOf("switched to", "i have switched", "now using", "i loaded")) {
            assertFalse("the offer says: $words", words.contains(claim))
        }

        // Every offer case the golden file holds obeys the same rule.
        for (name in cases.keys.filter { it.startsWith("words_") }) {
            val each = offer(name)
            assertTrue(name, each.offered)
            assertFalse(name, each.switched)
            assertTrue(name, each.words.contains("Nothing has changed"))
        }
    }

    @Test
    fun `an offer is made for work, and never for a mention or a crisis`() {
        val wants = mapOf(
            "words_android_app" to "coding",
            "words_coding_bug" to "coding",
            "words_coding_gradle" to "coding",
            "words_admin_taxes" to "admin",
            "words_admin_letter" to "admin",
            "words_admin_inbox" to "admin",
            "words_long_document" to "long",
            "words_long_book" to "long",
            "words_specialist" to "specialist",
            "words_everyday" to "everyday",
        )
        for ((name, want) in wants) {
            val o = offer(name)
            assertTrue(name, o.offered)
            assertEquals(name, want, o.id)
            assertTrue(name, o.words.isNotBlank() && o.name!!.isNotBlank())
        }
        // The half that matters more: the turns that must offer NOTHING.
        for (name in cases.keys.filter { it.startsWith("none_") }) {
            assertFalse(name, offer(name).offered)
            assertNull(name, offer(name).id)
        }
    }

    @Test
    fun `the step is only offered for a setup that was chosen`() {
        val none = status("today")
        assertNull("no setup is chosen", none.chosen)
        for (setup in none.setups) {
            val ask = WorkSetups.stepRequest(none, setup)
            assertTrue("nothing may be asked for before a choice",
                ask is WorkSetups.StepAsk.No)
            assertTrue((ask as WorkSetups.StepAsk.No).reason.contains("not the setup you chose"))
        }
        val chosen = status("chosen_coding")
        assertEquals("coding", chosen.chosen)
        val coding = requireNotNull(chosen.setup("coding"))
        val ask = WorkSetups.stepRequest(chosen, coding)
        assertTrue(ask is WorkSetups.StepAsk.Post)
        assertEquals(WorkSetups.SWITCH_PATH, (ask as WorkSetups.StepAsk.Post).route)
        // ... and every OTHER setup in the same answer is still refused, even
        // though the PC sends each one a step. Two setups' steps can look
        // identical; only the chosen one may ever be posted.
        for (setup in chosen.setups.filter { it.id != "coding" }) {
            assertTrue(setup.id, WorkSetups.stepRequest(chosen, setup) is WorkSetups.StepAsk.No)
        }
    }

    @Test
    fun `a setup whose model is already running needs no step at all`() {
        val s = status("chosen_admin_already_running")
        val admin = requireNotNull(s.setup("admin"))
        assertEquals("qwen3.5:9b", s.currentModel)
        assertEquals("none", admin.step.kind)
        assertEquals(true, admin.step.done)
        val ask = WorkSetups.stepRequest(s, admin)
        assertTrue(ask is WorkSetups.StepAsk.No)
        assertTrue((ask as WorkSetups.StepAsk.No).reason.contains("already"))
    }

    @Test
    fun `a model that is not downloaded is never a download button`() {
        val fresh = status("fresh_pc")
        val specialist = requireNotNull(fresh.setup("specialist"))
        assertEquals("missing", specialist.ready)
        assertTrue(specialist.readyWords, specialist.readyWords.contains("ornith:9b"))
        assertTrue(specialist.readyWords, specialist.readyWords.contains("card"))
        assertEquals("missing", specialist.step.kind)
        assertNull("no route to post a download to", specialist.step.route)
        val ask = WorkSetups.stepRequest(fresh.copy(chosen = "specialist"), specialist)
        assertTrue(ask is WorkSetups.StepAsk.No)
        // ... and the only route a step may ever name is the switch.
        assertEquals(listOf(WorkSetups.SWITCH_PATH), WorkSetups.STEP_ROUTES)
    }

    @Test
    fun `an Ollama that cannot be reached is not an empty PC`() {
        val s = status("ollama_unreachable")
        assertFalse(s.ollamaSeen)
        assertNull(s.currentModel)
        for (setup in s.setups) {
            assertEquals("unknown", setup.ready)
            assertEquals(WorkSetups.COULD_NOT_ASK, WorkSetups.readyLine(setup))
            assertFalse("must not claim a download is needed",
                setup.readyWords.contains("not downloaded yet"))
        }
    }

    @Test
    fun `choosing answers in words and never claims a change`() {
        val result = post("post_choose_coding")
        assertTrue(result is ApiResult.Ok)
        val body = (result as ApiResult.Ok).value
        assertEquals("coding", body["chosen"]!!.jsonPrimitive.content)
        val message = body["message"]!!.jsonPrimitive.content
        assertTrue(message, message.contains("Nothing has changed"))
        val line = WorkSetups.replyLine(result)
        assertEquals(message.replaceFirstChar { it.uppercase() }.trimEnd('.') + ".", line)
        // The setup's own words come back with it, so the screen can draw the
        // explanation from the same answer that recorded the choice.
        val setup = body["setup"]!!.jsonObject
        assertTrue(setup["what"]!!.jsonPrimitive.content.isNotBlank())
        assertTrue(setup["cost"]!!.jsonPrimitive.content.isNotBlank())
        assertTrue(setup["worse"]!!.jsonPrimitive.content.isNotBlank())
    }

    @Test
    fun `forgetting a setup, and an unknown setup, both answer in plain words`() {
        val none = post("post_choose_none")
        assertTrue(none is ApiResult.Ok)
        assertTrue((none as ApiResult.Ok).value["chosen"] is JsonNull)
        val bad = post("post_choose_unknown")
        assertTrue("a 400's sentence is shown word for word", bad is ApiResult.Ok)
        val line = WorkSetups.replyLine(bad)
        assertTrue(line, line.contains("no work setup called"))
        assertTrue(line, line.contains("everyday"))
    }

    @Test
    fun `a recommend with no words is refused, and the refusal is shown`() {
        val bad = post("post_recommend_no_words")
        assertTrue(bad is ApiResult.Ok)
        assertTrue(WorkSetups.replyLine(bad).contains("words"))
    }

    @Test
    fun `the bodies this app builds are the shape the PC wants`() {
        assertEquals("""{"setup":"coding"}""", WorkSetups.chooseBody("coding"))
        assertEquals("""{"setup":null}""", WorkSetups.chooseBody(null))
        assertEquals("""{"words":"build an app"}""", WorkSetups.recommendBody("build an app"))
        // A quote inside the owner's own words must not break the JSON.
        val tricky = WorkSetups.recommendBody("""he said "hello" to me""")
        val parsed = JarvisJson.parseToJsonElement(tricky) as JsonObject
        assertEquals("""he said "hello" to me""", parsed["words"]!!.jsonPrimitive.content)
    }

    @Test
    fun `what a step may be asked for is checked here, not trusted`() {
        val s = status("chosen_coding")
        val coding = requireNotNull(s.setup("coding"))
        // A step naming a route this app does not know is refused.
        val bad = coding.copy(
            step = coding.step.copy(kind = "switch", route = "/api/models/install",
                body = buildJsonObject { put("ref", "x") }),
        )
        assertTrue(WorkSetups.stepRequest(s, bad) is WorkSetups.StepAsk.No)
        // A switch with no model named is refused too.
        val nameless = coding.copy(
            step = coding.step.copy(kind = "switch", route = WorkSetups.SWITCH_PATH,
                body = JsonObject(emptyMap())),
        )
        assertTrue(WorkSetups.stepRequest(s, nameless) is WorkSetups.StepAsk.No)
        // ... and a body that is not an object at all.
        val noBody = coding.copy(
            step = coding.step.copy(kind = "switch", route = WorkSetups.SWITCH_PATH, body = null),
        )
        assertTrue(WorkSetups.stepRequest(s, noBody) is WorkSetups.StepAsk.No)
        // ... and a setup nobody chose, however complete its step looks.
        val other = requireNotNull(s.setup("everyday"))
        assertTrue(WorkSetups.stepRequest(s, other) is WorkSetups.StepAsk.No)
    }

    @Test
    fun `the words a person reads are the PC's own, not rebuilt here`() {
        val s = status()
        for (setup in s.setups) {
            assertEquals(setup.name, WorkSetups.setupLine(setup).substringBefore(" - "))
            assertTrue(WorkSetups.headLine(setup).contains(WorkSetups.readyLine(setup)))
            assertTrue(WorkSetups.headLine(setup).contains(setup.what))
            for (p in setup.places) {
                val line = WorkSetups.placeLine(p)
                assertTrue(line, line.contains(p.model))
                assertTrue(line, line.contains(p.card))
            }
        }
        // The five names, word for word - the ones the design note promises.
        assertEquals(
            listOf(
                "Everyday quick answers",
                "Building an Android app",
                "Admin and paperwork",
                "Long conversations and big documents",
                "Careful coding with a coding specialist",
            ),
            s.setups.map { it.name },
        )
    }

    @Test
    fun `asking reads as waiting for a while, so one tap is one card`() {
        val s = status("chosen_coding")
        val step = requireNotNull(s.setup("coding")).step
        val now = 1_000_000L
        assertEquals(WorkSetups.WAITING, WorkSetups.stepWords(step, now - 1_000L, now))
        assertEquals(step.words, WorkSetups.stepWords(step, now - WorkSetups.ASKED_FOR_MS, now))
        assertEquals(step.words, WorkSetups.stepWords(step, null, now))
    }

    @Test
    fun `a read that is not the right shape is a sentence, never a crash`() {
        assertNull(WorkSetups.parse(JsonObject(emptyMap())))
        assertNull(WorkSetups.parse(buildJsonObject { put("setups", JsonPrimitive("no")) }))
        val empty = WorkSetups.parse(buildJsonObject {
            put("setups", kotlinx.serialization.json.JsonArray(emptyList()))
        })
        assertNotNull(empty)
        assertEquals(0, empty!!.setups.size)
    }

    @Test
    fun `an older backend, and a missing module, say what to do`() {
        assertTrue(
            WorkSetups.readLine(WorkSetups.Read.OlderBackend)!!.contains("apply-patches.ps1"),
        )
        assertTrue(WorkSetups.readLine(WorkSetups.Read.NotInstalled)!!.contains("apply-patches.ps1"))
        assertTrue(WorkSetups.readLine(WorkSetups.Read.NotAsked)!!.contains("Asking"))
        assertNull(WorkSetups.readLine(WorkSetups.Read.Loaded(status())))
    }

    @Test
    fun `no answer in the golden file carries a token`() {
        val all = cases.toString()
        for (needle in listOf("X-Jarvis-Token", "Bearer ", "\"token\":", "pairing")) {
            assertFalse(needle, all.contains(needle))
        }
        assertTrue(status().notACatalogue.contains("no list here of models"))
    }
}
