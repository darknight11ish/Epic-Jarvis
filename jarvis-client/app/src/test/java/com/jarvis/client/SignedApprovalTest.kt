package com.jarvis.client

import com.jarvis.client.net.ApprovalRefusal
import com.jarvis.client.net.Devices
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.SignedApproval
import com.jarvis.client.net.SignedApproval.ChallengeAnswer
import com.jarvis.client.net.SignedApproval.Local
import com.jarvis.client.net.SignedApproval.Path
import com.jarvis.client.net.SignedApproval.State
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Signed approvals, the phone's pure half (docs/PAIRING-DESIGN.md §11): the
 * words hash, the bytes that are signed, the PC's answers, this phone's state
 * and which way an approval goes.
 *
 * The two hash vectors are the frozen ones the backend and desktop builders
 * test against too. A contract test against the shared cases file
 * (contract/approval-sign-cases.json) is to be added after the three halves
 * merge; until then the vectors are written out here.
 */
class SignedApprovalTest {

    @After
    fun forget() = ApprovalRefusal.clear()

    private fun obj(text: String) = JarvisJson.parseToJsonElement(text) as JsonObject

    private val emailText = "To: sam@example.com\nSubject: Lunch\n\nSee you at noon."

    // ── The words hash ────────────────────────────────────────────────────

    @Test
    fun `the frozen vectors hold`() {
        assertEquals(
            "9f37085786f66802d4749c0d8ee5d12416ef264ac438efb4c071c3b25a907145",
            SignedApproval.wordsSha256("a1", "send_email", "Jarvis wants to send an email", emailText),
        )
        assertEquals(
            "b6def5b9c7862ccb21bd2989ede743136284ef9147e1c14abbe21434e63e758c",
            SignedApproval.wordsSha256("b2", "lockdown_off", "Jarvis wants to turn Lockdown off", ""),
        )
    }

    @Test
    fun `the parts are told apart by the separator, not run together`() {
        assertFalse(
            SignedApproval.wordsSha256("a", "bc", "d", "") == SignedApproval.wordsSha256("ab", "c", "d", ""),
        )
    }

    @Test
    fun `text comes from detail text, a plain string, or nothing`() {
        assertEquals("hello", SignedApproval.wordsTextOf(obj("""{"text": "hello", "diff": "x"}""")))
        assertEquals("", SignedApproval.wordsTextOf(obj("""{"diff": "x"}""")))
        assertEquals("", SignedApproval.wordsTextOf(obj("""{"text": 5}""")))
        assertEquals("plain words", SignedApproval.wordsTextOf(JsonPrimitive("plain words")))
        assertEquals("", SignedApproval.wordsTextOf(JsonPrimitive(7)))
        assertEquals("", SignedApproval.wordsTextOf(null))
        // Kept exactly as sent, spaces and all.
        assertEquals("  spaced \n", SignedApproval.wordsTextOf(obj("""{"text": "  spaced \n"}""")))
    }

    private fun read(json: String): PendingItem {
        val rows = decodePendingRows(listOf(JarvisJson.parseToJsonElement(json)))
        assertEquals(0, rows.skipped)
        return rows.items.single()
    }

    @Test
    fun `a card read from the PC's list hashes to the vector`() {
        val item = read(
            """{"id": "a1", "action": "send_email",
                "notice": {"title": "Jarvis wants to send an email"},
                "detail": {"text": ${JsonPrimitive(emailText)}, "to": "sam@example.com"}}""",
        )
        assertEquals(emailText, item.signText)
        assertEquals(
            "9f37085786f66802d4749c0d8ee5d12416ef264ac438efb4c071c3b25a907145",
            SignedApproval.wordsSha256(item),
        )
        assertTrue(SignedApproval.wordsMatch(item, "9F37085786F66802D4749C0D8EE5D12416EF264AC438EFB4C071C3B25A907145"))
        assertFalse(SignedApproval.wordsMatch(item, "0".repeat(64)))
    }

