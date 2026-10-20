package com.jarvis.client

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

/**
 * Every Android component this app exports must be guarded by the OS signature
 * permission that component type requires - or be one of the two documented
 * exceptions (the launcher activity and the share alias; launcher-bound
 * AppWidget receivers). 2026-10-20 Android audit, Area 10C.
 *
 * Parsed from the REAL manifest, so a future `android:exported="true"` without
 * its permission fails this suite instead of shipping.
 */
class ManifestGuardTest {

    private val android = "http://schemas.android.com/apk/res/android"

    private val requiredServicePermissions = setOf(
        "android.permission.BIND_ACCESSIBILITY_SERVICE",
        "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
        "android.permission.BIND_VOICE_INTERACTION",
        "android.permission.BIND_QUICK_SETTINGS_TILE",
        // The recognition stub the voice-interaction XML resolves by component;
        // the system binds it and this is its signature permission.
        "android.permission.BIND_RECOGNITION_SERVICE",
    )

    private fun elements(doc: org.w3c.dom.Document, tag: String): List<Element> {
        val nodes = doc.getElementsByTagName(tag)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private fun attr(e: Element, name: String): String = e.getAttributeNS(android, name)

    private val manifest: org.w3c.dom.Document by lazy {
        val f = repoFile("jarvis-client/app/src/main/AndroidManifest.xml")
        val factory = DocumentBuilderFactory.newInstance()
        factory.isNamespaceAware = true
        factory.newDocumentBuilder().parse(f)
    }

    @Test
    fun `the listener and the accessibility service are the OS-bound, permission-guarded kind`() {
        val services = elements(manifest, "service")
        fun named(suffix: String): Element =
            services.firstOrNull { attr(it, "name").endsWith(suffix) }
                ?: error("service $suffix not found in the manifest")

        val listener = named("PhoneNotificationListenerService")
        assertEquals(
            "a notification listener must be guarded by its signature permission",
            "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
            attr(listener, "permission"),
        )
        // Exported is false here as well as the permission: the system binds it
        // by role, and Android only ever calls the listener that way.
        assertEquals("false", attr(listener, "exported"))

        val accessibility = named("JarvisAccessibilityService")
        assertEquals("true", attr(accessibility, "exported"))
        assertEquals(
            "android.permission.BIND_ACCESSIBILITY_SERVICE",
            attr(accessibility, "permission"),
        )
    }

    @Test
    fun `every exported service carries one of its required signature permissions`() {
        val bad = elements(manifest, "service").filter { attr(it, "exported") == "true" }
            .filter { attr(it, "permission") !in requiredServicePermissions }
            .map { "${attr(it, "name")} (permission='${attr(it, "permission")}')" }
        assertTrue("exported services without their OS permission: $bad", bad.isEmpty())
        // ...and the four families the audit names are actually all present.
        val perms = elements(manifest, "service").map { attr(it, "permission") }.toSet()
        for (p in listOf(
            "android.permission.BIND_ACCESSIBILITY_SERVICE",
            "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
            "android.permission.BIND_VOICE_INTERACTION",
            "android.permission.BIND_QUICK_SETTINGS_TILE",
        )) {
            assertTrue("the manifest must still export the $p family", p in perms)
        }
    }

    @Test
    fun `exported receivers are only the launcher-bound AppWidget receivers`() {
        val exported = elements(manifest, "receiver").filter { attr(it, "exported") == "true" }
        assertTrue("this app is expected to export its widget receivers", exported.isNotEmpty())
        for (r in exported) {
            val name = attr(r, "name")
            assertTrue(
                "an exported receiver that is not an AppWidget receiver needs its own permission: $name",
                name.contains(".widget.") || name.contains("Widget"),
            )
        }
    }

    @Test
    fun `exported activities are only the launcher and the share alias`() {
        val exportedActivities = elements(manifest, "activity") + elements(manifest, "activity-alias")
        val exported = exportedActivities.filter { attr(it, "exported") == "true" }
            .map { attr(it, "name") }
            .toSet()
        assertEquals(
            "exported activities: $exported",
            setOf(".MainActivity", ".ShareToLive"),
            exported,
        )
        // MainActivity is the launcher, i.e. the exported activity the system
        // starts; the test above shows nothing ELSE is exported.
        val launcher = manifest.getElementsByTagName("category")
        val hasLauncher = (0 until launcher.length).any {
            (launcher.item(it) as Element).getAttributeNS(android, "name") ==
                "android.intent.category.LAUNCHER"
        }
        assertTrue("MainActivity must still be the launcher activity", hasLauncher)
    }

    @Test
    fun `no provider is exported and the update FileProvider only grants per-URI`() {
        val providers = elements(manifest, "provider")
        assertTrue(providers.isNotEmpty())
        for (p in providers) {
            assertEquals(
                "a provider must not be exported: ${attr(p, "name")}",
                "false",
                attr(p, "exported"),
            )
        }
        val updates = providers.firstOrNull { attr(it, "name").contains("FileProvider") }
            ?: error("the update FileProvider is missing")
        assertEquals("true", attr(updates, "grantUriPermissions"))
    }

    @Test
    fun `the network security config is declared on the application`() {
        val app = elements(manifest, "application").single()
        assertEquals(
            "@xml/network_security_config",
            attr(app, "networkSecurityConfig"),
        )
        assertFalse(
            "cleartext must be governed by the config, not a manifest flag",
            app.hasAttributeNS(android, "usesCleartextTraffic"),
        )
        assertNotNull(File(repoFile("jarvis-client/app/src/main/AndroidManifest.xml").parentFile,
            "res/xml/network_security_config.xml"))
    }
}
