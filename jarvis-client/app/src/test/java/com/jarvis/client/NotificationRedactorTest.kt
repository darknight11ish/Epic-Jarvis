package com.jarvis.client

import com.jarvis.client.data.NotificationRedactor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `data/NotificationRedactor.kt` - the one-time-code heuristic every
 * captured notification's title and text go through BEFORE
 * [com.jarvis.client.data.CapturedNotifications] ever stores them
 * (CLAUDE.md, 2026-09-26: "one-time codes hidden before anything reaches
 * the model"). The class's own doc has the full, honest list of what this
 * catches and what it does not; these tests prove that list is actually
 * true of the code, not just claimed of it.
 */
class NotificationRedactorTest {

    // --------------------------------------------------- caught, with a trigger word

    @Test
    fun `a code after the trigger word is hidden`() {
        assertEquals(
            "Your verification code is [hidden code]",
            NotificationRedactor.redact("Your verification code is 482913"),
        )
    }

    @Test
    fun `a code before the trigger word is hidden too`() {
        assertEquals(
            "[hidden code] is your WhatsApp code",
            NotificationRedactor.redact("482913 is your WhatsApp code"),
        )
    }

    @Test
    fun `the NNN NNN and NNN-NNN groupings are both caught with a trigger word`() {
        assertEquals("Your code: [hidden code]", NotificationRedactor.redact("Your code: 123 456"))
        assertEquals("OTP [hidden code] expires soon", NotificationRedactor.redact("OTP 123-456 expires soon"))
    }

    @Test
    fun `otp, passcode, 2fa and one-time all count as trigger words`() {
        for (word in listOf("otp", "OTP", "passcode", "2FA", "one-time", "one time", "security code")) {
            val text = "Your $word is 482913"
            assertTrue(text, NotificationRedactor.redact(text).contains(NotificationRedactor.MASK))
        }
    }

    // --------------------------------------------------- caught, no trigger word needed (bare code)

    @Test
    fun `a bare digit-only notification is hidden even with no trigger word`() {
        assertEquals("[hidden code]", NotificationRedactor.redact("482913"))
    }

    @Test
    fun `google's leading-letter-and-dash shape is hidden too`() {
        assertEquals("G-[hidden code]", NotificationRedactor.redact("G-482913"))
    }

    @Test
    fun `a bare code with ordinary trailing punctuation is still hidden`() {
        assertEquals("[hidden code].", NotificationRedactor.redact("482913."))
    }

    // --------------------------------------------------- honestly NOT caught

    @Test
    fun `a bare digit run with no trigger word, inside a sentence, is left alone`() {
        val text = "Meeting starts at 1400 in room 482913"
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `a ten-digit run - a phone number shape - is never touched`() {
        val text = "Call me at 4829136721 today"
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `a currency amount with thousands separators is untouched`() {
        val text = "Your account balance is $1,234,567"
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `a trigger word in a language other than english is not recognised`() {
        // "code" in French - not on the English-only trigger list.
        val text = "Votre code de vérification est 482913"
        // "verification" IS an English substring inside "vérification"? No -
        // the accented e breaks it; this proves the documented limit stands.
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `a 3-digit or shorter run is never treated as a code, trigger word or not`() {
        val text = "Your code is 42"
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `over-redaction is the documented, accepted trade-off`() {
        // A year, not a code - redacted anyway because "code" is right next to
        // it. Documented in the class's own doc as an accepted trade-off.
        assertEquals("verification code [hidden code]", NotificationRedactor.redact("verification code 2026"))
        // The same year, with NO trigger word, is left alone.
        assertEquals(
            "Reminder: your appointment is in 2026",
            NotificationRedactor.redact("Reminder: your appointment is in 2026"),
        )
    }

    // --------------------------------------------------- both fields, blank input, idempotence

    @Test
    fun `redactBoth redacts title and text independently`() {
        val (title, text) = NotificationRedactor.redactBoth(
            "Your code is 111222",
            "Use 111222 to sign in - never share this code with anyone",
        )
        assertFalse(title.contains("111222"))
        assertFalse(text.contains("111222"))
    }

    @Test
    fun `blank text is returned as it is, never crashes`() {
        assertEquals("", NotificationRedactor.redact(""))
        assertEquals("   ", NotificationRedactor.redact("   "))
    }

    @Test
    fun `text with nothing code-shaped in it is returned unchanged`() {
        val text = "Your package has been delivered"
        assertEquals(text, NotificationRedactor.redact(text))
    }

    @Test
    fun `redacting an already-redacted text changes nothing further`() {
        val once = NotificationRedactor.redact("Your code is 482913")
        assertEquals(once, NotificationRedactor.redact(once))
    }
}
