package com.jarvis.client

import com.jarvis.client.data.PipLayout
import com.jarvis.client.data.PipMode
import com.jarvis.client.data.PipText
import com.jarvis.client.data.PipWords
import com.jarvis.client.net.ChatHistory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Picture-in-picture (`docs/PIP-DESIGN.md`, the owner's settled design of
 * 2026-10-11, built 2026-10-30): the small Jarvis window that stays on screen
 * while the owner uses other apps.
 *
 * The design asks for its claims to be PROVEN, not stated (§6), and lists what
 * a plain JVM can check. This file is that list, in order:
 *
 *  1. the mode mapping and the persistence rule (`PipMode.fromWire`);
 *  2. THE WHOLE TRUTH TABLE - every combination of the four inputs to
 *     [PipLayout.fromState]: the stored Off mode is [PipLayout.OFF] whatever the
 *     privacy state, and with "Hide memory lists and chat history" or App lock
 *     every OTHER mode is [PipLayout.HIDDEN] and never an answer layout (§6.1);
 *  2b. THE F-13 REGRESSION PIN (2026-10-31, the field-test defect where Off
 *     still produced a window): Off is decided BEFORE privacy in `fromState`,
 *     and auto-enter is keyed on the stored mode rather than the layout;
 *  3. THE FORBIDDEN-WORDS TEST ON THE VALUES - the one that makes §4 real
 *     rather than stated (§6.2);
 *  4. the first line, and only the first line (§6.3);
 *  5. ONE action, and it is Expand (§6.4);
 *  6. the manifest, read as text, and "no service gained a foregroundServiceType"
 *     (§6.6);
 *  7. the Settings row really being wired on this phone, and the overlay really
 *     yielding to the window (§2.2).
 *
 * WHAT THIS FILE DELIBERATELY DOES NOT CLAIM: whether the window actually
 * appears, what Android's own chrome does to it, whether the face holds its
 * frame budget inside it, or whether a tap on Expand returns the app. Those are
 * the phone steps in §7 - BLOCKED until the owner drives them, never a pass
 * from here.
 */
class PipTest {

    // ------------------------------------------------------------------
    //   1. The mode, and what a stored value means
    // ------------------------------------------------------------------

    @Test
    fun `every mode has its own wire value and its own label, and the wire round-trips`() {
        assertEquals(
            listOf("off", "face", "thread", "live"),
            PipMode.entries.map { it.wire },
        )
        for (mode in PipMode.entries) {
            assertEquals(mode, PipMode.fromWire(mode.wire))
        }
        assertEquals("no two modes share a label",
            PipMode.entries.size, PipMode.entries.map { it.label }.toSet().size)
        assertEquals("no two modes share a wire value",
            PipMode.entries.size, PipMode.entries.map { it.wire }.toSet().size)
    }

    @Test
    fun `the default is the face and the answer, and a missing or unknown value reads as it`() {
        // §2.1 and the lead's recorded call: mode 1 is the default because the
        // face and the answer is always true, where Live needs a session.
        assertEquals(PipMode.FACE, PipMode.DEFAULT)
        assertEquals(PipMode.FACE, PipMode.fromWire(null))
        assertEquals(PipMode.FACE, PipMode.fromWire(""))
        assertEquals(PipMode.FACE, PipMode.fromWire("live-ish"))
        assertEquals(PipMode.FACE, PipMode.fromWire("A value a newer build writes"))
        // ...and the explicit Off is NOT the same as "never chosen": Off is one
        // of the four values the owner picks, and it reads back as Off.
        assertEquals(PipMode.OFF, PipMode.fromWire("off"))
    }

