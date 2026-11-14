package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * The GGUF reader against small binary fixtures in `src/test/resources/gguf/`
 * - no real model, no network, no Android.
 *
 * Every check the screen depends on is held here: the header fields, every
 * value type the Dart reader supported, arrays kept as shape only, the two
 * memory estimates, and a refusal (not a crash) for each kind of broken file.
 */
class GgufMetadataTest {

    private fun fixture(name: String): ByteArray =
        javaClass.getResourceAsStream("/gguf/$name")?.readBytes()
            ?: error("missing fixture /gguf/$name")

    private fun ok(name: String): GgufInfo {
        val read = GgufMetadata.read(fixture(name))
        assertTrue("$name should be readable, was $read", read is GgufMetadata.Read.Ok)
        return (read as GgufMetadata.Read.Ok).info
    }

    private fun refused(name: String): String {
        val read = GgufMetadata.read(fixture(name))
        assertTrue("$name should be refused, was $read", read is GgufMetadata.Read.Refused)
        return (read as GgufMetadata.Read.Refused).reason
    }

    @Test
    fun aRealQwenHeaderIsReadFieldByField() {
        val info = ok("qwen2-valid.gguf")
        assertEquals("qwen2", info.architecture)
        assertEquals("Qwen2.5 0.5B Instruct", info.name)
        assertEquals(3, info.version)
        assertEquals(0L, info.tensorCount)
        assertEquals(24L, info.metadataCount)
        assertEquals(24, info.layers)
        assertEquals(32768, info.trainedContext)
        assertEquals(896, info.embeddingLength)
        assertEquals(14, info.headCount)
        assertEquals(2, info.headCountKv)
        assertEquals(64, info.keyLength)
        assertEquals(64, info.valueLength)
        assertEquals(15, info.fileType)
        assertEquals("Q4_K_M", info.quant)
        assertEquals(890L, info.fileBytes)
    }

    @Test
    fun everyScalarValueTypeIsRead() {
        val values = ok("qwen2-valid.gguf").metadata
        assertEquals(200, values["some.u8"])
        assertEquals(-5, values["some.i8"])
        assertEquals(65530, values["some.u16"])
        assertEquals(-1234, values["some.i16"])
        assertEquals(-70000, values["some.i32"])
        assertEquals(0.5f, values["some.f32"])
        assertEquals(true, values["some.bool"])
        assertEquals(9_000_000_000L, values["some.u64"])
        assertEquals(-9_000_000_000L, values["some.i64"])
        assertEquals(1.25, values["some.f64"])
    }

    @Test
    fun arraysAreKeptAsShapeOnlyNotContents() {
        val values = ok("qwen2-valid.gguf").metadata
        val tokens = values["tokenizer.ggml.tokens"] as GgufArray
        assertEquals(GgufValueType.STRING.id, tokens.itemType)
        assertEquals(3L, tokens.count)
        assertEquals("string", tokens.itemLabel)

        val flags = values["some.flags"] as GgufArray
        assertEquals(GgufValueType.BOOL.id, flags.itemType)
        assertEquals(2L, flags.count)

        val counts = values["some.counts"] as GgufArray
        assertEquals(GgufValueType.UINT32.id, counts.itemType)
        assertEquals(3L, counts.count)

        // Nested arrays are walked without being materialised.
        val nested = values["some.nested"] as GgufArray
        assertEquals(GgufValueType.ARRAY.id, nested.itemType)
        assertEquals(2L, nested.count)
    }

    @Test
    fun aFileThatIsNotGgufIsRefusedWithPlainWords() {
        assertEquals(GgufMetadata.NOT_GGUF_WORDS, refused("bad-magic.gguf"))
    }

    @Test
    fun aVersionOneFileIsRefused() {
        assertEquals(GgufMetadata.OLD_VERSION_WORDS, refused("v1.gguf"))
    }

    @Test
    fun aCutShortFileIsRefusedRatherThanGuessedAt() {
        assertEquals(GgufMetadata.TRUNCATED_WORDS, refused("truncated.gguf"))
    }

    @Test
    fun aHeaderWithoutAnArchitectureIsRefused() {
        assertEquals(GgufMetadata.NO_ARCHITECTURE_WORDS, refused("no-arch.gguf"))
    }