    @Test
    fun `a card with no detail hashes with empty text, and the title shown is the one hashed`() {
        val item = read(
            """{"id": "b2", "action": "lockdown_off", "notice": {"title": "Jarvis wants to turn Lockdown off"}}""",
        )
        assertEquals("", item.signText)
        assertEquals(
            "b6def5b9c7862ccb21bd2989ede743136284ef9147e1c14abbe21434e63e758c",
            SignedApproval.wordsSha256(item),
        )
        // With no notice the title is the shared fallback, and that is what is hashed.
        val bare = read("""{"id": "b2", "action": "lockdown_off"}""")
        assertEquals(
            SignedApproval.wordsSha256("b2", "lockdown_off", bare.title, ""),
            SignedApproval.wordsSha256(bare),
        )
    }

    @Test
    fun `a row cannot bring its own sign_text`() {
        val item = read("""{"id": "c3", "action": "x", "sign_text": "forged", "detail": "real"}""")
        assertEquals("real", item.signText)
    }

    @Test
    fun `detail sent as a json string is hashed as that string`() {
        val item = read("""{"id": "c4", "action": "x", "detail": "{\"text\": \"inner\"}"}""")
        assertEquals("{\"text\": \"inner\"}", item.signText)
    }

    // ── What is signed and how it travels ─────────────────────────────────

    @Test
    fun `the signed bytes are prefix, id, action, nonce, words joined by NUL`() {
        val words = "ab".repeat(32)
        val expected = "jarvis-approve-v1\u0000a1\u0000send_email\u0000NONCE22CHARACTERS_ABCD\u0000$words"
            .toByteArray(Charsets.UTF_8)
        assertArrayEquals(
            expected,
            SignedApproval.signedMessage("a1", "send_email", "NONCE22CHARACTERS_ABCD", words),
        )
        assertEquals(4, expected.count { it == 0.toByte() })
    }

    @Test
    fun `base64url has no padding and no plus or slash`() {
        assertEquals("-_8", SignedApproval.b64url(byteArrayOf(0xfb.toByte(), 0xff.toByte())))
        assertEquals("AQ", SignedApproval.b64url(byteArrayOf(1)))
        assertEquals("", SignedApproval.b64url(byteArrayOf()))
    }

    @Test
    fun `the approve body is the old one without a signature and carries one with it`() {
        assertEquals("""{"id":"a1"}""", SignedApproval.approveBody("a1", null))
        val body = obj(SignedApproval.approveBody("a1", SignedApproval.Signature("d3f9a1c2e", "N", "SIG")))
        assertEquals("a1", (body["id"] as JsonPrimitive).content)
        val sig = body["signature"] as JsonObject
        assertEquals("d3f9a1c2e", (sig["device"] as JsonPrimitive).content)
        assertEquals("N", (sig["nonce"] as JsonPrimitive).content)
        assertEquals("SIG", (sig["sig"] as JsonPrimitive).content)
    }

    @Test
    fun `the other two bodies`() {
        assertEquals("""{"id":"a1"}""", SignedApproval.challengeBody("a1"))
        assertEquals("""{"public_key":"-_8"}""", SignedApproval.registerBody(byteArrayOf(0xfb.toByte(), 0xff.toByte())))
    }

    // ── The PC's answers ──────────────────────────────────────────────────

    @Test
    fun `a challenge is read`() {
        val words = "a".repeat(64)
        val got = SignedApproval.challengeAnswer(
            200,
            obj("""{"nonce": "abcdefghijklmnopqrstuv", "words_sha256": "$words", "expires_in": 120}"""),
        ) as ChallengeAnswer.Got
        assertEquals("abcdefghijklmnopqrstuv", got.nonce)
        assertEquals(words, got.wordsSha256)
        assertEquals(120, got.expiresIn)
    }

    @Test
    fun `a challenge that cannot be read is refused, not trusted`() {
        val bad = listOf(
            obj("""{"nonce": "", "words_sha256": "${"a".repeat(64)}"}"""),
            obj("""{"nonce": "n", "words_sha256": "short"}"""),
            obj("""{"nonce": "n"}"""),
        )
        for (b in bad) assertTrue(SignedApproval.challengeAnswer(200, b) is ChallengeAnswer.Refused)
        assertTrue(SignedApproval.challengeAnswer(200, null) is ChallengeAnswer.Refused)
    }

