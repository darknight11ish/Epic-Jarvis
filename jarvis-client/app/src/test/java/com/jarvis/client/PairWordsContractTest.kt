package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Pairing
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's pairing sentences are the PC's (`backend/jarvis_devices.py`
 * PHONE_WORDS, written into contract/pairing-cases.json by
 * tools/gen_pairing_cases.py). Two of the PC's are not the phone's:
 * "this_pc" (the phone is never the PC) and "collect_gone" (the phone says
 * which of the two it was, TIMED_OUT or CANCELLED).
 */
class PairWordsContractTest {

    private val phone: JsonObject by lazy {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/pairing-cases.json")) {
            "contract/pairing-cases.json is missing - run tools/gen_pairing_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["sentences"]!!.jsonObject["phone"]!!.jsonObject
    }

    private fun pc(key: String): String = phone[key]!!.jsonPrimitive.content

    @Test
    fun `every sentence the phone shows is the PC's own`() {
        assertEquals(pc("not_mesh"), Pairing.NOT_MESH)
        assertEquals(pc("gone"), Pairing.GONE)
        assertEquals(pc("name"), Pairing.BAD_NAME)
        assertEquals(pc("bad_request"), Pairing.BAD_REQUEST)
        assertEquals(pc("card"), Pairing.NO_CARD)
        assertEquals(pc("words_differ"), Pairing.WORDS_DIFFER)
        assertEquals(pc("waiting"), Pairing.APPROVE_IF_SAME)
        assertEquals(pc("denied"), Pairing.DENIED)
        assertEquals(pc("qr_invalid"), Pairing.NOT_A_CODE)
        assertEquals(pc("qr_newer"), Pairing.NEWER_CODE)
        assertEquals(pc("code_invalid"), Pairing.BAD_TYPED_CODE)
        assertEquals(pc("camera"), Pairing.CAMERA_WHY)
        assertEquals(pc("claimed"), Pairing.CLAIMED_ALREADY)
    }

    @Test
    fun `the wrong-code sentences match for every count`() {
        assertEquals(pc("wrong_proof").replace("{n}", "2"), Pairing.wrongCode(2))
        assertEquals(pc("wrong_proof_one"), Pairing.wrongCode(1))
        assertEquals(pc("wrong_proof_none"), Pairing.wrongCode(0))
    }

    @Test
    fun `a second claim says another device used the code, and is final`() {
        val body = JsonObject(
            mapOf(
                "ok" to JsonPrimitive(false),
                "reason" to JsonPrimitive("wrong_proof"),
                "tries_left" to JsonPrimitive(2),
                "claimed" to JsonPrimitive(true),
            ),
        )
        val got = Pairing.readClaim(403, body)
        assertTrue(got is Pairing.Claimed.Refused)
        got as Pairing.Claimed.Refused
        assertEquals(Pairing.CLAIMED_ALREADY, got.message)
        assertTrue(got.final)

        val plain = Pairing.readClaim(
            403,
            JsonObject(mapOf("reason" to JsonPrimitive("wrong_proof"), "tries_left" to JsonPrimitive(2))),
        ) as Pairing.Claimed.Refused
        assertEquals(Pairing.wrongCode(2), plain.message)
        assertFalse(plain.final)
    }
}
