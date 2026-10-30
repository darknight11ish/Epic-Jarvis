package com.jarvis.client

import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.Risk
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * THE OWNER'S RULING OF 2026-10-30, PINNED: *"if there is anything that needs
 * approval for Jarvis on desktop with the Windows Hello PIN as well, make the
 * Android app require a fingerprint to approve the same card - but I can
 * approve the same level of card on Android as well."*
 *
 * Two halves, and this file holds both to the PC's own answers:
 *
 *  1. **The same cards.** The desktop's Windows Hello covers exactly
 *     `jarvis_owner_check.is_risky`'s set. `contract/risky-approval-cases.json`
 *     is written by `tools/gen_risky_approval_cases.py` from that function, and
 *     `RiskyApprovalContractTest` already holds [SecurityRules.riskyByToday] to
 *     it. Here the CARD's line is held to it too, so the sentence a person
 *     reads and the check that runs can never describe different cards.
 *  2. **The same level.** Every one of those cards can be approved on this
 *     phone - the line appears on all of them, and an approval only goes out
 *     after a confirmed check (`SecurityRules.approvalNeedsCheck`, the gate in
 *     `MainActivity.approveItem`, and `BiometricGate`). No card is refused here
 *     for being "too risky to answer on the phone"; the only ones with no
 *     Approve at all are the PC-only ceremonies, which is a decision about
 *     WHERE, not about how much checking.
 *
 * The sentence itself is checked to be plain words: it names the fingerprint,
 * it says "or PIN" only when this phone's method really offers the PIN, and it
 * says nothing that only a developer would know.
 */
class ApproveAsksFingerprintTest {

    /** The PC's own rows and answers, the same file the other two suites read. */
    private val cases: List<JsonObject> = run {
        val text = requireNotNull(
            javaClass.classLoader?.getResource("contract/risky-approval-cases.json"),
        ) {
            "contract/risky-approval-cases.json is missing - run " +
                "python3 tools/gen_risky_approval_cases.py"
        }.readText()
        ((JarvisJson.parseToJsonElement(text) as JsonObject)["cases"] as JsonArray).map { it.jsonObject }
    }

    private fun items(): List<Triple<String, PendingItem, Boolean>> = cases.map { case ->
        val name = case["name"]!!.jsonPrimitive.content
        val risky = case["risky"]!!.jsonPrimitive.boolean
        Triple(name, decodePendingRows(listOf(case["row"]!!)).items.single(), risky)
    }

    // ------------------------------------------------- the same cards ----

    @Test
    fun `exactly the cards the desktop asks Windows Hello for show the line`() {
        assertTrue(cases.size >= 10)
        for ((name, item, risky) in items()) {
            val words = SecurityRules.approveCheckWords(Security(), item)
            if (risky) {
                assertNotNull("$name is a Windows Hello card on the PC, so its Approve " +
                    "must say a check is coming", words)
            } else {
                assertNull("$name is not a Windows Hello card on the PC, so the phone " +
                    "must not claim a check it will not run", words)
            }
        }
    }

    @Test
    fun `the line and the check are one decision, never two`() {
        // The invariant behind the sentence: it is drawn if and only if
        // pressing Approve will really run the check. Written as
        // `approveCheckWords(s, i) != null == approvalNeedsCheck(s, i)` over
        // every combination of the settings, so a future edit to either half
        // that leaves the other behind fails here.
        for (s in listOf(
            Security(),
            Security(approvals = ApprovalCheck.EVERY),
            Security(method = CheckMethod.FINGERPRINT_ONLY),
            Security(approvals = ApprovalCheck.EVERY, method = CheckMethod.FINGERPRINT_ONLY),
        )) {
            for ((name, item, _) in items()) {
                assertEquals(
                    "$name under ${s.approvals}/${s.method}",
                    SecurityRules.approvalNeedsCheck(s, item),
                    SecurityRules.approveCheckWords(s, item) != null,
                )
            }
        }
    }

    @Test
    fun `every approval asks on every card once the owner chooses that`() {
        // The owner can already be stricter than "risky only"; the new line
        // follows that setting rather than re-deriving its own list.
        val every = Security(approvals = ApprovalCheck.EVERY)
        val safe = PendingItem(
            id = "safe",
            risk = Risk(reversible = "yes", reach = "local", classified = true),
        )
        assertNull(SecurityRules.approveCheckWords(Security(), safe))
        assertNotNull(SecurityRules.approveCheckWords(every, safe))
    }

    // ------------------------------------------------- the same level ----

    @Test
    fun `no risky card is refused on the phone for being too risky to answer`() {
        // The other half of the ruling: these are cards the owner MAY answer
        // here. Approve is drawn unless the card is one of the PC's own
        // ceremonies (`item.pcOnly` - a decision about WHERE it can happen, not
        // about how much checking) or a proposal that needs a named plan
        // (`item.needsChoice`, which the PC's decide route cannot carry yet).
        // Neither is the risk level refusing the phone.
        for ((name, item, risky) in items()) {
            if (!risky) continue
            assertTrue("$name would not even draw an Approve button here", !item.pcOnly)
            assertTrue("$name would not even draw an Approve button here", !item.needsChoice)
        }
    }

    // ------------------------------------------------- plain words ----

    @Test
    fun `the line names the fingerprint, and says PIN only when the PIN is allowed`() {
        val item = PendingItem(
            id = "x",
            risk = Risk(reversible = "no", reach = "outbound", classified = true),
        )
        val orPin = SecurityRules.approveCheckWords(Security(), item)
        assertEquals(SecurityRules.APPROVE_ASKS_FINGERPRINT_OR_PIN, orPin)
        assertTrue(orPin!!, "fingerprint" in orPin && "PIN" in orPin)

        val only = SecurityRules.approveCheckWords(
            Security(method = CheckMethod.FINGERPRINT_ONLY),
            item,
        )
        assertEquals(SecurityRules.APPROVE_ASKS_FINGERPRINT, only)
        // "Fingerprint only" means the PIN is not offered - promising it would
        // send the owner looking for an option that is not on the prompt.
        assertFalse(only!!, "PIN" in only)
    }

    @Test
    fun `the line reads as a sentence for the owner, not as a developer note`() {
        for (words in listOf(
            SecurityRules.APPROVE_ASKS_FINGERPRINT,
            SecurityRules.APPROVE_ASKS_FINGERPRINT_OR_PIN,
        )) {
            assertTrue(words, words.startsWith("Approve asks for your "))
            assertTrue(words, words.endsWith("."))
            // One short line under the buttons: it has to fit on a phone.
            assertTrue(words, words.length <= 48)
            for (jargon in listOf(
                "biometric", "BIOMETRIC", "authenticator", "CryptoObject",
                "Keystore", "API", "null", "error",
            )) {
                assertFalse("$words must not say \"$jargon\"", jargon in words)
            }
        }
    }
}
