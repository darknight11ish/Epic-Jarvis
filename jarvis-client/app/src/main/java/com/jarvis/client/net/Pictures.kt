package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi
import java.util.Locale

/**
 * "Ask for a picture, and keep it" — the owner's decision of 2026-09-27
 * (*"12 GB card: longer conversations with picture understanding first, and
 * making pictures too (swapped in when asked, since both cannot sit on the
 * card at once)"*), docs/JARVIS-API.md section 129 and backend
 * `jarvis_pictures.py`.
 *
 * Three routes, and NOT ONE OF THEM PUTS A MODEL ON THE PHONE:
 *
 *  - `GET /api/pictures` — the folder, its size, the switch, and every
 *    picture with its own prompt, seed and when it was made;
 *  - `GET /api/pictures/file?id=<id>` — ONE picture, as base64 PNG. The phone
 *    writes it into its own Pictures collection when the owner taps "Save to
 *    my phone": the owner's own device, over Tailscale or Meshnet, which is
 *    not a way out of the PC;
 *  - `POST /api/pictures` — draw one and keep it, from the owner's own words.
 *
 * **NOTHING LEAVES THE OWNER'S OWN MACHINES.** The prompt is typed on the
 * phone and drawn by a program on the PC; no picture is ever uploaded,
 * emailed, attached or searched. There is no code here that could.
 *
 * **MAKING A PICTURE NEEDS NO APPROVAL CARD**, and that is a decision rather
 * than an omission: it is a new file in a folder on the PC, from words the
 * owner typed — the same shape as a timer or a note. Drawing one is still
 * held on a stale link (rule 4), because it does write something.
 *
 * **THE CARD SWAP IS TWO REQUESTS, AND THE FIRST ONE DRAWS NOTHING** (added
 * 2026-10-25). The 12 GB card holds the everyday chat and a draw needs it, so
 * the first `POST` answers `409 needs: "free_card"` with the PC's own sentence
 * and minutes. The owner's tap sends the same body plus `free_card: true` -
 * ONE long request ([CONFIRM_TIMEOUT_S]) that steps the chat aside, draws,
 * releases the drawing model and loads the chat back. EITHER app may confirm
 * it: the owner's decision of 2026-10-24, in their own words *"i would like to
 * be able to approve this from my phone as well"*. A PC that is still on the
 * older rule answers the phone's confirm with `403 pc_only`; that is shown as
 * it is ([PicturesAnswer.OldPc]), never as a bad token and never retried.
 *
 * **THE PHONE CANNOT CHANGE THE SWITCH, THE PROGRAM OR THE FOLDER.** Those
 * are the PC's own business and the backend refuses them from anywhere else
 * (`pc_only`). This file has no field for them at all, so there is nothing to
 * send.
 *
 * **HIDDEN WITH THE PRIVATE THINGS.** The prompts are the owner's own words,
 * so the gallery hides under "Hide memory lists and chat history" — added to
 * that rule rather than beside it. The plate fetches nothing at all while the
 * switch is on and draws one line saying so; [Reply.visible] is what it asks.
 *
 * Pure Kotlin, no Android types, so `PicturesTest` runs it on a plain JVM.
 * The one Android step — writing the PNG into the phone's Pictures collection
 * — lives in the plate, not here.
 */
object Pictures {

    /** The PC path this route lives at, as `check_parity.py` reads it. */
    const val PATH = "/api/pictures"

    /** The one picture's bytes. `check_parity.py` reads this exact string too. */
    const val FILE_PATH = "/api/pictures/file"

    /** The PC's own cap on a prompt; the phone refuses above it rather than sending. */
    const val MAX_PROMPT = 2000

    /**
     * The phone's own name for this feature, in the owner's words ("image
     * mode"): a small heading on the one screen that has it, so the owner can
     * find it by the name they use. NOT a switch and not a second entry - the
     * switch is the PC's (`settings.pictures`, PC-only on purpose) and the
     * gallery is already `brain.projects.pictures` in both apps. Added
     * 2026-10-25 because the owner asked for the image mode to be easy to find
     * on the phone.
     */
    const val IMAGE_MODE = "Image mode"

