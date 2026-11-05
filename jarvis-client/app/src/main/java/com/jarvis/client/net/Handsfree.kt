package com.jarvis.client.net

import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Hands-free mode, as the phone sees it (owner's request, 2026-11-04).
 *
 * WHAT IT IS, in the owner's words: a setting he can turn off, and in that mode
 * ANY approval card for a task he asked Jarvis to do is read out loud, and he
 * answers "confirm" or "deny" with his voice. The phone is the ears, the mouth
 * and the SMS hand; the PC decides. That split is not a preference here - it is
 * the project's own rule that a client never does speech-to-text (CLAUDE.md),
 * so the phone records one clip and uploads it (`/api/handsfree/answer`), and
 * the PC transcribes it, checks it against the owner's voice print and decides.
 *
 * THE FROZEN CONTRACT (both halves land together; the PC lane owns the backend
 * section of docs/JARVIS-API.md):
 *
 *  - events, over the one existing stream (`/api/events`):
 *      `handsfree_card` {`card_id`, `action`, `say`, `expires_in_sec`}
 *      `phone_command`  {`id`, `kind:"send_sms"`, `contact`, `text`}
 *  - routes:
 *      `GET  /api/handsfree`           the state, as [Read]
 *      `POST /api/handsfree/enabled`   {"enabled": bool} - ON may answer 202
 *                                      "waiting" with a card, OFF 200 at once
 *      `POST /api/handsfree/answer`    {"card_id", "data_b64", "sample_rate"}
 *                                      -> {"ok", "heard", "decision", "card_state"}
 *                                      a refusal SENTENCE is not in the
 *                                      contract; one is read leniently from
 *                                      `why`/`refusal`/`reason`/... when the PC
 *                                      sends it, and otherwise the phone says
 *                                      the general refusal ([REFUSED]) - never
 *                                      "the card had expired" without the card's
 *                                      own state saying so.
 *      `POST /api/phone/result`        {"id", "ok", "receipt", "why"}
 *  - the spoken audio for a card comes from the existing `POST /api/voice/say`
 *    (a WAV). The phone NEVER makes up its own words for card text.
 *
 * HONEST DEGRADATION, which is the half this file exists to make checkable: a
 * PC that has never heard of hands-free answers 404 on all four routes, and
 * sends neither event. Then [NOT_HERE] is what the owner is told, the Settings
 * switch says so, and nothing is invented: no mode is claimed, no card is read
 * out, and no microphone is opened. That is a state with its own words rather
 * than a feature that looks broken ([readOf] and [Enabled.of] are where the
 * 404 becomes those words).
 *
 * Everything here is PURE - no Android, no socket - so `HandsfreeEventTest`
 * holds every parse, every line of plain words and the degradation to the
 * contract above, on the JVM, in CI's required phone-unit-tests job.
 */
object Handsfree {

    // ------------------------------------------------------------ routes ----

    /** `GET` the state; `POST` nothing (the switch has its own route). */
    const val PATH = "/api/handsfree"

    /** `POST {"enabled": bool}`. ON may answer 202 with a card waiting. */
    const val ENABLED_PATH = "/api/handsfree/enabled"

    /** `POST` one recorded clip of the owner saying confirm or deny. */
    const val ANSWER_PATH = "/api/handsfree/answer"

    /** `POST` what happened to a `phone_command` this phone carried out. */
    const val RESULT_PATH = "/api/phone/result"

    // ------------------------------------------------------------ events ----

    /** A card the PC wants read out. */
    const val EVENT_CARD = "handsfree_card"

    /** Something the PC wants this phone to DO. Only `send_sms` today. */
    const val EVENT_COMMAND = "phone_command"

    /** The one `phone_command` kind this app carries out. */
    const val KIND_SEND_SMS = "send_sms"

    /**
     * The sample rate the answer clip is sent at: the SAME format the PC asks
     * every other upload for (`audio_in` in `/api/voice/status`), and the rate
     * `Recorder` already records at, so nothing here invents a second format.
     */
    const val SAMPLE_RATE = 16_000

    // ------------------------------------------------------------- words ----

    /**
     * The Settings row's heading. Also the search index's title, so a search
     * for "hands free" finds this row - see `SettingsSearch.ROWS`.
     */
    const val SECTION = "Hands-free"

    /**
     * What the mode does, in plain words - the sentence under the switch.
     *
     * One string, because it is shown in three places (the Settings row, the
     * confirmation line, the docs) and three copies of a sentence about what
     * the microphone does is three chances to describe it differently.
     */
    const val ABOUT = "Jarvis reads each approval card out loud on this phone, " +
        "then listens for ten seconds so you can say \"confirm\" or \"deny\". " +
        "It can also write a text message to a contact you ask for."

    /**
     * The second Settings line, and the one that matters most for trust: the
     * microphone is open only inside that ten seconds, never while no card is
     * waiting.
     */
    const val WHEN_LISTENING = "The microphone opens only while a card is being answered - " +
        "ten seconds, after the card has been read out - and it says so on screen while it does."

    /** The switch's own two states. */
    const val ON = "Hands-free is on"
    const val OFF = "Hands-free is off"

    /**
     * The ONE sentence a PC without the feature gets, on every surface. Not a
     * failure and not red: the app has no reason to think anything is broken -
     * this desktop simply does not have it yet (both halves ship together).
     */
    const val NOT_HERE = "Hands-free is not available on this PC yet."

    /** The same fact, short enough for Home's one-line status. */
    const val NOT_HERE_SHORT = "Hands-free: not on this PC"

    /** Home's status word while the mode is armed. */
    const val ARMED_SHORT = "Hands-free"

    /** Reading out a card, before the listening window opens. */
    const val READING = "Reading the card out…"

    /** The listening window's own state - the words on the talk button. */
    const val LISTENING = "Listening for your confirm/deny"

    /** After the clip has gone: the PC is deciding. */
    const val SENDING = "Sending your answer to the PC…"

    /** Nothing at all was heard, so nothing was sent. */
    const val NOTHING_HEARD = "I didn't catch that - say confirm or deny."

    /** Words came back but the PC's voice check did not pass. */
    const val NOT_YOUR_VOICE = "That was not your voice - nothing was approved."

    /** The card expired before the answer arrived. */
    const val CARD_GONE = "That card had already been answered or expired - nothing changed."

    /**
     * The general refusal: the PC would not take the answer and did not say
     * why in words.
     *
     * WHY IT EXISTS RATHER THAN [CARD_GONE]. The frozen contract's answer body
     * is `{ok, heard, decision, card_state}` and carries no refusal SENTENCE, so
     * an `ok:false` with nothing else used to be reported as "the card had
     * already expired" - a guess, and the wrong one for the common refusal (a
     * voice check that did not pass, a card the PC would not decide). The
     * expired sentence now needs the card's own state to say so; everything
     * else gets this one (audit finding, 2026-11-05).
     */
    const val REFUSED = "Your PC did not accept that answer - nothing changed."

    /** The mode was turned off while a card was being handled. */
    const val STOPPED = "Hands-free is off, so nothing was said."

    /** A card, read out while the owner was on a call - never spoken over one. */
    const val IN_CALL = "You were on a call, so the card was not read out. " +
        "It is in the notification, and on your Home screen."

    /** OFF is immediate - the PC's own contract says so, and so does this. */
    const val OFF_DONE = "Hands-free is off. Jarvis will not read cards out or listen for an answer."

    /** ON while the PC is already armed and nothing has to be approved. */
    const val ON_DONE = "Hands-free is on. Cards for what you ask Jarvis to do will be read out."

    /**
     * ON going through the PC's own card. The contract says a 202 means
     * waiting, and a waiting card is answered where cards always are - it is
     * never assumed to have been accepted by the fact that it was asked for.
     */
    const val ON_WAITING = "Hands-free will be on once you approve the card your PC just raised."

    /** The chat/Live command's own words, so the two surfaces cannot drift. */
    const val COMMAND_ON = "turn on hands-free"
    const val COMMAND_OFF = "turn off hands-free"

    /** What the chat says when the owner asks for the state instead. */
    const val COMMAND_STATE = "hands-free?"

    /**
     * The audio the PC's own speech comes from. The phone never synthesises a
     * card's words: an unavailable voice is a card that is shown and not said,
     * never a card said in the phone's own voice.
     */
    const val NO_VOICE = "The PC could not make the sound, so the card is shown only."

    // ------------------------------------------------------------ models ----

    /**
     * One card the PC wants read out.
     *
     * @param cardId the id a recorded answer is posted against.
     * @param action the card's kind (`change_own_config`, `models_switch`, ...).
     *   Never shown to the owner on its own - `CardWords` has the plain words -
     *   but it is what the notification's short title falls back to.
     * @param say the whole sentence to read out, in the PC's words. It is sent
     *   to `/api/voice/say` exactly as it arrives.
     * @param expiresInSec how long the card itself has left. 0 or less means
     *   the PC did not say, and nothing is claimed about it.
     */
    data class Card(
        val cardId: String,
        val action: String = "",
        val say: String = "",
        val expiresInSec: Int = 0,
    ) {
        /** True when there is an id to answer against, which is the whole point. */
        val answerable: Boolean get() = cardId.isNotBlank()
    }

    /**
     * One thing the PC asked this phone to do.
     *
     * @param id the id posted back to `/api/phone/result`.
     * @param kind only [KIND_SEND_SMS] is carried out; anything else is
     *   reported back as not done, with [UNKNOWN_KIND] as the reason. A PC that
     *   grows a new kind before this phone ships the code for it must never see
     *   silence and must never see a false "done".
     * @param contact the name the owner said. The PHONE resolves it against its
     *   own address book - see [SmsSend.resolve] - because the PC has no
     *   address book and must not be given one.
     * @param text the exact words to send.
     */
    data class Command(
        val id: String,
        val kind: String,
        val contact: String = "",
        val text: String = "",
    ) {
        val answerable: Boolean get() = id.isNotBlank()
    }

    /** The reason a `phone_command` this app cannot carry out posts back. */
    const val UNKNOWN_KIND = "This phone does not know how to do that."

    /**
     * What the PC decided about one recorded answer.
     *
     * The four fields are the frozen contract's, and `heard` is the PC's own
     * transcription - the phone shows it, which is how the owner can tell "it
     * misheard me" from "it did not hear me".
     *
     * @param ok false when the PC refused the clip or failed to check it.
     * @param heard what the PC's speech model heard, or null/blank when it
     *   heard no words.
     * @param decision `approved`/`denied` and the spellings [APPROVE] and
     *   [DENY] list; anything else is shown as the PC's own word - including a
     *   refusal ([NOT_OUR_VOICE]), which is read even when `ok` is false.
     * @param cardState the card's state after the answer (`waiting`,
     *   `approved`, `denied`, `expired`), or null when the PC did not say. It
     *   is what makes [CARD_GONE] true; without it, a refusal with no words is
     *   [REFUSED].
     * @param why the PC's own sentence about a refusal, when it wrote one. It
     *   is read from `why`, `refusal`, `detail`, `reason`, `message` or `note`,
     *   because the frozen contract has no refusal field ([plain]).
     */
    data class Answer(
        val ok: Boolean,
        val heard: String? = null,
        val decision: String? = null,
        val cardState: String? = null,
        val why: String? = null,
    )

    /**
     * The state `GET /api/handsfree` answers, read leniently.
     *
     * READ LENIENTLY ON PURPOSE. This half of the feature ships against a
     * backend another lane is writing at the same time, and the one shape that
     * is pinned by the frozen contract is the EVENTS and the four ROUTES - the
     * state object's own keys are the PC's to choose. So every key below is
     * read by its most likely name, an alias is accepted where the project
     * already uses one (`on` for `enabled`, exactly as `/api/model-lanes/auto`
     * does), and anything absent falls to a value that claims nothing.
     *
     * @param available false only when the PC says so in words. A 404 from the
     *   route is a separate, stronger "this PC does not have it" and never
     *   reaches here at all ([readOf]).
     * @param enabled whether the PC has the mode armed.
     * @param card a card already waiting, when the PC names one.
     * @param why the PC's own sentence about the state, shown as it is.
     */
    data class Read(
        val available: Boolean,
        val enabled: Boolean,
        val card: Card? = null,
        val why: String? = null,
    )

    /**
     * What `POST /api/handsfree/enabled` answered.
     *
     * @param waiting true for the contract's 202: a card has been raised and
     *   the mode is NOT on yet. Nothing may say "on" while this is true.
     * @param cardId the card's id, when the PC named one.
     * @param why the PC's own sentence, when it gave one.
     */
    data class Enabled(
        val waiting: Boolean,
        val cardId: String? = null,
        val why: String? = null,
    ) {
        companion object {
            /**
             * The answer, from the HTTP status and body - the one place the
             * contract's 202/200 split is turned into words.
             *
             * A `waiting` card is never reported as on: the owner has not
             * approved anything yet, and the PC said so.
             */
            fun of(status: Int, body: JsonObject?): Enabled {
                val why = body?.let { plain(it) }
                val cardId = body?.let { string(it, "card_id", "cardId", "id") }
                return Enabled(waiting = status == 202, cardId = cardId, why = why)
            }
        }
    }

    // ----------------------------------------------------------- parsing ----

    /** What an event carried, or null when it is not one of ours. */
    sealed interface Arrival {
        data class CardArrived(val card: Card) : Arrival
        data class CommandArrived(val command: Command) : Arrival
    }

    /**
     * Reads one event by its kind. Anything else - including a `handsfree_card`
     * whose id is missing, because an answer to it could not be posted - is
     * null, which the caller ignores in silence: the stream carries every kind
     * this app knows and a few it does not, and an unknown one is not an error.
     *
     * This is the whole of "unknown events are ignored", kept pure so
     * `HandsfreeEventTest` can hold it: a `phone_command` of an unknown `kind`
     * IS returned (with the unknown kind intact) rather than dropped, because
     * the PC is owed a result saying this phone could not do it.
     */
    fun arrival(kind: String, data: JsonElement?): Arrival? {
        val obj = data as? JsonObject ?: return null
        return when (kind) {
            EVENT_CARD -> {
                val id = string(obj, "card_id", "cardId", "id") ?: return null
                if (id.isBlank()) return null
                Arrival.CardArrived(
                    Card(
                        cardId = id,
                        action = string(obj, "action").orEmpty(),
                        say = string(obj, "say", "text").orEmpty(),
                        expiresInSec = int(obj, "expires_in_sec", "expiresInSec") ?: 0,
                    ),
                )
            }
            EVENT_COMMAND -> {
                val id = string(obj, "id", "command_id", "commandId") ?: return null
                if (id.isBlank()) return null
                Arrival.CommandArrived(
                    Command(
                        id = id,
                        kind = string(obj, "kind").orEmpty(),
                        contact = string(obj, "contact", "to").orEmpty(),
                        text = string(obj, "text", "body").orEmpty(),
                    ),
                )
            }
            else -> null
        }
    }

    /** `GET /api/handsfree`'s body, or the honest "nothing said" read. */
    fun readOf(body: JsonObject?): Read {
        if (body == null) return Read(available = false, enabled = false)
        val available = bool(body, "available") ?: true
        val enabled = bool(body, "enabled", "on") ?: false
        val card = (body["card"] as? JsonObject)?.let { arrival(EVENT_CARD, it) }
            as? Arrival.CardArrived
        val inline = arrival(EVENT_CARD, body) as? Arrival.CardArrived
        return Read(
            available = available,
            enabled = enabled,
            card = card?.card ?: inline?.card,
            why = plain(body),
        )
    }

    /** `POST /api/handsfree/answer`'s body, read leniently; null when it is not an object. */
    fun answerOf(body: JsonObject?): Answer {
        if (body == null) return Answer(ok = false)
        return Answer(
            // `ok` absent is NOT a refusal: a PC that answers with the four
            // contract fields and no `ok` still heard something. Only an
            // explicit false refuses.
            ok = bool(body, "ok") ?: true,
            heard = string(body, "heard"),
            decision = string(body, "decision"),
            cardState = string(body, "card_state", "cardState", "state"),
            why = plain(body),
        )
    }

    // ------------------------------------------------------------- bodies ----

    /** `{"enabled": true|false}` - the contract's one key, and nothing else. */
    fun enabledBody(enabled: Boolean): String = "{\"enabled\":$enabled}"

    /**
     * The answer upload: `{"card_id", "data_b64", "sample_rate"}`.
     *
     * [wav] is the 16 kHz mono clip [com.jarvis.client.handsfree.HandsfreeClip]
     * built. It is base64 in JSON because the contract says so, and the clip is
     * the owner's voice: nothing here logs it, and no caller may.
     */
    fun answerBody(cardId: String, wav: ByteArray, rate: Int = SAMPLE_RATE): String {
        val b64 = com.jarvis.client.handsfree.HandsfreeClip.base64(wav)
        return "{\"card_id\":${quote(cardId)},\"data_b64\":${quote(b64)}," +
            "\"sample_rate\":${rate.coerceIn(8_000, 48_000)}}"
    }

    /** `{"id", "ok", "receipt", "why"}` - what happened to a [Command]. */
    fun resultBody(id: String, ok: Boolean, receipt: String, why: String): String =
        "{\"id\":${quote(id)},\"ok\":$ok,\"receipt\":${quote(receipt)}," +
            "\"why\":${quote(why)}}"

    // -------------------------------------------------------------- words ----

    /** Decision words the PC may use for a yes, all of them meaning approved. */
    val APPROVE = setOf("approved", "approve", "yes", "confirmed", "confirm", "allowed", "allow")

    /** ...and for a no. */
    val DENY = setOf("denied", "deny", "no", "declined", "decline", "refused", "refuse")

    /**
     * Decisions that mean "the clip was heard and was not the owner's" - the
     * PC's voice check did not pass, so nothing was approved.
     */
    val NOT_OUR_VOICE = setOf(
        "not_you", "not-you", "not_owner", "not-owner", "other_voice", "other-voice",
        "wrong_voice", "wrong-voice", "voice_mismatch", "refused_voice", "impostor",
    )

    /**
     * Card states that make [CARD_GONE] the true sentence: the answer arrived
     * after the card had been decided elsewhere or had timed out.
     */
    val GONE = setOf("expired", "answered", "decided", "gone", "missing", "not_waiting")

    /**
     * What the owner is shown after an answer, in plain words - one of four
     * sentences, never a raw decision token.
     *
     * The order of the branches is the whole of the rule and is written down
     * here rather than discovered from the tests:
     *
     *  1. the PC said `ok: false` - its own sentence if it gave one ([why],
     *     which also reads a `refusal`/`reason`/`detail` field when the PC
     *     sends one), then a voice check that did not pass ([NOT_YOUR_VOICE] -
     *     checked HERE, inside the refusal, because `{"ok":false,
     *     "decision":"not_you"}` used to short-circuit to "the card had
     *     expired"), then [CARD_GONE] only when the card's own state says it is
     *     gone, and otherwise [REFUSED];
     *  2. the PC named a voice check that did not pass - [NOT_YOUR_VOICE];
     *  3. a yes or a no - "Heard: \"...\" - approved/denied";
     *  4. no words at all - [NOTHING_HEARD], with no claim about the card;
     *  5. words but no decision - [NOT_YOUR_VOICE], because something was heard
     *     and nothing was approved, which is exactly what the owner must know.
     */
    fun answerWords(a: Answer): String {
        val decision = a.decision?.trim()?.lowercase().orEmpty()
        if (!a.ok) {
            val why = a.why?.trim().orEmpty()
            if (why.isNotEmpty()) return why
            if (decision in NOT_OUR_VOICE) return NOT_YOUR_VOICE
            // The refusal sentence is the PC's to give and the contract has no
            // field for it, so "the card had expired" may only be said when the
            // card's own state says so. Anything else is the general refusal -
            // never a guess about expiry.
            val state = a.cardState?.trim()?.lowercase().orEmpty()
            return if (state in GONE) CARD_GONE else REFUSED
        }
        if (decision in NOT_OUR_VOICE) return NOT_YOUR_VOICE
        val heard = a.heard?.trim().orEmpty()
        val said = if (heard.isEmpty()) "yes" else heard
        if (decision in APPROVE) return "Heard: \"$said\" - approved."
        if (decision in DENY) return "Heard: \"$said\" - denied."
        if (heard.isEmpty()) return NOTHING_HEARD
        if (decision.isEmpty()) return NOT_YOUR_VOICE
        // The PC's own word, quoted as it came: an unclassified decision is
        // still the answer, and inventing "approved" for it would be the one
        // claim this app may never make.
        return "Heard: \"$heard\" - the PC said \"${a.decision}\"."
    }

    /**
     * One line for Home's status, or null when there is nothing to say.
     *
     * @param missing true when this PC answered 404 for the feature - the
     *   honest "not on this PC yet", which is a fact about the desktop and not
     *   a fault in the phone.
     */
    fun oneLine(read: Read?, missing: Boolean): String? = when {
        missing -> NOT_HERE_SHORT
        read == null -> null
        !read.available -> NOT_HERE_SHORT
        read.enabled -> ARMED_SHORT
        else -> null
    }

    // ------------------------------------------------------------ command ----

    /** What a typed or spoken sentence asked for. */
    enum class Asked { ON, OFF, STATE }

    /**
     * "turn on hands-free" / "turn off hands-free" / "hands-free?" - the chat
     * and Live command, in the owner's own wording.
     *
     * Deliberately narrow, and it returns null for everything else: this is the
     * ONE sentence the phone answers without the PC, and a wide net here would
     * take ordinary questions away from the model. Both hyphenated spellings
     * ("hands-free", "hands free") are accepted because the owner writes both,
     * and trailing punctuation is stripped so a typed sentence works.
     */
    fun command(text: String): Asked? {
        val t = text.trim().lowercase().trimEnd('.', '!', '?', ' ')
            .replace('-', ' ').replace(Regex("\\s+"), " ")
        if (t.isEmpty()) return null
        // 1. The state question: "hands-free?", "hands free mode", and the
        //    "is/are" forms. Read first, because "is hands free on" is a
        //    question while "hands free on" is a request to turn it on.
        if (t == "hands free" || t == "handsfree" ||
            t == "hands free mode" || t == "handsfree mode"
        ) {
            return Asked.STATE
        }
        Regex("^(is|are) (hands free|handsfree)( mode)?( on| off)?$").matchEntire(t)
            ?.let { return Asked.STATE }
        // 2. The verb, in either order of the two words after it: "turn on
        //    hands-free", "set handsfree off", "switch the hands free on".
        Regex(
            "^(turn|switch|put|set) (on|off)( the)? (hands free|handsfree)( mode)?$",
        ).matchEntire(t)?.let { m ->
            return if (m.groupValues[2] == "on") Asked.ON else Asked.OFF
        }
        Regex(
            "^(turn|switch|put|set) (the )?(hands free|handsfree)( mode)? (on|off)$",
        ).matchEntire(t)?.let { m ->
            return if (m.groupValues[4] == "on") Asked.ON else Asked.OFF
        }
        // 3. The verbless form: "hands free on", "handsfree off".
        if (t == "hands free on" || t == "handsfree on") return Asked.ON
        if (t == "hands free off" || t == "handsfree off") return Asked.OFF
        return null
    }

    // ------------------------------------------------------------ helpers ----

    /** A JSON string literal, the same encoding `JarvisApi.quote` uses. */
    private fun quote(s: String): String = JarvisJson.encodeToString(String.serializer(), s)

    private fun string(o: JsonObject, vararg names: String): String? = names
        .firstNotNullOfOrNull { n ->
            (o[n] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                ?.takeIf { it.isNotBlank() }
        }

    private fun bool(o: JsonObject, vararg names: String): Boolean? = names
        .firstNotNullOfOrNull { n -> (o[n] as? JsonPrimitive)?.booleanOrNull }

    private fun int(o: JsonObject, vararg names: String): Int? = names
        .firstNotNullOfOrNull { n -> (o[n] as? JsonPrimitive)?.intOrNull }

    /**
     * The PC's own sentence, when it wrote one.
     *
     * READ LENIENTLY ON PURPOSE. The frozen contract's answer body has no
     * field for a refusal SENTENCE, so a PC that refuses in words may put them
     * anywhere: the keys below are every name this project already uses for
     * "why", plus `refusal` for an answer. Reading them all is how a PC's own
     * sentence reaches the owner instead of this app inventing one - and when
     * none is present, [answerWords] says the general refusal rather than
     * blaming the card's expiry.
     */
    private fun plain(o: JsonObject): String? =
        string(o, "why", "refusal", "detail", "reason", "message", "note")
}
