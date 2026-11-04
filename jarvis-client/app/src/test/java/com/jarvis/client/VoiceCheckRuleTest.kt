package com.jarvis.client

import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.VoiceCheckRule
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * THE ONE VOICE-CHECK RULE, on the phone's half (the owner, 2026-11-03):
 * *"my voice should only need to be confirmed if i say hi jarvis when the
 * phone is locked ... when i start jarvis live on my unlocked phone i dont
 * want it to need to confirm my voice. make this a setting i can change"*.
 *
 * The decision itself is the PC's - `jarvis_live.voice_check_needed()` in
 * `backend/jarvis_live.py` - and `backend/test_voice_check_rule.py` holds the
 * same table there. The rows below are that table, row for row: the two copies
 * cannot drift apart without one of the two tests failing.
 *
 * What this phone is allowed to do is SAY whether its own screen was locked
 * ([VoiceCheckRule.lockedField]) and ASK for the one setting
 * ([VoiceCheckRule.body]); it never skips a check and never approves a card.
 */
class VoiceCheckRuleTest {

    @Test
    fun `the mic press NEVER checks - locked, unlocked or unknown`() {
        for (locked in listOf(true, false, null)) {
            assertFalse(
                "mic press with locked=$locked",
                VoiceCheckRule.checks(VoiceCheckRule.MIC_PRESS, locked, settingOn = true),
            )
            assertFalse(
                "mic press with locked=$locked and the setting off",
                VoiceCheckRule.checks(VoiceCheckRule.MIC_PRESS, locked, settingOn = false),
            )
        }
    }