    @Test
    fun `challenge refusals`() {
        assertEquals(
            ChallengeAnswer.NoApprovalKey,
            SignedApproval.challengeAnswer(403, obj("""{"owner_check": "no_approval_key"}""")),
        )
        assertEquals(ChallengeAnswer.CardGone, SignedApproval.challengeAnswer(404, null))
        val other = SignedApproval.challengeAnswer(403, obj("""{"error": "shared key"}""")) as ChallengeAnswer.Refused
        assertEquals("Not approved. shared key", other.words)
        val bare = SignedApproval.challengeAnswer(500, null) as ChallengeAnswer.Refused
        assertEquals(SignedApproval.NOT_ACCEPTED, bare.words)
    }

    @Test
    fun `registering is read`() {
        assertEquals(true to SignedApproval.WAITING_WORDS_SETTINGS, SignedApproval.registerAnswer(202, obj("""{"waiting": true}""")))
        assertEquals(false to SignedApproval.MISSING, SignedApproval.registerAnswer(404, null))
        assertEquals(false to "needs cryptography", SignedApproval.registerAnswer(503, obj("""{"error": "needs cryptography"}""")))
        assertEquals(false to SignedApproval.NEEDS_CRYPTO, SignedApproval.registerAnswer(503, null))
        assertEquals(false to "Not turned on. Try again.", SignedApproval.registerAnswer(500, null))
    }

    @Test
    fun `the three refusals are read from a 403 body and explained`() {
        for (word in listOf("no_approval_key", "no_signature", "bad_signature")) {
            assertEquals(word, SignedApproval.refusalIn("""{"owner_check": "$word"}"""))
        }
        // Another owner_check reason, or nothing, is not one of ours.
        assertNull(SignedApproval.refusalIn("""{"owner_check": "not_set_up"}"""))
        assertNull(SignedApproval.refusalIn("""{"error": "bad or missing X-Jarvis-Token"}"""))
        assertNull(SignedApproval.refusalIn("not json"))
        assertNull(SignedApproval.refusalIn(null))

        assertEquals(SignedApproval.OFFER_WORDS, SignedApproval.refusalWords("no_approval_key"))
        assertEquals(SignedApproval.NOT_ACCEPTED, SignedApproval.refusalWords("no_signature"))
        // A refused signature gets the one button: the usual cause is a key the PC does not hold.
        assertEquals(SignedApproval.OFFER_BAD_WORDS, SignedApproval.refusalWords("bad_signature"))
        assertTrue(SignedApproval.offersTurnOn(SignedApproval.OFFER_BAD_WORDS))
        assertNull(SignedApproval.refusalWords(null))
        assertTrue(SignedApproval.NOT_ACCEPTED.contains("turn signed approvals off and on again in Settings -> Devices"))
    }

    @Test
    fun `the kept refusal is taken once`() {
        ApprovalRefusal.note("""{"owner_check": "bad_signature"}""")
        assertEquals("bad_signature", ApprovalRefusal.take())
        assertNull(ApprovalRefusal.take())
        ApprovalRefusal.note("""{"error": "x"}""")
        assertNull(ApprovalRefusal.take())
    }

    // ── This phone's state, and the path an approval takes ────────────────

