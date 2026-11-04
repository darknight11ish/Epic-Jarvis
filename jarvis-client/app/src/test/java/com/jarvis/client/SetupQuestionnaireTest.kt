package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.SetupQuestionnaire
import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
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
 * "Personalize Jarvis" on the phone (docs/JARVIS-API.md section 147;
 * `net/SetupQuestionnaire.kt`, `ui/screens/SetupQuestionnairePlate.kt`; the
 * PC's module is `backend/jarvis_setup.py`).
 *
 * The questions are read from the SHARED fixture the PC's own table writes
 * (`tools/gen_setup_questions.py`; the desktop suite reads the same file), so
 * this cannot pass against a hand-written idea of the questionnaire.
 *
 * What it proves: the phone reads the PC's questions and choices without
 * inventing a word, prefills the last accepted answers and drops choices this
 * PC no longer offers, splits the questions by the PC's OWN sections (and
 * shows a section it has no title for by the id the PC sent), builds the
 * READ-ONLY plan body and NOTHING else, reads the plan's effects and the PC's
 * "would not change" reasons, and says a card still waiting is still waiting.
 * The ONE progress line says whether the PC's question set is finished, how
 * many questions it has answered and which question its card is on - and a set
 * finished before the new questions is NOT called finished. The last checks
 * read the two phone files as text and fail if an apply path, a `confirm` body
 * or a progress write ever appears: applying and recording progress are
 * deliberately the PC's steps, not the phone's.
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
    fun thePcsQuestionnaireIsItsOwnQuestionsInItsOwnOrder() {
        // The count is the PC's, never a number typed into this test: the
        // question set grows (14 -> 25 for "Personalize Jarvis"), and a pinned
        // count would go red on the day the PC adds one rather than prove
        // anything about this app.
        assertEquals(fixture["count"]!!.jsonPrimitiveInt(), view.questions.size)
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

    /**
     * The number of questions is the PC's, so this screen may not type one:
     * the kicker used to say "Twenty-five questions" while the progress line
     * beside it was computed from the PC's own list, and the two disagreed on
     * the same page as soon as the set changed (audit 2026-11-03, bug 3).
     */
    @Test
    fun theKickerCarriesNoCountOfItsOwn() {
        // The count the page really shows is `view.questions.size`, which the
        // fixture proves is the PC's number - not a second opinion.
        assertEquals(fixture["count"]!!.jsonPrimitiveInt(), view.questions.size)
        val kicker = SetupQuestionnaire.KICKER
        assertTrue(
            "the kicker types a number: ${kicker.filter { it.isDigit() }}",
            kicker.none { it.isDigit() },
        )
        val spelled = Regex(
            "\\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|" +
                "seventeen|eighteen|nineteen|twenty|thirty|forty|fifty)\\b",
            RegexOption.IGNORE_CASE,
        )
        assertNull(
            "the kicker spells a number of questions: ${spelled.find(kicker)?.value}",
            spelled.find(kicker),
        )
        // It still says what the screen is for.
        assertTrue(kicker.contains("how you want Jarvis to behave"))
    }

    // -- The PC's sections ----------------------------------------------------

    /** One question as `GET /api/setup` sends it, with the PC's own section id. */
    private fun questionRow(id: String, section: String? = null): JsonObject = buildJsonObject {
        put("id", id)
        put("title", "Question $id")
        put("help", "")
        put("multi", false)
        if (section != null) put("section", section)
        putJsonArray("options") {
            add(buildJsonObject {
                put("id", "on")
                put("label", "On")
                put("detail", "")
            })
        }
    }

    private fun bodyWith(
        questions: List<JsonObject>,
        sections: JsonElement? = null,
    ): JsonObject = buildJsonObject {
        put("available", true)
        if (sections != null) put("sections", sections)
        put("questions", JsonArray(questions))
    }

    @Test
    fun theQuestionsAreSplitByThePcsOwnSectionsInItsOwnOrder() {
        val declared = buildJsonArray {
            add(buildJsonObject { put("id", "talk"); put("title", "How it talks") })
            add(buildJsonObject { put("id", "read"); put("title", "What it may read") })
            add(buildJsonObject { put("id", "empty"); put("title", "Nothing here yet") })
        }
        val got = SetupQuestionnaire.parse(
            bodyWith(
                listOf(
                    questionRow("q1", "read"),
                    questionRow("q2", "talk"),
                    questionRow("q3", "other"),
                ),
                declared,
            ),
        )!!
        // The PC's declared order wins over the order its questions arrive in,
        // and a declared section with no question is not drawn as an empty tab.
        assertEquals(listOf("talk", "read", "other"), got.sections.map { it.id })
        assertEquals(listOf("How it talks", "What it may read", ""), got.sections.map { it.title })
        assertEquals(listOf("q2"), got.sections[0].questions.map { it.id })
        assertEquals(listOf("q1"), got.sections[1].questions.map { it.id })
        assertEquals(listOf("q3"), got.sections[2].questions.map { it.id })
        // A section the PC declared no word for keeps the id it sent.
        assertEquals("other", SetupQuestionnaire.sectionWords(got.sections[2]))
        // The flat list keeps the PC's own order, which is what the plan posts.
        assertEquals(listOf("q1", "q2", "q3"), got.questions.map { it.id })
    }

    @Test
    fun aSectionTitleIsReadInEveryShapeThePcSendsAndItsIdWhenItSendsNone() {
        val pairs = SetupQuestionnaire.parse(
            bodyWith(
                listOf(questionRow("q1", "talk")),
                buildJsonArray {
                    add(buildJsonArray {
                        add(JsonPrimitive("talk"))
                        add(JsonPrimitive("How it talks"))
                    })
                },
            ),
        )!!
        assertEquals("How it talks", pairs.sections.single().title)

        val mapped = SetupQuestionnaire.parse(
            bodyWith(
                listOf(questionRow("q1", "talk")),
                buildJsonObject { put("talk", "How it talks") },
            ),
        )!!
        assertEquals("How it talks", mapped.sections.single().title)

        val untitled = SetupQuestionnaire.parse(bodyWith(listOf(questionRow("q1", "learning"))))!!
        assertEquals(listOf("learning"), untitled.sections.map { it.id })
        assertEquals("", untitled.sections.single().title)
        assertEquals("learning", SetupQuestionnaire.sectionWords(untitled.sections.single()))
    }

    @Test
    fun aPcFromBeforeSectionsDrawsOneUnnamedGroup() {
        val old = SetupQuestionnaire.parse(bodyWith(listOf(questionRow("q1"), questionRow("q2"))))!!
        assertEquals(1, old.sections.size)
        assertEquals("", old.sections.single().id)
        assertEquals("", old.sections.single().title)
        assertEquals(listOf("q1", "q2"), old.sections.single().questions.map { it.id })
        assertEquals(
            SetupQuestionnaire.ALL_SECTIONS,
            SetupQuestionnaire.sectionWords(old.sections.single()),
        )
        // The shared fixture is the PC's own table: whatever `section` each row
        // carries is the group it lands in, and no question is lost.
        val fromFixture = SetupQuestionnaire.parse(
            buildJsonObject {
                put("available", true)
                put("questions", fixture["questions"]!!)
            },
        )!!
        val sent = (fixture["questions"]!!.jsonArray).associate { row ->
            val body = row.jsonObject
            body["id"]!!.jsonPrimitiveText() to (body["section"]?.jsonPrimitiveText() ?: "")
        }
        for (group in fromFixture.sections) {
            for (question in group.questions) assertEquals(sent[question.id], group.id)
        }
        assertEquals(
            fromFixture.questions.size,
            fromFixture.sections.sumOf { it.questions.size },
        )
    }

    // -- The one progress line ------------------------------------------------

    private fun progressBody(
        version: Int? = null,
        completedVersion: Int? = null,
        completedAt: Double? = null,
        answeredCount: Int? = null,
        question: String? = null,
    ): JsonObject = buildJsonObject {
        put("available", true)
        putJsonArray("questions") {
            add(questionRow("q1", "talk"))
            add(questionRow("q2", "talk"))
            add(questionRow("q3", "read"))
        }
        if (version != null) put("version", version)
        if (completedVersion != null) put("completed_version", completedVersion)
        if (completedAt != null) put("completed_at", completedAt)
        if (answeredCount != null) put("answered_count", answeredCount)
        if (question != null) {
            putJsonObject("in_progress") {
                put("section", "talk")
                put("question", question)
            }
        }
    }

    @Test
    fun theProgressLineSaysHowManyAreAnsweredAndWhereThePcsCardIs() {
        val both = SetupQuestionnaire.parse(
            progressBody(
                version = 2, completedVersion = 1, answeredCount = 2, question = "q3",
            ),
        )!!
        assertEquals(3, SetupQuestionnaire.questionNumber(both))
        assertEquals(
            "Not finished - 2 of 3 answered. On the PC this is at question 3 of 3.",
            SetupQuestionnaire.progressWords(both),
        )

        val countOnly = SetupQuestionnaire.parse(
            progressBody(version = 2, completedVersion = 1, answeredCount = 1),
        )!!
        assertEquals("Not finished - 1 of 3 answered.", SetupQuestionnaire.progressWords(countOnly))

        val whereOnly = SetupQuestionnaire.parse(
            progressBody(version = 2, completedVersion = 1, question = "q2"),
        )!!
        assertEquals(
            "Not finished. On the PC this is at question 2 of 3.",
            SetupQuestionnaire.progressWords(whereOnly),
        )

        // A question this phone does not have in its list: no invented place.
        val unknown = SetupQuestionnaire.parse(
            progressBody(version = 2, completedVersion = 1, answeredCount = 1, question = "gone"),
        )!!
        assertNull(SetupQuestionnaire.questionNumber(unknown))
        assertEquals("Not finished - 1 of 3 answered.", SetupQuestionnaire.progressWords(unknown))

        // An older backend sends nothing to say, so the screen says nothing.
        val quiet = SetupQuestionnaire.parse(progressBody())!!
        assertEquals("", SetupQuestionnaire.progressWords(quiet))
    }

    @Test
    fun aSetFinishedBeforeTheNewQuestionsIsNotCalledFinished() {
        val before = SetupQuestionnaire.parse(
            progressBody(
                version = 2, completedVersion = 1, completedAt = 1_765_000_000.0,
                answeredCount = 2, question = "q3",
            ),
        )!!
        assertFalse(SetupQuestionnaire.finished(before))
        assertEquals(
            "Not finished - 2 of 3 answered. On the PC this is at question 3 of 3.",
            SetupQuestionnaire.progressWords(before),
        )

        // A `completed_version` with no `version` sent is never read as done.
        val unknownSet = SetupQuestionnaire.parse(
            progressBody(completedVersion = 1, answeredCount = 2),
        )!!
        assertFalse(SetupQuestionnaire.finished(unknownSet))
        assertEquals(
            "Not finished - 2 of 3 answered.",
            SetupQuestionnaire.progressWords(unknownSet),
        )

        // A PC that names its question set but not the one it finished is not
        // called finished either, even with a `completed_at` from an older set.
        val halfSaid = SetupQuestionnaire.parse(
            progressBody(version = 2, completedAt = 1_765_000_000.0),
        )!!
        assertFalse(SetupQuestionnaire.finished(halfSaid))

        // An older PC has no versions at all: its `completed_at` is the sign.
        val oldPc = SetupQuestionnaire.parse(progressBody(completedAt = 1_765_000_000.0))!!
        assertTrue(SetupQuestionnaire.finished(oldPc))

        val done = SetupQuestionnaire.parse(
            progressBody(version = 2, completedVersion = 2, completedAt = 1_765_000_000.0),
        )!!
        assertTrue(SetupQuestionnaire.finished(done))
        assertEquals(
            "Finished ${SetupQuestionnaire.dateText(1_765_000_000.0)}.",
            SetupQuestionnaire.progressWords(done),
        )
        assertNotNull(SetupQuestionnaire.dateText(1_765_000_000.0))
        assertNull(SetupQuestionnaire.dateText(null))
        assertNull(SetupQuestionnaire.dateText(0.0))

        // Finished but no date to show: no invented date either.
        val doneNoDate = SetupQuestionnaire.parse(progressBody(version = 2, completedVersion = 2))!!
        assertEquals("Finished.", SetupQuestionnaire.progressWords(doneNoDate))
    }

    // -- Read-only on purpose -------------------------------------------------

    @Test
    fun theTwoPhoneFilesHoldNoApplyPathNoConfirmBodyAndNoProgressWrite() {
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
        // The routes and the body fields stay on the PC: this app can only read
        // and ask for the read-only plan, and only READ where the card is -
        // recording it is the card's own state (ARCHITECTURE.md section 8).
        for (source in listOf(net, plate)) {
            assertFalse(source.contains("/api/setup/apply"))
            assertFalse(source.contains("confirm"))
            assertFalse(source.contains("setupApply"))
            assertFalse(source.contains("applyBody"))
            assertFalse(source.contains("/api/setup/progress"))
            assertFalse(source.contains("setupProgress"))
            assertFalse(source.contains("progressBody"))
        }
        assertTrue(net.contains(SetupQuestionnaire.PLAN_PATH))
        assertTrue(net.contains("progressWords"))
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
