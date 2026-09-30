package com.jarvis.client.net

import java.net.URLEncoder
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull

/**
 * "Jarvis filled in a web form - check it before it is sent" (the owner's
 * decision of 2026-09-30, docs/FORM-REVIEW-DESIGN.md; the PC's
 * backend/jarvis_form_review.py).
 *
 * The card that asks to submit a form (gate action `browser_form_submit`) may
 * carry `detail.picture`: an id. `GET /api/form-review/picture?id=<id>` then
 * answers `{"ok": true, "jpeg": "<base64>", "width", "height"}`, or 404
 * `{"ok": false}` once the card is decided or has expired.
 *
 * What this phone does with it:
 *  - asks for it ONLY while the card is on screen, the app is in front and
 *    unlocked (ui/approval/FormPicture.kt);
 *  - holds it as a bitmap in memory for that card only: never saved, never in
 *    a notification, the approval widget or the home-screen widget (those
 *    stay title-only);
 *  - blocks screenshots of Jarvis while it shows ([shown],
 *    SecurityRules.blockScreenCapture);
 *  - shows it exactly as the PC sent it - it is NOT cleaned, because it goes
 *    only to the owner's own devices and never to a model.
 *
 * The picture changes nothing about deciding: a risky card still needs the
 * screen lock or fingerprint, Approve is never automatic, and a card whose
 * picture could not be loaded says so in words and is decided as before, by
 * reading the text.
 *
 * Pure Kotlin (no Android), so FormReviewTest runs it on the JVM.
 */
object FormReview {
    const val PICTURE_PATH = "/api/form-review/picture"

    /** Most characters of an id this phone will use (the PC's are short random strings). */
    private const val ID_MOST = 128

    /** Screen reader text for the picture. */
    const val PICTURE_DESCRIPTION = "The form as Jarvis filled it in"

    const val PICTURE_HEADING = "The form as Jarvis filled it in"
    const val TAP_TO_ENLARGE = "Tap the picture to see it bigger."
    const val LOADING = "Loading the picture of the form..."
    const val CLOSE = "Close"

    /** The fetch failed (no link, an error): the wording the owner asked for. */
    const val COULD_NOT_LOAD =
        "Jarvis could not load the picture of the form. Read the details below before you approve."

    /**
     * "Hide memory lists and chat history" is on (the owner, 2026-09-30): the
     * picture shows the owner's name, phone and email, as private as those
     * lists, so it is not fetched or drawn until the setting is off.
     */
    const val HIDDEN_BY_SETTING =
        "The picture shows your name, phone and email, so it is hidden while " +
            "\"Hide memory lists and chat history\" is on. " +
            "Turn that off in Security to see it, or read the details below before you approve."

    /** The PC no longer has it (card decided or timed out, or the picture was dropped). */
    const val GONE =
        "The picture of the form is gone. The card may have timed out. Read the details below before you approve."

    /**
     * The picture id in a row's raw `detail`: an object, or a JSON string of
     * an object (the gate's own tests use both shapes). Null when there is
     * none or it is not a plain id - and then the card is exactly as before.
     */
    fun pictureIdOf(rawDetail: JsonElement?): String? {
        val obj: JsonObject = when (rawDetail) {
            is JsonObject -> rawDetail
            is JsonPrimitive -> {
                if (!rawDetail.isString) return null
                // Text the gate cut short no longer parses: read the id from it
                // the way the desktop does, so both apps still find the picture.
                runCatching { JarvisJson.parseToJsonElement(rawDetail.content) as? JsonObject }.getOrNull()
                    ?: return CUT_SHORT_ID.find(rawDetail.content)?.groupValues?.get(1)?.let { cleanId(it) }
            }
            else -> return null
        }
        return cleanId(idOf(obj["picture"]))
    }

    private val CUT_SHORT_ID = Regex("\"picture\"\\s*:\\s*\"([A-Za-z0-9_-]{1,64})\"")

    private fun cleanId(raw: String?): String? {
        val t = raw?.trim() ?: return null
        if (t.isEmpty() || t.length > ID_MOST) return null
        if (t.any { it.code < 33 || it.code == 127 }) return null
        return t
    }

    /** `/api/form-review/picture?id=<id>`, the id URL-encoded; null for an id that is not usable. */
    fun pathFor(id: String): String? {
        val clean = cleanId(id) ?: return null
        return "$PICTURE_PATH?id=" + URLEncoder.encode(clean, "UTF-8")
    }

    sealed interface Answer {
        /** The picture: base64 JPEG and its size in page pixels. */
        data class Picture(val jpeg: String, val width: Int, val height: Int) : Answer

        /** The PC no longer has it (a 404). */
        data object Gone : Answer

        /** Anything else went wrong; [words] is the sentence for the card. */
        data class Failed(val words: String) : Answer
    }

    /** The PC's answer (status and body as sent) as an [Answer]. Never throws. */
    fun answer(code: Int, body: JsonObject?): Answer {
        if (code == 404) return Answer.Gone
        if (code !in 200..299) return Answer.Failed(COULD_NOT_LOAD)
        val ok = (body?.get("ok") as? JsonPrimitive)?.content
        val jpeg = (body?.get("jpeg") as? JsonPrimitive)?.takeIf { it.isString }?.content
        if (ok == "false" || jpeg.isNullOrBlank()) return Answer.Failed(COULD_NOT_LOAD)
        val w = (body?.get("width") as? JsonPrimitive)?.intOrNull ?: 0
        val h = (body?.get("height") as? JsonPrimitive)?.intOrNull ?: 0
        return Answer.Picture(jpeg, w, h)
    }

    /** The JPEG's bytes, or null when the text is not valid base64 (never throws). */
    fun decodeBytes(base64: String): ByteArray? =
        runCatching { java.util.Base64.getDecoder().decode(base64.trim()) }
            .getOrNull()
            ?.takeIf { it.isNotEmpty() }

    /**
     * How many cards are showing a form picture right now. MainActivity blocks
     * screenshots of Jarvis while this is above zero. Set by the card before
     * it asks for the picture, and back down the moment the card goes.
     */
    private val shownCount = MutableStateFlow(0)
    val shown: StateFlow<Int> get() = shownCount

    fun enterView() {
        shownCount.value = shownCount.value + 1
    }

    fun leaveView() {
        shownCount.value = (shownCount.value - 1).coerceAtLeast(0)
    }
}
