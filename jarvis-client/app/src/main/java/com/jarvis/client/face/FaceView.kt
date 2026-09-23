package com.jarvis.client.face

import android.opengl.GLSurfaceView
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.viewinterop.AndroidView
import com.jarvis.client.FaceState
import com.jarvis.client.face.gl.MeshFaces
import com.jarvis.client.face.gl.MeshRenderer
import androidx.compose.foundation.Canvas
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/**
 * The shell that hosts a face.
 *
 * **Everything here is shell-level and happens exactly once.** If a face's own
 * draw code ever needs to know about envelopes, crossfades, frame pacing or
 * overlays, it is in the wrong layer — that was the whole finding behind the
 * `state_transforms` block: twenty faces each implementing the same four
 * borrowed states twenty different ways.
 */
@Composable
fun FaceView(
    state: FaceState,
    notches: Int,
    modifier: Modifier = Modifier,
    face: Face = Faces.default,
    bindings: Bindings = Bindings.DEFAULTS,
    /** The owner's microphone, 0..1, per audio frame. Null when the mic is shut. */
    micLevel: () -> Float? = { null },
    /** Jarvis's own voice, 0..1, per audio frame. Null when nothing is playing. */
    speechLevel: () -> Float? = { null },
    /**
     * The ground this face draws on — [Spec.BACKGROUND] unless a caller reads
     * [com.jarvis.client.ui.theme.Chrome.well] and passes it, which is the
     * theme's own answer to what the reactor should sit in. Both paths follow
     * it: the `Canvas` faces paint it, and [GLFaceSurface]'s two mesh faces
     * clear their GPU surface to it (handed over on the GL thread, alongside
     * each frame). They used to clear to [Spec.BACKGROUND] whatever the theme,
     * so Tokamak and Membrane sat in a different black from the well around
     * them.
     */
    background: Color = Spec.BACKGROUND,
    /**
     * How much of the glow to draw, as a share of the normal amount: 1 is the
     * glow as designed, 0.25 a quarter of it. The caller folds in the theme's
     * own `Chrome.postScale` and the owner's Glow setting and passes the
     * product.
     *
     * Clamped to 0..1 here, whatever arrives, so this can only ever take
     * light AWAY. The flash limits in [Spec] are written against the glow at
     * its designed strength; a setting that could raise it would be a way
     * round them, and nothing in this app is allowed one. Scales the additive
     * glow sprite on the canvas faces and Tokamak's radial wash; Membrane has
     * no glow of its own to scale.
     */
    glow: Float = 1f,
    /**
     * Calm motion: the face moves at [CALM_MOTION_RATE] of its normal speed,
     * and drops the three positional jolts (the error shake, the tap flinch
     * and the speech push). Never faster than normal, whatever else is set.
     *
     * What it deliberately does NOT touch: the colour patterns and the two
     * flash governors that police them, which still run on real time exactly
     * as before, and state changes, which still animate - a face that stops
     * moving when Jarvis changes state has stopped reporting state. The caller
     * decides when this is on (the owner's Motion setting, or the phone's own
     * "remove animations" when that setting says to follow the phone).
     */
    calmMotion: Boolean = false,
) {
    val host = remember { FaceHost() }
    var frame by remember { mutableStateOf(host.snapshot()) }

    // The loop below is keyed on face and bindings, not on these. Called
    // directly they would be captured from whichever composition started the
    // loop and never updated — so the first non-remembered lambda a caller
    // passes would freeze the mic at its opening value for the life of the
    // face. rememberUpdatedState is the fix for exactly that shape.
    val mic by rememberUpdatedState(micLevel)
    val speech by rememberUpdatedState(speechLevel)

    // And `state`, which is the same shape and was the one that mattered.
    //
    // The loop below is keyed on `face, bindings`, so a coroutine started while
    // the face was IDLE held IDLE for the life of the process. Two consequences,
    // and the second is not a performance problem:
    //
    //  - `Spec.fpsFor(IDLE)` is 30, so THINKING and SPEAKING — which ask for
    //    every frame the display gives — were capped at 30 on a panel that had
    //    just been asked for 120, and BANKED and STANDBY never got their 2 and
    //    15, so the battery saving described twenty lines down never happened.
    //  - `advance(dt, wanted = state, …)` begins `if (wanted != state)
    //    onStateChange(wanted)`. So one frame after LaunchedEffect(state) moved
    //    the host to THINKING, the loop handed it the stale IDLE and moved it
    //    straight back — resetting the flash governor and restarting the colour
    //    crossfade each time. The reactor could not leave idle. The single most
    //    visible thing this app does was inert, and no test could see it.
    val liveState by rememberUpdatedState(state)

    // Same shape again: the loop below outlives any one composition, so a
    // Motion setting changed while the face is on screen has to reach it
    // through here rather than being captured once when the loop started.
    val calm by rememberUpdatedState(calmMotion)

    // Clamped once, here, so no draw below can be handed more than 1. NaN is
    // treated as "the designed amount" rather than passed on, because
    // coerceIn lets NaN straight through and a NaN alpha is undefined.
    val glowK = if (glow.isNaN()) 1f else glow.coerceIn(0f, 1f)

    // One glow sprite, painted once and reused.
    //
    // It used to be a Brush.radialGradient built inside the draw: a new
    // ArrayList, two boxed Colors, a new ShaderBrush and — because a
    // ShaderBrush caches its native shader per instance — a fresh
    // RadialGradient and gradient ramp, every active frame. At radius 2.1x it
    // covers essentially the whole canvas, roughly thirty times the fill of the
    // entire particle field, so it was the single most expensive thing on
    // screen and it was being rebuilt sixty times a second.
    val glowSprite = rememberGlowSprite()

    // A tap wakes the sleeping branch of the loop below. In BANKED the loop
    // sleeps half a second between frames, so a tap could sit unanswered for
    // that long - the one moment the face is supposed to react instantly.
    // Conflated: a burst of touches is one wake, not a queue of them.
    val wake = remember { Channel<Unit>(Channel.CONFLATED) }

    LaunchedEffect(state) { host.onStateChange(state) }

    // The frame loop is suspended while the app is not at least STARTED.
    //
    // withFrameNanos stops on its own when the display stops producing frames,
    // but the 1..15 fps branch below sleeps on `delay` instead - and `delay`
    // keeps firing with the screen off. STANDBY (15 fps) and BANKED (2 fps) are
    // precisely the states the phone sits in while pocketed, so that branch
    // woke the CPU, advanced the host and wrote Compose state for as long as
    // the composition lived, on the two states meant to be the cheap ones.
    // repeatOnLifecycle cancels the whole loop at ON_STOP and starts it again
    // at ON_START; `last` is re-declared inside, so the first frame back is
    // treated as a fresh start rather than one enormous delta.
    val frameLoopOwner = LocalLifecycleOwner.current
    LaunchedEffect(face, bindings, frameLoopOwner) {
        frameLoopOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            var last = 0L
            while (true) {
                val fps = Spec.fpsFor(liveState)
                if (fps in 1..30) {
                    // Was `1..15`, which left IDLE and APPROVAL (both 30,
                    // per fpsFor) waking the Choreographer at the display
                    // rate to decide to do nothing 60-120 times a second,
                    // across what the spec itself calls nine tenths of
                    // screen-on time - the exact waste this branch exists to
                    // avoid for STANDBY and BANKED, just below the line that
                    // used to stop at them. The screen-off concern that
                    // keeps STANDBY/BANKED on `delay` rather than
                    // `withFrameNanos` (see the comment above this loop)
                    // does not apply here: IDLE and APPROVAL are foreground,
                    // screen-on states by definition - if the screen goes
                    // off from either, `repeatOnLifecycle` below STARTED
                    // suspends this whole loop regardless of which branch
                    // it is in. Sleeping to the next due instant costs
                    // nothing in between.
                    val stepMs = 1000L / fps
                    // Sleep to the next due instant - or until a tap arrives,
                    // whichever is first. The tap's own frame then draws now
                    // rather than at the end of the step.
                    withTimeoutOrNull(stepMs) { wake.receive() }
                    val now = System.nanoTime()
                    if (last == 0L) last = now
                    val dt = ((now - last) / 1_000_000_000.0).toFloat().coerceIn(0f, 0.25f)
                    last = now
                    if (host.advance(dt, liveState, mic(), speech(), bindings, face, calm)) {
                        frame = host.snapshot()
                    }
                } else {
                    withFrameNanos { now ->
                        if (last == 0L) last = now
                        // Measured on the surface that actually matters, rather
                        // than assumed: the panel drops rate on its own for battery
                        // saver, brightness and heat, and a face driven by an
                        // assumed delta runs at the wrong speed the moment it does.
                        com.jarvis.client.platform.DisplayRate.sample(now - last)
                        val dt = ((now - last) / 1_000_000_000.0).toFloat().coerceIn(0f, 0.25f)
                        last = now
                        // Resting states draw at 30 rather than the display rate.
                        // The accumulated dt is handed to the draw, so motion covers
                        // the same distance — frame skipping, not slow motion.
                        if (host.advance(dt, liveState, mic(), speech(), bindings, face, calm)) {
                            frame = host.snapshot()
                        }
                    }
                }
            }
        }
    }

    // The face is the largest thing on the screen and the app's primary status
    // indicator, and to a screen reader it was not there at all: a bare Canvas
    // carries no semantics, so TalkBack treats it as decoration and skips it.
    // Everything the precedence chain resolves - that Jarvis has errored, that
    // something is waiting - was available only as colour and motion.
    //
    // A live region, because the point of this surface is that it CHANGES.
    // Polite rather than assertive: it should not interrupt what is being read,
    // and the approval card below it is the thing that actually needs reading.
    val spoken = when (state) {
        FaceState.ERROR -> "Jarvis has a problem"
        FaceState.APPROVAL -> "Jarvis is waiting for your decision"
        FaceState.LISTENING -> "Jarvis is listening"
        FaceState.THINKING -> "Jarvis is working"
        FaceState.SPEAKING -> "Jarvis is speaking"
        FaceState.BANKED -> "Jarvis has notes saved for later"
        FaceState.STANDBY -> "Jarvis is on standby and will not speak"
        FaceState.IDLE -> "Jarvis is idle"
    }
    Box(
        modifier
            .semantics {
                contentDescription = spoken
                liveRegion = LiveRegionMode.Polite
            }
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        host.onTap(it, size.width.toFloat())
                        wake.trySend(Unit)
                    },
                )
            }
            .pointerInput(Unit) {
                detectDragGestures(
                    onDragEnd = { host.onDragEnd() },
                ) { change, drag ->
                    change.consume()
                    host.onDrag(drag)
                }
            },
    ) {
        val mesh = remember(face.id) { MeshFaces.rendererFor(face.id) }
        if (mesh != null) {
            // key(), because the new renderer above is useless without a new
            // view to attach it to. GLFaceSurface is one call site, so
            // AndroidView's factory runs exactly once for it: switching from
            // tokamak to membrane built a fresh MembraneRenderer, kept feeding
            // it frames through `update`, and went on showing the SAME
            // GLSurfaceView still driving the old TokamakRenderer - whose
            // onSurfaceCreated had run, while the membrane's never did. What
            // the owner saw was a motionless torus. Re-calling setRenderer is
            // not an alternative: GLSurfaceView throws if it is called twice on
            // one view, so the view itself has to be new, and `key` is what
            // makes the composition treat it as new.
            //
            // `{ frame }`, a lambda, not `frame`: passing the value here read
            // it during COMPOSITION, so every frame the loop wrote re-ran this
            // whole function - the semantics block, the spoken-state string,
            // GLFaceSurface and AndroidView's update - up to the panel rate.
            // Exactly what FaceHost's own doc warns against. The canvas branch
            // below never had the problem, because it reads `frame` only inside
            // its draw lambda; the lambda gives the mesh branch the same shape,
            // read only where it is used (see GLFaceSurface).
            key(face.id) {
                GLFaceSurface(mesh, { frame }, face, notches, background, glowK)
            }
        } else {
            Canvas(Modifier.matchParentSize()) {
                drawFace(frame, face, notches, glowSprite, background, glowK)
            }
        }
    }
}

