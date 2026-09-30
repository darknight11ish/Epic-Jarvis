package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Quiz
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Quiz me on a text" on the phone (docs/STUDY-FROM-TEXT-DESIGN.md section
 * 11; [Quiz]). The shapes read here are the frozen contract's; the PC side
 * of the same contract is `backend/test_quiz.py`.
 */
class QuizTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val quizJson = """{"ok":true,"quiz":{"id":"q-abc123","title":"Bees","grader_verified":false,
        "questions":[
          {"n":2,"kind":"explain","prompt":"Why do bees dance?","mark":null},
          {"n":1,"kind":"recall","prompt":"How many wings?",
           "mark":{"level":"got_it","comment":"Right.","passage":"Bees have four wings."}},
          {"n":0,"kind":"recall","prompt":"dropped: n is not 1 or more"},
          {"n":3,"kind":"apply"},
          "not an object"
        ],"answered":1,"extra_field":{"ignored":true}}}"""

    @Test
    fun aQuizIsReadOrderedAndBadRowsAreDropped() {
        val q = Quiz.parseQuiz(obj(quizJson))!!
        assertEquals("q-abc123", q.id)
        assertEquals("Bees", q.title)
        assertFalse(q.graderVerified)
        assertEquals(listOf(1, 2), q.questions.map { it.n })
        assertEquals(1, q.answered)
        assertEquals("got_it", q.questions[0].mark?.level)
        assertEquals("Bees have four wings.", q.questions[0].mark?.passage)
        assertNull(q.questions[1].mark)
        assertEquals(2, Quiz.next(q)?.n)
    }

    @Test
    fun aMissingVerifiedFlagStaysUnverifiedAndAVerifiedOneIsTrusted() {
        assertFalse(Quiz.parseQuiz(obj("""{"quiz":{"id":"a1","questions":[]}}"""))!!.graderVerified)
        assertTrue(
            Quiz.parseQuiz(obj("""{"quiz":{"id":"a1","grader_verified":true,"questions":[]}}"""))!!.graderVerified,
        )
        // A string "true" is not a boolean: it does not switch the honest label off.
        assertFalse(
            Quiz.parseQuiz(obj("""{"quiz":{"id":"a1","grader_verified":"true","questions":[]}}"""))!!.graderVerified,
        )
    }

    @Test
    fun malformedQuizzesAreNullNeverACrash() {
        assertNull(Quiz.parseQuiz(obj("""{"ok":true}""")))
        assertNull(Quiz.parseQuiz(obj("""{"quiz":"x"}""")))
        assertNull(Quiz.parseQuiz(obj("""{"quiz":{"questions":[]}}""")))
        assertNull(Quiz.parseQuiz(obj("""{"quiz":{"id":"../etc","questions":[]}}""")))
        assertNull(Quiz.parseQuiz(obj("""{"quiz":{"id":"a1"}}""")))
        // A mark with a level this phone does not know is not a mark.
        val q = Quiz.parseQuiz(
            obj("""{"quiz":{"id":"a1","questions":[{"n":1,"prompt":"p","mark":{"level":"perfect","comment":"c"}}]}}"""),
        )!!
        assertNull(q.questions[0].mark)
        // "answered" beyond the question count is clamped.
        assertEquals(
            1,
            Quiz.parseQuiz(obj("""{"quiz":{"id":"a1","answered":99,"questions":[{"n":1,"prompt":"p"}]}}"""))!!.answered,
        )
    }

    @Test
    fun anAnswerNeedsBothTheMarkAndTheQuiz() {
        val ok = Quiz.parseAnswered(
            obj(
                """{"ok":true,"mark":{"level":"partly","comment":"Close.","passage":"p"},
                    "quiz":{"id":"a1","questions":[{"n":1,"prompt":"q"}]}}""",
            ),
        )!!
        assertEquals("partly", ok.first.level)
        assertEquals("a1", ok.second.id)
        assertNull(Quiz.parseAnswered(obj("""{"ok":true,"quiz":{"id":"a1","questions":[]}}""")))
        assertNull(Quiz.parseAnswered(obj("""{"ok":true,"mark":{"level":"got_it"}}""")))
    }

    @Test
    fun aCrisisAnswerHasTheOnesWordsAndNoMark() {
        val body = obj(
            """{"ok":true,"crisis":true,"message":"Words from the PC.\n\nCall **988** any time.",
                "quiz":{"id":"a1","questions":[{"n":1,"prompt":"q","mark":null}]}}""",
        )
        val a = Quiz.parseAnswer(body)!!
        assertNull(a.mark)
        assertEquals("Words from the PC.\n\nCall **988** any time.", a.crisis)
        assertNull(a.quiz.questions[0].mark)
        // The help words are the PC's: a crisis flag with none, or with no quiz, is unreadable.
        assertNull(Quiz.parseAnswer(obj("""{"ok":true,"crisis":true,"quiz":{"id":"a1","questions":[]}}""")))
        assertNull(Quiz.parseAnswer(obj("""{"ok":true,"crisis":true,"message":"x"}""")))
        // An ordinary answer is a mark and no crisis; crisis:false is an ordinary answer.
        val plain = Quiz.parseAnswer(
            obj("""{"ok":true,"crisis":false,"mark":{"level":"got_it"},"quiz":{"id":"a1","questions":[]}}"""),
        )!!
        assertEquals("got_it", plain.mark!!.level)
        assertNull(plain.crisis)
        assertNull(Quiz.parseAnswer(obj("""{"ok":true,"quiz":{"id":"a1","questions":[]}}""")))
        // Through the outcome: ok, with the words, and no mark.
        val out = Quiz.answeredSaid(Quiz.Reply(200, body))
        assertTrue(out.ok)
        assertNull(out.value!!.mark)
        assertNotNull(out.value!!.crisis)
    }

    @Test
    fun theHelpWordsAreDrawnAsParagraphsOfRuns() {
        val p = Quiz.crisisParagraphs("A **988** b.\n\nSecond.")
        assertEquals(2, p.size)
        assertEquals(
            listOf(Quiz.Run("A ", false), Quiz.Run("988", true), Quiz.Run(" b.", false)),
            p[0],
        )
        assertEquals(listOf(Quiz.Run("Second.", false)), p[1])
        assertTrue(Quiz.crisisParagraphs("").isEmpty())
    }

    @Test
    fun theSummaryIsReadSortedAndTolerant() {
        val s = Quiz.parseSummary(
            obj("""{"ok":true,"summary":{"counts":{"got_it":2,"partly":1,"not_yet":2},"again":[4,2,2,0,"x",3.0]}}"""),
        )!!
        assertEquals(2, s.gotIt)
        assertEquals(1, s.partly)
        assertEquals(2, s.notYet)
        assertEquals(listOf(2, 3, 4), s.again)
        assertNull(Quiz.parseSummary(obj("""{"ok":true}""")))
        assertNull(Quiz.parseSummary(obj("""{"summary":{"again":[1]}}""")))
        val bare = Quiz.parseSummary(obj("""{"summary":{"counts":{}}}"""))!!
        assertEquals(0, bare.gotIt)
        assertTrue(bare.again.isEmpty())
    }

    @Test
    fun theBodiesAreTheContractsAndAreTrimmed() {
        val start = obj(Quiz.startBody("  hello  ", 5))
        assertEquals("hello", start["text"]!!.jsonPrimitive.content)
        assertEquals(5, start["count"]!!.jsonPrimitive.int)
        val answer = obj(Quiz.answerBody(3, "  four  "))
        assertEquals(3, answer["n"]!!.jsonPrimitive.int)
        assertEquals("four", answer["answer"]!!.jsonPrimitive.content)
        assertEquals("{}", Quiz.EMPTY_BODY)
    }

    @Test
    fun theLimitsAreTheContractsLimits() {
        assertFalse(Quiz.validText("a".repeat(199)))
        assertTrue(Quiz.validText("a".repeat(200)))
        assertTrue(Quiz.validText("a".repeat(20000)))
        assertFalse(Quiz.validText("a".repeat(20001)))
        // Spaces around the text do not count toward the minimum.
        assertFalse(Quiz.validText(" ".repeat(50) + "a".repeat(199) + " ".repeat(50)))
        assertFalse(Quiz.validAnswer("   "))
        assertTrue(Quiz.validAnswer("x"))
        assertTrue(Quiz.validAnswer("x".repeat(2000)))
        assertFalse(Quiz.validAnswer("x".repeat(2001)))
        assertFalse(Quiz.validCount(0))
        assertTrue(Quiz.validCount(1))
        assertTrue(Quiz.validCount(10))
        assertFalse(Quiz.validCount(11))
        assertTrue(Quiz.validId("q-abc_123"))
        assertFalse(Quiz.validId("a/b"))
        assertFalse(Quiz.validId(""))
        assertFalse(Quiz.validId(null))
    }

    @Test
    fun everyContractErrorCodeHasPlainWords() {
        val codes = listOf(
            Quiz.E_TEXT_SHORT, Quiz.E_TEXT_LONG, Quiz.E_BAD_COUNT, Quiz.E_TOO_MANY, Quiz.E_NOT_FOUND,
            Quiz.E_BAD_QUESTION, Quiz.E_ANSWERED, Quiz.E_ANSWER_EMPTY, Quiz.E_ANSWER_LONG, Quiz.E_MODEL,
        )
        assertEquals(
            listOf(
                "text_too_short", "text_too_long", "bad_count", "too_many_quizzes", "not_found",
                "bad_question", "already_answered", "answer_empty", "answer_too_long", "model_unavailable",
            ),
            codes,
        )
        codes.forEach { c ->
            val words = Quiz.messageFor(c)
            assertNotNull(c, words)
            // Plain words: no snake_case code leaks into the sentence.
            assertFalse(c, words!!.contains("_"))
        }
        assertNull(Quiz.messageFor("something_new"))
        assertNull(Quiz.messageFor(null))
        assertTrue(Quiz.messageFor(Quiz.E_MODEL)!!.contains("Nothing was lost"))
    }

    @Test
    fun aRefusalIsSaidByItsCodeNotItsStatus() {
        val tooShort = Quiz.Reply(400, obj("""{"ok":false,"error":"text_too_short","message":"x"}"""))
        assertEquals(Quiz.messageFor("text_too_short"), Quiz.refusalSaid(tooShort, "Not started."))
        // A 404 with the not_found code is a quiz that ended; a bare 404 is a PC without quizzes.
        val gone = Quiz.Reply(404, obj("""{"ok":false,"error":"not_found","message":"x"}"""))
        assertTrue(Quiz.readSaid(gone).gone)
        assertEquals(Quiz.messageFor("not_found"), Quiz.readSaid(gone).said)
        val noRoute = Quiz.Reply(404, null)
        assertFalse(Quiz.readSaid(noRoute).gone)
        assertEquals(Quiz.TOO_OLD, Quiz.readSaid(noRoute).said)
        assertEquals(Quiz.TOO_OLD, Quiz.startedSaid(Quiz.Reply(501, null)).said)
        // An unknown code falls back to the PC's own message, capitalised, after the lead.
        val odd = Quiz.Reply(400, obj("""{"ok":false,"error":"odd","message":"the moon is wrong"}"""))
        assertEquals("Not started. The moon is wrong", Quiz.refusalSaid(odd, "Not started."))
        // Nothing readable at all still gives a sentence.
        assertEquals("Not started. Your PC answered 500.", Quiz.refusalSaid(Quiz.Reply(500, null), "Not started."))
        assertTrue(Quiz.missing(ApiError.NotFound))
        assertTrue(Quiz.missing(ApiError.Server(501, "")))
        assertFalse(Quiz.missing(ApiError.NotAvailable))
    }

    @Test
    fun theOutcomesFollowTheReply() {
        val started = Quiz.startedSaid(Quiz.Reply(200, obj(quizJson)))
        assertTrue(started.ok)
        assertEquals("q-abc123", started.value!!.id)
        // A quiz with no questions is not a started quiz.
        assertFalse(Quiz.startedSaid(Quiz.Reply(200, obj("""{"ok":true,"quiz":{"id":"a1","questions":[]}}"""))).ok)
        // ok:false in a 200 is a refusal.
        assertFalse(Quiz.startedSaid(Quiz.Reply(200, obj("""{"ok":false,"error":"bad_count"}"""))).ok)
        assertTrue(Quiz.stoppedSaid(Quiz.Reply(200, obj("""{"ok":true}"""))).ok)
        assertTrue(Quiz.finishedSaid(Quiz.Reply(200, obj("""{"ok":true,"summary":{"counts":{"got_it":1}}}"""))).ok)
        // A success the phone cannot read is said plainly, never a crash.
        val unreadable = Quiz.finishedSaid(Quiz.Reply(200, obj("""{"ok":true}""")))
        assertFalse(unreadable.ok)
        assertTrue(unreadable.said.contains(Quiz.UNREADABLE))
        assertFalse(Quiz.answeredSaid(Quiz.Reply(200, null)).ok)
        val busy = Quiz.answeredSaid(Quiz.Reply(503, obj("""{"ok":false,"error":"model_unavailable"}""")))
        assertEquals(Quiz.messageFor("model_unavailable"), busy.said)
    }

    @Test
    fun theSharedWordsAreWordForWord() {
        assertEquals("Quiz me on a text", Quiz.TITLE)
        assertEquals("Write questions", Quiz.START)
        assertEquals("Check my answer", Quiz.ANSWER)
        assertEquals("Jarvis's guess", Quiz.GUESS)
        assertEquals("Finish", Quiz.FINISH)
        assertEquals("Stop and forget this quiz", Quiz.STOP)
        assertEquals("Look at these again", Quiz.SUMMARY_TITLE)
        assertEquals("Nothing to look at again.", Quiz.SUMMARY_EMPTY)
        assertEquals("This text is treated as outside text: Jarvis never learns facts from it.", Quiz.OUTSIDE_TEXT)
        assertEquals(
            "Paste some text and Jarvis writes a few questions about it. Your answers are marked by the model " +
                "on this PC. Nothing is saved or learned, and nothing leaves this PC.",
            Quiz.INTRO,
        )
        assertEquals("Got it", Quiz.levelWords("got_it"))
        assertEquals("Partly", Quiz.levelWords("partly"))
        assertEquals("Not yet", Quiz.levelWords("not_yet"))
    }

    @Test
    fun theGuessLabelStaysUntilTheGraderIsVerified() {
        val m = Quiz.Mark("partly", "c", "p")
        assertEquals("Partly - Jarvis's guess", Quiz.markLine(m, verified = false))
        assertEquals("Partly", Quiz.markLine(m, verified = true))
    }

    @Test
    fun hidingBlanksEveryQuestionAndMark() {
        val q = Quiz.parseQuiz(obj(quizJson))!!
        val h = Quiz.hide(q)
        assertEquals("", h.title)
        assertTrue(h.questions.all { it.prompt == Quiz.HIDDEN_TEXT })
        val mark = h.questions.first { it.mark != null }.mark!!
        assertEquals("", mark.comment)
        assertEquals("", mark.passage)
        // The level and the ids survive, so Finish and Stop still work blind.
        assertEquals("got_it", mark.level)
        assertEquals(q.id, h.id)
    }

    @Test
    fun theWordsMatchTheDesktopsWordForWord() {
        assertEquals("Remember", Quiz.kindWords("recall"))
        assertEquals("Explain why", Quiz.kindWords("explain"))
        assertEquals("Apply", Quiz.kindWords("apply"))
        assertEquals("Close", Quiz.CLOSE)
        assertEquals("(hidden)", Quiz.HIDDEN_TEXT)
        assertEquals("Your PC's Jarvis does not have Quiz yet - run apply-patches.ps1 on the PC.", Quiz.MISSING)
        assertEquals(Quiz.MISSING, Quiz.TOO_OLD)
        val q = Quiz.parseQuiz(obj(quizJson))!!
        assertEquals("Question 2 of 2 · 1 answered", Quiz.progressLine(q))
        val done = q.copy(questions = q.questions.map { it.copy(mark = Quiz.Mark("partly", "", "")) })
        assertEquals("All 2 answered", Quiz.progressLine(done))
        assertEquals("", Quiz.progressLine(null))
        assertEquals("2 Got it · 1 Partly · 0 Not yet", Quiz.countsLine(Quiz.Summary(2, 1, 0, emptyList())))
    }

    @Test
    fun theSummaryListsThePromptsIncludingSkippedOnes() {
        val q = Quiz.parseQuiz(obj(quizJson))!!
        // Question 2 was never answered: the PC lists it under "again" all the same.
        assertEquals("2. Why do bees dance?", Quiz.againLine(2, q.questions, hidden = false))
        assertEquals("2. (hidden)", Quiz.againLine(2, q.questions, hidden = true))
        assertEquals("9. (hidden)", Quiz.againLine(9, q.questions, hidden = false))
        val s = Quiz.parseSummary(obj("""{"ok":true,"summary":{"counts":{"got_it":1,"partly":0,"not_yet":0},"again":[3,2,2]}}"""))!!
        assertEquals(listOf(2, 3), s.again)
    }

    @Test
    fun thePasteCountIsOfTheTrimmedTextAndNeverCutShort() {
        assertEquals("0 / 20,000 characters · at least 200 needed", Quiz.textNote(""))
        // 250 spaces are 0 characters to the PC.
        assertEquals(0, Quiz.textLength(" ".repeat(250)))
        assertFalse(Quiz.validText(" ".repeat(250)))
        assertEquals("250 / 20,000 characters", Quiz.textNote("x".repeat(250)))
        // Over the limit: the real count and "too long" show, and Write questions stays off.
        val long = "x".repeat(Quiz.MAX_TEXT + 5)
        assertEquals("20,005 / 20,000 characters · too long", Quiz.textNote(long))
        assertFalse(Quiz.validText(long))
        assertEquals(Quiz.MAX_TEXT + 5, Quiz.textLength(long))
        assertTrue(Quiz.messageFor(Quiz.E_TEXT_LONG)!!.contains("too long"))
        assertEquals("12 / 2000 characters", Quiz.answerNote("x".repeat(12)))
    }

    @Test
    fun theBoolHelpersAreImportedAndUsed() {
        // Keeps the kotlinx helpers this file relies on honest.
        assertTrue(obj("""{"a":true}""")["a"]!!.jsonPrimitive.boolean)
        assertTrue(obj("""{"a":{"b":1}}""")["a"]!!.jsonObject.isNotEmpty())
    }

    // ---- Spanish practice and Keep (docs/QUIZ-DECKS-DESIGN.md, contract C2-C3, C5) ----

    private val spanishJson = """{"ok":true,"quiz":{"id":"q-es1","title":"Plantas","grader_verified":false,
        "mode":"spanish","level":"B1","key_source":"model","notice":"Jarvis cannot recognise a crisis message written in Spanish.",
        "questions":[
          {"n":1,"kind":"blank","prompt":"Ella _____ en casa.","mark":
            {"level":"partly","comment":"Close.","passage":"Ella está en casa.","marked_by":"code",
             "expected":"está","key_label":"Answer key written by the model"}},
          {"n":2,"kind":"translate","prompt":"I am hungry.","mark":
            {"level":"got_it","comment":"Yes.","passage":"Tengo hambre.","marked_by":"model","expected":"Tengo hambre."}},
          {"n":3,"kind":"complete","prompt":"Me gusta ...","mark":null},
          {"n":4,"kind":"recall","prompt":"Old kind","mark":null}
        ],"answered":2,"more":1}}"""

    @Test
    fun aSpanishQuizIsReadWithItsModeLevelKeyAndNotice() {
        val q = Quiz.parseQuiz(obj(spanishJson))!!
        assertEquals("spanish", q.mode)
        assertTrue(q.modeKnown)
        assertEquals("B1", q.level)
        assertEquals("model", q.keySource)
        assertEquals("Jarvis cannot recognise a crisis message written in Spanish.", q.notice)
        val blank = q.questions[0].mark!!
        assertEquals("code", blank.markedBy)
        assertEquals("está", blank.expected)
        assertEquals("Answer key written by the model", blank.keyLabel)
        assertEquals("model", q.questions[1].mark!!.markedBy)
        assertNull(q.questions[1].mark!!.keyLabel)
        assertEquals("Level B1 (roughly)", Quiz.levelLine(q.level!!))
        assertEquals("Example sentence", Quiz.passageHeading(q))
        assertEquals("From the text", Quiz.passageHeading(q.copy(keySource = "text")))
    }

    @Test
    fun aReplyWithNoModeIsAnOlderPcAndATextQuiz() {
        val q = Quiz.parseQuiz(obj(quizJson))!!
        assertFalse(q.modeKnown)
        assertEquals("text", q.mode)
        assertNull(q.level)
        assertNull(q.keySource)
        assertNull(q.notice)
        assertEquals(
            "Your PC's Jarvis does not have Spanish practice yet - run apply-patches.ps1 on the PC.",
            Quiz.OLD_PC,
        )
        // A notice on a text quiz is not shown; an unknown level or key source is dropped.
        val odd = Quiz.parseQuiz(
            obj("""{"quiz":{"id":"a1","mode":"text","level":"Z9","key_source":"web","notice":"x","questions":[]}}"""),
        )!!
        assertTrue(odd.modeKnown)
        assertNull(odd.level)
        assertNull(odd.keySource)
        assertNull(odd.notice)
    }

    @Test
    fun theGuessLabelShowsOnlyForAModelMarkOnAnUnverifiedGrader() {
        val model = Quiz.Mark("partly", "c", "p", markedBy = "model")
        val code = Quiz.Mark("partly", "c", "p", markedBy = "code")
        assertEquals("Partly - Jarvis's guess", Quiz.markLine(model, verified = false))
        assertEquals("Partly", Quiz.markLine(model, verified = true))
        assertEquals("Partly", Quiz.markLine(code, verified = false))
        // A missing marked_by fails toward showing the label.
        val bare = Quiz.parseQuiz(
            obj("""{"quiz":{"id":"a1","questions":[{"n":1,"prompt":"p","mark":{"level":"got_it"}}]}}"""),
        )!!.questions[0].mark!!
        assertEquals("model", bare.markedBy)
        assertEquals("Got it - Jarvis's guess", Quiz.markLine(bare, verified = false))
    }

    @Test
    fun theSpanishWordsAreTheContractsWordsForWord() {
        assertEquals("Text", Quiz.MODE_TEXT_LABEL)
        assertEquals("Spanish practice", Quiz.MODE_SPANISH_LABEL)
        assertEquals("Level (roughly)", Quiz.LEVEL_HEADING)
        assertEquals(listOf("A1", "A2", "B1", "B2", "C1", "C2"), Quiz.LEVELS)
        assertEquals(
            listOf("Translate", "Fill the blank", "Finish the sentence", "Mixed"),
            Quiz.EXERCISES.map { it.second },
        )
        assertEquals(listOf("translate", "blank", "complete", "mixed"), Quiz.EXERCISES.map { it.first })
        assertEquals("Topic (optional)", Quiz.TOPIC_LABEL)
        assertEquals("Paste Spanish text (optional)", Quiz.SPANISH_HINT)
        assertEquals("Answer: ", Quiz.ANSWER_PREFIX)
        assertEquals(listOf("á", "é", "í", "ó", "ú", "ñ", "ü", "¿", "¡"), Quiz.ACCENTS)
        assertEquals("Translate", Quiz.kindWords("translate"))
        assertEquals("Fill the blank", Quiz.kindWords("blank"))
        assertEquals("Finish the sentence", Quiz.kindWords("complete"))
        assertEquals("Keep these questions", Quiz.KEEP_OPEN)
        assertEquals("Keep and finish", Quiz.KEEP_DO)
        assertEquals("Cancel", Quiz.CANCEL)
        assertEquals("Type the answer in your own words", Quiz.KEEP_HINT)
        assertEquals("Turn off Hide memory lists to keep questions", Quiz.KEEP_HIDDEN)
        assertEquals("New deck", Quiz.NEW_DECK)
        assertEquals("Deck name", Quiz.DECK_NAME)
        assertEquals("Choose a deck", Quiz.CHOOSE_DECK)
        assertEquals("Kept 3 questions", Quiz.keptLine(3))
        assertEquals("Kept 1 question", Quiz.keptLine(1))
    }

    @Test
    fun theSpanishStartBodyCarriesOnlyWhatWasChosen() {
        val b = obj(Quiz.startSpanishBody("  ", "B1", "blank", "  food  ", 5))
        assertEquals("spanish", b["mode"]!!.jsonPrimitive.content)
        assertEquals("B1", b["level"]!!.jsonPrimitive.content)
        assertEquals("blank", b["exercise"]!!.jsonPrimitive.content)
        assertEquals("food", b["topic"]!!.jsonPrimitive.content)
        assertEquals(5, b["count"]!!.jsonPrimitive.int)
        // Blank text is not sent (the model writes the sentences).
        assertFalse(b.containsKey("text"))
        val withText = obj(Quiz.startSpanishBody(" Hola ", "A2", "mixed", "", 5))
        assertEquals("Hola", withText["text"]!!.jsonPrimitive.content)
        assertFalse(withText.containsKey("topic"))
        // A topic is cut to 60; an unknown level or exercise is not sent.
        val long = obj(Quiz.startSpanishBody("", "Z9", "nope", "x".repeat(80), 5))
        assertEquals(60, long["topic"]!!.jsonPrimitive.content.length)
        assertFalse(long.containsKey("level"))
        assertFalse(long.containsKey("exercise"))
        // Text mode is unchanged: no mode, level, exercise or topic.
        val text = obj(Quiz.startBody("hello", 5))
        assertEquals(setOf("text", "count"), text.keys)
        assertTrue(Quiz.validSpanishText(""))
        assertTrue(Quiz.validSpanishText("   "))
        assertFalse(Quiz.validSpanishText("too short"))
        assertTrue(Quiz.validSpanishText("x".repeat(200)))
    }

    @Test
    fun anAccentGoesInAtTheCursorAndNeverPastTheLimit() {
        assertEquals("ma" + "ñ" + "ana" to 3, Quiz.insertAt("maana", 2, 2, "ñ"))
        // A selection is replaced; the cursor may be given either way round.
        assertEquals("aéa" to 2, Quiz.insertAt("abca", 3, 1, "é"))
        // Out-of-range cursors are clamped.
        assertEquals("¿hola" to 1, Quiz.insertAt("hola", -5, -5, "¿"))
        assertEquals("hola¡" to 5, Quiz.insertAt("hola", 99, 99, "¡"))
        // At the limit nothing is cut silently: the button does nothing.
        assertNull(Quiz.insertAt("x".repeat(Quiz.MAX_ANSWER), 3, 3, "á"))
        assertEquals(Quiz.MAX_ANSWER, Quiz.insertAt("x".repeat(Quiz.MAX_ANSWER - 1), 3, 3, "á")!!.first.length)
    }

    @Test
    fun theKeepBodyCarriesOnlyNumbersAndBacks() {
        val cards = listOf(Quiz.KeepCard(2, "the back"), Quiz.KeepCard(3, ""))
        val existing = obj(Quiz.keepBody("d1a2b3c4d5e6", null, cards)!!)["keep"]!!.jsonObject
        assertEquals("d1a2b3c4d5e6", existing["deck"]!!.jsonPrimitive.content)
        assertFalse(existing.containsKey("new_deck"))
        val list = existing["cards"] as kotlinx.serialization.json.JsonArray
        assertEquals(2, list.size)
        // Only n and answer: an app cannot put other text on a card.
        assertEquals(setOf("n", "answer"), list[0].jsonObject.keys)
        assertEquals(2, list[0].jsonObject["n"]!!.jsonPrimitive.int)
        assertEquals("the back", list[0].jsonObject["answer"]!!.jsonPrimitive.content)
        assertEquals("", list[1].jsonObject["answer"]!!.jsonPrimitive.content)
        // A new deck: deck is null and new_deck is the trimmed name.
        val fresh = obj(Quiz.keepBody(null, "  Plants  ", cards)!!)["keep"]!!.jsonObject
        assertTrue(fresh["deck"] is kotlinx.serialization.json.JsonNull)
        assertEquals("Plants", fresh["new_deck"]!!.jsonPrimitive.content)
        // Refused before sending: nothing ticked, a name of 0 or 61 characters, a back over 2,000,
        // a repeated question, a deck id that is not safe in a URL.
        assertNull(Quiz.keepBody(null, "Plants", emptyList()))
        assertNull(Quiz.keepBody(null, "   ", cards))
        assertNull(Quiz.keepBody(null, "x".repeat(61), cards))
        assertNotNull(Quiz.keepBody(null, "x".repeat(60), cards))
        assertNull(Quiz.keepBody(null, "Plants", listOf(Quiz.KeepCard(1, "x".repeat(2001)))))
        assertNull(Quiz.keepBody(null, "Plants", listOf(Quiz.KeepCard(1, "a"), Quiz.KeepCard(1, "b"))))
        assertNull(Quiz.keepBody("../x", null, cards))
        assertEquals("Plants", Quiz.defaultDeckName("  Plants  "))
        assertEquals(60, Quiz.defaultDeckName("y".repeat(90)).length)
    }

    @Test
    fun aKeepSuccessSaysHowManyWereKept() {
        val ok = Quiz.finishedKeepSaid(
            Quiz.Reply(200, obj("""{"ok":true,"summary":{"counts":{"got_it":1,"partly":1,"not_yet":0},"again":[2]},"kept":2}""")),
        )
        assertTrue(ok.ok)
        assertEquals(2, ok.value!!.kept)
        assertEquals(1, ok.value!!.summary!!.gotIt)
        assertNull(ok.value!!.crisis)
        // A plain finish (no keep) has no count.
        val plain = Quiz.finishedKeepSaid(
            Quiz.Reply(200, obj("""{"ok":true,"summary":{"counts":{"got_it":0,"partly":0,"not_yet":0},"again":[]}}""")),
        )
        assertNull(plain.value!!.kept)
        assertFalse(Quiz.finishedKeepSaid(Quiz.Reply(200, obj("""{"ok":true}"""))).ok)
    }

    @Test
    fun aCrisisPhraseInABackKeepsNothingAndLeavesTheQuizOpen() {
        val out = Quiz.finishedKeepSaid(
            Quiz.Reply(
                200,
                obj(
                    """{"ok":true,"crisis":true,"message":"Words from the PC.","quiz":
                        {"id":"a1","questions":[{"n":1,"prompt":"q","mark":{"level":"got_it"}}]}}""",
                ),
            ),
        )
        assertTrue(out.ok)
        assertEquals("Words from the PC.", out.value!!.crisis)
        assertNull(out.value!!.summary)
        assertNull(out.value!!.kept)
        assertEquals("a1", out.value!!.quiz!!.id)
        // The help words are the PC's: a crisis flag with none, or with no quiz, is unreadable.
        assertFalse(Quiz.finishedKeepSaid(Quiz.Reply(200, obj("""{"ok":true,"crisis":true,"quiz":{"id":"a1","questions":[]}}"""))).ok)
        assertFalse(Quiz.finishedKeepSaid(Quiz.Reply(200, obj("""{"ok":true,"crisis":true,"message":"x"}"""))).ok)
    }

    @Test
    fun everyKeepRefusalShowsThePcsMessageAndKeepsItsCode() {
        val codes = listOf(
            400 to "nothing_to_keep", 400 to "bad_question", 400 to "answer_too_long", 400 to "answer_empty",
            400 to "bad_deck_name", 404 to "deck_not_found", 409 to "duplicate_card", 409 to "too_many_decks",
            409 to "deck_full", 503 to "deck_unavailable",
        )
        codes.forEach { (status, code) ->
            val withMessage = Quiz.finishedKeepSaid(
                Quiz.Reply(status, obj("""{"ok":false,"error":"$code","message":"the PC's own words"}""")),
            )
            assertFalse(code, withMessage.ok)
            assertEquals(code, "The PC's own words", withMessage.said)
            assertEquals(code, withMessage.code)
            // No message of its own: this phone's plain words for the code, never the code itself.
            val bare = Quiz.finishedKeepSaid(Quiz.Reply(status, obj("""{"ok":false,"error":"$code"}""")))
            assertTrue(code, bare.said.isNotEmpty())
            assertFalse(code, bare.said.contains("_"))
            // A deck that is gone is not a quiz that is gone.
            assertFalse(code, bare.gone)
        }
        // The quiz itself ending is.
        assertTrue(Quiz.finishedKeepSaid(Quiz.Reply(404, obj("""{"ok":false,"error":"not_found","message":"x"}"""))).gone)
    }
}
