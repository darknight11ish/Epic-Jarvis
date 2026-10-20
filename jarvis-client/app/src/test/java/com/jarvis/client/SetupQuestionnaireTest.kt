package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.SetupQuestionnaire
import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The setup questionnaire on the phone (docs/JARVIS-API.md section 147;
 * `net/SetupQuestionnaire.kt`, `ui/screens/SetupQuestionnairePlate.kt`; the
 * PC's module is `backend/jarvis_setup.py`).
 *
 * The questions are read from the SHARED fixture the PC's own table writes
 * (`tools/gen_setup_questions.py`; the desktop suite reads the same file), so
 * this cannot pass against a hand-written idea of the questionnaire.
 *
 * What it proves: the phone reads the PC's questions and choices without
 * inventing a word, prefills the last accepted answers and drops choices this
 * PC no longer offers, builds the READ-ONLY plan body and NOTHING else, reads
 * the plan's effects and the PC's "would not change" reasons, and says a card
 * still waiting is still waiting. The last checks read the two phone files as
 * text and fail if an apply path or a `confirm` body ever appears: applying is
 * deliberately the PC's step, not the phone's.
 */
class SetupQuestionnaireTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, rel)
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val fixture: JsonObject by lazy {
        Json.parseToJsonElement(
            repoFile("backend/fixtures/setup_questions.json").readText(),
        ) as JsonObject
    }

    private val view: SetupQuestionnaire.View by lazy {
        requireNotNull(
            SetupQuestionnaire.parse(
                buildJsonObject {
                    put("available", true)
                    put("questions", fixture["questions"]!!)
                    putJsonObject("current") { put("manner", "warm") }
                    putJsonObject("answers") {
                        put("talk_style", "warm")
                        putJsonArray("reading_tools") {
                            add(JsonPrimitive("calendar"))
                            add(JsonPrimitive("email"))
                        }
                    }
                    put("completed_at", 1_765_000_000.0)
                    putJsonArray("last_outcomes") {
                        add(buildJsonObject {
                            put("setting", "manner")
                            put("label", "How Jarvis talks")
                            put("effect", "instant")
                            put("state", "changed")
                            put("message", "changed.")
                        })
                        add(buildJsonObject {
                            put("setting", "email_read")
                            put("label", "Email reading")
                            put("effect", "card")
                            put("state", "asked-no-answer")
                            put("message", "The card is still waiting.")
                        })
                    }
                    put("card_wait_s", 300)
                    put("storage", "setup.json in the Jarvis settings folder")
                    put("about", "A guided path through settings that already exist.")
                },
            ),
            { "the PC's own question shape did not parse" },
        )
    }

    // -- The PC's questions ---------------------------------------------------

    @Test
    fun thePcsQuestionnaireIsFourteenQuestionsInItsOwnOrder() {
        assertEquals(14, fixture["count"]!!.jsonPrimitiveInt())
        assertEquals(14, view.questions.size)
        assertEquals(
            (fixture["questions"]!!.jsonArray).map { it.jsonObject["id"]!!.jsonPrimitiveText() },
            view.questions.map { it.id },
        )
        assertTrue(view.available)
        assertEquals("setup.json in the Jarvis settings folder", view.storage)
        assertEquals(300, view.cardWaitS ?: 0)
        assertNotNull(view.completedAt)
    }

    @Test
    fun everyQuestionAndChoiceIsThePcsOwnWords() {
        val sent = fixture["questions"]!!.jsonArray.map { it.jsonObject }
        for ((index, row) in sent.withIndex()) {
            val got = view.questions[index]
            assertEquals(row["title"]!!.jsonPrimitiveText(), got.title)
            assertEquals(row["help"]!!.jsonPrimitiveText(), got.help)
            assertEquals(
                row["options"]!!.jsonArray.map { it.jsonObject["id"]!!.jsonPrimitiveText() },
                got.options.map { it.id },
            )
            assertEquals(
                row["options"]!!.jsonArray.map { it.jsonObject["label"]!!.jsonPrimitiveText() },
                got.options.map { it.label },
            )
            assertEquals(row["multi"]!!.jsonPrimitiveBoolean(), got.multi)
            assertEquals(got.multi, got.allNone)
        }
    }

    // -- The draft ------------------------------------------------------------

    @Test
    fun theDraftPrefillsTheLastAnswersAndDropsChoicesThisPcNoLongerOffers() {
        val draft = SetupQuestionnaire.initialDraft(view)
        assertEquals(listOf("warm"), draft["talk_style"])
        assertEquals(listOf("calendar", "email"), draft["reading_tools"])

        val stale = SetupQuestionnaire.parse(
            buildJsonObject {
                put("available", true)
                put("questions", fixture["questions"]!!)
                putJsonObject("answers") {
                    put("talk_style", "gone")
                    putJsonObject("reading_tools") { }
                }
            },
        )!!
        assertTrue("a stale option is dropped", SetupQuestionnaire.initialDraft(stale).isEmpty())
    }

    @Test
    fun answersReadBothABareStringAndAListAndNeverInventOne() {
        val answers = SetupQuestionnaire.answers(
            buildJsonObject {
                put("talk_style", "warm")
                putJsonArray("reading_tools") { add(JsonPrimitive("calendar")) }
                putJsonArray("empty") { }
                put("numeric", 7)
            },
        )
        assertEquals(listOf("warm"), answers["talk_style"])
        assertEquals(listOf("calendar"), answers["reading_tools"])
        assertNull(answers["empty"])
        assertNull(answers["numeric"])
    }

    @Test
    fun oneChoiceReplacesAndChooseAnyTogglesWithAllAndNoneKeptAsData() {
        val style = view.questions.first { !it.multi }
        val tools = view.questions.first { it.multi }

        var draft = SetupQuestionnaire.chooseOne(emptyMap(), style.id, style.options[1].id)
        assertEquals(listOf(style.options[1].id), draft[style.id])
        draft = SetupQuestionnaire.chooseOne(draft, style.id, style.options[0].id)
        assertEquals(listOf(style.options[0].id), draft[style.id])

        var chosen = emptyMap<String, List<String>>()
        chosen = SetupQuestionnaire.toggle(chosen, tools, tools.options[0].id)
        assertEquals(listOf(tools.options[0].id), chosen[tools.id])
        chosen = SetupQuestionnaire.toggle(chosen, tools, tools.options[1].id)
        assertEquals(listOf(tools.options[0].id, tools.options[1].id), chosen[tools.id])
        chosen = SetupQuestionnaire.toggle(chosen, tools, tools.options[0].id)
        assertEquals(listOf(tools.options[1].id), chosen[tools.id])

        val all = SetupQuestionnaire.chooseAll(emptyMap(), tools.id)
        assertEquals("all", SetupQuestionnaire.allNoneState(all, tools.id))
        assertTrue(SetupQuestionnaire.picked(all, tools, tools.options[2].id))
        val rest = SetupQuestionnaire.toggle(all, tools, tools.options[0].id)
        assertEquals(
            tools.options.drop(1).map { it.id },
            rest[tools.id],
        )

        val none = SetupQuestionnaire.chooseNone(emptyMap(), tools.id)
        assertEquals("none", SetupQuestionnaire.allNoneState(none, tools.id))
        assertFalse(SetupQuestionnaire.picked(none, tools, tools.options[0].id))
        assertEquals(
            listOf(tools.options[0].id),
            SetupQuestionnaire.toggle(none, tools, tools.options[0].id)[tools.id],
        )
        // Unticking the last choice leaves the question unanswered, not blank.
        assertTrue(SetupQuestionnaire.toggle(chosen, tools, tools.options[1].id).isEmpty())
        assertEquals(1, SetupQuestionnaire.answeredCount(mapOf(style.id to listOf("warm"))))
    }

    // -- The read-only plan ---------------------------------------------------

    @Test
    fun thePlanBodyIsAnswersOnlyAndCanNeverCarryConfirm() {
        val style = view.questions.first { !it.multi }
        val tools = view.questions.first { it.multi }
        val body = SetupQuestionnaire.planBody(
            mapOf(
                style.id to listOf("warm"),
                tools.id to listOf("calendar"),
                "blank" to listOf(""),
            ),
            setOf(tools.id),
        )
        val sent = Json.parseToJsonElement(body) as JsonObject
        val answers = sent["answers"] as JsonObject
        assertEquals("warm", (answers[style.id] as JsonPrimitive).content)
        assertEquals(
            listOf("calendar"),
            (answers[tools.id] as kotlinx.serialization.json.JsonArray)
                .map { (it as JsonPrimitive).content },
        )
        assertNull(answers["blank"])
        assertNull(sent["confirm"])
        assertFalse(body.contains("confirm"))
    }

    @Test
    fun thePlanKeepsThePcsEffectsReasonsAndRecommendationAndNeverRoundsAnUnknownEffect() {
        val plan = SetupQuestionnaire.parsePlan(
            buildJsonObject {
                put("ok", true)
                putJsonArray("changes") {
                    add(buildJsonObject {
                        put("setting", "manner")
                        put("label", "How Jarvis talks")
                        put("question", "talk_style")
                        put("from", "warm")
                        put("to", "plain")
                        put("effect", "instant")
                        put("sentence", "How Jarvis talks: warm -> plain")
                    })
                    add(buildJsonObject {
                        put("setting", "email_read")
                        put("label", "Email reading")
                        put("question", "reading_tools")
                        put("from", false)
                        put("to", true)
                        put("effect", "card")
                        put("sentence", "Email reading: off -> on")
                    })
                    add(buildJsonObject {
                        put("setting", "odd")
                        put("label", "Odd")
                        put("question", "talk_style")
                        put("effect", "experimental")
                        put("sentence", "Odd: a -> b")
                    })
                }
                putJsonArray("summary") { add(JsonPrimitive("Takes effect immediately")) }
                putJsonArray("skipped") {
                    add(buildJsonObject {
                        put("setting", "humor")
                        put("reason", "Humour: already off")
                    })
                }
                putJsonObject("recommendation") {
                    put("id", "coding")
                    put("title", "Coding")
                    put("why", "A preset changes models, so it is only a recommendation here.")
                }
            },
        )
        assertTrue(plan.ok)
        assertEquals(3, plan.changes.size)
        assertEquals("Instant", SetupQuestionnaire.effectWords(plan.changes[0].effect))
        assertEquals("Asks you on a card", SetupQuestionnaire.effectWords(plan.changes[1].effect))
        assertEquals("off", plan.changes[1].from)
        assertEquals("on", plan.changes[1].to)
        assertEquals("experimental", SetupQuestionnaire.effectWords(plan.changes[2].effect))
        assertEquals("Humour: already off", plan.skipped.single().reason)
        assertEquals("Coding", plan.recommendation!!.title)
        assertEquals(listOf("Takes effect immediately"), plan.summary)

        val refused = SetupQuestionnaire.parsePlan(
            buildJsonObject {
                put("ok", false)
                put("error", "the answers must be one object")
            },
        )
        assertFalse(refused.ok)
        assertEquals("the answers must be one object", refused.error)
    }

    @Test
    fun aCardStillWaitingIsSaidSoAndAnOutcomeKeepsThePcsOwnSentence() {
        assertEquals(
            "Still waiting: answer its card on the PC and it changes.",
            SetupQuestionnaire.outcomeWords("asked-no-answer"),
        )
        assertEquals(
            "Not changed - the card was not approved.",
            SetupQuestionnaire.outcomeWords("asked-and-denied"),
        )
        assertEquals("", SetupQuestionnaire.outcomeWords("made-up"))
        assertEquals(2, view.lastOutcomes.size)
        assertEquals("asked-no-answer", view.lastOutcomes[1].state)
    }

    @Test
    fun theCardPatienceIsSaidInMinutesAndAnOlderBackendIsNamed() {
        assertEquals(
            "Each approval card can wait up to 5 minutes for you before the questionnaire moves on.",
            SetupQuestionnaire.cardWaitWords(300),
        )
        assertEquals(
            "Each approval card can wait up to 1 minute for you before the questionnaire moves on.",
            SetupQuestionnaire.cardWaitWords(60),
        )
        assertTrue(SetupQuestionnaire.missing(ApiError.NotFound))
        assertTrue(SetupQuestionnaire.missing(ApiError.NotAvailable))
        assertTrue(SetupQuestionnaire.missing(ApiError.Server(501, "")))
        assertFalse(SetupQuestionnaire.missing(ApiError.Server(400, "")))
        assertFalse(SetupQuestionnaire.missing(ApiError.Malformed("bad or missing X-Jarvis-Token")))
    }

    @Test
    fun theAboutAndWordsComeFromThePcWhenItSendsThem() {
        assertEquals(
            "A guided path through settings that already exist.",
            view.about,
        )
        val old = SetupQuestionnaire.parse(buildJsonObject { })!!
        assertTrue(old.available)
        assertTrue(old.questions.isEmpty())
        assertEquals("", old.about)
        assertEquals("", old.reason)
    }

    // -- Read-only on purpose -------------------------------------------------

    @Test
    fun theTwoPhoneFilesHoldNoApplyPathAndNoConfirmBody() {
        val net = codeOnly(
            repoFile(
                "jarvis-client/app/src/main/java/com/jarvis/client/net/SetupQuestionnaire.kt",
            ).readText(),
        )
        val plate = codeOnly(
            repoFile(
                "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SetupQuestionnairePlate.kt",
            ).readText(),
        )
        // The route and the body field stay on the PC: this app can only read
        // and ask for the read-only plan.
        for (source in listOf(net, plate)) {
            assertFalse(source.contains("/api/setup/apply"))
            assertFalse(source.contains("confirm"))
            assertFalse(source.contains("setupApply"))
            assertFalse(source.contains("applyBody"))
        }
        assertTrue(net.contains(SetupQuestionnaire.PLAN_PATH))
        assertTrue(SetupQuestionnaire.PLAIN_ONLY.contains("made on the PC"))
    }

    /** The file without its comment lines, so a doc line naming a route or the
     *  word "confirm" does not count as code that sends one. */
    private fun codeOnly(text: String): String = text.lineSequence()
        .filterNot { line ->
            val trimmed = line.trimStart()
            trimmed.startsWith("*") || trimmed.startsWith("//") ||
                trimmed.startsWith("/*") || trimmed.startsWith("*/")
        }
        .joinToString("\n")

    private fun kotlinx.serialization.json.JsonElement.jsonPrimitiveInt(): Int =
        (this as JsonPrimitive).content.toInt()

    private fun kotlinx.serialization.json.JsonElement.jsonPrimitiveText(): String =
        (this as JsonPrimitive).content

    private fun kotlinx.serialization.json.JsonElement.jsonPrimitiveBoolean(): Boolean =
        (this as JsonPrimitive).content.toBoolean()
}