/**
 * One still picture of [face], for a picker that shows every face at once.
 *
 * Not a small [FaceView]. The picker's own comment says why a grid of live
 * reactors is wrong - twenty frame loops, twenty flash governors, and a phone
 * that can afford one animated surface - so this has no frame loop, no clock
 * and no state: it advances a throwaway [FaceHost] a little over a second of
 * IDLE once, when the face or the colours change, and draws that one frame.
 * The Canvas then redraws only when Compose asks it to (size or colours), not
 * per frame.
 *
 * The two mesh faces (Tokamak, Membrane) get a simple drawn stand-in instead
 * of their real picture: their real picture needs a live `GLSurfaceView` - a
 * GL thread and a GPU context each - which is exactly the cost this exists to
 * avoid, twenty times over. The stand-in is their silhouette in the same
 * colours, not a render of them.
 *
 * Nucleus draws its real picture here, which compiles its shader the first
 * time a thumbnail of it is drawn - once, and only if the picker is opened.
 */
@Composable
fun FaceThumbnail(
    face: Face,
    bindings: Bindings,
    modifier: Modifier = Modifier,
    /** The same ground FaceView takes - pass `Chrome.well` to match Home. */
    background: Color = Spec.BACKGROUND,
) {
    val still = remember(face, bindings) { stillFrameOf(face, bindings) }
    val mesh = remember(face.id) { MeshFaces.isMesh(face.id) }
    Canvas(modifier) {
        if (mesh) {
            drawMeshStandIn(still, face, background)
        } else {
            // No glow sprite: IDLE is not an active state, so drawFace would
            // not draw one anyway, and a still picture is no reason to hold a
            // bitmap per thumbnail.
            drawFace(still, face, notches = 0, glow = null, background = background, glowScale = 1f)
        }
    }
}

