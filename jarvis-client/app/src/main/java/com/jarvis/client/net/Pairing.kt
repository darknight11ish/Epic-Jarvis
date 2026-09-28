package com.jarvis.client.net

import com.jarvis.client.data.PhoneAddress
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Pairing this phone with the QR code on the PC, or the short typed code -
 * the phone's half of docs/PAIRING-DESIGN.md, phase 1 (sections 3, 6.2,
 * 8.4, 8.5).
 *
 * In plain words: the PC shows a QR code (and an 8-letter code under it).
 * Both hold a one-time secret. The secret itself NEVER goes over the
 * network: the phone proves it saw it by sending a sum made from it (an
 * HMAC - a keyed checksum only someone with the secret can make), and the
 * PC proves it is the real PC by answering with a sum of its own
 * ([pcProof]), which this phone checks before it trusts anything. Both
 * sides then work out the same four short words; the owner compares them
 * with the approval card on the PC.
 *
 * Everything here is pure Kotlin and JDK (no Android types), so the JVM
 * unit tests run it against the design's own test vectors. The network
 * calls go through [PairTransport], which [JarvisApi.pairPost] fills in.
 *
 * Never logged, anywhere: the secret, the typed code, the proofs, the key
 * the PC hands over. This file does no logging at all.
 */
object Pairing {

    /** The two phone routes that take no key (design §6.2). */
    const val CLAIM_PATH = "/api/pair/claim"
    const val COLLECT_PATH = "/api/pair/collect"

    /** How often the phone asks whether the card was approved (design §6.2). */
    const val COLLECT_EVERY_MS = 2_000L

    /** The QR text's fixed start (design §8.4). */
    const val QR_PREFIX = "jarvis-pair:"

    /** Crockford's alphabet: 0-9 and A-Z without I, L, O and U (design §8.5). */
    const val CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    /** How many words the word list must have: one per 4-dice roll. */
    const val WORD_COUNT = 1296

    // ── The owner's words (design §6.2, §7.2, §8.4, §8.5) ────────────────

    const val NOT_A_CODE = "That is not a Jarvis pairing code."
    const val NEWER_CODE = "This code is from a newer Jarvis - update the app."
    const val BAD_TYPED_CODE = "The code is 8 letters and numbers, like K7QM-4TXD."
    const val BAD_NAME = "Use a shorter name, with letters and numbers only."
    const val NOT_MESH =
        "Pairing only works over Tailscale or NordVPN Meshnet. Turn one on, on this phone and on your PC."
    const val GONE = "This code no longer works. On your PC, press Pair a phone again."
    const val NO_CARD = "Your PC could not show the approval card. Try again."
    const val WORDS_DIFFER =
        "The PC answered with different words. Do not approve the card on your PC."
    const val NOT_THE_PC =
        "The answer did not come from the PC that showed this code. Do not approve any card on your PC."
    const val DENIED = "You said no on your PC. Nothing changed on this phone."
    const val TIMED_OUT = "The card on your PC ran out of time. Start again on the PC."
    const val CANCELLED = "The pairing was cancelled on your PC. Start again on the PC."
    const val NO_PAIRING_HERE =
        "Your PC's Jarvis does not have QR pairing yet. Use the old shared key instead."
    const val BAD_REQUEST = "Your PC did not understand this phone's request. Start again on the PC."
    const val BAD_KEY = "Your PC sent a key this app does not understand. Start again on the PC."
    const val NO_ANSWER =
        "Could not reach your PC. Check that Tailscale or NordVPN Meshnet is on, on this phone and on your PC."
    const val WAITED_TOO_LONG = "No answer from your PC in time. Start again on the PC."
    const val CLAIMED_ALREADY =
        "Another device already used this code. On your PC, deny the card it raised, then press Pair a phone again."
    const val APPROVE_IF_SAME = "Approve the card on your PC if it shows these same words."
    const val CAMERA_WHY =
        "Jarvis uses the camera only to read the code on your PC. Nothing is recorded or sent."
    const val CAMERA_REFUSED =
        "Jarvis can't use the camera, so it can't scan the code. Type the code instead, or allow the " +
            "camera for Jarvis in Android's settings."
    const val HOST_NOT_MESH =
        "Pairing needs your PC's Tailscale name (ending in .ts.net) or its NordVPN Meshnet name " +
            "(ending in .nord)."

    /** "That code is not right. 2 tries left." */
    fun wrongCode(triesLeft: Int?): String = when {
        triesLeft == null -> "That code is not right."
        triesLeft <= 0 -> "That code is not right, and it no longer works. On your PC, press Pair a phone again."
        triesLeft == 1 -> "That code is not right. 1 try left."
        else -> "That code is not right. $triesLeft tries left."
    }

