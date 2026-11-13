package com.jarvis.client.localai

import java.util.Locale

/**
 * What this phone can safely be asked to run.
 *
 * ## Where this comes from
 *
 * A Kotlin re-expression of PrivateLM's `lib/services/device_info_service.dart`
 * (`orailnoor/cross-platform-llm-client`, MIT, © 2025 dragneel2074). The RAM
 * tier table - 4 GB and under, 6, 8, 12, and above - is carried across with
 * the same numbers: context size, reply budget, maximum context and the safe
 * reply cap. What is added here is the refusal: the Dart service offered the
 * numbers and left the fit check to its model downloader, while this screen
 * must tell the owner in one plain sentence whether the file they just picked
 * can run on the phone in their hand.
 *
 * ## The numbers are not a promise
 *
 * Android reports total RAM, not what this app can actually get. The budget
 * below takes [RAM_BUDGET_PERCENT] of total RAM and [MAX_THREADS_CAP] CPU
 * threads, leaving room for the system, the rest of Jarvis and the owner's own
 * phone. The estimate itself comes from [GgufInfo], whose three constants were
 * calibrated on a Pixel 8 and deliberately err high. When in doubt this file
 * refuses; a refusal is a sentence, while an out-of-memory kill is a closed
 * app.
 *
 * Pure Kotlin, no Android imports: [DeviceTiersAndroid] reads the phone and
 * hands the numbers in, so `DeviceTiersTest` holds every boundary on a JVM.
 */
object DeviceTiers {

    /** The four RAM tiers the Dart service names, in plain words. */
    enum class Bucket(val word: String) {
        LOW("low memory"),
        MID("mid-range"),
        HIGH("high-end"),
        ULTRA("large memory"),
    }

    /** The numbers for one phone: what to load with, and how big a model may be. */
    data class Tier(
        val bucket: Bucket,
        /** Total RAM in GiB, or 0.0 when the phone did not report it. */
        val totalRamGb: Double,
        /** Android's per-app heap class in MB - read, and reported, never used as the cap. */
        val heapClassMb: Int,
        val cores: Int,
        val contextTokens: Int,
        val maxTokens: Int,
        val maxContextTokens: Int,
        val maxSafeTokens: Int,
        val safeThreads: Int,
        /** The memory this app may try to use, in bytes. */
        val budgetBytes: Long,
        /** A rough pre-check on the file's own size, before its header is read. */
        val maxModelBytes: Long,
    ) {

        val ramKnown: Boolean get() = totalRamGb > 0.0

        /** One line about this phone, for the screen's own explanation. */
        val summary: String
            get() {
                val ram = if (ramKnown) {
                    String.format(Locale.UK, "%.1f GB", totalRamGb)
                } else {
                    "an unknown amount"
                }
                val context = String.format(Locale.UK, "%,d", contextTokens)
                return "This phone has $ram of memory and $cores processor cores. " +
                    "It uses $safeThreads of them for the model, and up to $context tokens of " +
                    "context. It can give a model about ${bytesText(budgetBytes)}."
            }

        /** Whether the owner's file is too big even before its header is read. */
        fun fileTooBig(fileBytes: Long): Boolean = fileBytes > maxModelBytes

        /**
         * Whether [info] can be loaded and used on this phone, and at what
         * context size. For a file whose header could not be read, only the
         * file-size check is possible, and the answer says so rather than
         * pretending to know.
         */
        fun verdict(info: GgufInfo?): ModelVerdict {
            if (info == null) {
                return ModelVerdict.Unknown(
                    "Jarvis could not read this model's header, so it cannot say whether it " +
                        "fits. This phone can give a model about ${bytesText(budgetBytes)}.",
                )
            }

            val preferred = minOf(contextTokens, maxOf(GgufMetadata.MIN_CONTEXT_TOKENS, info.trainedContext))
            val atPreferred = info.estimateBytes(preferred)
            if (atPreferred <= budgetBytes) {
                return ModelVerdict.Fits(
                    contextTokens = preferred,
                    estimatedBytes = atPreferred,
                    shortened = preferred < contextTokens,
                    words = "Fits on this phone: about ${bytesText(atPreferred)} of memory, " +
                        "at ${tokensText(preferred)} tokens of context.",
                )
            }

            // Too big at the recommended context. A shorter context may still
            // fit, which is the honest "yes, but" answer.
            val fitted = info.maxContextFitting(budgetBytes)
            if (fitted != null) {
                val estimate = info.estimateBytes(fitted)
                return ModelVerdict.Fits(
                    contextTokens = fitted,
                    estimatedBytes = estimate,
                    shortened = true,
                    words = "Fits on this phone, with a shorter memory: about " +
                        "${bytesText(estimate)} at ${tokensText(fitted)} tokens of context.",
                )
            }

            val atMinimum = info.estimateBytes(GgufMetadata.MIN_CONTEXT_TOKENS)
            return ModelVerdict.TooBig(
                estimatedBytes = atMinimum,
                budgetBytes = budgetBytes,
                words = "Too big for this phone: even a short conversation would need about " +
                    "${bytesText(atMinimum)}, and this phone can give about " +
                    "${bytesText(budgetBytes)}. A smaller model, or one saved in a smaller " +
                    "format, would fit.",
            )
        }
    }

