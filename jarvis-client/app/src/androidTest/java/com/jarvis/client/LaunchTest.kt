package com.jarvis.client

import android.Manifest
import android.util.Log
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.jarvis.client.platform.CrashLog
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Does the app start.
 *
 * This is the test that was missing, and its absence is not a detail: the
 * suite compiled the APK and ran unit tests and never once launched it, so a
 * throw in `onCreate` shipped with a green tick on every check. Every "CI is
 * green" I reported was green on a build that could not open.
 *
 * It is deliberately shallow. A deep UI test would need Compose's test rule,
 * and the reactor runs an unbounded `withFrameNanos` loop that Compose's test
 * clock reads as "not idle" — so the rule would wait forever for a face that
 * never stops. Reaching RESUMED without throwing is the property that was
 * actually broken, and it is worth far more than nothing.
 *
 * The crash log doubles as the oracle. A throw on a background thread would
 * not fail `ActivityScenario`, but it does reach the handler installed in
 * `Application.onCreate`, so asserting the file is absent catches what the
 * lifecycle state cannot.
 */
@RunWith(AndroidJUnit4::class)
class LaunchTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    /** Whether this device let the test grant POST_NOTIFICATIONS (see [grantNotifications]). */
    private var granted = true

    @Before
    fun clean() {
        CrashLog.clear(context)
        granted = grantNotifications()
    }

    /**
     * Granted up front, or the app's own permission prompt covers the activity
     * and it never reaches RESUMED.
     *
     * MainActivity asks for POST_NOTIFICATIONS the first time it is paired -
     * which is the whole point of that ask, because without the permission no
     * approval is ever announced. A system permission dialog on top means the
     * activity under it is STARTED rather than RESUMED: Android behaving
     * correctly, not the app failing to start. So the test grants the
     * permission instead of weakening the assertion to STARTED - a weaker
     * assertion would also stop catching "the app did not come up", which is
     * the only thing this test exists for.
     *
     * UiAutomation rather than androidx.test's GrantPermissionRule, so this
     * does not add a dependency that cannot be resolved or verified from this
     * branch. grantRuntimePermission is public API from 28; minSdk here is 33.
     *
     * **Returns whether the grant really happened**, and that matters: some
     * OEM builds refuse it to the shell the instrumentation runs as, from
     * inside the platform. Measured on the owner's OnePlus CPH2419 (Android 15)
     * on 2026-10-09: `SecurityException: grantRuntimePermission: Neither user
     * 2000 nor current process has android.permission.GRANT_RUNTIME_PERMISSIONS`,
     * thrown out of `@Before`, failing all three tests of this class - and it
     * stopped the whole instrumented run with them, so `TokenStoreTest` and
     * `FaceRenderTest` (which runs later) never ran at all. The crash log is
     * the real oracle, so the run is allowed to continue without the grant
     * (see [assertCameUp]).
     */
    private fun grantNotifications(): Boolean = runCatching {
        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(
            context.packageName,
            Manifest.permission.POST_NOTIFICATIONS,
        )
        true
    }.getOrElse {
        Log.w(
            "JarvisLaunch",
            "the shell could not grant POST_NOTIFICATIONS (${it.javaClass.simpleName}: ${it.message}); " +
                "the app's own prompt may cover the activity, so only STARTED is asserted",
        )
        false
    }

    /**
     * The app really came up. RESUMED is the assertion the class was written
     * for, and it is kept whenever the permission was granted. When the
     * platform refused the grant, the app's own prompt is on top and no dialog
     * this test may touch can be dismissed, so STARTED is accepted instead -
     * the reason is in the device log, and [assertNoCrash] is unchanged.
     */
    private fun assertCameUp(scenario: ActivityScenario<MainActivity>, where: String) {
        if (granted) {
            assertEquals("MainActivity did not reach RESUMED ($where)", Lifecycle.State.RESUMED, scenario.state)
        } else {
            assertTrue(
                "MainActivity did not even reach STARTED ($where; state ${scenario.state})",
                scenario.state.isAtLeast(Lifecycle.State.STARTED),
            )
        }
    }

    @Test
    fun launchesFromColdWhenUnpaired() {
        // The out-of-the-box path: no host, no token, straight to pairing.
        JarvisRuntime.initialize(context)
        JarvisRuntime.settings.setHost("")

        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            assertCameUp(scenario, "unpaired")
            settle()
            assertNoCrash()
        }
    }

    @Test
    fun launchesWhenPaired() {
        // The other half, and the one that composes the most: home draws the
        // reactor, the theme system, the link bar and the composer. An address
        // that refuses instantly keeps it honest without needing a server —
        // the app has to render its offline state rather than a happy path.
        JarvisRuntime.initialize(context)
        JarvisRuntime.settings.setHost("127.0.0.1:1")
        JarvisRuntime.tokens.setToken("instrumentation-test-token")

        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            assertCameUp(scenario, "paired")
            settle()
            assertNoCrash()
        }
    }

    @Test
    fun theRuntimeStartsOnRealHardware() {
        // The Keystore, the preferences and the OkHttp client, none of which a
        // JVM unit test touches. This is also the function that threw.
        JarvisRuntime.initialize(context)
        assertTrue("the runtime reported it never initialised", JarvisRuntime.isInitialized)

        JarvisRuntime.tokens.setToken("round-trip")
        assertEquals("round-trip", JarvisRuntime.tokens.token())
        assertTrue(JarvisRuntime.tokens.hasToken())
    }

    /** Lets the first frames draw, so a throw during composition surfaces. */
    private fun settle() {
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        Thread.sleep(1_500)
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
    }

    private fun assertNoCrash() {
        assertNull(
            "something threw during startup:\n" + (CrashLog.read(context) ?: ""),
            CrashLog.read(context),
        )
    }
}