    /** The four words as the screens show them: "tulip · anchor · mellow · crane". */
    fun wordsLine(words: List<String>): String = words.joinToString(" · ")

    // ── The QR text (design §8.4) ────────────────────────────────────────

    /** What a QR code or a typed code gives: where the PC is, and the key [k] the sums use. */
    class Target(
        /** Lower case, ends in .ts.net or .nord. */
        val host: String,
        val port: Int,
        /** "qr" or "code". */
        val method: String,
        /** The QR code's pair id; null for a typed code (the PC answers with it). */
        val pairId: String?,
        /** K in the design's sums: the 16 secret bytes, or SHA-256 of the code. */
        internal val key: ByteArray,
        /** When the PC says the code stops working, seconds since 1970 - a countdown only. */
        val expires: Long?,
    ) {
        /** The address as the app saves it: `host:port`. */
        val address: String get() = "$host:$port"

        /** The whole address a request goes to. */
        val base: String get() = "http://$host:$port"

        /** The design's `ref`: the pair id for a QR code, "-" for a typed code. */
        val ref: String get() = pairId ?: "-"
    }

    sealed interface Parsed {
        data class Ok(val target: Target) : Parsed
        data class Bad(val message: String) : Parsed
    }

    private val PAIR_ID = Regex("^[0-9a-f]{16}$")
    private val SECRET = Regex("^[A-Za-z0-9_-]{22}$")
    private val EXPIRES = Regex("^[0-9]{10}$")
    private val PORT = Regex("^[1-9][0-9]{0,4}$")
    private val HOST_CHARS = Regex("^[a-z0-9.-]{1,253}$")
    private val NONCE = Regex("^[A-Za-z0-9_-]{22}$")

    /**
     * `jarvis-pair:1/<host>/<port>/<pair_id>/<secret>/<expires>`, exactly -
     * nothing before or after, no spaces, six parts. The strict shape is on
     * purpose (design §8.4): the same rule in Python, Kotlin and Rust, and no
     * URL library guessing at an odd string.
     */
    fun parseQr(text: String): Parsed {
        if (!text.startsWith(QR_PREFIX)) return Parsed.Bad(NOT_A_CODE)
        val parts = text.substring(QR_PREFIX.length).split("/")
        val version = parts[0]
        if (version != "1") {
            // A plain number other than 1 is a newer format, not a stranger's code.
            return Parsed.Bad(if (version.isNotEmpty() && version.all { it in '0'..'9' }) NEWER_CODE else NOT_A_CODE)
        }
        if (parts.size != 6) return Parsed.Bad(NOT_A_CODE)
        val host = parts[1]
        val portText = parts[2]
        val pairId = parts[3]
        val secret = parts[4]
        val expires = parts[5]
        if (hostProblem(host) != null) return Parsed.Bad(NOT_A_CODE)
        val port = portOf(portText) ?: return Parsed.Bad(NOT_A_CODE)
        if (!PAIR_ID.matches(pairId)) return Parsed.Bad(NOT_A_CODE)
        if (!SECRET.matches(secret)) return Parsed.Bad(NOT_A_CODE)
        if (!EXPIRES.matches(expires)) return Parsed.Bad(NOT_A_CODE)
        val key = runCatching { Base64.getUrlDecoder().decode(secret) }.getOrNull()
        if (key == null || key.size != 16) return Parsed.Bad(NOT_A_CODE)
        return Parsed.Ok(Target(host, port, "qr", pairId, key, expires.toLong()))
    }

    private fun portOf(text: String): Int? =
        text.takeIf { PORT.matches(it) }?.toIntOrNull()?.takeIf { it in 1..65535 }

    /**
     * Null when this phone may pair with [host], else the sentence why not:
     * lower-case letters, digits, dots and dashes, ending in `.ts.net` or
     * `.nord` (the phone reaches the PC only over Tailscale or NordVPN
     * Meshnet), and passing the phone's own address rule ([PhoneAddress]).
     */
    fun hostProblem(host: String): String? {
        if (!HOST_CHARS.matches(host)) return HOST_NOT_MESH
        if (host.startsWith(".") || host.startsWith("-") || ".." in host) return HOST_NOT_MESH
        val mesh = (host.endsWith(".ts.net") && host.length > ".ts.net".length) ||
            (host.endsWith(".nord") && host.length > ".nord".length)
        if (!mesh) return HOST_NOT_MESH
        return PhoneAddress.problem("http://$host")
    }

    // ── The typed code (design §8.5) ─────────────────────────────────────

