package com.jarvis.client

import com.jarvis.client.net.MemoryDates
import java.time.LocalDate
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * "What did Jarvis know on this date?" - the moment a typed date means.
 *
 * These numbers are also read by backend/test_memory_honesty.py, which runs
 * the desktop's own `asOfSeconds` (brain.js) on the same dates in the same
 * time zones and checks it gives the same numbers. So keep the calls in this
 * exact shape - `assertEquals(<n>L, MemoryDates.knownAt("<date>",
 * ZoneId.of("<zone>"), LocalDate.of(y, m, d)))` and `assertNull(...)` - or
 * that cross-check stops finding them (it fails, rather than passing
 * quietly, if it finds too few).
 */
class MemoryDatesTest {

    @Test
    fun `a date means the last second of that day, where the phone is`() {
        // 23:59:59 on 1 June in London (summer time, UTC+1) and Los Angeles (UTC-7).
        assertEquals(1780354799L, MemoryDates.knownAt("2026-06-01", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        assertEquals(1780383599L, MemoryDates.knownAt("2026-06-01", ZoneId.of("America/Los_Angeles"), LocalDate.of(2026, 9, 23)))
        // The clocks went forward in London that morning; the end of the day is still 23:59:59.
        assertEquals(1774825199L, MemoryDates.knownAt("2026-03-29", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        assertEquals(1709269199L, MemoryDates.knownAt("2024-02-29", ZoneId.of("America/New_York"), LocalDate.of(2026, 9, 23)))
        assertEquals(1009897199L, MemoryDates.knownAt("2002-01-01", ZoneId.of("Asia/Tokyo"), LocalDate.of(2026, 9, 23)))
    }

    @Test
    fun `today can be asked about`() {
        assertEquals(1790204399L, MemoryDates.knownAt("2026-09-23", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        // Spaces around what was typed do not matter.
        assertEquals(1790204399L, MemoryDates.knownAt(" 2026-09-23 ", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
    }

    @Test
    fun `a date that cannot be asked is refused, not sent`() {
        // Tomorrow.
        assertNull(MemoryDates.knownAt("2026-09-24", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        // Not a real date - it is not rolled into March.
        assertNull(MemoryDates.knownAt("2026-02-31", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        // Before any Jarvis; the server would answer with today's facts.
        assertNull(MemoryDates.knownAt("1999-12-31", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        // Not the YYYY-MM-DD shape.
        assertNull(MemoryDates.knownAt("1/6/2026", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
        assertNull(MemoryDates.knownAt("", ZoneId.of("Europe/London"), LocalDate.of(2026, 9, 23)))
    }
}
