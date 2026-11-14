package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The RAM tier table, the thread choice and the refusal sentence - all on a
 * JVM, with no phone and no `ActivityManager`.
 *
 * The table numbers are PrivateLM's (`device_info_service.dart`, MIT); the
 * boundaries are checked on both sides of every threshold so an off-by-one in
 * a comparison cannot ship.
 */
class DeviceTiersTest {

    private fun info(
        fileBytes: Long = 890L,
        layers: Int = 24,
        context: Int = 32768,
        embedding: Int = 896,
        heads: Int = 14,
        headsKv: Int = 2,
    ) = GgufInfo(
        architecture = "qwen2",
        name = "test",
        layers = layers,
        trainedContext = context,
        embeddingLength = embedding,
        headCount = heads,
        headCountKv = headsKv,
        keyLength = null,
        valueLength = null,
        fileBytes = fileBytes,
        version = 3,
        tensorCount = 0,
        metadataCount = 0,
        fileType = 15,
        metadata = emptyMap(),
    )

    @Test
    fun theDartTierTableIsCarriedAcrossAtEveryBoundary() {
        assertEquals(DeviceTiers.Table(1024, 256, 2048, 512), DeviceTiers.tableFor(3.9))
        assertEquals(DeviceTiers.Table(1024, 256, 2048, 512), DeviceTiers.tableFor(4.0))
        assertEquals(DeviceTiers.Table(2048, 512, 4096, 1024), DeviceTiers.tableFor(4.1))
        assertEquals(DeviceTiers.Table(2048, 512, 4096, 1024), DeviceTiers.tableFor(6.0))
        assertEquals(DeviceTiers.Table(4096, 1024, 8192, 2048), DeviceTiers.tableFor(6.1))
        assertEquals(DeviceTiers.Table(4096, 1024, 8192, 2048), DeviceTiers.tableFor(8.0))
        assertEquals(DeviceTiers.Table(4096, 2048, 8192, 4096), DeviceTiers.tableFor(8.1))
        assertEquals(DeviceTiers.Table(4096, 2048, 8192, 4096), DeviceTiers.tableFor(12.0))
        assertEquals(DeviceTiers.Table(8192, 4096, 16384, 4096), DeviceTiers.tableFor(12.1))
        assertEquals(DeviceTiers.Table(8192, 4096, 16384, 4096), DeviceTiers.tableFor(16.0))
    }

    @Test
    fun theTierNamesAreTheDartServicesOwn() {
        assertEquals(DeviceTiers.Bucket.LOW, DeviceTiers.bucketFor(4.0))
        assertEquals(DeviceTiers.Bucket.MID, DeviceTiers.bucketFor(5.0))
        assertEquals(DeviceTiers.Bucket.HIGH, DeviceTiers.bucketFor(7.0))
        assertEquals(DeviceTiers.Bucket.ULTRA, DeviceTiers.bucketFor(10.0))
        assertEquals(DeviceTiers.Bucket.ULTRA, DeviceTiers.bucketFor(24.0))
    }

    @Test
    fun threadsLeaveOneCoreForThePhoneAndCapAtFour() {
        assertEquals(1, DeviceTiers.safeThreads(0))
        assertEquals(1, DeviceTiers.safeThreads(1))
        assertEquals(1, DeviceTiers.safeThreads(2))
        assertEquals(2, DeviceTiers.safeThreads(3))
        assertEquals(3, DeviceTiers.safeThreads(4))
        assertEquals(4, DeviceTiers.safeThreads(8))
        assertEquals(4, DeviceTiers.safeThreads(16))
    }

    @Test
    fun aTwelveGigabytePhoneGetsTheDartUltraNumbersAndARealBudget() {
        val tier = DeviceTiers.of(
            totalRamBytes = 12L * DeviceTiers.GIB,
            memoryClassMb = 512,
            cores = 8,
        )
        assertEquals(12.0, tier.totalRamGb, 0.0001)
        assertEquals(DeviceTiers.Bucket.ULTRA, tier.bucket)
        assertEquals(4096, tier.contextTokens)
        assertEquals(2048, tier.maxTokens)
        assertEquals(8192, tier.maxContextTokens)
        assertEquals(4096, tier.maxSafeTokens)
        assertEquals(4, tier.safeThreads)
        assertEquals(512, tier.heapClassMb)
        assertEquals((12L * DeviceTiers.GIB * 45L) / 100L, tier.budgetBytes)
        assertTrue(tier.maxModelBytes < tier.budgetBytes)
        assertTrue(tier.summary.contains("12.0 GB"))
    }

