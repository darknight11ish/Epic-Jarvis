package com.jarvis.client

import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
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

    // ---- Changing the one-time answer later, on each animal's row ----

    private fun animalRow(vararg extra: Pair<String, JsonElement>) = JsonObject(
        mapOf<String, JsonElement>(
            "face" to JsonPrimitive("redpanda"),
            "name" to JsonPrimitive("Red Panda"),
            "speaker" to JsonPrimitive("3"),
            "semitones" to JsonPrimitive(1.5),
            "pace" to JsonPrimitive("normal"),
        ) + extra,
    )

    private fun answerOf(row: JsonObject): String? {
        val choices = JsonObject(
            mapOf(
                "voices" to JsonArray(
                    listOf(JsonObject(mapOf("id" to JsonPrimitive("3"), "label" to JsonPrimitive("Nicole")))),
                ),
                "paces" to JsonArray(
                    listOf(JsonObject(mapOf("id" to JsonPrimitive("normal"), "label" to JsonPrimitive("Normal")))),
                ),
            ),
        )
        val status = requireNotNull(
            CustomVoices.parse(
                withFaceVoice(
                    mapOf(
                        "enabled" to JsonPrimitive(true),
                        "animal_choices" to choices,
                        "animals" to JsonArray(listOf(row)),
                    ),
                ),
            ),
        )
        val animals = requireNotNull(status.faceVoice).animals
        assertEquals(1, animals.size)
        return animals[0].answer
    }

    @Test
    fun anAnimalRowsAnswerIsUseKeepOrNothing() {
        assertEquals("use", answerOf(animalRow("answer" to JsonPrimitive("use"))))
        assertEquals("keep", answerOf(animalRow("answer" to JsonPrimitive("keep"))))
        assertNull(answerOf(animalRow("answer" to JsonNull)))
        // An older PC sends no `answer` at all.
        assertNull(answerOf(animalRow()))
        // Garbage of any kind is no answer, never a crash.
        assertNull(answerOf(animalRow("answer" to JsonPrimitive("maybe"))))
        assertNull(answerOf(animalRow("answer" to JsonPrimitive(true))))
        assertNull(answerOf(animalRow("answer" to JsonObject(emptyMap()))))
    }

    @Test
    fun eachAnswerGetsTheOppositeButtonAndNoAnswerGetsNone() {
        assertEquals("Use its own voice", CustomVoices.changeMindLabel("keep"))
        assertEquals(true, CustomVoices.changeMindUse("keep"))
        assertEquals("Keep my voice", CustomVoices.changeMindLabel("use"))
        assertEquals(false, CustomVoices.changeMindUse("use"))
        assertNull(CustomVoices.changeMindLabel(null))
        assertNull(CustomVoices.changeMindUse(null))
        assertNull(CustomVoices.changeMindLabel("maybe"))
        assertNull(CustomVoices.changeMindUse("maybe"))
    }

    @Test
    fun pressingTheButtonSendsTheOppositeAnswerForThatAnimal() {
        assertEquals(
            "{\"face\":\"pygmyowl\",\"answer\":\"use\"}",
            CustomVoices.faceOfferBody("pygmyowl", use = requireNotNull(CustomVoices.changeMindUse("keep"))),
        )
        assertEquals(
            "{\"face\":\"pygmyowl\",\"answer\":\"keep\"}",
            CustomVoices.faceOfferBody("pygmyowl", use = requireNotNull(CustomVoices.changeMindUse("use"))),
        )
    }
}
