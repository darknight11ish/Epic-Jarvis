package com.jarvis.assistant

import com.jarvis.assistant.notifications.ApprovalSigner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class ApprovalSignerTest {

    private val secret = "pairing-secret"

    private fun reference(payload: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(payload.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    @Test
    fun `signs the documented canonical payload`() {
        val signature = ApprovalSigner.sign(
            secret = secret,
            id = "req-1",
            approved = true,
            deviceId = "device-9",
            atMs = 1_726_200_000_000,
            nonce = "nonce-abc",
        )
        assertEquals(reference("req-1|true|device-9|1726200000000|nonce-abc"), signature)
    }

    /** Pinned so a refactor cannot silently change what the desktop must verify. */
    @Test
    fun `signature is stable lowercase hex of the expected length`() {
        val signature = ApprovalSigner.sign(secret, "r", false, "d", 1, "n")
        assertEquals(64, signature!!.length)
        assertEquals(signature.lowercase(), signature)
    }

    @Test
    fun `approved flag is part of the signature`() {
        val yes = ApprovalSigner.sign(secret, "r", true, "d", 1, "n")
        val no = ApprovalSigner.sign(secret, "r", false, "d", 1, "n")
        assertNotEquals(yes, no)
    }

    @Test
    fun `nonce is part of the signature`() {
        val first = ApprovalSigner.sign(secret, "r", true, "d", 1, "n1")
        val second = ApprovalSigner.sign(secret, "r", true, "d", 1, "n2")
        assertNotEquals(first, second)
    }

    /** The fail-closed contract: no secret means no signature, not an empty one. */
    @Test
    fun `returns null rather than an empty signature when unpaired`() {
        assertNull(ApprovalSigner.sign("", "r", true, "d", 1, "n"))
    }
}