    /**
     * The code as the sums use it: upper case; spaces and `-` dropped; `O`
     * read as `0`, `I` and `L` as `1`. Null unless exactly 8 characters of
     * [CODE_ALPHABET] are left.
     */
    fun normaliseCode(typed: String): String? {
        val out = StringBuilder()
        for (ch in typed.uppercase()) {
            when {
                ch == ' ' || ch == '-' || ch == '\t' -> Unit
                ch == 'O' -> out.append('0')
                ch == 'I' || ch == 'L' -> out.append('1')
                else -> out.append(ch)
            }
        }
        val code = out.toString()
        return code.takeIf { it.length == 8 && it.all { c -> c in CODE_ALPHABET } }
    }

    /**
     * A typed code aimed at [address] (what the owner typed as the PC's name,
     * with or without `:port`). The port defaults to Jarvis's own.
     */
    fun typedTarget(address: String, typedCode: String, defaultPort: Int): Parsed {
        val code = normaliseCode(typedCode) ?: return Parsed.Bad(BAD_TYPED_CODE)
        var a = address.trim().lowercase()
        a = a.removePrefix("http://").trimEnd('/')
        if (a.startsWith("https://")) return Parsed.Bad(HOST_NOT_MESH)
        val host: String
        val port: Int
        val colon = a.lastIndexOf(':')
        if (colon >= 0) {
            host = a.substring(0, colon)
            port = portOf(a.substring(colon + 1)) ?: return Parsed.Bad(HOST_NOT_MESH)
        } else {
            host = a
            port = defaultPort
        }
        hostProblem(host)?.let { return Parsed.Bad(it) }
        return Parsed.Ok(Target(host, port, "code", null, codeKey(code), null))
    }

    /** K for a typed code: SHA-256 of `"jarvis-pair-code-v1" \0 CODE`. */
    fun codeKey(code: String): ByteArray =
        MessageDigest.getInstance("SHA-256").digest(join("jarvis-pair-code-v1", code))

    // ── The phone's name (design §4) ─────────────────────────────────────

    private val NAME_EXTRA = setOf(' ', '-', '_', '.', '\'', '(', ')')

    /** Null when [name] may be sent, else [BAD_NAME]: 1-40 characters, letters and digits of any script, and `space - _ . ' ( )`. */
    fun nameProblem(name: String): String? {
        val count = name.codePointCount(0, name.length)
        if (count < 1 || count > 40) return BAD_NAME
        var i = 0
        while (i < name.length) {
            val cp = name.codePointAt(i)
            val ok = Character.isLetterOrDigit(cp) || (cp < 0x80 && cp.toChar() in NAME_EXTRA)
            if (!ok) return BAD_NAME
            i += Character.charCount(cp)
        }
        if (name.isBlank()) return BAD_NAME
        return null
    }

    /**
     * The name offered first: the phone's model ("Pixel 9"), with anything
     * the rule refuses dropped. Only a suggestion - the owner can change it,
     * and what is sent is exactly what the field then holds.
     */
    fun suggestedName(model: String?): String {
        val kept = buildString {
            for (ch in model.orEmpty()) {
                if (Character.isLetterOrDigit(ch) || ch in NAME_EXTRA) append(ch)
            }
        }.trim().take(40).trim()
        return if (kept.isEmpty() || nameProblem(kept) != null) "My phone" else kept
    }

    // ── The sums (design §6.2) ───────────────────────────────────────────

    /** base64url with no padding. */
    fun b64u(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)

    /** 16 fresh random bytes, as the phone's nonce. */
    fun newNonce(random: SecureRandom = SecureRandom()): ByteArray = ByteArray(16).also { random.nextBytes(it) }

