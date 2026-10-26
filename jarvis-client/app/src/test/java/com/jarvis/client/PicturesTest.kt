package com.jarvis.client

import com.jarvis.client.net.Pictures
import com.jarvis.client.net.PicturesAnswer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Ask for a picture, and keep it" on the phone (the owner's decision of
 * 2026-09-27: *"12 GB card: longer conversations with picture understanding
 * first, and making pictures too (swapped in when asked, since both cannot sit
 * on the card at once)"*; docs/JARVIS-API.md section 129;
 * net/Pictures.kt, ui/screens/PicturesPlate.kt, backend jarvis_pictures.py).
 *
 * WHAT THIS IS, HONESTLY
 *
 * There is no phone, no PC, no graphics card and no model anywhere in this
 * file, and there must not be. It tests the ONE thing the phone actually
 * decides: how it reads what the PC sent, what it sends and when, and what it
 * does while a request is running or the private lists are hidden. Whether
 * ComfyUI draws a good picture is not a question this suite can ask, and it
 * does not pretend to.
 *
 * WHAT IS COVERED
 *
 *  - a real gallery reads back: the folder, the size, the switch, and every
 *    picture's own prompt, seed and when it was made;
 *  - the PC's own sentences are shown word for word, never rebuilt here;
 *  - the FINAL card contract (2026-10-25): the first request sends the words
 *    alone; a 409 `free_card` is read with the PC's own minutes; only the
 *    owner's tap sends the same words plus `free_card: true`; that one is a
 *    1,200 s request and is never re-sent, including on a timeout;
 *  - a 409 `needs: "drawing"` is the PC's own "wait for that one" sentence,
 *    shown as sent and not retried;
 *  - a 403 `pc_only` from an OLDER PC is its sentence plus one honest line
 *    saying the PC needs the newer Jarvis - never a bad token, never a code;
 *  - "Not now" sends nothing and leaves the typed words in the box (checked
 *    against the plate's own source, the way the settings check below is);
 *  - a HIDDEN answer is read as hidden, and holds no prompt at all;
 *  - the phone cannot change the switch, the program or the folder: it has no
 *    call for them, and the settings route is the PC's alone;
 *  - a blank or too-long prompt is refused before anything is sent;
 *  - an id is a bare file stem: no separator, no "..", no other path;
 *  - "Save to my phone" names the file safely, from the PC's own name;
 *  - the words are the ones both apps share, and the one sentence that says
 *    nothing is sent anywhere is there.
 */
class PicturesTest {

    private fun obj(vararg pairs: Pair<String, Any?>): JsonObject = buildJsonObject {
        for ((k, v) in pairs) when (v) {
            null -> put(k, kotlinx.serialization.json.JsonNull)
            is String -> put(k, v)
            is Int -> put(k, v)
            is Long -> put(k, v)
            is Double -> put(k, v)
            is Boolean -> put(k, v)
            // A nested array or object (a buildJsonObject { } fixture, or
            // arr(...)). This branch was missing, and the helper DROPPED the
            // value instead of failing: "pictures" to arr() produced a body
            // with no "pictures" key at all, so `readReply` answered MISSING
            // and the test that built it was checking the wrong thing.
            is kotlinx.serialization.json.JsonElement -> put(k, v)
        }
    }

    private fun arr(vararg items: JsonObject) =
        kotlinx.serialization.json.JsonArray(items.toList())

    /** One of the app's own source files, or null when run from elsewhere. */
    private fun source(path: String): String? =
        java.io.File(path).takeIf { it.isFile }?.readText()

    private fun plate(): String? =
        source("src/main/java/com/jarvis/client/ui/screens/PicturesPlate.kt")

    private fun api(): String? =
        source("src/main/java/com/jarvis/client/net/JarvisApi.kt")

    /**
     * The body of the first `{...}` block after [marker], brace-matched. Used
     * to hold ONE handler to its rule without depending on line numbers.
     */
    private fun blockAfter(text: String, marker: String): String? {
        val at = text.indexOf(marker)
        if (at < 0) return null
        val open = text.indexOf('{', at)
        if (open < 0) return null
        var depth = 0
        for (i in open until text.length) {
            when (text[i]) {
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return text.substring(open + 1, i)
                }
            }
        }
        return null
    }

    private val realAnswer: JsonObject = buildJsonObject {
        put("ok", true)
        put("available", true)
        put("enabled", true)
        put("runtime", "comfyui")
        put("runtime_plain", "ComfyUI")
        put("folder", "C:\\Users\\owner\\Pictures\\Jarvis")
        put("count", 2)
        put("bytes", 900_000L)
        put("size_words", "879 KB")
        put("words", "")
        put("keep", "Your pictures are kept until you delete them yourself.")
        put("runtimes", arr(
            obj("id" to "comfyui", "plain" to "ComfyUI", "address" to "http://127.0.0.1:8188"),
            obj("id" to "sd_cpp", "plain" to "stable-diffusion.cpp", "address" to "http://127.0.0.1:1234"),
        ))
        put("pictures", arr(
            obj("name" to "2026-10-11-140509-a-red-panda.png", "id" to "2026-10-11-140509-a-red-panda",
                "prompt" to "a red panda in a library", "seed" to 1234L, "model" to "sd_xl_base.safetensors",
                "made_at_words" to "11 Oct 2026, 14:05", "bytes" to 400_000L, "record" to true),
            obj("name" to "2026-10-11-140600-an-owl.png", "id" to "2026-10-11-140600-an-owl",
                "prompt" to "", "made_at_words" to "11 Oct 2026, 14:06", "bytes" to 500_000L,
                "record" to false),
        ))
    }

    /** The PC's own 409 question, exactly as `jarvis_pictures.py` sends it. */
    private val freeCardQuestion: JsonObject = obj(
        "ok" to false, "available" to true, "needs" to "free_card", "option" to "A",
        "estimate" to obj("draw_seconds" to 275.0, "chat_away_seconds" to 335.0, "minutes" to 6),
        "confirm" to obj("free_card" to true),
        "error" to ("Drawing needs the 12 GB card, and your everyday chat is using it. " +
            "If you agree, Jarvis sets the everyday chat aside for a few minutes, draws " +
            "the picture, then loads the chat back the way it was - the conversation and " +
            "its settings are kept. Nothing else changes. This takes about 6 minutes, and " +
            "the chat comes back on its own afterwards."),
    )

    // ── a real answer ────────────────────────────────────────────────────

    @Test
    fun aRealAnswerReadsBackWhole() {
        val r = Pictures.readReply(200, realAnswer)
        assertTrue(r.available)
        assertTrue(r.enabled)
        assertTrue(r.canAsk)
        assertTrue(r.visible)
        assertEquals("C:\\Users\\owner\\Pictures\\Jarvis", r.folder)
        assertEquals(2, r.count)
        assertEquals("879 KB", r.sizeWords)
        assertEquals(2, r.shots.size)
        assertEquals("a red panda in a library", r.shots[0].prompt)
        assertEquals(1234L, r.shots[0].seed)
        assertEquals("sd_xl_base.safetensors", r.shots[0].model)
        assertEquals("11 Oct 2026, 14:05", r.shots[0].madeAtWords)
        assertTrue(r.shots[0].hasRecord)
        assertFalse(r.shots[1].hasRecord)
        // The two programs the PC supports, with what to install, so the
        // screen can say what is missing without inventing a word.
        assertEquals(listOf("comfyui", "sd_cpp"), r.programs.map { it.id })
        assertEquals("ComfyUI", r.programs[0].plain)
    }

    @Test
    fun thePcsOwnSentencesAreShownWordForWord() {
        // Nothing set up: the PC's one plain sentence, not a code and not blank.
        val notSetUp = obj(
            "ok" to true, "available" to true, "enabled" to true,
            "folder" to "C:\\Pictures\\Jarvis", "count" to 0, "bytes" to 0,
            "size_words" to "0 B",
            "words" to ("Jarvis has no picture-making program set up yet, so it "
                + "cannot draw one. Install ComfyUI or stable-diffusion.cpp's "
                + "server, then choose which one you installed in Settings, under Pictures."),
            "keep" to "kept",
            "runtimes" to arr(),
            "pictures" to arr(),
        )
        val r = Pictures.readReply(200, notSetUp)
        assertTrue(r.canAsk)  // the switch is on; the PROGRAM is what is missing
        assertTrue(r.words.startsWith("Jarvis has no picture-making program"))
        assertTrue(r.words.endsWith("under Pictures."))
        // A refusal comes back as its own sentence, as sent.
        val refused = obj("ok" to false, "error" to "Jarvis is set to use ComfyUI, but it is not answering. Start it on this PC, then ask again.")
        assertEquals(
            "Jarvis is set to use ComfyUI, but it is not answering. Start it on this PC, then ask again.",
            Pictures.refusal(refused),
        )
        // A refusal with no sentence at all still says something true.
        assertEquals(Pictures.WORDS.getValue("unreadable"), Pictures.refusal(obj("ok" to false)))
        assertEquals(Pictures.WORDS.getValue("unreadable"), Pictures.refusal(null))
    }

    // ── the 409 question, and the owner's two answers (2026-10-25) ───────

    @Test
    fun the409QuestionIsReadWithThePcsOwnMinutes() {
        val answer = Pictures.readMake(409, freeCardQuestion)
        assertTrue(answer is PicturesAnswer.NeedsConfirm)
        val question = answer as PicturesAnswer.NeedsConfirm
        // The PC's sentence, word for word - nothing rebuilt on the phone.
        assertEquals(Pictures.refusal(freeCardQuestion), question.said)
        assertTrue(question.said.endsWith("the chat comes back on its own afterwards."))
        // The minutes are the PC's own estimate, never guessed here.
        assertEquals(6, question.minutes)
        // The two answers the plate draws, in the PC's own minutes.
        assertEquals(
            "Set the chat aside and draw (about 6 minutes)",
            Pictures.confirmLabel(question.minutes),
        )
        assertEquals(
            "Set the chat aside and draw (about 1 minute)",
            Pictures.confirmLabel(1),
        )
        assertEquals("Set the chat aside and draw", Pictures.confirmLabel(null))
        assertEquals(
            "Drawing - this takes about 6 minutes. Your everyday chat will come back when it is done.",
            Pictures.confirmingWords(question.minutes),
        )
        assertEquals(
            "Drawing - this takes a few minutes. Your everyday chat will come back when it is done.",
            Pictures.confirmingWords(null),
        )
        // No estimate at all is still a question with a plain label.
        val bare = Pictures.readMake(409, obj("ok" to false, "needs" to "free_card", "error" to "May I?"))
        assertTrue(bare is PicturesAnswer.NeedsConfirm)
        assertNull((bare as PicturesAnswer.NeedsConfirm).minutes)
    }

    @Test
    fun theFirstRequestSendsTheWordsAloneAndOnlyTheTapAddsFreeCard() {
        val first = Pictures.makeBody("  a red panda in a library  ")
        assertNotNull(first)
        assertEquals("{\"prompt\":\"a red panda in a library\"}", first)
        assertFalse("the first request must never confirm the swap", first!!.contains("free_card"))
        // The tap sends the SAME words plus the one consent key, and nothing else.
        val confirm = Pictures.confirmBody("  a red panda in a library  ")
        assertEquals(
            "{\"prompt\":\"a red panda in a library\",\"free_card\":true}",
            confirm,
        )
        assertEquals(Pictures.makeBody("a red panda in a library", freeCard = true), confirm)
        // Both refuse a blank or over-long prompt before anything is sent.
        assertNull(Pictures.makeBody("   ", freeCard = true))
        assertNull(Pictures.confirmBody("   "))
        assertNull(Pictures.confirmBody(""))
        assertNull(Pictures.confirmBody("x".repeat(Pictures.MAX_PROMPT + 1)))
        assertNotNull(Pictures.confirmBody("x".repeat(Pictures.MAX_PROMPT)))
        // `free_card` is put ONLY behind the parameter: no path in this file
        // can add it without the caller asking for the owner's own confirm.
        val text = source("src/main/java/com/jarvis/client/net/Pictures.kt")
        if (text != null) {
            assertTrue(text.contains("if (freeCard) put(\"free_card\", true)"))
        }
    }

    @Test
    fun aConfirmIsOneLongRequestAndOnlyOnePlaceSendsIt() {
        // The PC's worst case is the SUM of its five own ceilings, not the
        // draw alone: unload_lane 120 s + DRAW_WAIT_S 600 s + the `/free`
        // call's FREE_WAIT_S 180 s + the `/system_stats` poll's second
        // FREE_WAIT_S 180 s + warm_lane 600 s = 1,680 s
        // (backend/jarvis_picture_card.py:526 and :564-565;
        // backend/jarvis_pictures.py:197 and :208 - free_models() sets a poll
        // deadline of FREE_WAIT_S after the /free call's own FREE_WAIT_S
        // timeout). A read timeout measures silence, and the PC says nothing
        // until the swap is done, so the phone must wait longer than that whole
        // sum.
        val pcWorstCaseS = 120L + 600L + 180L + 180L + 600L
        assertEquals("the PC's five ceilings add up to 1,680 s", 1_680L, pcWorstCaseS)
        assertTrue(
            "the confirm must outlast the PC's ${pcWorstCaseS} s worst case",
            Pictures.CONFIRM_TIMEOUT_S > pcWorstCaseS,
        )
        assertTrue(
            "... with a minute to spare (the settled 1,740 s)",
            Pictures.CONFIRM_TIMEOUT_S >= 1_740L,
        )
        val api = api()
        if (api != null) {
            assertTrue(
                "the confirm's client must use the shared constant",
                api.contains("readTimeout(Pictures.CONFIRM_TIMEOUT_S, TimeUnit.SECONDS)"),
            )
            // EVERY make request runs on that long client, the first one too:
            // when the everyday chat is not holding the card the PC draws
            // inside request 1 (measured 381-383 s), and the old 300 s write
            // client cut that off at five minutes.
            assertTrue("every make request runs on the long client", api.contains("else makeCall"))
            assertFalse("no make request keeps the old 300 s bound", api.contains("else -> writeCall"))
        }
        val plate = plate()
        if (plate != null) {
            // EXACTLY ONE place sends `confirm = true`: the confirm tap.
            assertEquals(
                "one tap, one request",
                1,
                Regex("confirm = true").findAll(plate).count(),
            )
            val handler = blockAfter(plate, "suspend fun confirmNow()")
            assertNotNull("the confirm handler must exist", handler)
            // The question is cleared BEFORE the request, so a second tap
            // cannot send the same confirmation twice.
            val cleared = handler!!.indexOf("confirmPrompt = \"\"")
            val sent = handler.indexOf("confirm = true")
            assertTrue("the question is cleared before the call", cleared in 0 until sent)
            // And no loop around it: this is one request, never a retry.
            assertFalse(handler.contains("while ("))
            assertFalse(handler.contains("for ("))
            assertEquals(1, Regex("makePicture\\(").findAll(handler).count())
            assertFalse(plate.contains("resend", ignoreCase = true))
            assertFalse(plate.contains("retry", ignoreCase = true))
            // The waiting state lasts minutes and offers no button while it runs.
            assertTrue(plate.contains("Pictures.confirmingWords(minutes)"))
            assertTrue(plate.contains("if (confirming)"))
        }
    }

    @Test
    fun theFirstMakeRequestAlsoGetsTheLongBudgetBecauseItCanBeTheDraw() {
        // The PC does not always answer 409 first: `handshake_plan` answers
        // needs=False whenever the everyday chat is NOT holding the card (the
        // chat is unloaded, or the PC is on way C), and `_draw_now` then draws
        // inside the FIRST request. A measured draw is 381-383 s, past the old
        // 300 s bound, so the first request runs on the long client too.
        val api = api() ?: return
        val call = blockAfter(api, "private suspend fun picturesCall") ?: return
        assertTrue(
            "every POST picture call runs on the long client",
            call.contains("else makeCall"),
        )
        assertFalse("the old 300 s write client must not make a picture", call.contains("writeCall"))
        val long = api.substringAfter("private val makeCall").substringBefore(".build()")
        assertTrue(
            "the long client uses the shared 1,740 s constant",
            long.contains("readTimeout(Pictures.CONFIRM_TIMEOUT_S, TimeUnit.SECONDS)"),
        )
        // A read timeout measures silence; a whole-call bound would cut a real
        // draw off, so this client sets none.
        assertFalse("no whole-call bound on a make", long.contains("callTimeout"))
    }

    @Test
    fun aTimedOutConfirmIsNeverSentAgainAndSaysSo() {
        // A read timeout on THIS phone is not the PC saying no: the draw may
        // still be running there, so the answer offers no confirm again.
        assertTrue(Pictures.gaveUpWaiting("read_timeout"))
        assertFalse(Pictures.gaveUpWaiting("refused"))
        assertFalse(Pictures.gaveUpWaiting("connect_timeout"))
        assertTrue(Pictures.TIMED_OUT_MAKE.timedOut)
        assertFalse(Pictures.TIMED_OUT_MAKE.ok)
        assertFalse("a timeout must not offer the confirm again", Pictures.TIMED_OUT_MAKE.needsConfirm)
        assertNull(Pictures.TIMED_OUT_MAKE.id)
        assertTrue(Pictures.TIMED_OUT_MAKE.said.contains("may still be drawing"))
        assertTrue(Pictures.TIMED_OUT_MAKE.said.contains("not sent again"))
        // The phone's own sentence must never claim the picture failed.
        assertFalse(Pictures.TIMED_OUT_MAKE.said.contains("was not drawn"))
    }

    @Test
    fun aSecondDrawIsThePcsOwnSentenceAndIsNotRetried() {
        val still = "Jarvis is still drawing the last picture. Wait for that one to finish, then ask again."
        val answer = Pictures.readMake(
            409,
            obj("ok" to false, "available" to true, "needs" to "drawing", "error" to still),
        )
        assertTrue(answer is PicturesAnswer.StillDrawing)
        // Shown as sent, word for word. It is NOT a question and NOT a refusal
        // with a retry: the first draw is still running.
        assertEquals(still, (answer as PicturesAnswer.StillDrawing).said)
        assertEquals(still, Pictures.refusal(obj("error" to still)))
        // The plate shows that sentence through the ordinary `said` line and
        // offers no second request when it is a `drawing` answer.
        val plate = plate()
        if (plate != null) {
            assertFalse(plate.contains("needs = \"drawing\""))
            // No branch in the plate turns any answer into another request.
            assertEquals(2, Regex("makePicture\\(").findAll(plate).count())  // ask + confirmNow
        }
    }

    @Test
    fun anOlderPcIsShownHonestlyAndNeverRetried() {
        // What an older PC (the rule before 2026-10-24) answers a phone's
        // confirm with: 403 pc_only, and its own sentence.
        val oldWords = "Making a picture now means setting this PC's everyday chat aside " +
            "for a few minutes. That can only be started on the PC itself."
        val answer = Pictures.readMake(
            403,
            obj("ok" to false, "pc_only" to true, "needs" to "free_card", "error" to oldWords),
        )
        assertTrue(answer is PicturesAnswer.OldPc)
        assertEquals(oldWords, (answer as PicturesAnswer.OldPc).said)
        // The phone's one added line says this PC needs the NEWER Jarvis, and
        // it is never a raw status code.
        assertTrue(Pictures.OLD_PC_WORDS.contains("needs the newer Jarvis"))
        assertTrue(Pictures.OLD_PC_WORDS.contains("apply-patches.ps1"))
        assertFalse(Pictures.OLD_PC_WORDS.contains("403"))
        assertFalse(Pictures.OLD_PC_WORDS.contains("pc_only"))
        // A 403 that is NOT pc_only is a cross-origin refusal: the old reading
        // of it (a bad token) is unchanged, and it is never this answer.
        val crossOrigin = obj("ok" to false, "error" to "cross-origin request refused")
        assertFalse(Pictures.isPcOnly(crossOrigin))
        assertTrue(Pictures.readMake(403, crossOrigin) is PicturesAnswer.Refused)
        assertTrue(Pictures.isPcOnly(obj("pc_only" to true)))
    }

    @Test
    fun notNowSendsNothingAndKeepsTheTypedWords() {
        val plate = plate()
        assertNotNull("the plate's own source is where this rule lives", plate)
        val handler = blockAfter(plate!!, "Pictures.WORDS.getValue(\"set_aside_no\")")
        assertNotNull("the Not now button must exist", handler)
        val body = handler!!
        // NOTHING is sent: no call, no coroutine started.
        assertFalse("Not now must send no request", body.contains("makePicture("))
        assertFalse("Not now must start no coroutine", body.contains("launch"))
        // The typed words stay in the box: the box's own `prompt` is not cleared.
        assertFalse("Not now must keep the typed words", body.contains(Regex("\\bprompt = ")))
        // The owner is told the truth about what did not happen.
        assertTrue(body.contains("set_aside_stopped"))
    }

    // ── an ordinary no is not a question ────────────────────────────────

    @Test
    fun anOrdinaryNoIsNotTheCardQuestion() {
        // Nothing set up / the switch off / the drawing program not running:
        // their own sentence, shown as an ordinary refusal.
        val notSetUp = Pictures.readMake(
            503,
            obj("ok" to false, "available" to false,
                "error" to "Jarvis has no picture-making program set up yet."),
        )
        assertTrue(notSetUp is PicturesAnswer.Refused)
        assertEquals(
            "Jarvis has no picture-making program set up yet.",
            (notSetUp as PicturesAnswer.Refused).said,
        )
        val off = Pictures.readMake(
            503,
            obj("ok" to false, "available" to true, "off" to true, "error" to "Making pictures is switched off."),
        )
        assertTrue(off is PicturesAnswer.Refused)
        // A 409 with another reason, or with no needs at all, is not the question.
        assertTrue(Pictures.readMake(409, obj("ok" to false, "error" to "something else")) is PicturesAnswer.Refused)
        assertTrue(Pictures.readMake(409, null) is PicturesAnswer.Refused)
        // A 503 that NAMES free_card because setting the chat aside FAILED is a
        // real failure with its own sentence, not a question to confirm again.
        val failed = Pictures.readMake(
            503,
            obj("ok" to false, "available" to true, "needs" to "free_card",
                "error" to "The everyday chat could not be set aside, so nothing was drawn."),
        )
        assertTrue(failed is PicturesAnswer.Refused)
        assertEquals(
            "The everyday chat could not be set aside, so nothing was drawn.",
            (failed as PicturesAnswer.Refused).said,
        )
        // A PC with no pictures route at all.
        assertTrue(Pictures.readMake(404, null) is PicturesAnswer.Missing)
        assertTrue(Pictures.readMake(501, null) is PicturesAnswer.Missing)
    }

    @Test
    fun theDrawnAnswerCarriesThePcsTwoSentencesAndTheSwapRecord() {
        val drawn = obj(
            "ok" to true, "available" to true,
            "name" to "2026-10-11-140509-a-red-panda.png",
            "id" to "2026-10-11-140509-a-red-panda",
            "words" to "Drawn in 41.2 seconds and saved as 2026-10-11-140509-a-red-panda.png.",
            "card" to obj(
                "option" to "A", "did" to true,
                "chat_away_seconds" to 2.5, "chat_back_seconds" to 9.0,
                "chat_back" to true, "models_freed" to true,
                "words" to ("Your everyday chat stepped aside for 2.5 seconds and is " +
                    "back on the card after another 9.0 seconds."),
            ),
        )
        val answer = Pictures.readMake(200, drawn)
        assertTrue(answer is PicturesAnswer.Made)
        val made = (answer as PicturesAnswer.Made).body
        assertEquals("2026-10-11-140509-a-red-panda", Pictures.madeId(made))
        // Both of the PC's sentences, word for word, in the order the PC sent
        // them. Nothing here is rebuilt or rounded on the phone.
        val words = Pictures.madeWords(made)
        assertTrue(words.startsWith("Drawn in 41.2 seconds"))
        assertTrue(words.endsWith("back on the card after another 9.0 seconds."))
        assertTrue(words.contains("Your everyday chat stepped aside for 2.5 seconds"))
        // The swap's own numbers, as the PC measured them.
        assertEquals(2.5, Pictures.cardAwaySeconds(made)!!, 0.001)
        assertEquals(9.0, Pictures.cardBackSeconds(made)!!, 0.001)
        assertEquals(
            "Your everyday chat stepped aside for 2.5 seconds and is back on the card " +
                "after another 9.0 seconds.",
            Pictures.cardWords(made),
        )
        // A draw that needed no swap has no card block and still reads whole.
        val plain = obj("ok" to true, "words" to "Drawn in 5.0 seconds and saved as a.png.")
        assertEquals("Drawn in 5.0 seconds and saved as a.png.", Pictures.madeWords(plain))
        assertNull(Pictures.cardAwaySeconds(plain))
        assertEquals("", Pictures.cardWords(plain))
        assertNull(Pictures.cardAwaySeconds(null))
    }

    @Test
    fun anOlderPcDrawsNothingAtAll() {
        // Not "no pictures yet" - the feature is simply not there.
        for (status in listOf(404, 501)) {
            val r = Pictures.readReply(status, null)
            assertFalse(r.available)
            assertFalse(r.visible)
            assertFalse(r.canAsk)
            assertTrue(r.shots.isEmpty())
        }
        assertFalse(Pictures.readReply(200, null).available)
        assertFalse(Pictures.readReply(200, obj("ok" to true)).available)
    }

    // ── the hiding rule ──────────────────────────────────────────────────

    @Test
    fun aHiddenAnswerCarriesNoPromptAndNothingIsFetched() {
        // What the PC sends while "Hide memory lists and chat history" is on:
        // the whole gallery taken out, and its own line.
        val hidden = obj(
            "ok" to true, "available" to true, "hidden" to true,
            "keep_on_screen" to true, "title" to "Pictures",
            "hidden_words" to "Hidden while memory lists and chat history are hidden.",
        )
        val r = Pictures.readReply(200, hidden)
        assertTrue(r.hidden)
        assertFalse(r.visible)
        assertFalse(r.canAsk)
        assertTrue(r.shots.isEmpty())
        assertEquals("", r.folder)
        assertEquals(0, r.count)
        assertEquals("", r.sizeWords)
        assertTrue(r.hiddenWords.isNotBlank())
        // The PC's own hidden line is not rebuilt on the phone: no literal of
        // the phone's own can appear in its place.
        assertEquals("Hidden while memory lists and chat history are hidden.", r.hiddenWords)
        // A hidden answer with no words at all still gets a true sentence.
        val bare = Pictures.readReply(200, obj("ok" to true, "available" to true, "hidden" to true))
        assertEquals(Pictures.WORDS.getValue("hidden"), bare.hiddenWords)
        // And the plate's own rule: while hidden it throws the answer away and
        // fetches nothing, which is what Reply.HIDDEN is for.
        assertFalse(Pictures.Reply.HIDDEN.visible)
        // A draw can outlast the owner hiding the lists: its answer must not
        // fetch then, so every refresh in the plate is guarded on the switch
        // as it is NOW, not as it was when the request started.
        val plate = plate()
        if (plate != null) {
            assertTrue(plate.contains("hiddenNow = hidden"))
            assertTrue(plate.contains("if (!hiddenNow) load()"))
        }
    }

    // ── the phone changes nothing but its own consent ────────────────────

    @Test
    fun thePhoneHasNoWayToChangeTheSwitchTheProgramOrTheFolder() {
        // The phone's own source, read from the classpath path the test task
        // runs in. It READS the switch, the program and the folder - the
        // gallery says which is on and where the pictures are - but it must
        // never PUT any of them into a request body, and the settings route
        // must be nowhere in the file. So the check is on what it SENDS: every
        // `put("...")` key in this file, which is the whole of what any body
        // it builds can carry.
        //
        // The earlier version of this check asserted the strings "enabled",
        // "runtime" and "folder" appeared NOWHERE in the file, which is not
        // the rule and cannot hold: `body["enabled"]`, `body["folder"]` and
        // `one["plain"]` are how it reads them back. It failed on every run.
        //
        // `free_card` is here because the owner's 2026-10-24 decision lets a
        // phone confirm the swap. It is still not a SETTING: it is the one
        // consent key, and it is put only behind `freeCard = true`, which only
        // the confirm tap passes.
        val text = source("src/main/java/com/jarvis/client/net/Pictures.kt")
        if (text == null) return  // run from somewhere else: the checks below still hold
        assertFalse(text.contains("pictures/settings"))
        val sent = Regex("put\\(\"([\\w_]+)\"").findAll(text).map { it.groupValues[1] }.toSet()
        listOf("enabled", "runtime", "address", "folder", "seed", "model", "steps",
               "width", "height", "settings").forEach {
            assertFalse("the phone must not send $it", sent.contains(it))
        }
        assertEquals(
            "the body carries the words, plus the owner's own consent and nothing else",
            setOf("prompt", "free_card"),
            sent,
        )
        assertTrue(text.contains("const val PATH = \"/api/pictures\""))
        assertTrue(text.contains("const val FILE_PATH = \"/api/pictures/file\""))
    }

    // ── what the phone sends ─────────────────────────────────────────────

    @Test
    fun theBodyHoldsTheOwnersWordsAndNothingElse() {
        val body = Pictures.makeBody("  a red panda in a library  ")
        assertNotNull(body)
        assertEquals("{\"prompt\":\"a red panda in a library\"}", body)
        // Not a seed, not a model, not a size, not a step count: the phone
        // cannot pick a drawing program's knobs.
        listOf("seed", "model", "steps", "width", "height", "settings").forEach {
            assertFalse("the body must not hold $it", body!!.contains(it))
        }
        // A prompt of spaces, or one over the PC's own cap, is refused HERE
        // rather than sent to be refused a second time.
        assertNull(Pictures.makeBody("   "))
        assertNull(Pictures.makeBody(""))
        assertNull(Pictures.makeBody("x".repeat(Pictures.MAX_PROMPT + 1)))
        assertNotNull(Pictures.makeBody("x".repeat(Pictures.MAX_PROMPT)))
    }

    @Test
    fun anIdIsABareFileStemAndNeverAPath() {
        val good = "2026-10-11-140509-a-red-panda"
        assertNotNull(Pictures.filePath(good))
        assertEquals("/api/pictures/file?id=$good", Pictures.filePath(good))
        val bad = listOf(
            "",
            "..",
            "../pictures.json",
            "/etc/passwd",
            "C:\\Windows\\win.ini",
            "2026-10-11-140509-a/b",
            "2026-10-11-140509-a\\b",
            "2026-10-11-140509-..",
            "not-a-date-at-all",
            "9".repeat(97),
        )
        bad.forEach { id -> assertNull("the id $id must be refused", Pictures.filePath(id)) }
    }

    @Test
    fun theBytesAreDecodedAndNothingElseIs() {
        // A real 1x1 PNG, base64, exactly as the PC sends it.
        val png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        val bytes = Pictures.pngBytes(obj("ok" to true, "png" to png, "encoding" to "base64"))
        assertNotNull(bytes)
        assertTrue(bytes!!.size > 50)
        // The PNG magic, so this is a picture and not a string that decoded.
        assertEquals(0x89.toByte(), bytes[0])
        assertEquals('P'.code.toByte(), bytes[1])
        assertNull(Pictures.pngBytes(obj("ok" to true, "png" to "")))
        assertNull(Pictures.pngBytes(obj("ok" to true, "png" to "not base64 at all !!")))
        assertNull(Pictures.pngBytes(obj("ok" to true)))
        assertNull(Pictures.pngBytes(null))
    }

    @Test
    fun theFileSavedToThePhoneIsNamedSafely() {
        val shot = Pictures.Shot(
            name = "2026-10-11-140509-a-red-panda.png", id = "2026-10-11-140509-a-red-panda",
            prompt = "a red panda", seed = 1L, model = "", madeAtWords = "", bytes = 0L,
            hasRecord = true,
        )
        assertEquals("2026-10-11-140509-a-red-panda.png", Pictures.fileName(shot))
        // A name with anything unsafe in it comes out with only safe characters.
        val nasty = shot.copy(id = "a/b\\c:d*e?f", name = "../x.png")
        val safe = Pictures.fileName(nasty)
        assertTrue(safe.endsWith(".png"))
        assertFalse(safe.contains("/"))
        assertFalse(safe.contains("\\"))
        assertFalse(safe.contains(".."))
        // An id that is nothing usable still gets a file name rather than a path.
        assertEquals("jarvis-picture.png", Pictures.fileName(shot.copy(id = "", name = "")))
    }

    @Test
    fun theWordsBothAppsShareAreTheOnesTheFeatureNeeds() {
        for (key in listOf(
            "title", "under", "ask_label", "make", "another", "save_phone",
            "saved_phone", "empty", "hidden", "hidden_short", "prompt_label",
            "made_label", "seed_label", "no_record", "not_kept", "missing",
            "unreadable", "no_words", "show", "show_title", "still_hidden",
            // The PC's 409 question and the owner's two answers (2026-10-25).
            "set_aside", "set_aside_no", "set_aside_stopped", "timed_out",
        )) {
            assertTrue("no `$key`", Pictures.WORDS.containsKey(key))
            assertTrue("`$key` is empty", Pictures.WORDS.getValue(key).isNotBlank())
        }
        assertTrue(Pictures.WORDS.getValue("not_kept").contains("never sent anywhere"))
        assertEquals("Pictures", Pictures.WORDS.getValue("title"))
        // The owner's own name for the feature, so the plate is findable by it.
        assertEquals("Image mode", Pictures.IMAGE_MODE)
        // The PC's two answers, in the words the desktop's own panel uses.
        assertEquals("Not now", Pictures.WORDS.getValue("set_aside_no"))
        assertTrue(Pictures.WORDS.getValue("set_aside").startsWith("Set the chat aside and draw"))
        // A picture with no record is still listed, and says so rather than
        // showing a blank line where the words should be.
        val shot = Pictures.Shot("a.png", "2026-10-11-140509-a", "", null, "", "11 Oct", 0L, false)
        assertTrue(shot.said().contains(Pictures.WORDS.getValue("no_record")))
    }

    @Test
    fun theImageModeIsNamedOnItsOneScreen() {
        // The owner asked for the phone's image mode to be easy to find. It is
        // found by its own name, in the one place it lives: a heading on the
        // Pictures plate. Not a new screen, not a preset, and not a button -
        // the switch is the PC's, so a control here would be a fake one.
        assertEquals("Image mode", Pictures.IMAGE_MODE)
        val plate = plate()
        if (plate != null) {
            assertTrue(
                "the plate draws the owner's own name for it",
                plate.contains("Kicker(Pictures.IMAGE_MODE"),
            )
            assertFalse(plate.contains("Primary(Pictures.IMAGE_MODE"))
            assertFalse(plate.contains("Quiet(Pictures.IMAGE_MODE"))
        }
    }

    @Test
    fun theSizeAPersonReadsIsSaidTheWayThePcSaysIt() {
        assertEquals("0 B", Pictures.sizedWords(0))
        assertEquals("2 KB", Pictures.sizedWords(2048))
        assertEquals("1.0 MB", Pictures.sizedWords(1024L * 1024))
        assertEquals("1.50 GB", Pictures.sizedWords(1024L * 1024 * 1024 * 3 / 2))
    }

    @Test
    fun aFailedReadIsNotAMissingFeature() {
        // The PC's own handler answers a failed gallery read with
        // {"ok":false,"available":false,"error":"The pictures could not be
        // read (…)."} and NO `pictures` key. The phone used to fall through to
        // Reply.MISSING and tell the owner to run apply-patches.ps1 for a
        // folder/permission fault (the 2026-10-24 round-2 audit, M7).
        val body = obj(
            "ok" to false,
            "available" to false,
            "error" to "The pictures could not be read (PermissionError).",
        )
        val r = Pictures.readReply(503, body)
        assertFalse("a failed read is still drawn as 'no Pictures feature'", r == Pictures.Reply.MISSING)
        assertTrue("the failure is not marked available, so the plate hides it", r.available)
        assertTrue("the PC's own sentence was thrown away", r.words.contains("PermissionError"))
        // A body that says nothing about a failure is still an older PC.
        assertEquals(Pictures.Reply.MISSING, Pictures.readReply(200, obj("ok" to true)))
    }
}
