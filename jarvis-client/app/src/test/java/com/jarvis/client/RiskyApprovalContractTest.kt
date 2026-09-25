package com.jarvis.client

import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Which approvals are risky - one rule, in three places.
 *
 * `contract/risky-approval-cases.json` is written by
 * tools/gen_risky_approval_cases.py: each `/api/pending` row with the
 * backend's own answer (`jarvis_owner_check.is_risky`), the same file the
 * desktop's `lock/rules.rs` test reads. Since the approval gap's step 1 the
 * PC's backend asks Windows Hello itself for a risky approval made on the
 * PC, by that rule; this phone asks its fingerprint for its own approvals,
 * by [SecurityRules.riskyByToday]. They must not disagree about which cards
 * those are.
 */
class RiskyApprovalContractTest {

    private val cases: List<JsonObject> = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/risky-approval-cases.json")) {
            "contract/risky-approval-cases.json is missing - run python3 tools/gen_risky_approval_cases.py"
        }.readText()
        ((JarvisJson.parseToJsonElement(text) as JsonObject)["cases"] as JsonArray).map { it.jsonObject }
    }

    @Test
    fun `the phone and the backend agree on every row`() {
        assertTrue(cases.size >= 10)
        for (case in cases) {
            val name = case["name"]!!.jsonPrimitive.content
            val read = decodePendingRows(listOf(case["row"]!!))
            assertEquals(name, 1, read.items.size)
            assertEquals(name, case["risky"]!!.jsonPrimitive.boolean, SecurityRules.riskyByToday(read.items[0]))
        }
    }

    @Test
    fun `the fingerprint prompt says what the PC's Windows Hello prompt says`() {
        // Where the row carries the gate's notice: its title, then why. (With
        // no notice the phone names the action in words, the PC by its name.)
        for (case in cases.filter { (it["row"] as JsonObject).containsKey("notice") }) {
            val item = decodePendingRows(listOf(case["row"]!!)).items.single()
            val why = item.risk.why.ifBlank { "Check the card before you confirm." }
            assertEquals(case["name"]!!.jsonPrimitive.content, case["message"]!!.jsonPrimitive.content, "${item.title}\n$why")
        }
    }
}
