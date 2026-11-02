package com.jarvis.client

import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.service.ApprovalNotificationPolicy
import com.jarvis.client.service.ApprovalNotificationPolicy.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The five-point envelope for approving a card from an Android notification
 * (owner's ask of 2026-11-02; Gemini's binding ruling).
 *
 * What is held here, in the ruling's own order:
 *  1. Deny needs no unlock and is always offered when the desktop allows it.
 *  2. Every Approve asks Android for an unlocked device.
 *  3. Only a small read-only card may submit from the notification; every
 *     write/config/send/phone-app card opens Jarvis and runs its own check.
 *  4. A card whose words do not fit (more than 240 characters) is Review in
 *     Jarvis, never Approve.
 *  5. The lock screen gets a redacted public version and no Approve at all;
 *     a card that leaves `/api/pending` takes its notification with it.
 *
 * The policy is pure Kotlin on purpose: these are the rules that must not
 * depend on a phone, a notification shade or a system prompt being present.
 */
class ApprovalNotificationPolicyTest {

    private fun item(json: String): PendingItem =
        JarvisJson.decodeFromString(PendingItem.serializer(), json)

    /** A card with the given action and risk row; everything else minimal. */
    private fun card(
        id: String,
        action: String,
        risk: String = """{"reversible":"yes","reach":"local","swipe_ok":true,"classified":true}""",
        extra: String = "",
    ): PendingItem = item(
        """{"id":"$id","title":"Jarvis wants to do a thing","summary":"A short summary.",
             "tier":"ask","action":"$action","risk":$risk$extra}""",
    )

    /** `search_the_web` is on SecurityRules.SMALL_ACTIONS and changes nothing. */
    private fun smallCard(id: String = "s1") = card(id, "search_the_web")

    /**
     * A write that the owner's default setting would NOT ask about on the card
     * itself (`riskyByToday` is false: local and reversible). It is still not
     * small, so the notification must not approve it by itself.
     */
    private fun writeCard(id: String = "w1") = card(id, "setting_change")

    private fun plan(
        item: PendingItem,
        security: Security = Security(),
        locked: Boolean = false,
        title: String = item.title,
        body: String = "A short summary.",
    ) = ApprovalNotificationPolicy.plan(item, security, locked, title, body)

    // ---------------------------------------------------------------- point 1

    @Test
    fun `Deny is offered whenever the desktop allows refusing without reading`() {
        val offered = plan(smallCard()).actions.first { it.action == Action.DENY }
        assertFalse("Deny must stay reachable from the lock screen", offered.requiresUnlock)
    }

    @Test
    fun `Deny is dropped when the desktop says refusing is not safe`() {
        val card = item(
            """{"id":"n1","title":"A thing","action":"search_the_web",
                 "risk":{"reversible":"yes","reach":"local","swipe_ok":true,"classified":true},
                 "notice":{"title":"A thing","body":"Nothing has happened yet.","deny_ok":false}}""",
        )
        assertFalse(ApprovalNotificationPolicy.plan(card, Security(), false, card.title, "Body")
            .offers(Action.DENY))
    }

    // ---------------------------------------------------------------- point 2

    @Test
    fun `every approve asks Android for an unlocked device`() {
        val direct = plan(smallCard()).actions.first { it.action == Action.APPROVE_DIRECT }
        assertTrue("a direct approve still needs the phone unlocked", direct.requiresUnlock)
        val inApp = plan(writeCard()).actions.first { it.action == Action.APPROVE_IN_APP }
        assertTrue("opening the card to approve needs the phone unlocked", inApp.requiresUnlock)
        // Review only opens the app; it decides nothing, so it may work locked.
        val review = plan(writeCard(), title = "x", body = "x".repeat(241))
            .actions.first { it.action == Action.REVIEW }
        assertFalse("Review decides nothing, so it needs no unlock", review.requiresUnlock)
    }

    // ---------------------------------------------------------------- point 3

    @Test
    fun `a small read-only card may approve from the notification itself`() {
        val p = plan(smallCard())
        assertTrue(p.offers(Action.APPROVE_DIRECT))
        assertFalse("a direct approve must not also open the app", p.offers(Action.APPROVE_IN_APP))
        assertFalse(
            "the default setting exempts a small card from the check",
            SecurityRules.approvalNeedsCheck(Security(), smallCard()),
        )
        assertFalse(
            "so the notification path does not force one for it",
            ApprovalNotificationPolicy.notificationApproveNeedsCheck(smallCard(), Security()),
        )
    }

