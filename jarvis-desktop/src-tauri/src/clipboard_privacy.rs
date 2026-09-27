//! "Private copy" (feasibility I114, docs/FEASIBILITY-AUDIT-2026-09-26.md:
//! "Windows clipboard sync can carry a copied answer off the PC." / "Needs a
//! small Rust command."): the Jarvis bar's Copy button keeps what it copies
//! OUT of Windows Clipboard History (Win+V) and Cloud Clipboard (sync to the
//! owner's other signed-in devices).
//!
//! ## Why this needs its own command, not `tauri_plugin_clipboard_manager`
//!
//! `write_clipboard` (`commands.rs`) already copies text with
//! `tauri_plugin_clipboard_manager`'s `write_text` (the `arboard` crate
//! underneath it). That call opens the clipboard, sets `CF_UNICODETEXT`, and
//! closes it again, all in one step, with no hook to add anything else to
//! that same clipboard sequence. Windows' own opt-out for History and Cloud
//! Clipboard has to be set in the SAME open/close sequence as the text
//! itself — Microsoft's own documented mechanism (two registered clipboard
//! formats, each carrying a `DWORD` value of 0):
//!
//!   * `CanIncludeInClipboardHistory` — 0 keeps this clip out of Win+V's
//!     history.
//!   * `CanUploadToCloudClipboard` — 0 keeps it from syncing to the owner's
//!     other Microsoft-account-linked Windows PCs.
//!
//! Setting these on an ALREADY-CLOSED clipboard does nothing: the format has
//! to be present when Windows itself walks the clip's formats to decide
//! whether to keep or sync it, which happens at `CloseClipboard`. So this
//! module talks to Win32 directly, one clipboard sequence, in the same
//! `#[cfg(windows)]` / `#[cfg(not(windows))]` shape as `token_store.rs`.
//!
//! ## What this changes, and does not
//!
//! Only the ONE clip this command writes. The clipboard's ordinary text
//! (`CF_UNICODETEXT`) is unchanged — any other app can still read and paste
//! it normally, on THIS PC, right now. What is turned off is Windows
//! remembering it for later (History) or copying it to another of the
//! owner's own devices (Cloud Clipboard) — exactly the two ways an
//! answer that never left this PC over Jarvis's own network could still
//! leave it through Windows' own clipboard features.
//!
//! `read_clipboard` (`commands.rs`) is untouched: reading back what is
//! already on the clipboard has nothing to do with what gets remembered or
//! synced going forward.

/// Writes `text` to the clipboard, excluded from Windows Clipboard History
/// and Cloud Clipboard sync. On anything but Windows, or if the ordinary
/// clipboard write itself fails, returns an error naming why.
///
/// The two privacy formats are best-effort: if OpenClipboard, EmptyClipboard
/// or the CF_UNICODETEXT write fails, this returns Err and copies nothing
/// (the same failure the plain `write_clipboard` command would report) - but
/// once the ordinary text is on the clipboard, a failure to register or set
/// EITHER privacy format still returns Err, naming which, rather than
/// silently leaving a copy that looks private but is not: the owner's own
/// answer, the whole point of this command, must not end up in History or
/// Cloud Clipboard with no warning that it did.
pub fn write_private(text: &str) -> Result<(), String> {
    imp::write_private(text)
}

#[cfg(windows)]
mod imp {
    use std::ptr;
    use windows_sys::Win32::Foundation::{GetLastError, GlobalFree, HGLOBAL};
    use windows_sys::Win32::System::DataExchange::{
        CloseClipboard, EmptyClipboard, OpenClipboard, RegisterClipboardFormatW, SetClipboardData,
    };
    use windows_sys::Win32::System::Memory::{
        GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE,
    };

    /// `CF_UNICODETEXT` (`winuser.h`) - `13`, a Win32 constant that has been
    /// stable since Windows NT and is never renumbered. Defined here rather
    /// than pulling in `windows-sys`'s `Win32_System_Ole` feature (where it
    /// actually lives) for one integer this module has no other use for
    /// that whole OLE surface for.
    const CF_UNICODETEXT: u32 = 13;

    /// How many times to retry `OpenClipboard` when another app (very
    /// commonly a clipboard manager, running right beside Windows' own
    /// History feature this command is working around) holds it for a
    /// moment. 10 tries, 15ms apart — under 200ms total, and Microsoft's own
    /// sample code for clipboard writers uses the same short-retry shape for
    /// the same reason.
    const OPEN_RETRIES: u32 = 10;
    const OPEN_RETRY_DELAY_MS: u64 = 15;