    @Test
    fun `the setting is saved on this phone only, under the design's own key`() {
        val settings = file("jarvis-client/app/src/main/java/com/jarvis/client/data/ClientSettings.kt")
        assertTrue("no pip_mode key in ClientSettings",
            settings.contains("const val KEY_PIP_MODE = \"pip_mode\""))
        assertTrue("the stored value is not read through PipMode.fromWire",
            settings.contains("PipMode.fromWire(prefs.getString(KEY_PIP_MODE, null))"))
        assertTrue("the mode is not written back under that key",
            settings.contains("putString(KEY_PIP_MODE, mode.wire)"))
        // No route, no token, nothing about this phone's window leaves the
        // phone (§2.1): the setting's own file must not reach the network.
        assertFalse("ClientSettings must not call the API for pip mode",
            settings.substringAfter("val pipMode").substringBefore("fun setPipMode")
                .contains("api", ignoreCase = true))
    }

    // ------------------------------------------------------------------
    //   2. The truth table
    // ------------------------------------------------------------------

    @Test
    fun `the whole truth table - Off wins for Off, privacy wins for every other mode`() {
        var combinations = 0
        for (mode in PipMode.entries) {
            for (liveRunning in listOf(false, true)) {
                for (privateHidden in listOf(false, true)) {
                    for (appLock in listOf(false, true)) {
                        combinations += 1
                        val got = PipLayout.fromState(mode, liveRunning, privateHidden, appLock)
                        val why = "mode=$mode live=$liveRunning privateHidden=$privateHidden " +
                            "appLock=$appLock"
                        if (mode == PipMode.OFF) {
                            // The SETTING decides whether a window exists at
                            // all - F-13 (2026-10-31): with hidden lists on,
                            // Off used to fall through to HIDDEN and a window
                            // appeared after Home and after a fresh start.
                            assertEquals("$why must be OFF - the setting comes first", PipLayout.OFF, got)
                            assertFalse("$why must not draw an answer", got.answerShown)
                            assertFalse("$why must not draw the thread", got.threadShown)
                            assertFalse("$why must not draw Live", got.liveShown)
                        } else if (privateHidden || appLock) {
                            // §4 and §9.1: NEVER the answer, NEVER the
                            // conversation, NEVER Live - the dimmed face and
                            // one sentence for every mode the owner chose.
                            assertEquals("$why must be HIDDEN", PipLayout.HIDDEN, got)
                            assertFalse("$why must not draw an answer", got.answerShown)
                            assertFalse("$why must not draw the thread", got.threadShown)
                            assertFalse("$why must not draw Live", got.liveShown)
                        } else {
                            val want = when (mode) {
                                PipMode.OFF -> PipLayout.OFF   // handled above
                                // §2.4: while Live runs it takes the window;
                                // it gives it back when Live ends.
                                PipMode.FACE -> if (liveRunning) PipLayout.LIVE else PipLayout.FACE
                                PipMode.THREAD -> if (liveRunning) PipLayout.LIVE else PipLayout.THREAD
                                PipMode.LIVE -> if (liveRunning) PipLayout.LIVE else PipLayout.LIVE_OFF
                            }
                            assertEquals(why, want, got)
                        }
                    }
                }
            }
        }
        assertEquals("the four inputs must be driven exhaustively", 32, combinations)
    }

