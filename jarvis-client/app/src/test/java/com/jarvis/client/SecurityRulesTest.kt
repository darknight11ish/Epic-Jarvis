package com.jarvis.client

import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.CheckAvailability
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.CheckOutcome
import com.jarvis.client.data.LockSession
import com.jarvis.client.data.RelockAfter
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.data.SecurityRules.Verdict
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.Raised
import com.jarvis.client.net.Risk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's lock and fingerprint settings (data/Security.kt): which
 * approvals ask, what a phone with no screen lock does, what counts as
 * loosening, and when the app locks again.
 */
class SecurityRulesTest {

    private val safe = PendingItem(
        id = "s",
        risk = Risk(reversible = "yes", reach = "local", swipeOk = true, classified = true),
    )
    private val outbound = PendingItem(
        id = "o",
        risk = Risk(reversible = "yes", reach = "outbound", classified = true),
    )
    private val irreversible = PendingItem(
        id = "i",
        risk = Risk(reversible = "no", reach = "local", classified = true),
    )
    private val unclassified = PendingItem(id = "u")
    private val rushed = PendingItem(
        id = "r",
        risk = Risk(reversible = "yes", reach = "local", swipeOk = true, classified = true),
        raised = Raised(code = "rushed", quote = "hurry", countToday = 1),
    )

    // ---------------------------------------------------------- defaults --

    @Test
    fun `the defaults are today's behaviour`() {
        val d = Security()
        assertFalse(d.appLock)
        assertEquals(RelockAfter.ONE_MINUTE, d.relockAfter)
        assertEquals(ApprovalCheck.RISKY, d.approvals)
        assertFalse(d.privateLists)
        assertEquals(CheckMethod.FINGERPRINT_OR_PIN, d.method)
        assertFalse(d.anyLockOn)
    }

    @Test
    fun `today's rule asks for outbound, irreversible, unclassified and rushed`() {
        assertTrue(SecurityRules.riskyByToday(outbound))
        assertTrue(SecurityRules.riskyByToday(irreversible))
        assertTrue(SecurityRules.riskyByToday(unclassified))
        assertTrue(SecurityRules.riskyByToday(rushed))
        assertFalse(SecurityRules.riskyByToday(safe))
    }

    @Test
    fun `every approval asks for the check, and risky only never asks for less than today`() {
        val every = Security(approvals = ApprovalCheck.EVERY)
        for (item in listOf(safe, outbound, irreversible, unclassified, rushed)) {
            assertTrue(SecurityRules.approvalNeedsCheck(every, item))
            assertEquals(SecurityRules.riskyByToday(item), SecurityRules.approvalNeedsCheck(Security(), item))
        }
    }

    // ------------------------------------------------- no screen lock ----

    @Test
    fun `with nothing turned on, a phone that cannot check still lets the approval through`() {
        assertEquals(Verdict.Go, SecurityRules.afterApprovalCheck(Security(), CheckOutcome.UNAVAILABLE))
    }

    @Test
    fun `with any lock on, a phone with no screen lock refuses and says how to fix it`() {
        val turnedOn = listOf(
            Security(appLock = true),
            Security(approvals = ApprovalCheck.EVERY),
            Security(privateLists = true),
            Security(method = CheckMethod.FINGERPRINT_ONLY),
        )
        for (s in turnedOn) {
            val v = SecurityRules.afterApprovalCheck(s, CheckOutcome.UNAVAILABLE)
            assertTrue("$s", v is Verdict.Stop)
            val say = (v as Verdict.Stop).say!!
            assertTrue(say, say.startsWith("Nothing was approved."))
            if (s.method == CheckMethod.FINGERPRINT_ONLY) {
                assertTrue(say, "Add a fingerprint" in say)
            } else {
                assertTrue(say, "screen lock" in say)
            }
        }
    }

    @Test
    fun `a cancelled check stops quietly and a check that did not show says so`() {
        val s = Security(appLock = true)
        assertEquals(Verdict.Stop(null), SecurityRules.afterApprovalCheck(s, CheckOutcome.CANCELLED))
        assertEquals(Verdict.Stop(SecurityRules.CHECK_NOT_SHOWN), SecurityRules.afterApprovalCheck(s, CheckOutcome.FAILED))
        assertEquals(Verdict.Go, SecurityRules.afterApprovalCheck(s, CheckOutcome.CONFIRMED))
    }

