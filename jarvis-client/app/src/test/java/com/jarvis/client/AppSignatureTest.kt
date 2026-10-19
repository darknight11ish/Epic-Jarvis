package com.jarvis.client

import com.jarvis.client.platform.AppSignature
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The installed-APK signing fingerprint shown in Settings -> About (release
 * safety, 2026-10-18). The Android half is `AppSignature.installed`; these are
 * the pure rules behind the line, so they run on a plain JVM.
 */
class AppSignatureTest {

    /** SHA-256("abc"), the standard NIST vector. */
    private val abc = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    @Test
    fun `the certificate bytes are hashed as lowercase 64-hex`() {
        val got = AppSignature.sha256("abc".toByteArray())
        assertEquals(abc, got)
        assertEquals(64, got!!.length)
        assertTrue(got.matches(Regex("^[0-9a-f]{64}$")))
    }

    @Test
    fun `no certificate reads as nothing, never as a zero fingerprint`() {
        assertNull(AppSignature.sha256(null))
        assertNull(AppSignature.sha256(ByteArray(0)))
    }

    @Test
    fun `the settings line shows eight to sixteen characters, twelve by default`() {
        assertEquals(abc.take(12), AppSignature.short(abc))
        assertEquals(8, AppSignature.short(abc, 8)!!.length)
        assertEquals(16, AppSignature.short(abc, 16)!!.length)
        // Out-of-range requests are clamped into 8..16, never shortened to
        // something that would match too much.
        assertEquals(8, AppSignature.short(abc, 4)!!.length)
        assertEquals(16, AppSignature.short(abc, 64)!!.length)
    }

    @Test
    fun `the line is the plain label and the short digest`() {
        assertEquals("Signed by ${abc.take(12)}", AppSignature.line(abc))
        assertTrue(AppSignature.line(abc)!!.startsWith("Signed by "))
        assertEquals(AppSignature.SHORT_CHARS, AppSignature.short(abc)!!.length)
    }

    @Test
    fun `a missing or non-hex signature reads as nothing`() {
        assertNull(AppSignature.short(null))
        assertNull(AppSignature.short(""))
        assertNull(AppSignature.short("   "))
        assertNull(AppSignature.short("not a digest"))
        assertNull(AppSignature.short("AA:BB:CC"))
        assertNull(AppSignature.line(null))
        // keytool's uppercase form is normalised, not rejected outright.
        assertEquals(abc.take(12), AppSignature.short(abc.uppercase()))
    }
}