    /**
     * THE F-13 REGRESSION PIN (field test 2026-10-30/31, pass8 NOTES.md F-13;
     * dumps `p8-pip-off.xml`, `pip-13-check.png`, `pip-13d-off-freshstart.png`):
     * Off selected, yet a PiP window appeared after Home AND after a
     * force-stop/fresh start. Two one-line causes, and this test pins the
     * ORDER of both so neither can come back by a tidy-up:
     *
     *  1. `PipMode.fromState` must test the mode for Off BEFORE the privacy
     *     check - otherwise an Off mode answers HIDDEN while the lists are
     *     hidden (the owner's setting is on in the measured run).
     *  2. `MainActivity.buildPipParams` must key auto-enter on the stored MODE,
     *     never on the layout - HIDDEN != OFF, which armed the window.
     *
     * A source pin as well as a value test, because the bug was ordering and
     * the value test alone would not stop a different order coming back.
     */
    @Test
    fun `Off is decided before privacy, and auto-enter is keyed on the mode - F-13 cannot come back`() {
        // 1. The ordering inside fromState, read from the real file.
        val pipMode = file("jarvis-client/app/src/main/java/com/jarvis/client/data/PipMode.kt")
        val body = pipMode.substringAfter("fun fromState(").substringBefore("\n        }\n")
        val offAt = body.indexOf("if (mode == PipMode.OFF) return OFF")
        val hiddenAt = body.indexOf("if (privateHidden || appLock) return HIDDEN")
        assertTrue("fromState must still test the Off mode explicitly", offAt >= 0)
        assertTrue("fromState must still test the privacy state", hiddenAt >= 0)
        assertTrue(
            "the Off test must come BEFORE the privacy test - F-13 was this order reversed " +
                "(offAt=$offAt, hiddenAt=$hiddenAt)",
            offAt < hiddenAt,
        )
        // ...and the measured case, as a value: hidden lists ON + Off stored.
        assertEquals("F-13: Off with hidden lists on is still OFF",
            PipLayout.OFF,
            PipLayout.fromState(PipMode.OFF, liveRunning = false, privateHidden = true, appLock = false))
        assertEquals("F-13: Off with hidden lists AND App lock on is still OFF",
            PipLayout.OFF,
            PipLayout.fromState(PipMode.OFF, liveRunning = true, privateHidden = true, appLock = true))
        // The behaviour §7 step 9 needs is unchanged: a NON-Off mode that is
        // hidden is HIDDEN (an enterable window that says why it is empty).
        assertEquals("design §7 step 9: a hidden window is still enterable when the mode is on",
            PipLayout.HIDDEN,
            PipLayout.fromState(PipMode.FACE, liveRunning = false, privateHidden = true, appLock = true))

        // 2. Auto-enter is keyed on the stored mode, in the params builder.
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        val from = main.indexOf("private fun buildPipParams")
        assertTrue("buildPipParams is the one place the params are built", from >= 0)
        val block = main.substring(from, main.indexOf("\n    }", from))
        assertTrue("auto-enter must be keyed on the stored mode",
            block.contains("JarvisRuntime.settings.pipMode.value != PipMode.OFF"))
        assertTrue("...and set from that value", block.contains(".setAutoEnterEnabled(enterable)"))
        assertFalse("auto-enter must never be keyed on the layout again (F-13)",
            block.contains("setAutoEnterEnabled(layout != PipLayout.OFF)"))
    }

    @Test
    fun `each layout draws exactly one thing, and the aspect ratios are the design's`() {
        // 2026-10-31: no layout puts the chat's answer into the window any more.
        assertFalse("mode 1 is the face alone - no answer line", PipLayout.FACE.answerShown)
        assertFalse("mode 3's fallback shows its own one line, not the answer",
            PipLayout.LIVE_OFF.answerShown)
        assertTrue("mode 1 draws the face", PipLayout.FACE.faceShown)
        assertTrue("mode 3's fallback draws the face", PipLayout.LIVE_OFF.faceShown)
        assertTrue("mode 3's fallback draws one short line", PipLayout.LIVE_OFF.oneLineShown)
        assertFalse("mode 1 draws no line at all", PipLayout.FACE.oneLineShown)
        assertFalse(PipLayout.THREAD.answerShown)
        assertTrue(PipLayout.THREAD.threadShown)
        assertTrue(PipLayout.LIVE.liveShown)
        assertFalse("HIDDEN draws no content", PipLayout.HIDDEN.answerShown ||
            PipLayout.HIDDEN.threadShown || PipLayout.HIDDEN.liveShown)
        // §3: modes 1 and 3 about 16:9, mode 2 taller (9:16 in portrait).
        for (layout in listOf(PipLayout.OFF, PipLayout.HIDDEN, PipLayout.FACE,
                             PipLayout.LIVE, PipLayout.LIVE_OFF)) {
            assertEquals("$layout must be 16:9", 16 to 9, layout.aspectW to layout.aspectH)
        }
        assertEquals("the conversation is taller", 9 to 16,
            PipLayout.THREAD.aspectW to PipLayout.THREAD.aspectH)
        assertTrue("an aspect ratio cannot be zero or negative",
            PipLayout.entries.all { it.aspectW > 0 && it.aspectH > 0 })
    }

