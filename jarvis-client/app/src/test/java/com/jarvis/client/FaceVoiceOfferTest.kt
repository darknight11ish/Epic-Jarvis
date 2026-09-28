package com.jarvis.client

import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The one-time "The panda has its own voice. Use it?" question (owner,
 * 2026-09-28): `GET /api/voice/voices` -> `face_voice.offer`, answered with
 * `POST /api/voice/voices/face_offer`.
 *
 * The JSON is built here, in the backend's documented shape, because the
 * shared fixture (`contract/phone-voice-cases.json`) did not have an offer
 * case when this was written. Once tools/gen_phone_voice_cases.py records
 * one, a case against the PC's real answer belongs in CustomVoicesTest.
 */
class FaceVoiceOfferTest {

    private val empty: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/phone-voice-cases.json")) {
            "contract/phone-voice-cases.json is missing - run tools/gen_phone_voice_cases.py"
        }.readText()
        val voices = (JarvisJson.parseToJsonElement(text) as JsonObject)["voices"]!!.jsonObject
        voices["status"]!!.jsonObject["empty"]!!.jsonObject
    }

    private fun withFaceVoice(fv: Map<String, kotlinx.serialization.json.JsonElement>) =
        JsonObject(empty + ("face_voice" to JsonObject(fv)))

    private val offerJson = JsonObject(
        mapOf(
            "face" to JsonPrimitive("redpanda"),
            "question" to JsonPrimitive("The Red Panda has its own voice. Use it?"),
            "use" to JsonPrimitive("Use it"),
            "keep" to JsonPrimitive("Keep my voice"),
        ),
    )

    @Test
    fun theOfferIsReadWithThePcsOwnWords() {
        val status = requireNotNull(
            CustomVoices.parse(withFaceVoice(mapOf("enabled" to JsonPrimitive(false), "offer" to offerJson))),
        )
        val offer = requireNotNull(status.faceVoice?.offer)
        assertEquals("redpanda", offer.face)
        assertEquals("The Red Panda has its own voice. Use it?", offer.question)
        assertEquals("Use it", offer.use)
        assertEquals("Keep my voice", offer.keep)
    }

    @Test
    fun noOfferANullOfferOrAnOlderPcShowsNothing() {
        val nullOffer = CustomVoices.parse(withFaceVoice(mapOf("enabled" to JsonPrimitive(true), "offer" to JsonNull)))
        assertNull(requireNotNull(nullOffer?.faceVoice).offer)
        val older = CustomVoices.parse(withFaceVoice(mapOf("enabled" to JsonPrimitive(true))))
        assertNull(requireNotNull(older?.faceVoice).offer)
        // Without a face or a question there is nothing to ask.
        assertNull(CustomVoices.parseFaceOffer(JsonObject(offerJson - "face")))
        assertNull(CustomVoices.parseFaceOffer(JsonObject(offerJson - "question")))
        // Button words missing: the owner's own wording stands in.
        val bare = requireNotNull(CustomVoices.parseFaceOffer(JsonObject(offerJson - "use" - "keep")))
        assertEquals(CustomVoices.OFFER_USE_LABEL, bare.use)
        assertEquals(CustomVoices.OFFER_KEEP_LABEL, bare.keep)
    }

    @Test
    fun theAnswerSentIsTheFaceAndUseOrKeep() {
        assertEquals("/api/voice/voices/face_offer", CustomVoices.FACE_OFFER_PATH)
        assertEquals("{\"face\":\"redpanda\",\"answer\":\"use\"}", CustomVoices.faceOfferBody("redpanda", use = true))
        assertEquals("{\"face\":\"seaotter\",\"answer\":\"keep\"}", CustomVoices.faceOfferBody("seaotter", use = false))
    }
}
