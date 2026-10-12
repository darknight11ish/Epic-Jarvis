package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Money
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's reading half of the chatbot money limits
 * (`net/Money.kt`; `GET /api/chatbot/money`; `backend/jarvis_chatbot_limits.py`
 * `view()`; docs/JARVIS-API.md section 122).
 *
 * The bodies below are the REAL shapes, not invented ones: the 200 body was
 * printed by running `jarvis_chatbot_limits.view()` against the module's own
 * `jarvis_chatbot_api` (its `_load()` returns an empty money file, so nothing
 * was written and no money file of the owner's was touched), and the 503 body
 * by making `api._load()` raise `MoneyFileError`, which is exactly what the
 * handler does when the money file is there but unreadable. The `line`,
 * `price.line`, `cap` and `about` strings are the PC's own words, copied
 * verbatim from that run.
 *
 * The one answer this file exists for is the 503 `money_unreadable`: it must
 * become the PC's own `message`, and the plate must draw it rather than a
 * blank. That is checked end to end - the parse, and the screen's own line.
 */
class MoneyTest {

    // --------------------------------------------------------------- fixtures

    /**
     * `GET /api/chatbot/money` 200, as the real handler writes it: one service
     * with no limit yet (a default, UNVERIFIED price), one with a limit set and
     * a price the owner corrected ("yours").
     */
    private val ok = obj(
        """
        {
          "ok": true,
          "available": true,
          "title": "Chatbot money limits",
          "about": "How much Jarvis may spend on this service's account in one calendar month. Raising it lets Jarvis spend more of your money than it could before.",
          "can_change": true,
          "can_change_prices": true,
          "pc_only": "The API key itself is still typed on the PC. A limit and a price can be changed from either app: raising a limit asks you on a card, and lowering one, removing one or correcting a price changes at once, with no card.",
          "raise_words": "Raising a limit asks you on an approval card: Windows Hello on this PC, or the fingerprint or PIN of the phone that asked.",
          "raise_action": "raise_api_limit",
          "lower_action": "lower_api_limit",
          "estimates": "Every price here is used to ESTIMATE what an answer cost. The default prices are unverified guesses, so the amounts spent are about, not exact - only the service's own bill is exact.",
          "until": "November 1",
          "money_file_words": "api-money.json",
          "services": [
            {
              "service": "openai",
              "company": "OpenAI",
              "name": "ChatGPT (OpenAI API)",
              "host": "api.openai.com",
              "model": "gpt-5-mini",
              "model_problem": "",
              "limit": null,
              "limit_words": "not set",
              "spent": 0.0,
              "spent_words": "${'$'}0.00",
              "left_words": "--",
              "until": "November 1",
              "reached": false,
              "ready": "No OpenAI API key is saved on this PC.",
              "cap": "Answer length: capped with max_completion_tokens (at most 8,000 word-pieces, fewer as the month's limit nears).",
              "price_page": "https://openai.com/api/pricing",
              "price": {
                "model": "gpt-5-mini",
                "source": "default",
                "verified": false,
                "set": "",
                "in": 0.25,
                "out": 2.0,
                "line": "${'$'}0.25 per million word-pieces in, ${'$'}2 out - the default written 2026-09-28, UNVERIFIED. Check it at https://openai.com/api/pricing and correct it here.",
                "price_page": "https://openai.com/api/pricing",
                "default": true
              },
              "can_change": true,
              "line": "No monthly money limit is set for OpenAI, so Jarvis will not use ChatGPT (OpenAI API) yet. Set one on the PC, in PowerShell in Jarvis's folder - for example ${'$'}5 a month: py -3 jarvis_chatbot_api.py limit openai 5"
            },
            {
              "service": "deepseek",
              "company": "DeepSeek",
              "name": "DeepSeek (API)",
              "host": "api.deepseek.com",
              "model": "deepseek-flash",
              "model_problem": "",
              "limit": 5.0,
              "limit_words": "${'$'}5",
              "spent": 0.98,
              "spent_words": "${'$'}0.98",
              "left_words": "${'$'}4.02",
              "until": "November 1",
              "reached": false,
              "ready": "",
              "cap": "Answer length: capped with max_tokens (at most 8,000 word-pieces, fewer as the month's limit nears).",
              "price_page": "https://api-docs.deepseek.com/quick_start/pricing",
              "price": {
                "model": "deepseek-flash",
                "source": "yours",
                "verified": true,
                "set": "2026-10-12",
                "in": 0.3,
                "out": 1.2,
                "line": "${'$'}0.3 per million word-pieces in, ${'$'}1.2 out - your own price, set 2026-10-12."
              },
              "can_change": true,
              "line": "About ${'$'}4.02 of ${'$'}5 left this month for DeepSeek (prices are estimates you can correct on the PC)."
            }
          ]
        }
        """,
    )

    /**
     * The 503, exactly as the handler writes it when the money file is there
     * but unreadable: `_refuse`-free, three fields and the PC's own sentence
     * ([Money.UNREADABLE] is its `error`).
     */
    private val unreadable = obj(
        """
        {"ok": false, "available": false, "error": "money_unreadable",
         "message": "Jarvis's record of API spending (chatbot\\api-money.json in Jarvis's settings folder) cannot be read: it could not be opened (PermissionError). No API chatbot is used until it is fixed; deleting the file forgets this month's spending and every limit"}
        """,
    )

    private val unreadableText: String = unreadable.toString()

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    // --------------------------------------------------------------- the read

    @Test
    fun theViewIsReadAsThePcWroteIt() {
        val read = Money.readBody(ok)
        val view = (read as Money.Read.Shown).view
        assertEquals("Chatbot money limits", view.title)
        assertTrue(view.about.startsWith("How much Jarvis may spend"))
        assertTrue(view.estimates.contains("ESTIMATE"))
        assertTrue(view.pcOnly.contains("API key itself is still typed on the PC"))
        assertEquals(2, view.services.size)

        val first = view.services[0]
        assertEquals("openai", first.service)
        assertEquals("OpenAI", first.company)
        assertEquals("gpt-5-mini", first.model)
        // The fields the desktop's own page reads, and the words it shows.
        assertEquals("not set", first.limitWords)
        assertEquals("${'$'}0.00", first.spentWords)
        assertEquals("--", first.leftWords)
        assertEquals("November 1", first.until)
        assertFalse(first.reached)
        assertTrue(first.line.startsWith("No monthly money limit is set for OpenAI"))
        val openaiPrice = first.price!!
        assertEquals("default", openaiPrice.source)
        assertFalse(openaiPrice.verified)
        assertTrue(openaiPrice.unverified)
        assertTrue(openaiPrice.line.contains("UNVERIFIED"))

        val second = view.services[1]
        assertEquals("${'$'}5", second.limitWords)
        assertEquals("${'$'}4.02", second.leftWords)
        val deepseekPrice = second.price!!
        assertEquals("yours", deepseekPrice.source)
        assertTrue(deepseekPrice.verified)
        assertFalse(deepseekPrice.unverified)
        assertEquals("2026-10-12", deepseekPrice.set)
    }

    /**
     * The figures line is the desktop's own sentence
     * (`chatbot-api-keys-settings.js`'s `moneyRow`), carrying the PC's three
     * values unchanged - and a value the PC did not send drops its clause
     * instead of leaving a gap.
     */
    @Test
    fun theFiguresLineCarriesThePcsOwnValues() {
        val view = (Money.readBody(ok) as Money.Read.Shown).view
        assertEquals(
            "Spent this month: ${'$'}0.00. Left: --. The count starts again on November 1.",
            Money.figuresLine(view.services[0]),
        )
        assertEquals(
            "Spent this month: ${'$'}0.98. Left: ${'$'}4.02. The count starts again on November 1.",
            Money.figuresLine(view.services[1]),
        )
        // Nothing sent, nothing drawn - never "Spent this month: ." with a hole.
        val bare = view.services[0].copy(spentWords = "", leftWords = "", until = "")
        assertEquals("", Money.figuresLine(bare))
    }

    // ------------------------------------------- the 503 that must not be blank

    @Test
    fun a503MoneyUnreadableIsThePcsOwnSentence() {
        // The code this file names, in the body the handler really sends.
        assertEquals(Money.UNREADABLE, unreadable["error"]!!.jsonPrimitive.content)
        // What JarvisApi.probeKeeping503 hands on: ApiError.Server(503, body).
        val read = Money.readFailure(ApiError.Server(503, unreadableText))
        val refused = read as Money.Read.Refused
        assertEquals(
            "the PC's own message, word for word",
            "Jarvis's record of API spending (chatbot\\api-money.json in Jarvis's settings folder) " +
                "cannot be read: it could not be opened (PermissionError). No API chatbot is used " +
                "until it is fixed; deleting the file forgets this month's spending and every limit",
            refused.message,
        )
        assertTrue("the PC's sentence, not the app's fallback", refused.message != Money.NOT_READ)
        assertTrue("and not a blank", refused.message.isNotBlank())
    }

    @Test
    fun a503WithNoWordsOfItsOwnStillSaysSomething() {
        // The fail-closed code with no `message` beside it: the app's sentence
        // for it, which says what it means.
        assertEquals(
            Money.NOT_READ,
            (Money.readFailure(ApiError.Server(503, """{"ok":false,"available":false,"error":"money_unreadable"}"""))
                as Money.Read.Refused).message,
        )
        // Some other code: read as a sentence, never dropped.
        assertEquals(
            "No money file.",
            (Money.readFailure(ApiError.Server(503, """{"error":"no_money_file"}"""))
                as Money.Read.Refused).message,
        )
        // No body at all, or one that is not JSON: the app's fixed sentence.
        for (body in listOf("", "<html>not json</html>", "{}")) {
            assertEquals(
                body,
                Money.NOT_READ,
                (Money.readFailure(ApiError.Server(503, body)) as Money.Read.Refused).message,
            )
        }
    }

    @Test
    fun a200ThatSaysItIsNotAvailableIsRefusedToo() {
        // The same refusal wearing a 200: `available: false` must never read as
        // "no services", which would draw an empty page instead of the words.
        val read = Money.readBody(unreadable)
        assertEquals(
            (Money.readFailure(ApiError.Server(503, unreadableText)) as Money.Read.Refused).message,
            (read as Money.Read.Refused).message,
        )
    }

    @Test
    fun aPcWithoutTheRouteSaysSoAndOtherFailuresAreLeftToTheApp() {
        assertEquals(
            Money.MISSING,
            (Money.readFailure(ApiError.NotFound) as Money.Read.Refused).message,
        )
        // A 503 that lost its body: the app's fixed sentence, never a blank.
        assertEquals(
            Money.NOT_READ,
            (Money.readFailure(ApiError.NotAvailable) as Money.Read.Refused).message,
        )
        // Everything else is the app's own plain words (the plate's
        // JarvisRuntime.noticeFor), so this answers null.
        assertNull(Money.readFailure(ApiError.BadToken))
        assertNull(Money.readFailure(ApiError.Server(500, "boom")))
        assertNull(Money.readFailure(ApiError.Unreachable("no address")))
    }

    @Test
    fun anAnswerThatIsNotAViewIsNeverDrawnAsAnEmptyOne() {
        // No `services` at all: not a view this app can read.
        assertNull(Money.parseView(obj("""{"ok":true,"available":true,"title":"Chatbot money limits"}""")))
        // A row the PC did not write (no `line`): the whole answer is refused,
        // rather than quietly dropping that service from the page.
        assertNull(
            Money.parseView(obj("""{"services":[{"service":"openai","company":"OpenAI"}]}""")),
        )
        assertEquals(
            Money.UNREADABLE_ANSWER,
            (Money.readBody(obj("""{"ok":true,"available":true}""")) as Money.Read.Failed).why,
        )
        // An empty list is a real answer, and says so rather than drawing nothing.
        val none = Money.readBody(obj("""{"ok":true,"available":true,"services":[]}"""))
        assertTrue((none as Money.Read.Shown).view.services.isEmpty())
        assertEquals("Your PC listed no chatbot services.", Money.NO_SERVICES)
    }

    @Test
    fun theAmountsAreHiddenWithTheMemoryListsLikeTheOtherFinancePlates() {
        assertFalse(Money.hiddenNow(hideLists = false, locked = false))
        assertTrue(Money.hiddenNow(hideLists = true, locked = false))
        assertTrue(Money.hiddenNow(hideLists = false, locked = true))
    }

    // ----------------------------------------------------------- the wiring

    @Test
    fun theApiReadsTheRouteAndKeepsIts503Body() {
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(
            "JarvisApi does not read the money route",
            api.contains("suspend fun chatbotMoney(): ApiResult<JsonObject> = probeKeeping503(Money.PATH)"),
        )
        // The 503 keeps its body, and every request is authed - token and
        // `X-Jarvis-Client: hud` ride along through the shared builder.
        val probe = api.substring(api.indexOf("private suspend fun probeKeeping503("))
        val body = probe.substring(0, probe.indexOf("\n    }\n"))
        assertTrue("a 503 loses its body", body.contains("ApiError.Server(503,"))
        assertTrue("the read is not authed", body.contains(".authed()"))
        assertTrue("the token is not sent", api.contains("header(TOKEN_HEADER, headerSafe(tokens.token()))"))
        assertTrue(
            "X-Jarvis-Client: hud is not sent",
            api.contains("const val CLIENT_VALUE = \"hud\"") &&
                api.contains("header(CLIENT_HEADER, CLIENT_VALUE)"),
        )
        // And the runtime is the one caller the plate goes through.
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(rt.contains("suspend fun chatbotMoney(): ApiResult<JsonObject> = api.chatbotMoney()"))
    }

    /**
     * The plate draws the PC's own sentence for a refusal. A blank here is the
     * defect this whole piece exists for, so the screen's own line is read: a
     * `Refused` that drew nothing, or drew a fixed sentence of the app's, would
     * pass every parse check above and still show the owner nothing.
     */
    @Test
    fun thePlateDrawsThePcsOwnSentenceRatherThanABlank() {
        // CODE, not the raw text: the plate's own notes say "plain `remember`,
        // never `rememberSaveable`", and a word quoted in a note is not a word
        // the screen writes (the project's `code()` habit, BrainListTest).
        val plate = code(repoFile("$main/ui/screens/MoneyPlate.kt").readText())
        val refused = plate.substringAfter("is Money.Read.Refused ->")
        val block = refused.substring(0, refused.indexOf("is Money.Read.Failed ->"))
        assertTrue("the refusal is not drawn at all", block.contains("r.message"))
        assertFalse("the refusal is replaced by a fixed sentence", block.contains("Money.NOT_READ"))
        assertFalse("the refusal branch can draw nothing", block.contains("return"))
        // The 503 keeps its body, so the read must go through readFailure which
        // reads it - not through a plain probe, which would report NotAvailable.
        assertTrue(plate.contains("Money.readFailure(r.error) ?: Money.Read.Failed(JarvisRuntime.noticeFor(r.error))"))
        // No control: this step sends no body to the route at all.
        assertFalse("the plate posts to the money route", plate.contains("postJson") || plate.contains(".post("))
        // Nothing is kept, and nothing is logged: plain `remember`, never saved
        // state, and no token or money figure in a log line.
        assertFalse(plate.contains("rememberSaveable"))
        assertFalse(plate.contains("android.util.Log"))
        for (file in listOf("net/Money.kt", "ui/screens/MoneyPlate.kt")) {
            val src = code(repoFile("$main/$file").readText())
            assertFalse("$file logs", src.contains("Log.") || src.contains("println("))
            assertFalse("$file names the token", src.contains("X-Jarvis-Token") || src.contains("TOKEN_HEADER"))
        }
    }

    @Test
    fun thePlateIsWiredIntoBrainAndItsHeadingKnowsIt() {
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        val call = brain.substring(brain.indexOf("plate(\"chatbot-money\""))
        val block = call.substring(0, call.indexOf("\n                }"))
        assertTrue("the section is not drawn", block.contains("ChatbotMoneySection("))
        assertTrue("the hidden state is not handed down", block.contains("privateHidden = privateHidden"))
        // No menu id guards it: the phone has no id for this page.
        assertFalse("the plate is behind a hideable menu", block.contains("menus.shows("))
        val sections = repoFile("$main/ui/screens/BrainSections.kt").readText()
        assertTrue("BrainSections does not declare it", sections.contains("""Plate("chatbot-money""""))
        val moneyTime = sections.substringAfter("key = \"money-time\"")
        assertTrue(
            "the plate is not under Money and time",
            moneyTime.substringBefore("key = \"projects\"").contains("""Plate("chatbot-money""""),
        )
    }

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"

    /**
     * [src] with whole-line `//` comments and block comments blanked (not
     * dropped, so a line's own offset never moves) - the project's `code()`
     * habit. A word quoted in a note is not a word the file writes.
     */
    private fun code(src: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in src.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line)
        }
        return out.joinToString("\n")
    }

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