    /**
     * How long the CONFIRMING request may say NOTHING before the phone gives
     * up: 1,200 s. It is ONE long request - the PC sets the everyday chat
     * aside, draws, makes the drawing program release its models and loads the
     * chat back, and answers only at the end. Measured on this PC: **500.1 s**
     * wall clock for the phone path (draw 382.0 s) and 405.8 s for the
     * desktop's; the PC's own bound is `DRAW_WAIT_S` (600) + `FREE_WAIT_S`
     * (180) + the warm-back, about 14 minutes, so 1,200 s is that bound plus a
     * margin. A READ timeout measures silence, not the whole call, so a draw
     * that is quietly working is never cut off - and it is never re-sent: see
     * [TIMED_OUT_MAKE].
     */
    const val CONFIRM_TIMEOUT_S = 1_200L

    /**
     * The phone's ONE added line when an OLDER PC answers a confirm with `403
     * pc_only` (the rule before the owner's 2026-10-24 decision). The PC's own
     * sentence is shown first, word for word; this says why it refused and
     * what to do. Never a code, never a retry.
     */
    const val OLD_PC_WORDS =
        "This PC's Jarvis is older than this phone and needs the newer Jarvis before the " +
            "phone can set the chat aside. Update Jarvis on the PC by running " +
            "apply-patches.ps1 there, then ask again."

    /**
     * The screens' own words, both apps, word for word. Every OTHER sentence
     * on this screen comes from the PC — the folder, the sizes, the two
     * programs to install and the reason a drawing failed are all its words.
     */
    val WORDS: Map<String, String> = mapOf(
        "title" to "Pictures",
        "under" to "Ask for a picture in your own words. Jarvis draws it on this PC and keeps it here.",
        "ask_label" to "What should the picture show?",
        "make" to "Make a picture",
        "another" to "Make another",
        "save_phone" to "Save to my phone",
        "saved_phone" to "Saved to your phone.",
        "empty" to "No pictures yet. Ask for one and it will appear here.",
        "hidden" to "Hidden while memory lists and chat history are hidden.",
        "hidden_short" to "Turn off Hide memory lists to see your pictures.",
        "prompt_label" to "You asked for",
        "made_label" to "Made",
        "seed_label" to "Seed",
        "no_record" to "The note beside this picture is gone, so what made it is not known.",
        "not_kept" to "A picture is never sent anywhere by Jarvis. Save to my phone copies it to your own phone.",
        "missing" to "Your PC's Jarvis does not have pictures yet - run apply-patches.ps1 on the PC.",
        "unreadable" to "Jarvis answered, but not in a way this app can read. Update the backend by running apply-patches.ps1.",
        "no_words" to "Say what the picture should show, and Jarvis will draw it.",
        "show" to "Show",
        "show_title" to "Lift Hide memory lists for this screen",
        "still_hidden" to "Still hidden - turn off App lock, or turn off Hide memory lists, to see your pictures.",
        // The PC's 409 question and the owner's two answers to it (2026-10-25).
        // "(about N minutes)" is added from the PC's own estimate, never guessed.
        "set_aside" to "Set the chat aside and draw",
        "set_aside_no" to "Not now",
        "set_aside_stopped" to "Nothing was drawn - your everyday chat stays where it is.",
        // The one long confirm request timed out on THIS phone. Never a claim
        // about the PC's state: it may well be drawing.
        "timed_out" to ("This phone stopped waiting for your PC before the answer came. " +
            "Your PC may still be drawing the picture and putting your chat back, so it " +
            "was not sent again - if it finished, the picture will appear below."),
    )

    /** One picture as the PC describes it. Nothing here is worked out on the phone. */
    data class Shot(
        val name: String,
        val id: String,
        val prompt: String,
        val seed: Long?,
        val model: String,
        val madeAtWords: String,
        val bytes: Long,
        val hasRecord: Boolean,
    ) {
        /** What a screen reader says for one picture: the prompt, then when. */
        fun said(): String = listOf(
            prompt.ifBlank { WORDS.getValue("no_record") },
            madeAtWords,
            seed?.let { "${WORDS.getValue("seed_label")} $it" } ?: "",
        ).filter { it.isNotBlank() }.joinToString(", ")
    }