    // ------------------------------------------------------------------
    //   3. The forbidden words - on the values, not on a call
    // ------------------------------------------------------------------

    /**
     * The three things §4 says must never survive into the window, in the shape
     * the app really carries them: a made-up turn whose CHAT text is an ordinary
     * answer, while its other halves - what a card holds and what an email turn
     * names - are the forbidden pieces.
     *
     * The last part is the point of the test, and it is the part that would have
     * caught the plate this project lost: the window is handed CHAT TEXT and the
     * fixed words only (§4.3, §4.5, §5), so a card's title, body, recipients,
     * search words, plan or file names cannot arrive at a formatter at all. The
     * assertions below are on the VALUE that comes out, never on "the formatter
     * ran".
     */
    @Test
    fun `no approval, address or secret can appear in any PiP result, in any mode`() {
        val chatAnswer = "Tomorrow looks mild, with a light breeze in the afternoon."
        val forbidden = listOf(
            "Send this email?",                          // an approval's title
            "Send this email to the address below",      // an approval's body / plan
            "made.up@example.invalid",                   // a recipient
            "Re: the invoice",                           // a subject line
            "API_KEY=sk-live-0000",                      // a fake secret
            "4111 1111 1111 1111",                       // a fake card number
        )
        // The card and the email turn are the parts the PiP pipeline never sees:
        // there is no parameter here through which they could travel. This is
        // the same fixture the private-aloud cases use, applied to a glanceable
        // surface instead of a speaker.
        val cardTitle = forbidden[0]
        val cardBody = forbidden[1]
        val emailTo = forbidden[2]
        val emailSubject = forbidden[3]
        val actionWords = listOf(PipWords.EXPAND)
        var checked = 0
        for (mode in PipMode.entries) {
            for (privateHidden in listOf(false, true)) {
                for (appLock in listOf(false, true)) {
                    for (liveRunning in listOf(false, true)) {
                        checked += 1
                        val layout = PipLayout.fromState(mode, liveRunning, privateHidden, appLock)
                        val rendered = buildList {
                            addAll(actionWords)
                            add(PipWords.state(FaceState.IDLE, offline = false, stale = false,
                                approval = false))
                            when (layout) {
                                PipLayout.HIDDEN -> add(PipWords.LOCKED)
                                PipLayout.THREAD -> addAll(
                                    PipText.threadRows(listOf(
                                        ChatHistory.Exchange("What is the weather?", chatAnswer),
                                    )).map { it.text },
                                )
                                // An Off mode draws no answer at all: no
                                // window exists (F-13), and the fallback line
                                // is the state word only.
                                PipLayout.OFF -> add(PipWords.STANDING_BY)
                                // 2026-10-31: the normal window is the face alone,
                                // so it draws no answer text at all.
                                PipLayout.FACE -> {}
                                // Mode 3's fallback: one fixed short line, never
                                // the answer.
                                PipLayout.LIVE_OFF -> add(PipWords.LIVE_OFF)
                                PipLayout.LIVE -> add(PipWords.LIVE_LISTENING)
                            }
                        }
                        for (safe in rendered) {
                            for (bad in forbidden) {
                                assertFalse(
                                    "mode=$mode privateHidden=$privateHidden appLock=$appLock " +
                                        "live=$liveRunning leaked \"$bad\": $safe",
                                    safe.contains(bad),
                                )
                            }
                        }
                        if (layout == PipLayout.HIDDEN) {
                            // The other half: the hidden window says WHY, and
                            // shows no answer at all - empty is never mistaken
                            // for broken (§9.1).
                            assertTrue("the hidden window must say ${PipWords.LOCKED}",
                                rendered.contains(PipWords.LOCKED))
                            assertFalse("the hidden window must show no answer text",
                                rendered.any { it.contains(PipText.firstLine(chatAnswer)) })
                        } else if (layout == PipLayout.FACE || layout == PipLayout.LIVE_OFF) {
                            // The owner's revision (2026-10-31): the answer line
                            // is gone from both, so neither may draw it.
                            assertFalse("the face-first window must show no answer text",
                                rendered.any { it.contains(PipText.firstLine(chatAnswer)) })
                            assertTrue("it must still draw the face",
                                layout.faceShown)
                        }
                        // The fixture's card/email halves are never rendered,
                        // because nothing in the PiP pipeline carries them.
                        assertFalse(cardTitle.isNotEmpty() && rendered.any { it.contains(cardTitle) })
                        assertFalse(cardBody.isNotEmpty() && rendered.any { it.contains(cardBody) })
                        assertFalse(emailTo.isNotEmpty() && rendered.any { it.contains(emailTo) })
                        assertFalse(emailSubject.isNotEmpty() &&
                            rendered.any { it.contains(emailSubject) })
                    }
                }
            }
        }
        assertEquals(4 * 2 * 2 * 2, checked)
    }

