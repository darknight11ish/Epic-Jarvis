package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Plain words when something goes wrong, with the fix on the spot (the
 * creativity audit, 2026-09-25, item 5; docs/JARVIS-API.md section 4, "When
 * an answer fails").
 *
 * One mapping from each kind of failure to a short sentence ([Kind.says]),
 * one thing to do ([Kind.fix]) and one button ([Kind.button], [Kind.action]).
 * The SAME words as the desktop's `plain-errors.js`: both are checked, word
 * for word, against `contract/plain-error-cases.json`, which
 * tools/gen_plain_error_cases.py writes from the one list (PlainErrorsTest
 * here, tests/plain-errors.mjs there). Change a word there, regenerate, then
 * here and on the desktop.
 *
 * The technical detail stays available for a bug report behind "Details",
 * scrubbed first ([scrubDetails]): no token, key, password, email address
 * or user name - the backend log scrubber's rules.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object PlainErrors {
    // The actions. Each app turns one into its own place: "retry" asks again
    // (a failed question) or reconnects (anything else), "connection" opens
    // Checks (where "Change desktop or token" is), "models" opens Mind.
    const val RETRY = "retry"
    const val RECONNECT = "reconnect"
    const val CONNECTION = "connection"
    const val MODELS = "models"
    const val NONE = "none"

    val BUTTONS: Map<String, String> = linkedMapOf(
        RETRY to "Try again",
        RECONNECT to "Reconnect",
        CONNECTION to "Check the connection settings",
        MODELS to "Choose a model",
        NONE to "",
    )

    data class Kind(val says: String, val fix: String, val action: String) {
        val button: String get() = BUTTONS[action].orEmpty()
    }

    val KINDS: Map<String, Kind> = linkedMapOf(
        "pc_unreachable" to Kind(
            "Your PC isn't answering.",
            "It may be asleep or switched off, or Tailscale or NordVPN Meshnet may be off at one end. " +
                "Wake the PC, check the private network on both, then try again.",
            RETRY,
        ),
        "jarvis_not_running" to Kind(
            "Jarvis isn't running on your PC.",
            "The PC is on, but Jarvis is not started. Start it from the desktop app (Settings, Start " +
                "Jarvis), then try again.",
            RETRY,
        ),
        "name_not_found" to Kind(
            "This device can't find your PC by its name.",
            "Check that Tailscale or NordVPN Meshnet is on here, and that the PC's name in the " +
                "connection settings is right.",
            CONNECTION,
        ),
        "device_offline" to Kind(
            "This device isn't connected to a network.",
            "Turn on Wi-Fi or mobile data, then try again.",
            RETRY,
        ),
        "connection_dropped" to Kind(
            "The connection to your PC dropped.",
            "Try again. If it keeps happening, check the private network is steady at both ends.",
            RETRY,
        ),
        "link_stale" to Kind(
            "The connection to your PC is catching up.",
            "Nothing can be sent until it does. Wait a moment, or reconnect.",
            RECONNECT,
        ),
        "token_wrong" to Kind(
            "Your PC didn't accept this app's pairing key.",
            "Enter the key again in the connection settings. The PC's desktop app shows it: " +
                "Settings, \"Show the token for my phone\".",
            CONNECTION,
        ),
        "not_paired" to Kind(
            "This app isn't connected to a PC yet.",
            "Add your PC's name and pairing key in the connection settings.",
            CONNECTION,
        ),
        "not_jarvis" to Kind(
            "Something answered at that address, but it isn't Jarvis.",
            "Check the PC's name and port in the connection settings.",
            CONNECTION,
        ),
        "backend_too_old" to Kind(
            "Your PC's Jarvis is too old for this.",
            "Update it: on the PC, run apply-patches.ps1, then restart Jarvis.",
            NONE,
        ),
        "feature_off" to Kind(
            "That part of Jarvis isn't running on your PC right now.",
            "Restart Jarvis on the PC. If it stays off, run apply-patches.ps1 there to update it.",
            NONE,
        ),
        "server_error" to Kind(
            "Jarvis on your PC ran into a problem.",
            "Try again. If it keeps happening, restart Jarvis on the PC and send the Details with a bug " +
                "report.",
            RETRY,
        ),
        "unreadable" to Kind(
            "Your PC answered in a way this app can't read.",
            "Update both: run apply-patches.ps1 on the PC, and install the latest app.",
            NONE,
        ),
        "timeout" to Kind(
            "Jarvis took too long to answer.",
            "Try again in a moment. If it keeps happening, restart Ollama on the PC.",
            RETRY,
        ),
        "model_missing" to Kind(
            "The AI model Jarvis uses isn't installed on your PC.",
            "Choose a model you have (Models, in the Brain on the PC or the phone), or " +
                "install this one.",
            MODELS,
        ),
        "model_not_running" to Kind(
            "The AI model isn't running on your PC.",
            "Open Ollama on the PC (or restart Jarvis), then try again.",
            RETRY,
        ),
        "model_stuck" to Kind(
            "The AI model stopped answering.",
            "Restart Ollama on the PC, then try again.",
            RETRY,
        ),
        "model_stopped" to Kind(
            "The AI model stopped in the middle of the answer.",
            "Try again. If it keeps happening, restart Ollama on the PC.",
            RETRY,
        ),
        "model_error" to Kind(
            "The AI model reported a problem.",
            "Try again. If it keeps happening, restart Ollama on the PC.",
            RETRY,
        ),
        "key_store_refused" to Kind(
            "Windows Credential Manager wouldn't save it.",
            "Nothing was written anywhere else. Try again; if it keeps failing, restart the PC and try " +
                "once more.",
            RETRY,
        ),
        // The PC said what is wrong in its own sentence: shown as it is.
        "pc_said" to Kind("", "", NONE),
    )

    /** The waits. "loading" is the PC's word for a model not yet in memory. */
    val STATUSES: Map<String, String> = linkedMapOf(
        "thinking" to "Thinking…",
        "loading" to "Waking up the model - the first answer after standby takes a little longer.",
        "working" to "Working…",
        "approval" to "Waiting for your approval…",
        "answering" to "Answering…",
    )

    /** The stream's error `code` (jarvis_agent.ERROR_CODES) -> a kind. */
    val CODES: Map<String, String> = linkedMapOf(
        "model_missing" to "model_missing",
        "model_not_running" to "model_not_running",
        "model_stuck" to "model_stuck",
        "model_stopped" to "model_stopped",
        "model_error" to "model_error",
    )

    /** The Details are at most this long, after scrubbing. */
    const val DETAILS_MAX = 600

    /** [ApiError.Unreachable.network] for "no PC address saved yet". */
    const val NOT_PAIRED = "not_paired"

    private val NETWORK = mapOf(
        "refused" to "jarvis_not_running",
        "connect_timeout" to "pc_unreachable",
        "no_route" to "pc_unreachable",
        "unknown_host" to "name_not_found",
        "no_network" to "device_offline",
        "read_timeout" to "timeout",
        "dropped" to "connection_dropped",
    )

    /** One failure, described the way the contract file's `classify` cases are. */
    data class Input(
        val network: String? = null,
        val http: Int? = null,
        val said: String? = null,
        val available: Boolean? = null,
        val code: String? = null,
        val stale: Boolean = false,
        val notPaired: Boolean = false,
        val malformed: Boolean = false,
        val notJarvis: Boolean = false,
        val keyStore: Boolean = false,
    )

    /** The kind for one failure - the same rules as the desktop's `classify`. */
    fun classify(i: Input): String {
        if (i.notPaired) return "not_paired"
        if (i.stale) return "link_stale"
        if (i.keyStore) return "key_store_refused"
        if (i.notJarvis) return "not_jarvis"
        if (i.malformed) return "unreadable"
        i.network?.let { return NETWORK[it] ?: "connection_dropped" }
        i.code?.let { c -> CODES[c]?.let { return it } }
        val said = i.said?.trim().orEmpty()
        return when {
            i.http == 401 || i.http == 403 -> "token_wrong"
            i.http == 501 -> "backend_too_old"
            i.http == 503 && i.available == false -> "backend_too_old"
            said.isNotEmpty() -> "pc_said"
            i.http == 404 -> "backend_too_old"
            i.http == 503 -> "feature_off"
            else -> "server_error"
        }
    }

    /** What to show: what happened, what to do, the button, and the Details. */
    data class Shown(
        val kind: String,
        val says: String,
        val fix: String,
        val button: String,
        val action: String,
        val details: String = "",
        /** A failed QUESTION: "Try again" asks it again, rather than reconnecting. */
        val chat: Boolean = false,
    ) {
        /** The one line a notice shows: what happened, then what to do. */
        val text: String get() = listOf(says, fix).filter { it.isNotBlank() }.joinToString(" ")
    }

    /** The PC's sentences start in lower case, and may lack a full stop. */
    private fun sentence(text: String?): String {
        val t = text?.trim().orEmpty()
        if (t.isEmpty()) return t
        val s = t.replaceFirstChar { it.uppercaseChar() }
        return if (s.last() in ".!?") s else "$s."
    }

    fun shown(kind: String, pcSaid: String? = null, details: String = ""): Shown {
        if (kind == "pc_said") {
            val says = sentence(pcSaid).ifEmpty { KINDS.getValue("server_error").says }
            return Shown(kind, says, "", "", NONE, details)
        }
        val k = KINDS[kind] ?: KINDS.getValue("server_error")
        val named = if (KINDS.containsKey(kind)) kind else "server_error"
        return Shown(named, k.says, k.fix, k.button, k.action, details)
    }

    /** The shown words for a failure, with its technical detail scrubbed behind Details. */
    fun forInput(i: Input, detail: String = ""): Shown {
        val kind = classify(i)
        val tech = listOfNotNull(
            i.http?.let { "HTTP $it" }, i.network, detail.takeIf { it.isNotBlank() },
        ).joinToString(" · ")
        return shown(kind, i.said, scrubDetails("($kind) $tech"))
    }

    /**
     * The network failure's kind, from the exception's class name and
     * message (OkHttp on Android): refused -> Jarvis not running, a connect
     * that timed out or found no route -> the PC is not answering, an
     * unknown name, no network on this device, a read that timed out.
     */
    fun networkKind(className: String, message: String?): String {
        val m = message.orEmpty()
        return when {
            className == "UnknownHostException" -> "unknown_host"
            className == "NoRouteToHostException" || "EHOSTUNREACH" in m ||
                "No route to host" in m -> "no_route"
            "ENETUNREACH" in m || "Network is unreachable" in m -> "no_network"
            className == "ConnectException" && ("ETIMEDOUT" in m || "timed out" in m) -> "connect_timeout"
            className == "ConnectException" -> "refused"
            className == "SocketTimeoutException" &&
                (m.startsWith("failed to connect") || m.startsWith("connect timed out")) -> "connect_timeout"
            className == "SocketTimeoutException" || className == "InterruptedIOException" -> "read_timeout"
            else -> "dropped"
        }
    }

    /** [networkKind] for a real exception. */
    fun networkKind(t: Throwable): String = networkKind(t::class.java.simpleName, t.message)

    /** The PC's own sentence in an error body (`{"error": "..."}` or `{"error": {"message"}}`). */
    fun saidIn(body: String?): Pair<String?, Boolean?> {
        val obj = runCatching { JarvisJson.parseToJsonElement(body.orEmpty()) as? JsonObject }.getOrNull()
            ?: return null to null
        val err = obj["error"]
        val said = (err as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            ?: ((err as? JsonObject)?.get("message") as? JsonPrimitive)?.contentOrNull
            ?: (obj["detail"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        val available = (obj["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
        return said?.trim()?.takeIf { it.isNotEmpty() } to available
    }

    /**
     * Any request's failure in plain words. [handshake] true for
     * `GET /api/version`, where a 404 means "not Jarvis at all" rather than
     * "a Jarvis too old for this route".
     */
    fun forApiError(e: ApiError, handshake: Boolean = false): Shown = when (e) {
        is ApiError.Unreachable -> when (e.network) {
            NOT_PAIRED -> forInput(Input(notPaired = true), e.detail)
            // This app's own sentence (a blocker): it is the plain words.
            "" -> shown("pc_said", e.detail)
            else -> forInput(Input(network = e.network), e.detail)
        }
        ApiError.BadToken -> forInput(Input(http = 401))
        ApiError.AlreadyHandled -> Shown("pc_said", "Already handled elsewhere.", "", "", NONE)
        ApiError.NotFound ->
            if (handshake) forInput(Input(notJarvis = true), "HTTP 404")
            else forInput(Input(http = 404))
        ApiError.NotAvailable -> forInput(Input(http = 503))
        is ApiError.Server -> {
            val (said, available) = saidIn(e.body)
            forInput(Input(http = e.code, said = said, available = available), e.body.take(400))
        }
        is ApiError.Malformed -> forInput(Input(malformed = true), e.detail)
    }

    // ── The Details scrubber ─────────────────────────────────────────────
    // The backend's log scrubber's rules (backend/jarvis_scrub.py), for text
    // an app shows: the token it holds, then shapes. Addresses, ports and
    // status codes stay - a bug report needs them.

    private const val HIDDEN = "[hidden]"
    private val SHAPES: List<Pair<Regex, String>> = listOf(
        Regex("(?i)(x-jarvis-token[\"']?\\s*[:=]\\s*[\"']?)[^\\s\"'&,;]+") to "$1$HIDDEN",
        Regex("(?i)\\b(authorization\\s*:\\s*)(?:bearer|basic|token)?\\s*[^\\s\"',;]+") to "$1$HIDDEN",
        Regex("(?i)\\b(bearer|basic)\\s+[A-Za-z0-9._~+/=-]{8,}") to "$1 $HIDDEN",
        Regex("(?i)\\b([a-z][a-z0-9+.-]*://[^/\\s:@]+:)[^/\\s@]+(?=@)") to "$1$HIDDEN",
        Regex("(?i)([?&](?:access_|refresh_|id_|auth_)?(?:token|api[_-]?key|key|secret|password|passwd|sig|signature)=)[^&\\s#\"']+") to "$1$HIDDEN",
        Regex("(?i)\\b((?:api[ _-]?key|token|secret|password|passwd|pwd|passphrase)\\s*[:=]\\s*[\"']?)[^\\s\"',;&]+") to "$1$HIDDEN",
        Regex("-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\\s\\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)") to HIDDEN,
        Regex("\\b(?:AKIA|ASIA)[0-9A-Z]{16}\\b") to HIDDEN,
        Regex("\\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{22,})") to HIDDEN,
        Regex("\\bglpat-[A-Za-z0-9_-]{20,}") to HIDDEN,
        Regex("\\b(?:sk|rk)_(?:test|live)_[A-Za-z0-9]{16,}") to HIDDEN,
        Regex("\\bsk-[A-Za-z0-9_-]{16,}") to HIDDEN,
        Regex("\\btvly-[A-Za-z0-9_-]{12,}") to HIDDEN,
        Regex("\\bya29\\.[0-9A-Za-z_-]{20,}") to HIDDEN,
        Regex("\\bxox[baprs]-[A-Za-z0-9-]{10,}") to HIDDEN,
        Regex("\\bAIza[0-9A-Za-z_-]{30,}") to HIDDEN,
        Regex("\\bhf_[A-Za-z0-9]{30,}") to HIDDEN,
        Regex("\\beyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}") to HIDDEN,
        Regex("(?i)/private-[0-9a-f]{16,}") to "/$HIDDEN",
        // A long run of letters AND digits: a token with no prefix (the
        // pairing token is 43 of them). Hex ids of 32 and fewer stay.
        Regex("(?<![\\w./-])(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\\d)[A-Za-z0-9_-]{33,}(?![\\w-])") to HIDDEN,
        Regex("(?<![\\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)+") to "[email]",
        Regex("(?i)(\\b[a-z]:[\\\\/]+users[\\\\/]+|(?<![\\w.])/home/|(?<![\\w.])/Users/)[^\\\\/\\s]+") to "$1[user]",
    )

    /**
     * [text] with every secret taken out, cut to [DETAILS_MAX]. [token] - the
     * pairing token this app holds, when given - goes first, whatever it
     * looks like.
     */
    fun scrubDetails(text: String?, token: String? = null): String {
        var out = text.orEmpty()
        if (token != null && token.length >= 4) out = out.replace(token, HIDDEN)
        for ((rx, to) in SHAPES) out = rx.replace(out, to)
        out = out.replace(Regex("\\s+"), " ").trim()
        return if (out.length > DETAILS_MAX) out.take(DETAILS_MAX - 1) + "…" else out
    }
}
