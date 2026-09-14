package com.jarvis.client

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.TokenStore
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The one secret the app stores, against the real Android Keystore.
 *
 * Rule 3 is "no API keys in the app; the only secret it stores is the pairing
 * token", and `JARVIS-API.md` §1 says that for a native client the token is the
 * *only* thing protecting the backend — there is no CORS and no origin check
 * that means anything. So "it is encrypted" is a security property rather than
 * an implementation detail, and until now nothing checked it.
 *
 * A round trip alone cannot: `encrypt`/`decrypt` replaced by the identity
 * function passes a round-trip test perfectly. What catches that is reading the
 * preferences file the class writes and asserting the token is not in it.
 *
 * This is instrumentation rather than a JVM test because none of it exists off
 * a device: `AndroidKeyStore` is a hardware-backed provider, `Base64` is the
 * Android one, and the failure modes that matter — an invalidated key, a
 * restored backup — are Keystore behaviours. This class only became possible
 * when the emulator job started working.
 */
@RunWith(AndroidJUnit4::class)
class TokenStoreTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private lateinit var store: TokenStore

    private fun prefs() = context.getSharedPreferences("jarvis_secure", Context.MODE_PRIVATE)

    @Before
    fun setUp() {
        store = TokenStore(context)
        store.clear()
    }

    @After
    fun tearDown() {
        store.clear()
    }

    @Test
    fun aStoredTokenComesBackExactly() {
        val token = "jarvis_pair_9f3c-ΔΩ-Σ-东京"
        store.setToken(token)
        assertTrue(store.hasToken())
        assertEquals(token, store.token())
        // A second instance, because the real read happens on a cold start with
        // nothing cached in memory.
        assertEquals(token, TokenStore(context).token())
    }

    /** The property the round trip above cannot see. */
    @Test
    fun whatLandsOnDiskIsNotTheToken() {
        val token = "sk-not-really-but-treat-it-like-one-0123456789"
        store.setToken(token)

        val blob = prefs().getString("token_blob", null)
        assertNotNull("nothing was written at all", blob)
        assertFalse("the token was written in the clear", blob!!.contains(token))

        // And not merely absent from that one key: nothing this class writes
        // may contain it, however the storage is reshaped later.
        val everything = prefs().all.entries.joinToString { "${it.key}=${it.value}" }
        assertFalse("the token appears somewhere in the preferences", everything.contains(token))

        // Base64 of the plaintext would also "not contain" it as a substring
        // while being trivially reversible, so decode and check the bytes too.
        val decoded = android.util.Base64.decode(blob, android.util.Base64.NO_WRAP)
        assertFalse(
            "the stored bytes are the token with an encoding on top",
            String(decoded, Charsets.ISO_8859_1).contains(token),
        )
    }

    @Test
    fun clearingLeavesNothingBehind() {
        store.setToken("something")
        store.clear()
        assertFalse(store.hasToken())
        assertEquals("", store.token())
        assertNull(prefs().getString("token_blob", null))
    }

    /** Unpairing is `setToken("")`, so it must mean clear rather than store-empty. */
    @Test
    fun anEmptyTokenUnpairs() {
        store.setToken("paired")
        store.setToken("   ")
        assertFalse(store.hasToken())
        assertEquals("", store.token())
    }

    /**
     * A blob the Keystore cannot open — an invalidated key, a restored backup —
     * must read as "no token" and be dropped, not throw. A phone in that state
     * should ask for the token again, and every request afterwards should be
     * unauthenticated rather than authenticated with a value that cannot be
     * produced.
     */
    @Test
    fun anUnreadableBlobIsDroppedRatherThanThrown() {
        prefs().edit().putString("token_blob", "bm90LWEtdmFsaWQtY2lwaGVydGV4dA==").commit()
        assertTrue(store.hasToken()) // it looks like a token until it is opened
        assertEquals("", store.token())
        assertFalse("the unreadable blob was left in place", store.hasToken())
    }
}
