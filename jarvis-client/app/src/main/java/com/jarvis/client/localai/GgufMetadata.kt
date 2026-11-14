package com.jarvis.client.localai

import java.io.BufferedInputStream
import java.io.ByteArrayInputStream
import java.io.File
import java.io.FileInputStream
import java.io.IOException
import java.io.InputStream
import kotlin.math.max

/**
 * The GGUF header reader: just enough of the format to tell the owner what a
 * model is and whether this phone can hold it.
 *
 * ## Where this comes from
 *
 * This is a Kotlin re-expression of PrivateLM's
 * `lib/services/gguf_metadata.dart` (`orailnoor/cross-platform-llm-client`,
 * MIT, © 2025 dragneel2074). The logic is the same - magic, version, the
 * metadata key/value table, the architecture's block/context/embedding/head
 * fields, the KV-cache estimate and the largest context that fits - and the
 * three estimation constants are carried across unchanged on purpose, because
 * they were calibrated on real hardware rather than guessed:
 *
 * > Calibrated on a Pixel 8 (Vulkan): Qwen2.5-1.5B Q4_K_M at 4096 ctx grew the
 * > app by ~1813 MB = 1066 MB weights + 112 MB KV + ~635 MB overhead.
 *
 * The Dart file is NOT vendored and its Flutter layer is not copied. See
 * `THIRD-PARTY-NOTICES.txt` for the attribution and `docs/ARCHITECTURE.md`
 * section 8 for why the phone alone has this.
 *
 * ## What it reads, and what it deliberately does not
 *
 * Only the header. Tensor data is never touched, so a 5 GB model costs one
 * short read, not a 5 GB one. Arrays inside the metadata (the tokenizer's
 * 150,000 strings, for example) are SKIPPED rather than kept: the reader
 * records their item type and count and steps over the bytes, so a vocabulary
 * cannot allocate a phone out of memory merely by being listed.
 *
 * ## Refusing is normal
 *
 * A file that is not GGUF, is v1 (32-bit counts), is cut short, claims an
 * impossible number of entries, or is missing the architecture fields is
 * refused with [Read.Refused] carrying one plain sentence. Every case is
 * exercised by `GgufMetadataTest` against small binary fixtures in
 * `src/test/resources/gguf/`; no real model and no network is involved.
 */
object GgufMetadata {

    /** The four bytes every GGUF file starts with. */
    val MAGIC = byteArrayOf(0x47, 0x47, 0x55, 0x46) // "GGUF"

    /** v1 used 32-bit counts and cannot be read by this reader. */
    const val MIN_VERSION = 2L

    /**
     * Metadata lives at the start of the file. A file whose header claims to
     * need more than this is refused rather than walked through: that is what
     * corrupt and hostile files do.
     */
    const val MAX_METADATA_BYTES: Long = 64L * 1024 * 1024

    /** A single text value longer than this is refused. */
    const val MAX_STRING_BYTES: Long = 1L * 1024 * 1024

    /** Sanity limits for the two counts in the header. */
    const val MAX_KEY_VALUE_COUNT: Long = 1_000_000L
    const val MAX_TENSOR_COUNT: Long = 10_000_000L

    /** Sanity limit for one array's item count. */
    const val MAX_ARRAY_COUNT: Long = 10_000_000L

    /** Nested arrays are legal in the format but never useful this deep. */
    const val MAX_ARRAY_DEPTH: Int = 8

    /** The smallest context worth loading; also the floor of [GgufInfo.maxContextFitting]. */
    const val MIN_CONTEXT_TOKENS: Int = 512

    /** Context sizes are chosen in this step, the same 512 the Dart reader uses. */
    const val CONTEXT_STEP: Int = 512

    /** A cap on the binary search, so a corrupt `context_length` cannot loop for minutes. */
    const val MAX_CONTEXT_STEPS: Int = 2_048

    /** The result of reading one file: either the facts, or one plain refusal. */
    sealed interface Read {

