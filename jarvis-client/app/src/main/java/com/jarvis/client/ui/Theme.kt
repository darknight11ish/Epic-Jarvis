package com.jarvis.client.ui

import androidx.compose.ui.graphics.Color

/**
 * Pulled out of MainActivity so the approval cards and the face host share
 * exactly these values rather than each declaring their own near-miss.
 *
 * These are the spec's own palette entries, not eyeballed approximations:
 * neutral-1, ice-4, neutral-4, verdant-4, amber-4, rose-4.
 */
object T {
    val Void = Color(0xFF05070B)
    val Plate = Color(0xFF0A1119)
    val Line = Color(0xFF17293A)
    val Ink = Color(0xFFDBE7F2)
    val Dim = Color(0xFF8FA3B8)
    val Pick = Color(0xFF6FE3FF)
    val Ok = Color(0xFF5FE0A8)
    val Warn = Color(0xFFFFB648)
    val Bad = Color(0xFFFF7B86)
}
