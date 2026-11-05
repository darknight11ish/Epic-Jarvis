package com.jarvis.client.net

import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.JsonArray
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
 * THE FROZEN CONTRACT is `docs/JARVIS-API.md` section 191, written by the PC
 * half (PR #1169) and not phone-owned: this file follows it, and where this
 * file's older shape disagreed with it the contract won (2026-11-05). It is:
 *
 *  - the setting `[handsfree] enabled`, false by default. ON is ONE ask-tier
 *    card, OFF is instant and raises nothing.
 *  - `GET  /api/handsfree` -> {ok, enabled, window_sec: 60,
 *    vocabulary: {confirm[8], deny[7]}, voice_print, phone: {ready, why},
 *    reading}. `reading` is the newest read-out the PC sent, or null - the
 *    fallback for a card this phone missed while the stream was down.
 *  - `POST /api/handsfree {"enabled": bool}` -> 200 {ok, enabled, changed,
 *    message}. ON refused by its own card is 403 {ok:false, enabled:false,
 *    error}; a settings file that cannot be written is 409. There is no 202
 *    and no "waiting" state in this contract: the PC's route answers after the
 *    card has been decided.
 *  - events, over the one existing stream (`/api/events`):
 *      `handsfree_card` {`card_id`, `action`, `say`, `expires_in_sec`}
 *      `phone_command`  {`id`, `kind:"send_sms"`, `contact`, `text`}
 *      `phone_result`   {`id`, `ok`, `say`, `receipt`, `why`}
 *  - `POST /api/handsfree/answer` {`card_id`, `data_b64` (16-bit PCM WAV, mono,
 *    16 kHz), `sample_rate`} -> 200 {ok, heard, decision, card_state, say}.
 *    `say` is the sentence the phone SPEAKS - every answer carries one, so the
 *    phone never writes its own refusal. Documented refusals: 400 (no clip / an
 *    unreadable clip / a mismatched rate / over 30 s), 403 (the mode is off, or
 *    the voice was not the owner's, or no print is enrolled), 409 (no read-out,
 *    past the window, the card is gone, already decided), 503 (a check could
 *    not run). A 403 is the ORDINARY refusal here, not a bad token, and its
 *    body carries the words.
 *  - `POST /api/phone/result` {`id`, `ok`, `receipt`, `why`} -> the PC's own
 *    receipt, then the `phone_result` event.
 *
 * TWO THINGS THAT LOOK SMALL AND ARE NOT:
 *
 *  1. `expires_in_sec` is the ANSWER window, not the card's own deadline
 *     (section 191.4 says so in as many words). The phone listens for that
 *     window - a minute at most, or the card's own shorter countdown - and the
 *     clip it uploads is capped at the PC's 30 seconds, because a longer one is
 *     refused rather than truncated (section 191.5).
 *  2. `say` is the PC's own sentence and is what the phone speaks and shows. An
 *     answer read with no `say` falls back to this file's words, but a PC that
 *     sends `say` is never paraphrased - the refusal sentences are the PC's,
 *     not this app's.
 *
 * HONEST DEGRADATION: a PC that has never heard of hands-free answers 404 on
 * these routes, and sends none of the three events. Then [NOT_HERE] is what the
 * owner is told, the Settings switch says so, and nothing is invented: no mode
 * is claimed, no card is read out, and no microphone is opened. That is a state
 * with its own words rather than a feature that looks broken ([readOf] and
 * [Enabled.of] are where the 404 becomes those words).
 *
 * Everything here is PURE - no Android, no socket - so `HandsfreeEventTest`
 * holds every parse, every line of plain words and the degradation to the
 * contract above, on the JVM, in CI's required phone-unit-tests job.
 */
object Handsfree {

    // ------------------------------------------------------------ routes ----

    /**
     * `GET` the state; `POST {"enabled": bool}` the switch. ONE path in the
     * frozen contract (section 191.0/191.3) - the older
     * `/api/handsfree/enabled` does not exist on the PC and is gone.
     */
    const val PATH = "/api/handsfree"

    /** `POST` one recorded clip of the owner saying confirm or deny. */
    const val ANSWER_PATH = "/api/handsfree/answer"

    /** `POST` what happened to a `phone_command` this phone carried out. */
    const val RESULT_PATH = "/api/phone/result"

    // ------------------------------------------------------------ events ----

    /** A card the PC wants read out. */
    const val EVENT_CARD = "handsfree_card"

    /** Something the PC wants this phone to DO. Only `send_sms` today. */
    const val EVENT_COMMAND = "phone_command"

    /** The PC's own word on a text this phone was asked to send. */
    const val EVENT_RESULT = "phone_result"

    /** The one `phone_command` kind this app carries out. */
    const val KIND_SEND_SMS = "send_sms"

    // ------------------------------------------------------------- audio ----

    /**
     * The rate the answer clip is sent at: the SAME format the PC asks every
     * other upload for (`audio_in` in `/api/voice/status`), and the rate
     * [com.jarvis.client.handsfree.HandsfreeClip] resamples to, so the body's
     * `sample_rate` can never disagree with the WAV it carries (section 191.5).
     */
    const val SAMPLE_RATE = 16_000

    /** The answer window the PC opens for a read-out, in seconds (section 191.4). */
    const val WINDOW_SEC = 60

    /**
     * The longest clip the PC will accept, in seconds (section 191.5).
     *
     * A longer one is REFUSED, never truncated, so the phone records at most
     * this much however long the answer window is.
     */
    const val MAX_CLIP_SEC = 30

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
     * the microphone does is three chances to describe it differently. The
     * window is the PC's - a minute at most - so this says a minute, not the
     * ten seconds this app used to open (section 191.4).
     */
    const val ABOUT = "Jarvis reads each approval card out loud on this phone, " +
        "then listens for your answer - one word, within the minute your PC allows. " +
        "It can also write a text message to a contact you ask for."

    /**
     * The second Settings line, and the one that matters most for trust: the
     * microphone is open only inside that answer window, never while no card is
     * waiting.
     */
    const val WHEN_LISTENING = "The microphone opens only while a card is being answered - " +
        "for your PC's answer window, a minute at most - and it says so on screen while it does."

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

    /** The card's answer window ran out before an answer was recorded. */
    const val WINDOW_OVER = "That card's minute for an answer is over - nothing was decided."

    /** Nothing at all was heard, so nothing was sent. */
    const val NOTHING_HEARD = "I didn't catch that - say confirm or deny."

    /**
     * The PC asked once more and this phone has no `say` from it to repeat (a
     * PC older than the frozen contract): the same question, in this app's
     * words. A PC that sends `say` is always preferred ([answerWords]).
     */
    const val ASK_AGAIN = "Sorry - I didn't catch a clear yes or no. Say \"confirm\" or \"deny\"."

    /** Words came back but the PC's voice check did not pass. */
    const val NOT_YOUR_VOICE = "That was not your voice - nothing was approved."

    /**
     * The card was already answered or had expired when the answer arrived.
     * Only said when the PC's own `card_state` says so and it sent no `say`.
     */
    const val CARD_GONE = "That card had already been answered or expired - nothing changed."

    /**
     * The general refusal, for a PC that refused and sent no words at all: the
     * frozen contract's answer body always carries `say`, so this is only the
     * fallback for a PC older than it.
     */
    const val REFUSED = "Your PC did not accept that answer - nothing changed."

    /** The mode was turned off while a card was being handled. */
    const val STOPPED = "Hands-free is off, so nothing was said."

    /** A card, read out while the owner was on a call - never spoken over one. */
    const val IN_CALL = "You were on a call, so the card was not read out. " +
        "It is in the notification, and on your Home screen."

    /** OFF is immediate - the PC's own contract says so, and so does this. */
    const val OFF_DONE = "Hands-free is off. Jarvis will not read cards out or listen for an answer."

    /** ON landed, and the PC says so. */
    const val ON_DONE = "Hands-free is on. Cards for what you ask Jarvis to do will be read out."

    /**
     * The PC answered 200 but its own state did not come back armed, and it
     * sent no sentence. Nothing is claimed: the switch follows the read-back.
     */
    const val ON_REFUSED = "Your PC did not turn hands-free on."

    /**
     * Shown when the PC has no enrolled voice print: a spoken yes is refused by
     * the PC until one exists (section 191.5 step 5), and this is the one place
     * the owner can be told before he tries.
     */
    const val NO_PRINT = "No voice is trained on your PC yet, so a spoken yes will be refused. " +
        "Train your voice on the PC, or answer cards on screen."

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
     * @param say the card's own notice words, then how to answer it. It is sent
     *   to `/api/voice/say` exactly as it arrives. It is a NOTIFICATION: reading
     *   a card out approves nothing, and the card is still in `/api/pending`.
     * @param expiresInSec how long a spoken ANSWER is open - the PC's 60
     *   seconds, or the card's own countdown when that is shorter - never the
     *   card's own deadline (that is `/api/pending`'s `expires_in`). 0 means the
     *   PC did not say, and the read's `window_sec` is used instead.
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

    /**
     * The PC's own receipt for a text this phone was asked to send - the
     * `phone_result` event (section 191.6).
     *
     * The phone has already posted its own result; this is the PC's sentence,
     * so the app can show the same words the PC will show. [ok] is the PC's
     * record of the phone's answer, never a second claim about the send.
     */
    data class PhoneResult(
        val id: String,
        val ok: Boolean,
        val say: String = "",
        val receipt: String = "",
        val why: String = "",
    )

    /** The reason a `phone_command` this app cannot carry out posts back. */
    const val UNKNOWN_KIND = "This phone does not know how to do that."

    /**
     * What the PC decided about one recorded answer.
     *
     * The frozen contract's fields are `ok`, `heard`, `decision`, `card_state`
     * and `say`; `heard` is the PC's own transcription - the phone shows it,
     * which is how the owner can tell "it misheard me" from "it did not hear me".
     *
     * @param ok false when the PC refused the clip, or when the answer was
     *   unclear and the PC asked once more ([decision] `again`). `ok = false`
     *   is NOT by itself a refusal.
     * @param heard what the PC's speech model heard, or null/blank when it
     *   heard no words.
     * @param decision `approved`, `denied`, `again` (unclear, asked once more),
     *   or `refused`. The spellings in [APPROVE] and [DENY] are accepted too;
     *   anything else is shown as the PC's own word - although with [say] the
     *   PC's sentence is what the owner sees.
     * @param cardState the card's state after the answer (`pending`,
     *   `approved`, `denied`, `expired`, `gone`, `unknown`, `unchanged`), or
     *   null when the PC did not say.
     * @param say the PC's own sentence for the owner: what the phone SPEAKS and
     *   shows, for a decision and for a refusal alike. Read from `say`, then
     *   from the older spellings ([plain]) for a PC that predates the contract.
     */
    data class Answer(
        val ok: Boolean,
        val heard: String? = null,
        val decision: String? = null,
        val cardState: String? = null,
        val say: String? = null,
    )

    /** The closed yes/no vocabulary `GET /api/handsfree` reports (section 191.2). */
    data class Vocabulary(
        val confirm: List<String> = emptyList(),
        val deny: List<String> = emptyList(),
    )

    /** Whether a paired phone can receive a command, and why not (section 191.2). */
    data class Phone(val ready: Boolean = true, val why: String = "")

    /**
     * The state `GET /api/handsfree` answers (section 191.2).
     *
     * @param available false only when the PC says so in words. A 404 from the
     *   route is a separate, stronger "this PC does not have it" and never
     *   reaches here at all ([com.jarvis.client.JarvisRuntime.refreshHandsfree]).
     * @param enabled whether the PC has the mode armed.
     * @param card the newest read-out (`reading`), or a card already waiting
     *   when the PC names one - the fallback for an event this phone missed.
     * @param windowSec the PC's answer window, in seconds; 60 in the contract.
     * @param vocabulary the words the PC will accept, for the Settings row and
     *   the tests that keep the two halves saying the same words.
     * @param voicePrint the enrolled print's label, or "" when none is enrolled
     *   - and with no print the PC refuses a spoken yes ([NO_PRINT]).
     * @param phone whether a paired phone can receive a command.
     * @param why the PC's own sentence about the state, shown as it is.
     */
    data class Read(
        val available: Boolean,
        val enabled: Boolean,
        val card: Card? = null,
        val windowSec: Int = WINDOW_SEC,
        val vocabulary: Vocabulary? = null,
        val voicePrint: String = "",
        val phone: Phone = Phone(),
        val why: String? = null,
    )

    /**
     * What `POST /api/handsfree {"enabled": bool}` answered (section 191.3).
     *
     * There is no 202 and no waiting state: the PC decides its own enable card
     * inside the request, and answers 200 once the mode is on (or already on),
     * 403 when that card was refused, 409 when its settings file cannot be
     * written, 503 when the gate itself cannot run.
     *
     * @param on the PC's own `enabled` after the request, or null when the body
     *   carried none. The caller reads the state back rather than assuming.
     * @param changed true when this request is what changed the setting; false
     *   when it was already in the asked-for state.
     * @param message the PC's own sentence about what happened.
     * @param error the PC's own sentence when it refused.
     */
    data class Enabled(
        val on: Boolean? = null,
        val changed: Boolean? = null,
        val message: String? = null,
        val error: String? = null,
    ) {
        companion object {
            /**
             * The answer, from the body. The status is not needed to read it:
             * a 200 carries `enabled`/`message`, a 403/409/503 carries `error`,
             * and [com.jarvis.client.net.JarvisApi.setHandsfree] has already
             * turned a 401 or a 404 into a failure before this is called.
             */
            fun of(body: JsonObject?): Enabled {
                if (body == null) return Enabled()
                return Enabled(
                    on = bool(body, "enabled", "on"),
                    changed = bool(body, "changed"),
                    message = string(body, "message"),
                    error = string(body, "error"),
                )
            }
        }
    }

    // ----------------------------------------------------------- parsing ----

    /** What an event carried, or null when it is not one of ours. */
    sealed interface Arrival {
        data class CardArrived(val card: Card) : Arrival
        data class CommandArrived(val command: Command) : Arrival
        data class ResultArrived(val result: PhoneResult) : Arrival
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
            EVENT_CARD -> cardOf(obj)?.let { Arrival.CardArrived(it) }
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
            EVENT_RESULT -> {
                val id = string(obj, "id", "command_id", "commandId") ?: return null
                if (id.isBlank()) return null
                Arrival.ResultArrived(
                    PhoneResult(
                        id = id,
                        ok = bool(obj, "ok") ?: false,
                        say = string(obj, "say").orEmpty(),
                        receipt = string(obj, "receipt").orEmpty(),
                        why = string(obj, "why").orEmpty(),
                    ),
                )
            }
            else -> null
        }
    }

    /** `GET /api/handsfree`'s body, or the honest "nothing said" read. */
    fun readOf(body: JsonObject?): Read {
        if (body == null) return Read(available = false, enabled = false)
        // `reading` is the contract's key. The two older spellings stay as a
        // lenient fallback for a PC built before it: a nested `card` object,
        // and a card flattened into the read itself.
        val reading = (body["reading"] as? JsonObject)?.let { cardOf(it) }
        val nested = (body["card"] as? JsonObject)?.let { cardOf(it) }
        val inline = if (reading == null && nested == null) cardOf(body) else null
        val vocabulary = (body["vocabulary"] as? JsonObject)?.let { v ->
            Vocabulary(confirm = strings(v, "confirm"), deny = strings(v, "deny"))
        }
        val phone = body["phone"] as? JsonObject
        return Read(
            available = bool(body, "available") ?: true,
            enabled = bool(body, "enabled", "on") ?: false,
            card = reading ?: nested ?: inline,
            windowSec = (int(body, "window_sec", "windowSec") ?: WINDOW_SEC)
                .coerceIn(1, WINDOW_SEC),
            vocabulary = vocabulary,
            voicePrint = string(body, "voice_print", "voicePrint").orEmpty(),
            phone = Phone(
                ready = phone?.let { bool(it, "ready") } ?: true,
                why = phone?.let { string(it, "why") }.orEmpty(),
            ),
            // Only a key that IS the PC's own sentence about the state. Not
            // [plain]: the contract's `detail` there is the whole Settings
            // paragraph, and drawing it under the switch would be a wall of
            // text on a row that shows one line.
            why = string(body, "why", "note"),
        )
    }

    /**
     * The answer window for one card, in seconds: the card's own
     * `expires_in_sec` when the PC sent one, else [fallback] (the read's
     * `window_sec`, section 191.2), else the contract's [WINDOW_SEC]. Never
     * shorter than a second and never longer than the minute the contract
     * allows - `expires_in_sec` is the ANSWER window, not the card's own
     * deadline, and the phone listens for exactly what the PC offered.
     */
    fun windowSec(card: Card, fallback: Int = WINDOW_SEC): Int {
        val asked = if (card.expiresInSec > 0) card.expiresInSec else fallback
        return asked.coerceIn(1, WINDOW_SEC)
    }

    /** `POST /api/handsfree/answer`'s body, read leniently; null is a refusal with no words. */
    fun answerOf(body: JsonObject?): Answer {
        if (body == null) return Answer(ok = false)
        return Answer(
            // `ok` absent is NOT a refusal: a PC that answers with the contract
            // fields and no `ok` still heard something. Only an explicit false
            // refuses (and `again` arrives as ok:false, which [answerWords]
            // reads as a question rather than a refusal).
            ok = bool(body, "ok") ?: true,
            heard = string(body, "heard"),
            decision = string(body, "decision"),
            cardState = string(body, "card_state", "cardState", "state"),
            say = plain(body),
        )
    }

    // ------------------------------------------------------------- bodies ----

    /** `{"enabled": true|false}` - the contract's one key, and nothing else. */
    fun enabledBody(enabled: Boolean): String = "{\"enabled\":$enabled}"

    /**
     * The answer upload: `{"card_id", "data_b64", "sample_rate"}`.
     *
     * [wav] is the 16 kHz mono clip [com.jarvis.client.handsfree.HandsfreeClip]
     * built, and `sample_rate` is [SAMPLE_RATE] because that is the rate the
     * WAV's own header carries: the contract refuses a clip whose header and
     * `sample_rate` disagree, so there is deliberately no way to pass another
     * number here. It is base64 in JSON because the contract says so, and the
     * clip is the owner's voice: nothing here logs it, and no caller may.
     */
    fun answerBody(cardId: String, wav: ByteArray): String {
        val b64 = com.jarvis.client.handsfree.HandsfreeClip.base64(wav)
        return "{\"card_id\":${quote(cardId)},\"data_b64\":${quote(b64)}," +
            "\"sample_rate\":$SAMPLE_RATE}"
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

    /** The PC's "I did not catch a clear yes or no - ask once more" decision. */
    const val AGAIN = "again"

    /**
     * Decisions that mean "the clip was heard and was not the owner's" - the
     * PC's voice check did not pass, so nothing was approved. A fallback only:
     * a contract-shaped PC sends its own `say` for this.
     */
    val NOT_OUR_VOICE = setOf(
        "not_you", "not-you", "not_owner", "not-owner", "other_voice", "other-voice",
        "wrong_voice", "wrong-voice", "voice_mismatch", "refused_voice", "impostor",
    )

    /**
     * Card states that make [CARD_GONE] the true sentence when the PC sent no
     * `say`: the answer arrived after the card had been decided elsewhere or
     * had timed out.
     */
    val GONE = setOf("expired", "answered", "decided", "gone", "missing")

    /**
     * What the owner is shown after an answer, in plain words - and it is the
     * PC's own sentence whenever the PC sent one, because `say` is the contract
     * field written FOR the owner (section 191.5).
     *
     * The order of the fallback branches is the whole of the rule and is
     * written down here rather than discovered from the tests:
     *
     *  1. the PC's `say`, in its own words ([Answer.say]) - a decision, a
     *     refusal, or the question it asks when an answer was unclear;
     *  2. `decision: "again"` with no `say` - [ASK_AGAIN], and the card is
     *     still waiting, so this is never reported as a refusal;
     *  3. `ok: false` with no `say` - a voice check that did not pass
     *     ([NOT_YOUR_VOICE]), then [CARD_GONE] only when the card's own state
     *     says it is gone, and otherwise [REFUSED];
     *  4. a yes or a no - "Heard: \"...\" - approved/denied";
     *  5. no words at all - [NOTHING_HEARD], with no claim about the card;
     *  6. words but no decision - [NOT_YOUR_VOICE], because something was heard
     *     and nothing was approved, which is exactly what the owner must know.
     */
    fun answerWords(a: Answer): String {
        val sentence = a.say?.trim().orEmpty()
        if (sentence.isNotEmpty()) return sentence
        val decision = a.decision?.trim()?.lowercase().orEmpty()
        if (decision == AGAIN) return ASK_AGAIN
        val heard = a.heard?.trim().orEmpty()
        val stated = a.cardState?.trim()?.lowercase().orEmpty()
        if (!a.ok) {
            if (decision in NOT_OUR_VOICE) return NOT_YOUR_VOICE
            // "The card had expired" may only be said when the card's own
            // state says so. Anything else is the general refusal - never a
            // guess about expiry.
            return if (stated in GONE) CARD_GONE else REFUSED
        }
        if (decision in NOT_OUR_VOICE) return NOT_YOUR_VOICE
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

    private fun cardOf(o: JsonObject): Card? {
        val id = string(o, "card_id", "cardId", "id") ?: return null
        if (id.isBlank()) return null
        return Card(
            cardId = id,
            action = string(o, "action").orEmpty(),
            say = string(o, "say", "text").orEmpty(),
            expiresInSec = int(o, "expires_in_sec", "expiresInSec") ?: 0,
        )
    }

    private fun string(o: JsonObject, vararg names: String): String? = names
        .firstNotNullOfOrNull { n ->
            (o[n] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
                ?.takeIf { it.isNotBlank() }
        }

    private fun bool(o: JsonObject, vararg names: String): Boolean? = names
        .firstNotNullOfOrNull { n -> (o[n] as? JsonPrimitive)?.booleanOrNull }

    private fun int(o: JsonObject, vararg names: String): Int? = names
        .firstNotNullOfOrNull { n -> (o[n] as? JsonPrimitive)?.intOrNull }

    /** A JSON array of strings, or an empty list - never a parse failure. */
    private fun strings(o: JsonObject, name: String): List<String> =
        (o[name] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()

    /**
     * The PC's own sentence, when it wrote one.
     *
     * `say` is the frozen contract's field and comes first. The rest are the
     * names this project already uses for "why", kept so a PC built before the
     * contract still reaches the owner in its own words rather than this app's
     * - and so a refusal whose body is `error` only is not paraphrased.
     */
    private fun plain(o: JsonObject): String? =
        string(o, "say", "why", "refusal", "detail", "reason", "message", "note", "error")
}