        data class Ok(val info: GgufInfo) : Read

        data class Refused(val reason: String) : Read
    }

    /**
     * Reads [file]'s header. Never throws: every failure comes back as
     * [Read.Refused] with words the Local AI screen can show as they are.
     */
    fun read(file: File): Read {
        if (!file.isFile) return Read.Refused(NOT_A_FILE_WORDS)
        val length = file.length()
        if (length < MIN_HEADER_BYTES) return Read.Refused(TRUNCATED_WORDS)
        return try {
            BufferedInputStream(FileInputStream(file), READ_BUFFER_BYTES).use { input ->
                readStream(input, length)
            }
        } catch (refused: GgufException) {
            Read.Refused(refused.reason)
        } catch (io: IOException) {
            Read.Refused(UNREADABLE_WORDS)
        } catch (denied: SecurityException) {
            Read.Refused(UNREADABLE_WORDS)
        }
    }

    /**
     * The same reader over bytes already in memory. The tests use this with
     * their fixtures; the app uses [read] with a file.
     */
    fun read(bytes: ByteArray): Read = try {
        ByteArrayInputStream(bytes).use { input -> readStream(input, bytes.size.toLong()) }
    } catch (refused: GgufException) {
        Read.Refused(refused.reason)
    } catch (io: IOException) {
        Read.Refused(UNREADABLE_WORDS)
    }

    private fun readStream(input: InputStream, length: Long): Read {
        val cursor = Cursor(input, length)

        val magic = cursor.bytes(4)
        if (!magic.contentEquals(MAGIC)) return Read.Refused(NOT_GGUF_WORDS)

        val version = cursor.u32()
        if (version < MIN_VERSION) return Read.Refused(OLD_VERSION_WORDS)

        val tensorCount = cursor.u64()
        if (tensorCount < 0L || tensorCount > MAX_TENSOR_COUNT) {
            return Read.Refused(BAD_HEADER_WORDS)
        }
        val metadataCount = cursor.u64()
        if (metadataCount < 0L || metadataCount > MAX_KEY_VALUE_COUNT) {
            return Read.Refused(BAD_HEADER_WORDS)
        }

        val values = LinkedHashMap<String, Any?>()
        var index = 0L
        while (index < metadataCount) {
            val key = cursor.string()
            val type = cursor.u32().toInt()
            if (GgufValueType.of(type) == null) return Read.Refused(UNKNOWN_TYPE_WORDS)
            values[key] = cursor.value(type, keep = true, depth = 0)
            index++
        }

        val architecture = values[KEY_ARCHITECTURE] as? String
            ?: return Read.Refused(NO_ARCHITECTURE_WORDS)

        val layers = intOf(values, architecture, "block_count")
        val embedding = intOf(values, architecture, "embedding_length")
        val heads = intOf(values, architecture, "attention.head_count")
        if (layers == null || layers <= 0 || embedding == null || embedding <= 0 ||
            heads == null || heads <= 0
        ) {
            return Read.Refused(MISSING_FIELDS_WORDS)
        }

        val info = GgufInfo(
            architecture = architecture,
            name = values[KEY_NAME] as? String,
            layers = layers,
            trainedContext = intOf(values, architecture, "context_length") ?: DEFAULT_CONTEXT,
            embeddingLength = embedding,
            headCount = heads,
            headCountKv = intOf(values, architecture, "attention.head_count_kv") ?: heads,
            keyLength = intOf(values, architecture, "attention.key_length"),
            valueLength = intOf(values, architecture, "attention.value_length"),
            fileBytes = length,
            version = version.toInt(),
            tensorCount = tensorCount,
            metadataCount = metadataCount,
            fileType = (values[KEY_FILE_TYPE] as? Number)?.toInt(),
            metadata = values,
        )
        return Read.Ok(info)
    }

    private fun intOf(values: Map<String, Any?>, architecture: String, field: String): Int? =
        (values["$architecture.$field"] as? Number)?.toInt()

