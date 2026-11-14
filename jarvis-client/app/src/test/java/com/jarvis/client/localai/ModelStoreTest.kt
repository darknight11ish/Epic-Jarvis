package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.io.InputStream

/**
 * The models folder: import, list, delete, and every refusal - all in a
 * temporary directory, with free space supplied by the test.
 *
 * There is no Android here: the same [ModelStore] the app builds from a
 * `Context` is built here from a folder, which is the point of keeping the
 * Android factory in `ModelStoreAndroid`.
 */
class ModelStoreTest {

    @get:Rule
    val temporary = TemporaryFolder()

    private fun bytes(name: String = "qwen2-valid.gguf"): ByteArray =
        javaClass.getResourceAsStream("/gguf/$name")?.readBytes()
            ?: error("missing fixture /gguf/$name")

    private fun store(
        free: Long = 10L * 1024 * 1024 * 1024,
        minFree: Long = 0L,
    ): ModelStore {
        val root = File(temporary.root, "models")
        return ModelStore(root, freeSpace = { free }, minFreeBytes = minFree)
    }

    @Test
    fun anImportLandsAsOneCompleteFileWithItsHeaderRead() {
        val store = store()
        val progress = mutableListOf<Pair<Long, Long?>>()
        val payload = bytes()
        val result = store.import("qwen2.gguf", payload.size.toLong(), ByteArrayInputStream(payload)) { copied, total ->
            progress += copied to total
        }
        assertTrue(result is ModelStore.ImportResult.Ok)
        val model = (result as ModelStore.ImportResult.Ok).model
        assertEquals("qwen2.gguf", model.name)
        assertEquals(payload.size.toLong(), model.bytes)
        assertEquals("qwen2", model.info?.architecture)
        assertEquals("Q4_K_M", model.quant)
        assertFalse(model.quantFromName)
        assertEquals(payload.size.toLong(), progress.last().first)
        assertEquals(payload.size.toLong(), progress.last().second)
        assertFalse("no partial file may survive", File(store.folder, "qwen2.gguf.part").exists())
    }

    @Test
    fun theListReadsSizesAndHeadersAndIgnoresEverythingElse() {
        val store = store()
        store.import("a.gguf", null, ByteArrayInputStream(bytes()))
        store.import("b.gguf", null, ByteArrayInputStream(bytes()))
        File(store.folder, "notes.txt").writeText("not a model")
        File(store.folder, "c.gguf.part").writeText("half a model")
        val listed = store.list()
        assertEquals(listOf("a.gguf", "b.gguf"), listed.map { it.name })
        assertTrue(listed.all { it.bytes > 0L })
        assertNotNull(listed.first().info)
    }

    @Test
    fun aFileThatIsNotGgufIsStillListedButWithoutAHeader() {
        val store = store()
        store.import("broken.gguf", null, ByteArrayInputStream("not a model".toByteArray()))
        val model = store.list().single()
        assertNull(model.info)
        assertEquals("broken.gguf", model.name)
    }

    @Test
    fun aNameThatIsNotAGgufIsRefusedBeforeAnythingIsWritten() {
        val store = store()
        val result = store.import("holiday.jpg", null, ByteArrayInputStream(bytes()))
        assertEquals(ModelStore.NOT_A_MODEL_WORDS, (result as ModelStore.ImportResult.Refused).reason)
        assertFalse(File(store.folder, "holiday.jpg").exists())
    }

    @Test
    fun anExistingModelIsNeverSilentlyReplaced() {
        val store = store()
        store.import("same.gguf", null, ByteArrayInputStream(bytes()))
        val before = File(store.folder, "same.gguf").readBytes()
        val second = store.import("same.gguf", null, ByteArrayInputStream(bytes("too-big.gguf")))
        assertTrue(second is ModelStore.ImportResult.Refused)
        assertTrue((second as ModelStore.ImportResult.Refused).reason.contains("already on this phone"))
        assertTrue(before.contentEquals(File(store.folder, "same.gguf").readBytes()))
    }