    @Test
    fun `the state, from the PC's word and this phone's key`() {
        // Not paired with a key of its own: nothing to sign with, whatever else.
        assertEquals(State.NOT_PAIRED, SignedApproval.stateOf(false, "true", Local.READY))
        // An older PC says nothing about approval keys.
        assertEquals(State.UNSUPPORTED, SignedApproval.stateOf(true, null, Local.NONE))
        assertEquals(State.ON, SignedApproval.stateOf(true, "true", Local.READY))
        assertEquals(State.WAITING, SignedApproval.stateOf(true, "waiting", Local.READY))
        assertEquals(State.OFF, SignedApproval.stateOf(true, "false", Local.NONE))
        assertEquals(State.OFF, SignedApproval.stateOf(true, "false", Local.READY))
        assertEquals(State.OFF, SignedApproval.stateOf(true, "waiting", Local.NONE))
        // The PC has a key but this phone has lost its half, or Android killed it.
        assertEquals(State.AGAIN, SignedApproval.stateOf(true, "true", Local.NONE))
        assertEquals(State.AGAIN, SignedApproval.stateOf(true, "true", Local.INVALID))
        assertEquals(State.AGAIN, SignedApproval.stateOf(true, "false", Local.INVALID))
        assertEquals(State.AGAIN, SignedApproval.stateOf(true, "waiting", Local.INVALID))
    }

    @Test
    fun `which way an approval goes`() {
        // Risky, own key, approval key on: signed.
        assertEquals(Path.SIGNED, SignedApproval.pathFor(true, State.ON))
        // Risky, own key, none yet: the one button; killed key: the button, again; waiting: wait.
        assertEquals(Path.OFFER, SignedApproval.pathFor(true, State.OFF))
        assertEquals(Path.OFFER_AGAIN, SignedApproval.pathFor(true, State.AGAIN))
        assertEquals(Path.WAITING, SignedApproval.pathFor(true, State.WAITING))
        // Not risky: today's way, whatever the state.
        for (s in State.entries) assertEquals(Path.PLAIN, SignedApproval.pathFor(false, s))
        // Shared key, or a PC that does not know signed approvals: today's way.
        assertEquals(Path.PLAIN, SignedApproval.pathFor(true, State.NOT_PAIRED))
        assertEquals(Path.PLAIN, SignedApproval.pathFor(true, State.UNSUPPORTED))
        // The PC could not be read: today's way (the PC says no_approval_key if it needs one).
        assertEquals(Path.PLAIN, SignedApproval.pathFor(true, null))
    }

    @Test
    fun `only the offer notices carry the one button`() {
        assertTrue(SignedApproval.offersTurnOn(SignedApproval.OFFER_WORDS))
        assertTrue(SignedApproval.offersTurnOn(SignedApproval.OFFER_AGAIN_WORDS))
        assertFalse(SignedApproval.offersTurnOn(SignedApproval.WAITING_WORDS))
        assertFalse(SignedApproval.offersTurnOn(SignedApproval.NOT_ACCEPTED))
        assertFalse(SignedApproval.offersTurnOn(null))
        assertEquals(SignedApproval.OFFER_WORDS, SignedApproval.noticeFor(Path.OFFER))
        assertEquals(SignedApproval.OFFER_AGAIN_WORDS, SignedApproval.noticeFor(Path.OFFER_AGAIN))
        assertEquals(SignedApproval.WAITING_WORDS, SignedApproval.noticeFor(Path.WAITING))
        assertNull(SignedApproval.noticeFor(Path.PLAIN))
        assertNull(SignedApproval.noticeFor(Path.SIGNED))
    }

    @Test
    fun `no sentence says a decision was taken`() {
        for (words in listOf(SignedApproval.OFFER_WORDS, SignedApproval.OFFER_AGAIN_WORDS, SignedApproval.WAITING_WORDS)) {
            assertTrue(words.startsWith("Nothing was approved."))
        }
    }

    // ── Settings, Devices ─────────────────────────────────────────────────

    @Test
    fun `the device list carries the approval key state`() {
        val v = Devices.parse(
            obj(
                """{"you": "d1", "devices": [
                  {"id": "d1", "name": "A", "kind": "phone", "this_device": true, "approval_key": true},
                  {"id": "d2", "name": "B", "kind": "phone", "approval_key": "waiting"},
                  {"id": "d3", "name": "C", "kind": "phone", "approval_key": false},
                  {"id": "d4", "name": "D", "kind": "phone"},
                  {"id": "d5", "name": "E", "kind": "phone", "approval_key": "maybe"}]}""",
            ),
        )
        assertEquals(listOf("true", "waiting", "false", null, null), v.devices.map { it.approvalKey })
    }
}
