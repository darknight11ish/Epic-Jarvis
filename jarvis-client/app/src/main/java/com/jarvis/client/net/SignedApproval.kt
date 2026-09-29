package com.jarvis.client.net

import java.security.MessageDigest
import java.util.Base64
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Signed approvals, the phone's half (docs/PAIRING-DESIGN.md §11): a risky
 * approval from a paired phone carries a signature that only this phone's
 * fingerprint or PIN can make, so a stolen key alone cannot approve.
 *
 * Only pure Kotlin here - the words, the hash, the bytes that are signed, the
 * reading of the PC's answers and the decision "which way does this approval
 * go" - so the JVM tests hold every rule. The Android Keystore is in
 * `platform/ApprovalKey.kt`, the fingerprint prompt in `BiometricGate`.
 *
 * Nothing here is ever logged: not a nonce, not a signature, not the words.
 */
object SignedApproval {

    const val KEY_PATH = "/api/devices/approval-key"
    const val CHALLENGE_PATH = "/api/approve/challenge"
    const val APPROVE_PATH = "/api/approve"

    /** The separator between the four parts of the words: the single byte 0x1F. */
    private const val UNIT_SEP = "\u001F"
    private const val NUL = "\u0000"
    private const val SIGN_PREFIX = "jarvis-approve-v1"

    // ── The words hash ────────────────────────────────────────────────────

    /**
     * The `text` part of the words: `detail.text` when the wire's `detail` is
     * an object with a `text` string, the detail itself when it is a plain
     * string, else "". Taken from the RAW wire row, before the phone rewrites
     * it for display (`normalisePendingRow`).
     */
    fun wordsTextOf(detail: JsonElement?): String = when (detail) {
        is JsonObject -> (detail["text"] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: ""
        is JsonPrimitive -> if (detail.isString) detail.content else ""
        else -> ""
    }

    /**
     * Lowercase hex SHA-256 (UTF-8) of id, action, title and text joined by
     * the single byte 0x1F. [title] is the title the phone DISPLAYS.
     */
    fun wordsSha256(id: String, action: String, title: String, text: String): String {
        val joined = listOf(id, action, title, text).joinToString(UNIT_SEP)
        return hex(MessageDigest.getInstance("SHA-256").digest(joined.toByteArray(Charsets.UTF_8)))
    }

    /** The hash of what the phone showed for [item]. */
    fun wordsSha256(item: PendingItem): String =
        wordsSha256(item.id, item.action.orEmpty(), item.title, item.signText)

    private fun hex(bytes: ByteArray): String =
        bytes.joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }

    /** True when the PC's hash is the phone's own. Compared without regard to letter case. */
    fun wordsMatch(item: PendingItem, pcHash: String): Boolean =
        wordsSha256(item).equals(pcHash.trim(), ignoreCase = true)

    // ── What is signed, and how it travels ────────────────────────────────

    /**
     * `"jarvis-approve-v1" 0x00 id 0x00 action 0x00 nonce 0x00 words_sha256`
     * (the hash as ASCII hex), as UTF-8 bytes.
     */
    fun signedMessage(id: String, action: String, nonce: String, wordsSha256: String): ByteArray =
        listOf(SIGN_PREFIX, id, action, nonce, wordsSha256).joinToString(NUL).toByteArray(Charsets.UTF_8)

