package com.jarvis.client

import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.Risk
import com.jarvis.client.net.SignedApproval
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

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
 *
 * DEF-022 (fixed 2026-10-31) added the second half this file had been missing:
 * a risky card's Approve does NOT always ask for the prompt. `SignedApproval
 * .pathFor` sends it down the OFFER path when signed approvals are off, need
 * turning on again, or are waiting for the PC's yes - and that path shows the
 * offer notice instead. So `approveCheckWords` now takes the signed state, and
 * the test below holds every state to what the press really does - and pins
 * the card/screen/app wiring that carries that state to the sentence.
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
            SecurityRules.APPROVE_ASKS_SIGNED_OFF,
            SecurityRules.APPROVE_ASKS_SIGNED_AGAIN,
            SecurityRules.APPROVE_ASKS_SIGNED_WAITING,
        )) {
            assertTrue(words, words.startsWith("Approve asks"))
            assertTrue(words, words.endsWith("."))
            // A line under the buttons, not an essay: the prompt lines are one
            // short sentence, and the turn-signing-on ones carry their reason.
            assertTrue(words, words.length <= 140)
            for (jargon in listOf(
                "biometric", "BIOMETRIC", "authenticator", "CryptoObject",
                "Keystore", "API", "null", "error",
            )) {
                assertFalse("$words must not say \"$jargon\"", jargon in words)
            }
        }
    }

    // ------------------------------------------- the signed-approval states ----
    // DEF-022: a risky card's Approve does not always ask for the prompt.
    // [SignedApproval.pathFor] decides, and the sentence below the buttons must
    // describe that same decision. This is the half the register's own test
    // asked for: the three signed-approval states crossed with a risky item.
    // It fails on the pre-fix code, where every risky state got the prompt line.

    private fun riskyItem(): PendingItem = PendingItem(
        id = "def022",
        risk = Risk(reversible = "no", reach = "outbound", classified = true),
    )

    private fun assertPrompt(words: String?) {
        assertEquals(SecurityRules.APPROVE_ASKS_FINGERPRINT_OR_PIN, words)
    }

    @Test
    fun `the sentence matches what Approve really does, on every signed-approval state`() {
        val item = riskyItem()
        for (state in SignedApproval.State.entries.toList() + null) {
            val path = SignedApproval.pathFor(risky = true, state = state)
            val words = SecurityRules.approveCheckWords(Security(), item, state)
            val why = "state=$state path=$path words=$words"
            when (path) {
                // The offer path shows NO fingerprint prompt: Approve's press
                // answers from `SignedApproval.noticeFor` and sends nothing.
                SignedApproval.Path.OFFER -> assertEquals(why, SecurityRules.APPROVE_ASKS_SIGNED_OFF, words)
                SignedApproval.Path.OFFER_AGAIN -> assertEquals(why, SecurityRules.APPROVE_ASKS_SIGNED_AGAIN, words)
                SignedApproval.Path.WAITING -> assertEquals(why, SecurityRules.APPROVE_ASKS_SIGNED_WAITING, words)
                // These really do run this phone's check: the SIGNED path with
                // the key, the PLAIN path through `confirmed()`.
                SignedApproval.Path.SIGNED, SignedApproval.Path.PLAIN -> assertPrompt(words)
            }
            if (path == SignedApproval.Path.OFFER) {
                assertNotEquals(why, SecurityRules.APPROVE_ASKS_FINGERPRINT_OR_PIN, words)
                assertNotEquals(why, SecurityRules.APPROVE_ASKS_FINGERPRINT, words)
                assertTrue("$why must say signing needs turning on once", words!!.contains("once they are on"))
            }
        }
    }

    @Test
    fun `a signed-approval state only changes a risky card's line`() {
        val safe = PendingItem(
            id = "safe",
            risk = Risk(reversible = "yes", reach = "local", classified = true),
        )
        // Not risky, and not "every card": no line at all, whatever the state.
        for (state in SignedApproval.State.entries) {
            assertNull(SecurityRules.approveCheckWords(Security(), safe, state))
        }
        // Risky, but the owner asked for EVERY card to be checked: the local
        // check runs on the PLAIN path, so the state cannot change the sentence.
        for (state in SignedApproval.State.entries) {
            assertEquals(
                SecurityRules.APPROVE_ASKS_FINGERPRINT_OR_PIN,
                SecurityRules.approveCheckWords(
                    Security(approvals = ApprovalCheck.EVERY),
                    safe,
                    state,
                ),
            )
        }
        // The method still decides which prompt is named, when a prompt runs.
        assertEquals(
            SecurityRules.APPROVE_ASKS_FINGERPRINT,
            SecurityRules.approveCheckWords(
                Security(method = CheckMethod.FINGERPRINT_ONLY),
                riskyItem(),
                SignedApproval.State.ON,
            ),
        )
    }

    @Test
    fun `the signed-approval state really reaches the card's line`() {
        // The rule above is only worth anything if the card is handed the
        // state: pin the three links of the chain (read -> state -> card).
        val main = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("the app does not read the signed-approval state for the card",
            main.contains("signedApprovals = signedApprovals,"))
        assertTrue(main.contains("JarvisRuntime.signedApprovalRead()?.state"))
        val home = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt")
        assertTrue("HomeState does not carry the signed-approval state",
            home.contains("val signedApprovals: com.jarvis.client.net.SignedApproval.State? = null"))
        assertTrue("a card is not handed the signed-approval state",
            home.contains("signedApprovals = state.signedApprovals,"))
        val card = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt")
        assertTrue("the card's sentence ignores the signed-approval state",
            card.contains("SecurityRules.approveCheckWords(security, item, signedApprovals)"))
    }

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun repoFile(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
