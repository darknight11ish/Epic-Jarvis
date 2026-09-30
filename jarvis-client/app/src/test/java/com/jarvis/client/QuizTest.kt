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
    fun theBoolHelpersAreImportedAndUsed() {
        // Keeps the kotlinx helpers this file relies on honest.
        assertTrue(obj("""{"a":true}""")["a"]!!.jsonPrimitive.boolean)
        assertTrue(obj("""{"a":{"b":1}}""")["a"]!!.jsonObject.isNotEmpty())
    }
}
