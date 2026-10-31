package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The source pins for the 2026-10-24 round-2 Android bundle (R8).
 *
 * Nine of these fixes sit in Compose or Android-service paths, and this repo has
 * no Compose UI test host (`androidTestImplementation` has no `ui-test-junit4`),
 * so the rule is held the way `AuditPlumbingTest`, `ExpiredCardShowsNoButtonsTest`
 * and `OpenPlaceTest` hold theirs: by reading the shipped source for the exact
 * line that implements it. Each pin FAILS on the tree before its group's fix.
 *
 * M7's pin is a real JUnit test and lives in `PicturesTest`.
 * Nothing here is a runtime pass: the phone and emulator are NOT-TESTABLE in
 * this session.
 */
class R8SourcePinTest {

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

    private fun after(src: String, marker: String): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        return src.substring(at, minOf(src.length, at + 2_000))
    }

    // ------------------------------------------- group 1: M6 + L3 ---

    @Test
    fun steeringAJobHoldsTheStaleLinkGate() {
        val rt = source("JarvisRuntime.kt")
        assertTrue(
            "taskAct moves work on the PC with no stale-link gate",
            after(rt, "suspend fun taskAct(").contains("actionBlocker()"),
        )
        assertTrue(
            "taskAnswer moves work on the PC with no stale-link gate",
            after(rt, "suspend fun taskAnswer(").contains("actionBlocker()"),
        )
    }

    @Test
    fun aBriefingNotificationWritesTheResumePointFirst() {
        val rt = source("JarvisRuntime.kt")
        assertTrue(
            "onBriefingReady can replay and re-ring after a kill inside the 2 s window",
            after(rt, "private fun onBriefingReady(").contains("flushResumePoint()"),
        )
    }

    // ------------------------------------------- group 2: M11 ---

    @Test
    fun theSwipeGestureIsKeyedOnTheGatesItReads() {
        val card = source("ui/approval/ApprovalCard.kt")
        assertTrue(
            "the swipe keeps the canApprove/canDeny of the composition that created it",
            card.contains("pointerInput(item.id, canApprove, canDeny, replace)"),
        )
    }

    // ------------------------------------------- group 3: M10 ---

    @Test
    fun theSandboxPlateKeepsReadingWhileACardWaits() {
        val plate = source("ui/screens/SandboxPlate.kt")
        assertTrue(
            "the sandbox plate polls once, so a decided card still reads as waiting",
            plate.contains("while (panel?.waiting == true)"),
        )
    }

    // ------------------------------------------- group 4: M3 ---

    @Test
    fun briefMeNowKeepsWhatThePlateAlreadyRead() {
        val plate = source("ui/screens/BriefingPlate.kt")
        val brief = plate.substringAfter("fun briefNow(").substringBefore("fun whatDidIMiss(")
        assertTrue(
            "briefNow replaces the whole view with /now's answer, which has no setups/senders",
            brief.contains("view?.setups"),
        )
    }

    // ------------------------------------------- group 5: M4 ---

    @Test
    fun goalsDrawTheRedactedViewWhileTheListsAreHidden() {
        val plate = source("ui/screens/GoalsPlate.kt")
        assertTrue("the goals rows are built from the raw view", plate.contains("Goals.ordered(shown)"))
        assertFalse("the raw view is still fed to the rows", plate.contains("Goals.ordered(view)"))
    }

    // ------------------------------------------- group 7: M2 + L2 ---

    @Test
    fun aRotationDoesNotReApplyTheShare() {
        val ma = source("MainActivity.kt")
        val share = after(ma, "private fun readShareIntent(")
        assertFalse(
            "the text share still ignores `fresh`, so it doubles on a rotation",
            share.contains("if (!text.isNullOrEmpty()) sharedText.value = text"),
        )
        assertTrue("the text branch does not honour `fresh`", share.contains("if (fresh && !text.isNullOrEmpty())"))
        assertTrue("the picture branch does not honour `fresh`", share.contains("if (!fresh) return"))
    }

    @Test
    fun theCaptureFlagOutlastsTheExitFade() {
        val ma = source("MainActivity.kt")
        val start = ma.indexOf("val handoffShown = nav.current == Screen.HANDOFF")
        assertTrue(start >= 0)
        val flags = ma.substring(start, minOf(ma.length, start + 2_500))
        assertTrue(
            "FLAG_SECURE is cleared the instant HANDOFF is left, while it is still drawn",
            flags.substringBefore("clearFlags").contains("delay("),
        )
    }

    // ------------------------------------------- group 8: M1 ---

    @Test
    fun theCardRaisingWritesOutlastTheApprovalWait() {
        val api = source("net/JarvisApi.kt")
        val limit = after(api, "suspend fun setLimit(")
        assertTrue("a limits change dies at the 20 s client", limit.contains("cardCall"))
        assertFalse("a limits change still runs on shortCall", limit.contains("shortCall.newCall(req)"))
        val attention = after(api, "suspend fun setAttentionLimit(")
        assertTrue("an attention change dies at the 20 s client", attention.contains("cardCall"))
        assertFalse("an attention change still runs on shortCall", attention.contains("shortCall.newCall(req)"))
        assertTrue(
            "a model switch still dies at the 20 s client",
            api.substringAfter("suspend fun switchModel(").substringBefore("suspend fun rollbackModel(")
                .contains("postCard"),
        )
        assertTrue(
            "a model install still dies at the 20 s client",
            after(api, "suspend fun installModel(").contains("postCard"),
        )
        // The restraint: ordinary writes keep the short client.
        assertTrue(api.contains("postJson(path, json, shortCall)"))
    }

    // ------------------------------------------- group 9: M9 ---

    @Test
    fun aFaceThatWillNotCompileCostsThatFaceNotTheApp() {
        val view = source("face/FaceView.kt")
        assertTrue("a face's draw can still take the process down", view.contains("drawOneFace(face,"))
        assertTrue("a failed face is not remembered", view.contains("failedFaces.add(face.id)"))
        assertTrue(
            "nothing draws the default face in its place",
            view.contains("drawOneFace(Faces.default,"),
        )
        assertTrue("an unexpected draw error still propagates", view.contains("catch (t: RuntimeException)"))
    }

    // ------------------------------------------- group 10: L7 ---

    @Test
    fun theTokamakWashIsNotRebuiltEveryFrame() {
        val view = source("face/FaceView.kt")
        assertTrue(
            "the wash circle is no longer drawn from the cached brush",
            view.contains("drawCircle(brush = tokamakWashBrush(hot, glowNow, radius)"),
        )
        assertFalse(
            "a radial-gradient brush is still built inline in the per-frame draw",
            view.contains("brush = Brush.radialGradient("),
        )
        assertTrue("the cached brush is gone", view.contains("tokamakWashBrush("))
    }

    // --------------------- group 11: the 2026-10-30 home-screen widget repaint ---

    /**
     * R8 (the tool that shrinks the release APK) merged the home-screen widget
     * classes into two, and the release build could no longer tell the cards
     * apart: Glance finds a widget's ids by the widget class's canonical name
     * (`GlanceAppWidgetManager.getGlanceIds`), so a merged class made every
     * board card repaint with the last slot's widget - the owner's "Jarvis
     * widget 2 still says No widget chosen" field-test finding. The mechanism,
     * the dexdump evidence and the phone symptom are all in
     * app/proguard-rules.pro under "A HOME-SCREEN WIDGET'S CLASS NAME IS ITS
     * IDENTITY TO GLANCE".
     *
     * This is a source pin and not a runtime pass, deliberately: `updateAll`'s
     * name lookup only goes wrong in the MINIFIED APK - the unit-test build is
     * not minified, so these classes are already distinct here and no JUnit
     * test can reproduce the merge. What this CAN do is go red the moment one of
     * the keep rules is deleted, which is the whole fix.
     */
    @Test
    fun everyHomeScreenWidgetClassKeepsItsOwnNameInReleaseBuilds() {
        val rules = repoFile("jarvis-client/app/proguard-rules.pro").readText()
        val classes = listOf(
            "ApprovalWidget",
            "QuickLinkWidget",
            "CalendarWidget",
            "JarvisBoardWidget",
            "JarvisBoardWidgetOne",
            "JarvisBoardWidgetTwo",
            "JarvisBoardWidgetThree",
        )
        for (name in classes) {
            val keep = Regex("(?m)^-keep class com\\.jarvis\\.client\\.widget\\.$name$")
            assertTrue(
                "R8 may merge com.jarvis.client.widget.$name again: Glance tells the " +
                    "home-screen cards apart by canonical class name, and a merge made " +
                    "every board card repaint with the last slot's widget",
                keep.containsMatchIn(rules),
            )
        }
    }
}