    /** The keys this reader names; everything else stays in [GgufInfo.metadata]. */
    const val KEY_ARCHITECTURE = "general.architecture"
    const val KEY_NAME = "general.name"
    const val KEY_FILE_TYPE = "general.file_type"

    /** What the Dart reader assumes when a model does not state its trained context. */
    const val DEFAULT_CONTEXT = 4096

    private const val MIN_HEADER_BYTES = 4L + 4L + 8L + 8L
    private const val READ_BUFFER_BYTES = 1 shl 20

    // ------------------------------------------------------------- refusals --

    const val NOT_A_FILE_WORDS =
        "There is no model file at that place on this phone."
    const val NOT_GGUF_WORDS =
        "That file is not a .gguf model, so Jarvis cannot run it."
    const val OLD_VERSION_WORDS =
        "That model file is an old GGUF version (v1). Jarvis can only read v2 and newer."
    const val BAD_HEADER_WORDS =
        "That model file's header is damaged: it claims more entries than a real model has."
    const val TRUNCATED_WORDS =
        "That model file is cut short: its header says more than the file holds."
    const val TOO_LARGE_WORDS =
        "That model file's header is bigger than the 64 MB Jarvis reads in one go, so it was not opened."
    const val UNKNOWN_TYPE_WORDS =
        "That model file uses a metadata value type Jarvis does not know."
    const val BAD_STRING_WORDS =
        "That model file is damaged: one of its text values has an impossible length."
    const val NO_ARCHITECTURE_WORDS =
        "That .gguf file does not say which model architecture it is, so Jarvis cannot run it."
    const val MISSING_FIELDS_WORDS =
        "That .gguf file's header is missing the layer, embedding or head counts Jarvis needs."
    const val UNREADABLE_WORDS =
        "That model file could not be read from this phone's storage."

    /** A refusal raised while walking the header. */
    private class GgufException(val reason: String) : Exception(reason)

