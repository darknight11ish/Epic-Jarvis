package com.jarvis.client

import com.jarvis.client.net.CustomVoices
import com.jarvis.client.voice.VoiceNow
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone's half of "one PC-wide voice" (2026-10-28, the owner: *"when i
 * change the jarvis voice in the android app it still stays the same in jarvis
 * live in the android app"*).
 *
 * What it holds:
 *
 *  - the one doorbell: the `voices` event re-reads the PC's voice setting
 *    whatever screen is open, so a change made on the desktop reaches a phone
 *    that never opened the Voices screen. Before this the phone only re-read
 *    once that screen had asked, so its copy of the voice went stale;
 *  - the same state parsed from the PC's own JSON names the same voice the
 *    Voices screen names - one read, one vocabulary, so the two screens cannot
 *    disagree;
 *  - Live's chosen voice, said plainly: the PC's voice (named) when the reply
 *    sound came from the PC, and the phone's own voice - with why - when the
 *    PC had no engine to speak with, which no PC setting can change.
 *
 * The cases are the PC's real `GET /api/voice/voices` shape (docs/JARVIS-API.md
 * section 15), written out here rather than mocked through the network layer.
 */
class VoiceNowTest {

    private fun status(json: String): CustomVoices.Status = statusOf(JarvisJson.parseToJsonElement(json) as JsonObject)

    private fun statusOf(o: JsonObject): CustomVoices.Status =
        CustomVoices.parse(o) ?: error("the fixture did not parse as a status")

    /** The shape `GET /api/voice/voices` answers with, cut to what a voice line needs. */
    private fun fixture(choice: String?, label: String, speed: String = "normal"): String = """
        {
          "available": true,
          "active": "builtin",
          "active_name": "Built-in voice",
          "speaking_with": "kokoro",
          "voices": [{"id": "builtin", "name": "Built-in voice", "builtin": true, "ready": true,
                      "seconds": 0, "why": ""}],
          "better": {"enabled": false, "pending": false, "available": false, "can_turn_on": false,
                     "title": "", "detail": "", "why": ""},
          "pending": null,
          "last": null,
          "timings": [],
          "sentences": [],
          ${if (choice == null) "" else """
          "speaker": {"choice": "$choice", "note": "", "title": "Jarvis's built-in voice",
                      "detail": "", "make_line": "",
                      "choices": [
                        {"id": "af_bella", "label": "American (female) - Bella"},
                        {"id": "bm_george", "label": "British (male) - George"},
                        {"id": "af_sarah", "label": "American (female) - Sarah"}
                      ]},
          """}
          "speed": {"choice": "$speed", "value": 1.0, "default": "normal", "note": "",
                    "title": "How fast Jarvis speaks", "detail": "",
                    "choices": [{"id": "slower", "label": "Slower"},
                                {"id": "normal", "label": "Normal"},
                                {"id": "faster", "label": "Faster"}]},
          "limits": {"min_seconds": 3, "max_seconds": 10, "max_clip_bytes": 2900000,
                     "max_transcript_chars": 300, "max_name_chars": 40, "max_voices": 20}
        }
    """.trimIndent()

    // ---- the one doorbell --------------------------------------------------

    @Test
    fun the_voices_event_re_reads_the_setting_and_nothing_else_does() {
        assertTrue("the PC's voice event is the one that re-reads it", VoiceNow.rereadOn("voices"))
        for (other in listOf("approach", "voice", "voices_changed", "manner", "appearance", "")) {
            assertFalse("'$other' is not a voice change", VoiceNow.rereadOn(other))
        }
        assertEquals("voices", VoiceNow.RELOAD_EVENT)
    }

    // ---- the same read, the same name -------------------------------------

    @Test
    fun the_voice_live_names_is_the_voice_the_voices_screen_names() {
        val s = status(fixture("af_bella", ""))
        // The Voices screen's own line and Live's line come from ONE parsed
        // row, so a change in either app shows the same voice on both screens.
        assertEquals("American (female) - Bella", VoiceNow.label(s))
        assertEquals("Voice: American (female) - Bella, from your PC", VoiceNow.line(s, VoiceNow.Source.PC))
        assertTrue("the Voices screen still has its own sentence", CustomVoices.nowLine(s).isNotEmpty())
    }

    @Test
    fun a_changed_voice_changes_the_line_at_once() {
        val before = status(fixture("af_bella", ""))
        val after = status(fixture("bm_george", ""))
        assertEquals("Voice: American (female) - Bella, from your PC", VoiceNow.line(before, VoiceNow.Source.PC))
        assertEquals("Voice: British (male) - George, from your PC", VoiceNow.line(after, VoiceNow.Source.PC))
    }

    @Test
    fun a_choice_the_picker_does_not_list_is_still_named() {
        // The PC adds the current choice as an extra row; if it ever did not,
        // the id is better than a blank line - never "the voice" with no name.
        val s = status(fixture("bm_lewis", ""))
        assertEquals("bm_lewis", VoiceNow.label(s))
        assertEquals("Voice: bm_lewis, from your PC", VoiceNow.line(s, VoiceNow.Source.PC))
    }

    @Test
    fun a_pc_too_old_to_have_the_setting_says_only_that_it_is_the_pc() {
        val old = status(fixture(null, ""))
        assertNull("no speaker row: nothing to name", VoiceNow.label(old))
        assertEquals(VoiceNow.PC_LINE, VoiceNow.line(old, VoiceNow.Source.PC))
    }

    @Test
    fun a_status_the_phone_never_read_does_not_invent_a_voice() {
        assertNull(VoiceNow.label(null))
        assertNull("nothing spoken: nothing claimed", VoiceNow.line(null, VoiceNow.Source.NONE))
        assertEquals(VoiceNow.PC_LINE, VoiceNow.line(null, VoiceNow.Source.PC))
    }

    // ---- Live's chosen voice, said plainly ---------------------------------

    @Test
    fun the_phones_own_voice_is_said_plainly_and_says_why() {
        val s = status(fixture("af_bella", ""))
        val line = VoiceNow.line(s, VoiceNow.Source.PHONE) ?: error("the phone's voice must be said")
        assertTrue("it says the voice is the phone's", line.contains("this phone's own"))
        assertTrue("it says a PC setting cannot change it",
            line.contains("changing it on your PC changes nothing here"))
        assertFalse("it never claims to be the PC's voice", line.contains("from your PC"))
    }

    @Test
    fun the_source_of_a_reply_is_decided_by_what_really_happened() {
        // The PC made the sound.
        assertEquals(VoiceNow.Source.PC, VoiceNow.sourceOf(saidOnPc = true, fallbackAllowed = true, spoke = true))
        // The PC had no engine, and the phone's own voice was allowed and spoke.
        assertEquals(VoiceNow.Source.PHONE, VoiceNow.sourceOf(saidOnPc = false, fallbackAllowed = true, spoke = true))
        // The PC's 503 did not allow the phone to speak: nothing was said.
        assertEquals(VoiceNow.Source.NONE, VoiceNow.sourceOf(saidOnPc = false, fallbackAllowed = false, spoke = false))
        // The phone's voice was stopped or had no offline voice: never "the phone's".
        assertEquals(VoiceNow.Source.NONE, VoiceNow.sourceOf(saidOnPc = false, fallbackAllowed = true, spoke = false))
        assertNull(VoiceNow.line(status(fixture("af_bella", "")), VoiceNow.Source.NONE))
    }
}