    @Test
    fun aHeaderMissingTheCountsIsRefused() {
        assertEquals(GgufMetadata.MISSING_FIELDS_WORDS, refused("missing-fields.gguf"))
    }

    @Test
    fun animpossibleEntryCountIsRefusedWithoutWalkingIt() {
        assertEquals(GgufMetadata.BAD_HEADER_WORDS, refused("huge-count.gguf"))
    }

    @Test
    fun anUnknownValueTypeIsRefused() {
        assertEquals(GgufMetadata.UNKNOWN_TYPE_WORDS, refused("bad-type.gguf"))
    }

    @Test
    fun aMissingFileIsRefusedNotThrown() {
        val dir = Files.createTempDirectory("gguf-missing").toFile()
        try {
            val read = GgufMetadata.read(File(dir, "nope.gguf"))
            assertEquals(
                GgufMetadata.NOT_A_FILE_WORDS,
                (read as GgufMetadata.Read.Refused).reason,
            )
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun theKvCacheEstimateMatchesTheCalibratedFormula() {
        val info = ok("qwen2-valid.gguf")
        // 24 layers * 4096 tokens * 2 kv heads * (64 + 64) dims * 2 bytes.
        assertEquals(50_331_648L, info.kvCacheBytes(4096))
        assertEquals(0L, info.kvCacheBytes(0))
    }

    @Test
    fun theOverheadEstimateKeepsTheDartConstants() {
        val info = ok("qwen2-valid.gguf")
        // 400 MB floor + 20% of 890 bytes + 4096 tokens at 4 KB.
        assertEquals(
            400L * 1024 * 1024 + 178L + 4096L * 4096L,
            info.overheadBytes(4096),
        )
    }

    @Test
    fun theWholeEstimateIsTheSumOfItsThreeParts() {
        val info = ok("qwen2-valid.gguf")
        assertEquals(
            info.fileBytes + info.kvCacheBytes(2048) + info.overheadBytes(2048),
            info.estimateBytes(2048),
        )
    }

    @Test
    fun theLargestFittingContextIsOneThatReallyFits() {
        val info = ok("qwen2-valid.gguf")
        val budget = info.estimateBytes(4096)
        val fitted = info.maxContextFitting(budget)
        requireNotNull(fitted)
        assertTrue("fitted $fitted should be at least 4096", fitted >= 4096)
        assertTrue(info.estimateBytes(fitted) <= budget)
        // The next step up must not fit, or the answer was not the largest.
        assertTrue(info.estimateBytes(fitted + GgufMetadata.CONTEXT_STEP) > budget)
    }

    @Test
    fun aBudgetTooSmallForTheSmallestContextHasNoAnswer() {
        val info = ok("qwen2-valid.gguf")
        assertNull(info.maxContextFitting(info.estimateBytes(512) - 1))
        assertNull(info.maxContextFitting(0))
    }

    @Test
    fun aHugeBudgetStopsAtTheModelsTrainedContext() {
        val info = ok("qwen2-valid.gguf")
        assertEquals(32768, info.maxContextFitting(Long.MAX_VALUE / 4))
    }

    @Test
    fun quantNamesComeFromTheHeadersOwnNumber() {
        assertEquals("Q4_K_M", GgufFileType.label(15))
        assertEquals("F16", GgufFileType.label(1))
        assertEquals("BF16", GgufFileType.label(28))
        assertEquals("type 999", GgufFileType.label(999))
        assertEquals("guessed", GgufFileType.label(1024))
    }

    @Test
    fun aQuantNameCanFallBackToTheFilesOwnName() {
        assertEquals("Q4_K_M", GgufFileType.fromName("qwen2.5-3b-instruct-q4_k_m.gguf"))
        assertEquals("Q4_0_4_4", GgufFileType.fromName("model-Q4_0_4_4.gguf"))
        assertNull(GgufFileType.fromName("model-with-no-quant.gguf"))
        assertFalse(GgufFileType.fromName("model-q4_k_m.gguf").isNullOrBlank())
    }

    @Test
    fun readingMovesTheFileLengthIntoTheEstimate() {
        val info = ok("too-big.gguf")
        // A tiny file whose header claims an enormous model is not judged by
        // its size - the estimate is what refuses it.
        assertEquals(358L, info.fileBytes)
        assertTrue(info.estimateBytes(4096) > 1024L * 1024 * 1024 * 1024)
    }
}
