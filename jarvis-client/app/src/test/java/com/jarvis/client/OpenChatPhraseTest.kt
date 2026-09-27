package com.jarvis.client

import com.jarvis.client.net.OpenChatPhrase
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** "Open a chat" while Floating Jarvis is up (net/OpenChatPhrase.kt). */
class OpenChatPhraseTest {

    @Test
    fun `matches the fixed phrases`() {
        assertTrue(OpenChatPhrase.matches("open a chat"))
        assertTrue(OpenChatPhrase.matches("Open the chat"))
        assertTrue(OpenChatPhrase.matches("show me the chat"))
        assertTrue(OpenChatPhrase.matches("bring up the chat window"))
    }

    @Test
    fun `no longer matches what the backend's own grammar never did (bug audit 2026-09-27, finding #7)`() {
        // These used to be in PHRASES and brought the app to the front here
        // - but typing or saying the same words as an ordinary chat message
        // would never have opened anything, since jarvis_quick.py's own
        // _OPEN_CHAT grammar never matched them either. Removed so the two
        // can no longer disagree; open-chat-cases.json is the shared proof.
        assertFalse(OpenChatPhrase.matches("show me the chat screen."))
        assertFalse(OpenChatPhrase.matches("let's chat"))
        assertFalse(OpenChatPhrase.matches("open jarvis"))
        assertFalse(OpenChatPhrase.matches("open the app"))
    }

    @Test
    fun `is case and punctuation insensitive`() {
        assertTrue(OpenChatPhrase.matches("OPEN A CHAT!"))
        assertTrue(OpenChatPhrase.matches("  open a chat   "))
    }

    @Test
    fun `ignores a leading hey jarvis`() {
        assertTrue(OpenChatPhrase.matches("hey jarvis, open a chat"))
        assertTrue(OpenChatPhrase.matches("Jarvis, show me the chat"))
        assertTrue(OpenChatPhrase.matches("okay jarvis open the chat"))
    }

    @Test
    fun `an ordinary question is not a match`() {
        assertFalse(OpenChatPhrase.matches("what's the weather like"))
        assertFalse(OpenChatPhrase.matches("open a chat with my sister"))
        assertFalse(OpenChatPhrase.matches("can you open a chat for me please and then"))
        assertFalse(OpenChatPhrase.matches(""))
        assertFalse(OpenChatPhrase.matches("hey jarvis"))
    }
}
