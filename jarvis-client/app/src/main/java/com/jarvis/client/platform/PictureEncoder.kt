package com.jarvis.client.platform

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageDecoder
import android.net.Uri
import com.jarvis.client.net.ChatPicture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

/**
 * Turns a photo the owner picked into a JPEG small enough for the PC -
 * in memory, never on disk.
 *
 * The photo comes from Android's photo picker as a `content://` address the
 * app may read once; no storage permission is involved. It is decoded
 * straight to at most [ChatPicture.MAX_LONG_EDGE] pixels on its long side
 * (`ImageDecoder.setTargetSize`, so the full-size photo is never held),
 * turned the right way up (ImageDecoder applies the photo's rotation), and
 * compressed at the desktop's quality. If that is still over
 * [ChatPicture.MAX_JPEG_BYTES], it tries lower qualities, then smaller sizes.
 *
 * Nothing here logs, and the error text never carries the picture.
 */
object PictureEncoder {

    sealed interface Outcome {
        data class Ok(val picture: ChatPicture.Ready) : Outcome
        data class Failed(val why: String) : Outcome
    }

    suspend fun encode(context: Context, uri: Uri): Outcome = withContext(Dispatchers.IO) {
        try {
            var edge = ChatPicture.MAX_LONG_EDGE
            while (true) {
                val bitmap = decode(context, uri, edge)
                try {
                    for (quality in listOf(ChatPicture.JPEG_QUALITY) + ChatPicture.FALLBACK_QUALITIES) {
                        val jpeg = compress(bitmap, quality)
                        if (jpeg.size <= ChatPicture.MAX_JPEG_BYTES) {
                            return@withContext Outcome.Ok(
                                ChatPicture.Ready(
                                    dataUri = ChatPicture.dataUri(jpeg),
                                    width = bitmap.width,
                                    height = bitmap.height,
                                    jpegBytes = jpeg.size,
                                ),
                            )
                        }
                    }
                } finally {
                    bitmap.recycle()
                }
                if (edge <= ChatPicture.SMALLEST_LONG_EDGE) break
                edge = maxOf(ChatPicture.SMALLEST_LONG_EDGE, edge * 3 / 4)
            }
            Outcome.Failed("That picture is too detailed to send, even made smaller. Try another one.")
        } catch (e: OutOfMemoryError) {
            Outcome.Failed("That picture is too big for this phone to prepare. Try another one.")
        } catch (e: Exception) {
            // The class name only: a message could quote the address it was read from.
            Outcome.Failed("Could not read that picture (${e.javaClass.simpleName}).")
        }
    }

    private fun decode(context: Context, uri: Uri, maxLongEdge: Int): Bitmap {
        val source = ImageDecoder.createSource(context.contentResolver, uri)
        return ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
            val (w, h) = ChatPicture.targetSize(info.size.width, info.size.height, maxLongEdge)
            decoder.setTargetSize(w, h)
            // A software bitmap: a hardware one lives on the graphics chip and
            // cannot be read back to compress.
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }
    }

    private fun compress(bitmap: Bitmap, quality: Int): ByteArray {
        val out = ByteArrayOutputStream(512 * 1024)
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
        return out.toByteArray()
    }
}