    @Test
    fun `a write card opens Jarvis and runs the check the card alone would skip`() {
        val p = plan(writeCard())
        assertTrue("a write card opens the app", p.offers(Action.APPROVE_IN_APP))
        assertFalse("never approved by the notification tap alone", p.offers(Action.APPROVE_DIRECT))
        // The point of the ruling: this card looks harmless to the owner's
        // default setting, and the notification surface must ask anyway.
        assertFalse(SecurityRules.riskyByToday(writeCard()))
        assertFalse(SecurityRules.approvalNeedsCheck(Security(), writeCard()))
        assertTrue(
            "the notification's Approve forces the BiometricPrompt",
            ApprovalNotificationPolicy.notificationApproveNeedsCheck(writeCard(), Security()),
        )
    }

    @Test
    fun `a send-file card is never a direct approve`() {
        val send = card(
            "f1",
            "send_file_to_phone",
            """{"reversible":"no","reach":"outbound","swipe_ok":false,"classified":true}""",
        )
        val p = plan(send)
        assertFalse(p.offers(Action.APPROVE_DIRECT))
        assertTrue(p.offers(Action.APPROVE_IN_APP))
        assertTrue(ApprovalNotificationPolicy.notificationApproveNeedsCheck(send, Security()))
    }

    @Test
    fun `a small card opens the app when the owner checks every approval`() {
        val every = Security(approvals = ApprovalCheck.EVERY)
        val p = plan(smallCard(), security = every)
        assertFalse("the owner's stricter setting wins", p.offers(Action.APPROVE_DIRECT))
        assertTrue(p.offers(Action.APPROVE_IN_APP))
        assertTrue(ApprovalNotificationPolicy.notificationApproveNeedsCheck(smallCard(), every))
    }

    @Test
    fun `a PC-only card, or one that needs a plan chosen, is Review not Approve`() {
        val pcOnly = card("p1", "desktop_update")
        assertTrue("desktop_update is on the PC-only list", pcOnly.pcOnly)
        assertTrue(plan(pcOnly).offers(Action.REVIEW))
        assertFalse(plan(pcOnly).offers(Action.APPROVE_IN_APP))

        val choice = card(
            "c1",
            "ambiguous_plan",
            extra = ""","options":[{"id":"a","label":"One","summary":"One","weight":"normal"},
                              {"id":"b","label":"Two","summary":"Two","weight":"normal"}]""",
        )
        assertTrue("two plans means no bare approve", choice.needsChoice)
        assertTrue(plan(choice).offers(Action.REVIEW))
        assertFalse(plan(choice).offers(Action.APPROVE_IN_APP))
    }

    // ---------------------------------------------------------------- point 4

    @Test
    fun `a card whose words do not fit offers Review instead of Approve`() {
        val body = "x".repeat(ApprovalNotificationPolicy.MAX_SHOWN_CHARS + 1)
        val p = plan(smallCard(), title = "", body = body)
        assertTrue(p.offers(Action.REVIEW))
        assertFalse("a clipped card is never approved sight-unseen", p.offers(Action.APPROVE_DIRECT))
        assertFalse(p.offers(Action.APPROVE_IN_APP))
        // Deny stays: refusing without reading is the safe direction.
        assertTrue(p.offers(Action.DENY))
    }

    @Test
    fun `exactly the limit still fits`() {
        val body = "x".repeat(ApprovalNotificationPolicy.MAX_SHOWN_CHARS)
        val p = plan(smallCard(), title = "", body = body)
        assertTrue(p.offers(Action.APPROVE_DIRECT))
        assertFalse(p.offers(Action.REVIEW))
    }

    @Test
    fun `the title counts too, because it is what gets clipped`() {
        val title = "y".repeat(ApprovalNotificationPolicy.MAX_SHOWN_CHARS)
        val p = plan(smallCard(), title = title, body = "a filename")
        assertTrue("title plus body is the text the owner reads", p.offers(Action.REVIEW))
    }

    // ---------------------------------------------------------------- point 5

