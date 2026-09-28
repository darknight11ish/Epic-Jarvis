package com.jarvis.client

import com.jarvis.client.data.PairWords
import com.jarvis.client.net.Pairing
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The sums, checked against docs/PAIRING-DESIGN.md §6.2's own test vectors
 * (worked out for the design with Python's hmac): secret bytes 00..0f,
 * pair_id 00112233445566ff, phone_nonce bytes 10..1f, pc_nonce bytes 20..2f,
 * name "Pixel 9".
 */
class PairProofTest {

    private val secret = ByteArray(16) { it.toByte() }
    private val phoneNonce = Pairing.b64u(ByteArray(16) { (0x10 + it).toByte() })
    private val pcNonce = Pairing.b64u(ByteArray(16) { (0x20 + it).toByte() })
    private val pairId = "00112233445566ff"
    private val name = "Pixel 9"

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    @Test
    fun `base64url without padding`() {
        assertEquals("AAECAwQFBgcICQoLDA0ODw", Pairing.b64u(secret))
        assertEquals("EBESExQVFhcYGRobHB0eHw", phoneNonce)
        assertEquals("ICEiIyQlJicoKSorLC0uLw", pcNonce)
    }

    @Test
    fun `method qr`() {
        val t = Pairing.transcript("qr", pairId, phoneNonce, name)
        assertEquals("H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c", Pairing.claimProof(secret, t))
        assertEquals("HkPzmveXlM4XdYo_7TECbY7y3HF1Q4mIXmSxVXxDM80", Pairing.pcProof(secret, t, pcNonce))
        assertEquals(listOf(330, 679, 1036, 970), Pairing.wordNumbers(secret, t, pcNonce))
        assertEquals("xqsJqE1r6hkgKSjlXeofy2K_C65PQiTjkZgEtpuTCEg", Pairing.collectProof(secret, pairId, phoneNonce))
    }

    @Test
    fun `method code`() {
        val k = Pairing.codeKey("K7QM4TXD")
        assertEquals("e898e958c53b4f306488422d76cbdd30ba929057ac21bc70fb8ffbaeadff5c2e", hex(k))
        val t = Pairing.transcript("code", "-", phoneNonce, name)
        assertEquals("5cbB9b5oknDpoMN3xu_fPdO5q_GvgR5BwN19a2eXxQ4", Pairing.claimProof(k, t))
        assertEquals("WM3nmfZziLG4yNxam4xdbLkbCmz34-67h9-Vig0ZdUo", Pairing.pcProof(k, t, pcNonce))
        assertEquals(listOf(1164, 578, 141, 383), Pairing.wordNumbers(k, t, pcNonce))
        assertEquals("vGv4Z06RSHN36fZ3dWXisIq7S6ALIBm_EsRAgf7xeqE", Pairing.collectProof(k, pairId, phoneNonce))
    }

    @Test
    fun `the typed code's key is made from the normalised code`() {
        val target = (Pairing.typedTarget("pc.tail1.ts.net", "k7qm-4txd", 4719) as Pairing.Parsed.Ok).target
        assertEquals(hex(Pairing.codeKey("K7QM4TXD")), hex(target.key))
    }

    @Test
    fun `the claim body carries the sums, never the secret`() {
        val target = (Pairing.parseQr(
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/$pairId/AAECAwQFBgcICQoLDA0ODw/1790000600",
        ) as Pairing.Parsed.Ok).target
        val t = Pairing.transcript("qr", pairId, phoneNonce, name)
        val body = Pairing.claimBody(target, phoneNonce, name, Pairing.claimProof(target.key, t))
        assertEquals(
            "{\"method\":\"qr\",\"pair_id\":\"$pairId\",\"phone_nonce\":\"$phoneNonce\"," +
                "\"name\":\"Pixel 9\",\"proof\":\"H0lGV2Jnwf0UFy1oAmBO4EZNtAWRnoyX8RjVNFIqq9c\"}",
            body,
        )
        assertTrue("the secret must never be sent", "AAECAwQFBgcICQoLDA0ODw" !in body)
        val code = (Pairing.typedTarget("pc.tail1.ts.net", "K7QM4TXD", 4719) as Pairing.Parsed.Ok).target
        val codeBody = Pairing.claimBody(code, phoneNonce, name, "p")
        assertTrue("method code leaves out pair_id", "pair_id" !in codeBody)
        assertTrue("the code must never be sent", "K7QM" !in codeBody)
    }

    /** The bundled list is EFF's short list 2: 1,296 words, each with its own first three letters. */
    @Test
    fun `the word list and the design's word numbers`() {
        val parsed = PairWords.parse(wordsFile().readText())
        assertNotNull("the bundled list must be 1,296 distinct words", parsed)
        val words = parsed!!
        assertEquals(1296, words.size)
        assertEquals(1296, words.map { it.take(3) }.toSet().size)
        assertEquals("aardvark", words.first())
        assertEquals("zucchini", words.last())
        assertEquals(listOf("easel", "lecturer", "siesta", "riptide"), listOf(330, 679, 1036, 970).map { words[it] })
        assertEquals(listOf("unlocking", "iguana", "blouse", "envoy"), listOf(1164, 578, 141, 383).map { words[it] })
    }

    private fun wordsFile(): File {
        val rel = "src/main/assets/${PairWords.ASSET}"
        return listOf(File(rel), File("app/$rel")).firstOrNull { it.isFile }
            ?: error("$rel not found from ${System.getProperty("user.dir")}")
    }
}