/**
 * About a second and a quarter of IDLE, in the same 30 fps steps the live
 * loop takes for that state - enough for the angles to leave zero, so a
 * thumbnail is not every face at its starting pose, and for the colour to be
 * the resolved one rather than the host's initial placeholder.
 */
private fun stillFrameOf(face: Face, bindings: Bindings): FaceFrame {
    val host = FaceHost()
    repeat(STILL_FRAME_STEPS) {
        host.advance(1f / 30f, FaceState.IDLE, null, null, bindings, face)
    }
    return host.snapshot()
}

private const val STILL_FRAME_STEPS = 38

/**
 * The mesh faces' silhouettes, for [FaceThumbnail] only - see there for why
 * they are not the real render. Proportions follow the renderers' own
 * numbers (Tokamak's ring radius 0.72 and tube 0.29, viewed from its -0.55
 * pitch; Membrane's disc from its -0.72 pitch), so the stand-in is at least
 * the right shape and size.
 */
private fun DrawScope.drawMeshStandIn(f: FaceFrame, face: Face, background: Color) {
    drawRect(background, size = Size(size.width, size.height))
    val w = size.minDimension
    val cx = size.width / 2f
    val cy = size.height / 2f
    val r = w / 2f * 0.5f * face.fit
    val hot = dimmed(f.swatch.a, f.dim, background)
    val cool = dimmed(f.swatch.b, f.dim, background)
    if (face.id == "tokamak") {
        // A torus seen from above at an angle: one thick elliptical band.
        val ring = r * (0.72f / 1.01f)
        val squash = sin(0.55f)
        val tube = r * (0.29f * 2f / 1.01f)
        drawOval(
            color = cool,
            topLeft = Offset(cx - ring, cy - ring * squash),
            size = Size(ring * 2f, ring * 2f * squash),
            style = Stroke(width = tube),
        )
        drawOval(
            color = hot,
            topLeft = Offset(cx - ring, cy - ring * squash),
            size = Size(ring * 2f, ring * 2f * squash),
            style = Stroke(width = tube * 0.18f),
        )
    } else {
        // A drum skin seen at an angle: a disc with its rings.
        val squash = sin(0.72f)
        drawOval(
            color = cool,
            topLeft = Offset(cx - r, cy - r * squash),
            size = Size(r * 2f, r * 2f * squash),
        )
        for (i in 1..3) {
            val rr = r * i / 4f
            drawOval(
                color = hot.copy(alpha = 0.9f - i * 0.2f),
                topLeft = Offset(cx - rr, cy - rr * squash),
                size = Size(rr * 2f, rr * 2f * squash),
                style = Stroke(width = r * 0.04f),
            )
        }
    }
}

