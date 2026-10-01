package com.jarvis.client

import com.jarvis.client.net.Topics
import kotlinx.serialization.json.Json
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

/**
 * Topic controls on the phone (docs/TOPIC-CONTROLS-DESIGN.md, "Slice
 * contract (frozen)"; docs/JARVIS-API.md section 107). Pure JVM: no Android.
 *
 * The shared fixture `contract/topics-cases.json` is written by
 * tools/gen_topics_cases.py (byte-identical to the desktop's copy); its
 * words, errors, modes and worked cases are held equal to this app's here.
 * The palette check needs [com.jarvis.client.net.ChatTags], so it lives in
 * TopicsLookTest.
 */
class TopicsTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/topics-cases.json")) {
            "contract/topics-cases.json is missing - run tools/gen_topics_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }

    private fun strMap(key: String): Map<String, String> =
        doc[key]!!.jsonObject.mapValues { it.value.jsonPrimitive.content }

    private fun obj(json: String): JsonObject = Json.parseToJsonElement(json).jsonObject

    // ------------------------------------------------------ the fixture ---

    @Test
    fun `every word, error and ending sentence is the fixture's`() {
        assertEquals(strMap("words"), Topics.WORDS)
        assertEquals(strMap("errors"), Topics.ERRORS)
        assertEquals(strMap("last_words"), Topics.LAST_WORDS)
        assertEquals(doc["gate_failed"]!!.jsonPrimitive.content, Topics.GATE_FAILED)
    }

    @Test
    fun `the four modes, in order, with their sentences`() {
        val fixture = doc["modes"]!!.jsonArray.map {
            val o = it.jsonObject
            Triple(o["id"]!!.jsonPrimitive.content, o["name"]!!.jsonPrimitive.content, o["sentence"]!!.jsonPrimitive.content)
        }
        assertEquals(fixture, Topics.MODES.map { Triple(it.id, it.name, it.sentence) })
        assertEquals(listOf("both", "use_only", "learn_only", "off"), Topics.MODES.map { it.id })
    }

    @Test
    fun `limits and icons are the fixture's`() {
        val l = doc["limits"]!!.jsonObject
        assertEquals(l["max_topics"]!!.jsonPrimitive.int, Topics.MAX_TOPICS)
        assertEquals(l["name_max"]!!.jsonPrimitive.int, Topics.NAME_MAX)
        assertEquals(l["batch"]!!.jsonPrimitive.int, Topics.BATCH)
        assertEquals(l["colours"]!!.jsonPrimitive.int, Topics.COLOURS)
        assertEquals(l["unsorted_id"]!!.jsonPrimitive.int, Topics.UNSORTED_ID)
        assertEquals(doc["icons"]!!.jsonArray.map { it.jsonPrimitive.content }, Topics.ICONS)
        assertTrue("heart" in Topics.ICONS && "coin" in Topics.ICONS && "people" in Topics.ICONS)
    }

    @Test
    fun `which changes show the ask-first line - the fixture's mode_cases`() {
        val cases = doc["mode_cases"]!!.jsonArray
        assertTrue(cases.size >= 16)
        for (c in cases) {
            val o = c.jsonObject
            val old = o["old"]!!.jsonPrimitive.content
            val new = o["new"]!!.jsonPrimitive.content
            val priv = o["private"]!!.jsonPrimitive.boolean
            assertEquals("$old -> $new loosens", o["loosens"]!!.jsonPrimitive.boolean, Topics.loosens(old, new))
            assertEquals("$old -> $new private=$priv", o["needs_card"]!!.jsonPrimitive.boolean, Topics.needsCard(old, new, priv))
        }
    }

    @Test
    fun `names are cleaned the way the PC cleans them - name_cases`() {
        for (c in doc["name_cases"]!!.jsonArray) {
            val o = c.jsonObject
            val raw = o["raw"]!!.jsonPrimitive.content
            val clean = (o["clean"] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
            assertEquals("cleanName(\"$raw\")", clean, Topics.cleanName(raw))
        }
    }

    @Test
    fun `screen reader, hidden row and preview lines - the fixture's cases`() {
        for (c in doc["screen_reader_cases"]!!.jsonArray) {
            val o = c.jsonObject
            assertEquals(
                o["expect"]!!.jsonPrimitive.content,
                Topics.screenReader(o["name"]!!.jsonPrimitive.content, o["facts"]!!.jsonPrimitive.int, o["mode"]!!.jsonPrimitive.content),
            )
        }
        for (c in doc["hidden_row_cases"]!!.jsonArray) {
            val o = c.jsonObject
            assertEquals(
                o["expect"]!!.jsonPrimitive.content,
                Topics.hiddenRow(o["index"]!!.jsonPrimitive.int, o["facts"]!!.jsonPrimitive.int, o["mode"]!!.jsonPrimitive.content),
            )
        }
        for (c in doc["preview_cases"]!!.jsonArray) {
            val o = c.jsonObject
            assertEquals(
                o["expect"]!!.jsonPrimitive.content,
                Topics.previewLeftOut(o["name"]!!.jsonPrimitive.content, o["n"]!!.jsonPrimitive.int),
            )
        }
    }

    // --------------------------------------------------------- reading ---

    private val sample = """
        {"ok": true, "unchecked": 3, "facts": 230, "sorted": 212, "model_help": true,
         "backfill": {"done": false, "remaining": 18},
         "limits": {"max_topics": 16, "name_max": 24, "batch": 10, "icons": ["folder", "heart"]},
         "topics": [
           {"id": 3, "name": "Health", "colour": 5, "icon": "heart", "mode": "learn_only", "private": true,
            "ord": 2, "system": false, "facts": 12, "unchecked": 1, "hidden": false, "skipped_week": 0, "extra": 1},
           {"id": 1, "name": "Unsorted", "colour": 6, "icon": "flag", "mode": "both", "system": true, "facts": 20},
           {"id": 2, "name": "Work", "colour": 0, "icon": "briefcase", "mode": "off", "ord": 1, "facts": 41,
            "skipped_week": 3},
           {"name": "no id"},
           {"id": 9}
         ],
         "waiting": {"topic": 3, "kind": "mode"},
         "last": {"outcome": "denied", "why": "x", "at": 1790000100.5, "message": "The card was turned down, so nothing about your topics changed."}}
    """.trimIndent()

    @Test
    fun `the list is read, Unsorted first, then the owner's order`() {
        val v = Topics.view(obj(sample))!!
        assertEquals(listOf(1, 2, 3), v.topics.map { it.id })
        assertEquals(listOf(2, 3), v.own.map { it.id })
        assertEquals(3, v.unchecked)
        assertEquals(230, v.facts)
        assertEquals(18, v.sortingRemaining)
        assertTrue(v.modelHelp)
        assertEquals(Topics.Waiting(3, "mode"), v.waiting)
        assertEquals(listOf("folder", "heart"), v.icons)
        val work = v.byId(2)!!
        assertEquals("off", work.mode)
        assertTrue("hidden is exactly off when the PC did not say", work.hidden)
        assertEquals(3, work.skippedWeek)
        assertTrue(v.byId(3)!!.isPrivate)
        assertTrue(v.byId(1)!!.system)
        assertEquals(41, work.facts)
    }

    @Test
    fun `an odd or old answer degrades instead of crashing`() {
        assertNull(Topics.view(null))
        assertNull(Topics.view(obj("""{"ok": false, "error": "unavailable"}""")))
        assertNull(Topics.view(obj("""{"nothing": 1}""")))
        val bare = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted"}]}"""))!!
        assertEquals("both", bare.topics.single().mode)
        assertEquals(Topics.MAX_TOPICS, bare.maxTopics)
        assertEquals(Topics.ICONS, bare.icons)
        assertNull(bare.waiting)
        assertNull(bare.last)
        assertFalse(bare.modelHelp)
        assertEquals(Topics.UNSORTED_ID, bare.topics.single().id)
        // Duplicate ids are kept once.
        val dup = Topics.view(obj("""{"topics": [{"id": 4, "name": "A"}, {"id": 4, "name": "B"}]}"""))!!
        assertEquals(listOf("A"), dup.topics.map { it.name })
    }

    @Test
    fun `Add a topic is off at the limit of the owner's own topics, Unsorted not counted`() {
        val many = (2..17).joinToString(",") { """{"id": $it, "name": "T$it", "ord": $it}""" }
        val full = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "system": true}, $many]}"""))!!
        assertEquals(16, full.own.size)
        assertFalse(full.canAdd)
        val fifteen = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "system": true}, ${(2..16).joinToString(",") { """{"id": $it, "name": "T$it"}""" }}]}"""))!!
        assertTrue(fifteen.canAdd)
    }

    @Test
    fun `preview, review and hidden read what the PC sends`() {
        val p = Topics.preview(obj("""{"ok": true, "id": 2, "mode": "off", "affected": 12, "pinned": 1, "stops_learning": true, "loosens": false, "needs_card": false, "private": true, "line": "12 things Jarvis knows about Work will be left out of answers.", "card_line": ""}"""))!!
        assertEquals(12, p.affected)
        assertTrue(p.stopsLearning && p.isPrivate)
        assertEquals("12 things Jarvis knows about Work will be left out of answers.", p.line)
        assertEquals("", p.cardLine)
        assertNull(Topics.preview(obj("""{"ok": false}""")))

        val r = Topics.review(obj("""{"ok": true, "facts": [
            {"id": 7, "text": "I like jazz", "saved_at": 1790000000, "topic": 5, "alt": null, "how": "model", "checked": false, "held_back": true},
            {"id": 8, "text": "Standup at ten", "topic": 2, "alt": 4, "how": "rule"},
            {"text": "no id"}], "next": "c9", "total": 38, "batch": 10}"""))!!
        assertEquals(2, r.facts.size)
        assertTrue(r.facts[0].guessed && r.facts[0].heldBack)
        assertEquals(4, r.facts[1].alt)
        assertEquals("c9", r.next)
        assertEquals(38, r.total)
        assertNull(Topics.review(obj("""{"ok": true, "facts": [], "next": null, "total": 0}"""))!!.next)

        val h = Topics.hidden(obj("""{"ok": true, "id": 2, "mode": "off", "facts": [{"id": 3, "text": "t", "topic": 2}], "next": 44}"""))!!
        assertEquals(2, h.id)
        assertEquals("44", h.next)
        assertEquals(3L, h.facts.single().id)
    }

    @Test
    fun `review facts group under consecutive suggested topics`() {
        fun f(id: Long, topic: Int) = Topics.ReviewFact(id, "x", null, topic, null, "rule", false, false)
        val g = Topics.groups(listOf(f(1, 2), f(2, 2), f(3, 5), f(4, 2)))
        assertEquals(listOf(2, 5, 2), g.map { it.first })
        assertEquals(listOf(2, 1, 1), g.map { it.second.size })
    }

    // --------------------------------------------------------- writes ---

    @Test
    fun `200 is done, 202 is waiting, and the PC's sentence wins on a failure`() {
        val done = Topics.outcome(200, obj(sample.replace("\"ok\": true,", "\"ok\": true, \"id\": 2, \"changed\": true,")))
        assertTrue(done is Topics.Outcome.Done)
        assertEquals(2, (done as Topics.Outcome.Done).id)
        assertNotNull(done.view)

        val filed = Topics.outcome(200, obj("""{"ok": true, "filed": 4, "topics": []}""")) as Topics.Outcome.Done
        assertEquals(4, filed.filed)

        val waiting = Topics.outcome(202, obj("""{"ok": true, "waiting": true, "id": 3, "kind": "mode", "message": "Waiting for your approval."}"""))
        assertEquals(Topics.Outcome.Waiting(3, "mode", Topics.WORDS["waiting"]!!), waiting)

        val taken = Topics.outcome(409, obj("""{"ok": false, "error": "name_taken", "message": "You already have a topic with that name."}""")) as Topics.Outcome.Failed
        assertEquals("You already have a topic with that name.", taken.said)
        assertFalse(taken.missing)

        // No message: the fixture's sentence for the code.
        val noMsg = Topics.outcome(400, obj("""{"ok": false, "error": "bad_mode"}""")) as Topics.Outcome.Failed
        assertEquals(Topics.ERRORS["bad_mode"], noMsg.said)
        val gate = Topics.outcome(503, obj("""{"ok": false, "error": "no_card"}""")) as Topics.Outcome.Failed
        assertEquals(Topics.GATE_FAILED, gate.said)
        val odd = Topics.outcome(500, obj("""{"ok": false, "error": "what_is_this"}""")) as Topics.Outcome.Failed
        assertEquals(Topics.ERROR_FALLBACK, odd.said)
    }

    @Test
    fun `every fixture error code has its sentence, and a missing route says so`() {
        for ((code, sentence) in strMap("errors")) {
            if (code == "unavailable") continue
            val code400 = if (code.endsWith("not_found") || code == "no_such_fact") 404 else 400
            val f = Topics.outcome(code400, obj("""{"ok": false, "error": "$code"}""")) as Topics.Outcome.Failed
            assertEquals(code, sentence, f.said)
            assertFalse(code, f.missing)
        }
        val gone = Topics.outcome(404, null) as Topics.Outcome.Failed
        assertTrue(gone.missing)
        assertEquals(Topics.WORDS["missing"], gone.said)
        val unavailable = Topics.outcome(503, obj("""{"ok": false, "error": "unavailable", "message": "x"}""")) as Topics.Outcome.Failed
        assertTrue(unavailable.missing)
        assertTrue((Topics.outcome(501, null) as Topics.Outcome.Failed).missing)
    }

    @Test
    fun `polling waits while a card is up and then shows the PC's sentence for THIS card`() {
        val waiting = Topics.view(obj(sample))!!
        assertEquals(Topics.Poll.Waiting, Topics.pollStep(waiting, 0.0))
        assertEquals(Topics.Poll.Waiting, Topics.pollStep(null, 0.0))

        val over = Topics.view(obj(sample.replace(""""waiting": {"topic": 3, "kind": "mode"},""", """"waiting": null,""")))!!
        val fresh = Topics.pollStep(over, 1790000000.0) as Topics.Poll.Done
        assertEquals("The card was turned down, so nothing about your topics changed.", fresh.message)
        // An ending older than the card being waited for is an earlier card's.
        val old = Topics.pollStep(over, 1790000200.0) as Topics.Poll.Done
        assertNull(old.message)
        // No message from the PC: the fixture's sentence for the outcome.
        val bare = Topics.view(obj("""{"topics": [], "last": {"outcome": "applied", "at": 5.0}}"""))!!
        assertEquals(Topics.LAST_WORDS["applied"], (Topics.pollStep(bare, 1.0) as Topics.Poll.Done).message)
        assertTrue(Topics.POLL_MS == 2_000L)
    }

    @Test
    fun `request bodies are the contract's`() {
        assertEquals("""{"id":2,"mode":"off"}""", Topics.modeBody(2, "off"))
        assertNull(Topics.modeBody(2, "hide"))
        assertNull(Topics.modeBody(0, "off"))
        assertEquals("""{"op":"add","name":"Garden plans","colour":1,"icon":"leaf"}""", Topics.addBody("  Garden   plans ", 1, "leaf"))
        assertEquals("""{"op":"add","name":"Pets"}""", Topics.addBody("Pets"))
        assertNull(Topics.addBody("   "))
        assertNull(Topics.addBody("x".repeat(25)))
        assertEquals("""{"op":"rename","id":4,"name":"Pets"}""", Topics.renameBody(4, "Pets"))
        assertNull(Topics.renameBody(1, "Sorted"))
        assertEquals("""{"op":"style","id":4,"colour":7}""", Topics.styleBody(4, colour = 7))
        assertEquals("""{"op":"style","id":4,"icon":"coin"}""", Topics.styleBody(4, icon = "coin"))
        assertNull(Topics.styleBody(4, colour = 8))
        assertNull(Topics.styleBody(4, icon = "rocket"))
        assertNull(Topics.styleBody(4))
        assertEquals("""{"op":"private","id":4,"private":false}""", Topics.privateBody(4, false))
        assertNull(Topics.privateBody(1, true))
        assertEquals("""{"op":"delete","id":4,"move_to":1}""", Topics.deleteBody(4, 1))
        assertNull("a delete needs a home", Topics.deleteBody(4, null))
        assertNull(Topics.deleteBody(4, 4))
        assertNull(Topics.deleteBody(1, 2))
        assertEquals("""{"ids":[3,4],"topic_id":2}""", Topics.fileBody(listOf(3, 4, 3), 2))
        assertEquals("""{"ids":[3,4],"confirm":true}""", Topics.confirmBody(listOf(3, 4)))
        assertNull(Topics.fileBody(emptyList(), 2))
        assertNull(Topics.fileBody((1L..201L).toList(), 2))
        assertNotNull(Topics.fileBody((1L..200L).toList(), 2))
        assertEquals("""{"model_help":true}""", Topics.settingsBody(true))
    }

    @Test
    fun `reordering moves among the owner's topics and never Unsorted`() {
        val v = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "system": true},
            {"id": 2, "name": "A", "ord": 1}, {"id": 3, "name": "B", "ord": 2}, {"id": 4, "name": "C", "ord": 3}]}"""))!!
        assertNull(Topics.moveUpBody(v, 2))
        assertEquals("""{"op":"move","id":3,"before":2}""", Topics.moveUpBody(v, 3))
        assertEquals("""{"op":"move","id":2,"before":4}""", Topics.moveDownBody(v, 2))
        assertEquals("""{"op":"move","id":3,"before":null}""", Topics.moveDownBody(v, 3))
        assertNull(Topics.moveDownBody(v, 4))
        assertNull(Topics.moveUpBody(v, 1))
    }

    @Test
    fun `paths are literal routes with the query in`() {
        assertEquals("/api/topics/preview?id=2&mode=off", Topics.previewPath(2, "off"))
        assertNull(Topics.previewPath(2, "nope"))
        assertEquals("/api/topics/review?limit=10", Topics.reviewPath())
        assertEquals("/api/topics/review?limit=10&after=a+b%2B", Topics.reviewPath("a b+"))
        assertEquals("/api/topics/hidden?id=2&limit=100&after=44", Topics.hiddenPath(2, "44"))
    }

    @Test
    fun `while lists are hidden only a mode change and the model switch are sent`() {
        assertFalse(Topics.refusedWhileHidden(Topics.MODE_PATH))
        assertFalse(Topics.refusedWhileHidden(Topics.SETTINGS_PATH))
        assertTrue(Topics.refusedWhileHidden(Topics.TOPICS_PATH))
        assertTrue(Topics.refusedWhileHidden(Topics.FILE_PATH))
    }

    // ---------------------------------------------------- hiding, rows ---

    @Test
    fun `hidden lists show Topic N and the count and the mode, never a name`() {
        val v = Topics.view(obj(sample))!!
        val health = v.byId(3)!!
        val work = v.byId(2)!!
        assertEquals("Health", Topics.shownName(v, health, false))
        assertEquals("Topic 2", Topics.shownName(v, health, true))
        assertEquals("Topic 1", Topics.shownName(v, work, true))
        assertEquals("Unsorted", Topics.shownName(v, v.byId(1)!!, true))
        assertEquals("Topic 2, 12 facts, Learn, but don't use", Topics.hiddenRow(Topics.ownerIndex(v, 3), health.facts, health.mode))
        assertTrue("no tags or notes while hidden", Topics.rowNotes(health, true).isEmpty())
        // The PC's preview sentence names the topic: the name is swapped out.
        assertEquals(
            "12 things Jarvis knows about Topic 1 will be left out of answers.",
            Topics.maskName("12 things Jarvis knows about Work will be left out of answers.", "Work", "Topic 1"),
        )
    }

    @Test
    fun `row notes are the states of C3 in words`() {
        val v = Topics.view(obj(sample))!!
        assertEquals(listOf("Private", "not used in answers"), Topics.rowNotes(v.byId(3)!!, false))
        assertEquals(listOf("41 facts kept, hidden", "3 new things not saved this week"), Topics.rowNotes(v.byId(2)!!, false))
        assertTrue(Topics.rowNotes(v.byId(1)!!, false).isEmpty())
        assertEquals("Jarvis is still sorting 18 of your facts.", Topics.sortingLine(v))
        assertEquals(
            "Jarvis sorted 3 of your 230 facts by guessing from the words. Check them so switching a topic off works as you expect.",
            Topics.guessLine(v),
        )
        assertEquals("Check these (3)", Topics.checkButton(v))
        val nothing = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted"}]}"""))!!
        assertNull(Topics.guessLine(nothing))
        assertNull(Topics.checkButton(nothing))
        assertNull(Topics.sortingLine(nothing))
    }

    @Test
    fun `the delete destination warns when it is more open than the topic going`() {
        val v = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "mode": "both", "system": true},
            {"id": 2, "name": "Work", "mode": "off", "ord": 1}, {"id": 3, "name": "Pets", "mode": "off", "ord": 2}]}"""))!!
        val work = v.byId(2)!!
        assertEquals(listOf(1, 3), Topics.homes(v, 2).map { it.id })
        assertEquals(Topics.w("delete_looser", "name" to "Work"), Topics.deleteLooser(work, v.byId(1)!!))
        assertNull(Topics.deleteLooser(work, v.byId(3)!!))
    }

    // -------------------------------------------- the chat and the lists ---

    @Test
    fun `the answer's route opens Topics, with or without a topic`() {
        assertEquals(Topics.Open(2), Topics.openFromRoute("""{"open_brain": "topics", "topic_id": 2}"""))
        assertEquals(Topics.Open(null), Topics.openFromRoute("""{"open_brain": "topics"}"""))
        assertNull(Topics.openFromRoute("""{"open_brain": "history", "topic_id": 2}"""))
        assertNull(Topics.openFromRoute("""{"topic_id": 2}"""))
        assertNull(Topics.openFromRoute("not json"))
        assertNull(Topics.openFromRoute(null))
        assertEquals(Topics.Open(null), Topics.openFromRoute("""{"open_brain": "topics", "topic_id": "x"}"""))
    }

    @Test
    fun `left out is a count under the answer`() {
        assertEquals(2, Topics.leftOutFromRoute("""{"topics_left_out": 2}"""))
        assertEquals(0, Topics.leftOutFromRoute("""{"topics_left_out": -3}"""))
        assertEquals(0, Topics.leftOutFromRoute("""{"topics_left_out": "many"}"""))
        assertEquals(0, Topics.leftOutFromRoute(null))
        assertNull(Topics.leftOutLine(0))
        assertEquals("Left out 1 fact because of your topic settings", Topics.leftOutLine(1))
        assertEquals("Left out 2 facts because of your topic settings", Topics.leftOutLine(2))
    }

    @Test
    fun `list tags, paused pins, used facts and topic-question cards use the fixture's words`() {
        val v = Topics.view(obj(sample))!!
        assertEquals("not used in answers", Topics.notUsedTag(3, v))
        assertNull(Topics.notUsedTag(2, v))
        assertNull(Topics.notUsedTag(null, v))
        assertNull(Topics.notUsedTag(3, null))
        assertEquals("Paused: Work is off", Topics.pinPausedLine("Work"))
        assertEquals("A memory from a topic you have since switched off.", Topics.usedLeftOutLine())
        assertEquals("Save under Unsorted" to "Skip it", Topics.askLabels(obj("""{"id": 4, "topic_ask": true}""")))
        assertNull(Topics.askLabels(obj("""{"id": 4, "topic_ask": false}""")))
        assertNull(Topics.askLabels(obj("""{"id": 4}""")))
        assertEquals("Held back: might be about Work", Topics.heldLine("Work"))
    }

    @Test
    fun `the modes are two switches`() {
        assertEquals(listOf(true, true), Topics.mode("both")!!.let { listOf(it.learns, it.uses) })
        assertEquals(listOf(false, true), Topics.mode("use_only")!!.let { listOf(it.learns, it.uses) })
        assertEquals(listOf(true, false), Topics.mode("learn_only")!!.let { listOf(it.learns, it.uses) })
        assertEquals(listOf(false, false), Topics.mode("off")!!.let { listOf(it.learns, it.uses) })
        assertEquals("nonsense", Topics.modeName("nonsense"))
    }

    @Test
    fun `a paused pin names its topic only when exactly one topic is not used`() {
        val one = Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "system": true},
            {"id": 2, "name": "Work", "mode": "off", "ord": 1}, {"id": 3, "name": "Pets", "mode": "use_only", "ord": 2}]}"""))!!
        assertEquals("Paused: Work is off", Topics.pinPausedFor(one))
        val two = Topics.view(obj("""{"topics": [{"id": 2, "name": "Work", "mode": "off"}, {"id": 3, "name": "Pets", "mode": "learn_only"}]}"""))!!
        assertEquals(Topics.PIN_PAUSED_GENERIC, Topics.pinPausedFor(two))
        assertEquals(Topics.PIN_PAUSED_GENERIC, Topics.pinPausedFor(null))
        // The PC now sends the pin's topic id: it names the topic and the mode it is in.
        assertEquals("Paused: Work is off", Topics.pinPausedFor(two, 2))
        assertEquals("Paused: Pets is set to Learn, but don't use", Topics.pinPausedFor(two, 3))
        for (c in doc["pin_paused_cases"]!!.jsonArray) {
            val o = c.jsonObject
            assertEquals(
                o["expect"]!!.jsonPrimitive.content,
                Topics.pinPausedLine(o["name"]!!.jsonPrimitive.content, o["mode"]!!.jsonPrimitive.content),
            )
        }
    }

    @Test
    fun `one fact reads singular - count_cases and the singular rows`() {
        for (c in doc["count_cases"]!!.jsonArray) {
            val o = c.jsonObject
            val n = o["n"]!!.jsonPrimitive.int
            val got = when (o["line"]!!.jsonPrimitive.content) {
                "kept_hidden" -> Topics.keptHiddenLine(n)
                "skipped" -> Topics.w(if (n == 1) "skipped_one" else "skipped", "n" to n)
                else -> Topics.guessLine(
                    Topics.view(obj("""{"topics": [{"id": 1, "name": "Unsorted", "system": true}], "unchecked": $n, "facts": ${o["total"]!!.jsonPrimitive.int}}"""))!!,
                )
            }
            assertEquals(o["expect"]!!.jsonPrimitive.content, got)
        }
        assertEquals("1 fact", Topics.factsText(1))
        assertEquals("2 facts", Topics.factsText(2))
    }

    @Test
    fun `the literal routes are the seven the parity table names`() {
        assertEquals(
            listOf(
                "/api/topics", "/api/topics/mode", "/api/topics/file", "/api/topics/settings",
                "/api/topics/preview", "/api/topics/review", "/api/topics/hidden",
            ),
            listOf(
                Topics.TOPICS_PATH, Topics.MODE_PATH, Topics.FILE_PATH, Topics.SETTINGS_PATH,
                Topics.PREVIEW_PATH, Topics.REVIEW_PATH, Topics.HIDDEN_PATH,
            ),
        )
        assertEquals("topics", Topics.PLACE)
    }
}
