package com.jarvis.client

import androidx.compose.ui.geometry.Offset
import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CALM_MOTION_RATE
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Calm motion (FaceView's `calmMotion`) may only ever make the face slower and
 * stiller - never faster, and never silent about a touch.
 *
 * Checked on FaceHost directly, because that is where the rule lives and it
 * needs no screen: the draw only reads what the host hands it.
 */
class FaceCalmMotionTest {

    private fun advanced(calm: Boolean, state: FaceState, steps: Int): FaceFrame {
        val host = FaceHost()
        repeat(steps) {
            host.advance(1f / 60f, state, null, null, Bindings.DEFAULTS, Arc, calm)
        }
        return host.snapshot()
    }

    @Test
    fun `calm motion is slower than full motion, never faster`() {
        val full = advanced(calm = false, state = FaceState.THINKING, steps = 120)
        val calm = advanced(calm = true, state = FaceState.THINKING, steps = 120)

        assertTrue("a calm face must still move", calm.tableAngle > 0f)
        assertTrue(
            "calm turned ${calm.tableAngle} rad against full motion's ${full.tableAngle}",
            calm.tableAngle < full.tableAngle,
        )
        // The clock faces animate from runs at exactly the calm rate.
        assertEquals(full.t * CALM_MOTION_RATE, calm.t, 1e-3f)
        assertTrue("the calm rate must be below 1", CALM_MOTION_RATE < 1f)
    }

    @Test
    fun `calm motion drops the tap flinch but still shows the tap ring`() {
        for (calm in listOf(false, true)) {
            val host = FaceHost()
            host.advance(1f / 60f, FaceState.IDLE, null, null, Bindings.DEFAULTS, Arc, calm)
            host.onTap(Offset(10f, 10f), 100f)
            host.advance(1f / 60f, FaceState.IDLE, null, null, Bindings.DEFAULTS, Arc, calm)
            val f = host.snapshot()
            if (calm) {
                assertEquals("calm motion flinched", Offset.Zero, f.flinch)
            } else {
                assertNotEquals("full motion stopped flinching", Offset.Zero, f.flinch)
            }
            // The touch is still visibly received either way.
            assertNotNull(f.ringAt)
            assertTrue(f.ringFrac in 0f..1f)
        }
    }

    @Test
    fun `calm motion drops the error shake`() {
        // 27 frames at 60 Hz is 0.45 s into ERROR, inside the shake window.
        val full = advanced(calm = false, state = FaceState.ERROR, steps = 27)
        val calm = advanced(calm = true, state = FaceState.ERROR, steps = 27)
        assertTrue("full motion should shake here", full.shake.x != 0f)
        assertEquals(Offset.Zero, calm.shake)
    }
}