/**
 * The two-layer stand-in for [drawFace], for a face [MeshFaces] hands a real
 * `GLSurfaceView.Renderer` instead of a `DrawScope` body. A `GLSurfaceView`
 * is its own `Surface`, not a `DrawScope` call, so it cannot be interleaved
 * between [drawFace]'s background/glow/overlay draws the way a normal face's
 * body is - it is a whole layer underneath a second, much smaller Canvas
 * that draws only the shell-level pieces every face still needs: the
 * approval clock, the notch ring, the tap ring. The GL surface clears to
 * [background] itself (handed to the renderer with each frame, on the GL
 * thread - see `MeshRenderer.setFrame`), so there is no separate background
 * rect to paint here.
 *
 * [frame] is a function, not a value, so that reading it is never a
 * composition read: it is called only inside AndroidView's `update` block and
 * the overlay Canvas's draw lambda. Compose watches the reads inside `update`
 * and re-runs just that block when the frame changes, and a read inside a draw
 * lambda re-runs just the draw - so a new frame costs one GL upload and one
 * overlay redraw, and nothing recomposes.
 *
 * Two things every canvas face gets are deliberately skipped for a mesh
 * face: the additive glow sprite, and the shake/flinch/speech-push
 * positional wobble. Both are z-order tricks specific to one `DrawScope`
 * pass (the glow relies on the face's own opaque strokes being drawn
 * OVER it, which only makes sense as two draws on the SAME canvas) and
 * do not have an honest equivalent split across two separately composited
 * surfaces - guessing at one without a device to look at it on was a worse
 * risk than a mesh face sitting still while every other face flinches.
 */
@Composable
private fun GLFaceSurface(
    mesh: MeshRenderer,
    frame: () -> FaceFrame,
    face: Face,
    notches: Int,
    background: Color,
    glow: Float,
) {
    val lifecycleOwner = LocalLifecycleOwner.current
    // AndroidView's factory runs exactly once per call site and hands back
    // the same instance on every later recomposition - this just keeps that
    // instance reachable from the DisposableEffect below, which runs
    // independently of it.
    var glSurfaceView by remember { mutableStateOf<GLSurfaceView?>(null) }

    // fillMaxSize, not matchParentSize: this composable is called from
    // inside the caller's Box, not written inline as its content lambda, so
    // there is no BoxScope receiver here for matchParentSize to resolve
    // against. The two fill the same space in this case regardless, since
    // nothing else inside that Box competes with either child for it.
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { ctx ->
            GLSurfaceView(ctx).apply {
                setEGLContextClientVersion(3)
                // The torus mesh needs real depth testing - the near wall
                // has to hide the far one - and GLSurfaceView's own default
                // config carries no depth buffer at all unless one is asked
                // for. RGBA8888 plus a 16-bit depth buffer, no stencil, and
                // now 4x multisampling where the device has it: the kit's
                // WebGL context antialiases its mesh edges, and without it
                // the torus and drum silhouettes were single-sample
                // staircases. Falls back to exactly the old config.
                setEGLConfigChooser(com.jarvis.client.face.gl.GL.MsaaConfigChooser())
                setRenderer(mesh)
                renderMode = GLSurfaceView.RENDERMODE_WHEN_DIRTY
            }.also { glSurfaceView = it }
        },
        update = { glView ->
            // Read once, here on the UI thread, into a local the GL-thread
            // lambda captures - never read from inside queueEvent, which runs
            // later on another thread.
            val f = frame()
            // Dimmed toward the same ground the surface now clears to, as the
            // canvas faces do, so a dimmed state fades into the well it is
            // actually drawn on rather than into a different black.
            val hot = dimmed(f.swatch.a, f.dim, background)
            val cool = dimmed(f.swatch.b, f.dim, background)
            glView.queueEvent { mesh.setFrame(f, hot, cool, face.fit, background) }
            glView.requestRender()
        },
    )

    // GLSurfaceView owns a real GL thread and EGL context that has to be
    // told explicitly to pause and resume - Compose disposing the AndroidView
    // is not enough on its own, and neither is leaving it to the Activity,
    // since this can be torn down by navigation while the Activity itself
    // stays resumed.
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_PAUSE -> glSurfaceView?.onPause()
                Lifecycle.Event.ON_RESUME -> glSurfaceView?.onResume()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            glSurfaceView?.onPause()
        }
    }

    Canvas(Modifier.fillMaxSize()) {
        val f = frame()
        val w = size.minDimension
        val cx = size.width / 2f
        val cy = size.height / 2f
        val radius = w / 2f * 0.5f * face.fit
        val hot = dimmed(f.swatch.a, f.dim, background)
        val cool = dimmed(f.swatch.b, f.dim, background)

        // Tokamak's own reference composites a soft, centre-bright radial
        // wash back over its GPU mesh output after drawing it (the `gr0`
        // gradient in its own draw() in the desktop's faces.html). Ported as
        // a post-layer here for the same reason: it already IS one on the
        // reference, not a new choice made to fit this split.
        //
        // It is this face's glow, so the Glow setting scales it the same way
        // it scales the canvas faces' sprite - down only, `glow` is 0..1.
        //
        // The kit's wash reaches half its canvas (`S * .5`), and its torus is
        // `S * 1.05 / 4` per unit where this one is `radius` per unit - so
        // half the kit's canvas is 1.9 radii here. It was 2.5, a wash a
        // third wider than the kit's; narrowing it only ever takes light away.
        if (face.id == "tokamak" && glow > 0f) {
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(hot.copy(alpha = 0.13f * glow), hot.copy(alpha = 0f)),
                    center = Offset(cx, cy),
                    radius = radius * 1.9f,
                ),
                radius = radius * 1.9f,
                center = Offset(cx, cy),
            )
        }

        when (f.overlay) {
            Spec.Overlay.CLOCK -> drawApprovalClock(cx, cy, radius, hot, f)
            Spec.Overlay.NOTCHES -> drawNotches(cx, cy, radius, cool, notches)
            else -> Unit
        }

        val at = f.ringAt
        if (at != null && f.ringFrac in 0f..1f) {
            drawCircle(
                color = hot.copy(alpha = (1f - f.ringFrac) * 0.6f),
                radius = w * Spec.TAP_RING_FRAC * f.ringFrac,
                center = at,
                style = Stroke(width = 2f),
            )
        }
    }
}