    @Test
    fun `loosening, unlocking or showing needs a real confirmation`() {
        val m = CheckMethod.FINGERPRINT_OR_PIN
        assertEquals(Verdict.Go, SecurityRules.afterOwnerCheck(m, CheckOutcome.CONFIRMED, "nothing was changed"))
        assertEquals(Verdict.Stop(null), SecurityRules.afterOwnerCheck(m, CheckOutcome.CANCELLED, "nothing was changed"))
        val none = SecurityRules.afterOwnerCheck(m, CheckOutcome.UNAVAILABLE, "nothing was changed")
        assertEquals("Nothing was changed.", ((none as Verdict.Stop).say!!).substringBefore(" This"))
        val failed = SecurityRules.afterOwnerCheck(m, CheckOutcome.FAILED, "nothing was changed")
        assertTrue((failed as Verdict.Stop).say!!.contains("so nothing was changed."))
    }

    // ------------------------------------------------------ loosening ----

    @Test
    fun `each loosening is caught, one field at a time`() {
        val strict = Security(
            appLock = true,
            relockAfter = RelockAfter.NOW,
            approvals = ApprovalCheck.EVERY,
            privateLists = true,
            method = CheckMethod.FINGERPRINT_ONLY,
        )
        assertTrue(SecurityRules.loosens(strict, strict.copy(appLock = false)))
        assertTrue(SecurityRules.loosens(strict, strict.copy(relockAfter = RelockAfter.ONE_MINUTE)))
        assertTrue(SecurityRules.loosens(strict, strict.copy(approvals = ApprovalCheck.RISKY)))
        assertTrue(SecurityRules.loosens(strict, strict.copy(privateLists = false)))
        assertTrue(SecurityRules.loosens(strict, strict.copy(method = CheckMethod.FINGERPRINT_OR_PIN)))
        assertFalse(SecurityRules.loosens(strict, strict))
    }

    @Test
    fun `each tightening is instant`() {
        val loose = Security(relockAfter = RelockAfter.FIFTEEN_MINUTES)
        assertFalse(SecurityRules.loosens(loose, loose.copy(appLock = true)))
        assertFalse(SecurityRules.loosens(loose, loose.copy(relockAfter = RelockAfter.FIVE_MINUTES)))
        assertFalse(SecurityRules.loosens(loose, loose.copy(approvals = ApprovalCheck.EVERY)))
        assertFalse(SecurityRules.loosens(loose, loose.copy(privateLists = true)))
        assertFalse(SecurityRules.loosens(loose, loose.copy(method = CheckMethod.FINGERPRINT_ONLY)))
    }

    @Test
    fun `a change that tightens one thing and loosens another still needs the check`() {
        val from = Security(appLock = true)
        assertTrue(SecurityRules.loosens(from, Security(appLock = false, approvals = ApprovalCheck.EVERY)))
    }

    @Test
    fun `a lock the phone cannot check is refused before it can lock the owner out`() {
        val on = Security(appLock = true)
        assertNull(SecurityRules.refuseTightening(on, CheckAvailability.READY))
        assertNotNull(SecurityRules.refuseTightening(on, CheckAvailability.NOT_SET_UP))
        assertNotNull(SecurityRules.refuseTightening(on, CheckAvailability.NO_HARDWARE))
        val fp = Security(method = CheckMethod.FINGERPRINT_ONLY)
        assertTrue(SecurityRules.refuseTightening(fp, CheckAvailability.NOT_SET_UP)!!.startsWith("Add a fingerprint"))
        // Everything off needs nothing from the phone.
        assertNull(SecurityRules.refuseTightening(Security(), CheckAvailability.NO_HARDWARE))
    }

    @Test
    fun `the Checks summary says what is on in plain words`() {
        assertTrue(SecurityRules.summary(Security()).startsWith("Off."))
        assertEquals(
            "App lock on (5 min), every approval asks, memory lists hidden, fingerprint only.",
            SecurityRules.summary(
                Security(true, RelockAfter.FIVE_MINUTES, ApprovalCheck.EVERY, true, CheckMethod.FINGERPRINT_ONLY),
            ),
        )
        assertEquals("App lock off, risky approvals ask, memory lists hidden.", SecurityRules.summary(Security(privateLists = true)))
    }

    // -------------------------------------------------------- storage ----

    @Test
    fun `settings survive the round trip, and unreadable ones fall back to the default`() {
        val s = Security(true, RelockAfter.FIVE_MINUTES, ApprovalCheck.EVERY, true, CheckMethod.FINGERPRINT_ONLY)
        val stored = SecurityRules.toStored(s)
        assertEquals(s, SecurityRules.fromStored { stored[it] })
        assertEquals(Security(), SecurityRules.fromStored { null })
        assertEquals(Security(), SecurityRules.fromStored { "garbage" })
    }