    /** The answer to `GET /api/pictures`, read once and drawn. */
    data class Reply(
        val ok: Boolean,
        val enabled: Boolean,
        /** The whole gallery is hidden right now: no prompt is in this answer. */
        val hidden: Boolean,
        val hiddenWords: String,
        val folder: String,
        val count: Int,
        val sizeWords: String,
        /** The PC's own one plain sentence: nothing set up, or the switch is off. */
        val words: String,
        val keep: String,
        /** The two drawing programs this PC supports, with what to install. */
        val programs: List<Program>,
        val shots: List<Shot>,
        val available: Boolean,
    ) {
        /** True when there is something to draw with AND the switch is on. */
        val canAsk: Boolean get() = available && enabled && !hidden

        /** While the lists are hidden, the plate draws one line and fetches nothing. */
        val visible: Boolean get() = available && !hidden

        companion object {
            /** A PC that has no such route: draw nothing at all. */
            val MISSING = Reply(
                ok = false, enabled = false, hidden = false, hiddenWords = "",
                folder = "", count = 0, sizeWords = "", words = "", keep = "",
                programs = emptyList(), shots = emptyList(), available = false,
            )
            val HIDDEN = Reply(
                ok = true, enabled = false, hidden = true, hiddenWords = "",
                folder = "", count = 0, sizeWords = "", words = "", keep = "",
                programs = emptyList(), shots = emptyList(), available = true,
            )
        }
    }

    /** One drawing program the PC can use: its id, its name and what to install. */
    data class Program(val id: String, val plain: String, val install: String)

    /** The answer to `GET /api/pictures/file`: the PNG's bytes, decoded. */
    @OptIn(ExperimentalEncodingApi::class)
    fun pngBytes(body: JsonObject?): ByteArray? {
        val text = body?.get("png")?.jsonPrimitive?.contentOrNull ?: return null
        if (text.isBlank()) return null
        return runCatching { Base64.decode(text) }.getOrNull()
    }

