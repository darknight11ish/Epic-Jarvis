package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Chatbot money limits" on the phone - the reading half only.
 *
 * THE DESKTOP'S OWN PAGE, READ FROM THE PHONE. `GET /api/chatbot/money`
 * (`backend/jarvis_chatbot_limits.py`'s `view()`, JARVIS-API section 122)
 * answers every API service with its monthly limit, what is spent, what is
 * left, its model's price WITH where that number came from and when it was
 * set, and the PC's own sentences. On the desktop that page is Settings ->
 * Chatbot API keys (`src-tauri/src/chatbot_money.rs`); on the phone a paired
 * device is answered the same way - the route refuses nothing to a phone -
 * so the phone can show exactly what the PC shows.
 *
 * READ ONLY, ON PURPOSE, IN THIS STEP. Nothing here builds a body, changes a
 * limit, corrects a price or raises a card: [JarvisApi.chatbotMoney] is the
 * one call, and the plate only draws what came back. The write half (the
 * one `POST`, its `WRITE_PATHS` entry and the Raise control) is a separate
 * piece of work that ships with its own caller (CLAUDE.md's "a WRITE_PATHS
 * entry must ship with its caller or not at all").
 *
 * FAILING CLOSED, AND THE SENTENCE THAT MATTERS. When the PC's money file is
 * there but unreadable, the route answers
 *
 * ```
 * 503  {"ok": false, "available": false, "error": "money_unreadable",
 *       "message": <the PC's own words>}
 * ```
 *
 * rather than reporting nothing spent - that is the whole point of the
 * refusal (`_file_words`). A 503 is normally `ApiError.NotAvailable`, which
 * carries no body, so this route is read through
 * [JarvisApi.probeKeeping503] and [readFailure] turns the 503 into the PC's
 * own `message` ([Read.Refused]). A plate that drew a blank, or "0.00", on
 * that answer would be the one mistake this file exists to prevent.
 *
 * Pure Kotlin, no Android types, so [MoneyTest] runs it on a plain JVM.
 */
object Money {
    /** `GET /api/chatbot/money`. The one route this file reads. */
    const val PATH = "/api/chatbot/money"

    /** The PC's own `error` code for "the money file is there but unreadable". */
    const val UNREADABLE = "money_unreadable"

    /** The plate's title, when the PC's answer did not name one. */
    const val TITLE = "Chatbot money limits"

    /** Said when the PC sent no sentence of its own on a 503. */
    const val NOT_READ =
        "Your PC could not read its money file, so it is not showing any amounts."

    /** A PC whose Jarvis has no money page yet: the route answers 404. */
    const val MISSING =
        "Your PC's Jarvis cannot set chatbot money limits yet - run apply-patches.ps1 on the PC."

    /** Said when the answer was not a money view this app can read. */
    const val UNREADABLE_ANSWER = "The desktop sent something this app could not read."

    const val READING = "Reading…"

    /** Stands in for the amounts while "Hide memory lists and chat history" is on. */
    const val HIDDEN = "Chatbot money hidden"

    /**
     * The empty list's own line, in this app's voice. The PC's table is a fixed
     * set of services, so this is not a state the backend has - but an answer
     * with no rows must say so rather than draw nothing.
     */
    const val NO_SERVICES = "Your PC listed no chatbot services."

    /**
     * Said under the amounts, in this app's own voice: the PC's `pc_only`
     * sentence says a limit can be changed "from either app", and that is true
     * of the backend and of the desktop - but not yet of this plate. Saying so
     * is cheaper than letting the owner look for a control that is not here.
     */
    const val READ_ONLY =
        "This shows what your PC has. Changing a limit from the phone is not built yet."

    /**
     * Whether the amounts are drawn or [HIDDEN] stands in their place, with NO
     * fetch: "Hide memory lists and chat history" is on, or App lock is locked.
     * The same rule the spending table and the retirement what-if keep - these
     * are the owner's own money figures.
     */
    fun hiddenNow(hideLists: Boolean, locked: Boolean): Boolean = hideLists || locked

    // --------------------------------------------------------------- the shapes

    /** One model's price, with where it came from and when it was set. */
    data class Price(
        val model: String,
        /** `"yours"`, `"default"` or `"none"` - as the PC wrote it. */
        val source: String,
        val verified: Boolean,
        /** `"YYYY-MM-DD"` when the owner set it, else "". */
        val set: String,
        val inPerMillion: Double?,
        val outPerMillion: Double?,
        /** The PC's own sentence about this price, drawn as it came. */
        val line: String,
    ) {
        /** True for the default figure the PC marks UNVERIFIED. */
        val unverified: Boolean get() = !verified && source == "default"
    }

    /**
     * One API service: its limit, what is spent and what is left. The field
     * names are the desktop's own reading of the same answer
     * (`src/chatbot-api-keys.js` `moneyFor`), so the two apps cannot drift
     * apart: the desktop drops `ready` and `host` too, which are a long
     * PowerShell sentence and an address the page never shows.
     */
    data class Service(
        val service: String,
        val company: String,
        val name: String,
        val model: String,
        /** Why no model could be named, when the PC sent one. */
        val modelProblem: String?,
        val limitWords: String,
        val spentWords: String,
        val leftWords: String,
        /** When the amounts start again, in the PC's own words. */
        val until: String,
        /** True when what is spent has reached the limit. */
        val reached: Boolean,
        /** The PC's words for the answer-length cap it asks the service for. */
        val cap: String,
        val price: Price?,
        /** The PC's own one-line summary for this service. */
        val line: String,
    )

    /** The whole answer, as the PC wrote it. */
    data class View(
        val title: String,
        val about: String,
        /** The PC's sentence about the one thing that is still the PC's alone. */
        val pcOnly: String,
        /** The PC's sentence that every price here is an estimate. */
        val estimates: String,
        val services: List<Service>,
    )

    /** What one read found. */
    sealed interface Read {
        /** The view, to be drawn in the PC's own words. */
        data class Shown(val view: View) : Read

        /**
         * The PC said, in its own words, why it is not showing amounts - a 503
         * `money_unreadable` above all, and a 404 on a PC without the page.
         * [message] is drawn as it came; nothing here re-words it.
         */
        data class Refused(val message: String) : Read

        /** The route failed for a reason the PC did not put into words. */
        data class Failed(val why: String) : Read
    }

    // --------------------------------------------------------------- the reading

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /** A real JSON boolean only - the string "true" is not one. */
    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull

    /** A real JSON number only; a figure sent as text is left to the PC's own words. */
    private fun JsonObject.num(key: String): Double? =
        prim(key)?.takeIf { !it.isString }?.doubleOrNull?.takeIf { it.isFinite() }

    /**
     * The PC's own sentence out of a refusal: its `message` (the plain words
     * `_file_words` wrote) first, then its `error` code read as a sentence. The
     * fail-closed code with no sentence beside it gets [NOT_READ], which says
     * what it means, rather than "Money unreadable.". A field the PC did not
     * send is null, never a guess.
     */
    private fun wordsOf(o: JsonObject?): String? =
        o?.str("message") ?: o?.str("error")?.let { code ->
            if (code == UNREADABLE) NOT_READ else DesktopWrite.asSentence(code.replace('_', ' '))
        }

    /** The same, from a 503's raw body text (`probeKeeping503` keeps it). */
    fun pcWords(body: String?): String? {
        if (body.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(body) as? JsonObject }.getOrNull() ?: return null
        return wordsOf(o)
    }

    private fun price(o: JsonObject?): Price? {
        o ?: return null
        val model = o.str("model") ?: return null
        return Price(
            model = model,
            source = o.str("source").orEmpty(),
            verified = o.flag("verified") ?: false,
            set = o.str("set").orEmpty(),
            inPerMillion = o.num("in"),
            outPerMillion = o.num("out"),
            line = o.str("line").orEmpty(),
        )
    }

    /**
     * One service row. A row with no `line` is not one the PC wrote - the
     * backend writes one for every row - and [parseView] refuses the whole
     * answer rather than dropping it silently, so a page can never be missing a
     * service without saying so.
     */
    private fun service(o: JsonObject): Service? {
        val line = o.str("line") ?: return null
        return Service(
            service = o.str("service").orEmpty(),
            company = o.str("company").orEmpty(),
            name = o.str("name").orEmpty(),
            model = o.str("model").orEmpty(),
            modelProblem = o.str("model_problem"),
            limitWords = o.str("limit_words").orEmpty(),
            spentWords = o.str("spent_words").orEmpty(),
            leftWords = o.str("left_words").orEmpty(),
            until = o.str("until").orEmpty(),
            reached = o.flag("reached") ?: false,
            cap = o.str("cap").orEmpty(),
            price = price(o["price"] as? JsonObject),
            line = line,
        )
    }

    /**
     * `GET /api/chatbot/money`'s 2xx body. Null when it is not a view this app
     * can read: `services` missing or not the PC's list of rows, or a row with
     * no words of the PC's in it. One unreadable row refuses the whole answer
     * rather than quietly dropping a service - a money page missing a service
     * is worse than one that says it could not be read.
     */
    fun parseView(body: JsonObject): View? {
        val raw = body["services"] as? JsonArray ?: return null
        val services = raw.map { (it as? JsonObject)?.let(::service) ?: return null }
        return View(
            title = body.str("title") ?: TITLE,
            about = body.str("about").orEmpty(),
            pcOnly = body.str("pc_only").orEmpty(),
            estimates = body.str("estimates").orEmpty(),
            services = services,
        )
    }

    /**
     * The figures line the desktop's own page writes for one service
     * (`chatbot-api-keys-settings.js`'s `moneyRow`), so both apps say the same
     * thing in the same words: the PC's own `spent_words`, `left_words` and
     * `until`, unchanged. The three values are drawn as they came - never added
     * up, rounded or re-worded - and a value the PC did not send drops its
     * clause rather than leaving a gap. The framing sentence is the desktop's;
     * every figure in it is the PC's.
     */
    fun figuresLine(s: Service): String {
        val parts = ArrayList<String>(3)
        if (s.spentWords.isNotEmpty()) parts.add("Spent this month: ${s.spentWords}.")
        if (s.leftWords.isNotEmpty()) parts.add("Left: ${s.leftWords}.")
        if (s.until.isNotEmpty()) parts.add("The count starts again on ${s.until}.")
        return parts.joinToString(" ")
    }

    /**
     * A 2xx body turned into what the plate draws. `available: false` (or
     * `ok: false`) is the PC saying, in its own words, that it is not showing
     * amounts - drawn as [Read.Refused] rather than as an empty view.
     */
    fun readBody(body: JsonObject): Read {
        if (body.flag("available") == false || body.flag("ok") == false) {
            return Read.Refused(wordsOf(body) ?: NOT_READ)
        }
        return parseView(body)?.let { Read.Shown(it) } ?: Read.Failed(UNREADABLE_ANSWER)
    }

    /**
     * A failed route turned into the PC's own words where it sent any - null
     * for the rest, which the plate says in the app's own words.
     *
     * The 503 is the one that matters: the route keeps its body through
     * [JarvisApi.probeKeeping503], and `money_unreadable` plus
     * `message` is a refusal the owner must read, not a blank.
     */
    fun readFailure(e: ApiError): Read? = when (e) {
        ApiError.NotFound -> Read.Refused(MISSING)
        // A PC that answers this route without the module behind it.
        ApiError.NotAvailable -> Read.Refused(NOT_READ)
        is ApiError.Server -> if (e.code == 503) Read.Refused(pcWords(e.body) ?: NOT_READ) else null
        else -> null
    }
}
