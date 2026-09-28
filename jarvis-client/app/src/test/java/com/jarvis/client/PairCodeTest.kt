package com.jarvis.client

import com.jarvis.client.net.Pairing
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The typed code (docs/PAIRING-DESIGN.md §8.5) and the phone's name (§4). */
class PairCodeTest {

    @Test
    fun `the code is normalised the design's way`() {
        assertEquals("K7QM4TXD", Pairing.normaliseCode("K7QM-4TXD"))
        assertEquals("K7QM4TXD", Pairing.normaliseCode("k7qm 4txd"))
        assertEquals("K7QM4TXD", Pairing.normaliseCode(" k7qm-4txd "))
        // O reads as 0; I and L as 1.
        assertEquals("K0QM1TX1", Pairing.normaliseCode("KOQM-ITXL"))
        assertEquals("K0QM1TX1", Pairing.normaliseCode("koqm-itxl"))
    }

    @Test
    fun `anything but 8 characters of the alphabet is refused`() {
        for (c in listOf("", "K7QM", "K7QM-4TXD-1", "K7QM4TXU", "K7QM4TX!", "K7QM4TXDD", "K7QM_4TXD")) {
            assertNull(c, Pairing.normaliseCode(c))
        }
    }

    @Test
    fun `the name rule`() {
        for (ok in listOf("Pixel 9", "Galaxy S24 (work)", "Sam's phone", "a", "x_y-z.1", "Téléphone", "電話", "1".repeat(40))) {
            assertNull(ok, Pairing.nameProblem(ok))
        }
        for (bad in listOf("", " ", "1".repeat(41), "line\nbreak", "tab\there", "a/b", "a<b>", "evil‮eman", "emoji 😀")) {
            assertEquals(bad, Pairing.BAD_NAME, Pairing.nameProblem(bad))
        }
    }

    @Test
    fun `the suggested name is the model, kept inside the rule`() {
        assertEquals("Pixel 9", Pairing.suggestedName("Pixel 9"))
        assertEquals("SM-S921B", Pairing.suggestedName("SM-S921B"))
        assertEquals("My phone", Pairing.suggestedName(null))
        assertEquals("My phone", Pairing.suggestedName("///"))
        assertEquals(40, Pairing.suggestedName("x".repeat(60)).length)
    }

    @Test
    fun `wrong-code words`() {
        assertEquals("That code is not right. 2 tries left.", Pairing.wrongCode(2))
        assertEquals("That code is not right. 1 try left.", Pairing.wrongCode(1))
        assertEquals("That code is not right.", Pairing.wrongCode(null))
    }
}