    fn wide_nul(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// One global-memory block holding `bytes`, moveable (the shape
    /// `SetClipboardData` requires — Windows takes ownership of the handle
    /// on success and frees it itself; on any earlier failure the caller
    /// must free it, which every call site below does).
    ///
    /// # Safety
    /// `bytes` must not be empty. The returned handle is either null (on
    /// allocation failure) or a valid `GlobalAlloc` handle the caller either
    /// hands to `SetClipboardData` or frees with `GlobalFree`.
    unsafe fn global_copy(bytes: &[u8]) -> HGLOBAL {
        let h = GlobalAlloc(GMEM_MOVEABLE, bytes.len());
        if h.is_null() {
            return ptr::null_mut();
        }
        let dst = GlobalLock(h);
        if dst.is_null() {
            GlobalFree(h);
            return ptr::null_mut();
        }
        ptr::copy_nonoverlapping(bytes.as_ptr(), dst as *mut u8, bytes.len());
        GlobalUnlock(h);
        h
    }

    /// Sets one clipboard format to a `DWORD` value of `0`, the documented
    /// opt-out shape for `CanIncludeInClipboardHistory`/
    /// `CanUploadToCloudClipboard`. The clipboard must already be open.
    /// Returns the format's plain-word name on failure, for the caller to
    /// report which of the two (if either) did not take.
    fn set_privacy_format(name: &str, label: &str) -> Result<(), String> {
        let wname = wide_nul(name);
        // SAFETY: `wname` is a NUL-terminated UTF-16 buffer for the
        // duration of this call.
        let fmt = unsafe { RegisterClipboardFormatW(wname.as_ptr()) };
        if fmt == 0 {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            return Err(format!(
                "could not register the {label} clipboard format (Windows error {code})"
            ));
        }
        let zero: u32 = 0;
        // SAFETY: `zero`'s 4 bytes are a valid, fully-initialised DWORD to
        // copy into the global block.
        let h = unsafe { global_copy(&zero.to_ne_bytes()) };
        if h.is_null() {
            return Err(format!(
                "could not allocate memory for the {label} clipboard format"
            ));
        }
        // SAFETY: `h` is a valid, unlocked global-memory handle from
        // `global_copy` above; the clipboard is open (the caller's
        // precondition). On success Windows owns `h` from here; on failure
        // it is freed below so nothing leaks.
        let ok = unsafe { SetClipboardData(fmt, h) };
        if ok.is_null() {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            unsafe { GlobalFree(h) };
            return Err(format!(
                "could not set the {label} clipboard format (Windows error {code})"
            ));
        }
        Ok(())
    }

    pub fn write_private(text: &str) -> Result<(), String> {
        let wtext = wide_nul(text);
        let text_bytes =
            unsafe { std::slice::from_raw_parts(wtext.as_ptr() as *const u8, wtext.len() * 2) };

        let mut opened = false;
        for attempt in 0..OPEN_RETRIES {
            // SAFETY: a null owner window is a documented, valid argument -
            // the clip is not tied to any window closing.
            if unsafe { OpenClipboard(ptr::null_mut()) } != 0 {
                opened = true;
                break;
            }
            if attempt + 1 < OPEN_RETRIES {
                std::thread::sleep(std::time::Duration::from_millis(OPEN_RETRY_DELAY_MS));
            }
        }
        if !opened {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            return Err(format!(
                "could not open the clipboard (Windows error {code}) - another program may be \
                 holding it"
            ));
        }

        // From here on, every path below MUST reach CloseClipboard exactly
        // once - done via this small guard rather than duplicating the call
        // on every early return.
        struct Closer;
        impl Drop for Closer {
            fn drop(&mut self) {
                // SAFETY: the clipboard is open for the life of this guard.
                unsafe {
                    CloseClipboard();
                }
            }
        }
        let _closer = Closer;

        // SAFETY: the clipboard is open (just confirmed above).
        if unsafe { EmptyClipboard() } == 0 {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            return Err(format!(
                "could not clear the clipboard (Windows error {code})"
            ));
        }

        // SAFETY: text_bytes is a valid, non-empty byte view of wtext for
        // the duration of this call (wtext outlives it).
        let h_text = unsafe { global_copy(text_bytes) };
        if h_text.is_null() {
            return Err("could not allocate memory for the clipboard text".to_string());
        }
        // SAFETY: h_text is a valid, unlocked global-memory handle; the
        // clipboard is open. Windows owns it from here on success.
        let ok = unsafe { SetClipboardData(CF_UNICODETEXT, h_text) };
        if ok.is_null() {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            unsafe { GlobalFree(h_text) };
            return Err(format!(
                "could not set the clipboard text (Windows error {code})"
            ));
        }

        // The text is on the clipboard now (readable by any app on this
        // PC). Everything from here decides whether Windows also remembers
        // or syncs it - see set_privacy_format's own doc comment for why a
        // failure here still returns Err rather than reporting success.
        set_privacy_format("CanIncludeInClipboardHistory", "Clipboard History")?;
        set_privacy_format("CanUploadToCloudClipboard", "Cloud Clipboard")?;
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn wide_nul_ends_in_one_nul_and_encodes_the_text_before_it() {
            let w = wide_nul("Hi");
            assert_eq!(w, vec![b'H' as u16, b'i' as u16, 0]);
        }

        #[test]
        fn wide_nul_of_the_empty_string_is_just_the_terminator() {
            assert_eq!(wide_nul(""), vec![0]);
        }

        /// `CF_UNICODETEXT` is `13` in every Windows SDK header that defines
        /// it (`winuser.h`) - pinned here so a typo in the hardcoded value
        /// (see its own doc comment for why it is hardcoded at all) fails a
        /// test rather than silently copying plain text as the wrong
        /// clipboard format.
        #[test]
        fn cf_unicodetext_is_the_documented_win32_constant() {
            assert_eq!(CF_UNICODETEXT, 13);
        }
    }
}

#[cfg(not(windows))]
mod imp {
    pub fn write_private(_text: &str) -> Result<(), String> {
        Err("Private copy needs Windows".to_string())
    }
}
