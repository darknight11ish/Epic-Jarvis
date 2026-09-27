package com.jarvis.client

import com.jarvis.client.net.CloudOffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * "A cloud model could give this one a second look." - `net/CloudOffer.kt`,
 * read off the same `X-Jarvis-Route` header [com.jarvis.client.net.Wellbeing]
 * and [com.jarvis.client.net.SecondCard] already read.
 */
class CloudOfferTest {

    @Test
    fun `names the lane only when gate is exactly offer`() {
        assertEquals(
            "jarvis-escalate",
            CloudOffer.laneFromHeader("""{"gate":"offer","offer":"jarvis-escalate"}"""),
        )
    }

    @Test
    fun `an escalated turn is not an offer - the cloud already answered it`() {
        // A non-blank `offer` on any gate but "offer" is not this project's
        // contract (docs/JARVIS-API.md: "offer" is "" on every gate but
        // this one) - but a header from a future backend that got that
        // wrong must still not be read as an offer to ask about, since the
        // answer already came from the cloud.
        assertNull(CloudOffer.laneFromHeader("""{"gate":"escalate","offer":"jarvis-escalate"}"""))
    }

    @Test
    fun `a blank offer is no offer`() {
        assertNull(CloudOffer.laneFromHeader("""{"gate":"offer","offer":""}"""))
    }

    @Test
    fun `no offer field at all is no offer`() {
        assertNull(CloudOffer.laneFromHeader("""{"gate":"offer"}"""))
    }

    @Test
    fun `every ordinary gate carries no offer`() {
        for (gate in listOf("local", "taint", "image", "private", "secret", "complexity",
            "budget", "escalate", "unavailable", "cloud_model")) {
            assertNull(CloudOffer.laneFromHeader("""{"gate":"$gate"}"""), gate)
        }
    }

    @Test
    fun `a non-string offer is refused, not thrown`() {
        assertNull(CloudOffer.laneFromHeader("""{"gate":"offer","offer":123}"""))
    }

    @Test
    fun `no header, a blank header, and malformed JSON are all no offer, never a crash`() {
        assertNull(CloudOffer.laneFromHeader(null))
        assertNull(CloudOffer.laneFromHeader(""))
        assertNull(CloudOffer.laneFromHeader("   "))
        assertNull(CloudOffer.laneFromHeader("not json"))
        assertNull(CloudOffer.laneFromHeader("[1,2,3]"))
    }

    @Test
    fun `the wording is fixed and has no exclamation marks or film phrases`() {
        for (line in listOf(CloudOffer.LABEL, CloudOffer.BUTTON, CloudOffer.MICRO)) {
            org.junit.Assert.assertFalse(line, "!" in line)
            org.junit.Assert.assertFalse(line, "sir" in line.lowercase())
            org.junit.Assert.assertFalse(line, "at your service" in line.lowercase())
        }
    }
}