    /** Base64url, no padding: the public key and the signature travel this way. */
    fun b64url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)

    /** What `POST /api/approve` carries besides the id. */
    data class Signature(val device: String, val nonce: String, val sig: String)

    /** The body of `POST /api/approve`: `{"id"}` as ever, plus `"signature"` when there is one. */
    fun approveBody(id: String, signature: Signature?): String {
        val fields = mutableMapOf<String, JsonElement>("id" to JsonPrimitive(id))
        if (signature != null) {
            fields["signature"] = JsonObject(
                mapOf(
                    "device" to JsonPrimitive(signature.device),
                    "nonce" to JsonPrimitive(signature.nonce),
                    "sig" to JsonPrimitive(signature.sig),
                ),
            )
        }
        return JsonObject(fields).toString()
    }

    /** The body of `POST /api/approve/challenge`. */
    fun challengeBody(id: String): String = JsonObject(mapOf("id" to JsonPrimitive(id))).toString()

    /** The body of `POST /api/devices/approval-key`: the SPKI DER public key, base64url. */
    fun registerBody(publicKeyDer: ByteArray): String =
        JsonObject(mapOf("public_key" to JsonPrimitive(b64url(publicKeyDer)))).toString()

    // ── The PC's answers ──────────────────────────────────────────────────

    sealed interface ChallengeAnswer {
        data class Got(val nonce: String, val wordsSha256: String, val expiresIn: Int) : ChallengeAnswer

        /** 403 `owner_check: no_approval_key`: this phone has none on the PC. */
        data object NoApprovalKey : ChallengeAnswer

        /** 404: the card is no longer there. */
        data object CardGone : ChallengeAnswer

        data class Refused(val words: String) : ChallengeAnswer
    }

    /** `POST /api/approve/challenge`, read. */
    fun challengeAnswer(code: Int, body: JsonObject?): ChallengeAnswer {
        val check = (body?.get("owner_check") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return when {
            code == 200 -> {
                val nonce = (body?.get("nonce") as? JsonPrimitive)?.takeIf { it.isString }?.content.orEmpty()
                val words = (body?.get("words_sha256") as? JsonPrimitive)?.takeIf { it.isString }?.content.orEmpty()
                val expires = (body?.get("expires_in") as? JsonPrimitive)?.intOrNull ?: 0
                if (nonce.isBlank() || !HEX64.matches(words)) {
                    ChallengeAnswer.Refused(CHALLENGE_UNREADABLE)
                } else {
                    ChallengeAnswer.Got(nonce, words, expires)
                }
            }
            code == 403 && check == REFUSAL_NO_APPROVAL_KEY -> ChallengeAnswer.NoApprovalKey
            code == 404 -> ChallengeAnswer.CardGone
            else -> {
                val why = (body?.get("error") as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                ChallengeAnswer.Refused(why?.takeIf { it.isNotBlank() }?.let { "Not approved. $it" } ?: NOT_ACCEPTED)
            }
        }
    }

    private val HEX64 = Regex("[0-9a-fA-F]{64}")

    /** `POST /api/devices/approval-key`, read: true when the PC now waits for its card. */
    fun registerAnswer(code: Int, body: JsonObject?): Pair<Boolean, String> {
        val why = (body?.get("error") as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        return when (code) {
            200, 202 -> true to WAITING_WORDS_SETTINGS
            503 -> false to (why?.takeIf { it.isNotBlank() } ?: NEEDS_CRYPTO)
            404 -> false to MISSING
            else -> false to (why?.takeIf { it.isNotBlank() }?.let { "Not turned on. $it" } ?: "Not turned on. Try again.")
        }
    }

    const val REFUSAL_NO_APPROVAL_KEY = "no_approval_key"
    const val REFUSAL_NO_SIGNATURE = "no_signature"
    const val REFUSAL_BAD_SIGNATURE = "bad_signature"

    /** The refusal word in a 403's body, when it is one of the three this feature explains. */
    fun refusalIn(bodyText: String?): String? {
        val obj = runCatching { JarvisJson.parseToJsonElement(bodyText.orEmpty()) as? JsonObject }.getOrNull()
        val word = (obj?.get("owner_check") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return word?.takeIf {
            it == REFUSAL_NO_APPROVAL_KEY || it == REFUSAL_NO_SIGNATURE || it == REFUSAL_BAD_SIGNATURE
        }
    }

    /** The sentence for a refusal word, or null for none of the three. */
    fun refusalWords(word: String?): String? = when (word) {
        REFUSAL_NO_APPROVAL_KEY -> OFFER_WORDS
        REFUSAL_NO_SIGNATURE -> NOT_ACCEPTED
        REFUSAL_BAD_SIGNATURE -> OFFER_BAD_WORDS
        else -> null
    }

    // ── This phone's state, and which way an approval goes ────────────────

    /** What this phone's own Keystore holds. */
    enum class Local { NONE, READY, INVALID }

    /** What Settings, Devices says about signed approvals on this phone. */
    enum class State(val line: String) {
        /** Paired, no approval key. */
        OFF("Off. Risky approvals from this phone are held until you turn it on."),
        WAITING("Waiting for your yes on the PC."),
        ON("On. Risky approvals need your fingerprint or PIN, signed on this phone."),
        AGAIN("Needs turning on again. This phone no longer has a working approval key."),

        /** Not paired with a key of its own: nothing to sign with. */
        NOT_PAIRED("Pair this phone first (Pair a phone, in Settings, Devices, on your PC)."),

        /** An older PC that does not know signed approvals: nothing to show. */
        UNSUPPORTED(""),
    }

    /**
     * [pc] is this phone's row's `approval_key` from `GET /api/devices`:
     * "waiting", "true" or "false" - and null when the row has none (an older PC).
     */
    fun stateOf(usesOwnKey: Boolean, pc: String?, local: Local): State = when {
        !usesOwnKey -> State.NOT_PAIRED
        pc == null -> State.UNSUPPORTED
        local == Local.INVALID -> State.AGAIN
        pc == "true" -> if (local == Local.READY) State.ON else State.AGAIN
        pc == "waiting" -> if (local == Local.READY) State.WAITING else State.OFF
        else -> State.OFF
    }

    /** Which way one approval goes. */
    enum class Path {
        /** Today's way, unchanged. */
        PLAIN,

        /** Challenge, check the words, fingerprint prompt with the key, signature. */
        SIGNED,

        /** Offer the one button "Turn on signed approvals". */
        OFFER,

        /** The same button, worded "again". */
        OFFER_AGAIN,

        /** Registered, waiting for the owner's yes on the PC. */
        WAITING,
    }

    /**
     * [state] is null when it could not be read: then today's way, and the PC
     * says `no_approval_key` if it needed one. A card that is not risky, the
     * shared key, and a PC without signed approvals all keep today's way.
     */
    fun pathFor(risky: Boolean, state: State?): Path = when {
        !risky || state == null -> Path.PLAIN
        else -> when (state) {
            State.ON -> Path.SIGNED
            State.OFF -> Path.OFFER
            State.AGAIN -> Path.OFFER_AGAIN
            State.WAITING -> Path.WAITING
            State.NOT_PAIRED, State.UNSUPPORTED -> Path.PLAIN
        }
    }

    // ── Words ─────────────────────────────────────────────────────────────

    const val TURN_ON = "Turn on signed approvals"
    const val TURN_OFF = "Turn off"

    /** The notice that carries the one button [TURN_ON]. */
    const val OFFER_WORDS =
        "Nothing was approved. Risky approvals from this phone need to be signed with your " +
            "fingerprint or PIN, and signed approvals are not turned on yet."

    const val OFFER_AGAIN_WORDS =
        "Nothing was approved. This phone's approval key stopped working (a fingerprint was " +
            "added or the screen lock changed), so signed approvals need turning on again."

    /**
     * The PC refused this phone's signature. The usual cause is a key the PC
     * no longer holds the other half of (a re-registration the owner denied on
     * the PC, or one that never got through), so the one button makes a fresh
     * key and asks the PC once more.
     */
    const val OFFER_BAD_WORDS =
        "Nothing was approved. The PC did not accept this phone's signature - it may hold a " +
            "different key than this phone does. Turn signed approvals on again to make a fresh " +
            "key; your PC asks you once more."

    const val WAITING_WORDS =
        "Nothing was approved. Signed approvals are waiting for your yes on the PC. Approve the " +
            "card there, then try again."

    const val CARD_CHANGED = "The card changed on your PC. Look at it again."

    const val NOT_ACCEPTED =
        "The PC did not accept the signed approval. Try again; if it keeps failing, turn signed " +
            "approvals off and on again in Settings -> Devices."

    const val CHALLENGE_UNREADABLE = "Your PC's answer could not be read, so nothing was approved. Try again."

    const val SIGN_FAILED = "The signing did not work just now, so nothing was approved. Try again."

    const val WAITING_WORDS_SETTINGS = "Waiting for your yes on the PC."

    const val NEEDS_CRYPTO =
        "Signed approvals need the cryptography package on your PC. Nothing was turned on."

    const val MISSING = "Your PC's Jarvis does not have signed approvals yet."

    const val KEY_NOT_MADE =
        "This phone could not make the approval key. It needs a screen lock (Android's Settings, " +
            "Security, Screen lock). Nothing was turned on."

    const val TURNED_OFF =
        "Signed approvals are off on this phone and its key is deleted. Your PC still lists it " +
            "until you remove it in the PC's Devices list; risky approvals from this phone are " +
            "held until you turn it on again."

    /** True when [text] is a notice that carries the one button [TURN_ON]. */
    fun offersTurnOn(text: String?): Boolean =
        text == OFFER_WORDS || text == OFFER_AGAIN_WORDS || text == OFFER_BAD_WORDS

    /** The notice for an approval that took a path other than SIGNED or PLAIN. */
    fun noticeFor(path: Path): String? = when (path) {
        Path.OFFER -> OFFER_WORDS
        Path.OFFER_AGAIN -> OFFER_AGAIN_WORDS
        Path.WAITING -> WAITING_WORDS
        Path.PLAIN, Path.SIGNED -> null
    }
}

/**
 * The reason the PC gave when it refused the LAST approval for want of a
 * signature ([SignedApproval.refusalIn]) - kept as a word only, never the
 * body. [JarvisApi.approve] sets it on a 403 and clears it on every approval
 * it sends; [com.jarvis.client.JarvisRuntime.decide] takes it, so that a
 * refusal it explains is not shown as a refused key (which would send the
 * owner to the pairing screen).
 */
object ApprovalRefusal {
    @Volatile private var word: String? = null

    fun note(bodyText: String?) {
        word = SignedApproval.refusalIn(bodyText)
    }

    fun clear() {
        word = null
    }

    /** The word, once. */
    fun take(): String? = word.also { word = null }
}