    // ---------------------------------------------------- lock session ----

    @Test
    fun `a fresh process starts locked when the app lock is on, and open when it is off`() {
        val session = LockSession()
        assertTrue(session.locked(Security(appLock = true)))
        assertFalse(session.locked(Security()))
    }

    @Test
    fun `it locks again only after the chosen time away`() {
        val s = Security(appLock = true, relockAfter = RelockAfter.ONE_MINUTE)
        val session = LockSession().apply { unlock() }
        session.left(1_000)
        session.returned(1_000 + 59_999, s)
        assertFalse(session.locked(s))
        session.left(100_000)
        session.returned(100_000 + 60_000, s)
        assertTrue(session.locked(s))
    }

    @Test
    fun `straight away locks on any time out of sight`() {
        val s = Security(appLock = true, relockAfter = RelockAfter.NOW)
        val session = LockSession().apply { unlock() }
        session.left(5)
        session.returned(5, s)
        assertTrue(session.locked(s))
    }

    @Test
    fun `a clock that goes backwards locks`() {
        val s = Security(appLock = true, relockAfter = RelockAfter.FIFTEEN_MINUTES)
        val session = LockSession().apply { unlock() }
        session.left(10_000)
        session.returned(5_000, s)
        assertTrue(session.locked(s))
    }

    @Test
    fun `the PIN screen during a confirmed check does not count as away, in either order`() {
        val s = Security(appLock = true, relockAfter = RelockAfter.NOW)
        // Activity comes back before the success arrives.
        val a = LockSession()
        a.beginCheck()
        a.left(1_000)
        a.returned(4_000, s)
        a.endCheck(CheckOutcome.CONFIRMED, 4_001, s)
        a.unlock()
        assertFalse(a.locked(s))
        // Success arrives before the activity comes back.
        val b = LockSession()
        b.beginCheck()
        b.left(1_000)
        b.endCheck(CheckOutcome.CONFIRMED, 4_000, s)
        b.unlock()
        b.returned(4_001, s)
        assertFalse(b.locked(s))
    }

    @Test
    fun `leaving during a check that was not confirmed counts from when they left`() {
        val s = Security(appLock = true, relockAfter = RelockAfter.ONE_MINUTE)
        val session = LockSession().apply { unlock() }
        session.beginCheck()
        session.left(1_000)
        session.endCheck(CheckOutcome.CANCELLED, 1_500, s)
        session.returned(1_000 + 60_000, s)
        assertTrue(session.locked(s))
    }

    @Test
    fun `private lists hide again when the app relocks, even with the app lock off`() {
        val s = Security(privateLists = true, relockAfter = RelockAfter.ONE_MINUTE)
        val session = LockSession()
        assertTrue(session.privateHidden(s))
        session.showPrivate()
        assertFalse(session.privateHidden(s))
        session.left(0)
        session.returned(30_000, s)
        assertFalse(session.privateHidden(s))
        session.left(100_000)
        session.returned(200_000, s)
        assertTrue(session.privateHidden(s))
        assertFalse(session.privateHidden(Security()))
    }

    @Test
    fun `turning the lock on keeps the owner in`() {
        val session = LockSession()
        session.lockTurnedOn()
        assertFalse(session.locked(Security(appLock = true)))
    }

    @Test
    fun `screenshots are blocked while App lock or hidden lists is on, and only then`() {
        assertFalse("defaults block nothing", SecurityRules.blockScreenCapture(Security()))
        assertTrue(SecurityRules.blockScreenCapture(Security(appLock = true)))
        assertTrue(SecurityRules.blockScreenCapture(Security(privateLists = true)))
        assertTrue(SecurityRules.blockScreenCapture(Security(appLock = true, privateLists = true)))
        // The other settings are about approvals and how to check, not about
        // what is on screen: on their own they block nothing.
        assertFalse(SecurityRules.blockScreenCapture(Security(approvals = ApprovalCheck.EVERY)))
        assertFalse(SecurityRules.blockScreenCapture(Security(method = CheckMethod.FINGERPRINT_ONLY)))
        assertFalse(SecurityRules.blockScreenCapture(Security(relockAfter = RelockAfter.NOW)))
        // Whether the app is locked right now does not matter: the rule is
        // the setting, so an unlocked, in-use Jarvis is covered too.
        val session = LockSession()
        session.lockTurnedOn()
        val on = Security(appLock = true)
        assertFalse(session.locked(on))
        assertTrue(SecurityRules.blockScreenCapture(on))
    }
}