/** Everything the draw needs, computed once per advanced frame. */
data class FaceFrame(
    val state: FaceState,
    val swatch: Swatch,
    val angle: Float,
    val tableAngle: Float,
    val motion: FaceState,
    val amp: Float,
    val speechPush: Float,
    val dim: Float,
    val overlay: Spec.Overlay,
    val clockFrac: Float,
    val hitchPhase: Float,
    val shake: Offset,
    val flinch: Offset,
    val ringAt: Offset?,
    val ringFrac: Float,
    val yaw: Float,
    val pitch: Float,
    val t: Float,
    /**
     * Calm motion is on (see FaceView's `calmMotion`). [t], [angle] and
     * [tableAngle] are already slowed when it is, and [shake] and [flinch]
     * already zero - this is for the few readers that keep their own clock or
     * add their own jolt: the speech push in `drawFace`, and
     * `MembraneRenderer`'s physics, which runs on real elapsed time.
     */
    val calm: Boolean = false,
    /**
     * The movement ([motion]) of the state before the current one; [motion]
     * itself when nothing has changed yet. With [hitchPhase] (seconds since
     * that change) it lets a face ease a per-state target in from where the
     * last state left it - see `CoreKit.settle` - while staying a pure
     * function of this frame, rather than carrying last frame's value.
     */
    val prevMotion: FaceState = motion,
)

/**
 * The share of normal speed a face moves at under calm motion: two thirds, so
 * every period is half as long again. Slower only - a rate below 1 can only
 * stretch a movement out, never add to it.
 */
const val CALM_MOTION_RATE = 2f / 3f

/**
 * The state machine behind a face. Not a composable: it is mutable, per-frame
 * and deliberately outside the snapshot system, because running it as Compose
 * state would invalidate the tree sixty times a second to change a float.
 */
class FaceHost {

    private val governor = FlashGovernor()

    /**
     * Per surface, like the governor and for the same reason: a strobe budget
     * shared between faces would stop one face because another had been
     * strobing.
     */
    private val strobeBudget = StrobeBudget()

    /**
     * Per-surface jitter for `flicker`, so a grid of faces does not flicker in
     * lockstep. The reference derives it per face for the same reason.
     */
    private val seed = (0..9_999).random()

    private var t = 0f

    /**
     * The clock handed to faces as [FaceFrame.t]. The same as [t] unless calm
     * motion is on, when it runs at [CALM_MOTION_RATE] of it.
     *
     * A separate clock rather than a slowed [t], because [t] also feeds the
     * flash governor and the strobe budget, whose limits are in real seconds:
     * slowing their clock would stretch "at most two seconds of strobe" into
     * three. They keep real time; only what the face draws slows down.
     * Accumulated, never computed as `t * rate`, for the reason the angle
     * comment in [advance] gives - so turning calm on or off mid-flight is a
     * change of speed, not a jump.
     */
    private var motionT = 0f
    private var calm = false
    private var angle = 0f
    private var tableAngle = 0f
    private var rate = 1f
    private var rateTarget = 1f

    private var mic = 0f
    private var voice = 0f
    private var lastVoiceAt = -999f

    private var colFrom: Swatch? = null
    private var colShown: Swatch = Swatch(Spec.ICE_3, Spec.ICE_3)
    private var colEase = 1f

    private var state: FaceState = FaceState.IDLE
    private var prevState: FaceState = FaceState.IDLE
    private var changedAt = -999f

    private var clockStartedAt = -999f

    private var yaw = 0f
    private var pitch = 0f
    private var yawVel = 0f
    private var dragging = false

    private var tapAt: Offset? = null
    private var tapStartedAt = -999f
    private var faceWidth = 1f

    private var accum = 0f

    fun onStateChange(next: FaceState) {
        if (next == state) return
        prevState = state
        state = next
        changedAt = t
        // The RATE is eased, not snapped: a face whose rate steps from 0.22 to
        // 1.35 in one frame reads as a cut even when the angle is continuous.
        rateTarget = Spec.transformFor(next).rate
        // Remember the colour actually on screen and fade from it, so a state
        // change reads as the same object changing its mind rather than a cut.
        colFrom = colShown
        colEase = 0f
        if (next == FaceState.APPROVAL) clockStartedAt = t
        governor.reset()
    }

    fun onTap(at: Offset, width: Float) {
        tapAt = at
        tapStartedAt = t
        faceWidth = max(1f, width)
    }

    fun onDrag(delta: Offset) {
        dragging = true
        yaw += delta.x * Spec.DRAG_YAW_PER_PX
        pitch = (pitch + delta.y * Spec.DRAG_PITCH_PER_PX)
            .coerceIn(-Spec.DRAG_PITCH_LIMIT, Spec.DRAG_PITCH_LIMIT)
        yawVel = (delta.x * Spec.DRAG_YAW_PER_PX * 60f)
            .coerceIn(-Spec.DRAG_MAX_RAD_S, Spec.DRAG_MAX_RAD_S)
    }

