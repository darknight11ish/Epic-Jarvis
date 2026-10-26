package com.jarvis.client

import com.jarvis.client.net.ApprovalRefusal
import com.jarvis.client.net.AsksFirst
import com.jarvis.client.net.PcOnlyActions
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.SignedApproval
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The second pull request's fixes from the 2026-10-24 full audit's Android half
 * (`.dsh-scratch/ANDROID-AUDIT-R7-2026-10-24.md`, §Fix list items 1-5, the A0
 * wording half, and C2).
 *
 * Most of these are Compose or Android-service paths, and there is no emulator
 * in this session, so those rules are held the way `ExpiredCardShowsNoButtonsTest`
 * and `OpenPlaceTest` hold theirs: by reading the shipped source for the exact
 * line that implements the rule. C2 and the backup wording are plain data and
 * are tested by behaviour.
 *
 * Nothing here is a runtime pass: the screens and the microphone stay
 * NOT-TESTABLE / field-test rows, never a green tick.
 */
class AuditPlumbingTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    /** The text from [marker] on for a while - enough to hold the one function. */
    private fun after(src: String, marker: String): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        return src.substring(at, minOf(src.length, at + 2_000))
    }

    // ----------------------------------------------------------------- C2 ---

    @Test
    fun everyPcOnlyActionIsKnownAndTheRestAreNot() {
        // The PC's own set, as `jarvis_owner_check.PC_ONLY_ACTIONS` lists it on
        // 2026-10-24. If it gains or loses one there, this test should be the
        // first thing that notices - not a tap that fails.
        assertEquals(
            setOf(
                "loosen_what_asks_first", "enable_reading_tool", "restore_backup",
                "pair_device", "unretire_shared_key", "register_approval_key",
                "handoff_keep_offering", "handoff_bring_to_front",
            ),
            PcOnlyActions.ALL,
        )
        assertEquals(8, PcOnlyActions.ALL.size)
        assertTrue(AsksFirst.LOOSEN_ACTION in PcOnlyActions.ALL)
        for (action in PcOnlyActions.ALL) {
            assertTrue(
                "$action can only be approved on the PC, but the card does not say so",
                PendingItem(id = "x", action = action).pcOnly,
            )
        }
        // The actions the owner deliberately allowed from the phone stay allowed.
        for (action in listOf("raise_api_limit", "send_email", "tidy_inbox", "model_switch")) {
            assertFalse(
                "$action must stay approvable from the phone",
                PendingItem(id = "x", action = action).pcOnly,
            )
        }
    }

    @Test
    fun aPcOnlyRefusalIsExplainedRatherThanBlamedOnTheKey() {
        val body = """{"ok":false,"error":"This card can only be approved on the PC, with """ +
            """Windows Hello, so nothing was approved","owner_check":"pc_only"}"""
        assertEquals(SignedApproval.REFUSAL_PC_ONLY, SignedApproval.refusalIn(body))
        // The sentence is the "approve this one on the PC" one, and never the
        // refused-key sentence that opens the pairing screen.
        assertEquals(AsksFirst.APPROVE_ON_PC, SignedApproval.refusalWords(SignedApproval.REFUSAL_PC_ONLY))
        assertFalse(SignedApproval.refusalWords(SignedApproval.REFUSAL_PC_ONLY)!!.contains("pairing key"))
        // The route `JarvisApi.approve` uses keeps it as a word, once.
        ApprovalRefusal.note(body)
        assertEquals(SignedApproval.REFUSAL_PC_ONLY, ApprovalRefusal.take())
        assertNull(ApprovalRefusal.take())
        // The three signature refusals still read as they did.
        assertEquals(
            SignedApproval.REFUSAL_NO_APPROVAL_KEY,
            SignedApproval.refusalIn("""{"owner_check":"no_approval_key"}"""),
        )
        assertEquals(SignedApproval.OFFER_WORDS, SignedApproval.refusalWords(SignedApproval.REFUSAL_NO_APPROVAL_KEY))
        assertNull(SignedApproval.refusalIn("""{"owner_check":"unreadable"}"""))
        assertNull(SignedApproval.refusalIn(null))
    }

    // ----------------------------------------------------------- plumbing ---

    @Test
    fun closingTheAddVoicePlateStopsARecording() {
        val voices = source("ui/screens/VoicesScreen.kt")
        assertTrue(
            "closing the plate leaves a take recording, and its clip lands in the next attempt",
            after(voices, "fun resetAdd()").contains("stopFlag.set(true)"),
        )
        assertTrue(
            "picking a file leaves a take recording",
            after(voices, "onFromFile = {").contains("stopFlag.set(true)"),
        )
    }

    @Test
    fun aFailedVoiceCheckKeepsItsRecordingsForARetry() {
        val screen = source("ui/screens/VoiceCheckScreen.kt")
        assertTrue(
            "a failed send throws away the twenty recordings",
            screen.contains("if (tested?.ok == true) for (k in clips.indices) clips[k] = null"),
        )
    }

    @Test
    fun trainingAndWakeClipsRefuseWhileLiveHasTheMicrophone() {
        val voice = source("voice/VoiceSession.kt")
        assertTrue(
            "training can open a second recorder beside Jarvis Live",
            after(voice, "suspend fun recordTrainingClip(").contains("liveOn()"),
        )
        assertTrue(
            "a wake clip can be recorded beside Jarvis Live",
            after(voice, "suspend fun deliverWakeClip(").contains("liveOn()"),
        )
    }

    @Test
    fun aDeadMicrophoneStopsLiveInsteadOfSpinning() {
        val live = source("service/LiveService.kt")
        assertTrue(
            "a dead microphone read is still treated as 'nothing said', so the loop spins",
            live.contains("if (!readFully(rec, buf)) throw MicStopped()"),
        )
        assertTrue("the exception the loop throws is gone", live.contains("private class MicStopped"))
    }

    @Test
    fun sendIsNotArmedWhileAPhotoIsBeingPrepared() {
        val home = source("ui/screens/HomeScreen.kt")
        assertTrue(
            "Send does not wait for a picture that is still being prepared",
            home.contains("state.link == LinkState.CONNECTED && !state.pictureBusy"),
        )
    }

    // ------------------------------------------------- the talk button ---

    @Test
    fun theTalkButtonsOwnCaptureStateCannotRestartTheGesture() {
        val button = source("ui/parts/VoiceButton.kt")
        // Code only: the file's own doc comment explains the old key in words,
        // and the forbidden pattern must be read from the CODE, not from the
        // explanation of why it was wrong.
        val code = button.lines()
            .filterNot {
                val t = it.trimStart()
                t.startsWith("//") || t.startsWith("/*") || t.startsWith("*")
            }
            .joinToString("\n")
        // The owner's report of 2026-10-13 - "the mic button ... doesnt work
        // if i tap it or hold it down" - was this: the pointerInput was keyed
        // on `capturing`, and `onBegin()` makes VoiceSession set CAPTURING
        // within a frame, so the key change RESTARTED the gesture; the
        // restarted gesture's `finally` saw no release and ran the teardown
        // branch, calling onCancel() straight after onBegin(). The keys are
        // `enabled` only now, and the flag is read live at finger-down.
        assertTrue(
            "the talk button's gesture is not keyed on `enabled` alone",
            button.contains(".pointerInput(enabled)"),
        )
        assertFalse(
            "`capturing` is a pointerInput key again - the gesture will restart and cancel itself",
            Regex("""pointerInput\([^)]*capturing""").containsMatchIn(code),
        )
        assertTrue(
            "`capturing` is not read through rememberUpdatedState",
            button.contains("rememberUpdatedState(capturing)"),
        )
        assertTrue(
            "the gesture does not read the live capture state at finger-down",
            button.contains("capturingNow.value"),
        )
        assertTrue(
            "the release decision is not the pure VoicePress.release",
            button.contains("VoicePress.release("),
        )
        // The cancel-on-teardown path is kept: a gesture disposed with no
        // release must still cancel, never send.
        assertTrue(
            "a torn-down gesture no longer cancels",
            button.contains("VoicePress.Release.CANCEL -> currentOnCancel.value()"),
        )
    }

    @Test
    fun fullScreensMicrophoneIsGatedOnThePcOfferingIt() {
        val home = source("ui/screens/HomeScreen.kt")
        // The whole of VoiceBar, not a fixed character window: a More control
        // now sits above the microphone in the same bar, and the old 2,000
        // character window would have pushed these lines out of view.
        val voiceBar = home.substringAfter("private fun VoiceBar(")
            .substringBefore("private fun ReplyPeek(")
        assertTrue(
            "Full screen draws its microphone for a PC that has not offered push-to-talk",
            voiceBar.contains("if (state.voiceOffered) {"),
        )
        assertTrue(
            "Full screen's microphone is enabled without the PC's own voice offer",
            voiceBar.contains("enabled = state.voiceOffered &&"),
        )
    }

    // ------------------------------------------------- the shared More menu ---

    @Test
    fun theMovedChatControlsLiveInOneSharedMenu() {
        val home = source("ui/screens/HomeScreen.kt")
        val composer = home.substringAfter("private fun Composer(").substringBefore("\n@Composable")
        // The whole of VoiceBar again - see fullScreensMicrophoneIsGated...
        val voiceBar = home.substringAfter("private fun VoiceBar(")
            .substringBefore("private fun ReplyPeek(")
        val menu = home.substringAfter("private fun HomeMoreMenu(")
        // The chat bar keeps only the typing box, Send and the microphone -
        // and the one button that opens the rest (the owner's ask of
        // 2026-10-25). None of the moved controls may be drawn in it.
        for (moved in listOf(
            "FocusPresetChip(",
            "TemporaryChatStrip(",
            "state.pictureOffered",
            "state.thinkOffered",
        )) {
            assertFalse("the chat bar still draws $moved", composer.contains(moved))
        }
        assertTrue("the chat bar has no More control", composer.contains("onClick = onOpenMore"))
        // The full-screen face bar opens the SAME menu (one shared menu, not
        // a second list that can drift).
        assertTrue("the face bar has no More control", voiceBar.contains("onClick = onOpenMore"))
        // The "why the microphone is greyed" line must survive on both
        // surfaces: moving a control must not move its explanation with it.
        assertTrue(
            "the chat bar no longer says why the microphone is greyed",
            composer.contains("MicWords.heldLine("),
        )
        assertTrue(
            "the full-screen bar no longer says why the microphone is greyed",
            voiceBar.contains("MicWords.heldLine("),
        )
        // ...and that one menu carries every moved control, under the same
        // offer gates the controls themselves used.
        for (word in listOf(
            "MoreMenuWords.PRESETS",
            "MoreMenuWords.PHOTO",
            "Thinking.ONE_SHOT_LABEL",
            "TemporaryChat.START",
            "ChatHistory.EARLIER_CHATS",
            "MoreMenuWords.NOTIFICATIONS",
            "MoreMenuWords.QUICK_NOTE",
        )) {
            assertTrue("the shared More menu does not offer $word", menu.contains(word))
        }
        // The coach button left PromptCoachBar for the menu: the bar must be
        // able to hide its own button and to be asked to coach from outside.
        val coachBar = source("ui/screens/PromptCoachBar.kt")
        assertTrue(
            "the coach bar cannot hide its own button",
            coachBar.contains("showButton: Boolean = true"),
        )
        assertTrue(
            "the coach bar cannot be asked to coach from outside",
            coachBar.contains("request: Int = 0"),
        )
        // The two controls the owner asked to have gone really are gone from
        // Home: the redundant "Open the Brain →" caption and the Find button
        // (Find moved into Help - FindAnythingTest holds that side). The
        // caption is pinned by its action, not its words: the file's own
        // comments quote the removed words to explain them.
        assertFalse(
            "the removed \"Open the Brain →\" caption is back on Home",
            home.contains(".pressable(onClick = actions.onOpenBrain)"),
        )
        assertFalse(
            "a Find button is back on Home",
            home.contains("com.jarvis.client.ui.FindWords.BUTTON"),
        )
    }
}
