package com.jarvis.client.localai

import java.io.File
import java.io.IOException
import java.io.InputStream

/**
 * The models on this phone: one folder, `.gguf` files only, and no other door.
 *
 * ## Where the files live
 *
 * `context.getExternalFilesDir("models")` - the app's own folder on shared
 * storage ([ModelStoreAndroid.forApp]). It needs **no permission**, is removed
 * when the app is uninstalled, and is not scanned by the gallery or the file
 * manager's "recent" list. Import copies a picked document into it; Jarvis
 * never writes a model anywhere else.
 *
 * ## What this class cannot do, on purpose
 *
 * - **No network.** There is no URL, socket, HTTP client or download anywhere
 *   in this file or its callers. A model arrives only because the owner picked
 *   a file that is already on the phone.
 * - **No secret.** The store is a folder of public model files. It is never
 *   given the connection secret Jarvis uses to reach the owner's PC, an API
 *   key, a request header or anything that identifies that machine.
 *   `LocalAiShipsOffTest` reads this package and fails if one appears in it.
 * - **No silent overwrite.** A name that is already here is refused; deleting
 *   a model is its own explicit action.
 * - **No half files.** A copy lands in `<name>.part` and is renamed only after
 *   every byte is written, so a killed app leaves no file that looks like a
 *   model. A name is reduced to its last path component, so `../../x.gguf`
 *   cannot escape the folder.
 *
 * ## Testable without Android
 *
 * The constructor takes a [File] and a way to measure free space; `ModelStore
 * Test` uses a temporary folder and an in-memory stream. Only the factory in
 * [ModelStoreAndroid] knows about a `Context`.
 */
