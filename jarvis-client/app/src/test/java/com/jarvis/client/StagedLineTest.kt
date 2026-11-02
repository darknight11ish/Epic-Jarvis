package com.jarvis.client

import com.jarvis.client.net.AttachFile
import com.jarvis.client.net.ChatPicture
import com.jarvis.client.net.StagedLine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The pure half of the staged-attachment strip: the sentence both chips open
 * with, the action that removes them, and the one rule that decides whether a
 * strip comes back after a send.
 *
 * The owner's report of 2026-11-02 is the reason: a photo and a document were
 * picked, and the two strips under the composer were read as Jarvis's answer.
 */
class StagedLineTest {

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

    @Test
    fun `both chips open with the one sentence that says nothing was sent`() {
        assertTrue(StagedLine.HEAD.contains("not sent yet"))
        assertTrue(StagedLine.HEAD.contains("Type it and press Send."))
        // The same words for a file and for a picture: the owner should not
        // have to learn two sentences for the same state.
        assertTrue(AttachFile.attachedLine(attach).startsWith(StagedLine.HEAD))
        assertTrue(ChatPicture.attachedLine(picture).startsWith(StagedLine.HEAD))
    }

    @Test
    fun `the action removes the owner's own attachment`() {
        assertEquals("Remove", StagedLine.REMOVE)
    }

    // -------------------------------------------------- after a send returns ---

    @Test
    fun `a real failure brings the strip back`() {
        // Offline, a stale link, the PC refusing, an oversize body: no answer,
        // and the chat put its error on screen. The bytes are nowhere else.
        assertTrue(StagedLine.comesBack(answer = null, errorShown = true))
    }

    @Test
    fun `Stop does not, because the bytes had already gone`() {
        // The owner's Stop cancels the call: no answer, but no error either.
        // Putting the file back would invite a second copy of one the PC read.
        assertFalse(StagedLine.comesBack(answer = null, errorShown = false))
    }

    @Test
    fun `a finished answer does not`() {
        assertFalse(StagedLine.comesBack(answer = "", errorShown = true))
        assertFalse(StagedLine.comesBack(answer = "It is a tax form.", errorShown = false))
        assertFalse(StagedLine.comesBack(answer = "It is a tax form.", errorShown = true))
    }
}