    /**
     * A forward-only reader with the Dart reader's two guards: never read past
     * the file, and never read past [MAX_METADATA_BYTES]. Every count is
     * checked before it is used, so a header saying "4 billion entries" costs
     * one comparison rather than a phone that hangs.
     */
    private class Cursor(
        private val input: InputStream,
        private val length: Long,
    ) {

        private var position: Long = 0L

        private fun ensure(bytes: Long) {
            if (bytes < 0L || position + bytes < position) throw GgufException(BAD_STRING_WORDS)
            val end = position + bytes
            if (end > length) throw GgufException(TRUNCATED_WORDS)
            if (end > MAX_METADATA_BYTES) throw GgufException(TOO_LARGE_WORDS)
        }

        fun bytes(count: Int): ByteArray {
            if (count < 0) throw GgufException(BAD_STRING_WORDS)
            ensure(count.toLong())
            if (count == 0) return ByteArray(0)
            val out = ByteArray(count)
            var read = 0
            while (read < count) {
                val got = input.read(out, read, count - read)
                if (got < 0) throw GgufException(TRUNCATED_WORDS)
                read += got
            }
            position += count
            return out
        }

        /** One reused buffer: a 150,000-string vocabulary must not allocate 150,000 arrays. */
        private val skipBuffer = ByteArray(SKIP_BUFFER_BYTES)

        fun skip(count: Long) {
            ensure(count)
            var left = count
            while (left > 0L) {
                val ask = minOf(skipBuffer.size.toLong(), left).toInt()
                val got = input.read(skipBuffer, 0, ask)
                if (got < 0) throw GgufException(TRUNCATED_WORDS)
                left -= got
            }
            position += count
        }

        fun u8(): Int = bytes(1)[0].toInt() and 0xFF

        fun u16(): Int {
            val b = bytes(2)
            return (b[0].toInt() and 0xFF) or ((b[1].toInt() and 0xFF) shl 8)
        }

        fun u32(): Long {
            val b = bytes(4)
            var value = 0L
            for (i in 3 downTo 0) value = (value shl 8) or (b[i].toLong() and 0xFF)
            return value
        }

        fun u64(): Long {
            val b = bytes(8)
            var value = 0L
            for (i in 7 downTo 0) value = (value shl 8) or (b[i].toLong() and 0xFF)
            return value
        }

        fun string(): String {
            val size = u64()
            if (size < 0L || size > MAX_STRING_BYTES) throw GgufException(BAD_STRING_WORDS)
            if (size == 0L) return ""
            return String(bytes(size.toInt()), Charsets.UTF_8)
        }

        fun skipString() {
            val size = u64()
            if (size < 0L || size > MAX_STRING_BYTES) throw GgufException(BAD_STRING_WORDS)
            skip(size)
        }

        /**
         * Reads one metadata value. Arrays are summarised and skipped; their
         * contents are never materialised.
         */
        fun value(type: Int, keep: Boolean, depth: Int): Any? {
            when (type) {
                GgufValueType.STRING.id -> {
                    if (!keep) {
                        skipString()
                        return null
                    }
                    return string()
                }

                GgufValueType.ARRAY.id -> {
                    if (depth >= MAX_ARRAY_DEPTH) throw GgufException(BAD_HEADER_WORDS)
                    val itemType = u32().toInt()
                    val item = GgufValueType.of(itemType)
                        ?: throw GgufException(UNKNOWN_TYPE_WORDS)
                    val count = u64()
                    if (count < 0L || count > MAX_ARRAY_COUNT) {
                        throw GgufException(BAD_HEADER_WORDS)
                    }
                    when {
                        item.size != null -> skip(item.size.toLong() * count)
                        item == GgufValueType.STRING -> {
                            // Every string carries an 8-byte length, so this is
                            // the least the array could occupy. Refusing here
                            // stops a hostile count before the loop.
                            ensureAtLeast(8L * count)
                            var i = 0L
                            while (i < count) {
                                skipString()
                                i++
                            }
                        }
                        else -> {
                            ensureAtLeast(8L * count)
                            var i = 0L
                            while (i < count) {
                                value(itemType, keep = false, depth = depth + 1)
                                i++
                            }
                        }
                    }
                    return if (keep) GgufArray(itemType = itemType, count = count) else null
                }

                else -> {
                    val value = GgufValueType.of(type) ?: throw GgufException(UNKNOWN_TYPE_WORDS)
                    val size = value.size ?: throw GgufException(UNKNOWN_TYPE_WORDS)
                    val raw = bytes(size)
                    if (!keep) return null
                    return when (value) {
                        GgufValueType.UINT8 -> raw[0].toInt() and 0xFF
                        GgufValueType.INT8 -> raw[0].toInt()
                        GgufValueType.UINT16 -> {
                            (raw[0].toInt() and 0xFF) or ((raw[1].toInt() and 0xFF) shl 8)
                        }
                        GgufValueType.INT16 -> {
                            ((raw[0].toInt() and 0xFF) or (raw[1].toInt() shl 8)).toShort().toInt()
                        }
                        GgufValueType.UINT32 -> leU32(raw)
                        GgufValueType.INT32 -> leU32(raw).toInt()
                        GgufValueType.FLOAT32 -> Float.fromBits(leU32(raw).toInt())
                        GgufValueType.BOOL -> raw[0].toInt() != 0
                        GgufValueType.UINT64 -> leU64(raw)
                        GgufValueType.INT64 -> leU64(raw)
                        GgufValueType.FLOAT64 -> Double.fromBits(leU64(raw))
                        GgufValueType.STRING, GgufValueType.ARRAY -> null
                    }
                }
            }
        }

        private fun ensureAtLeast(bytes: Long) {
            val remainingInFile = length - position
            if (bytes > remainingInFile) throw GgufException(TRUNCATED_WORDS)
            if (position + bytes > MAX_METADATA_BYTES) throw GgufException(TOO_LARGE_WORDS)
        }

        private fun leU32(raw: ByteArray): Long {
            var value = 0L
            for (i in 3 downTo 0) value = (value shl 8) or (raw[i].toLong() and 0xFF)
            return value
        }

        private fun leU64(raw: ByteArray): Long {
            var value = 0L
            for (i in 7 downTo 0) value = (value shl 8) or (raw[i].toLong() and 0xFF)
            return value
        }

        private companion object {
            const val SKIP_BUFFER_BYTES = 8 * 1024
        }
    }
}