    /** The id the PC sent back for a picture it just drew, or null. */
    fun madeId(body: JsonObject?): String? =
        body?.get("id")?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }

    /**
     * The PC's own words for a picture it just drew, word for word and never
     * rebuilt here: "Drawn in 41.2 seconds and saved as
     * 2026-10-11-140509-a-red-panda.png." and, when the chat had to step
     * aside, the swap's own sentence after it - "Your everyday chat stepped
     * aside for 2.5 seconds and is back on the card after another 9.0
     * seconds." Both are the PC's; joining them with one space keeps every
     * word of both, which is the whole rule on this screen.
     */
    fun madeWords(body: JsonObject?): String {
        val drawn = body?.get("words")?.jsonPrimitive?.contentOrNull.orEmpty()
        return listOf(drawn, cardWords(body)).filter { it.isNotBlank() }.joinToString(" ")
    }

    /** One field of the swap's own record (`card`), or null when it is absent. */
    private fun cardField(body: JsonObject?, key: String): JsonPrimitive? = runCatching {
        body?.get("card")?.jsonObject?.get(key)?.jsonPrimitive
    }.getOrNull()

    /** The swap's sentence ("Your everyday chat stepped aside ..."), or "". */
    fun cardWords(body: JsonObject?): String = cardField(body, "words")?.contentOrNull.orEmpty()

    /** How long the everyday chat was set aside, as the PC measured it, or null. */
    fun cardAwaySeconds(body: JsonObject?): Double? =
        cardField(body, "chat_away_seconds")?.doubleOrNull

    /** How long the everyday chat took to come back, as the PC measured it, or null. */
    fun cardBackSeconds(body: JsonObject?): Double? =
        cardField(body, "chat_back_seconds")?.doubleOrNull

    /**
     * Reads ONE answer to `POST /api/pictures`, whole. Every sentence here is
     * the PC's own, taken from the answer as sent; nothing is rebuilt.
     */
    fun readMake(status: Int, body: JsonObject?): PicturesAnswer {
        if (status in 200..299) {
            return PicturesAnswer.Made(body ?: JsonObject(emptyMap()))
        }
        if (status == 404 || status == 501) return PicturesAnswer.Missing
        val said = refusal(body)
        val needs = body?.get("needs")?.jsonPrimitive?.contentOrNull
        return when {
            status == 409 && needs == "free_card" ->
                PicturesAnswer.NeedsConfirm(said, minutesOf(body))
            status == 409 && needs == "drawing" -> PicturesAnswer.StillDrawing(said)
            status == 403 && isPcOnly(body) -> PicturesAnswer.OldPc(said)
            else -> PicturesAnswer.Refused(said)
        }
    }

    /**
     * True only for the PC saying "on this PC only" - here, an older PC
     * refusing a phone's confirm. A cross-origin 403 says no such thing.
     */
    fun isPcOnly(body: JsonObject?): Boolean =
        body?.get("pc_only")?.jsonPrimitive?.booleanOrNull == true

    /** The PC's own minutes from a 409 `estimate`, or null when it sent none. */
    fun minutesOf(body: JsonObject?): Int? = runCatching {
        body?.get("estimate")?.jsonObject?.get("minutes")?.jsonPrimitive?.intOrNull
    }.getOrNull()?.takeIf { it >= 1 }

    /**
     * The confirm button's label: "Set the chat aside and draw (about 6
     * minutes)", from the PC's estimate. With no estimate it is the plain
     * label - never "about 0".
     */
    fun confirmLabel(minutes: Int?): String {
        val base = WORDS.getValue("set_aside")
        if (minutes == null || minutes < 1) return base
        val unit = if (minutes == 1) "minute" else "minutes"
        return "$base (about $minutes $unit)"
    }

    /**
     * The waiting sentence while the confirm runs, in the desktop's own words:
     * "Drawing - this takes about 6 minutes. Your everyday chat will come back
     * when it is done." With no estimate, "a few minutes".
     */
    fun confirmingWords(minutes: Int?): String {
        val stretch = if (minutes != null && minutes >= 1) {
            val unit = if (minutes == 1) "minute" else "minutes"
            "about $minutes $unit"
        } else {
            "a few minutes"
        }
        return "Drawing - this takes $stretch. Your everyday chat will come back when it is done."
    }

    /** True when a failed request was the phone giving up waiting, not the PC answering. */
    fun gaveUpWaiting(network: String): Boolean = network == "read_timeout"

    /**
     * What the plate shows when the ONE long confirm request timed out. It
     * offers no confirm again ([PicturesMake.needsConfirm] is false): sending
     * the same body twice would answer `409 needs: "drawing"` while the first
     * draw carries on, which is exactly the confusion this avoids.
     */
    val TIMED_OUT_MAKE = PicturesMake(
        ok = false,
        said = WORDS.getValue("timed_out"),
        id = null,
        timedOut = true,
    )

    /**
     * The body of `POST /api/pictures`. The prompt is trimmed, and a prompt of
     * spaces is refused here rather than sent: the PC would refuse it too, and
     * a round trip to be told "say what the picture should show" is one more
     * thing between the owner and their picture.
     *
     * [freeCard] is the owner's OWN confirmation of the PC's 409 question
     * (`readMake`), and it is false on the first request, always. The only
     * caller that passes true is the confirm button's own handler
     * ([confirmBody]); nothing sends it on the owner's behalf.
     */
    fun makeBody(prompt: String, freeCard: Boolean = false): String? {
        val text = prompt.trim()
        if (text.isEmpty() || text.length > MAX_PROMPT) return null
        return buildJsonObject {
            put("prompt", text)
            if (freeCard) put("free_card", true)
        }.toString()
    }

    /**
     * The SAME words plus `free_card: true` - the one second request, sent
     * only after the owner taps the PC's 409 question. The PC then sets the
     * everyday chat aside, draws, releases the drawing model and loads the chat
     * back; that is one long request ([CONFIRM_TIMEOUT_S]).
     */
    fun confirmBody(prompt: String): String? = makeBody(prompt, freeCard = true)

    /**
     * The path for one picture's bytes, or null when the id is not one the PC
     * could have made. An id with a separator or a `..` in it is refused here
     * so the phone can never ask the PC for another path.
     */
    fun filePath(id: String): String? {
        val text = id.trim()
        if (text.length < 20 || text.length > 96) return null
        if (!text[0].isDigit()) return null
        if (text.contains("..")) return null
        if (!text.all { it.isLetterOrDigit() || it == '-' || it == '_' || it == '.' }) return null
        return "$FILE_PATH?id=$text"
    }

    /** One picture's name as a file name on this phone: only safe characters. */
    fun fileName(shot: Shot): String {
        val base = shot.id.ifBlank { shot.name }.removeSuffix(".png")
        val safe = base.map { if (it.isLetterOrDigit() || it == '-' || it == '_') it else '-' }
            .joinToString("")
            .trim('-')
        return (safe.ifBlank { "jarvis-picture" }) + ".png"
    }

    /**
     * `GET /api/pictures` read into a [Reply]. A 404/501 is an older PC and
     * draws nothing ([Reply.MISSING]); anything else with a body is read as
     * sent, so a plain sentence from the PC is shown word for word.
     */
    fun readReply(status: Int, body: JsonObject?): Reply {
        if (status == 404 || status == 501) return Reply.MISSING
        if (body == null) return Reply.MISSING
        val hidden = body["hidden"]?.jsonPrimitive?.booleanOrNull == true
        val words = body["words"]?.jsonPrimitive?.contentOrNull.orEmpty()
        if (hidden) {
            return Reply(
                ok = true, enabled = false, hidden = true,
                hiddenWords = body["hidden_words"]?.jsonPrimitive?.contentOrNull
                    ?.takeIf { it.isNotBlank() } ?: WORDS.getValue("hidden"),
                folder = "", count = 0, sizeWords = "", words = "",
                keep = "", programs = emptyList(), shots = emptyList(),
                available = true,
            )
        }
        // A body that SAYS the read itself failed is not a missing feature. The
        // PC's own handler answers a failed gallery read with 503
        // `{"ok":false,"available":false,"error":"The pictures could not be
        // read (…)."}` and no `pictures` key (backend/jarvis_pictures.py). That
        // used to fall through to `Reply.MISSING`, so the plate told the owner
        // to run apply-patches.ps1 for a folder/permission fault - advice that
        // cannot fix it, and it threw the PC's sentence away (the 2026-10-24
        // round-2 audit, M7). Carry the sentence on the plate's ordinary
        // "words" line and keep the feature marked available.
        val serverWords = body["error"]?.jsonPrimitive?.contentOrNull.orEmpty()
        val readFailed = serverWords.isNotBlank() && body["pictures"] == null &&
            (body["ok"]?.jsonPrimitive?.booleanOrNull == false ||
                body["available"]?.jsonPrimitive?.booleanOrNull == false)
        if (readFailed) {
            return Reply(
                ok = false, enabled = false, hidden = false,
                hiddenWords = "", folder = "", count = 0, sizeWords = "",
                words = serverWords, keep = "", programs = emptyList(),
                shots = emptyList(), available = true,
            )
        }
        val shots = (body["pictures"]?.jsonArray ?: return Reply.MISSING).mapNotNull { element ->
            val one = runCatching { element.jsonObject }.getOrNull() ?: return@mapNotNull null
            val id = one["id"]?.jsonPrimitive?.contentOrNull.orEmpty()
            if (id.isBlank()) return@mapNotNull null
            Shot(
                name = one["name"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                id = id,
                prompt = one["prompt"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                seed = one["seed"]?.jsonPrimitive?.contentOrNull?.toLongOrNull(),
                model = one["model"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                madeAtWords = one["made_at_words"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                bytes = one["bytes"]?.jsonPrimitive?.contentOrNull?.toLongOrNull() ?: 0L,
                hasRecord = one["record"]?.jsonPrimitive?.booleanOrNull == true,
            )
        }
        val programs = (body["runtimes"]?.jsonArray ?: emptyList()).mapNotNull { element ->
            val one = runCatching { element.jsonObject }.getOrNull() ?: return@mapNotNull null
            val id = one["id"]?.jsonPrimitive?.contentOrNull.orEmpty()
            if (id.isBlank()) return@mapNotNull null
            Program(
                id = id,
                plain = one["plain"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                install = one["install"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            )
        }
        return Reply(
            ok = body["ok"]?.jsonPrimitive?.booleanOrNull != false,
            enabled = body["enabled"]?.jsonPrimitive?.booleanOrNull == true,
            hidden = false,
            hiddenWords = "",
            folder = body["folder"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            count = body["count"]?.jsonPrimitive?.intOrNull ?: shots.size,
            sizeWords = body["size_words"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            words = words,
            keep = body["keep"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            programs = programs,
            shots = shots,
            available = body["available"]?.jsonPrimitive?.booleanOrNull != false,
        )
    }

    /**
     * The PC's own sentence from a refusal, as sent. Never invented here: a
     * refusal with no sentence at all falls back to the shared "unreadable"
     * line rather than a blank.
     */
    fun refusal(body: JsonObject?): String =
        body?.get("error")?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotBlank() }
            ?: WORDS.getValue("unreadable")

    /**
     * The size a person reads. The PC sends `size_words` and the phone shows
     * it; this is only for a picture's own byte count, and it says the same
     * things in the same words.
     */
    fun sizedWords(bytes: Long): String = when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024L * 1024 -> "${bytes / 1024} KB"
        bytes < 1024L * 1024 * 1024 ->
            String.format(Locale.US, "%.1f MB", bytes / 1024.0 / 1024.0)
        else -> String.format(Locale.US, "%.2f GB", bytes / 1024.0 / 1024.0 / 1024.0)
    }
}

/** The type `JarvisApi.pictures` and `JarvisApi.picturesFile` hand back. */
typealias PicturesReply = Pictures.Reply

/**
 * What the PC said to one draw, read before any screen decides anything
 * (added 2026-10-25, and rewritten for the FINAL contract the same day).
 * Five answers, and they are not the same thing:
 *
 *  - [Made] - drawn and kept.
 *  - [NeedsConfirm] - **409 `needs: "free_card"`**: NOTHING WAS DRAWN. The
 *    12 GB card holds the everyday chat, so the PC is asking whether it may
 *    set the chat aside, draw, and load the chat back. The answer carries
 *    the PC's own sentence and its measured minutes; only the owner's tap
 *    sends the SAME body plus `free_card: true` ([Pictures.confirmBody]).
 *  - [StillDrawing] - **409 `needs: "drawing"`**: a draw is already
 *    running. Its one sentence is shown as sent and NOTHING is retried;
 *    the first draw and its warm-back carry on.
 *  - [OldPc] - **403 `pc_only`**: a PC still running the rule before the
 *    owner's 2026-10-24 decision, which refused a phone's confirm. Show its
 *    sentence, then [Pictures.OLD_PC_WORDS]; never a bad pairing token and
 *    never a retry.
 *  - [Refused] - any other answered refusal, in the PC's own sentence.
 *  - [Missing] - 404/501: this PC's Jarvis has no pictures route at all.
 *
 * A PLAIN "no" is [Refused]: nothing set up, the drawing program not running
 * or the switch off keep their own status and sentence. A 403 that is not
 * `pc_only` (a cross-origin refusal) is not [OldPc] either - the caller keeps
 * its existing "bad token" reading for that one.
 */
sealed interface PicturesAnswer {
    /** Drawn and kept. Its fields are read by [Pictures.madeWords] and [Pictures.madeId]. */
    data class Made(val body: JsonObject) : PicturesAnswer

    /** The PC's 409 question: show [said] and the minutes, wait for the owner's tap. */
    data class NeedsConfirm(val said: String, val minutes: Int?) : PicturesAnswer

    /** A draw is already running: [said] is the PC's own "wait for that one". */
    data class StillDrawing(val said: String) : PicturesAnswer

    /** An older PC refused a phone's confirm: [said], then [Pictures.OLD_PC_WORDS]. */
    data class OldPc(val said: String) : PicturesAnswer

    /** Any other answered refusal, in the PC's own sentence. */
    data class Refused(val said: String) : PicturesAnswer

    /** No pictures route on this PC at all. */
    data object Missing : PicturesAnswer
}

/**
 * What drawing one picture came back as, for the plate: whether it worked,
 * the sentence to show (the PC's own words, never rebuilt here) and the new
 * picture's id so the gallery can be read back.
 *
 * The four outcomes are separate flags rather than one nullable field, so a
 * screen cannot confuse "the PC asked a question" with "an older PC refused"
 * or "this phone gave up waiting":
 *
 *  - [needsConfirm] - the 409 question, waiting for the owner's tap. It is the
 *    ONLY thing that offers the button which sends `free_card: true`.
 *  - [oldPc] - a 403 `pc_only` from a PC still on the old rule. Show [said],
 *    then [Pictures.OLD_PC_WORDS]; no retry.
 *  - [timedOut] - the confirm's read timed out. The PC may still be drawing;
 *    nothing is re-sent, and no confirm is offered again.
 *  - all false with `ok = false` - an ordinary refusal, in [said] as sent.
 */
data class PicturesMake(
    val ok: Boolean,
    val said: String,
    val id: String?,
    /** 409 `needs: "free_card"`: the owner has to tap the confirm button. */
    val needsConfirm: Boolean = false,
    /** The PC's own estimate of how long the chat stays away, when it sent one. */
    val minutes: Int? = null,
    /** 403 `pc_only`: an older PC; [said] plus [Pictures.OLD_PC_WORDS]. */
    val oldPc: Boolean = false,
    /** The confirm's read timed out on this phone: never re-sent. */
    val timedOut: Boolean = false,
)