    @Test
    fun `the window's code has no way to decide anything, and its only action is Expand`() {
        // A source pin, because the guarantee is structural: no approval type,
        // no pending list and no decision call may appear in the PiP layout's
        // own files (comments removed - the prose there says "approve" on
        // purpose, explaining WHY it cannot).
        for (path in listOf(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/PipWindow.kt",
            "jarvis-client/app/src/main/java/com/jarvis/client/data/PipMode.kt",
        )) {
            val code = stripComments(file(path))
            for (banned in listOf("JarvisRuntime.pending", "JarvisRuntime.decide(",
                                  "ApprovalNotifier", "PendingItem", "Approval(")) {
                assertFalse("$path must not reach $banned", code.contains(banned))
            }
        }
        assertTrue("the only action word is Expand", PipWords.EXPAND == "Expand")
        assertEquals("the fixed words are the owner's own sentences",
            "Hidden while Jarvis is locked.", PipWords.LOCKED)
        assertEquals("Live is off. Start it and it shows here.", PipWords.LIVE_OFF)
    }

    @Test
    fun `the PiP parameters carry exactly one action and it is Expand`() {
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        val from = main.indexOf("private fun buildPipParams")
        assertTrue("buildPipParams is the one place the params are built", from >= 0)
        val block = main.substring(from, main.indexOf("\n    }", from))
        assertEquals("exactly one RemoteAction in the whole file",
            1, Regex("RemoteAction\\(").findAll(main).count())
        assertTrue("the one action is Expand", block.contains("PipWords.EXPAND"))
        assertTrue("the one action is attached to the params",
            block.contains(".setActions(listOf(expand))"))
        assertFalse("a second action would be a decision surface (§5)",
            block.contains("addAction("))
        assertTrue("the aspect ratio comes from the layout",
            block.contains("Rational(layout.aspectW, layout.aspectH)"))
        assertTrue("auto-enter is armed from the stored mode, never from the layout",
            block.contains("JarvisRuntime.settings.pipMode.value != PipMode.OFF"))
        assertTrue("...and set from that value", block.contains(".setAutoEnterEnabled(enterable)"))
    }

    // ------------------------------------------------------------------
    //   4. The first line, and only the first line
    // ------------------------------------------------------------------

    @Test
    fun `the answer body is one line, ellipsised, and carries no markdown`() {
        val multi = "**Tomorrow** looks mild.\nSecond line with `code` and # heading.\nThird line."
        val one = PipText.firstLine(multi)
        assertFalse("no second line", one.contains("\n"))
        assertFalse("no markdown asterisks", one.contains("**"))
        assertFalse("no backticks", one.contains("`"))
        assertFalse("no heading marker", one.startsWith("#"))
        assertTrue("the words themselves are kept", one.contains("Tomorrow"))
        assertFalse("the second line must not be there", one.contains("Second line"))

        val long = "a".repeat(PipText.MAX_LINE * 2)
        val cut = PipText.firstLine(long)
        assertTrue("a long line is ellipsised", cut.endsWith("…"))
        assertTrue("and never longer than the line budget", cut.length <= PipText.MAX_LINE)

        assertEquals("an empty answer draws nothing rather than a guess", "", PipText.firstLine(""))
        assertEquals("whitespace only is empty too", "", PipText.firstLine("   \n\t "))
    }

