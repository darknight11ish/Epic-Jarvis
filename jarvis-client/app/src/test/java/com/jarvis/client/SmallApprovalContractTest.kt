package com.jarvis.client

import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * THE OWNER'S REQUEST OF 2026-11-01, PINNED TO THE PC'S OWN ANSWERS: *"for small
 * approvals like asking jarvis to search the web (for things like weather or the
 * news or anything small) i would like to only have to approve the card, not
 * necessarily use my fingerprint on top of approving the card."*
 *
 * The rule is [SecurityRules.isSmall]: an action on an explicit read-only list,
 * whose own risk row says it changes nothing. The PC decides the same question
 * in `jarvis_owner_check.is_small`, and `contract/risky-approval-cases.json` is
 * written by `tools/gen_risky_approval_cases.py` from THAT function - so this
 * file holds the phone's copy to the PC's answer for every row, the way
 * `RiskyApprovalContractTest` holds the risky half.
 *
 * What the split is:
 *
 *   risky + small      a web search, a page, the news, public GitHub data, the
 *                      catalog: they leave the PC, so they are risky - and they
 *                      are reads, so the card's own yes is enough.
 *   risky, not small   anything unclassified, irreversible, rushed, or that
 *                      writes / spends / sends / deletes / changes a device, an
 *                      account or a permission: still asks, exactly as before.
 *   not risky, small   the local reads (calendar, mail, notes, home status):
 *                      they never asked on the phone, and they are small too.
 *
 * The near-miss rows are the point of the fixture: a small ACTION with a risk
 * row saying "no undo", "not classified" or "rushed" is NOT small, so the list
 * alone can never make an unsafe card skip the check.
 */
class SmallApprovalContractTest {

    /** The PC's own rows and answers, the same file the other suites read. */
    private val cases: List<JsonObject> = run {
        val text = requireNotNull(
            javaClass.classLoader?.getResource("contract/risky-approval-cases.json"),
        ) {
            "contract/risky-approval-cases.json is missing - run " +
                "python3 tools/gen_risky_approval_cases.py"
        }.readText()
        ((JarvisJson.parseToJsonElement(text) as JsonObject)["cases"] as JsonArray).map { it.jsonObject }
    }

    private data class Case(val name: String, val item: PendingItem, val risky: Boolean, val small: Boolean)

    private fun items(): List<Case> = cases.map { case ->
        Case(
            name = case["name"]!!.jsonPrimitive.content,
            item = decodePendingRows(listOf(case["row"]!!)).items.single(),
            risky = case["risky"]!!.jsonPrimitive.boolean,
            small = case["small"]!!.jsonPrimitive.boolean,
        )
    }

    @Test
    fun `the phone's answer is the PC's answer for every card`() {
        assertTrue(cases.size >= 10)
        for (c in items()) {
            assertEquals("${c.name}: isSmall disagrees with the PC", c.small, SecurityRules.isSmall(c.item))
            // The risky half is unchanged by this feature, and still held here
            // so a row can never be made small by making it non-risky.
            assertEquals("${c.name}: riskyByToday disagrees with the PC", c.risky, SecurityRules.riskyByToday(c.item))
        }
    }

    @Test
    fun `the fixture really holds all three kinds of card`() {
        val all = items()
        assertTrue("no risky-and-small card in the contract",
            all.any { it.risky && it.small })
        assertTrue("no risky card that still asks",
            all.any { it.risky && !it.small })
        assertTrue("no local read that is small without being risky",
            all.any { !it.risky && it.small })
        assertTrue("no card that is neither", all.any { !it.risky && !it.small })
        // The owner's own example must be in the small set.
        assertTrue("search_the_web is not in the contract as a small card",
            all.any { it.small && it.item.action == "search_the_web" })
    }

    @Test
    fun `the default leaves the small cards alone and keeps every other check`() {
        val shopping = Security()
        for (c in items()) {
            assertEquals("${c.name} under the default",
                c.risky && !c.small, SecurityRules.approvalNeedsCheck(shopping, c.item))
        }
        // Choosing today's rule back puts the check on every risky card again,
        // the small ones included - the way back the owner asked for.
        val today = Security(approvals = ApprovalCheck.RISKY)
        for (c in items()) {
            assertEquals("${c.name} under Risky only", c.risky,
                SecurityRules.approvalNeedsCheck(today, c.item))
        }
    }

    @Test
    fun `a small card is never signed, and everything else that asks still is`() {
        val shopping = Security()
        for (c in items()) {
            if (!c.risky) {
                assertFalse("${c.name} never needed a signature", SecurityRules.approveTakesSignedPath(shopping, c.item))
                continue
            }
            assertEquals(
                "${c.name}: only a card that asks may take the signed path",
                !c.small,
                SecurityRules.approveTakesSignedPath(shopping, c.item),
            )
        }
    }

    @Test
    fun `the phone's own words say what small means without naming every action`() {
        // The Settings sentence under the three choices, from SecurityScreen's
        // own source: it must name the read-only shape and the card-only
        // approval, because a person choosing between three radios reads that.
        val screen = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SecurityScreen.kt")
        assertTrue("the Security screen does not explain the small choice",
            screen.contains("approved by the card alone"))
        assertTrue("the small choice's label is not drawn from ApprovalCheck",
            screen.contains("options = ApprovalCheck.entries"))
        assertEquals("Small cards", ApprovalCheck.SMALL.label)
        assertEquals("small", ApprovalCheck.SMALL.wire)
    }

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun repoFile(rel: String): String {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = java.io.File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        throw AssertionError("could not find $rel from ${System.getProperty("user.dir")}")
    }
}
