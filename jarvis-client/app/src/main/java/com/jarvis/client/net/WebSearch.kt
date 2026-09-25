package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Web search (the owner's decisions of 2026-09-25; docs/JARVIS-API.md
 * section 23; backend `jarvis_search.py`, `web-search.patch`).
 *
 * Four providers, SearXNG the default (a search program on the PC, in
 * Docker), then DuckDuckGo (the ddgs package), Tavily and Brave Search. Each
 * has a short "why use this one" line: the PC sends them with every
 * `GET /api/search`, and Mind shows the PC's words. The copies below are the
 * same words (backend/test_web_search.py checks them against the PC's and
 * the desktop's `web-search.js`), used only when an answer lacks them.
 *
 * What the phone does: choose the provider, set the SearXNG address, turn
 * "Ask before every web search" on (at once) or off (ONE approval card on
 * the PC), and run a test search - each ONE change, held on a stale link.
 *
 * What the phone does NOT do: take a Tavily or Brave key. There is no box for
 * one and no route for one. Sending a key over the link to the PC would send
 * it somewhere other than its one service (CLAUDE.md rule 3); keys are typed
 * on the PC ([KEY_ENTRY]). The phone shows only whether one is saved.
 *
 * Pure Kotlin, no Android types, so `WebSearchTest` runs it on a plain JVM
 * against `contract/web-search-cases.json` - the PC's real answers.
 */
object WebSearch {
    const val PATH = "/api/search"
    const val SETTINGS_PATH = "/api/search/settings"
    const val TEST_PATH = "/api/search/test"

    val PROVIDERS = listOf("searxng", "duckduckgo", "tavily", "brave")
    val KEYED = setOf("tavily", "brave")
    const val DEFAULT_ADDRESS = "http://127.0.0.1:8888"

    val WHY: Map<String, String> = mapOf(
        "searxng" to
            "Free, no key and no account: a search program that runs on this PC in Docker and asks several search engines for you, without their cookies or trackers. Those engines still see your internet address, and it needs Docker plus one setting (JSON) switched on.",
        "duckduckgo" to
            "Free, no key, and only one Python package to install (ddgs). It reads DuckDuckGo's public pages because there is no official way in, so it can be slowed down or stop working when DuckDuckGo changes, and DuckDuckGo still sees your internet address.",
        "tavily" to
            "Made for AI assistants: short, clean results, with 1,000 free credits a month (a basic search uses one). Needs a free account and a key, and Tavily sees what you search, tied to your key.",
        "brave" to
            "Brave's own independent index, with about \$5 of free credit each month. Needs an account, a payment card to verify it, and a key, and Brave sees what you search, tied to your key.",
    )
    val LABEL: Map<String, String> = mapOf(
        "searxng" to "SearXNG (on this PC)",
        "duckduckgo" to "DuckDuckGo",
        "tavily" to "Tavily",
        "brave" to "Brave Search",
    )
    const val WHOOGLE_WHY =
        "Not offered: its own README says it no longer returns results, since Google blocked searching without JavaScript in 2025."
    const val DEFAULT_WHY =
        "SearXNG is the default because it costs nothing, needs no key or account, and runs on this PC, so no single search company keeps a record of your searches."
    const val ASK_LABEL = "Ask before every web search"
    const val ASK_DETAIL =
        "Off (the default): Jarvis asks first only when private things could slip into a search - after it has read your email, files, notes, saved memories or other outside text - and shows you the exact search words. On: it asks before every search. Turning this on is immediate; turning it off asks you with an approval card."
    const val KEY_ENTRY =
        "Keys are entered on the PC only - in the desktop app's Settings, Web search, or with one line in PowerShell (backend/README.md). The phone never asks for one: sending a key to the PC would send it somewhere other than its own service."
    val KEY_WHERE: Map<String, String> = mapOf(
        "tavily" to "https://app.tavily.com (sign in, then API Keys)",
        "brave" to "https://api-dashboard.search.brave.com (sign up, add a card, then API Keys)",
    )

    // The desktop's words (web-search.js), for the parts of the screen.
    const val TITLE = "Web search"
    const val DETAIL =
        "Choose where Jarvis searches the web. Only the search words are sent, to the search you " +
            "choose, and never quietly to another one: if it is not working, Jarvis says so and offers " +
            "to switch."
    const val MISSING = "Your PC's Jarvis does not have web search yet - run apply-patches.ps1 on the PC."
    const val LEFT_OUT_TITLE = "Left out"
    const val ADDRESS_LABEL = "SearXNG address"
    const val ADDRESS_NOTE =
        "This PC or your own network only (your home network, Tailscale or NordVPN Meshnet). Leave " +
            "it empty for this PC's http://127.0.0.1:8888."
    const val ADDRESS_SAVE = "Save address"
    const val KEYS_TITLE = "Keys"
    const val KEY_SAVED = "A key is saved on this PC."
    const val KEY_NONE = "No key saved yet."
    const val KEY_UNKNOWN = "Could not check whether a key is saved."
    const val TEST_LABEL = "Test search"
    const val TEST_BUSY = "Searching…"
    const val TEST_NOTE =
        "Sends one search for the word \"wikipedia\" through the search you chose, and says what " +
            "happened. It is a real search: on Tavily it uses one credit."
    const val READY = "Ready."
    const val CHOSEN = "In use."
    const val WAITING_CARD = "Waiting for your approval card."
    const val STALE =
        "Not connected to the desktop, so changes and the test wait until the link is back."

    data class Provider(
        val id: String,
        val label: String,
        val why: String,
        val needsKey: Boolean,
        val keySaved: Boolean?,
        val keyWhere: String,
        val ready: Boolean,
        val state: String,
        val said: String,
    )

    data class LeftOut(val label: String, val why: String)

    data class View(
        val provider: String?,
        val why: String,
        val defaultWhy: String,
        val providers: List<Provider>,
        val leftOut: List<LeftOut>,
        val address: String,
        val askEveryTime: Boolean,
        val askLabel: String,
        val askDetail: String,
        val keyEntry: String,
        val waiting: Boolean,
        val last: String,
    )

    /** `GET /api/search`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): View? {
        val providers = (body["providers"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.text("id")?.takeIf { it in PROVIDERS } ?: return@mapNotNull null
            Provider(
                id = id,
                label = o.text("label") ?: LABEL[id] ?: id,
                why = o.text("why") ?: WHY[id].orEmpty(),
                needsKey = o.flag("needs_key") == true,
                keySaved = o.flag("key_saved"),
                keyWhere = o.text("key_where") ?: KEY_WHERE[id].orEmpty(),
                ready = o.flag("ready") == true,
                state = o.text("state") ?: "",
                said = o.text("said") ?: "",
            )
        } ?: return null
        if (providers.isEmpty()) return null
        val leftOut = (body["left_out"] as? JsonArray)?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val label = o.text("label") ?: return@mapNotNull null
            LeftOut(label, o.text("why") ?: "")
        } ?: listOf(LeftOut("Whoogle", WHOOGLE_WHY))
        return View(
            provider = body.text("provider")?.takeIf { it in PROVIDERS },
            why = body.text("why") ?: "",
            defaultWhy = body.text("default_why") ?: DEFAULT_WHY,
            providers = providers,
            leftOut = leftOut,
            address = body.text("searxng_url") ?: DEFAULT_ADDRESS,
            askEveryTime = body.flag("ask_every_time") == true,
            askLabel = body.text("ask_every_time_label") ?: ASK_LABEL,
            askDetail = body.text("ask_every_time_detail") ?: ASK_DETAIL,
            keyEntry = body.text("key_entry") ?: KEY_ENTRY,
            waiting = body.flag("waiting") == true,
            last = (body["last"] as? JsonObject)?.text("message") ?: "",
        )
    }

    /** A read that failed because this PC has no web search. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    /** The line under a provider: in use, ready, or what stands in the way. */
    fun providerLine(p: Provider, chosen: String?): String {
        val now = if (p.id == chosen) "$CHOSEN " else ""
        return (if (p.ready) "$now$READY" else "$now${p.said}").trim()
    }

    /** The line under a key: saved, not, or unknown - never the key. */
    fun keyLine(p: Provider): String = when (p.keySaved) {
        true -> KEY_SAVED
        false -> KEY_NONE
        null -> KEY_UNKNOWN
    }

    /** ONE change: the provider. Null for anything but the four. */
    fun providerBody(id: String): String? =
        if (id in PROVIDERS) JsonObject(mapOf("provider" to JsonPrimitive(id))).toString() else null

    /** ONE change: the SearXNG address (the PC decides whether it is the owner's own network). */
    fun addressBody(url: String): String? {
        val u = url.trim()
        if (u.length > 200) return null
        return JsonObject(mapOf("searxng_url" to JsonPrimitive(u))).toString()
    }

    /** ONE change: "Ask before every web search". Off raises a card on the PC. */
    fun askBody(on: Boolean): String = JsonObject(mapOf("ask_every_time" to JsonPrimitive(on))).toString()

    /** A POST's status and body, the way [Hardware.classifyPost] reads them. */
    fun classifyPost(code: Int, body: JsonObject?): ApiResult<JsonObject> = when {
        code == 401 || code == 403 -> ApiResult.Failed(ApiError.BadToken)
        code == 404 && body?.text("error") == null -> ApiResult.Failed(ApiError.NotFound)
        body?.flag("available") == false -> ApiResult.Failed(ApiError.NotAvailable)
        code in 200..299 && body != null -> ApiResult.Ok(body)
        body?.text("error") != null -> ApiResult.Ok(body)
        code == 503 -> ApiResult.Failed(ApiError.NotAvailable)
        else -> ApiResult.Failed(ApiError.Server(code, ""))
    }

    /** What to tell the owner after a change: the PC's own sentence. */
    fun replyLine(result: ApiResult<JsonObject>): String = when (result) {
        is ApiResult.Ok -> result.value.text("error") ?: result.value.text("said") ?: "Done."
        is ApiResult.Failed -> when (val e = result.error) {
            ApiError.NotFound, ApiError.NotAvailable -> MISSING
            ApiError.BadToken -> "Nothing changed. Your PC refused this phone's token. Pair the phone again."
            is ApiError.Unreachable -> "Nothing changed. Could not reach your PC: ${e.detail}."
            else -> "Nothing changed. Your PC answered in a way this screen cannot read."
        }
    }

    /** Test search's answer as one line, with the offer to switch when it did not work. */
    fun testLine(result: ApiResult<JsonObject>): Pair<Boolean, String> = when (result) {
        is ApiResult.Ok -> {
            val ok = result.value.flag("ok") == true
            val said = result.value.text("said") ?: result.value.text("error") ?: "It did not work."
            val offer = if (ok) null else result.value.text("offer")
            ok to (if (offer != null) "$said $offer" else said)
        }
        is ApiResult.Failed -> false to replyLine(result).removePrefix("Nothing changed. ")
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
