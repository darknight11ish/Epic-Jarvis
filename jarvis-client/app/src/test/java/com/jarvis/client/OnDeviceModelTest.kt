package com.jarvis.client

import com.jarvis.client.ai.MobileLlamaEngine
import com.jarvis.client.data.LocalModel
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MobileLaneClient
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.FileOutputStream

class OnDeviceModelTest {

    @Test
    fun promptFormatUsesChatMLConventions() {
        val prompt = "Tell me a joke"
        val formatted = MobileLlamaEngine.formatChatPrompt(prompt)
        assertTrue("Must include system start tag", formatted.contains("<|im_start|>system"))
        assertTrue("Must include system role definition", formatted.contains("You are Jarvis"))
        assertTrue("Must include user turn", formatted.contains("<|im_start|>user\n$prompt<|im_end|>"))
        assertTrue("Must end ready for assistant reply", formatted.endsWith("<|im_start|>assistant\n"))
    }

    @Test
    fun localModelSerializesAndDeserializes() {
        val model = LocalModel(
            name = "qwen2.5-1.5b",
            filePath = "/data/user/0/com.jarvis.client/files/models/qwen2.5-1.5b.gguf",
            sizeBytes = 1084227584L,
            isVulkanCapable = true,
            quantization = "Q4_K_M",
            parameterCount = "1.5B"
        )
        val json = model.toJson()
        val parsed = LocalModel.fromJson(json)
        assertNotNull(parsed)
        assertEquals(model.name, parsed?.name)
        assertEquals(model.filePath, parsed?.filePath)
        assertEquals(model.sizeBytes, parsed?.sizeBytes)
        assertEquals(model.isVulkanCapable, parsed?.isVulkanCapable)
        assertEquals(model.quantization, parsed?.quantization)
        assertEquals(model.parameterCount, parsed?.parameterCount)
    }

    @Test
    fun transferModelParsesDesktopResponse() {
        val raw = """
            {
                "id": "qwen2.5-1.5b-instruct-q4",
                "name": "Qwen 2.5 1.5B Instruct",
                "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "size_bytes": 1084227584,
                "size_human": "1.08 GB",
                "recommended": true,
                "description": "Recommended for Pixel 9"
            }
        """.trimIndent()
        val obj = JarvisJson.parseToJsonElement(raw).jsonObject
        val parsed = MobileLaneClient.TransferModel.fromJson(obj)
        assertNotNull(parsed)
        assertEquals("qwen2.5-1.5b-instruct-q4", parsed?.id)
        assertEquals("Qwen 2.5 1.5B Instruct", parsed?.name)
        assertEquals("qwen2.5-1.5b-instruct-q4_k_m.gguf", parsed?.filename)
        assertEquals(1084227584L, parsed?.sizeBytes)
        assertTrue(parsed?.recommended == true)
    }

    @Test
    fun ggufValidationDetectsMagicHeader() {
        val tempValid = File.createTempFile("test_valid", ".gguf")
        val tempInvalid = File.createTempFile("test_invalid", ".gguf")
        try {
            FileOutputStream(tempValid).use { fos ->
                fos.write(byteArrayOf('G'.code.toByte(), 'G'.code.toByte(), 'U'.code.toByte(), 'F'.code.toByte(), 0x01, 0x00))
            }
            FileOutputStream(tempInvalid).use { fos ->
                fos.write(byteArrayOf('B'.code.toByte(), 'A'.code.toByte(), 'D'.code.toByte(), '!'.code.toByte()))
            }

            fun checkGguf(file: File): Boolean {
                if (!file.exists() || file.length() < 4) return false
                val header = ByteArray(4)
                file.inputStream().use { it.read(header) }
                return header[0] == 'G'.code.toByte() &&
                    header[1] == 'G'.code.toByte() &&
                    header[2] == 'U'.code.toByte() &&
                    header[3] == 'F'.code.toByte()
            }

            assertTrue("Valid header should be accepted", checkGguf(tempValid))
            assertFalse("Invalid header should be rejected", checkGguf(tempInvalid))
        } finally {
            tempValid.delete()
            tempInvalid.delete()
        }
    }

    @Test
    fun engineConfigurationCarriesConfigValues() {
        val config = MobileLlamaEngine.Config(
            modelPath = "/path/to/model.gguf",
            modelName = "test-model",
            contextSize = 4096,
            threads = 6,
            useVulkan = true,
            temperature = 0.7f
        )
        assertEquals("/path/to/model.gguf", config.modelPath)
        assertEquals("test-model", config.modelName)
        assertEquals(4096, config.contextSize)
        assertEquals(6, config.threads)
        assertTrue(config.useVulkan)
        assertEquals(0.7f, config.temperature, 0.001f)
    }

    @Test
    fun engineStatusEnumsAreDistinct() {
        val unloaded = MobileLlamaEngine.Status.UNLOADED
        val loading = MobileLlamaEngine.Status.LOADING
        val ready = MobileLlamaEngine.Status.READY
        val generating = MobileLlamaEngine.Status.GENERATING
        val error = MobileLlamaEngine.Status.ERROR
        assertEquals("UNLOADED", unloaded.name)
        assertEquals("LOADING", loading.name)
        assertEquals("READY", ready.name)
        assertEquals("GENERATING", generating.name)
        assertEquals("ERROR", error.name)
    }
}