    @Test
    fun `hi Jarvis on a LOCKED phone checks - the only check left`() {
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, true, settingOn = true))
    }

    @Test
    fun `hi Jarvis on an UNLOCKED phone does not check while the setting is ON`() {
        assertFalse(VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, false, settingOn = true))
        // ...but a phone that did not say keeps the check (fail closed).
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, null, settingOn = true))
        // ...and so does a locked one, which is the row above, restated here so
        // the three wake-word rows sit together.
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, true, settingOn = true))
    }

    @Test
    fun `Live started on an UNLOCKED phone does not check while the setting is ON`() {
        assertFalse(VoiceCheckRule.checks(VoiceCheckRule.LIVE_START, false, settingOn = true))
        // Locked, or a phone that did not say: still checks.
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.LIVE_START, true, settingOn = true))
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.LIVE_START, null, settingOn = true))
    }

    @Test
    fun `the setting OFF is the OLD, FULL CHECKS - an unlocked phone is IGNORED`() {
        // This is the row that used to be the other way round. OFF withdraws
        // the exemption, so the phone's "I am unlocked" is a claim and not a
        // permission: every trigger left checks, whatever it said.
        for (locked in listOf(true, false, null)) {
            assertTrue(
                "Live start with locked=$locked and the setting off must check",
                VoiceCheckRule.checks(VoiceCheckRule.LIVE_START, locked, settingOn = false),
            )
            assertTrue(
                "hi Jarvis with locked=$locked and the setting off must check",
                VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, locked, settingOn = false),
            )
        }
        // OFF never means "no checks", and it does not exempt a strange
        // trigger either.
        assertTrue(VoiceCheckRule.checks("something_new", false, settingOn = false))
    }

    @Test
    fun `the setting touches nothing else - the mic press never checks either way`() {
        for (locked in listOf(true, false, null)) {
            for (settingOn in listOf(true, false)) {
                assertFalse(
                    "mic press with locked=$locked and settingOn=$settingOn",
                    VoiceCheckRule.checks(VoiceCheckRule.MIC_PRESS, locked, settingOn),
                )
            }
        }
    }

    @Test
    fun `the default is the owner's rule, ON - and an unknown trigger keeps the check`() {
        assertEquals(true, VoiceCheckRule.DEFAULT_ON)
        // No argument means ON, which is also what a missing setting file reads
        // as on the PC.
        assertFalse(VoiceCheckRule.checks(VoiceCheckRule.LIVE_START, false))
        assertTrue(VoiceCheckRule.checks(VoiceCheckRule.WAKE_WORD, true))
        assertTrue(VoiceCheckRule.checks("something_new", null, settingOn = true))
    }

    @Test
    fun `the start body carries the lock state only when this phone knows it`() {
        assertEquals(
            "{\"do\":\"start\",\"device\":\"phone\",\"by\":\"button\"}",
            LiveRules.startBody(),
        )
        assertEquals(
            "{\"do\":\"start\",\"device\":\"phone\",\"by\":\"button\",\"locked\":false}",
            LiveRules.startBody(phoneLocked = false),
        )
        assertEquals(
            "{\"do\":\"start\",\"device\":\"phone\",\"by\":\"button\",\"locked\":true}",
            LiveRules.startBody(phoneLocked = true),
        )
        // The chat id is still sent, and the lock field comes after it.
        assertEquals(
            "{\"do\":\"start\",\"device\":\"phone\",\"by\":\"button\"," +
                "\"conversation_id\":\"abcdefgh\",\"locked\":false}",
            LiveRules.startBody("abcdefgh", phoneLocked = false),
        )
        // Nothing is sent when it cannot be read: an old phone's body, exactly.
        assertEquals(
            "{\"do\":\"start\",\"device\":\"phone\",\"by\":\"button\"," +
                "\"conversation_id\":\"abcdefgh\"}",
            LiveRules.startBody("abcdefgh", phoneLocked = null),
        )
    }

    @Test
    fun `the setting is read and written on the EXISTING Live route`() {
        assertEquals("{\"do\":\"voice_check\"}", VoiceCheckRule.body(null))
        assertEquals("{\"do\":\"voice_check\",\"enabled\":true}", VoiceCheckRule.body(true))
        assertEquals("{\"do\":\"voice_check\",\"enabled\":false}", VoiceCheckRule.body(false))
        // The command name is the one the PC dispatches on.
        assertEquals("voice_check", VoiceCheckRule.DO)
    }

    @Test
    fun `the PC's answer is read as it was written`() {
        val on = buildJsonObject {
            put("ok", JsonPrimitive(true))
            put("on", JsonPrimitive(true))
            put("waiting", JsonPrimitive(false))
            put("message", JsonPrimitive("Your voice is checked only when you say \"hi Jarvis\" on a locked phone."))
        }
        assertEquals(true, VoiceCheckRule.on(on))
        assertFalse(VoiceCheckRule.waiting(on))
        assertTrue(VoiceCheckRule.words(on).startsWith("Your voice is checked"))

        val waiting = buildJsonObject {
            put("ok", JsonPrimitive(true))
            put("on", JsonPrimitive(false))
            put("waiting", JsonPrimitive(true))
            put("message", JsonPrimitive("Waiting for your approval."))
        }
        assertEquals(false, VoiceCheckRule.on(waiting))
        assertTrue("an ON still waiting for its card is never read as on",
            VoiceCheckRule.waiting(waiting))

        val refused = buildJsonObject { put("error", JsonPrimitive("Not on this PC.")) }
        assertNull(VoiceCheckRule.on(refused))
        assertEquals("Not on this PC.", VoiceCheckRule.words(refused))
        assertNull(VoiceCheckRule.on(null))
    }

    @Test
    fun `the Live screen no longer promises a check per session`() {
        // The sentence at LiveScreen.kt used to say "Every full sentence is
        // checked for your voice on your PC; once this session is verified, a
        // short reply is trusted without a check." That stopped being true on
        // 2026-11-03, and the owner asked for the opposite, so the screen must
        // not promise it.
        val root = listOf(
            File("src/main/java"),
            File("app/src/main/java"),
            File("jarvis-client/app/src/main/java"),
        ).first { it.isDirectory }
        val screen = File(root, "com/jarvis/client/ui/screens/LiveScreen.kt").readText()
        assertFalse(
            "LiveScreen still promises a check on every full sentence",
            screen.contains("Every full sentence is checked"),
        )
        assertFalse(
            "LiveScreen still promises per-session verification",
            screen.contains("once this session is verified"),
        )
        assertTrue(
            "LiveScreen says where the one setting is",
            screen.contains("Settings, Voice"),
        )
        assertTrue(
            "LiveScreen states the only check left",
            screen.contains("hi Jarvis") && screen.contains("locked phone"),
        )
    }
}