    fun onDragEnd() {
        dragging = false
    }

    /**
     * @return true when this frame should be drawn. False means the state's
     *   frame rate says skip — the dt is kept and handed to the next draw.
     */
    fun advance(
        dtIn: Float,
        wanted: FaceState,
        micIn: Float?,
        voiceIn: Float?,
        bindings: Bindings,
        face: Face,
        /** Calm motion: see FaceView's `calmMotion`. Only ever slows. */
        calm: Boolean = false,
    ): Boolean {
        if (wanted != state) onStateChange(wanted)
        this.calm = calm
        // Exactly 1 when calm is off, so a full-motion face advances exactly
        // as it always has.
        val calmK = if (calm) CALM_MOTION_RATE else 1f
        t += dtIn
        motionT += dtIn * calmK
        accum += dtIn

        val tf = Spec.transformFor(state)

        // Frame pacing. The first 600 ms after any change and any live tap run
        // at full rate so no transition stutters.
        val fps = Spec.fpsFor(state)
        val settled = (t - changedAt) > Spec.FULL_RATE_WINDOW_S &&
            (t - tapStartedAt) > Spec.FULL_RATE_WINDOW_S
        if (fps > 0 && settled) {
            if (accum < 1f / fps) return false
        }
        val dt = accum
        accum = 0f

        // Envelopes, in seconds, so the feel does not change with refresh rate.
        mic = smooth(mic, (micIn ?: 0f).coerceIn(0f, 1f), dt, Spec.MIC_ATTACK_S, Spec.MIC_RELEASE_S)
        if (mic < Spec.MIC_GATE) mic = 0f

        if (voiceIn != null) {
            lastVoiceAt = t
            voice = smooth(voice, voiceIn.coerceIn(0f, 1f), dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        } else if (state == FaceState.SPEAKING && (t - lastVoiceAt) > Spec.SPEECH_FALLBACK_AFTER_S) {
            // Speaking is never frozen, even before TTS is wired: a
            // speech-shaped stand-in keeps the face moving. It is not his
            // voice, but it is not a still picture either.
            voice = smooth(voice, syntheticVoice(t), dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        } else {
            voice = smooth(voice, 0f, dt, Spec.VOICE_ATTACK_S, Spec.VOICE_RELEASE_S)
        }
        if (voice < Spec.VOICE_GATE) voice = 0f

        // What drives the pattern and the scale push.
        val drive = when (state) {
            // Silence is not absence of attention: a person pauses between
            // words, and a face that drops below idle during the pause reads as
            // "it stopped listening" at exactly the moment they check.
            FaceState.LISTENING, FaceState.APPROVAL -> max(Spec.LISTEN_FLOOR, mic)
            FaceState.SPEAKING -> max(Spec.SPEAK_FLOOR, voice)
            else -> 0f
        }

        // Rate easing, then angle ACCUMULATION. Never angle = clock * speed:
        // multiplying the absolute clock by a per-state speed makes the angle
        // jump by clock * (new - old) the instant the state changes — measured
        // at 434 to 773 radians on the reference build, forty to a hundred and
        // twenty revolutions on a single frame, at exactly the moment the owner
        // is looking at the face.
        rate = smooth(rate, rateTarget, dt, Spec.RATE_EASE_S, Spec.RATE_EASE_S)
        val motion = tf.borrow
        val faceSpeed = face.speedFor(motion)
        angle += dt * rate * tf.dir * faceSpeed * calmK
        tableAngle += dt * rate * faceSpeed * calmK

        // Colour: resolve the target, then crossfade from what is on screen.
        val target = resolve(bindings.of(state), t, drive, governor, strobeBudget, seed)
        colEase = min(1f, colEase + dt / Spec.COLOR_EASE_S)
        val delayed = if (state == FaceState.APPROVAL) {
            // The ring is seen to arrive before the colour follows: the knock
            // comes before the door opens.
            ((t - changedAt) - Spec.TINT_DELAY_APPROVAL_S) / Spec.COLOR_EASE_S
        } else {
            colEase
        }
        val k = smoothstep(delayed.coerceIn(0f, 1f))
        val from = colFrom
        colShown = if (from == null) target else Swatch(
            mix(from.a, target.a, k),
            mix(from.b, target.b, k),
        )

        // Drag inertia: a released face keeps turning and settles rather than
        // stopping dead under the finger.
        if (!dragging) {
            yaw += yawVel * dt
            yawVel *= exp(-dt / Spec.DRAG_INERTIA_TAU_S)
            if (abs(yawVel) < 0.001f) yawVel = 0f
        }

        return true
    }

    fun snapshot(): FaceFrame {
        val tf = Spec.transformFor(state)
        val sinceTap = t - tapStartedAt
        val tapLive = sinceTap in 0f..Spec.TAP_FLINCH_S
        val tapK = if (tapLive) 1f - (sinceTap / Spec.TAP_FLINCH_S) else 0f

        // Read once into a local rather than null-checked and then forced. The
        // field is written from the pointer handler and read from the frame
        // loop; both are the main thread today, so the `!!` could not actually
        // fire — but the compiler cannot prove that, which is exactly why it
        // demanded the `!!`, and a local makes it true instead of merely
        // likely. Last one in the codebase.
        val at = tapAt
        // Calm motion drops the flinch; the tap ring below still answers the
        // touch, so a tap is still visibly received.
        val flinch = if (tapLive && at != null && !calm) {
            val d = Offset(0.5f * faceWidth - at.x, 0.5f * faceWidth - at.y)
            val len = max(1f, hypot(d.x, d.y))
            val push = faceWidth * Spec.TAP_FLINCH_FRAC * tapK
            Offset(d.x / len * push, d.y / len * push)
        } else {
            Offset.Zero
        }

        val ringFrac = if (sinceTap in 0f..Spec.TAP_RING_S) sinceTap / Spec.TAP_RING_S else -1f

        val drive = when (state) {
            FaceState.LISTENING, FaceState.APPROVAL -> max(Spec.LISTEN_FLOOR, mic)
            FaceState.SPEAKING -> max(Spec.SPEAK_FLOOR, voice)
            else -> 0f
        }

        // The clock overlay closes over twenty seconds, with the first 220 ms
        // sweeping to 12% so the ring is on screen before the tint.
        val clockFrac = if (state == FaceState.APPROVAL) {
            val since = t - clockStartedAt
            if (since < 0.22f) (since / 0.22f) * 0.12f
            else min(1f, 0.12f + (since - 0.22f) / Spec.APPROVAL_CLOCK_S)
        } else {
            0f
        }

        // The error hitch: stop dead in 60 ms, hold, shake, then crawl.
        val sinceChange = t - changedAt
        // Not under calm motion. The error still reads: its own colour, and
        // the transform's stop-then-crawl, which is a change of speed rather
        // than a jolt.
        val shake = if (state == FaceState.ERROR && sinceChange in 0.31f..0.61f && !calm) {
            val amp = faceWidth * 0.015f
            Offset(sin(sinceChange * 8f * PI2) * amp, 0f)
        } else {
            Offset.Zero
        }

        return FaceFrame(
            state = state,
            swatch = colShown,
            angle = angle,
            tableAngle = tableAngle,
            motion = tf.borrow,
            amp = drive,
            speechPush = if (state == FaceState.SPEAKING) voice else mic,
            dim = tf.dim,
            overlay = tf.overlay,
            clockFrac = clockFrac,
            hitchPhase = sinceChange,
            shake = shake,
            flinch = flinch,
            ringAt = tapAt,
            ringFrac = ringFrac,
            yaw = yaw,
            pitch = pitch,
            t = motionT,
            calm = calm,
            prevMotion = Spec.transformFor(prevState).borrow,
        )
    }

    private fun syntheticVoice(time: Float): Float {
        val inRest = (time % Spec.SPEECH_REST_EVERY_S) > (Spec.SPEECH_REST_EVERY_S - Spec.SPEECH_REST_S)
        if (inRest) return 0f
        val syl = sin(time * Spec.SPEECH_SYLLABLE_HZ * PI2) * 0.5f + 0.5f
        // A hash, not a new XorWowRandom every frame. Random(seed) allocated a
        // generator sixty times a second for one float.
        val weight = 0.55f + 0.45f * hashUnit((time * 2f).toInt())
        return (syl * weight).coerceIn(0f, 1f)
    }
}

private fun smoothstep(x: Float) = x * x * (3f - 2f * x)

/**
 * Dims by blending toward the background, never by multiplying toward zero.
 *
 * A multiply lands banked's already-dark colour around 0.002 relative
 * luminance, which many OLED panels quantise to black — so the state that means
 * "something is waiting" would vanish on the device most likely to show it.
 *
 * `bg` should be the ground the face is actually drawn on - FaceView's
 * `background`, which both the canvas faces and (since they clear to it) the
 * mesh faces sit in. Dimming toward any other colour fades a dimmed state into
 * a ground that is not there. No default, so a new caller has to say which
 * ground it means rather than silently getting `Spec.BACKGROUND`.
 */
private fun dimmed(c: Color, dim: Float, bg: Color): Color = mix(bg, c, dim)

/**
 * @param glow the glow sprite, or null to draw no glow at all (a still
 *   thumbnail, which has no business holding its own 100 KB bitmap).
 * @param glowScale 0..1, already clamped by the caller - see FaceView's `glow`.
 */
private fun DrawScope.drawFace(
    f: FaceFrame,
    face: Face,
    notches: Int,
    glow: ImageBitmap?,
    background: Color,
    glowScale: Float,
) {
    val w = size.minDimension
    val cx = size.width / 2f
    val cy = size.height / 2f
    // faces[].render.fit — a uniform scale so no face touches its edge.
    val radius = w / 2f * 0.5f * face.fit

    // One ground for all faces on this path - a caller's theme, or
    // Spec.BACKGROUND by default. Each face used to paint its own background,
    // which showed as a differently tinted rectangle behind every one; this
    // keeps that single-ground guarantee while letting the ground itself be
    // themed, since a theme applies to every face identically or not at all.
    drawRect(background, size = Size(size.width, size.height))

    val hot = dimmed(f.swatch.a, f.dim, background)
    val cool = dimmed(f.swatch.b, f.dim, background)

    // The speech / microphone push: up to 3.5% growth on a loud syllable.
    // Positional, not luminance, so it is not a flash. Off under calm motion:
    // it is a jolt on every loud syllable. The brightness lift just below is
    // not motion and stays.
    val push = if (f.calm) 1f else 1f + Spec.SPEECH_SCALE * f.speechPush
    val lifted = lift(hot, Spec.SPEECH_BRIGHTNESS * f.speechPush)

    translate(f.flinch.x + f.shake.x, f.flinch.y + f.shake.y) {
        // A cached-gradient halo rather than a blur. A real blur over a canvas
        // face was measured at 3-6 ms on a mid-range phone; this is one draw.
        if (glow != null && glowScale > 0f && Spec.isActive(f.state)) {
            // One textured quad, tinted, composited additively.
            //
            // Additive rather than SrcOver because the spec's own canvas
            // fallback for bloom says the sprite is drawn "lighter" — this is a
            // light source, and a light source adds.
            val r = radius * 2.1f
            val side = (r * 2f).toInt().coerceAtLeast(1)
            drawImage(
                image = glow,
                dstOffset = IntOffset((cx - r).toInt(), (cy - r).toInt()),
                dstSize = IntSize(side, side),
                // 0.30 is the designed strength; glowScale (0..1) can only
                // take it down from there. See FaceView's `glow`.
                colorFilter = ColorFilter.tint(lifted.copy(alpha = 0.30f * glowScale)),
                blendMode = BlendMode.Plus,
            )
        }

        face.draw(this, cx, cy, radius * push, lifted, cool, f)

        when (f.overlay) {
            Spec.Overlay.CLOCK -> drawApprovalClock(cx, cy, radius, lifted, f)
            Spec.Overlay.NOTCHES -> drawNotches(cx, cy, radius, cool, notches)
            else -> Unit
        }

        val at = f.ringAt
        if (at != null && f.ringFrac in 0f..1f) {
            drawCircle(
                color = lifted.copy(alpha = (1f - f.ringFrac) * 0.6f),
                radius = w * Spec.TAP_RING_FRAC * f.ringFrac,
                center = at,
                style = Stroke(width = 2f),
            )
        }
    }
}

/**
 * The waiting clock: an arc from twelve o'clock closing clockwise, with the
 * knock ping on top.
 *
 * Approval and listening measure 4.5 ΔE apart for a deuteranope, so two states
 * may share a hue only if they never share a movement. This is approval's
 * identity, and it is legible with no colour at all.
 */
private fun DrawScope.drawApprovalClock(
    cx: Float, cy: Float, r: Float, tint: Color, f: FaceFrame,
) {
    val ring = r * 1.5f
    drawArc(
        color = tint.copy(alpha = 0.22f),
        startAngle = -90f,
        sweepAngle = 360f,
        useCenter = false,
        topLeft = Offset(cx - ring, cy - ring),
        size = Size(ring * 2, ring * 2),
        style = Stroke(width = 3f),
    )
    drawArc(
        color = tint,
        startAngle = -90f,
        sweepAngle = 360f * f.clockFrac,
        useCenter = false,
        topLeft = Offset(cx - ring, cy - ring),
        size = Size(ring * 2, ring * 2),
        style = Stroke(width = 3f),
    )

    // The knock: a ring leaving the core every 1.6 s. It repeats, it is
    // directional, and it stops the moment you answer.
    val ph = (f.t % 1.6f) / 0.4f
    if (ph <= 1f) {
        val e = 1f - (1f - ph) * (1f - ph) * (1f - ph)
        drawCircle(
            color = tint.copy(alpha = (1f - e) * 0.55f),
            radius = r * (0.12f + e * 0.82f) * 1.5f,
            center = Offset(cx, cy),
            style = Stroke(width = 2f),
        )
    }
}

/** The rim ring drawn full, with one notch per waiting item. */
private fun DrawScope.drawNotches(cx: Float, cy: Float, r: Float, tint: Color, notches: Int) {
    val ring = r * 1.5f
    drawCircle(tint.copy(alpha = 0.35f), ring, Offset(cx, cy), style = Stroke(width = 3f))
    if (notches <= 0) return
    val n = min(notches, 24)
    for (i in 0 until n) {
        val a = (-PI / 2 + i * (PI2 / n)).toFloat()
        val inner = ring - r * 0.12f
        drawLine(
            color = tint,
            start = Offset(cx + cos(a) * inner, cy + sin(a) * inner),
            end = Offset(cx + cos(a) * (ring + r * 0.06f), cy + sin(a) * (ring + r * 0.06f)),
            strokeWidth = 3f,
        )
    }
}


/**
 * The glow ramp: white in the middle, transparent at the edge, painted once.
 *
 * 160px is plenty — a smooth radial ramp upscales invisibly, and at ARGB that
 * is about 100 KB held for the life of the composition. The colour comes from a
 * ColorFilter at draw time rather than from the bitmap, so the sprite never
 * needs rebuilding when the state colour changes.
 *
 * Modifier.drawWithCache does not solve this on its own: its cache re-runs on a
 * size or key change, and the glow's colour changes continuously, so it would
 * invalidate every frame. Splitting the shape from the tint is what makes it
 * cacheable at all.
 */
@Composable
private fun rememberGlowSprite(): ImageBitmap = remember {
    val n = 160
    val bitmap = android.graphics.Bitmap.createBitmap(
        n, n, android.graphics.Bitmap.Config.ARGB_8888,
    )
    android.graphics.Canvas(bitmap).drawCircle(
        n / 2f, n / 2f, n / 2f,
        android.graphics.Paint().apply {
            isAntiAlias = true
            shader = android.graphics.RadialGradient(
                n / 2f, n / 2f, n / 2f,
                android.graphics.Color.WHITE,
                android.graphics.Color.TRANSPARENT,
                android.graphics.Shader.TileMode.CLAMP,
            )
        },
    )
    bitmap.asImageBitmap()
}

/** A cheap deterministic 0..1 from an int. Replaces a per-frame Random. */
private fun hashUnit(seed: Int): Float {
    var x = seed * -1640531527
    x = x xor (x ushr 15)
    x *= -2048144789
    x = x xor (x ushr 13)
    return ((x ushr 8) and 0xFFFF) / 65535f
}
