package com.jarvis.client

import android.Manifest
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Build
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.util.Log
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceQuality
import com.jarvis.client.face.FaceView
import com.jarvis.client.face.Faces
import com.jarvis.client.face.Spec
import com.jarvis.client.face.gl.GL
import com.jarvis.client.platform.CrashLog
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * A photograph of every face, taken on the CI emulator, so the faces can be
 * LOOKED at by someone who does not have the phone in their hand.
 *
 * Nobody working on this app from the container can see a face on Android.
 * There is no emulator there and no Android compiler; GitHub Actions is the
 * only machine that ever draws one. [FaceRenderTest] proves each face draws
 * without throwing, which says nothing about what it draws - a face that is
 * a quarter the size it should be, or hairline-thin, or blank, passes it.
 * This test is the missing half: it saves a PNG of each face, which the
 * `face-shots` CI job pulls off the device and uploads as the
 * `jarvis-client-face-shots` artifact on every run, red or green.
 *
 * **It gates nothing, on purpose.** Its only assertion is the stall check
 * described at the end of this comment; every other step that can go wrong
 * is caught and written into `manifest.txt` next to the pictures instead of
 * failing the run. Whether a face is RIGHT is a judgement made by
 * looking, not a check a test can make, and a new way for the smoke job to go
 * red would change what publishes the APK - which this work was asked not to
 * do. The two things that SHOULD stop a release (a face that throws, a shader
 * that will not build) are already asserted by [FaceRenderTest], unchanged.
 * A face that crashes the whole process still fails this run, as it would
 * fail that one.
 *
 * What is photographed, so pictures from different runs can be compared:
 *  - every face in [Faces.all], in that order, in the IDLE state - the
 *    state that is nine tenths of screen-on time, with the default bindings;
 *  - at a fixed [SHOT_DP] dp square, on [Spec.BACKGROUND], after about
 *    [ANIMATE_MS] ms of animation;
 *  - at PHONE density, not the emulator's. The smoke AVD's panel is
 *    320x640 at 160 dpi (1x) - the emulator's own log says so - and at 1x
 *    the thing most worth seeing is invisible: a 1-pixel line is a normal
 *    line at 1x and a hairline at the ~2.75x of a real phone. So for this
 *    test only, the display is overridden to [PHONE_SIZE] at [PHONE_DPI]
 *    dpi (2.625x, a Pixel-class phone) with `wm size` / `wm density`, and
 *    put back afterwards, in a `finally`. `manifest.txt` records what the
 *    display actually reported, so a picture is never mistaken for more than
 *    it is.
 *
 * HOW the pixels are captured matters, because two of the faces are not in
 * the view hierarchy at all. Tokamak and Membrane draw into a GLSurfaceView,
 * which is its own Surface composited by SurfaceFlinger; `View.draw` and
 * `PixelCopy` on the window both miss it (the window holds only a transparent
 * hole where it sits). So this uses [android.app.UiAutomation.takeScreenshot]
 * - the whole display, as SurfaceFlinger composited it, GL layers and the
 *   overlay drawn over them included - and crops it to the face's bounds.
 *   Every face goes through the same path, so the twenty are comparable.
 *
 * Where the files go: the app's own storage is wiped when
 * `connectedDebugAndroidTest` uninstalls the app at the end of the suite, so
 * the PNGs are written to [SHOT_DIR] under /data/local/tmp - which belongs to
 * the adb shell, survives the uninstall, and is where the workflow pulls
 * from. The app process cannot write there itself; each file is streamed
 * through a shell `dd` (see [writeViaShell]).
 *
 * Not a Compose test rule, for the reason [LaunchTest] and [FaceRenderTest]
 * give: a face never goes idle, so the rule would wait forever.
 *
 * **Nothing here waits for the main thread to go idle, beyond the two waits
 * `ActivityScenario` makes itself at the start and the one when it closes.**
 * `Instrumentation.waitForIdleSync` has no time limit, and the test used to
 * make five such waits per face (two of its own, and one each inside
 * `ActivityScenario.launch`, `onActivity` and `close`) - a hundred a run. At
 * phone size on the CI emulator's software GPU a face can keep the main
 * thread busy enough that it never goes idle, and three runs in a row then
 * sat silent after face 4, 6 and 14 until the job's time limit, with the
 * emulator still alive and adb still answering. That is the likely reason,
 * not a proven one. So now: ONE activity for every face, the face swapped in
 * place; a poll for the face's layout instead of an idle wait; the screen
 * read through `runOnMainSync`, which needs the main thread to answer, not to
 * be idle; the face taken off the screen before the scenario closes; and a
 * watchdog ([STALL_MS]) that stops the run and says where it stuck, rather
 * than letting it hang until the job is cancelled. `manifest.txt` is saved
 * after every face, so a run that dies still says how far it got.
 *
 * A stall FAILS the test, after the pictures and the manifest are saved.
 * It runs in its own non-gating job, so red there means "not every face was
 * photographed" and costs nothing else.
 */
