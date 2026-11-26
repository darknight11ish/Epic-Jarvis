package com.jarvis.client.voice

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/**
 * The three wake-word models, run by ONNX Runtime on this phone: openWakeWord's
 * own front end (melspectrogram and embedding) and the head that is scored on
 * top of it.
 *
 * ONNX Runtime comes from Maven Central (`com.microsoft.onnxruntime:
 * onnxruntime-android`), pinned to 1.22.0 in build.gradle.kts on purpose:
 * 1.30.0 adds a telemetry uploader to the Android library (a content
 * provider that starts itself and an HTTP client), and nothing in this app
 * may phone home. 1.22.0 has neither - checked by unzipping both AARs.
 *
 * Everything runs on the CPU, one thread per model: a step is three tiny
 * models every 80 ms.
 *
 * The same class runs on a desktop JVM with the plain `onnxruntime` jar (same
 * `ai.onnxruntime` API), which is how it was checked against the real model
 * files and the PC's scores without a phone.
 */
class OrtWakeModels private constructor(
    private val env: OrtEnvironment,
    private val mel: OrtSession,
    private val emb: OrtSession,
    private val wake: OrtSession,
) : WakeModels {

    private val melIn = mel.inputNames.first()
    private val embIn = emb.inputNames.first()
    private val wakeIn = wake.inputNames.first()

    override fun melspec(samples: FloatArray): Array<FloatArray> =
        OnnxTensor.createTensor(env, FloatBuffer.wrap(samples), longArrayOf(1, samples.size.toLong()))
            .use { t ->
                mel.run(mapOf(melIn to t)).use { r ->
                    // [1][1][frames][32]
                    @Suppress("UNCHECKED_CAST")
                    val out = (r.get(0).value as Array<Array<Array<FloatArray>>>)[0][0]
                    Array(out.size) { i -> FloatArray(WakeSpotter.MEL_BINS) { j -> out[i][j] / 10f + 2f } }
                }
            }

    override fun embed(frames: Array<FloatArray>): FloatArray = embedMany(listOf(frames)).first()

    override fun embedMany(windows: List<Array<FloatArray>>): List<FloatArray> {
        if (windows.isEmpty()) return emptyList()
        val n = windows.size
        val flat = FloatArray(n * WakeSpotter.MEL_WINDOW * WakeSpotter.MEL_BINS)
        var k = 0
        for (w in windows) for (frame in w) for (v in frame) flat[k++] = v
        val shape = longArrayOf(n.toLong(), WakeSpotter.MEL_WINDOW.toLong(), WakeSpotter.MEL_BINS.toLong(), 1)
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(flat), shape).use { t ->
            emb.run(mapOf(embIn to t)).use { r ->
                // [n][1][1][96]
                @Suppress("UNCHECKED_CAST")
                val out = r.get(0).value as Array<Array<Array<FloatArray>>>
                List(n) { i -> out[i][0][0].copyOf() }
            }
        }
    }

    override fun score(feats: Array<FloatArray>): Float {
        val flat = FloatArray(feats.size * WakeSpotter.EMB_SIZE)
        var k = 0
        for (f in feats) for (v in f) flat[k++] = v
        val shape = longArrayOf(1, feats.size.toLong(), WakeSpotter.EMB_SIZE.toLong())
        return OnnxTensor.createTensor(env, FloatBuffer.wrap(flat), shape).use { t ->
            wake.run(mapOf(wakeIn to t)).use { r ->
                @Suppress("UNCHECKED_CAST")
                (r.get(0).value as Array<FloatArray>)[0][0]
            }
        }
    }

    override fun close() {
        runCatching { mel.close() }
        runCatching { emb.close() }
        runCatching { wake.close() }
    }

    companion object {
        /** The files in `assets/wakeword/`, and on the PC in `voice-models\wakeword`. */
        const val MEL_FILE = "melspectrogram.onnx"
        const val EMB_FILE = "embedding_model.onnx"

        /**
         * The owner's trained "Hey Atlas" head (2026-11-25). The first two
         * files are openWakeWord's front end and are unchanged; only the head
         * differs, and the PC runs the same file through the same steps
         * (`backend/jarvis_wakeword.py`, `PHRASE_MODELS["hey_atlas"]`), so one
         * threshold still means one thing on both. Its SHA-256 is pinned in
         * `jarvis_wakeword.KNOWN_FILES` and checked against this copy by
         * `backend/test_voice_upgrades.py`.
         *
         * `hey_jarvis_v0.1.onnx` is still in the folder: no code here loads it,
         * but it is this repository's only real copy of openWakeWord's pinned
         * bytes and two backend suites build a fake PC model folder from it.
         */
        const val WAKE_FILE = "hey_atlas.onnx"

        /** Throws if a model will not load; the caller says so and stops. */
        fun load(mel: ByteArray, emb: ByteArray, wake: ByteArray): OrtWakeModels {
            val env = OrtEnvironment.getEnvironment()
            fun session(bytes: ByteArray): OrtSession {
                val opts = OrtSession.SessionOptions()
                opts.setIntraOpNumThreads(1)
                opts.setInterOpNumThreads(1)
                return env.createSession(bytes, opts)
            }
            val m = session(mel)
            val e = runCatching { session(emb) }.getOrElse { m.close(); throw it }
            val w = runCatching { session(wake) }.getOrElse { m.close(); e.close(); throw it }
            return OrtWakeModels(env, m, e, w)
        }
    }
}
