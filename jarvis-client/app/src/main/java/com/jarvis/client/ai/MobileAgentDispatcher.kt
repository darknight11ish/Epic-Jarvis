package com.jarvis.client.ai

import android.content.Context
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import com.jarvis.client.data.OfflineStore
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

/**
 * Mobile Agent Tool Dispatcher (inspired by Mobile-Harness autonomous agent drivers).
 *
 * Runs bounded, safe local tools on-device during Offline Companion Mode.
 *
 * Compliance with The Five Rules:
 * - Rule 1: All operations are local to the phone and private storage.
 * - Rule 4: Risky tools (shell execution, external email, code deletion) are
 *   strictly declined offline and queued for desktop approval upon reconnection.
 */
class MobileAgentDispatcher(
    private val context: Context? = null,
    private val offlineStore: OfflineStore? = null,
) {

    data class ToolResult(
        val ok: Boolean,
        val output: String,
        val queuedForSync: Boolean = false,
        val needsDesktopApproval: Boolean = false,
    )

    /**
     * Executes a requested on-device tool by name with arguments.
     */
    fun dispatch(name: String, args: Map<String, String>): ToolResult {
        return when (name.lowercase().trim()) {
            "take_note", "note", "add_note" -> {
                val title = args["title"] ?: "Offline Note"
                val text = args["content"] ?: args["text"] ?: ""
                if (text.isBlank()) {
                    ToolResult(ok = false, output = "Note content cannot be empty.")
                } else {
                    val payload = buildJsonObject {
                        put("title", title)
                        put("text", text)
                        put("created_offline", true)
                    }.toString()
                    offlineStore?.queueTask(actionType = "note", payloadJson = payload)
                    ToolResult(
                        ok = true,
                        output = "Drafted note '$title' into offline queue. Will sync to PC on reconnect.",
                        queuedForSync = true,
                    )
                }
            }

            "remember_fact", "memory", "save_memory" -> {
                val fact = args["fact"] ?: args["text"] ?: ""
                val category = args["category"] ?: "general"
                val sensitive = args["sensitive"]?.toBooleanStrictOrNull() ?: false
                if (fact.isBlank()) {
                    ToolResult(ok = false, output = "Memory fact text cannot be empty.")
                } else {
                    offlineStore?.recordMemory(fact = fact, category = category, sensitive = sensitive)
                    ToolResult(
                        ok = true,
                        output = "Captured offline memory ($category). Will reconcile with PC brain on reconnect.",
                        queuedForSync = true,
                    )
                }
            }

            "device_status", "device_info", "battery" -> {
                val batteryStatus = getBatteryPercentage()
                val freeStorageMb = getFreeStorageMb()
                val counts = offlineStore?.getPendingCounts() ?: Triple(0, 0, 0)
                val statusText = buildString {
                    append("Battery: $batteryStatus% | ")
                    append("Free Storage: ${freeStorageMb}MB | ")
                    append("Offline Queue: ${counts.first} turns, ${counts.second} memories, ${counts.third} tasks pending sync")
                }
                ToolResult(ok = true, output = statusText)
            }

            "list_offline_queue", "sync_status" -> {
                val counts = offlineStore?.getPendingCounts() ?: Triple(0, 0, 0)
                val msg = "Offline Queue Status: ${counts.first} chats, ${counts.second} memories, ${counts.third} notes/tasks waiting to sync."
                ToolResult(ok = true, output = msg)
            }

            // Explicit Rule 4 Guard: Risky tools declined offline
            "shell_exec", "run_command", "send_email", "delete_file", "git_push" -> {
                ToolResult(
                    ok = false,
                    output = "Action '$name' is risky and cannot be run offline (Rule 4). Please reconnect to your desktop PC to approve this action.",
                    needsDesktopApproval = true,
                )
            }

            else -> {
                ToolResult(
                    ok = false,
                    output = "Unknown or unsupported on-device tool '$name'. Supported offline tools: take_note, remember_fact, device_status, list_offline_queue.",
                )
            }
        }
    }

    private fun getBatteryPercentage(): Int {
        val bm = context?.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        return bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
    }

    private fun getFreeStorageMb(): Long {
        return runCatching {
            val stat = StatFs(Environment.getDataDirectory().path)
            (stat.availableBlocksLong * stat.blockSizeLong) / (1024 * 1024)
        }.getOrDefault(0L)
    }
}