    /** Text parts joined by a zero byte, as UTF-8. */
    internal fun join(vararg parts: String): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        parts.forEachIndexed { i, p ->
            if (i > 0) out.write(0)
            out.write(p.toByteArray(Charsets.UTF_8))
        }
        return out.toByteArray()
    }

    private fun hmac(key: ByteArray, message: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(message)
    }

    /** T = `"jarvis-pair-v1" \0 method \0 ref \0 phone_nonce \0 name`. */
    fun transcript(method: String, ref: String, phoneNonce: String, name: String): String =
        listOf("jarvis-pair-v1", method, ref, phoneNonce, name).joinToString("\u0000")

    /** proof = b64u(HMAC(K, "claim" \0 T)). */
    fun claimProof(key: ByteArray, t: String): String = b64u(hmac(key, join("claim", t)))

    /** pc_proof = b64u(HMAC(K, "pc" \0 T \0 pc_nonce)). */
    fun pcProof(key: ByteArray, t: String, pcNonce: String): String = b64u(hmac(key, join("pc", t, pcNonce)))

    /** The four word numbers: D = HMAC(K, "words" \0 T \0 pc_nonce); (D[2i]*256 + D[2i+1]) mod 1296. */
    fun wordNumbers(key: ByteArray, t: String, pcNonce: String): List<Int> {
        val d = hmac(key, join("words", t, pcNonce))
        return (0 until 4).map { i ->
            (((d[2 * i].toInt() and 0xff) * 256) + (d[2 * i + 1].toInt() and 0xff)) % WORD_COUNT
        }
    }

    /** collect = b64u(HMAC(K, "collect" \0 pair_id \0 phone_nonce)). */
    fun collectProof(key: ByteArray, pairId: String, phoneNonce: String): String =
        b64u(hmac(key, join("collect", pairId, phoneNonce)))

    /** Compares two proofs in constant time. */
    fun sameProof(a: String, b: String): Boolean =
        MessageDigest.isEqual(a.toByteArray(Charsets.UTF_8), b.toByteArray(Charsets.UTF_8))

    // ── Bodies ───────────────────────────────────────────────────────────

    fun claimBody(target: Target, phoneNonce: String, name: String, proof: String): String {
        val m = linkedMapOf<String, kotlinx.serialization.json.JsonElement>(
            "method" to JsonPrimitive(target.method),
        )
        target.pairId?.let { m["pair_id"] = JsonPrimitive(it) }
        m["phone_nonce"] = JsonPrimitive(phoneNonce)
        m["name"] = JsonPrimitive(name)
        m["proof"] = JsonPrimitive(proof)
        return JsonObject(m).toString()
    }

    fun collectBody(pairId: String, proof: String): String =
        JsonObject(mapOf("pair_id" to JsonPrimitive(pairId), "proof" to JsonPrimitive(proof))).toString()

    // ── Answers (design §6.2's two tables) ───────────────────────────────

    private fun JsonObject?.str(key: String): String? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject?.int(key: String): Int? =
        (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    /** What `POST /api/pair/claim` said. */
    sealed interface Claimed {
        /** 202: the card is up. Not yet checked - see [check]. */
        data class CardUp(
            val pairId: String,
            val pcNonce: String,
            val pcProof: String,
            val words: List<String>,
            val expiresIn: Int?,
        ) : Claimed

        /** Anything else: the sentence to show. [final] is false only for a wrong code with tries left. */
        data class Refused(val message: String, val final: Boolean = true) : Claimed
    }

    /** Reads a claim answer. [code] 0 means nothing answered. */
    fun readClaim(code: Int, body: JsonObject?): Claimed = when (code) {
        202 -> {
            val pairId = body.str("pair_id")
            val pcNonce = body.str("pc_nonce")
            val pcProof = body.str("pc_proof")
            val words = (body?.get("words") as? JsonArray)
                ?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }
            if (pairId == null || !PAIR_ID.matches(pairId) || pcNonce == null || !NONCE.matches(pcNonce) ||
                pcProof == null || words == null || words.size != 4
            ) {
                Claimed.Refused(BAD_REQUEST)
            } else {
                Claimed.CardUp(pairId, pcNonce, pcProof, words, body.int("expires_in"))
            }
        }
        403 -> when (body.str("reason")) {
            "wrong_proof" -> {
                val left = body.int("tries_left")
                val claimed = (body?.get("claimed") as? JsonPrimitive)?.takeIf { !it.isString }?.content == "true"
                if (claimed && (left == null || left > 0)) {
                    // Another device got there first: never "retype it".
                    Claimed.Refused(CLAIMED_ALREADY, final = true)
                } else {
                    Claimed.Refused(wrongCode(left), final = left != null && left <= 0)
                }
            }
            else -> Claimed.Refused(NOT_MESH)
        }
        410 -> Claimed.Refused(GONE)
        400 -> Claimed.Refused(if (body.str("reason") == "name") BAD_NAME else BAD_REQUEST)
        503 -> Claimed.Refused(NO_CARD)
        404 -> Claimed.Refused(NO_PAIRING_HERE)
        0 -> Claimed.Refused(NO_ANSWER)
        else -> Claimed.Refused(BAD_REQUEST)
    }

    /**
     * The phone's own check of a [Claimed.CardUp]: the PC's proof must be
     * the one only the real PC could make, and the words the PC sent must be
     * the ones this phone works out itself. Returns the words to show, or
     * the refusal - never the PC's words on trust.
     */
    fun check(
        target: Target,
        phoneNonce: String,
        name: String,
        up: Claimed.CardUp,
        wordList: List<String>,
    ): Claimed {
        if (target.pairId != null && target.pairId != up.pairId) return Claimed.Refused(NOT_THE_PC)
        val t = transcript(target.method, target.ref, phoneNonce, name)
        if (!sameProof(pcProof(target.key, t, up.pcNonce), up.pcProof)) return Claimed.Refused(NOT_THE_PC)
        if (wordList.size != WORD_COUNT) return Claimed.Refused(BAD_REQUEST)
        val mine = wordNumbers(target.key, t, up.pcNonce).map { wordList[it] }
        if (mine != up.words) return Claimed.Refused(WORDS_DIFFER)
        return up.copy(words = mine)
    }

    /** What `POST /api/pair/collect` said. */
    sealed interface Collected {
        data object Waiting : Collected
        data class Approved(val deviceId: String, val token: String) : Collected
        data class Ended(val message: String) : Collected
        /** Nothing answered this time; worth asking again. */
        data object NoAnswer : Collected
    }

    fun readCollect(code: Int, body: JsonObject?): Collected = when (code) {
        202 -> Collected.Waiting
        200 -> {
            val id = body.str("device_id")
            val token = body.str("token")
            if (id != null && token != null && DeviceKey.isDeviceKey(token) && DeviceKey.idOf(token) == id) {
                Collected.Approved(id, token)
            } else {
                Collected.Ended(BAD_KEY)
            }
        }
        403 -> if (body.str("state") == "denied") Collected.Ended(DENIED) else Collected.Ended(BAD_REQUEST)
        410 -> Collected.Ended(
            when (body.str("state")) {
                "timed_out" -> TIMED_OUT
                "cancelled" -> CANCELLED
                "refused" -> NO_CARD
                else -> GONE
            },
        )
        404 -> Collected.Ended(NO_PAIRING_HERE)
        0 -> Collected.NoAnswer
        else -> if (code >= 500) Collected.NoAnswer else Collected.Ended(BAD_REQUEST)
    }
}

