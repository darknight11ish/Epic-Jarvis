package com.jarvis.client

import com.jarvis.client.net.Decks
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Quiz
import kotlinx.serialization.json.JsonObject
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
import java.io.File

/**
 * "My study decks" on the phone (docs/QUIZ-DECKS-DESIGN.md, "Slice contract
 * (frozen)", C1-C6; [Decks]). The shapes read here are the frozen contract's;
 * the PC side of the same contract is `backend/test_decks.py`. The words and
 * the worked examples are read from contract/decks-cases.json, which
 * tools/gen_decks_cases.py writes and the desktop's tests read as well.
 */
class DecksTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val listJson = """{"ok":true,"available":true,"why":"",
        "decks":[{"id":"d1a2b3c4d5e6","name":"Plants","cards":8,"ready":3,"paused":false,"kind":"study"},
                 {"id":"d2","name":"Spanish","cards":1,"ready":0,"paused":true,"kind":"spanish","future":1},
                 {"id":"../bad","name":"dropped"},"not an object"],
        "ready":3,"new_per_day":5,"new_left":2,"next_ready_day":"2026-10-03","line":"3 cards ready",
        "limits":{"decks":20,"cards":1000,"name":60,"front":500,"back":2000,"new_per_day":20},"extra":true}"""

    // ------------------------------------------------------------ parsing ----

    @Test
    fun theDeckListIsReadAndBadRowsAreDropped() {
        val v = Decks.parseList(obj(listJson))!!
        assertTrue(v.available)
        assertEquals(listOf("d1a2b3c4d5e6", "d2"), v.decks.map { it.id })
        assertEquals("Plants", v.decks[0].name)
        assertEquals(8, v.decks[0].cards)
        assertEquals(3, v.decks[0].ready)
        assertFalse(v.decks[0].paused)
        assertTrue(v.decks[1].paused)
        assertEquals("spanish", v.decks[1].kind)
        assertEquals(3, v.ready)
        assertEquals(5, v.newPerDay)
        assertEquals(2, v.newLeft)
        assertEquals("2026-10-03", v.nextReadyDay)
        assertEquals("3 cards ready", v.line)
        assertEquals(60, v.limits.name)
        assertEquals(2000, v.limits.back)
    }

    @Test
    fun anUnavailableListKeepsItsWhyAndItsCounts() {
        val v = Decks.parseList(
            obj("""{"ok":true,"available":false,"why":"No key in Credential Manager.","decks":[],"ready":2,"line":"2 cards ready","next_ready_day":null}"""),
        )!!
        assertFalse(v.available)
        assertEquals("No key in Credential Manager.", v.why)
        assertTrue(v.decks.isEmpty())
        assertEquals("2 cards ready", v.line)
        assertNull(v.nextReadyDay)
        // A missing "available" is not "available": nothing is offered on a guess.
        assertFalse(Decks.parseList(obj("""{"ok":true,"decks":[]}"""))!!.available)
        // Missing limits fall back to the contract's numbers.
        assertEquals(20, v.limits.decks)
        assertEquals(500, v.limits.front)
    }

    @Test
    fun malformedListsAreNullNeverACrash() {
        assertNull(Decks.parseList(obj("""{"ok":true}""")))
        assertNull(Decks.parseList(obj("""{}""")))
        val odd = Decks.parseList(obj("""{"available":true,"decks":"x","ready":"3","new_per_day":99}"""))!!
        assertTrue(odd.decks.isEmpty())
        // A string is not a count; the day setting is clamped to 0..20.
        assertEquals(0, odd.ready)
        assertEquals(20, odd.newPerDay)
    }

    @Test
    fun cardsAreReadInFullAndABackMayBeEmpty() {
        val v = Decks.parseCards(
            obj(
                """{"ok":true,"deck":{"id":"d1","name":"Plants"},"cards":[
                  {"id":"c1","front":"What absorbs sunlight?","back":"Chlorophyll","passage":"Plants use chlorophyll.",
                   "kind":"recall","level":null,"key_source":"text","key_label":null,"new":true,"due_day":null},
                  {"id":"c2","front":"Ella _____ en casa.","back":"","passage":"Ella está en casa.","kind":"blank",
                   "level":"A2","key_source":"model","key_label":"Answer key written by the model","new":false,"due_day":"2026-10-03"},
                  {"id":"bad id","front":"x"}, 7]}""",
            ),
        )!!
        assertEquals("d1", v.deckId)
        assertEquals("Plants", v.deckName)
        assertEquals(listOf("c1", "c2"), v.cards.map { it.id })
        assertTrue(v.cards[0].isNew)
        assertEquals("", v.cards[1].back)
        assertEquals("A2", v.cards[1].level)
        assertEquals("model", v.cards[1].keySource)
        assertEquals("Answer key written by the model", v.cards[1].keyLabel)
        assertEquals("2026-10-03", v.cards[1].dueDay)
        assertNull(Decks.parseCards(obj("""{"ok":true,"cards":[]}""")))
        assertNull(Decks.parseCards(obj("""{"ok":true,"deck":{"id":"d1"}}""")))
    }

    @Test
    fun aReviewIsReadFromCardOrFromNextAndOnlyShowsACardInTheCardState() {
        val got = Decks.parseReview(
            obj(
                """{"ok":true,"ready":3,"new_left":2,"state":"card","line":"3 cards ready",
                    "card":{"id":"c1","front":"What absorbs sunlight?","kind":"recall","level":null,"deck":"d1","new":true},
                    "run":{"done":0,"limit":20}}""",
            ),
        )!!
        assertEquals("card", got.state)
        assertEquals("c1", got.card!!.id)
        assertEquals("What absorbs sunlight?", got.card!!.front)
        assertTrue(got.card!!.isNew)
        assertEquals(0, got.done)
        assertEquals(20, got.limit)
        assertEquals(3, got.ready)
        // A rate reply carries the card as "next" and the day this one comes back.
        val rated = Decks.ratedSaid(
            Decks.Reply(
                200,
                obj(
                    """{"ok":true,"ready":2,"new_left":1,"state":"card","line":"2 cards ready","run":{"done":1,"limit":20},
                        "next":{"id":"c2","front":"Next?","kind":"recall","deck":"d1","new":false},"comes_back":"2026-10-03"}""",
                ),
            ),
        )
        assertTrue(rated.ok)
        assertEquals("c2", rated.value!!.card!!.id)
        assertEquals("2026-10-03", rated.value!!.comesBack)
        assertEquals(1, rated.value!!.done)
        // Other states carry no card, even if the PC sent one.
        val enough = Decks.parseReview(obj("""{"ok":true,"ready":5,"state":"enough","line":"5 cards ready","card":{"id":"c9","front":"x"}}"""))!!
        assertEquals("enough", enough.state)
        assertNull(enough.card)
        // With no state: a card means "card", none means "empty", and no ready count is unreadable.
        assertEquals("card", Decks.parseReview(obj("""{"ready":1,"card":{"id":"c1","front":"f"}}"""))!!.state)
        assertEquals("empty", Decks.parseReview(obj("""{"ready":0}"""))!!.state)
        assertNull(Decks.parseReview(obj("""{"ok":true}""")))
        // A rate with no "next" and no state is empty, not a crash.
        assertEquals("empty", Decks.ratedSaid(Decks.Reply(200, obj("""{"ok":true,"ready":0}"""))).value!!.state)
    }

    @Test
    fun aRevealCarriesTheAnswerThePassageAndTheKeyLabel() {
        val r = Decks.revealSaid(
            Decks.Reply(
                200,
                obj("""{"ok":true,"back":{"answer":"Chlorophyll","passage":"Plants use chlorophyll."},"key_label":null}"""),
            ),
        ).value!!
        assertEquals("Chlorophyll", r.answer)
        assertEquals("Plants use chlorophyll.", r.passage)
        assertNull(r.keyLabel)
        assertEquals("From the text", Decks.passageHeading(r.keyLabel))
        val model = Decks.parseReveal(
            obj("""{"ok":true,"back":{"answer":"","passage":"Ella está en casa."},"key_label":"Answer key written by the model"}"""),
        )!!
        assertEquals("", model.answer)
        assertEquals("Example sentence", Decks.passageHeading(model.keyLabel))
        assertNull(Decks.parseReveal(obj("""{"ok":true}""")))
    }

    // -------------------------------------------------------------- words ----

    // The words and the worked examples are written by tools/gen_decks_cases.py; the
    // desktop's decks.mjs reads the same file, so the two apps cannot drift apart.
    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/decks-cases.json")) {
            "contract/decks-cases.json is missing - run tools/gen_decks_cases.py"
        }.readText()
        obj(text)
    }
    private val words get() = fixture["words"]!!.jsonObject
    private fun w(key: String) = words[key]!!.jsonPrimitive.content

    @Test
    fun theWordsAreTheGeneratedFixturesWordsForWord() {
        listOf(
            "section_title" to Decks.TITLE,
            "cards_ready" to Decks.READY_HEADING,
            "nothing_ready" to Decks.NOTHING_READY,
            "new_per_day" to Decks.NEW_PER_DAY,
            "review" to Decks.REVIEW,
            "review_all" to Decks.REVIEW_ALL,
            "pause" to Decks.PAUSE,
            "resume" to Decks.RESUME,
            "delete_deck" to Decks.DELETE_DECK,
            "delete_card" to Decks.DELETE_CARD,
            "edit" to Decks.EDIT,
            "save" to Decks.SAVE,
            "cards_link" to Decks.CARDS,
            "delete" to Decks.DELETE,
            "delete_confirm" to Decks.CONFIRM_DELETE,
            "empty_state" to Decks.EMPTY,
            "review_hidden" to Decks.HIDDEN_REVIEW,
            "new_deck" to Decks.NEW_DECK,
            "deck_name" to Decks.DECK_NAME,
            "choose_deck" to Decks.CHOOSE_DECK,
            "show_answer" to Decks.SHOW_ANSWER,
            "typed_placeholder" to Decks.TYPE_HINT,
            "enough" to Decks.ENOUGH,
            "more" to Decks.DO_10_MORE,
            "stop" to Decks.STOP,
            "back_answer" to Decks.ANSWER_HEADING,
            "passage_from_text" to Decks.FROM_TEXT,
            "passage_example" to Decks.EXAMPLE_SENTENCE,
            "per_deck_note" to Decks.PER_DECK_NOTE,
            "keep_cancel" to Decks.CANCEL,
            "cards_many" to Decks.cardsWords(8),
            "cards_one" to Decks.cardsWords(1),
            "ready_row" to Decks.readyWords(3),
        ).forEach { (key, mine) -> assertEquals(key, w(key), mine) }
        assertEquals(w("cards_many") + " · " + w("ready_row"), Decks.countsLine(Decks.Deck("d1", "Plants", 8, 3, false, "study")))
        assertEquals(
            fixture["ratings"]!!.jsonArray.map { it.jsonPrimitive.content },
            Decks.RATINGS.map { it.first },
        )
        listOf("again", "hard", "good", "easy").forEach { id ->
            assertEquals(w("rating_$id"), Decks.ratingWords(id))
        }
        assertEquals(fixture["accents"]!!.jsonArray.map { it.jsonPrimitive.content }, Quiz.ACCENTS)
    }

    @Test
    fun theWorkedExamplesOfTheSmallRulesGiveTheGeneratedAnswers() {
        val ex = fixture["examples"]!!.jsonObject
        fun day(el: kotlinx.serialization.json.JsonElement): String? =
            (el as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { it.isString }?.content
        ex["format_day"]!!.jsonArray.forEach {
            val row = it.jsonArray
            assertEquals(row[1].jsonPrimitive.content, Decks.dayLabel(day(row[0])))
        }
        ex["next_ready_line"]!!.jsonArray.forEach {
            val row = it.jsonArray
            assertEquals(row[1].jsonPrimitive.content, Decks.nextReadyLine(day(row[0])))
        }
        ex["cards_label"]!!.jsonArray.forEach {
            val row = it.jsonArray
            assertEquals(row[1].jsonPrimitive.content, Decks.cardsWords(row[0].jsonPrimitive.int))
        }
        ex["kept_line"]!!.jsonArray.forEach {
            val row = it.jsonArray
            assertEquals(row[1].jsonPrimitive.content, Quiz.keptLine(row[0].jsonPrimitive.int))
        }
        // Which deck rows may start a review: ready and not paused, never while hidden or unavailable.
        ex["can_review"]!!.jsonArray.forEach {
            val row = it.jsonArray
            val d = row[0].jsonObject
            val deck = Decks.Deck(
                "d1", d["name"]!!.jsonPrimitive.content, d["cards"]!!.jsonPrimitive.int,
                d["ready"]!!.jsonPrimitive.int, d["paused"]!!.jsonPrimitive.boolean, "study",
            )
            assertEquals(
                row.toString(),
                row[3].jsonPrimitive.boolean,
                Decks.canReview(deck, available = row[1].jsonPrimitive.boolean, hidden = row[2].jsonPrimitive.boolean),
            )
        }
        ex["can_review_all"]!!.jsonArray.forEach {
            val row = it.jsonArray
            assertEquals(
                row.toString(),
                row[3].jsonPrimitive.boolean,
                Decks.canReviewAll(row[0].jsonPrimitive.int, row[1].jsonPrimitive.boolean, row[2].jsonPrimitive.boolean),
            )
        }
        // The note under the deck list: shown when the rows add up to more than the total.
        ex["per_deck_note"]!!.jsonArray.forEach {
            val row = it.jsonArray
            val decks = row[0].jsonArray.mapIndexed { i, n ->
                Decks.Deck("d$i", "n", 5, n.jsonPrimitive.int, false, "study")
            }
            val list = Decks.parseList(obj("""{"available":true,"decks":[],"ready":${row[1].jsonPrimitive.int}}"""))!!
                .copy(decks = decks)
            assertEquals(row.toString(), row[2].jsonPrimitive.boolean, Decks.perDeckNoteShown(list))
        }
    }

    @Test
    fun theFourRatingsMapInOrderToTheSharedWords() {
        assertEquals(
            listOf(
                "again" to "Didn't remember",
                "hard" to "Remembered, with effort",
                "good" to "Remembered",
                "easy" to "Easy",
            ),
            Decks.RATINGS,
        )
        assertEquals("Remembered, with effort", Decks.ratingWords("hard"))
        assertEquals("", Decks.ratingWords("perfect"))
        assertTrue(Decks.validRating("easy"))
        assertFalse(Decks.validRating("Easy"))
        val body = obj(Decks.rateBody("c1", "again")!!)
        assertEquals("c1", body["card"]!!.jsonPrimitive.content)
        assertEquals("again", body["rating"]!!.jsonPrimitive.content)
        assertNull("no scope sent unless asked", body["deck"])
        assertNull(Decks.rateBody("c1", "perfect"))
        // The scope the screen reviews: every deck is "", one deck is its id; a bad id is refused.
        assertEquals("", obj(Decks.rateBody("c1", "good", "")!!)["deck"]!!.jsonPrimitive.content)
        assertEquals("d1a2", obj(Decks.rateBody("c1", "good", "d1a2")!!)["deck"]!!.jsonPrimitive.content)
        assertNull(Decks.rateBody("c1", "good", "../bad"))
    }

    @Test
    fun daysAreFormattedForDisplayOnly() {
        assertEquals("3 Oct 2026", Decks.dayLabel("2026-10-03"))
        assertEquals("1 Jan 2027", Decks.dayLabel("2027-01-01"))
        // Anything else comes back as it was; nothing crashes.
        assertEquals("soon", Decks.dayLabel("soon"))
        assertEquals("2026-13-01", Decks.dayLabel("2026-13-01"))
        assertEquals("", Decks.dayLabel(null))
        assertEquals("Next cards ready on 3 Oct 2026", Decks.nextReadyLine("2026-10-03"))
        assertEquals("", Decks.nextReadyLine(null))
        assertEquals("Comes back on 3 Oct 2026", Decks.comesBackLine("2026-10-03"))
        assertEquals("Level B1 (roughly)", Decks.levelLine("B1"))
        assertEquals("", Decks.levelLine(null))
    }

    // ------------------------------------------------------------- bodies ----

    @Test
    fun theBodiesAndPathsAreTheContractsShapes() {
        assertEquals("Plants", obj(Decks.createBody("  Plants ")).let { it["name"]!!.jsonPrimitive.content })
        assertEquals(7, obj(Decks.settingsBody(7))["new_per_day"]!!.jsonPrimitive.int)
        assertTrue(Decks.validPerDay(0))
        assertTrue(Decks.validPerDay(20))
        assertFalse(Decks.validPerDay(21))
        assertFalse(Decks.validPerDay(-1))
        assertEquals("pause", obj(Decks.deckActBody("pause")!!)["do"]!!.jsonPrimitive.content)
        assertEquals("delete", obj(Decks.deckActBody("delete")!!)["do"]!!.jsonPrimitive.content)
        assertNull(Decks.deckActBody("explode"))
        val rename = obj(Decks.renameBody(" New "))
        assertEquals("rename", rename["do"]!!.jsonPrimitive.content)
        assertEquals("New", rename["name"]!!.jsonPrimitive.content)
        val edit = obj(Decks.cardEditBody(" Front ", "Back ")!!)
        assertEquals("edit", edit["do"]!!.jsonPrimitive.content)
        assertEquals("Front", edit["front"]!!.jsonPrimitive.content)
        assertEquals("Back ", edit["back"]!!.jsonPrimitive.content)
        assertNull(Decks.cardEditBody(null, null))
        assertEquals(setOf("do", "back"), obj(Decks.cardEditBody(null, "")!!).keys)
        assertEquals("delete", obj(Decks.CARD_DELETE_BODY)["do"]!!.jsonPrimitive.content)
        assertEquals("c1", obj(Decks.revealBody("c1"))["card"]!!.jsonPrimitive.content)
        assertEquals("{}", Decks.moreBody(null))
        assertEquals("d1", obj(Decks.moreBody("d1"))["deck"]!!.jsonPrimitive.content)
        // Limits on the owner's words, as the PC checks them.
        assertTrue(Decks.validName("x".repeat(60)))
        assertFalse(Decks.validName("x".repeat(61)))
        assertFalse(Decks.validName("   "))
        assertTrue(Decks.validFront("x".repeat(500)))
        assertFalse(Decks.validFront("x".repeat(501)))
        assertTrue(Decks.validBack(""))
        assertFalse(Decks.validBack("x".repeat(2001)))
        // Paths: an id that is not safe in a URL never makes one.
        assertEquals("/api/decks/d1/act", Decks.deckActPath("d1"))
        assertEquals("/api/decks/d1/cards", Decks.cardsPath("d1"))
        assertEquals("/api/decks/d1/cards/c1/act", Decks.cardActPath("d1", "c1"))
        assertEquals("/api/review", Decks.reviewPath(null))
        assertEquals("/api/review?deck=d1", Decks.reviewPath("d1"))
        assertNull(Decks.deckActPath("../x"))
        assertNull(Decks.cardsPath("a/b"))
        assertNull(Decks.cardActPath("d1", "c 1"))
        assertNull(Decks.reviewPath("d1&x=1"))
    }

    // ------------------------------------------------------------- errors ----

    @Test
    fun aRefusalShowsThePcsOwnMessageWordForWord() {
        val reply = Decks.Reply(
            503,
            obj("""{"ok":false,"error":"deck_unavailable","message":"no key in Credential Manager: run the setup step."}"""),
        )
        assertEquals("No key in Credential Manager: run the setup step.", Decks.refusalSaid(reply, "Not read."))
        val out = Decks.listSaid(reply)
        assertFalse(out.ok)
        assertEquals("deck_unavailable", out.code)
    }

    @Test
    fun everyContractErrorHasPlainWordsWhenThePcSendsNoMessage() {
        val codes = listOf(
            "bad_deck_name", "too_many_decks", "deck_not_found", "card_not_found", "bad_action", "bad_card",
            "bad_setting", "deck_unavailable", "not_revealed", "deck_paused", "bad_rating",
        )
        codes.forEach { c ->
            val words = Decks.messageFor(c)
            assertNotNull(c, words)
            // Plain words: no snake_case code leaks into the sentence.
            assertFalse(c, words!!.contains("_"))
            assertEquals(words, Decks.refusalSaid(Decks.Reply(400, obj("""{"ok":false,"error":"$c"}""")), "Not saved."))
        }
        assertNull(Decks.messageFor("something_new"))
        assertNull(Decks.messageFor(null))
    }

    @Test
    fun aBareFourOhFourIsAPcWithoutDecksButACodedOneIsNot() {
        val bare = Decks.Reply(404, null)
        assertTrue(Decks.missing(bare))
        assertEquals(Decks.MISSING, Decks.listSaid(bare).said)
        assertTrue(Decks.missing(Decks.Reply(501, null)))
        val coded = Decks.Reply(404, obj("""{"ok":false,"error":"deck_not_found"}"""))
        assertFalse(Decks.missing(coded))
        assertEquals("That deck is not there any more.", Decks.refusalSaid(coded, "Not read."))
        assertEquals("Not saved. Your PC answered 500.", Decks.refusalSaid(Decks.Reply(500, null), "Not saved."))
        assertEquals("Not saved. Your PC's Jarvis cannot do this right now.", Decks.refusalSaid(Decks.Reply(503, null), "Not saved."))
    }

    @Test
    fun aRatingBeforeTheRevealIsRefusedWithThePcsCodeKept() {
        val out = Decks.ratedSaid(
            Decks.Reply(409, obj("""{"ok":false,"error":"not_revealed","message":"Show the answer first."}""")),
        )
        assertFalse(out.ok)
        assertEquals("not_revealed", out.code)
        assertEquals("Show the answer first.", out.said)
        // A gone card is a code the screen reacts to by reading the review again.
        assertEquals(
            Decks.E_CARD_NOT_FOUND,
            Decks.revealSaid(Decks.Reply(404, obj("""{"ok":false,"error":"card_not_found"}"""))).code,
        )
    }

    @Test
    fun deckAndCardWritesReadTheirAnswers() {
        val made = Decks.deckSaid(
            Decks.Reply(200, obj("""{"ok":true,"deck":{"id":"d1","name":"Plants","cards":0,"ready":0,"paused":false,"kind":"empty"}}""")),
            "Not made.",
        )
        assertEquals("Plants", made.value!!.name)
        assertEquals("empty", made.value!!.kind)
        assertTrue(Decks.actedSaid(Decks.Reply(200, obj("""{"ok":true,"deleted":true}""")), "x").value!!.deleted)
        val paused = Decks.actedSaid(
            Decks.Reply(200, obj("""{"ok":true,"deck":{"id":"d1","name":"P","cards":1,"ready":0,"paused":true,"kind":"study"}}""")),
            "x",
        ).value!!
        assertTrue(paused.deck!!.paused)
        assertFalse(Decks.actedSaid(Decks.Reply(200, obj("""{"ok":true}""")), "Not changed.").ok)
        assertEquals(9, Decks.perDaySaid(Decks.Reply(200, obj("""{"ok":true,"new_per_day":9}"""))).value)
        assertFalse(Decks.perDaySaid(Decks.Reply(200, obj("""{"ok":true,"new_per_day":99}"""))).ok)
        val card = Decks.cardSaid(
            Decks.Reply(200, obj("""{"ok":true,"card":{"id":"c1","front":"F","back":"B","passage":"","kind":"recall"}}""")),
            "Not saved.",
        )
        assertEquals("B", card.value!!.back)
        assertTrue(Decks.deletedSaid(Decks.Reply(200, obj("""{"ok":true,"deleted":true}""")), "x").ok)
        // "ok": false in a 200 is still a refusal.
        assertFalse(Decks.deletedSaid(Decks.Reply(200, obj("""{"ok":false,"error":"card_not_found"}""")), "x").ok)
    }

    // ------------------------------------------------------------- hidden ----

    @Test
    fun hiddenListsBlankEveryWordAndKeepTheCounts() {
        val h = Decks.hide(Decks.parseList(obj(listJson))!!)
        assertTrue(h.decks.all { it.name == Decks.HIDDEN_TEXT })
        assertEquals(listOf(8, 1), h.decks.map { it.cards })
        assertEquals(3, h.ready)
        assertEquals("3 cards ready", h.line)
        assertEquals("2026-10-03", h.nextReadyDay)
        val cards = Decks.hide(
            Decks.parseCards(
                obj("""{"deck":{"id":"d1","name":"Plants"},"cards":[{"id":"c1","front":"F","back":"B","passage":"P"}]}"""),
            )!!,
        )
        assertEquals(Decks.HIDDEN_TEXT, cards.deckName)
        assertEquals(Decks.HIDDEN_TEXT, cards.cards[0].front)
        assertEquals("", cards.cards[0].back)
        assertEquals("", cards.cards[0].passage)
    }

    // --------------------------------------------- the source files' rules ----

    private val bannedWords = listOf(
        "streak", "missed", "overdue", "behind", "in a row", "keep it up",
        "XP", "hearts", "lost", "leaderboard", "league",
    )

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"

    /** A Kotlin file's code with its comments removed. */
    private fun codeOf(rel: String): String = repoFile("$main/$rel").readText()
        .replace(Regex("/\\*.*?\\*/", RegexOption.DOT_MATCHES_ALL), "")
        .replace(Regex("(?m)(^|\\s)//.*$"), "$1")

    /** Every string literal in a Kotlin file, comments removed first. */
    private fun literalsOf(rel: String): List<String> {
        val src = codeOf(rel)
        return Regex("\"(?:[^\"\\\\\\n]|\\\\.)*\"").findAll(src).map { it.value }.toList()
    }

    private fun banned(text: String): List<String> = bannedWords.filter {
        Regex("(?<![A-Za-z])" + Regex.escape(it) + "(?![A-Za-z])", RegexOption.IGNORE_CASE).containsMatchIn(text)
    }

    @Test
    fun noOwnerVisibleStringOfTheNewScreensUsesABannedWord() {
        // Contract C1: no streak, XP, hearts or guilt words in the decks, review, Keep and Spanish screens.
        val files = listOf("net/Decks.kt", "net/Quiz.kt", "ui/screens/DecksPlate.kt", "ui/screens/QuizPlate.kt")
        files.forEach { f ->
            val lits = literalsOf(f)
            assertTrue("$f has string literals", lits.isNotEmpty())
            lits.forEach { lit ->
                assertEquals("$f: $lit", emptyList<String>(), banned(lit))
            }
        }
        // The scanner itself works.
        assertEquals(listOf("streak"), banned("Your streak"))
        assertEquals(listOf("in a row"), banned("three In A Row"))
        assertEquals(emptyList<String>(), banned("A restreak of the hearthstone"))
    }

    @Test
    fun theNineRoutesAreWrittenOutInFullSoTheParityToolSeesThem() {
        val src = repoFile("$main/net/Decks.kt").readText() + repoFile("$main/JarvisRuntime.kt").readText()
        listOf(
            "\"/api/decks\"",
            "\"/api/decks/settings\"",
            "\"/api/decks/\$id/act\"",
            "\"/api/decks/\$id/cards\"",
            "\"/api/decks/\$id/cards/\$cid/act\"",
            "\"/api/review\"",
            "\"/api/review/reveal\"",
            "\"/api/review/rate\"",
            "\"/api/review/more\"",
        ).forEach { assertTrue(it, src.contains(it)) }
    }

    @Test
    fun nothingOfTheDecksIsKeptOnThePhone() {
        // Contract: no card text in SharedPreferences, a file or a saved state.
        listOf("net/Decks.kt", "ui/screens/DecksPlate.kt", "ui/screens/QuizPlate.kt").forEach { f ->
            val src = codeOf(f)
            listOf("SharedPreferences", "rememberSaveable", "DataStore", "openFileOutput", "FileWriter", "writeText").forEach {
                assertFalse("$f uses $it", src.contains(it))
            }
        }
    }

    @Test
    fun theHeadersRuleAndTheTokenRuleStillHoldForTheNewCall() {
        // X-Jarvis-Client: hud rides on every request through the shared authed() builder.
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        val call = api.substring(api.indexOf("suspend fun decksCall"))
        assertTrue(call.substring(0, 1200).contains(".authed()"))
        assertFalse(call.substring(0, 1200).contains("Log."))
    }

    /** A file of this repository, found from wherever the tests run. */
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
