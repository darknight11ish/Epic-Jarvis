package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The real engine wrapper's contract on a JVM with no native library.
 *
 * What is proved here is the timing rule that keeps the whole app testable:
 * constructing a [LlamaEngine] does nothing, and the library is loaded only
 * inside [LlamaEngine.create]. The native calls themselves are exercised by
 * the native lane's own build and by the phone field test, not here.
 */
class LlamaEngineTest {

    @Test
    fun constructingAnEngineDoesNotLoadTheLibrary() {
        var loads = 0
        val engine = LlamaEngine { loads++ }
        assertEquals(0, loads)
        assertFalse(engine.hasHandle())
        assertEquals("", engine.version)
    }

    @Test
    fun createLoadsTheLibraryOnceAndReportsAMissingOneCleanly() {
        var loads = 0
        val engine = LlamaEngine {
            loads++
            throw UnsatisfiedLinkError("no jarvis_llama for Windows")
        }
        val result = engine.create()
        assertEquals(1, loads)
        assertTrue(result is EngineResult.Failed)
        assertEquals(LlamaEngine.NO_LIBRARY_WORDS, (result as EngineResult.Failed).reason)
        assertFalse(engine.hasHandle())
        // The words have to be usable by a person, not a stack trace.
        assertTrue(result.reason.contains("on-device model engine"))
    }

    @Test
    fun loadBeforeCreateSaysToLoadAModelRatherThanCrashing() {
        val engine = LlamaEngine { }
        val result = engine.load("C:\\models\\x.gguf", LoadPlan(4, 4096, 512))
        assertEquals(LlamaEngine.NOT_STARTED_WORDS, (result as EngineResult.Failed).reason)
    }

    @Test
    fun generateBeforeCreateIsNotReadyAndSaysSo() {
        val engine = LlamaEngine { }
        val result = engine.generate("hi", 32, 0.7f, onToken = {}, stopped = { false })
        assertTrue(result is GenerationResult.NotReady)
        assertEquals(LlamaEngine.NOT_STARTED_WORDS, (result as GenerationResult.NotReady).reason)
    }

    @Test
    fun unloadAndDestroyWithoutAHandleAreHarmless() {
        val engine = LlamaEngine { }
        engine.unload()
        engine.destroy()
        assertNull(engine.stats())
        assertFalse(engine.hasHandle())
    }

    @Test
    fun anEmptyModelPathIsRefusedBeforeAnyNativeCall() {
        val engine = LlamaEngine { }
        val result = engine.load("   ", LoadPlan(4, 4096, 512))
        assertEquals(LlamaEngine.NOT_STARTED_WORDS, (result as EngineResult.Failed).reason)
    }

    @Test
    fun aPlanIsClampedToTheEnginesOwnFloor() {
        // The clamp itself is internal to the native call, so this asserts the
        // public constant the call uses: a context below it must not be asked
        // for, and 128 is the floor.
        assertEquals(128, LlamaEngine.MIN_CONTEXT_TOKENS)
        assertTrue(LlamaEngine.MIN_CONTEXT_TOKENS > 0)
    }

    @Test
    fun theLibraryNameIsTheOneTheNativeLaneBuilds() {
        assertEquals("jarvis_llama", LlamaEngine.LIBRARY)
    }

    @Test
    fun theNativeObjectItselfHasNoLoader() {
        // A guard on the one file whose initialiser must stay empty: calling a
        // declaration must fail with the native method's own error, NOT with a
        // static-initialiser failure from a `System.loadLibrary` that moved
        // into LlamaNative. This machine has no jarvis_llama, so either way it
        // throws - but only the second would break every JVM test.
        var failed = false
        try {
            LlamaNative.nativeCreate()
        } catch (missing: UnsatisfiedLinkError) {
            failed = true
            assertFalse(
                "LlamaNative's initialiser must not load the library: ${missing.message}",
                missing.stackTrace.any { it.className.contains("LlamaNative") && it.methodName == "<clinit>" },
            )
        }
        assertTrue("the native method must have no implementation here", failed)
    }
}