    @Test
    fun `the conversation shows the last few messages, oldest first, with no input box`() {
        val thread = (1..6).map { n ->
            ChatHistory.Exchange(question = "question $n", answer = "answer $n")
        }
        val rows = PipText.threadRows(thread)
        assertEquals("four exchanges at most, two rows each", 8, rows.size)
        assertEquals("the newest exchange is last", "answer 6", rows.last().text)
        assertFalse("the oldest exchanges fall off the top",
            rows.any { it.text == "question 1" })
        assertTrue("the owner's rows are marked as theirs", rows.first().fromOwner)
        assertFalse("Jarvis's rows are marked as his", rows[1].fromOwner)
        assertEquals("nothing is drawn for an empty conversation", 0,
            PipText.threadRows(emptyList()).size)
        // No input box, no send button, no card: the layout's own file must not
        // contain a text field or a send call.
        val window = stripComments(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/PipWindow.kt"))
        for (banned in listOf("TextField", "BasicTextField", "JarvisRuntime.send", "onSend")) {
            assertFalse("the PiP window must not carry $banned", window.contains(banned))
        }
    }

    // ------------------------------------------------------------------
    //   5. The manifest, read as text (§6.6)
    // ------------------------------------------------------------------

    @Test
    fun `MainActivity declares picture-in-picture and the four config changes`() {
        val manifest = file("jarvis-client/app/src/main/AndroidManifest.xml")
        val at = manifest.indexOf("android:name=\".MainActivity\"")
        assertTrue("MainActivity is declared", at >= 0)
        val block = manifest.substring(at, manifest.indexOf(">", at))
        assertTrue("supportsPictureInPicture is not on MainActivity:\n$block",
            block.contains("android:supportsPictureInPicture=\"true\""))
        for (change in listOf("screenSize", "smallestScreenSize", "screenLayout", "orientation")) {
            assertTrue("configChanges must include $change:\n$block",
                block.contains(change))
        }
        assertTrue("and it must be a configChanges attribute",
            block.contains("android:configChanges="))
        // resizeableActivity was already there for the bubble, and stays.
        assertTrue("resizeableActivity must not be lost",
            block.contains("android:resizeableActivity=\"true\""))
        // PiP needs no permission, and this feature added none.
        assertFalse("picture-in-picture needs no permission",
            manifest.contains("PICTURE_IN_PICTURE", ignoreCase = true))
    }

    @Test
    fun `no service gained a foreground service type for this feature`() {
        val manifest = file("jarvis-client/app/src/main/AndroidManifest.xml")
        // Measured on main before this slice (2026-10-30): five services carry
        // a foregroundServiceType, each for its own already-shipped job. A PiP
        // window does not keep anything alive that is not already alive (§1),
        // so this number must not move.
        assertEquals("a service gained or lost a foregroundServiceType",
            5, Regex("foregroundServiceType=").findAll(manifest).count())
    }

    // ------------------------------------------------------------------
    //   6. The Settings row, and the overlay yielding to the window (§2.2)
    // ------------------------------------------------------------------

    @Test
    fun `the Settings row is wired on this phone under its own menu id`() {
        val screen = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt")
        assertTrue("no pip-mode item on the Settings screen",
            screen.contains("item(key = \"pip-mode\")"))
        assertTrue("the row is not hideable by its menu id",
            screen.contains("menus.shows(\"settings.pip-mode\")"))
        assertTrue("the row is not filtered by the Settings search",
            screen.contains("drawn(\"pip-mode\")"))
        assertTrue("the row does not open the Picture-in-picture section",
            screen.contains("PipSection("))
        val jump = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt")
        assertTrue("no jump entry for the row", jump.contains("Entry(\"Picture-in-picture\", \"pip-mode\")"))
        val search = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt")
        assertTrue("no search index row for the row",
            search.contains("key = \"pip-mode\", title = \"Picture-in-picture\""))
        val places = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt")
        assertTrue("the menu has no place on the phone",
            places.contains("\"pip-mode\" to \"settings.pip-mode\""))
        val open = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt")
        assertTrue("\"open picture-in-picture\" has no phone decision",
            open.contains("\"pip-mode\" to Where.Go(Screen.SETTINGS, \"pip-mode\")"))
        // The generated menu catalogue really carries the id (it is written by
        // tools/gen_menu_cases.py from backend/jarvis_menus.py, and
        // MenuVisibilityTest holds this file to the fixture).
        val menus = file("jarvis-client/app/src/main/java/com/jarvis/client/net/MenuCatalog.kt")
        assertTrue("the menu catalogue has no settings.pip-mode",
            menus.contains("Menu(\"settings.pip-mode\""))
    }

    @Test
    fun `the floating face yields while the window is up, and returns after`() {
        val overlay = file(
            "jarvis-client/app/src/main/java/com/jarvis/client/service/AvatarOverlayService.kt")
        assertTrue("the overlay does not watch the PiP window",
            overlay.contains("PipPresence.up"))
        assertTrue("the overlay does not hide while PiP is up",
            overlay.contains("view?.visibility = View.GONE"))
        assertTrue("the overlay does not show itself again when PiP ends",
            overlay.contains("view?.visibility = View.VISIBLE"))
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("MainActivity never sets the presence flag",
            main.contains("PipPresence.setUp("))
        assertTrue("the window's state does not come from the PiP callback",
            main.contains("override fun onPictureInPictureModeChanged("))
        assertTrue("the app draws its own PiP layout",
            main.contains("com.jarvis.client.ui.PipWindow("))
    }

    @Test
    fun `a live session takes the window and gives it back through the same rule`() {
        // §2.4 is one preference, not two things to keep in sync: the layout
        // function above is the only place Live takes the window over, and this
        // pins that MainActivity asks it with the running state rather than
        // deciding the swap itself.
        val main = file("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue("MainActivity does not hand the running state to the layout rule",
            main.contains("liveRunning = com.jarvis.client.voice.LiveRules.onHere(pipLiveStatus)"))
        assertNotEquals("an idle window and a running Live session must not draw the same thing",
            PipLayout.fromState(PipMode.FACE, liveRunning = false, privateHidden = false, appLock = false),
            PipLayout.fromState(PipMode.FACE, liveRunning = true, privateHidden = false, appLock = false))
    }

    // ------------------------------------------------------------------
    //   7. The owner's revision of 2026-10-31: face-first, icon controls
    // ------------------------------------------------------------------

    private val windowPath =
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/PipWindow.kt"

    @Test
    fun `the normal window is the face alone - no state word and no answer line`() {
        val window = stripComments(file(windowPath))
        assertTrue("mode 1 must draw the face alone",
            window.contains("PipLayout.FACE -> PipFaceOnly(face)"))
        assertTrue("mode 3's fallback must draw the face with its one fixed line",
            window.contains("PipLayout.LIVE_OFF -> PipFaceLine(face, PipWords.LIVE_OFF)"))
        assertFalse("the old answer composable must be gone", window.contains("PipAnswer("))
        assertFalse("no layout may draw the state word beside the face",
            window.contains("PipWords.state("))
        assertFalse("the cut-off answer line must not be drawn",
            window.contains("PipText.firstLine"))
        val faceOnly = window.substringAfter("private fun PipFaceOnly(")
            .substringBefore("\n}")
        assertTrue("the face must fill the window", faceOnly.contains("fillMaxSize"))
        assertTrue("it is the app's ONE face", faceOnly.contains("PipFace(face)"))
        val fallback = window.substringAfter("private fun PipFaceLine(")
            .substringBefore("\n}")
        assertTrue("the fallback draws the same face", fallback.contains("PipFace(face)"))
        assertTrue("the fallback keeps its one short line", fallback.contains("PipLine("))
        assertTrue("that line is the owner's own LIVE_OFF words",
            window.contains("PipWords.LIVE_OFF"))
    }

    @Test
    fun `the Live controls are icons that keep the exact same two calls`() {
        val window = stripComments(file(windowPath))
        val live = window.substringAfter("private fun PipLive(")
        assertTrue("the Live view draws the face", live.contains("PipFace(face)"))
        assertTrue("the face must fill the window", live.contains("fillMaxSize"))
        assertTrue("End Live keeps its runtime call",
            live.contains("JarvisRuntime.liveEndNow(\"owner\")"))
        assertTrue("Mic keeps its runtime call", live.contains("JarvisRuntime.liveMute("))
        assertTrue("the mic toggle still reads LiveRules.MIC_OFF",
            live.contains("LiveRules.MIC_OFF"))
        assertTrue("the end control is the end icon",
            live.contains("R.drawable.ic_pip_end_live"))
        assertTrue("the mic control chooses the mic-on icon",
            live.contains("R.drawable.ic_pip_mic_on"))
        assertTrue("the mic control chooses the mic-off icon",
            live.contains("R.drawable.ic_pip_mic_off"))
        assertTrue("the icons carry their words for accessibility",
            live.contains("contentDescription = description"))
        assertFalse("the old text-link controls must be gone", live.contains("Quiet("))
        assertTrue("the status line is still drawn as small text", live.contains("PipLine("))
        assertTrue("the listening word is still the status", live.contains("PipWords.LIVE_LISTENING"))
        assertTrue("the status still shows the title when there is one",
            live.contains("sign.title.isNotEmpty()"))
    }

    @Test
    fun `the two Live icon drawables exist and are the ones referenced`() {
        for (rel in listOf(
            "jarvis-client/app/src/main/res/drawable/ic_pip_end_live.xml",
            "jarvis-client/app/src/main/res/drawable/ic_pip_mic_off.xml",
            "jarvis-client/app/src/main/res/drawable/ic_pip_mic_on.xml",
        )) {
            val drawable = file(rel)
            assertTrue("$rel must be a vector", drawable.contains("<vector"))
            assertTrue("$rel must be a solid silhouette", drawable.contains("android:fillColor"))
        }
        val window = stripComments(file(windowPath))
        for (name in listOf("ic_pip_end_live", "ic_pip_mic_off", "ic_pip_mic_on")) {
            assertTrue("$name is not referenced by the window", window.contains(name))
        }
    }

    @Test
    fun `the hidden window is untouched by the face-first revision`() {
        val window = stripComments(file(windowPath))
        assertTrue("the hidden layout still draws PipHidden",
            window.contains("PipLayout.HIDDEN -> PipHidden(face)"))
        val hidden = window.substringAfter("private fun PipHidden(")
            .substringBefore("\n}")
        assertTrue("the hidden face is still dimmed", hidden.contains("DIM_ALPHA"))
        assertTrue("the hidden face is neutral", hidden.contains("FaceState.STANDBY"))
        assertTrue("the hidden window still says why", hidden.contains("PipWords.LOCKED"))
        assertFalse("the hidden window must not draw the conversation",
            hidden.contains("PipText.threadRows"))
        // The window's ONLY system action is still Expand, and nothing here
        // decides anything (the same banned list as section 3's pin).
        for (banned in listOf("JarvisRuntime.pending", "JarvisRuntime.decide(",
                              "ApprovalNotifier", "PendingItem", "Approval(")) {
            assertFalse("the PiP window must not reach $banned", window.contains(banned))
        }
    }

    // ------------------------------------------------------------------
    //   Helpers
    // ------------------------------------------------------------------

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun file(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** Source with `//` and `/* */` comments removed, so prose cannot trip a code pin. */
    private fun stripComments(src: String): String =
        src.replace(Regex("/\\*[\\s\\S]*?\\*/"), "")
            .replace(Regex("//[^\n]*"), "")
}