/**
 * The shape of a key made for one device (design §5.1):
 * `jdk1.<id>.<secret>`, where the id is `d` + 8 hex characters and the
 * secret 43 url-safe characters. The old shared key has no prefix.
 */
object DeviceKey {
    /** The design's regex, shared by every scrubber (design §5.1, §8.6). */
    val PATTERN = Regex("jdk1\\.d[0-9a-f]{8}\\.[A-Za-z0-9_-]{43}")

    fun isDeviceKey(token: String): Boolean = PATTERN.matches(token)

    /** The device id inside a device key, or null for anything else. */
    fun idOf(token: String): String? = if (isDeviceKey(token)) token.split(".")[1] else null

    /** [text] with every device key replaced by [with]. */
    fun scrub(text: String, with: String): String = PATTERN.replace(text, with)
}

/** How the phone reaches the two no-key routes: a POST to [base] + [path], answered with a status (0: nothing answered) and a body. */
interface PairTransport {
    suspend fun post(base: String, path: String, json: String): Pair<Int, JsonObject?>
}

/**
 * One claim, then collects until the card is decided. Holds the key [target]
 * and the phone's nonce in memory only, for as long as the attempt lasts.
 */
class PairAttempt(
    val target: Pairing.Target,
    val name: String,
    private val transport: PairTransport,
    nonce: ByteArray = Pairing.newNonce(),
) {
    val phoneNonce: String = Pairing.b64u(nonce)
    private var pairId: String? = target.pairId

    /** Sends the claim and checks the PC's answer. */
    suspend fun claim(wordList: List<String>): Pairing.Claimed {
        val t = Pairing.transcript(target.method, target.ref, phoneNonce, name)
        val body = Pairing.claimBody(target, phoneNonce, name, Pairing.claimProof(target.key, t))
        val (code, obj) = transport.post(target.base, Pairing.CLAIM_PATH, body)
        val read = Pairing.readClaim(code, obj)
        if (read !is Pairing.Claimed.CardUp) return read
        val checked = Pairing.check(target, phoneNonce, name, read, wordList)
        if (checked is Pairing.Claimed.CardUp) pairId = checked.pairId
        return checked
    }

    /** Asks once whether the card was approved. Only after a successful [claim]. */
    suspend fun collect(): Pairing.Collected {
        val id = pairId ?: return Pairing.Collected.Ended(Pairing.BAD_REQUEST)
        val body = Pairing.collectBody(id, Pairing.collectProof(target.key, id, phoneNonce))
        val (code, obj) = transport.post(target.base, Pairing.COLLECT_PATH, body)
        return Pairing.readCollect(code, obj)
    }
}
