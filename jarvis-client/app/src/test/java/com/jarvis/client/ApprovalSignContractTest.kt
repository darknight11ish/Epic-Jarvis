package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.SignedApproval
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's half of the signed-approval rule, checked against the file the
 * PC writes (`backend/jarvis_devices.py` through
 * `tools/gen_approval_sign_cases.py`): for every case, the card as the PC
 * sends it, read by the phone's own row reader, hashes to the PC's
 * `words_sha256` - and the bytes that are signed are the PC's.
 */
class ApprovalSignContractTest {

    private val doc: JsonObject by lazy {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/approval-sign-cases.json")) {
            "contract/approval-sign-cases.json is missing - run tools/gen_approval_sign_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun text(o: JsonObject, key: String): String = o[key]!!.jsonPrimitive.content

    @Test
    fun everyCardHashesTheWayThePcHashesIt() {
        val cases = doc["words_hash"] as JsonArray
        assertTrue("the file has cases", cases.size >= 10)
        for (c in cases) {
            val case = c.jsonObject
            val name = text(case, "name")
            val read = decodePendingRows(listOf(case["row"]!!))
            assertEquals(name, 0, read.skipped)
            val item = read.items.single()
            assertEquals("$name: id", text(case, "id"), item.id)
            assertEquals("$name: title", text(case, "title"), item.title)
            assertEquals("$name: text", text(case, "text"), item.signText)
            assertEquals("$name: hash", text(case, "words_sha256"), SignedApproval.wordsSha256(item))
        }
    }

    @Test
    fun theSignedBytesArePcsBytes() {
        val message = doc["message"]!!.jsonObject
        val nonce = text(message, "nonce")
        val id = text(message, "id")
        val action = text(message, "action")
        val words = text(message, "words_sha256")
        val expected = text(message, "hex")
        val mine = SignedApproval.signedMessage(id, action, nonce, words)
        assertEquals(expected, mine.joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') })
    }
}
