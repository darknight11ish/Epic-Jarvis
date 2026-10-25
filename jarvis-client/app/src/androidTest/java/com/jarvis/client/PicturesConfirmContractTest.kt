package com.jarvis.client

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.Pictures
import com.jarvis.client.net.PicturesAnswer
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.TimeUnit

/**
 * The phone's half of the 2026-10-25 image-mode handshake, on the wire.
 *
 * Making a picture while the everyday chat is holding the 12 GB card is TWO
 * requests, and the phone cannot collapse them into one:
 *
 *  - the FIRST request carries the owner's words alone (`Pictures.makeBody`)
 *    and the PC answers `409 needs: "free_card"` with its own sentence and its
 *    own minutes - nothing is unloaded, nothing is drawn;
 *  - only the owner's own tap sends the SAME words plus `free_card: true`
 *    (`Pictures.confirmBody`), which is ONE long request that steps the chat
 *    aside, draws, and puts the chat back.
 *
 * A second ask while a draw is already running is the PC's own `409 needs:
 * "drawing"` sentence; an older PC answers a phone's confirm `403 pc_only`.
 * Neither is retried, and neither is ever reported as a bad pairing token.
 *
 * `PicturesTest` proves how each of those answers is READ, on a plain JVM.
 * What no unit test can prove is that the reader is REACHED: what leaves this
 * phone, which path it goes to, the headers beside it, and how many requests
 * one tap actually makes. So everything here is REAL - the real [JarvisApi] on
 * its real OkHttp clients, the real [ClientSettings] and [TokenStore] (whose
 * token comes back through the Android Keystore), and the real
 * `Pictures.readMake` classification - against a MockWebServer stub PC. Most
 * assertions are about the REQUEST, because that is the half a real server
 * cannot correct for.
 *
 * On 127.0.0.1, which `network_security_config.xml` already permits in
 * cleartext for debug builds (the same setup [ApiContractTest] uses). The stub
 * PC answers at once, so the app's real 1,560 s picture read timeout
 * ([Pictures.CONFIRM_TIMEOUT_S]) is never exercised here - it exists for a
 * real draw on the PC - and nothing in this file sleeps or waits on a clock.
 *
 * This is NOT a test of the Compose plate: there is no Compose test rule in
 * this project on purpose (`app/build.gradle.kts`), and the plate's own rules
 * (the question is cleared before the confirming call, "Not now" sends
 * nothing, no retry) are pinned against its source in `PicturesTest`.
 */
