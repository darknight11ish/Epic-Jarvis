package com.jarvis.client

import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.jarvis.client.face.Faces
import com.jarvis.client.platform.CrashLog
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Every offered face actually draws on real hardware, not just compiles.
 *
 * LaunchTest only ever launches with whatever face is currently the default
 * (Arc), so no other face has ever once been rendered by CI - a canvas face
 * nobody happened to pick during manual testing could throw on real hardware
 * and every check would still be green. That gap gets more dangerous, not
 * less, the moment a face is built on RuntimeShader: its AGSL source is
 * compiled at *runtime* by the device's own Skia build, and neither the unit
 * tests (`isReturnDefaultValues` stubs out android.graphics.RuntimeShader
 * rather than compiling anything through it) nor the plain launch test would
 * ever ask it to.
 *
 * So this launches once per face in [Faces.all] with that face persisted as
 * the active one - the same write AppearanceScreen's own picker makes
 * (`JarvisRuntime.appearance.setFace`) - and watches the real Home screen
 * render it for real. Deliberately not a Compose test rule, for the same
 * reason LaunchTest gives: the reactor runs an unbounded frame loop that
 * never goes idle, so the rule would hang forever waiting for a face that is
 * designed to never stop.
 */
@RunWith(AndroidJUnit4::class)
class FaceRenderTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    @Before
    fun clean() {
        CrashLog.clear(context)
    }

    @Test
    fun everyOfferedFaceRendersWithoutCrashing() {
        JarvisRuntime.initialize(context)
        JarvisRuntime.settings.setHost("127.0.0.1:1")
        JarvisRuntime.tokens.setToken("instrumentation-test-token")

        for (face in Faces.all) {
            CrashLog.clear(context)
            JarvisRuntime.appearance.setFace(face.id)
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                assertEquals(
                    "MainActivity did not reach RESUMED with face '${face.id}' active",
                    Lifecycle.State.RESUMED,
                    scenario.state,
                )
                settle()
                assertNull(
                    "face '${face.id}' threw while rendering:\n" + (CrashLog.read(context) ?: ""),
                    CrashLog.read(context),
                )
            }
        }
    }

    /** Lets the first frames draw, so a throw during composition or drawing surfaces. */
    private fun settle() {
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        Thread.sleep(1_500)
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
    }
}
