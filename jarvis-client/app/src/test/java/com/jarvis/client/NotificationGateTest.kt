package com.jarvis.client

import com.jarvis.client.data.NotificationGate
import com.jarvis.client.data.NotificationRedactor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The on-device notification gate (2026-10-20 Android audit, Area 10A): a
 * secret notification, the phone's SMS/MMS app and a banking package are all
 * refused BEFORE any word is kept, and a 4-8 digit contextual one-time code is
 * masked as the last step, still on the phone - so it can never reach the PC.
 *
 * These are the pure decisions; the listener wiring that calls them is pinned
 * separately in PhoneNotificationListenerService.kt by source.
 */
class NotificationGateTest {

    private fun capture(
        pkg: String = "com.example.chat",
        visibility: Int = 0,
        title: String = "Message",
        text: String = "hello",
        sms: Set<String> = emptySet(),
        category: Int? = null,
    ) = NotificationGate.capture(pkg, visibility, title, text, sms, category)

    @Test
    fun `a notification Android marks secret is never read or kept`() {
        val v = capture(visibility = NotificationGate.VISIBILITY_SECRET, text = "code 482913")
        assertTrue(v is NotificationGate.Verdict.SkipIt)
        assertEquals(NotificationGate.Skip.SECRET, (v as NotificationGate.Verdict.SkipIt).reason)
        // The skip carries no words at all - there is nothing in it that could
        // be stored or transmitted.
        assertTrue(v.toString().contains("SECRET"))
    }

    @Test
    fun `the phone's own SMS and MMS app is refused on device`() {
        val defaultSms = "com.google.android.apps.messaging"
        val v = capture(pkg = defaultSms, sms = setOf(defaultSms), text = "Your code is 482913")
        assertEquals(NotificationGate.Skip.SMS, (v as NotificationGate.Verdict.SkipIt).reason)
        // The static fallback list catches a Messages app even when Android's
        // default-SMS answer is empty (the audit's MMS concern arrives through
        // the same app).
        for (pkg in listOf("com.android.mms", "com.samsung.android.messaging")) {
            val fallback = capture(pkg = pkg, text = "anything")
            assertEquals(pkg, NotificationGate.Skip.SMS,
                (fallback as NotificationGate.Verdict.SkipIt).reason)
        }
    }

    @Test
    fun `a banking or payment package is refused even if it somehow reached the list`() {
        for (pkg in listOf(
            "com.chase.sig.android",
            "com.paypal.android.p2pmobile",
            "com.example.bank.mobile",
            "com.wellsfargo.mobile",
        )) {
            val v = capture(pkg = pkg, title = "Balance", text = "Your balance is visible")
            assertTrue(pkg, v is NotificationGate.Verdict.SkipIt)
            assertEquals(pkg, NotificationGate.Skip.BANKING,
                (v as NotificationGate.Verdict.SkipIt).reason)
        }
        // A normal app is not refused.
        val ok = capture(pkg = "com.example.chat", title = "Sam", text = "Lunch?")
        assertTrue(ok is NotificationGate.Verdict.Capture)
    }

    @Test
    fun `a 4 to 8 digit code is masked when either field carries a trigger word`() {
        val v = capture(
            title = "Your verification code",
            text = "Use 482913 to sign in to your account.",
        ) as NotificationGate.Verdict.Capture
        assertEquals("Your verification code", v.title)
        assertFalse("the code must be gone: ${v.text}", v.text.contains("482913"))
        assertTrue(v.text.contains(NotificationRedactor.MASK))
        // The trigger word in the TITLE counts for the TEXT (the 2026-09-28 fix).
        val t = capture(title = "OTP", text = "123456 is your code") as NotificationGate.Verdict.Capture
        assertFalse(t.text.contains("123456"))
        // A bare 4-8 digit code with nothing else is the common bank shape.
        val bare = capture(title = "Bank", text = "482913") as NotificationGate.Verdict.Capture
        assertFalse(bare.text.contains("482913"))
        assertEquals(NotificationRedactor.MASK, bare.text)
    }

    @Test
    fun `numbers that are not codes are left alone`() {
        val phone = capture(text = "Call me on 5551234567") as NotificationGate.Verdict.Capture
        assertEquals("Call me on 5551234567", phone.text)
        val time = capture(text = "Lunch at 12:30?") as NotificationGate.Verdict.Capture
        assertEquals("Lunch at 12:30?", time.text)
    }

    @Test
    fun `a keyword-less code in a longer sentence is honestly not caught`() {
        // Documented limit of the redactor: without a trigger word this cannot
        // be told apart from a number. The gate must not pretend otherwise.
        val v = capture(text = "call me at 482913 today") as NotificationGate.Verdict.Capture
        assertTrue(v.text.contains("482913"))
    }

    @Test
    fun `the secret and package refusals run before any code could be masked`() {
        // Order matters: a banking notification's words never come back at all,
        // even if they also carry a code.
        val bank = capture(pkg = "com.chase.sig.android", text = "code 482913")
        assertTrue(bank is NotificationGate.Verdict.SkipIt)
        val secret = capture(visibility = NotificationGate.VISIBILITY_SECRET, text = "code 482913")
        assertTrue(secret is NotificationGate.Verdict.SkipIt)
        assertFalse(bank.toString().contains("482913"))
        assertFalse(secret.toString().contains("482913"))
    }
}
