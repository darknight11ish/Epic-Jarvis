package com.jarvis.client.platform

import android.content.Context
import android.content.ContextWrapper
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Local network access on Android 17 (platform/LocalNetworkPermission.kt).
 *
 * WHAT THIS IS HERE TO KEEP TRUE, in one line: the app must never put a
 * permanent, unfixable warning on a phone whose Android has never heard of
 * `ACCESS_LOCAL_NETWORK`. `ContextCompat.checkSelfPermission` answers DENIED
 * for a permission the running platform does not know, so the tempting
 * implementation - ask the platform and believe it - reports "blocked" on
 * every Android 16 and 17 phone in use, for ever, on the one screen whose
 * whole job is to be believable. The permission is guarded by
 * [LocalNetworkPermission.required], and the tests below pin both halves:
 * below the gate the answer is ALLOWED without ever asking the platform, and
 * above it the gate is the DEVICE's API level compared against
 * [LocalNetworkPermission.FIRST_API].
 *
 * No hard-coded second copy of the manifest. The declaration is read out of
 * the real `app/src/main/AndroidManifest.xml` with an XML parser (as
 * PhoneAddressTest does for network_security_config.xml), so a rename in
 * either place fails here instead of shipping an inert declaration.
 *
 * WHAT A PLAIN JVM UNIT TEST CANNOT DO, said plainly rather than papered
 * over: it cannot vary `Build.VERSION.SDK_INT` (the mockable android.jar's
 * field is `static final`, so even reflection refuses to set it - measured,
 * not assumed). The live reading below the gate is therefore a real reading
 * of the platform the test runs on (0), and the at/above-37 side is pinned by
 * the source of `required()` plus `FIRST_API == 37` rather than by running it.
 * A one-line production seam - `internal fun requiredAt(api: Int): Boolean`
 * with `fun required() = requiredAt(Build.VERSION.SDK_INT)` - would let the
 * 36/37/38 boundary be exercised for real; it is not added here because
 * production files belong to whoever is building this feature.
 */
class LocalNetworkPermissionTest {

    /**
     * A stand-in for a platform that has never heard of the permission - which
     * is what every Android 16 and 17 phone this app has run on is, at
     * `targetSdk 36`. `checkPermission` answers [PackageManager.PERMISSION_DENIED]
     * exactly as the real platform does for an unknown permission, and counts
     * the asking so a test can prove the guard returns before the platform is
     * touched at all.
     *
     * ContextWrapper(null) rather than a Context subclass because Context has
     * dozens of abstract methods and none of them matter here: only
     * `checkPermission` is ever reached, and a guard that held would reach
     * nothing.
     */
    private class UnknownPermissionPlatform : ContextWrapper(null) {
        var asked = 0
            private set

        override fun checkPermission(permission: String, pid: Int, uid: Int): Int {
            asked++
            return PackageManager.PERMISSION_DENIED
        }

        /** No system services on this stand-in; each readiness check falls back. */
        override fun getSystemService(name: String): Any? = null
    }

    // ---------------------------------------------------------------- (1)

    /**
     * THE RULE THAT MATTERS MOST. On a platform that does not gate the
     * permission, access is ALLOWED - and the platform is never asked, because
     * asking it is what produces the permanent false warning.
     */
    @Test
    fun `a platform that does not gate it is allowed, and is never asked`() {
        val platform = UnknownPermissionPlatform()

        assertFalse(
            "the premise: this JVM test platform (API ${Build.VERSION.SDK_INT}) does not gate " +
                "ACCESS_LOCAL_NETWORK, which is the state every phone in use is in",
            LocalNetworkPermission.required(),
        )
        assertTrue(
            "granted() must report TRUE when the platform cannot ask - a DENIED answer from a " +
                "platform that has never heard of the permission would put an unfixable warning " +
                "on the Checks screen for ever",
            LocalNetworkPermission.granted(platform),
        )
        assertFalse(
            "blocked() must report FALSE on a platform that does not gate it",
            LocalNetworkPermission.blocked(platform),
        )
        assertEquals(
            "the guard must return before the platform is asked: checkSelfPermission on a " +
                "permission the running platform does not know answers DENIED, so reaching it " +
                "at all is the bug this test exists for",
            0,
            platform.asked,
        )
    }

    // ---------------------------------------------------------------- (2)