@RunWith(AndroidJUnit4::class)
class FaceShotTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()

    /** Everything that happened, written out as manifest.txt as it goes. */
    private val manifest = StringBuilder()

    /**
     * The one activity every face is shown in, once it is up. Held so that the
     * watchdog can take the face off the screen when the run stalls.
     */
    @Volatile private var activity: MainActivity? = null

    /** What the photographing thread is doing, and since when (for the watchdog). */
    @Volatile private var step = "starting"
    @Volatile private var stepSince = 0L

    /** Set by the watchdog: the photographing thread takes no further face. */
    @Volatile private var stopped = false

    // Two threads write here (the photographing thread and the watchdog), so
    // every read and write of the manifest holds the same lock.
    @Synchronized
    private fun note(line: String) {
        manifest.append(line).append('\n')
        Log.i(TAG, line)
    }

    @Synchronized
    private fun manifestText(): String = manifest.toString()

    private fun at(what: String) {
        step = what
        stepSince = SystemClock.elapsedRealtime()
    }

    /** Written after every face, so a run that dies part way still says how far it got. */
    private fun saveManifest() {
        runCatching { writeViaShell("manifest.txt", manifestText().toByteArray()) }
            .onFailure { Log.w(TAG, "manifest.txt could not be written", it) }
    }

    @Test
    fun photographEveryFaceIdle() {
        // The same setup FaceRenderTest uses, so MainActivity comes up the way
        // it is known to on this emulator: paired (to an address nothing
        // answers on), with the notification permission already granted so no
        // system dialog sits on top of the activity.
        runCatching {
            JarvisRuntime.initialize(context)
            JarvisRuntime.settings.setHost("127.0.0.1:1")
            JarvisRuntime.tokens.setToken("instrumentation-test-token")
            instrumentation.uiAutomation.grantRuntimePermission(
                context.packageName,
                Manifest.permission.POST_NOTIFICATIONS,
            )
        }.onFailure { note("setup: ${it.javaClass.simpleName}: ${it.message}") }

        // A fresh folder, so a picture can never be left over from a
        // previous run on the same device.
        shell("rm -rf $SHOT_DIR")
        shell("mkdir -p $SHOT_DIR")

        note("Jarvis face photographs - FaceShotTest")
        note("device: ${Build.MANUFACTURER} ${Build.MODEL}, API ${Build.VERSION.SDK_INT}")
        // What the one-time GPU check saw (GpuProbe). A software renderer puts
        // Auto adjust at Low before the first face draws.
        note("gpu: ${com.jarvis.client.platform.GpuProbe.renderer ?: "(not known yet)"}")
        note("each face: IDLE, ${SHOT_DP}dp square, ~${ANIMATE_MS}ms after it was laid out")
        note("capture: UiAutomation.takeScreenshot() (the composited display, GL layers included), cropped to the face")

        val overridden = emulatePhone()
        try {
            // The photographs are taken on a thread of their own, so that this
            // one can notice when they stop making progress. See the class
            // comment: a wait inside ActivityScenario has no time limit.
            at("launching MainActivity")
            val finished = CountDownLatch(1)
            Thread({
                try {
                    photographAll()
                } catch (t: Throwable) {
                    note("stopped: ${t.javaClass.simpleName}: ${t.message}")
                } finally {
                    finished.countDown()
                }
            }, "face-shots").apply {
                isDaemon = true
                start()
            }
            while (!finished.await(1, TimeUnit.SECONDS)) {
                val quietMs = SystemClock.elapsedRealtime() - stepSince
                if (quietMs > STALL_MS) {
                    stopped = true
                    note("STALLED: nothing happened for ${quietMs / 1000}s while $step; the faces after it were not photographed")
                    // Take the face off the screen, which lets a wait for the
                    // main thread to go idle return, so the stuck thread can
                    // finish instead of holding the activity open.
                    activity?.let { a -> runCatching { instrumentation.runOnMainSync { a.finish() } } }
                    break
                }
            }
        } finally {
            // Always, not only when emulatePhone said it worked: a size that
            // was applied before a later step failed still has to come off,
            // and resetting a display that was never overridden is a no-op.
            shell("wm density reset")
            shell("wm size reset")
            if (overridden) note("display override removed")
            saveManifest()
        }
        // After the pictures and the manifest are saved, never before.
        if (stopped) fail("FaceShotTest stalled while $step - see manifest.txt in the jarvis-client-face-shots artifact")
    }

    /**
     * Makes the emulator's 1x panel report itself as a Pixel-class phone.
     *
     * @return true when the override was applied, so the caller knows to take
     *   it off again. False leaves the pictures at the emulator's own density,
     *   which the manifest then says.
     */
    private fun emulatePhone(): Boolean = runCatching {
        note("display before: " + shell("wm size").oneLine() + " / " + shell("wm density").oneLine())
        shell("wm size $PHONE_SIZE")
        shell("wm density $PHONE_DPI")
        // The launcher and system UI reconfigure for the new size; let that
        // finish before the first activity of ours starts. (No activity of
        // ours is drawing yet, so this idle wait has nothing to starve it.)
        instrumentation.waitForIdleSync()
        Thread.sleep(1_500)
        note("display during: " + shell("wm size").oneLine() + " / " + shell("wm density").oneLine())
        true
    }.getOrElse {
        note("display override FAILED (${it.message}); shots are at the emulator's own density")
        false
    }

    /**
     * Every face, one after another, in ONE activity: the face on screen is
     * swapped in place rather than a new activity being launched for each,
     * because every launch and close waits for the main thread to go idle
     * with no time limit (see the class comment).
     */
    private fun photographAll() {
        // Which face was last laid out, and where, in window pixels. Set from
        // the layout pass, polled from this thread.
        val bounds = AtomicReference<Pair<String, Rect>?>(null)
        // The face on screen. Written on the main thread only.
        val shown = mutableStateOf<Face?>(null)

        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            at("replacing the home screen")
            // Home is replaced wholesale by one face on the ground colour: no
            // status line, no chat, no overlay - nothing that differs between
            // runs except the face itself.
            scenario.onActivity { a ->
                activity = a
                a.setContent {
                    val f = shown.value
                    Box(
                        Modifier.fillMaxSize().background(Spec.BACKGROUND),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (f != null) {
                            // key: each face starts from scratch, as it did
                            // when every face had an activity of its own.
                            key(f.id) {
                                FaceView(
                                    state = FaceState.IDLE,
                                    notches = 0,
                                    face = f,
                                    // requiredSize, not size: the same pixels
                                    // whatever constraints the window hands down.
                                    modifier = Modifier
                                        .requiredSize(SHOT_DP.dp)
                                        .onGloballyPositioned { c ->
                                            val r = c.boundsInWindow()
                                            bounds.set(
                                                f.id to Rect(
                                                    r.left.roundToInt(), r.top.roundToInt(),
                                                    r.right.roundToInt(), r.bottom.roundToInt(),
                                                ),
                                            )
                                        },
                                )
                            }
                        }
                    }
                }
            }

            for ((i, face) in Faces.all.withIndex()) {
                if (stopped) break
                val name = "%02d-%s.png".format(i + 1, face.id)
                at("photographing $name")
                runCatching { photograph(face, name, keepWholeScreen = i == 0, shown = shown, bounds = bounds) }
                    .onFailure { note("$name: NOT CAPTURED - ${it.javaClass.simpleName}: ${it.message}") }
                saveManifest()
            }

            // Nothing left drawing, so the idle wait inside close() has
            // nothing to starve it.
            at("closing the activity")
            if (!stopped) instrumentation.runOnMainSync { shown.value = null }
        }
        at("done")
    }

    /**
     * Where [id] was laid out, once it has been. A poll with a deadline,
     * where this used to be `waitForIdleSync`, which has none.
     */
    private fun waitForLayout(id: String, bounds: AtomicReference<Pair<String, Rect>?>): Rect {
        val deadline = SystemClock.elapsedRealtime() + LAYOUT_WAIT_MS
        while (SystemClock.elapsedRealtime() < deadline) {
            val placed = bounds.get()
            if (placed != null && placed.first == id) return placed.second
            Thread.sleep(50)
        }
        error("the face was never laid out (waited ${LAYOUT_WAIT_MS / 1000}s)")
    }

    private fun photograph(
        face: Face,
        name: String,
        keepWholeScreen: Boolean,
        shown: MutableState<Face?>,
        bounds: AtomicReference<Pair<String, Rect>?>,
    ) {
        val a = activity ?: error("the activity never came up")
        CrashLog.clear(context)
        GL.lastBuildFailure = null
        // runOnMainSync needs the main thread to ANSWER, not to be idle: it
        // runs between two frames of a face that never stops drawing.
        instrumentation.runOnMainSync { shown.value = face }
        val inWindow = waitForLayout(face.id, bounds)
        Thread.sleep(ANIMATE_MS)

        // Window -> screen offset, and the display's logical size, read on
        // the main thread where the views live.
        val offset = IntArray(2)
        val display = AtomicReference<Rect?>(null)
        // The ACTIVITY's density, not the application context's: it is
        // the one the face was laid out with after the override.
        val density = FloatArray(1)
        instrumentation.runOnMainSync {
            a.window.decorView.getLocationOnScreen(offset)
            display.set(a.windowManager.maximumWindowMetrics.bounds)
            density[0] = a.resources.displayMetrics.density
        }

        val screen = instrumentation.uiAutomation.takeScreenshot()
            ?: error("takeScreenshot returned nothing")
        // Read back as an ordinary bitmap: a screenshot may come back
        // GPU-backed, which cannot be cropped or compressed directly.
        val shot = if (screen.config == Bitmap.Config.HARDWARE) {
            screen.copy(Bitmap.Config.ARGB_8888, false)
        } else {
            screen
        }

        // If the capture came back at a different size from the logical
        // display (a panel-sized capture of an overridden display), scale
        // the crop to match rather than cutting the wrong square out.
        val logical = display.get()
        val sx = if (logical != null && logical.width() > 0) shot.width.toFloat() / logical.width() else 1f
        val sy = if (logical != null && logical.height() > 0) shot.height.toFloat() / logical.height() else 1f
        val left = ((inWindow.left + offset[0]) * sx).roundToInt().coerceIn(0, shot.width - 1)
        val top = ((inWindow.top + offset[1]) * sy).roundToInt().coerceIn(0, shot.height - 1)
        val right = ((inWindow.right + offset[0]) * sx).roundToInt().coerceIn(left + 1, shot.width)
        val bottom = ((inWindow.bottom + offset[1]) * sy).roundToInt().coerceIn(top + 1, shot.height)
        val crop = Bitmap.createBitmap(shot, left, top, right - left, bottom - top)

        writeViaShell(name, crop.png())
        if (keepWholeScreen) {
            // One uncropped screen, so a wrong crop can be told apart from
            // a wrong face without another CI run.
            writeViaShell("00-whole-screen-${name.removePrefix("01-")}", shot.png())
        }

        val lit = litShare(crop)
        note(
            "$name: ${crop.width}x${crop.height}px (${SHOT_DP}dp at %.3fx), ".format(density[0]) +
                "screen ${shot.width}x${shot.height}, " +
                "%.1f%% of pixels brighter than the ground".format(lit * 100f) +
                // What Auto adjust was drawing at when the picture was
                // taken: on a software renderer (this emulator) it starts
                // at Low, so a picture is never mistaken for High.
                ", quality ${FaceQuality.current.tier.id} at up to ${FaceQuality.current.fps} fps" +
                (if (FaceQuality.softwareGpu) " (software GPU)" else "") +
                (if (lit < 0.005f) " - LOOKS BLANK" else "") +
                (CrashLog.read(context)?.let { " - CRASH LOG: ${it.lineSequence().firstOrNull()}" } ?: "") +
                (GL.lastBuildFailure?.let { " - GL BUILD FAILURE: $it" } ?: ""),
        )
    }

    /**
     * The share of pixels noticeably brighter than the near-black ground: a
     * number next to each picture so a blank capture (a GL layer that was not
     * caught, a face that drew nothing) stands out in the manifest without
     * opening twenty files. Sampled on a grid - it is a sanity figure, not a
     * measurement.
     */
    private fun litShare(b: Bitmap): Float {
        val step = max(1, min(b.width, b.height) / 120)
        var lit = 0
        var seen = 0
        var y = 0
        while (y < b.height) {
            var x = 0
            while (x < b.width) {
                val c = b.getPixel(x, y)
                val luma = ((c shr 16) and 0xFF) + ((c shr 8) and 0xFF) + (c and 0xFF)
                if (luma > 3 * 24) lit++
                seen++
                x += step
            }
            y += step
        }
        return if (seen == 0) 0f else lit.toFloat() / seen
    }

    private fun Bitmap.png(): ByteArray = ByteArrayOutputStream().also {
        compress(Bitmap.CompressFormat.PNG, 100, it)
    }.toByteArray()

    /**
     * Runs [cmd] as the adb shell user and returns what it printed.
     *
     * The command is NOT passed through a shell - UiAutomation splits it on
     * spaces and executes it directly - so no redirection, pipes or quotes.
     * The output is read to the end because the command is only guaranteed to
     * have finished once its output is closed. A failure is noted and returns
     * an empty string rather than throwing.
     */
    private fun shell(cmd: String): String = runCatching {
        val pfd = instrumentation.uiAutomation.executeShellCommand(cmd)
        ParcelFileDescriptor.AutoCloseInputStream(pfd).use { it.readBytes().toString(Charsets.UTF_8) }
    }.getOrElse {
        // Never thrown on: see the class comment for why nothing here may
        // fail the run. The manifest says what went wrong instead.
        note("shell '$cmd' failed: ${it.javaClass.simpleName}: ${it.message}")
        ""
    }

    /**
     * Writes [bytes] to [SHOT_DIR]/[name] as the adb shell user.
     *
     * The app process cannot write to /data/local/tmp, and anything it can
     * write is deleted when the suite uninstalls it. So the bytes are fed to a
     * shell `dd` on its standard input: with no shell to interpret a `>`,
     * `dd of=` is the command that writes stdin to a named file by itself.
     * Returns once dd has exited (its stdout closes), so the file is complete
     * before the next one starts.
     */
    private fun writeViaShell(name: String, bytes: ByteArray) {
        val fds = instrumentation.uiAutomation.executeShellCommandRw("dd of=$SHOT_DIR/$name")
        val stdout = fds[0]
        val stdin = fds[1]
        ParcelFileDescriptor.AutoCloseOutputStream(stdin).use { it.write(bytes) }
        ParcelFileDescriptor.AutoCloseInputStream(stdout).use { it.readBytes() }
    }

    private fun String.oneLine() = trim().replace('\n', ' ')

    private companion object {
        const val TAG = "FaceShotTest"

        /** Where the PNGs land on the device; the workflow pulls this folder. */
        const val SHOT_DIR = "/data/local/tmp/jarvis-face-shots"

        /** The face's side, in dp. 945 px at [PHONE_DPI]. */
        const val SHOT_DP = 360

        /** How long a face animates before it is photographed. */
        const val ANIMATE_MS = 1_200L

        /** How long a face may take to be laid out after it is put on screen. */
        const val LAYOUT_WAIT_MS = 20_000L

        /**
         * How long the photographing thread may go without moving to its next
         * step before the run is called stalled. The one run that finished
         * (36074481330) took about 18 s a face, five idle waits each included,
         * so a minute and a half is several faces' worth of slack - and still
         * well inside the workflow's 900 s limit on the whole Gradle run.
         */
        const val STALL_MS = 90_000L

        /**
         * A Pixel-class phone: 1080 px wide at 420 dpi is 2.625x and 411 dp,
         * so a 360 dp face fits across it with room to spare. 1080x2160 keeps
         * the emulator panel's own 1:2 shape, so the override scales it
         * evenly rather than stretching it.
         */
        const val PHONE_SIZE = "1080x2160"
        const val PHONE_DPI = 420
    }
}