    @Test
    fun aDeclaredSizeBiggerThanTheFreeSpaceIsRefusedUpFront() {
        val store = store(free = 1_000L, minFree = 64L)
        val result = store.import("big.gguf", 2_000L, ByteArrayInputStream(ByteArray(2_000)))
        assertTrue(result is ModelStore.ImportResult.Refused)
        assertTrue((result as ModelStore.ImportResult.Refused).reason.contains("not enough free space"))
    }

    @Test
    fun runningOutOfSpaceDuringTheCopyLeavesNothingBehind() {
        val store = store(free = 100L, minFree = 64L)
        val result = store.import("grow.gguf", null, ByteArrayInputStream(ByteArray(200)))
        assertTrue(result is ModelStore.ImportResult.Refused)
        assertTrue((result as ModelStore.ImportResult.Refused).reason.contains("ran out of free space"))
        assertEquals(emptyList<String>(), store.folder.list()?.toList().orEmpty())
    }

    @Test
    fun anEmptyPickIsRefused() {
        val store = store()
        val result = store.import("empty.gguf", 0L, ByteArrayInputStream(ByteArray(0)))
        assertEquals(ModelStore.EMPTY_WORDS, (result as ModelStore.ImportResult.Refused).reason)
        assertFalse(File(store.folder, "empty.gguf").exists())
    }

    @Test
    fun aStreamThatFailsMidCopyLeavesNoPartialModel() {
        val store = store()
        val failing = object : InputStream() {
            private var served = 0
            override fun read(): Int = throw IOException("boom")
            override fun read(b: ByteArray, off: Int, len: Int): Int {
                if (served >= 3) throw IOException("boom")
                served++
                b[off] = 1
                return 1
            }
        }
        val result = store.import("dies.gguf", null, failing)
        assertEquals(ModelStore.COPY_FAILED_WORDS, (result as ModelStore.ImportResult.Refused).reason)
        assertFalse(File(store.folder, "dies.gguf").exists())
        assertFalse(File(store.folder, "dies.gguf.part").exists())
    }

    @Test
    fun deleteRemovesOnlyTheNamedModel() {
        val store = store()
        store.import("keep.gguf", null, ByteArrayInputStream(bytes()))
        store.import("drop.gguf", null, ByteArrayInputStream(bytes()))
        assertTrue(store.delete("drop.gguf"))
        assertFalse(File(store.folder, "drop.gguf").exists())
        assertTrue(File(store.folder, "keep.gguf").exists())
        assertFalse(store.delete("drop.gguf"))
    }

    @Test
    fun aPathIsReducedToItsLastComponentAndTraversalCannotDeleteOutside() {
        assertEquals("evil.gguf", ModelStore.modelName("../../evil.gguf"))
        assertEquals("model.gguf", ModelStore.modelName("C:\\Models\\model.gguf"))
        assertEquals("model.GGUF", ModelStore.modelName("model.GGUF"))
        assertNull(ModelStore.modelName("model.txt"))
        assertNull(ModelStore.modelName(".."))
        assertNull(ModelStore.modelName("   "))
        assertFalse("delete must never leave the folder", store().delete("../evil.gguf"))
    }

    @Test
    fun findReturnsTheSameModelTheListDoes() {
        val store = store()
        store.import("one.gguf", null, ByteArrayInputStream(bytes()))
        val found = store.find("one.gguf")
        assertNotNull(found)
        assertEquals(store.list().single().file.absolutePath, found!!.file.absolutePath)
        assertNull(store.find("two.gguf"))
    }

    @Test
    fun aNameFoundInTheFileIsMarkedAsComingFromTheName() {
        val store = store()
        store.import("qwen2.5-3b-instruct-q4_k_m.gguf", null, ByteArrayInputStream("not really a model".toByteArray()))
        val model = store.list().single()
        assertEquals("Q4_K_M", model.quant)
        assertTrue(model.quantFromName)
    }
}
