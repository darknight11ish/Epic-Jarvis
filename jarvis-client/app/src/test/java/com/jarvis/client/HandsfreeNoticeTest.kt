package com.jarvis.client

import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.SmsSend
import com.jarvis.client.service.ApprovalNotificationPolicy
import com.jarvis.client.service.HandsfreeNotice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The hands-free notification's ONE redaction rule, held without a phone.
 *
 * The bug this file exists for (privacy audit, 2026-11-05): `HandsfreeService`
 * put the PC's whole `say` sentence in the notification body and the recipient
 * plus the message text in the SMS receipt, and never applied
 * [SecurityRules.notificationsLocked] - so with App lock on, or "Hide memory
 * lists and chat history", or a phone whose own lock screen was not secure, the
 * card's words and the text message were readable by anyone who picked the
 * phone up. Every other notifier already redacted; this one did not.
 *
 * A JVM test cannot build an Android `Service`, so the words live in
 * [HandsfreeNotice] - a pure object the service calls - and this is where the
 * promise is proven. The last test pins the service to that object, so the rule
 * cannot be lifted back into a private function no test can reach.
 */
class HandsfreeNoticeTest {

    /** A card whose every word is private: a person, a message, and a deadline. */
    private fun card(expires: Int = 90) = Handsfree.Card(
        cardId = "card-7",
        action = "models_switch",
        say = "Jarvis wants to send Priya the message: running late tonight.",
        expiresInSec = expires,
    )

    private fun wordsOf(w: HandsfreeNotice.Words): String = "${w.title} | ${w.body}"

    /** Every fragment that must never reach a locked phone's screen. */
    private val privateWords = listOf(
        "Priya",
        "running late",
        "the message",
        "Jarvis wants to send",
        "90s",
        "models_switch",
    )

    private fun assertNoPrivate(words: HandsfreeNotice.Words, what: String) {
        for (secret in privateWords) {
            assertFalse(
                "$what leaked \"$secret\": ${wordsOf(words)}",
                wordsOf(words).contains(secret, ignoreCase = true),
            )
        }
    }

    // ------------------------------------------------------------- locked ----

    @Test
    fun `a locked phone gets no card words - not the say, not the action, not the time`() {
        val words = HandsfreeNotice.card(
            locked = true,
            card = card(),
            line = null,
            waiting = "An approval card is waiting.",
        )
        assertEquals("the whole notification is the generic line", HandsfreeNotice.LOCKED, words)
        assertNoPrivate(words, "a locked card notification")
    }

    @Test
    fun `a locked phone gets the decision line redacted too`() {
        // Once the PC has answered, the body is `flow.line()` - which quotes
        // what was heard ("Heard: \"yes, send it to Priya\" - approved"). It is
        // the same rule: nothing but the generic line on a locked screen.
        val words = HandsfreeNotice.card(
            locked = true,
            card = card(),
            line = "Heard: \"yes, send it to Priya\" - approved.",
            waiting = "An approval card is waiting.",
        )
        assertEquals(HandsfreeNotice.LOCKED, words)
        assertNoPrivate(words, "a locked decision line")
    }

    @Test
    fun `a locked phone gets no text message - not the name, not the words sent`() {
        val receipt = SmsSend.sentLine("Priya", "Running late tonight")
        // CONTROL: the receipt really is the leaky half; if this ever stops
        // naming the recipient, the test below would pass for the wrong reason.
        assertTrue("the receipt itself names the recipient", receipt.contains("Priya"))

        val words = HandsfreeNotice.sms(locked = true, title = "Text message", line = receipt)
        assertEquals(HandsfreeNotice.LOCKED, words)
        assertFalse("the recipient leaked", wordsOf(words).contains("Priya"))
        assertFalse("the message leaked", wordsOf(words).contains("Running late", ignoreCase = true))
        assertFalse("the receipt leaked", wordsOf(words).contains("Sent to"))
    }

    @Test
    fun `a locked phone's line never claims a card expired`() {
        // The generic line is about a decision waiting, because that is what a
        // locked phone knows. It is not a failure sentence and not an expiry.
        val words = HandsfreeNotice.LOCKED
        assertFalse(words.body.contains("expired", ignoreCase = true))
        assertFalse(words.body.contains("failed", ignoreCase = true))
        assertTrue("and it says what to do", words.body.contains("Unlock"))
        assertTrue("and where it is from", words.title.contains("Jarvis"))
    }

    // ----------------------------------------------------------- unlocked ----