/** Every GGUF metadata value type this reader knows, with its fixed size. */
enum class GgufValueType(val id: Int, val size: Int?, val label: String) {
    UINT8(0, 1, "u8"),
    INT8(1, 1, "i8"),
    UINT16(2, 2, "u16"),
    INT16(3, 2, "i16"),
    UINT32(4, 4, "u32"),
    INT32(5, 4, "i32"),
    FLOAT32(6, 4, "f32"),
    BOOL(7, 1, "bool"),
    STRING(8, null, "string"),
    ARRAY(9, null, "array"),
    UINT64(10, 8, "u64"),
    INT64(11, 8, "i64"),
    FLOAT64(12, 8, "f64");

    companion object {
        fun of(id: Int): GgufValueType? = entries.firstOrNull { it.id == id }
    }
}

/** An array in the metadata, kept as its shape only - never its contents. */
data class GgufArray(val itemType: Int, val count: Long) {
    val itemLabel: String get() = GgufValueType.of(itemType)?.label ?: "type $itemType"
}

/**
 * What a GGUF header says, and the two memory estimates the Dart reader
 * established. All of it is [GgufMetadata]'s answer; nothing here guesses.
 */
data class GgufInfo(
    val architecture: String,
    val name: String?,
    val layers: Int,
    val trainedContext: Int,
    val embeddingLength: Int,
    val headCount: Int,
    val headCountKv: Int,
    val keyLength: Int?,
    val valueLength: Int?,
    val fileBytes: Long,
    val version: Int,
    val tensorCount: Long,
    val metadataCount: Long,
    val fileType: Int?,
    val metadata: Map<String, Any?>,
) {

    /** A short quant name from the header's file type, or null if it has none. */
    val quant: String? get() = fileType?.let { GgufFileType.label(it) }

    /**
     * The per-head key/value widths. llama.cpp stores them explicitly in some
     * architectures and leaves them implied in others; the Dart reader's rule
     * (explicit, else embedding length / head count) is kept.
     */
    val headDimK: Int
        get() = keyLength ?: if (headCount > 0) embeddingLength / headCount else 0

    val headDimV: Int
        get() = valueLength ?: if (headCount > 0) embeddingLength / headCount else 0

    /**
     * Bytes of KV cache for [contextTokens], f16 keys and values - llama.cpp's
     * default. The one place this app predicts a number the file cannot state.
     */
    fun kvCacheBytes(contextTokens: Int): Long {
        val tokens = contextTokens.coerceAtLeast(0)
        return layers.toLong() *
            tokens *
            headCountKv *
            (headDimK.toLong() + headDimV.toLong()) *
            BYTES_PER_KV_ELEMENT
    }

    /**
     * Working memory beyond weights and KV cache: compute buffers, driver
     * allocations, the runtime and allocator slack. Errs HIGH on purpose,
     * because under-estimating is what gets the app killed by Android.
     */
    fun overheadBytes(contextTokens: Int): Long {
        val tokens = contextTokens.coerceAtLeast(0)
        return OVERHEAD_BASE_BYTES +
            (fileBytes * OVERHEAD_FILE_PERCENT / 100.0).toLong() +
            tokens * OVERHEAD_PER_TOKEN_BYTES
    }

    /** Estimated memory to load this model and use [contextTokens]. */
    fun estimateBytes(contextTokens: Int): Long =
        fileBytes + kvCacheBytes(contextTokens) + overheadBytes(contextTokens)

    /**
     * The largest multiple of 512 tokens (at least 512) whose estimate fits in
     * [availableBytes], or null if even 512 tokens does not fit. Monotonic in
     * the context size, so a binary search is exact rather than a guess.
     */
    fun maxContextFitting(availableBytes: Long): Int? {
        if (availableBytes <= 0L) return null
        if (estimateBytes(GgufMetadata.MIN_CONTEXT_TOKENS) > availableBytes) return null
        val steps = (max(trainedContext, GgufMetadata.MIN_CONTEXT_TOKENS) /
            GgufMetadata.CONTEXT_STEP).coerceIn(1, GgufMetadata.MAX_CONTEXT_STEPS)
        var low = 1
        var high = steps
        while (low < high) {
            val middle = (low + high + 1) / 2
            if (estimateBytes(middle * GgufMetadata.CONTEXT_STEP) <= availableBytes) {
                low = middle
            } else {
                high = middle - 1
            }
        }
        return low * GgufMetadata.CONTEXT_STEP
    }

    companion object {
        const val BYTES_PER_KV_ELEMENT = 2L

        /** 400 MB: the floor the calibration found on a Pixel 8. */
        const val OVERHEAD_BASE_BYTES = 400L * 1024 * 1024

        /** Plus a fifth of the weights again for the load itself. */
        const val OVERHEAD_FILE_PERCENT = 20.0

        /** Plus 4 KB per context token. */
        const val OVERHEAD_PER_TOKEN_BYTES = 4L * 1024
    }
}