    @Test
    fun `the lock screen is private and never offers Approve`() {
        val p = plan(smallCard(), locked = true)
        assertFalse("a redacted card cannot be approved", p.offers(Action.APPROVE_DIRECT))
        assertFalse(p.offers(Action.APPROVE_IN_APP))
        assertTrue("Deny is still the safe answer", p.offers(Action.DENY))
    }

    @Test
    fun `a redacted notification still offers Deny and the way to the card`() {
        val p = plan(smallCard(), locked = true)
        assertTrue("Deny is still the safe answer", p.offers(Action.DENY))
        assertTrue("Review only opens the card, where the app lock applies", p.offers(Action.REVIEW))
        assertFalse(p.offers(Action.APPROVE_DIRECT))
        assertFalse(p.offers(Action.APPROVE_IN_APP))
    }

    @Test
    fun `the public version says exactly what the owner asked for`() {
        assertEquals("Jarvis: 1 approval waiting", ApprovalNotificationPolicy.PUBLIC_WORDS)
    }

    @Test
    fun `a card that clears takes its notification with it`() {
        val a = smallCard("a")
        val b = smallCard("b")
        assertEquals(
            setOf("a"),
            ApprovalNotificationPolicy.cleared(listOf("a", "b"), listOf(b)),
        )
        assertEquals(
            "the whole drawer goes when the queue empties",
            setOf("a", "b"),
            ApprovalNotificationPolicy.cleared(listOf("a", "b"), emptyList()),
        )
        assertTrue(
            ApprovalNotificationPolicy.cleared(listOf("a", "b"), listOf(a, b)).isEmpty(),
        )
    }

    @Test
    fun `the notification's own approve is accepted only with the app's proof`() {
        assertTrue(InternalLaunch.approvesApproval(InternalLaunch.APPROVE_ACTION, "proof", "proof", true))
        assertFalse(InternalLaunch.approvesApproval(InternalLaunch.APPROVE_ACTION, "guess", "proof", true))
        assertFalse(InternalLaunch.approvesApproval(InternalLaunch.APPROVE_ACTION, "proof", "proof", false))
        assertFalse(
            InternalLaunch.approvesApproval(
                com.jarvis.client.service.ApprovalNotifier.ACTION_OPEN_APPROVAL,
                "proof", "proof", true,
            ),
        )
    }

    // ------------------------------------------------- what the code must wire

    private fun source(rel: String): String =
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/$rel")

    @Test
    fun `the notifier draws private, with the redacted public version`() {
        val src = source("service/ApprovalNotifier.kt")
        assertTrue(src.contains("setVisibility(NotificationCompat.VISIBILITY_PRIVATE)"))
        assertTrue(src.contains("setPublicVersion(redacted(context))"))
        assertTrue(src.contains("ApprovalNotificationPolicy.PUBLIC_WORDS"))
        assertTrue("the unlock rule must reach the Android action",
            src.contains("offered.requiresUnlock"))
        assertTrue(src.contains("setAuthenticationRequired(true)"))
        assertTrue(
            "a card that clears must cancel its notification through the tested rule",
            src.contains("ApprovalNotificationPolicy.cleared("),
        )
    }

    @Test
    fun `the in-app approve forces the card's own check`() {
        val src = source("MainActivity.kt")
        assertTrue(src.contains("notificationApproveNeedsCheck(item, currentSecurity())"))
        assertTrue(src.contains("confirmed(item, force = requireCheck)"))
        assertTrue(
            "the notification path must not look like a card press",
            src.contains("fromNotification = true"),
        )
    }

    @Test
    fun `the direct approve re-checks the live card before sending`() {
        val src = source("service/EventService.kt")
        val at = src.indexOf("private fun approveFromNotification(")
        assertTrue("approveFromNotification is gone from EventService", at >= 0)
        val end = src.indexOf("\n    /**", at)
        val fn = src.substring(at, if (end > at) end else src.length)
        assertTrue("the live card is re-read", fn.contains("JarvisRuntime.pending.value"))
        assertTrue("a refresh is asked for when it is missing", fn.contains("JarvisRuntime.refreshPending()"))
        assertTrue("the card must still be small", fn.contains("SecurityRules.isSmall(item)"))
        assertTrue("the phone's privacy state is re-checked", fn.contains("SecurityRules.notificationsLocked("))
        assertTrue("the decision is the same call the app makes", fn.contains("JarvisRuntime.decide(item, approve = true)"))
    }
}