    /**
     * CONTROL, and it is here because a check that cannot fail is not a check.
     *
     * Both implementations are run against the SAME platform in the same test:
     * the tempting one (ask `checkSelfPermission`, believe the answer) and the
     * real one. The tempting one answers "not granted" - which is why the
     * guard exists - and the real one answers TRUE. Drop the
     * `if (!required()) return true` from [LocalNetworkPermission.granted] and
     * the second assertion goes red; make the stand-in answer GRANTED and the
     * first one goes red. Neither assertion can pass vacuously.
     */
    @Test
    fun `CONTROL the tempting guardless check on the same platform reports blocked`() {
        val platform = UnknownPermissionPlatform()

        assertEquals(
            "the stand-in must answer exactly what a platform that has never heard of the " +
                "permission answers",
            PackageManager.PERMISSION_DENIED,
            ContextCompat.checkSelfPermission(platform, LocalNetworkPermission.PERMISSION),
        )
        assertTrue("the platform must have been asked by the guardless check", platform.asked > 0)

        assertFalse(
            "the tempting implementation (checkSelfPermission with no required() guard) " +
                "reports NOT granted here - this is the unfixable warning",
            naiveGranted(platform),
        )
        assertTrue(
            "the real implementation reports granted on that same platform; if this fails, " +
                "the required() guard is gone",
            LocalNetworkPermission.granted(platform),
        )
    }

    /** The tempting wrong implementation, spelled out so the control can compare. */
    private fun naiveGranted(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, LocalNetworkPermission.PERMISSION) ==
            PackageManager.PERMISSION_GRANTED

    // ---------------------------------------------------------------- (3)

    /** The declaration and the constant cannot drift apart. */
    @Test
    fun `the constant is the platform string and the real manifest declares it exactly once`() {
        assertEquals(
            "the platform's own string, which is the one thing that is not this repo's to rename",
            "android.permission.ACCESS_LOCAL_NETWORK",
            LocalNetworkPermission.PERMISSION,
        )

        val declared = declaredPermissions().mapNotNull { androidName(it) }
        assertEquals(
            "AndroidManifest.xml must declare ${LocalNetworkPermission.PERMISSION} exactly once; " +
                "it declares $declared",
            1,
            declared.count { it == LocalNetworkPermission.PERMISSION },
        )
    }

    /**
     * The declaration must stay plain. A `maxSdkVersion` would un-declare the
     * permission on exactly the Android versions that enforce it - the failure
     * mode this feature exists to prevent, wearing the costume of a tidy-up.
     */
    @Test
    fun `nothing narrows or removes the declaration`() {
        val element = declaredPermissions()
            .single { androidName(it) == LocalNetworkPermission.PERMISSION }

        assertFalse(
            "maxSdkVersion would un-declare ACCESS_LOCAL_NETWORK on the versions that enforce it",
            element.hasAttributeNS(ANDROID_NS, "maxSdkVersion"),
        )
        assertFalse(
            "tools:removePermission would strip the declaration at build time",
            element.hasAttributeNS(TOOLS_NS, "removePermission"),
        )
        assertFalse(
            "tools:ignore has nothing to ignore on a normal permission",
            element.hasAttributeNS(TOOLS_NS, "ignore"),
        )
    }

    // ---------------------------------------------------------------- (4)

    /** The API level the permission starts being enforced at. */
    @Test
    fun `the gate is Android 17 - API 37`() {
        assertEquals(37, LocalNetworkPermission.FIRST_API)
    }

    /** Below the gate: not required, so no dialog and no warning. */
    @Test
    fun `below the gate the permission is not required`() {
        assertTrue(
            "this unit test runs on a mocked platform that reports API " +
                "${Build.VERSION.SDK_INT}; the readings below are real readings of that, and if " +
                "it ever reaches ${LocalNetworkPermission.FIRST_API} they need re-reading",
            Build.VERSION.SDK_INT < LocalNetworkPermission.FIRST_API,
        )
        assertFalse(LocalNetworkPermission.required())
    }

    /** The live reading agrees with the boundary, whatever the platform says. */
    @Test
    fun `required is the device's API level against the gate`() {
        assertEquals(
            Build.VERSION.SDK_INT >= LocalNetworkPermission.FIRST_API,
            LocalNetworkPermission.required(),
        )
    }