class ModelStore(
    private val root: File,
    private val freeSpace: (File) -> Long = { it.usableSpace },
    /** Keep this much space free after a copy, so the phone does not fill up. */
    private val minFreeBytes: Long = MIN_FREE_BYTES,
) {

    /** One model file on this phone. */
    data class StoredModel(
        val name: String,
        val file: File,
        val bytes: Long,
        /** Its header, or null when the file could not be read as a GGUF. */
        val info: GgufInfo?,
    ) {

        /** The header's quant name, else one found in the file's own name. */
        val quant: String? get() = info?.quant ?: GgufFileType.fromName(name)

        /** True when [quant] came from the name rather than from the model's header. */
        val quantFromName: Boolean get() = info?.quant == null && quant != null
    }

    /** The result of one import: the model, or one plain sentence saying why not. */
    sealed interface ImportResult {

        data class Ok(val model: StoredModel) : ImportResult

        data class Refused(val reason: String) : ImportResult
    }

    /** The folder itself, for the screen's own explanation. */
    val folder: File get() = root

    /**
     * Every model in the folder, newest name order, with its size and header.
     * Reading a header is one short read per file, never the weights.
     */
    fun list(): List<StoredModel> {
        val files = root.listFiles() ?: return emptyList()
        return files
            .asSequence()
            .filter { it.isFile && it.name.endsWith(EXTENSION, ignoreCase = true) }
            .sortedBy { it.name.lowercase() }
            .map { stored(it) }
            .toList()
    }

    /** The model called [name], or null when it is not here. */
    fun find(name: String): StoredModel? {
        val safe = modelName(name) ?: return null
        val file = File(root, safe)
        return if (file.isFile) stored(file) else null
    }

    /** Deletes one model. False when the name is unsafe or the file is not here. */
    fun delete(name: String): Boolean {
        val safe = modelName(name) ?: return false
        val file = File(root, safe)
        val parent = runCatching { root.canonicalFile }.getOrNull() ?: return false
        val resolved = runCatching { file.canonicalFile }.getOrNull() ?: return false
        if (resolved.parentFile != parent) return false
        return resolved.isFile && resolved.delete()
    }

    /** Free bytes on the phone's shared storage, as the import check sees them. */
    fun freeBytes(): Long = freeSpace(root)

    /**
     * Copies [input] into the folder as [displayName].
     *
     * [declaredBytes] is the SAF provider's reported size, or null when it did
     * not report one; it is used for the early free-space refusal and for the
     * progress total, and the copy is checked again as it goes. [onProgress]
     * gets `(copied, total-or-null)` roughly every 2% (or every 8 MB when the
     * total is unknown), from the calling thread.
     *
     * The stream is closed by this method: the caller hands over ownership.
     */
    fun import(
        displayName: String,
        declaredBytes: Long?,
        input: InputStream,
        onProgress: (copied: Long, total: Long?) -> Unit = { _, _ -> },
    ): ImportResult {
        val name = modelName(displayName) ?: return ImportResult.Refused(NOT_A_MODEL_WORDS)
        val total = declaredBytes?.takeIf { it > 0L }

        if (!root.isDirectory && !root.mkdirs()) {
            return ImportResult.Refused(NO_FOLDER_WORDS)
        }
        val target = File(root, name)
        if (target.exists()) {
            return ImportResult.Refused(ALREADY_HERE_WORDS.format(name))
        }

        val available = freeSpace(root)
        if (total != null && (available < minFreeBytes || total > available - minFreeBytes)) {
            return ImportResult.Refused(notEnoughWords(total, available))
        }

        val part = File(root, "$name.part")
        if (part.exists()) part.delete()
        var copied = 0L
        var finished = false
        val step = if (total != null) maxOf(PROGRESS_MIN_STEP, total / PROGRESS_STEPS) else PROGRESS_MIN_STEP
        var lastReported = 0L
        try {
            part.outputStream().buffered().use { output ->
                val buffer = ByteArray(COPY_BUFFER_BYTES)
                while (true) {
                    val got = input.read(buffer)
                    if (got < 0) break
                    if (got == 0) continue
                    val free = freeSpace(root)
                    if (free - got < minFreeBytes) {
                        return ImportResult.Refused(outOfSpaceWords(copied + got, free))
                    }
                    output.write(buffer, 0, got)
                    copied += got
                    if (copied - lastReported >= step) {
                        lastReported = copied
                        onProgress(copied, total)
                    }
                }
            }
            if (copied == 0L) {
                return ImportResult.Refused(EMPTY_WORDS)
            }
            if (!part.renameTo(target)) {
                return ImportResult.Refused(COPY_FAILED_WORDS)
            }
            finished = true
            onProgress(copied, total ?: copied)
            return ImportResult.Ok(stored(target))
        } catch (io: IOException) {
            return ImportResult.Refused(COPY_FAILED_WORDS)
        } catch (failure: Throwable) {
            return ImportResult.Refused(COPY_FAILED_WORDS)
        } finally {
            if (!finished) runCatching { part.delete() }
            runCatching { input.close() }
        }
    }

    private fun stored(file: File): StoredModel {
        val info = (GgufMetadata.read(file) as? GgufMetadata.Read.Ok)?.info
        return StoredModel(
            name = file.name,
            file = file,
            bytes = file.length(),
            info = info,
        )
    }

    companion object {

        /** The extension a model must have. Case-insensitive. */
        const val EXTENSION = ".gguf"

        /** The folder's name inside the app's own external files directory. */
        const val FOLDER = "models"

        /** Keep at least this much free after an import. */
        const val MIN_FREE_BYTES: Long = 64L * 1024 * 1024

        private const val COPY_BUFFER_BYTES = 1 shl 20
        private const val PROGRESS_MIN_STEP = 8L * 1024 * 1024
        private const val PROGRESS_STEPS = 50L
        private const val MAX_NAME_LENGTH = 180

        /**
         * The safe file name for a picked document: its last path component,
         * ending in `.gguf`. Null means "refuse" - a name with a separator, a
         * control character, a Windows-reserved character, no `.gguf` ending
         * or an absurd length is not a model this screen will write.
         */
        fun modelName(raw: String): String? {
            val trimmed = raw.trim()
            if (trimmed.isEmpty()) return null
            val last = trimmed.substringAfterLast('/').substringAfterLast('\\')
            if (last.isEmpty() || last.length > MAX_NAME_LENGTH) return null
            if (last == "." || last == "..") return null
            if (!last.endsWith(EXTENSION, ignoreCase = true)) return null
            val reserved = "\\/:*?\"<>|"
            if (last.any { it.code < 32 || it in reserved }) return null
            return last
        }

        fun notEnoughWords(needed: Long, available: Long): String =
            "There is not enough free space on this phone. That model needs about " +
                "${DeviceTiers.bytesText(needed)}, and this phone has about " +
                "${DeviceTiers.bytesText(available)} free."

        private fun outOfSpaceWords(copied: Long, available: Long): String =
            "The phone ran out of free space after ${DeviceTiers.bytesText(copied)}. " +
                "It has about ${DeviceTiers.bytesText(available)} left, and Jarvis keeps a " +
                "little free on purpose. Nothing was kept."

        const val NOT_A_MODEL_WORDS =
            "That file is not a .gguf model. Pick a model file whose name ends in .gguf."

        const val NO_FOLDER_WORDS =
            "Jarvis could not make a models folder on this phone. Nothing was copied."

        const val ALREADY_HERE_WORDS =
            "A model called %s is already on this phone. Delete it first if you want to replace it."

        const val EMPTY_WORDS =
            "That file is empty, so there is nothing to run. Nothing was kept."

        const val COPY_FAILED_WORDS =
            "The model could not be copied from that file. Nothing was kept, and nothing left " +
                "this phone."
    }
}
