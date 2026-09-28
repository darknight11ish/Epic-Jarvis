package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PairAttempt
import com.jarvis.client.net.PairTransport
import com.jarvis.client.net.Pairing
import com.jarvis.client.net.PairingFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The claim / collect exchange (docs/PAIRING-DESIGN.md §6.2) against a fake
 * PC that does its half of the sums. The sums themselves are pinned by
 * [PairProofTest]'s vectors; this checks what the phone does with each
 * answer: it refuses a PC that cannot prove itself or sends other words,
 * never takes a key before the card is approved, and hands it over once.
 */
class PairFlowTest {

    private val words = List(1296) { "w$it" }
    private val secret = ByteArray(16) { it.toByte() }
    private val pcNonce = Pairing.b64u(ByteArray(16) { (0x20 + it).toByte() })
    private val pairId = "00112233445566ff"
    private val key = "jdk1.d3f9a1c2e." + "k".repeat(43)

    private val qr = (Pairing.parseQr(
        "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/$pairId/AAECAwQFBgcICQoLDA0ODw/1790000600",
    ) as Pairing.Parsed.Ok).target

    /** What the fake PC does with a claim, and then with each collect in turn. */
    private inner class FakePc(
        val tamperProof: Boolean = false,
        val tamperWords: Boolean = false,
        val claimAnswer: Pair<Int, String>? = null,
        val collects: List<Pair<Int, String>> = listOf(202 to """{"state":"waiting_for_card"}"""),
    ) : PairTransport {
        val bodies = mutableListOf<String>()
        var collectCount = 0

        override suspend fun post(base: String, path: String, json: String): Pair<Int, JsonObject?> {
            bodies += json
            assertEquals("http://jarvis-pc.tail1234.ts.net:4719", base)
            val body = JarvisJson.parseToJsonElement(json) as JsonObject
            if (path == Pairing.CLAIM_PATH) {
                claimAnswer?.let { return it.first to (JarvisJson.parseToJsonElement(it.second) as JsonObject) }
                val nonce = body["phone_nonce"]!!.jsonPrimitive.content
                val name = body["name"]!!.jsonPrimitive.content
                val t = Pairing.transcript("qr", pairId, nonce, name)
                // The PC checks the phone's proof, as the backend will.
                assertEquals(Pairing.claimProof(secret, t), body["proof"]!!.jsonPrimitive.content)
                val proof = if (tamperProof) Pairing.pcProof(ByteArray(16), t, pcNonce) else Pairing.pcProof(secret, t, pcNonce)
                var w = Pairing.wordNumbers(secret, t, pcNonce).map { words[it] }
                if (tamperWords) w = w.reversed()
                val wordsJson = w.joinToString(",") { "\"$it\"" }
                return 202 to JarvisJson.parseToJsonElement(
                    """{"state":"waiting_for_card","pair_id":"$pairId","pc_nonce":"$pcNonce",""" +
                        """"pc_proof":"$proof","words":[$wordsJson],"expires_in":600}""",
                ) as JsonObject
            }
            assertEquals(Pairing.COLLECT_PATH, path)
            assertEquals(pairId, body["pair_id"]!!.jsonPrimitive.content)
            val nonce = (JarvisJson.parseToJsonElement(bodies.first()) as JsonObject)["phone_nonce"]!!.jsonPrimitive.content
            assertEquals(Pairing.collectProof(secret, pairId, nonce), body["proof"]!!.jsonPrimitive.content)
            val answer = collects[minOf(collectCount, collects.size - 1)]
            collectCount += 1
            return answer.first to (JarvisJson.parseToJsonElement(answer.second) as JsonObject)
        }
    }

    @Test
    fun `a PC that proves itself and agrees on the words`() = runBlocking {
        val pc = FakePc()
        val attempt = PairAttempt(qr, "Pixel 9", pc)
        val c = attempt.claim(words) as Pairing.Claimed.CardUp
        assertEquals(4, c.words.size)
        assertTrue("never the secret on the wire", pc.bodies.none { "AAECAwQFBgcICQoLDA0ODw" in it })
        assertEquals(Pairing.Collected.Waiting, attempt.collect())
    }

    @Test
    fun `a PC that cannot prove itself is refused`() = runBlocking {
        val c = PairAttempt(qr, "Pixel 9", FakePc(tamperProof = true)).claim(words)
        assertEquals(Pairing.Claimed.Refused(Pairing.NOT_THE_PC), c)
    }

    @Test
    fun `different words are refused`() = runBlocking {
        val c = PairAttempt(qr, "Pixel 9", FakePc(tamperWords = true)).claim(words)
        assertEquals(Pairing.Claimed.Refused(Pairing.WORDS_DIFFER), c)
    }