/**
 * The header's `general.file_type` numbers, mapped to the short names people
 * actually use. An unknown number is shown as "type N" - never guessed into a
 * quantisation name that would be a lie about how big or how fast a model is.
 *
 * The numbers are llama.cpp's `llama_ftype` enum. Only names certain enough to
 * be useful are written; the rest fall back honestly.
 */
object GgufFileType {

    /** The names this app will state from the header, largest first for matching. */
    val KNOWN_LABELS: List<String> = listOf(
        "Q4_0_4_4", "Q4_0_4_8", "Q4_0_8_8",
        "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q3_K_M", "Q3_K_S", "Q3_K_L",
        "Q2_K", "Q6_K", "Q8_0", "Q5_0", "Q5_1", "Q4_0", "Q4_1",
        "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ3_XXS", "IQ3_S", "IQ1_S", "IQ1_M",
        "IQ4_NL", "IQ4_XS", "BF16", "F16", "F32",
    )

    fun label(id: Int): String = when (id) {
        0 -> "F32"
        1 -> "F16"
        2 -> "Q4_0"
        3 -> "Q4_1"
        7 -> "Q8_0"
        8 -> "Q5_0"
        9 -> "Q5_1"
        10 -> "Q2_K"
        11 -> "Q3_K_S"
        12 -> "Q3_K_M"
        13 -> "Q3_K_L"
        14 -> "Q4_K_S"
        15 -> "Q4_K_M"
        16 -> "Q5_K_S"
        17 -> "Q5_K_M"
        18 -> "Q6_K"
        19 -> "IQ2_XXS"
        20 -> "IQ2_XS"
        21 -> "IQ3_XXS"
        22 -> "IQ1_S"
        23 -> "IQ4_NL"
        24 -> "IQ3_S"
        25 -> "IQ2_S"
        26 -> "IQ4_XS"
        27 -> "IQ1_M"
        28 -> "BF16"
        29 -> "Q4_0_4_4"
        30 -> "Q4_0_4_8"
        31 -> "Q4_0_8_8"
        1024 -> "guessed"
        else -> "type $id"
    }

    /**
     * A quant name found in the file's own name, e.g. `...-Q4_K_M.gguf`.
     * Used only when the header has no file type, and the screen says
     * "(from the file name)" when it does, so this is never presented as a
     * fact read from the model.
     */
    fun fromName(fileName: String): String? {
        val upper = fileName.uppercase()
        return KNOWN_LABELS.firstOrNull { upper.contains(it) }
    }
}
