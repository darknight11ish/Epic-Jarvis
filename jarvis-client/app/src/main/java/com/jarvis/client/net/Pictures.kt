package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
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
     * The ONE line the phone adds under the PC's own sentence when a draw means
     * setting this PC's everyday chat aside first (added 2026-10-25). It is the
     * PHONE'S alone: the PC can do that step and shows its own button, while a
     * phone cannot - the PC answers it with `403 pc_only` - so this line says
     * where the step belongs, and that the picture still turns up here after.
     */
    const val NEEDS_PC_WORDS =
        "This step has to be done on the PC - the phone cannot set the everyday chat " +
            "aside. Draw it there and it will appear here."

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
     * The PC's own sentence for a picture it just drew - "Drawn in 41.2
     * seconds and saved as 2026-10-11-140509-a-red-panda.png." Shown word for
     * word; nothing on the phone rebuilds it.
     */
    fun madeWords(body: JsonObject?): String =
        body?.get("words")?.jsonPrimitive?.contentOrNull.orEmpty()

    /**
     * A draw the PC will not start from this phone (added 2026-10-25): the
     * 12 GB card holds the everyday chat, so one picture means the chat is set
     * aside, the picture drawn, and the chat loaded back. That is this PC's own
     * act - `backend/jarvis_pictures.py`'s `make_answer` answers a phone with
     * **403** `pc_only`, and answers the PC itself with **409**
     * `needs: "free_card"` until it sends `free_card: true` again.
     *
     * Both answers carry the PC's own plain sentence, which is shown word for
     * word; [minutes] is its own estimate when it sent one, else null. **The
     * phone never sends `free_card`** - [makeBody] has no field for it, and this
     * is the answer proving why: setting the chat aside is not the phone's to do.
     *
     * A PLAIN "no" is NOT this answer: nothing set up, the drawing program not
     * running or the switch off keep their own status and sentence, and a 403
     * that is not `pc_only` (a cross-origin refusal) is not this either.
     */
    data class FreeCard(
        /** The PC's own sentence, word for word. */
        val said: String,
        /** The PC's own estimate of how long the chat stays away, or null. */
        val minutes: Int?,
    )

    /**
     * Reads the PC's "the card has to be freed first" answer, or null when this
     * is an ordinary refusal and the caller should show that instead.
     */
    fun freeCard(status: Int, body: JsonObject?): FreeCard? {
        if (body == null) return null
        if (status != 409 && status != 403) return null
        if (body["needs"]?.jsonPrimitive?.contentOrNull != "free_card") return null
        // 403 is this answer only when the PC says `pc_only: true`; a
        // cross-origin refusal wears the same status and is a different thing.
        if (status == 403 && body["pc_only"]?.jsonPrimitive?.booleanOrNull != true) return null
        val minutes = runCatching {
            body["estimate"]?.jsonObject?.get("minutes")?.jsonPrimitive?.intOrNull
        }.getOrNull()
        return FreeCard(refusal(body), minutes)
    }

    /**
     * The body of `POST /api/pictures`. The prompt is trimmed, and a prompt of
     * spaces is refused here rather than sent: the PC would refuse it too, and
     * a round trip to be told "say what the picture should show" is one more
     * thing between the owner and their picture.
     */
    fun makeBody(prompt: String): String? {
        val text = prompt.trim()
        if (text.isEmpty() || text.length > MAX_PROMPT) return null
        return buildJsonObject { put("prompt", text) }.toString()
    }

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
 * The whole answer to `POST /api/pictures`, read before a screen decides what
 * to show. Added 2026-10-25 with the card handshake: a draw that needs this
 * PC's everyday chat set aside is not a failure of the phone's, and it is not
 * the same thing as a refusal - the PC said, in its own words, what has to
 * happen and where.
 */
sealed interface PicturesAnswer {

    /** Drawn and kept. Its fields are read by [Pictures.madeWords] and [Pictures.madeId]. */
    data class Made(val body: JsonObject) : PicturesAnswer

    /**
     * Not drawn from here: this PC's everyday chat holds the card and has to be
     * set aside, which only the PC itself can start.
     */
    data class NeedsPc(val said: String, val minutes: Int?) : PicturesAnswer
}

/**
 * What drawing one picture came back as, for the plate: whether it worked,
 * the sentence to show (the PC's own when it sent one) and the new picture's
 * id so the gallery can be read back.
 *
 * [needsPc] is the 2026-10-25 case: the PC answered "the everyday chat has to
 * be set aside first, and only from the PC". The plate then shows [said] word
 * for word plus [Pictures.NEEDS_PC_WORDS], keeps the owner's typed prompt, and
 * offers nothing that could carry that step out from the phone.
 */
data class PicturesMake(
    val ok: Boolean,
    val said: String,
    val id: String?,
    /** True when the draw has to be started on the PC, not from this phone. */
    val needsPc: Boolean = false,
    /** The PC's own estimate of how long the chat stays away, when it sent one. */
    val minutes: Int? = null,
)
