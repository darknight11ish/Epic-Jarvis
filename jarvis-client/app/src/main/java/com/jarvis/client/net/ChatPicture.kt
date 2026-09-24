package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import java.util.Base64

/**
 * A photo sent in chat, and the numbers that keep it inside what the PC accepts.
 *
 * ONLY WHILE PICTURES WORKS. The attach button is offered only while the PC
 * says its second graphics card's Pictures feature is `available`
 * ([SecondCard.visionAvailable]), and the send checks again first. Without it
 * the everyday model gets the picture and cannot see it.
 *
 * PRIVATE. A photo can show anything. It goes to the owner's PC and nowhere
 * else: the PC's router keeps any message with a picture on the local model
 * (`backend/rebuilt/jarvis_router.py`, "A PICTURE NEVER LEAVES"), and this app
 * sends it nowhere but `/api/chat` on that PC. It is decoded and re-encoded in
 * memory - never written to disk by this app - and dropped once sent. It is
 * never kept in the conversation either: only the words are
 * ([ChatHistory.commit]), which is what the desktop does too. Its bytes are
 * never logged. Re-encoding also drops the photo's metadata (where and when
 * it was taken), because only the pixels are copied.
 *
 * THE SHAPE is exactly what the desktop sends (`jarvis-desktop/src/main.js`,
 * the `content` array in `send`; `src-tauri/src/commands.rs` `stream_chat`):
 * the picture rides INSIDE the newest user message, as an OpenAI-style
 * `image_url` part holding a `data:image/jpeg;base64,` URI, after a `text`
 * part, with `has_image: true` beside `messages`. The PC reads the picture from
 * the message (`backend/jarvis_agent.py` `newest_turn_has_image`) and routes
 * on `has_image` (`jarvis_router.choose(has_image=...)`). Checked against the
 * backend's own functions by `backend/test_phone_second_card_contract.py`, whose
 * cases `ChatPictureContractTest` builds with this encoder.
 *
 * HOW BIG. The PC refuses any request body over 4 MiB (`MAX_BODY` in
 * jarvis_hud.py, seen in `backend/token-store.patch`'s context lines). The
 * desktop caps its screenshots at 1920 pixels wide and JPEG quality 82
 * (`commands.rs`, `MAX_CAPTURE_WIDTH`, `JPEG_QUALITY`). The phone uses the same
 * two numbers, on the LONG edge so a tall photo is capped too, and then holds
 * the JPEG to [MAX_JPEG_BYTES] - 2 MB once base64 has grown it by a third,
 * leaving room for the conversation that goes with it ([ChatHistory], at most
 * 18,000 characters).
 */
object ChatPicture {

    /** Longest side, in pixels. The desktop's `MAX_CAPTURE_WIDTH`. */
    const val MAX_LONG_EDGE = 1920

    /** The desktop's `JPEG_QUALITY`. */
    const val JPEG_QUALITY = 82

    /** Tried in turn when the first JPEG is still too big. */
    val FALLBACK_QUALITIES = listOf(70, 55)

    /** Then the picture is made smaller, down to this long edge, and tried again. */
    const val SMALLEST_LONG_EDGE = 1024

    /** The JPEG's own size limit, before base64. */
    const val MAX_JPEG_BYTES = 1_500_000

    /** The PC's `MAX_BODY`: the whole `/api/chat` request, in bytes. */
    const val BACKEND_MAX_BODY = 4 * 1024 * 1024

    /** A picture ready to send, held in memory only. */
    class Ready(
        /** `data:image/jpeg;base64,...` */
        val dataUri: String,
        val width: Int,
        val height: Int,
        val jpegBytes: Int,
    ) {
        /** Never the bytes: a data class's toString would print the whole picture. */
        override fun toString(): String = "ChatPicture.Ready(${width}x$height, $jpegBytes bytes)"
    }

    /**
     * A share from another app that chat can take as a picture: one image,
     * any `image/...` type (Android's Share sheet, `ACTION_SEND`). It is
     * decoded and shrunk exactly as a picked photo is, so the size limits
     * below hold for both.
     */
    fun isSharedImage(mimeType: String?): Boolean =
        mimeType?.trim()?.lowercase()?.startsWith("image/") == true

    /** Why Pictures is not working, in the PC's words where it has some. */
    fun notWorkingWhy(read: SecondCard.Read): String? =
        (read as? SecondCard.Read.Loaded)?.status?.feature(SecondCard.VISION)?.why
            ?: SecondCard.readLine(read)

    /**
     * Why a picture shared from another app is NOT attached, or null when it
     * is. The Photo button's own rule ([SecondCard.visionAvailable], read
     * fresh): a share is attached only when that button would be offered, and
     * is never dropped without a word. Sending checks again, as it does for a
     * picked photo.
     */
    fun sharedRefusal(read: SecondCard.Read): String? {
        if (SecondCard.visionAvailable(read)) return null
        return "The shared picture was not attached: Jarvis takes pictures only while Pictures " +
            "on the second graphics card is working" +
            (notWorkingWhy(read)?.let { " ($it)" } ?: "") + ". Nothing was sent."
    }

    /** The line under the composer while a picture is attached. */
    fun attachedLine(p: Ready): String =
        "Picture attached (${p.width} × ${p.height}, ${p.jpegBytes / 1024} KB). " +
            "It goes only to your PC."

    /**
     * The size to decode to: the long edge brought down to [maxLongEdge],
     * the other scaled to match, never enlarged, never below 1.
     */
    fun targetSize(width: Int, height: Int, maxLongEdge: Int = MAX_LONG_EDGE): Pair<Int, Int> {
        if (width <= 0 || height <= 0) return 1 to 1
        val long = maxOf(width, height)
        if (long <= maxLongEdge) return width to height
        val w = maxOf(1, (width.toLong() * maxLongEdge / long).toInt())
        val h = maxOf(1, (height.toLong() * maxLongEdge / long).toInt())
        return w to h
    }

    /** The JPEG as the data URI the desktop sends. */
    fun dataUri(jpeg: ByteArray): String =
        "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(jpeg)

    /**
     * The newest user message's `content` with a picture: the words, then the
     * picture - the desktop's order.
     */
    fun userContent(text: String, dataUri: String): JsonArray = buildJsonArray {
        add(
            buildJsonObject {
                put("type", "text")
                put("text", text)
            },
        )
        add(
            buildJsonObject {
                put("type", "image_url")
                putJsonObject("image_url") { put("url", dataUri) }
            },
        )
    }
}