    /** The answer to "will this model run here?", with the sentence to show. */
    sealed interface ModelVerdict {

        val words: String

        val fits: Boolean

        data class Fits(
            val contextTokens: Int,
            val estimatedBytes: Long,
            /** True when the recommended context did not fit and this is the reduced one. */
            val shortened: Boolean,
            override val words: String,
        ) : ModelVerdict {
            override val fits: Boolean get() = true
        }

        data class TooBig(
            val estimatedBytes: Long,
            val budgetBytes: Long,
            override val words: String,
        ) : ModelVerdict {
            override val fits: Boolean get() = false
        }

        data class Unknown(override val words: String) : ModelVerdict {
            override val fits: Boolean get() = false
        }
    }

    /** One GiB, the unit Android's `totalMem` is read in here. */
    const val GIB: Long = 1024L * 1024 * 1024

    /** One MiB, for the small-file labels. */
    const val MIB: Long = 1024L * 1024

    /**
     * How much of the phone's RAM a model may plan to use. Deliberately under
     * half: Android keeps the system, the launcher, the rest of Jarvis and
     * whatever the owner left open in the other half.
     */
    const val RAM_BUDGET_PERCENT: Long = 45L

    /**
     * An unknown total is treated as this small rather than as unlimited: a
     * phone that cannot report its RAM must not be handed a 4 GB model.
     */
    const val UNKNOWN_RAM_BUDGET_BYTES: Long = 1536L * 1024 * 1024

    /** Never fewer than this many bytes, so a tiny reported total cannot zero the budget. */
    const val MIN_BUDGET_BYTES: Long = 1024L * 1024 * 1024

    /** The most threads this app will hand a CPU engine, leaving cores for the UI. */
    const val MAX_THREADS_CAP: Int = 4

    /**
     * The recommended numbers for a phone with [totalRamGb] of RAM - the Dart
     * service's table, branch for branch.
     */
    fun tableFor(totalRamGb: Double): Table = when {
        totalRamGb <= 4.0 -> Table(1024, 256, 2048, 512)
        totalRamGb <= 6.0 -> Table(2048, 512, 4096, 1024)
        totalRamGb <= 8.0 -> Table(4096, 1024, 8192, 2048)
        totalRamGb <= 12.0 -> Table(4096, 2048, 8192, 4096)
        else -> Table(8192, 4096, 16384, 4096)
    }

    /** One row of the RAM tier table. */
    data class Table(
        val contextTokens: Int,
        val maxTokens: Int,
        val maxContextTokens: Int,
        val maxSafeTokens: Int,
    )

    /** The bucket name the Dart service prints, for the same RAM. */
    fun bucketFor(totalRamGb: Double): Bucket = when {
        totalRamGb <= 4.0 -> Bucket.LOW
        totalRamGb <= 6.0 -> Bucket.MID
        totalRamGb <= 8.0 -> Bucket.HIGH
        else -> Bucket.ULTRA
    }

    /**
     * Threads for a phone with [cores] processors: one fewer than the phone
     * has (so the UI and the system keep a core), never more than
     * [MAX_THREADS_CAP], never fewer than one.
     */
    fun safeThreads(cores: Int): Int {
        if (cores <= 0) return 1
        return (cores - 1).coerceIn(1, MAX_THREADS_CAP)
    }

    /**
     * The whole recommendation for one phone, from the three numbers Android
     * gives. [totalRamBytes] is `ActivityManager.MemoryInfo.totalMem`;
     * [memoryClassMb] is `ActivityManager.memoryClass`.
     */
    fun of(totalRamBytes: Long, memoryClassMb: Int, cores: Int): Tier {
        val totalGb = if (totalRamBytes > 0L) totalRamBytes.toDouble() / GIB else 0.0
        val table = tableFor(totalGb)
        val budget = when {
            totalRamBytes <= 0L -> UNKNOWN_RAM_BUDGET_BYTES
            else -> maxOf(MIN_BUDGET_BYTES, totalRamBytes * RAM_BUDGET_PERCENT / 100L)
        }
        return Tier(
            bucket = bucketFor(totalGb),
            totalRamGb = totalGb,
            heapClassMb = memoryClassMb,
            cores = cores,
            contextTokens = table.contextTokens,
            maxTokens = table.maxTokens,
            maxContextTokens = table.maxContextTokens,
            maxSafeTokens = table.maxSafeTokens,
            safeThreads = safeThreads(cores),
            budgetBytes = budget,
            maxModelBytes = (budget - GgufInfo.OVERHEAD_BASE_BYTES).coerceAtLeast(0L),
        )
    }

    /** Bytes as a person reads them: "5.4 GB", "812 MB". */
    fun bytesText(bytes: Long): String = when {
        bytes >= GIB -> String.format(Locale.UK, "%.1f GB", bytes.toDouble() / GIB)
        bytes >= MIB -> String.format(Locale.UK, "%d MB", bytes / MIB)
        else -> "$bytes bytes"
    }

    private fun tokensText(tokens: Int): String = String.format(Locale.UK, "%,d", tokens)
}