@RunWith(AndroidJUnit4::class)
class PicturesConfirmContractTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    private lateinit var server: MockWebServer
    private lateinit var settings: ClientSettings
    private lateinit var tokens: TokenStore
    private lateinit var api: JarvisApi

    /** Whatever the dispatcher should answer next, by path. */
    private val routes = mutableMapOf<String, MockResponse>()

    private fun ok(json: String) = MockResponse().setResponseCode(200)
        .setHeader("Content-Type", "application/json").setBody(json)

    /** The PC's answer when it is not a 2xx: its status and its body are the answer. */
    private fun refused(status: Int, json: String) = MockResponse().setResponseCode(status)
        .setHeader("Content-Type", "application/json").setBody(json)

    /**
     * A JSON object's field names as a set, for "exactly these fields and no
     * others" assertions. Android's `org.json.JSONObject` has `keys()` (an
     * Iterator) and `names()` (a JSONArray), not the `keySet()` of the desktop
     * JSON-java library - and the app runs on Android's.
     */
    private fun keys(json: JSONObject): Set<String> {
        val out = linkedSetOf<String>()
        val it = json.keys()
        while (it.hasNext()) out.add(it.next())
        return out
    }

    /** The body of the first tap: the owner's words and nothing else. */
    private val firstBody: String
        get() = checkNotNull(Pictures.makeBody(PROMPT)) {
            "Pictures.makeBody refused this test's own prompt"
        }

    /** The body of the owner's tap on the PC's question: the same words plus the one consent key. */
    private val confirmBody: String
        get() = checkNotNull(Pictures.confirmBody(PROMPT)) {
            "Pictures.confirmBody refused this test's own prompt"
        }

    /** The answer one tap got, as the screen reads it. A transport failure is a test failure. */
    private fun answered(out: ApiResult<PicturesAnswer>): PicturesAnswer = when (out) {
        is ApiResult.Ok -> out.value
        is ApiResult.Failed -> throw AssertionError(
            "the request failed instead of being answered: ${out.error}",
        )
    }

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path?.substringBefore('?').orEmpty()
                return routes[path] ?: MockResponse().setResponseCode(404).setBody("{}")
            }
        }
        server.start()

        settings = ClientSettings(context)
        settings.setHost("${server.hostName}:${server.port}")
        tokens = TokenStore(context)
        tokens.setToken(TOKEN)
        api = JarvisApi(settings, tokens)
    }

    @After
    fun stop() {
        tokens.clear()
        settings.setHost("")
        server.shutdown()
    }

    // ------------------------------------------------------------ the PC ---

    /**
     * The PC's 409 question: the price of the swap, said before anything is
     * unloaded.
     *
     * The shape is the real one - `needs`, `option`, `estimate` and `confirm`
     * beside the sentence (backend/jarvis_pictures.py's `_draw_now`, and
     * `docs/JARVIS-API.md` section 129.4b), with the card's own minutes.
     *
     * The sentence travels in **`error`**, which is the key [Pictures.refusal]
     * reads and the key the PC sends. `said` is this app's own field name for
     * that sentence on [PicturesAnswer.NeedsConfirm], not a second wire key.
     */
    private fun freeCardQuestion(minutes: Int) = refused(
        409,
        """{"ok":false,"available":true,"needs":"free_card","option":"A",
           "estimate":{"draw_seconds":380.0,"chat_away_seconds":440.0,"minutes":$minutes},
           "confirm":{"free_card":true},
           "error":"$FREE_CARD_SAID"}""",
    )

    /** The PC's 409 while a draw is already running: one sentence, no question. */
    private fun stillDrawing() = refused(
        409,
        """{"ok":false,"available":true,"needs":"drawing","error":"$STILL_DRAWING_SAID"}""",
    )

    /** An older PC refusing a phone's confirm: `pc_only`, with its own sentence. */
    private fun olderPc() = refused(
        403,
        """{"ok":false,"pc_only":true,"needs":"free_card","error":"$OLD_PC_SAID"}""",
    )

    /**
     * The PC's 200: the drawn answer, including the swap's own record.
     *
     * Derived from backend/jarvis_pictures.py's success body (`ok`,
     * `available`, `name`, `id`, `prompt`, `seed`, `model`, `runtime`,
     * `seconds`, `bytes`, `made_at_words`, `words`, and `card` when the chat
     * stepped aside - `docs/JARVIS-API.md` section 129.4b).
     *
     * [Pictures.readMake] reads EVERY 2xx as `Made`, so this exact shape is
     * not what makes the confirm test pass; it is here because a stub PC
     * should speak the real PC's words, and so [Pictures.madeId] and
     * [Pictures.madeWords] are exercised on the body a real PC sends.
     */
    private fun drawnAnswer() = ok(
        """{"ok":true,"available":true,
           "name":"2026-10-25-140509-a-red-panda.png",
           "id":"$MADE_ID",
           "prompt":"$PROMPT",
           "seed":1234,
           "model":"sd_xl_base.safetensors",
           "runtime":"comfyui",
           "seconds":381.0,
           "bytes":2087566,
           "made_at_words":"25 Oct 2026, 14:05",
           "words":"$MADE_WORDS",
           "card":{"option":"A","did":true,"chat_away_seconds":0.5,
                   "chat_back_seconds":23.6,"chat_back":true,"models_freed":true,
                   "words":"Your everyday chat stepped aside for 0.5 seconds and is back on the card after another 23.6 seconds."}}""",
    )

    // ── the first request: the words alone ──────────────────────────────

    /**
     * The first tap asks and moves nothing.
     *
     * The phone sends the owner's words alone and reads the PC's 409 as the
     * PC's own question, with the PC's sentence and minutes. The request must
     * carry the token and `X-Jarvis-Client: hud`, must go to the one picture
     * route, and must NOT carry `free_card`: the owner has not agreed to
     * anything yet.
     */
    @Test
    fun firstRequestAsksAndCarriesNoConfirmKey() = runBlocking {
        routes[Pictures.PATH] = freeCardQuestion(6)

        val out = answered(api.makePicture(firstBody))
        assertTrue("the 409 was not read as the PC's question: $out", out is PicturesAnswer.NeedsConfirm)
        val question = out as PicturesAnswer.NeedsConfirm
        assertEquals("the PC's sentence must be shown word for word", FREE_CARD_SAID, question.said)
        assertEquals("the minutes are the PC's own estimate", 6, question.minutes)

        val req = server.takeRequest(10, TimeUnit.SECONDS)
        assertNotNull("the first request never arrived", req)
        val first = req!!
        assertEquals("POST", first.method)
        assertEquals(Pictures.PATH, first.path)
        assertEquals(TOKEN, first.getHeader("X-Jarvis-Token"))
        assertEquals("hud", first.getHeader("X-Jarvis-Client"))

        val body = JSONObject(first.body.readUtf8())
        assertEquals("the owner's words, as typed", PROMPT, body.getString("prompt"))
        assertFalse("the first request must never confirm the card swap", body.has("free_card"))
        assertEquals("the words and nothing else", setOf("prompt"), keys(body))
    }

    // ── the owner's tap: the same words plus one key ────────────────────

    /**
     * The tap re-sends the SAME words plus `free_card: true`, and one tap is
     * one request.
     *
     * [Pictures.confirmBody] is the only body builder that may put that key on
     * the wire, and the stub answers it 200. The body comparison is the
     * assertion that matters: the prompt is identical to the first request's,
     * the key set grew by exactly `free_card`, and the answer is `Made` - not
     * the question again, not a still-drawing refusal, not an older PC's.
     * [MockWebServer.requestCount] pins that there was no retry.
     */
    @Test
    fun confirmResendsTheSameWordsPlusOnlyThatKey() = runBlocking {
        routes[Pictures.PATH] = freeCardQuestion(6)

        val asked = answered(api.makePicture(firstBody))
        assertTrue("the first request must be the 409 question: $asked", asked is PicturesAnswer.NeedsConfirm)
        val askedReq = server.takeRequest(10, TimeUnit.SECONDS)
        assertNotNull("the first request never arrived", askedReq)
        val first = JSONObject(askedReq!!.body.readUtf8())

        // The owner taps the PC's question. Only now may the consent be sent.
        routes[Pictures.PATH] = drawnAnswer()
        val out = answered(api.makePicture(confirmBody))

        assertTrue("a 200 is the drawn answer: $out", out is PicturesAnswer.Made)
        assertFalse("a 200 is not the card question again", out is PicturesAnswer.NeedsConfirm)
        assertFalse("a 200 is not a draw already running", out is PicturesAnswer.StillDrawing)
        assertFalse("a 200 is not an older PC's refusal", out is PicturesAnswer.OldPc)
        val made = out as PicturesAnswer.Made
        assertEquals("the PC's id for the picture it drew", MADE_ID, Pictures.madeId(made.body))
        val madeWords = Pictures.madeWords(made.body)
        assertTrue("the PC's own draw sentence is kept word for word", madeWords.startsWith(MADE_WORDS))
        assertTrue(
            "the swap's own sentence follows it",
            madeWords.contains("Your everyday chat stepped aside for 0.5 seconds"),
        )

        val confirmReq = server.takeRequest(10, TimeUnit.SECONDS)
        assertNotNull("the confirm request never arrived", confirmReq)
        val confirm = confirmReq!!
        assertEquals("POST", confirm.method)
        assertEquals(Pictures.PATH, confirm.path)
        val second = JSONObject(confirm.body.readUtf8())
        assertEquals(
            "the confirm must send the same words, not retyped ones",
            first.getString("prompt"),
            second.getString("prompt"),
        )
        assertTrue("the confirm must carry the owner's own consent", second.getBoolean("free_card"))
        assertEquals(
            "the confirm adds the consent key and nothing else",
            keys(first) + "free_card",
            keys(second),
        )
        assertEquals("one tap is one request: nothing was retried", 2, server.requestCount)
    }

    // ── a draw already running is its own sentence ──────────────────────

    /**
     * A second ask while a draw runs is the PC's own "wait for that one"
     * sentence, shown as sent, and NOT retried: the first draw and its
     * warm-back carry on. The phone is allowed to confirm a swap now, so a
     * double tap is a real second request - and this is what it must get back
     * rather than a second draw beside the first.
     */
    @Test
    fun aDrawingAlreadyInFlightIsItsOwnSentenceAndIsNotRetried() = runBlocking {
        routes[Pictures.PATH] = stillDrawing()

        val out = answered(api.makePicture(firstBody))
        assertTrue("the PC's still-drawing answer was misread: $out", out is PicturesAnswer.StillDrawing)
        assertEquals(STILL_DRAWING_SAID, (out as PicturesAnswer.StillDrawing).said)
        assertEquals("one tap is one request: nothing was retried", 1, server.requestCount)

        val req = server.takeRequest(10, TimeUnit.SECONDS)
        assertNotNull("the one request never arrived", req)
        assertEquals(Pictures.PATH, req!!.path)
    }

    // ── an older PC: its sentence, then one honest line ─────────────────

    /**
     * A PC still on the rule before the owner's 2026-10-24 decision answers a
     * phone's `free_card: true` with `403 pc_only`.
     *
     * That is the PC ANSWERING, not this phone's pairing token being refused:
     * `JarvisApi.picturesCall` keeps the bad-token reading for every OTHER 403
     * and only lets a `pc_only` one through. The screen shows the PC's own
     * sentence first, then the one honest line [Pictures.OLD_PC_WORDS] - and
     * nothing is retried.
     */
    @Test
    fun anOlderPcIsThePcOnlySentencePlusTheOneHonestLine() = runBlocking {
        routes[Pictures.PATH] = olderPc()

        val out = api.makePicture(confirmBody)
        assertTrue(
            "a pc_only 403 must be the PC's answer, not this phone's token being refused: $out",
            out is ApiResult.Ok,
        )
        val answer = answered(out)
        assertTrue("a pc_only 403 is the older PC's own reading: $answer", answer is PicturesAnswer.OldPc)
        val oldPc = answer as PicturesAnswer.OldPc
        assertEquals("the PC's sentence, word for word", OLD_PC_SAID, oldPc.said)

        // What the plate draws: the PC's sentence, then the honest line.
        val shown = oldPc.said + "\n" + Pictures.OLD_PC_WORDS
        assertTrue("the PC's own sentence is shown first", shown.startsWith(OLD_PC_SAID))
        assertTrue("the honest line is not added after it", shown.endsWith(Pictures.OLD_PC_WORDS))

        val req = server.takeRequest(10, TimeUnit.SECONDS)
        assertNotNull("the one request never arrived", req)
        assertTrue(
            "the confirm's consent must be on the wire",
            JSONObject(req!!.body.readUtf8()).getBoolean("free_card"),
        )
        assertEquals("never retried", 1, server.requestCount)
    }

    // ── one route, two requests ─────────────────────────────────────────

    /**
     * Two taps, two requests, and both go to exactly `/api/pictures`: there is
     * no second path, no chunked upload and no retry endpoint for a picture.
     * `Pictures` declares one route for making one, and this is what the
     * phone's real client does with it.
     */
    @Test
    fun twoRequestsOnlyEverGoToOnePath() = runBlocking {
        routes[Pictures.PATH] = freeCardQuestion(6)
        answered(api.makePicture(firstBody))

        routes[Pictures.PATH] = drawnAnswer()
        answered(api.makePicture(confirmBody))

        assertEquals("two taps, two requests", 2, server.requestCount)
        repeat(2) {
            val req = server.takeRequest(10, TimeUnit.SECONDS)
            assertNotNull("a request never arrived", req)
            assertEquals("a picture request went somewhere else", Pictures.PATH, req!!.path)
            assertEquals("POST", req.method)
        }
    }

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"

        /** What the owner typed; both requests must carry it unchanged. */
        const val PROMPT = "a red panda reading in a library"

        /**
         * The PC's 409 question, word for word: `FREE_CARD_WORDS` in
         * backend/jarvis_pictures.py, also shown in docs/JARVIS-API.md
         * section 129.4b. It is sent in `error`, the key `Pictures.refusal`
         * reads and the key the real PC sends (`said` is the app's field name
         * for it, not a wire key).
         */
        const val FREE_CARD_SAID =
            "Drawing needs the 12 GB card, and your everyday chat is using it. If you " +
                "agree, Jarvis sets the everyday chat aside for a few minutes, draws the " +
                "picture, then loads the chat back the way it was - the conversation and " +
                "its settings are kept. Nothing else changes."

        /** The one sentence a second request gets while a draw runs (same backend file). */
        const val STILL_DRAWING_SAID =
            "Jarvis is still drawing the last picture. Wait for that one to finish, " +
                "then ask again."

        /**
         * An older PC's refusal of a phone's confirm: the fixture `PicturesTest`
         * uses for exactly this reading (`anOlderPcIsShownHonestlyAndNeverRetried`).
         */
        const val OLD_PC_SAID =
            "Making a picture now means setting this PC's everyday chat aside " +
                "for a few minutes. That can only be started on the PC itself."

        /** The id the real PC gives a picture it has just drawn. */
        const val MADE_ID = "2026-10-25-140509-a-red-panda"

        /** The PC's own sentence for a finished draw (`WORDS["made"]`). */
        const val MADE_WORDS =
            "Drawn in 381.0 seconds and saved as 2026-10-25-140509-a-red-panda.png."
    }
}
