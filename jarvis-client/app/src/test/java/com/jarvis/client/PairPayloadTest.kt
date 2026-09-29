package com.jarvis.client

import com.jarvis.client.net.Pairing
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The QR text rule (docs/PAIRING-DESIGN.md §8.4) and the address rule for
 * pairing: only a Tailscale (.ts.net) or NordVPN Meshnet (.nord) name.
 */
class PairPayloadTest {

    private val good =
        "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600"

    private fun bad(text: String): String = (Pairing.parseQr(text) as Pairing.Parsed.Bad).message

    @Test
    fun `the design's own QR text parses`() {
        val t = (Pairing.parseQr(good) as Pairing.Parsed.Ok).target
        assertEquals("jarvis-pc.tail1234.ts.net", t.host)
        assertEquals(4719, t.port)
        assertEquals("qr", t.method)
        assertEquals("00112233445566ff", t.pairId)
        assertEquals("00112233445566ff", t.ref)
        assertEquals(1790000600L, t.expires)
        assertArrayEquals(ByteArray(16) { it.toByte() }, t.key)
        assertEquals("jarvis-pc.tail1234.ts.net:4719", t.address)
        assertEquals("http://jarvis-pc.tail1234.ts.net:4719", t.base)
    }

    @Test
    fun `a Meshnet name parses too`() {
        val t = (Pairing.parseQr(good.replace("jarvis-pc.tail1234.ts.net", "my-pc.nord")) as Pairing.Parsed.Ok).target
        assertEquals("my-pc.nord", t.host)
    }

    @Test
    fun `a newer format says update the app`() {
        assertEquals(Pairing.NEWER_CODE, bad(good.replace("jarvis-pair:1/", "jarvis-pair:2/")))
    }

    @Test
    fun `anything off the strict shape is not a Jarvis code`() {
        val cases = listOf(
            "",
            "hello",
            " $good",
            "$good ",
            "$good/",
            good.replace("jarvis-pair:", "JARVIS-PAIR:"),
            good.replace("jarvis-pair:1/", "jarvis-pair:x/"),
            // Host: upper case, a number, a home name, the open internet, a public tunnel.
            good.replace("jarvis-pc.tail1234.ts.net", "Jarvis-PC.tail1234.ts.net"),
            good.replace("jarvis-pc.tail1234.ts.net", "100.101.2.3"),
            good.replace("jarvis-pc.tail1234.ts.net", "jarvis-pc.local"),
            good.replace("jarvis-pc.tail1234.ts.net", "example.com"),
            good.replace("jarvis-pc.tail1234.ts.net", "abc.ngrok.io"),
            good.replace("jarvis-pc.tail1234.ts.net", "ts.net"),
            good.replace("jarvis-pc.tail1234.ts.net", ".nord"),
            good.replace("jarvis-pc.tail1234.ts.net", "a..b.ts.net"),
            // Port: leading zero, zero, too big, not digits.
            good.replace("/4719/", "/04719/"),
            good.replace("/4719/", "/0/"),
            good.replace("/4719/", "/65536/"),
            good.replace("/4719/", "/47a9/"),
            // Pair id: upper case, too short.
            good.replace("00112233445566ff", "00112233445566FF"),
            good.replace("00112233445566ff", "00112233445566f"),
            // Secret: too short, a bad character.
            good.replace("AAECAwQFBgcICQoLDA0ODw", "AAECAwQFBgcICQoLDA0OD"),
            good.replace("AAECAwQFBgcICQoLDA0ODw", "AAECAwQFBgcICQoLDA0OD+"),
            // Expires: not 10 digits.
            good.replace("1790000600", "179000060"),
            // Too few and too many parts.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw",
            "$good/extra",
        )
        for (c in cases) assertEquals(c, Pairing.NOT_A_CODE, bad(c))
    }

    @Test
    fun `pairing needs a mesh name`() {
        assertNull(Pairing.hostProblem("jarvis-pc.tail1234.ts.net"))
        assertNull(Pairing.hostProblem("my-pc.nord"))
        for (h in listOf("192.168.1.20", "100.64.1.5", "pc.local", "localhost", "example.com", "ts.net", "")) {
            assertEquals(h, Pairing.HOST_NOT_MESH, Pairing.hostProblem(h))
        }
    }

    @Test
    fun `a typed code takes the PC's name, with or without a port`() {
        val a = (Pairing.typedTarget("Jarvis-PC.tail1234.ts.net", "k7qm-4txd", 4719) as Pairing.Parsed.Ok).target
        assertEquals("jarvis-pc.tail1234.ts.net", a.host)
        assertEquals(4719, a.port)
        assertEquals("code", a.method)
        assertNull(a.pairId)
        assertEquals("-", a.ref)
        val b = (Pairing.typedTarget("http://my-pc.nord:5000/", "K7QM4TXD", 4719) as Pairing.Parsed.Ok).target
        assertEquals("my-pc.nord", b.host)
        assertEquals(5000, b.port)
        assertEquals(Pairing.BAD_TYPED_CODE, (Pairing.typedTarget("my-pc.nord", "K7QM", 4719) as Pairing.Parsed.Bad).message)
        assertEquals(Pairing.HOST_NOT_MESH, (Pairing.typedTarget("192.168.1.20", "K7QM4TXD", 4719) as Pairing.Parsed.Bad).message)
        assertTrue(Pairing.typedTarget("https://my-pc.nord", "K7QM4TXD", 4719) is Pairing.Parsed.Bad)
    }
}