    @Test
    fun anUnknownRamPhoneIsTreatedAsSmallRatherThanUnlimited() {
        val tier = DeviceTiers.of(totalRamBytes = 0L, memoryClassMb = 0, cores = 8)
        assertFalse(tier.ramKnown)
        assertEquals(DeviceTiers.UNKNOWN_RAM_BUDGET_BYTES, tier.budgetBytes)
        assertEquals(DeviceTiers.tableFor(0.0), DeviceTiers.tableFor(tier.totalRamGb))
    }

    @Test
    fun aSmallModelFitsAtTheRecommendedContext() {
        val tier = DeviceTiers.of(12L * DeviceTiers.GIB, 512, 8)
        val verdict = tier.verdict(info())
        assertTrue(verdict is DeviceTiers.ModelVerdict.Fits)
        verdict as DeviceTiers.ModelVerdict.Fits
        assertTrue(verdict.fits)
        assertEquals(4096, verdict.contextTokens)
        assertFalse(verdict.shortened)
        assertTrue(verdict.words.startsWith("Fits on this phone"))
        assertTrue(verdict.words.contains("4,096 tokens"))
    }

    @Test
    fun aModelThatCannotFitAtAllIsRefusedInPlainWords() {
        val tier = DeviceTiers.of(12L * DeviceTiers.GIB, 512, 8)
        val huge = info(
            fileBytes = 8L * 1024 * 1024 * 1024,
            layers = 80,
            embedding = 8192,
            heads = 64,
            headsKv = 8,
        )
        val verdict = tier.verdict(huge)
        assertTrue(verdict is DeviceTiers.ModelVerdict.TooBig)
        assertFalse(verdict.fits)
        assertTrue(verdict.words.startsWith("Too big for this phone"))
        assertTrue("the refusal must say what would work", verdict.words.contains("would fit"))
    }

    @Test
    fun aTinyBudgetRefusesAnOrdinaryModelRatherThanPretending() {
        // A 1 GB phone gets a 1 GB floor, and a 1.5B Q4 model at 1024 ctx
        // needs more than that with the overhead the Dart constants add.
        val tier = DeviceTiers.of(DeviceTiers.GIB, 128, 4)
        val verdict = tier.verdict(info(fileBytes = 1_100_000_000L, layers = 28, embedding = 1536, heads = 12, headsKv = 2))
        assertFalse(verdict.fits)
        assertTrue(verdict is DeviceTiers.ModelVerdict.TooBig)
    }

    @Test
    fun aShorterContextIsOfferedBeforeARefusal() {
        val tier = DeviceTiers.of(8L * DeviceTiers.GIB, 512, 8)
        val model = info(fileBytes = 2_700_000_000L, layers = 36, embedding = 2560, heads = 20, headsKv = 4)
        val verdict = tier.verdict(model)
        assertTrue(verdict is DeviceTiers.ModelVerdict.Fits)
        verdict as DeviceTiers.ModelVerdict.Fits
        assertTrue(verdict.shortened)
        assertTrue(verdict.contextTokens < tier.contextTokens)
        assertTrue(verdict.words.contains("shorter memory"))
    }

    @Test
    fun anUnreadableHeaderIsSaidOutLoudRatherThanGuessed() {
        val tier = DeviceTiers.of(12L * DeviceTiers.GIB, 512, 8)
        val verdict = tier.verdict(null)
        assertTrue(verdict is DeviceTiers.ModelVerdict.Unknown)
        assertFalse(verdict.fits)
        assertTrue(verdict.words.contains("could not read"))
    }

    @Test
    fun bytesAreShownTheWayAPersonReadsThem() {
        // Android's RAM is read in GiB, so the label is GiB too: 5.4 GB of
        // bytes is 5.0 GiB, and pretending otherwise would misstate a budget.
        assertEquals("5.0 GB", DeviceTiers.bytesText(5_400_000_000L))
        assertEquals("1.0 GB", DeviceTiers.bytesText(DeviceTiers.GIB))
        assertEquals("1.5 GB", DeviceTiers.bytesText(1536L * 1024 * 1024))
        assertEquals("812 MB", DeviceTiers.bytesText(812L * 1024 * 1024))
        assertEquals("12 bytes", DeviceTiers.bytesText(12L))
    }
}
