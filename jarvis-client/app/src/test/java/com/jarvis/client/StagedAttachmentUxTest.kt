package com.jarvis.client

import com.jarvis.client.net.AttachFile
import com.jarvis.client.net.ChatPicture
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The strip under the composer is NOT an answer, and a failed send does not
 * throw the file away.
 *
 * The owner's report of 2026-11-02: a photo and a document were attached and
 * an analysis was expected; what was on screen instead was the two strips and
 * an empty box. Nothing had been sent - a staged attachment waits for the
 * next typed question, and Send is disabled while the box has no words
 * (HomeScreen's `canSend`) - but neither strip said so, so both read as
 * Jarvis's answer.
 *
 * The words half calls the real functions. The wiring half reads the two
 * Android sources, because the picker callbacks and the send path live in
 * `MainActivity`'s composable and cannot be constructed in a JVM test; these
 * pins fail on the tree before the fix.
 */
class StagedAttachmentUxTest {

    private val attach = AttachFile.Ready(
        name = "taxes.pdf",
        mime = "application/pdf",
        size = 12,
        base64 = AttachFile.base64("123456789012".toByteArray()),
    )

    private val picture = ChatPicture.Ready(
        dataUri = "data:image/jpeg;base64,AA",
        width = 10,
        height = 20,
        jpegBytes = 2048,
    )

    private val main by lazy {
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
    }
    private val home by lazy {
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt")
    }
    private val strip by lazy {
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/VoiceButton.kt")
    }

    // ------------------------------------------------------------- the words ---

    @Test
    fun `a staged file says it has not been sent, and what to do`() {
        val line = AttachFile.attachedLine(attach)
        assertTrue(line, line.startsWith("Attached to your next question"))
        assertTrue(line, line.contains("not sent yet"))
        assertTrue(line, line.contains("Type it and press Send."))
        // Everything the chip said before is still said: the name, the size,
        // where it is read, and what a later web search will ask.
        assertTrue(line, line.contains("taxes.pdf"))
        assertTrue(line, line.contains("12 bytes"))
        assertTrue(line, line.contains(AttachFile.READ_ON_PC))
        assertTrue(line, line.contains(AttachFile.OUTSIDE_TEXT))
    }

    @Test
    fun `a staged picture says it has not been sent, and what to do`() {
        for (wordsOnly in listOf(true, false)) {
            val line = ChatPicture.attachedLine(picture, wordsOnly = wordsOnly)
            assertTrue(line, line.startsWith("Attached to your next question"))
            assertTrue(line, line.contains("not sent yet"))
            assertTrue(line, line.contains("Type it and press Send."))
            assertTrue(line, line.contains("10 × 20"))
            assertTrue(line, line.contains(ChatPicture.SECRETS_COVERED))
        }
    }

    // ---------------------------------------------------------- the picking ---

    @Test
    fun `picking a file or a picture leaves the typed question in the box`() {
        // A typed question is `draft` (rememberSaveable, MainActivity). The
        // picker callbacks only fill the staged slot; choosing a file must
        // never empty what the owner already typed.
        val filePicker = main.substringAfter("private val pickAttachFile")
            .substringBefore("private fun readAttachFile")
        val pictureAttach = main.substringAfter("private fun attachPicture(")
            .substringBefore("override fun onCreate")
        val attachActions = main.substringAfter("onAttachFile = {")
            .substringBefore("onRemoveAttach")
        for ((where, block) in listOf(
            "the file picker" to filePicker,
            "the picture picker" to pictureAttach,
            "the attach action" to attachActions,
        )) {
            assertFalse("$where clears the typed question", block.contains("draft ="))
            assertFalse("$where clears the typed question", block.contains("onDraftChange"))
        }
    }

    // ----------------------------------------------------- after a failed send ---

    @Test
    fun `a send that fails puts the file and the picture back`() {
        assertTrue(
            "the send path never gives the file back after a failure",
            main.contains("StagedLine.comesBack(answer, JarvisRuntime.chat.error.value != null)"),
        )
        assertTrue(
            "a failed send does not put the file back",
            main.contains("if (doc != null && attachedFile.value == null) attachedFile.value = doc"),
        )
        assertTrue(
            "a failed send does not put the picture back",
            main.contains("if (pic != null && picture.value == null) picture.value = pic"),
        )
    }

    @Test
    fun `try again carries the file the failed question had`() {
        val retry = main.substringAfter("val started = chat.retryLast(")
            .substringBefore(")")
        assertTrue(
            "a retry asks the question without the file it was asked with",
            retry.contains("attachment = doc"),
        )
        assertTrue(
            "a retry asks the question without the picture it was asked with",
            retry.contains("picture = pic?.dataUri"),
        )
        assertTrue(
            "a retry that never started loses the file",
            main.contains("if (!started || chat.error.value != null)"),
        )
    }

    @Test
    fun `the staged strips offer Remove, not Dismiss`() {
        // "Dismiss" reads like closing a message; these two strips are the
        // owner's own file and picture, which they REMOVE.
        val remove = "dismissLabel = com.jarvis.client.net.StagedLine.REMOVE"
        assertTrue("the file strip still says Dismiss", home.contains(remove))
        assertTrue(
            "only one of the two staged strips offers Remove",
            home.split(remove).size == 3,
        )
        // Every other strip keeps the old label: only an attachment is removed.
        assertTrue(strip.contains("dismissLabel: String = \"Dismiss\""))
    }
}