    @Test
    fun `an unlocked phone still shows the card's own sentence`() {
        // The control the leak would hide behind: a rule that redacted always
        // would make every test above pass and the feature useless.
        val words = HandsfreeNotice.card(
            locked = false,
            card = card(),
            line = null,
            waiting = "An approval card is waiting.",
        )
        assertNotEquals(HandsfreeNotice.LOCKED, words)
        assertTrue("the PC's own sentence is shown", words.body.contains("Priya"))
        assertTrue("and the time it has left", words.title.contains("90s left"))
        assertTrue("and the action's plain words", words.title.isNotBlank())
    }

    @Test
    fun `an unlocked phone still shows the text it sent`() {
        val receipt = SmsSend.sentLine("Priya", "Running late tonight")
        val words = HandsfreeNotice.sms(locked = false, title = "Text message", line = receipt)
        assertEquals("Text message", words.title)
        assertEquals(receipt, words.body)
    }

    @Test
    fun `a card the PC gave no sentence for falls back to the waiting line`() {
        val bare = Handsfree.Card(cardId = "c8", action = "", say = "", expiresInSec = 0)
        val words = HandsfreeNotice.card(
            locked = false,
            card = bare,
            line = null,
            waiting = "An approval card is waiting.",
        )
        assertEquals("An approval card is waiting.", words.body)
        assertTrue(words.title.isNotBlank())
    }

    // -------------------------------------------------------------- rules ----

    @Test
    fun `the redaction rule is the app's one rule, not this feature's own`() {
        // The three states the owner named: App lock, private lists, and a
        // phone with no secure lock of its own (M12 - Android's PRIVATE still
        // draws the body on a swipe-only lock screen, so it must be redacted).
        val open = Security()
        assertFalse(SecurityRules.notificationsLocked(open, deviceSecure = true))
        assertTrue(SecurityRules.notificationsLocked(open.copy(appLock = true), true))
        assertTrue(SecurityRules.notificationsLocked(open.copy(privateLists = true), true))
        assertTrue(SecurityRules.notificationsLocked(open, deviceSecure = false))
        // And the notifier's rule is that same function, not a copy of it: the
        // approval notifier reads it at its own build() and this file pins the
        // pair by name.
        val approval = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/ApprovalNotifier.kt",
        )
        assertTrue(
            "ApprovalNotifier no longer reads SecurityRules.notificationsLocked",
            approval.contains("SecurityRules.notificationsLocked("),
        )
        val service = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/HandsfreeService.kt",
        )
        assertTrue(
            "HandsfreeService no longer reads SecurityRules.notificationsLocked",
            service.contains("SecurityRules.notificationsLocked("),
        )
    }

    @Test
    fun `the locked line is the one the approval notifier already shows`() {
        val strings = repoFile("jarvis-client/app/src/main/res/values/strings.xml").readText()
        assertTrue(
            "the locked line and R.string.approval_locked have drifted apart",
            strings.contains("<string name=\"approval_locked\">${HandsfreeNotice.LOCKED.body}</string>"),
        )
    }

    @Test
    fun `the lock screen's public copy is the approval notifier's own sentence`() {
        assertEquals(ApprovalNotificationPolicy.PUBLIC_WORDS, HandsfreeNotice.PUBLIC)
        // It names no card and no message: it is a count of decisions waiting.
        assertFalse(HandsfreeNotice.PUBLIC.contains("Priya"))
        assertTrue(HandsfreeNotice.PUBLIC.contains("Jarvis"))
    }

    @Test
    fun `the service puts the rule on BOTH notifications, with a redacted public copy`() {
        // The half a JVM test cannot build: `post()` is Android. Pinned by
        // source so a later edit cannot drop the call that applies the rule, or
        // the PRIVATE/public pair that keeps the body off the lock screen.
        val service = SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/HandsfreeService.kt",
        )
        assertTrue(
            "the card notification no longer goes through HandsfreeNotice.card",
            service.contains("HandsfreeNotice.card("),
        )
        assertTrue(
            "the SMS notification no longer goes through HandsfreeNotice.sms",
            service.contains("HandsfreeNotice.sms("),
        )
        assertTrue(
            "post() no longer marks the notification VISIBILITY_PRIVATE",
            service.contains(".setVisibility(NotificationCompat.VISIBILITY_PRIVATE)"),
        )
        assertTrue(
            "post() no longer sets a redacted public version",
            service.contains(".setPublicVersion("),
        )
        assertTrue(
            "the public version is not the redacted line",
            service.contains("HandsfreeNotice.PUBLIC"),
        )
        // And the card's own words are not built in the service any more: the
        // leak lived in exactly those two lines.
        assertFalse(
            "the service builds the card body itself again",
            service.contains("card.say.trim()"),
        )
    }
}