    @Test
    fun `each refusal in the design's table has its words`() = runBlocking {
        fun claimWith(code: Int, body: String) =
            runBlocking { PairAttempt(qr, "Pixel 9", FakePc(claimAnswer = code to body)).claim(words) }
        assertEquals(
            Pairing.Claimed.Refused("That code is not right. 2 tries left.", final = false),
            claimWith(403, """{"reason":"wrong_proof","tries_left":2}"""),
        )
        assertEquals(Pairing.Claimed.Refused(Pairing.NOT_MESH), claimWith(403, """{"reason":"not_mesh"}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.GONE), claimWith(410, """{"reason":"gone","state":"burnt"}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.BAD_NAME), claimWith(400, """{"reason":"name"}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.NO_CARD), claimWith(503, """{"reason":"card"}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.NO_PAIRING_HERE), claimWith(404, """{}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.BAD_REQUEST), claimWith(202, """{"state":"waiting_for_card"}"""))
        assertEquals(Pairing.Claimed.Refused(Pairing.NO_ANSWER), Pairing.readClaim(0, null))
    }

    @Test
    fun `collect answers`() {
        fun read(code: Int, body: String) = Pairing.readCollect(code, JarvisJson.parseToJsonElement(body) as JsonObject)
        assertEquals(Pairing.Collected.Waiting, read(202, """{"state":"waiting_for_card","expires_in":500}"""))
        assertEquals(
            Pairing.Collected.Approved("d3f9a1c2e", key),
            read(200, """{"state":"approved","device_id":"d3f9a1c2e","token":"$key"}"""),
        )
        // A key of the wrong shape, or for another id, is not taken.
        assertEquals(Pairing.Collected.Ended(Pairing.BAD_KEY), read(200, """{"device_id":"d3f9a1c2e","token":"short"}"""))
        assertEquals(Pairing.Collected.Ended(Pairing.BAD_KEY), read(200, """{"device_id":"d00000000","token":"$key"}"""))
        assertEquals(Pairing.Collected.Ended(Pairing.DENIED), read(403, """{"state":"denied"}"""))
        assertEquals(Pairing.Collected.Ended(Pairing.TIMED_OUT), read(410, """{"state":"timed_out"}"""))
        assertEquals(Pairing.Collected.Ended(Pairing.CANCELLED), read(410, """{"state":"cancelled"}"""))
        assertEquals(Pairing.Collected.Ended(Pairing.GONE), read(410, """{"state":"used"}"""))
        assertEquals(Pairing.Collected.NoAnswer, Pairing.readCollect(0, null))
    }

    @Test
    fun `the flow hands the key over once, after the card is approved`() = runBlocking {
        val pc = FakePc(
            collects = listOf(
                202 to """{"state":"waiting_for_card"}""",
                200 to """{"state":"approved","device_id":"d3f9a1c2e","token":"$key"}""",
            ),
        )
        val flow = PairingFlow(this, pc, { words }, everyMs = 1L)
        flow.start(qr, "Pixel 9")
        val done = withTimeout(5_000) {
            flow.state.first { it is PairingFlow.State.Approved || it is PairingFlow.State.Ended }
        }
        assertTrue(done is PairingFlow.State.Approved)
        assertEquals(2, pc.collectCount)
        assertEquals("jarvis-pc.tail1234.ts.net:4719" to key, flow.takeKey())
        assertNull("given once", flow.takeKey())
        assertEquals(PairingFlow.State.Idle, flow.state.value)
    }

    @Test
    fun `a denied card ends the flow with nothing to take`() = runBlocking {
        val pc = FakePc(collects = listOf(403 to """{"state":"denied"}"""))
        val flow = PairingFlow(this, pc, { words }, everyMs = 1L)
        flow.start(qr, "Pixel 9")
        val done = withTimeout(5_000) {
            flow.state.first { it is PairingFlow.State.Approved || it is PairingFlow.State.Ended }
        }
        assertEquals(PairingFlow.State.Ended(Pairing.DENIED), done)
        assertNull(flow.takeKey())
    }

    @Test
    fun `different words end the flow before any collect`() = runBlocking {
        val pc = FakePc(tamperWords = true)
        val flow = PairingFlow(this, pc, { words }, everyMs = 1L)
        flow.start(qr, "Pixel 9")
        val done = withTimeout(5_000) { flow.state.first { it is PairingFlow.State.Ended } }
        assertEquals(PairingFlow.State.Ended(Pairing.WORDS_DIFFER), done)
        assertEquals(0, pc.collectCount)
    }

    @Test
    fun `a bad name never reaches the PC`() = runBlocking {
        val pc = FakePc()
        val flow = PairingFlow(this, pc, { words }, everyMs = 1L)
        flow.start(qr, "bad\nname")
        assertEquals(PairingFlow.State.Ended(Pairing.BAD_NAME), flow.state.value)
        assertFalse(pc.bodies.isNotEmpty())
    }
}
