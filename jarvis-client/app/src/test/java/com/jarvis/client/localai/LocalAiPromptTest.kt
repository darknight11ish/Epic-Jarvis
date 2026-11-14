package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The prompt formats, byte for byte where it matters: the system sentence, the
 * turns, the assistant's opening marker, the 8-turn window and the 300-character
 * cut.
 *
 * The shapes are PrivateLM's (`inference_android.dart`, MIT); a change here
 * would change what every model on every phone is asked, so the exact markers
 * are pinned.
 */
class LocalAiPromptTest {

    private val twoTurns = listOf(
        LocalAiPrompt.Turn(LocalAiPrompt.Role.USER, "What is this?"),
        LocalAiPrompt.Turn(LocalAiPrompt.Role.ASSISTANT, "A small local chat."),
    )

    @Test
    fun anUnknownModelGetsChatMl() {
        assertEquals(LocalAiPrompt.Template.CHATML, LocalAiPrompt.templateFor(null))
        assertEquals(LocalAiPrompt.Template.CHATML, LocalAiPrompt.templateFor("qwen2.5-0.5b.gguf"))
        val prompt = LocalAiPrompt.build("qwen2.5-0.5b.gguf", twoTurns, "And now?")
        assertTrue(prompt.startsWith("<|im_start|>system\n"))
        assertTrue(prompt.contains(LocalAiPrompt.SYSTEM))
        assertTrue(prompt.contains("<|im_start|>user\nWhat is this?<|im_end|>"))
        assertTrue(prompt.contains("<|im_start|>assistant\nA small local chat.<|im_end|>"))
        assertTrue(prompt.endsWith("<|im_start|>user\nAnd now?<|im_end|>\n<|im_start|>assistant\n"))
    }

    @Test
    fun aGemmaModelGetsGemmaTurns() {
        assertEquals(LocalAiPrompt.Template.GEMMA, LocalAiPrompt.templateFor("gemma-3-1b-it.gguf"))
        val prompt = LocalAiPrompt.build("gemma-3-1b-it.gguf", twoTurns, "Go on")
        assertTrue(prompt.startsWith("<start_of_turn>user\n" + LocalAiPrompt.SYSTEM))
        assertTrue(prompt.contains("<start_of_turn>model\nUnderstood.<end_of_turn>"))
        assertTrue(prompt.contains("<start_of_turn>user\nWhat is this?<end_of_turn>"))
        assertTrue(prompt.contains("<start_of_turn>model\nA small local chat.<end_of_turn>"))
        assertTrue(prompt.endsWith("<start_of_turn>user\nGo on<end_of_turn>\n<start_of_turn>model\n"))
    }

    @Test
    fun aLlamaThreeModelGetsTheHeaderTokens() {
        assertEquals(LocalAiPrompt.Template.LLAMA3, LocalAiPrompt.templateFor("Llama-3.2-1B-Instruct.gguf"))
        val prompt = LocalAiPrompt.build("Llama-3.2-1B-Instruct.gguf", twoTurns, "Go on")
        assertTrue(prompt.startsWith("<|begin_of_text|><|start_header_id|>system<|end_header_id|>"))
        assertTrue(prompt.contains("<|start_header_id|>user<|end_header_id|>\n\nWhat is this?<|eot_id|>"))
        assertTrue(prompt.contains("<|start_header_id|>assistant<|end_header_id|>\n\nA small local chat.<|eot_id|>"))
        assertTrue(prompt.endsWith("<|start_header_id|>assistant<|end_header_id|>\n\n"))
    }

    @Test
    fun onlyTheMostRecentEightTurnsAreSent() {
        val many = (1..20).map {
            LocalAiPrompt.Turn(LocalAiPrompt.Role.USER, "question-$it")
        }
        val prompt = LocalAiPrompt.build("qwen.gguf", many, "last")
        for (old in 1..12) {
            assertFalse("turn $old must be dropped", prompt.contains("question-$old<|im_end|>"))
        }
        for (kept in 13..20) {
            assertTrue("turn $kept must be kept", prompt.contains("question-$kept<|im_end|>"))
        }
    }

    @Test
    fun aLongEarlierTurnIsCutToThreeHundredCharacters() {
        val long = "x".repeat(1_000)
        val prompt = LocalAiPrompt.build(
            "qwen.gguf",
            listOf(LocalAiPrompt.Turn(LocalAiPrompt.Role.USER, long)),
            "now",
        )
        assertTrue(prompt.contains("x".repeat(LocalAiPrompt.MAX_TURN_CHARS) + "..."))
        assertFalse(prompt.contains("x".repeat(LocalAiPrompt.MAX_TURN_CHARS + 1)))
    }

    @Test
    fun aShortTurnIsNotTouched() {
        val prompt = LocalAiPrompt.build(
            "qwen.gguf",
            listOf(LocalAiPrompt.Turn(LocalAiPrompt.Role.USER, "short")),
            "now",
        )
        assertTrue(prompt.contains("short<|im_end|>"))
        assertFalse(prompt.contains("short..."))
    }

    @Test
    fun theSameMessageIsAlwaysInThePromptEvenWithNoHistory() {
        val prompt = LocalAiPrompt.build("qwen.gguf", emptyList(), "only this")
        assertTrue(prompt.contains("<|im_start|>user\nonly this<|im_end|>"))
        assertEquals(1, Regex(Regex.escape("<|im_start|>user")).findAll(prompt).count())
    }
}
