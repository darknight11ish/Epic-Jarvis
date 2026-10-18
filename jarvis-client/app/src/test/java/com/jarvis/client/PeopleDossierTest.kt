package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PeopleDossier
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Person dossier" on the phone (LM-4; [PeopleDossier]). Pure JVM.
 *
 * The bodies are the shape `/api/people/dossier` sends: the backend's own dict
 * passed back unchanged. What matters here is that a PC's answer is read
 * without inventing a word, and that a WITHHELD answer can never carry a name,
 * a fact or a count into the screen - even if a damaged answer carried them
 * beside the withheld flag.
 */
class PeopleDossierTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun aRealDossierShowsItsOwnWords() {
        val read = PeopleDossier.parse(
            obj(
                """{"ok": true, "withheld": false, "name": "Priya",
                   "active_facts": [{"id": 1, "text": "Sister, lives in Lisbon"}],
                   "states": {"facts": "ok"}, "why": {}, "read": [],
                   "text": "Priya - person dossier.\n- Sister, lives in Lisbon"}""",
            ),
        )
        assertTrue(read is PeopleDossier.Read.Shown)
        val shown = read as PeopleDossier.Read.Shown
        assertFalse(shown.withheld)
        assertEquals("Priya", shown.name)
        assertEquals("Priya - person dossier.\n- Sister, lives in Lisbon", shown.body)
    }

    @Test
    fun aWithheldAnswerIsOneSentenceAndNothingElse() {
        // A damaged answer that carries words BESIDE the withheld flag: the
        // reader must keep only the PC's sentence.
        val read = PeopleDossier.parse(
            obj(
                """{"ok": false, "withheld": true, "why": "Hidden while App lock is on.",
                   "text": "Hidden while App lock is on.", "name": "Priya",
                   "active_facts": [{"id": 1, "text": "Sister, lives in Lisbon"}]}""",
            ),
        )
        val shown = read as PeopleDossier.Read.Shown
        assertTrue(shown.withheld)
        assertEquals("", shown.name)
        assertEquals("Hidden while App lock is on.", shown.body)
        assertFalse(shown.body.contains("Priya"))
        assertFalse(shown.body.contains("Lisbon"))
    }

    @Test
    fun anAllowedButEmptyDossierSaysSoPlainly() {
        val read = PeopleDossier.parse(
            obj("""{"ok": true, "withheld": false, "name": "Nobody", "text": ""}"""),
        ) as PeopleDossier.Read.Shown
        assertEquals("Jarvis has no saved facts about them.", read.body)
    }

    @Test
    fun aRefusalIsThePcSentenceAndNeverInventsWords() {
        val said = "Say whose dossier to put together - a name."
        val read = PeopleDossier.parse(
            obj("""{"ok": false, "withheld": false, "why": "Say whose dossier to put together - a name.", "name": "", "text": "Say whose dossier to put together - a name."}"""),
        ) as PeopleDossier.Read.Shown
        assertFalse(read.withheld)
        assertEquals("", read.name)
        assertTrue(read.body.contains("Say whose dossier"))
    }

    @Test
    fun aShapeThatIsNotADossierIsUnreadable() {
        assertNull(PeopleDossier.parse(obj("""{"hello": true}""")))
        assertNull(PeopleDossier.parse(obj("""{"ok": "yes"}""")))
    }

    @Test
    fun theNameIsEncodedAndCanNeverAddAParameter() {
        assertEquals("/api/people/dossier?name=Priya", PeopleDossier.path("Priya"))
        assertEquals("/api/people/dossier?name=Ana%20Mara", PeopleDossier.path("Ana Mara"))
        assertEquals(
            "/api/people/dossier?name=x%26hidden%3D1",
            PeopleDossier.path("x&hidden=1"),
        )
    }

    @Test
    fun missingsAreTheSameRuleAsEveryOtherBrainRead() {
        assertTrue(PeopleDossier.missing(com.jarvis.client.net.ApiError.NotFound))
        assertTrue(PeopleDossier.missing(com.jarvis.client.net.ApiError.Server(501, "")))
        assertFalse(PeopleDossier.missing(com.jarvis.client.net.ApiError.Server(500, "")))
    }
}
