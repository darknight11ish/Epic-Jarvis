package com.jarvis.client

import com.jarvis.client.net.ChatPicture
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SecondCard
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A photo shared INTO Jarvis from another app's Share sheet is attached under
 * exactly the Photo button's rule: only while the PC says Pictures on the
 * second graphics card works - and never dropped without a word.
 *
 * The PC's answers are the second-card fixture (`contract/second-card-cases.json`,
 * written from the backend's own functions); the "working" answer is that
 * fixture with only the Pictures feature's `available` set true, because no
 * written case has one.
 */
class SharedPictureTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/second-card-cases.json")) {
            "contract/second-card-cases.json is missing"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    private fun loaded(case: String, visionOn: Boolean = false): SecondCard.Read {
        var obj = cases[case]!!.jsonObject
        if (visionOn) {
            val features = (obj["features"] as JsonArray).map { f ->
                val fo = f.jsonObject
                if (fo["id"]!!.jsonPrimitive.content == SecondCard.VISION) {
                    JsonObject(fo + ("available" to JsonPrimitive(true)))
                } else {
                    fo
                }
            }
            obj = JsonObject(obj + ("features" to JsonArray(features)))
        }
        return SecondCard.Read.Loaded(requireNotNull(SecondCard.parse(obj)))
    }

    @Test
    fun onlyImagesAreTakenAsPictures() {
        assertTrue(ChatPicture.isSharedImage("image/jpeg"))
        assertTrue(ChatPicture.isSharedImage("image/png"))
        assertTrue(ChatPicture.isSharedImage("IMAGE/HEIC"))
        assertFalse(ChatPicture.isSharedImage("text/plain"))
        assertFalse(ChatPicture.isSharedImage("video/mp4"))
        assertFalse(ChatPicture.isSharedImage("application/pdf"))
        assertFalse(ChatPicture.isSharedImage(null))
    }

    @Test
    fun whenPicturesWorksTheShareIsAttached() {
        val read = loaded("capable_off", visionOn = true)
        assertTrue("the Photo button would be offered", SecondCard.visionAvailable(read))
        assertNull(ChatPicture.sharedRefusal(read))
    }

    @Test
    fun whenPicturesIsOffTheShareIsRefusedInWordsWithThePcsReason() {
        val read = loaded("one_card")
        assertFalse(SecondCard.visionAvailable(read))
        val said = ChatPicture.sharedRefusal(read)!!
        assertTrue(said.startsWith("The shared picture was not attached"))
        assertTrue("the PC's own reason", said.contains("only one graphics card found"))
        assertTrue(said.endsWith("Nothing was sent."))
    }

    @Test
    fun whenThePcCouldNotBeAskedTheShareIsRefusedToo() {
        for (read in listOf(
            SecondCard.Read.NotAsked,
            SecondCard.Read.OlderBackend,
            SecondCard.Read.NotInstalled,
            SecondCard.Read.Failed("timed out"),
        )) {
            val said = ChatPicture.sharedRefusal(read)
            assertTrue("$read", said != null && said.startsWith("The shared picture was not attached"))
        }
        assertEquals(
            "The shared picture was not attached: Jarvis takes pictures only while Pictures on the " +
                "second graphics card is working, or your PC can read the words in them (timed out). " +
                "Nothing was sent.",
            ChatPicture.sharedRefusal(SecondCard.Read.Failed("timed out")),
        )
    }

    @Test
    fun whenThePcReadsTheWordsInAPictureTheShareIsAttachedAndSaysSo() {
        // The PC's real status (tools/gen_second_card_cases.py): no picture
        // model, but the PC reads the words in a picture (2026-09-26).
        val read = loaded("one_card_reads_words")
        assertFalse(SecondCard.visionAvailable(read))
        assertTrue(SecondCard.pictureTextAvailable(read))
        assertTrue("the Photo button would be offered", SecondCard.picturesTaken(read))
        assertNull(ChatPicture.sharedRefusal(read))
        val p = ChatPicture.Ready("data:image/jpeg;base64,AA", 10, 20, 2048)
        assertEquals(
            "Picture attached (10 × 20, 2 KB). " + ChatPicture.WORDS_ONLY,
            ChatPicture.attachedLine(p, wordsOnly = true),
        )
        assertTrue(ChatPicture.WORDS_ONLY.contains("outside text"))
        // An older PC says nothing about it: not taken.
        assertFalse(SecondCard.pictureTextAvailable(loaded("one_card")))
    }
}