    /**
     * The at/above-37 side, pinned where a JVM test can still reach it. A
     * hardcoded `false` (never ask, so the transport dies silently on Android
     * 17), an off-by-one, an inverted comparison or a gate on what the app
     * TARGETS instead of what the device RUNS all fail here.
     *
     * The BEHAVIOURAL half of this lives in
     * `requiredAt is the gate at the API 37 boundary`, which uses the
     * `requiredAt(api)` seam for 36, 37 and 38. This source pin is kept as well
     * because it is the only thing that catches `required()` ceasing to read the
     * device at all - `requiredAt` would stay correct while nothing called it.
     */
    @Test
    fun `the gate reads the device's version, not what the app targets`() {
        val source = codeOf(SOURCE)
        val body = requiredBody(source)
        val flat = body.replace(Regex("\\s+"), " ").trim()

        assertTrue(
            "required() must compare Build.VERSION.SDK_INT - the DEVICE's version. " +
                "It reads: $flat",
            flat.contains("Build.VERSION.SDK_INT"),
        )
        assertTrue(
            "required() must read the DEVICE's own version, through the one gate " +
                "function, so the boundary stays testable. It reads: $flat",
            flat.contains("requiredAt(Build.VERSION.SDK_INT)"),
        )
        // The comparison lives in requiredAt(api) since the seam was added, so it
        // is read from THAT function's body - checking for it in required()'s
        // would assert something that is no longer there and call a passing
        // delegation a failure.
        val gate = source.substringAfter("fun requiredAt", "")
            .substringBefore("\n    }")
            .replace(Regex("\\s+"), " ")
            .trim()
        assertTrue(
            "requiredAt must spell the comparison as `api >= FIRST_API`, so the number " +
                "lives in exactly one place and is not adjusted. It reads: $gate",
            gate.contains("api >= FIRST_API"),
        )
        assertFalse(
            "FIRST_API must not be adjusted in the comparison: `FIRST_API + 1` hides the gate " +
                "one Android version up. It reads: $gate",
            Regex("FIRST_API\\s*[+\\-*/]").containsMatchIn(gate),
        )
        assertFalse(
            "the gate must not be keyed to what the app targets: a phone on API 36 has no such " +
                "permission and never will, whatever this app's targetSdk says (build.gradle.kts " +
                "targets 36 today, so a targetSdk key would report 'nothing to do' on the " +
                "Android version that enforces it)",
            body.contains("targetSdk") || body.contains("TARGET_SDK") ||
                gate.contains("targetSdk") || gate.contains("TARGET_SDK"),
        )
    }

    /**
     * The boundary itself, BEHAVIOURALLY - 36 is not gated, 37 and 38 are.
     *
     * This is the half the source pin cannot prove. `Build.VERSION.SDK_INT` is
     * a `static final int` in the mockable jar, so a JVM test cannot set it
     * (measured: reflection throws `IllegalAccessException`) and this repo
     * deliberately carries no Robolectric. `requiredAt(api)` exists purely so
     * these three assertions can be ordinary ones.
     */
    @Test
    fun `requiredAt is the gate at the API 37 boundary`() {
        assertFalse(
            "API 36 must NOT be gated - that is every phone this app has run on, and " +
                "gating it would put an unfixable warning on all of them",
            LocalNetworkPermission.requiredAt(36),
        )
        assertTrue(
            "API 37 is the first version that enforces it; an off-by-one here loses the " +
                "whole transport on the version that matters",
            LocalNetworkPermission.requiredAt(37),
        )
        assertTrue(
            "and every version above it stays gated",
            LocalNetworkPermission.requiredAt(38),
        )
        // The boundary is exactly FIRST_API, not a number written twice.
        assertFalse(LocalNetworkPermission.requiredAt(LocalNetworkPermission.FIRST_API - 1))
        assertTrue(LocalNetworkPermission.requiredAt(LocalNetworkPermission.FIRST_API))
    }

    // ---------------------------------------------------------------- (5)

    /**
     * What the owner actually sees: on a phone that does not gate the
     * permission, the "Local network" row is OK, says so in words, and offers
     * no button - because a button that asks for a permission the platform has
     * never heard of resolves as a denial and leaves a warning that no tap can
     * clear.
     */
    @Test
    fun `the Checks row is OK with no button when nothing is gated`() {
        val rows = PlatformReadiness.report(UnknownPermissionPlatform(), "desk.ts.net")
        val row = rows.single { it.title == "Local network" }

        assertEquals(ReadinessItem.State.OK, row.state)
        assertNull("an unfixable warning is the bug; there must be no fix button here", row.fix)
        assertFalse(
            "the row must not tell the owner access is blocked when the platform does not gate " +
                "it. It reads: ${row.detail}",
            row.detail.contains("Not allowed"),
        )
        assertTrue(
            "the row must say there is nothing to do, so an owner reading Checks is not left " +
                "wondering. It reads: ${row.detail}",
            row.detail.contains("Nothing to do", ignoreCase = true),
        )
    }

    // ---------------------------------------------------------------- (6)

    /**
     * Single-sourced: both places that launch the request must name the one
     * constant, never the string again. A second literal is how the manifest
     * and the request drift apart - and the drift is silent, because the
     * request still resolves, it just resolves to a different permission.
     */
    @Test
    fun `both launchers ask for the one constant`() {
        for (file in listOf(MAIN_ACTIVITY, PAIRING_SCREEN)) {
            val text = codeOf(file)
            assertTrue(
                "$file must launch LocalNetworkPermission.PERMISSION",
                text.contains("LocalNetworkPermission.PERMISSION"),
            )
            assertFalse(
                "$file must not spell the permission string out a second time",
                text.contains("android.permission.ACCESS_LOCAL_NETWORK"),
            )
        }
    }

    // ------------------------------------------------------------- helpers

    /**
     * Found by walking up from Gradle's working folder, as PhoneAddressTest and
     * SpeechTextTest do - so this works whether the test JVM starts in
     * `jarvis-client/`, `jarvis-client/app/` or the repository root.
     */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** Production Kotlin with its comments removed, so prose cannot satisfy a check. */
    private fun codeOf(rel: String): String {
        val withoutBlocks = repoFile(rel).readText()
            .replace(Regex("/\\*.*?\\*/", RegexOption.DOT_MATCHES_ALL), " ")
        return withoutBlocks.lineSequence().joinToString("\n") { it.substringBefore("//") }
    }

    /**
     * The text of `required()` and nothing after it: from its declaration to
     * the next member (`\n    fun `), so a reordered or reformatted file still
     * reads correctly and the NEXT function's body cannot satisfy this check.
     */
    private fun requiredBody(source: String): String {
        val start = source.indexOf("fun required()")
        assertTrue("LocalNetworkPermission.kt has no fun required()", start >= 0)
        val end = source.indexOf("\n    fun ", start)
        return source.substring(start, if (end < 0) source.length else end)
    }

    /**
     * Namespace-aware on purpose: `android:name` is a namespaced attribute, and
     * a non-namespace-aware parser reads it as empty - which would make the
     * declaration look absent and this whole file pass for the wrong reason.
     */
    private val manifest: Element by lazy {
        DocumentBuilderFactory.newInstance()
            .apply { isNamespaceAware = true }
            .newDocumentBuilder()
            .parse(repoFile(MANIFEST))
            .documentElement
    }

    private fun declaredPermissions(): List<Element> = children(manifest, "uses-permission")

    private fun children(parent: Element, tag: String): List<Element> {
        val out = mutableListOf<Element>()
        val nodes = parent.childNodes
        for (i in 0 until nodes.length) {
            val n = nodes.item(i)
            if (n is Element && n.tagName == tag) out += n
        }
        return out
    }

    private fun androidName(element: Element): String? =
        element.getAttributeNS(ANDROID_NS, "name").ifEmpty { null }

    private companion object {
        const val ANDROID_NS = "http://schemas.android.com/apk/res/android"
        const val TOOLS_NS = "http://schemas.android.com/tools"

        const val CLIENT = "jarvis-client/app/src/main/"
        const val SOURCE = CLIENT + "java/com/jarvis/client/platform/LocalNetworkPermission.kt"
        const val MANIFEST = CLIENT + "AndroidManifest.xml"
        const val MAIN_ACTIVITY = CLIENT + "java/com/jarvis/client/MainActivity.kt"
        const val PAIRING_SCREEN = CLIENT + "java/com/jarvis/client/ui/screens/PairingScreen.kt"
    }
}
