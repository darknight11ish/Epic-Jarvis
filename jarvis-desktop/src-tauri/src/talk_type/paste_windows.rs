//! Talk-to-type's paste on Windows, and the checks before it.
//!
//! The clipboard half is adapted from Handy (https://github.com/cjpais/Handy,
//! `src-tauri/src/paste_tx/windows.rs`, read 2026-09-28): the words go on the
//! clipboard as a DELAYED-RENDER promise owned by a hidden message-only
//! window, so Windows tells this app (`WM_RENDERFORMAT`) when a program
//! actually reads them; the owner's previous clipboard is snapshotted first,
//! with every format, and put back once the reads go quiet - but only while
//! the clipboard's sequence number says nobody copied anything newer; and the
//! clip carries the three markers that keep it out of Windows Clipboard
//! History, Cloud Clipboard sync and clipboard-watching programs (the same
//! markers Chromium uses for a private window's copies). What was changed:
//! Handy's `enigo` keystrokes are replaced by `SendInput` (no new library),
//! its auto-submit Enter and its "leave the words on the clipboard" option
//! are removed, the sequence is checked again AFTER opening the clipboard to
//! put the owner's copy back (a copy made between the check and the open
//! would otherwise be overwritten), and the caller waits for the outcome so
//! the owner can be told when the program in front did not take the words.
//! The checks before the paste (the keys let go, the same window in front,
//! not a password box) are this project's own - Handy has none of them.
//!
//! MIT License
//!
//! Copyright (c) 2025 CJ Pais
//!
//! Permission is hereby granted, free of charge, to any person obtaining a
//! copy of this software and associated documentation files (the
//! "Software"), to deal in the Software without restriction, including
//! without limitation the rights to use, copy, modify, merge, publish,
//! distribute, sublicense, and/or sell copies of the Software, and to permit
//! persons to whom the Software is furnished to do so, subject to the
//! following conditions:
//!
//! The above copyright notice and this permission notice shall be included
//! in all copies or substantial portions of the Software.
//!
//! THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
//! OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
//! MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
//! NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
//! DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//! OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
//! USE OR OTHER DEALINGS IN THE SOFTWARE.
//!
//! Nothing here ever logs, stores or sends the words: they live in this
//! process's memory for one paste and are dropped with the transaction.

use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex, Once};
use std::thread;
use std::time::{Duration, Instant};

use windows::core::{w, PCWSTR};
use windows::Win32::Foundation::{
    GlobalFree, SetLastError, ERROR_SUCCESS, HANDLE, HGLOBAL, HINSTANCE, HWND, LPARAM, LRESULT,
    WPARAM,
};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED,
};
use windows::Win32::System::DataExchange::{
    CloseClipboard, EmptyClipboard, EnumClipboardFormats, GetClipboardData, GetClipboardOwner,
    GetClipboardSequenceNumber, OpenClipboard, RegisterClipboardFormatW, SetClipboardData,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{
    GlobalAlloc, GlobalLock, GlobalSize, GlobalUnlock, GMEM_MOVEABLE,
};
use windows::Win32::System::Ole::{
    CF_BITMAP, CF_DSPBITMAP, CF_DSPENHMETAFILE, CF_DSPMETAFILEPICT, CF_DSPTEXT, CF_ENHMETAFILE,
    CF_METAFILEPICT, CF_OWNERDISPLAY, CF_PALETTE, CF_UNICODETEXT,
};
use windows::Win32::UI::Accessibility::{CUIAutomation, IUIAutomation};
use windows::Win32::UI::Input::KeyboardAndMouse::{
    GetAsyncKeyState, SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS,
    KEYEVENTF_KEYUP, VIRTUAL_KEY, VK_CONTROL, VK_LWIN, VK_MENU, VK_RWIN, VK_SHIFT, VK_V,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CopyImage, CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetAncestor,
    GetClassNameW, GetForegroundWindow, GetGUIThreadInfo, GetMessageW, GetWindowLongPtrW,
    GetWindowLongW, GetWindowThreadProcessId, KillTimer, PostQuitMessage, RegisterClassW, SetTimer,
    SetWindowLongPtrW, ES_PASSWORD, GA_ROOT, GDI_IMAGE_TYPE, GUITHREADINFO, GWLP_USERDATA,
    GWL_STYLE, HWND_MESSAGE, IMAGE_FLAGS, MSG, WINDOW_EX_STYLE, WINDOW_STYLE, WM_DESTROYCLIPBOARD,
    WM_RENDERALLFORMATS, WM_RENDERFORMAT, WM_TIMER, WNDCLASSW,
};

use super::paste_tx::{evaluate, Settled, TxState, WaitDecision, CHORD_HOLD, RESTORE_TIMEOUT};

const CLASS_NAME: PCWSTR = w!("JarvisTalkTypePasteWindow");
const TIMER_ID: usize = 1;
const TIMER_INTERVAL_MS: u32 = 25;
/// A clipboard format bigger than this is not snapshotted (Handy's limit).
const MAX_FORMAT_BYTES: usize = 64 * 1024 * 1024;

const IMAGE_BITMAP_TYPE: GDI_IMAGE_TYPE = GDI_IMAGE_TYPE(0);
const LR_CREATEDIBSECTION_FLAG: IMAGE_FLAGS = IMAGE_FLAGS(0x2000);

/// How long the UI Automation question ("is the focused box a password
/// box?") may take. A program that does not answer in this long is not
/// going to take a paste promptly either.
const UIA_TIMEOUT: Duration = Duration::from_millis(1500);

// ---------------------------------------------------------------------------
// The checks before a paste (this project's own)
// ---------------------------------------------------------------------------

/// The top-level window in front right now, as a number (0: none).
pub(crate) fn foreground_root() -> isize {
    // SAFETY: no preconditions; both calls take and return plain handles.
    unsafe {
        let fg = GetForegroundWindow();
        if fg.is_invalid() {
            return 0;
        }
        GetAncestor(fg, GA_ROOT).0 as isize
    }
}

fn held(vk: VIRTUAL_KEY) -> bool {
    // SAFETY: no preconditions. The high bit says the key is down now.
    (unsafe { GetAsyncKeyState(i32::from(vk.0)) } as u16 & 0x8000) != 0
}

/// Waits (up to `timeout`) until Ctrl, Alt, Shift and the Windows keys are
/// all let go, so Ctrl+V is not read as Ctrl+Alt+V or Ctrl+Shift+V. True
/// once they are.
pub(crate) fn wait_keys_up(timeout: Duration) -> bool {
    let until = Instant::now() + timeout;
    loop {
        if ![VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN]
            .into_iter()
            .any(held)
        {
            return true;
        }
        if Instant::now() >= until {
            return false;
        }
        thread::sleep(Duration::from_millis(20));
    }
}

/// Is the box that has the keyboard focus a password box? `Some(true)` when
/// either check says so, `Some(false)` when UI Automation answered no and
/// the plain Windows check found nothing, `None` when UI Automation could
/// not answer (and the plain check found nothing either).
pub(crate) fn focused_is_password() -> Option<bool> {
    if win32_password_box() {
        return Some(true);
    }
    uia_password_box()
}

/// UI Automation's own answer (`IsPassword`): how browsers, WPF, WinUI and
/// most modern programs say a box hides what is typed. Asked on a thread of
/// its own, which sets COM up itself, with a time limit.
fn uia_password_box() -> Option<bool> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        // SAFETY: COM is initialised on this new thread and balanced below;
        // every COM object is created and dropped inside `ask`, before
        // CoUninitialize.
        let answer = unsafe {
            let init = CoInitializeEx(None, COINIT_MULTITHREADED);
            let ask = || -> windows::core::Result<bool> {
                let automation: IUIAutomation =
                    CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER)?;
                let element = automation.GetFocusedElement()?;
                Ok(element.CurrentIsPassword()?.as_bool())
            };
            let out = ask().ok();
            if init.is_ok() {
                CoUninitialize();
            }
            out
        };
        let _ = tx.send(answer);
    });
    rx.recv_timeout(UIA_TIMEOUT).ok().flatten()
}

/// The older Windows way: a classic edit box with the `ES_PASSWORD` style
/// (the Win32 dialogs many older programs still use). Only an edit box's
/// style is read that way - the same bit means something else on other
/// kinds of control.
fn win32_password_box() -> bool {
    // SAFETY: plain handle queries; `info` is a correctly sized, owned
    // struct and `class` a buffer the call writes at most `len` into.
    unsafe {
        let fg = GetForegroundWindow();
        if fg.is_invalid() {
            return false;
        }
        let thread_id = GetWindowThreadProcessId(fg, None);
        let mut info = GUITHREADINFO {
            cbSize: std::mem::size_of::<GUITHREADINFO>() as u32,
            ..Default::default()
        };
        if GetGUIThreadInfo(thread_id, &mut info).is_err() || info.hwndFocus.is_invalid() {
            return false;
        }
        let mut class = [0u16; 64];
        let len = GetClassNameW(info.hwndFocus, &mut class).max(0) as usize;
        let name = String::from_utf16_lossy(&class[..len.min(class.len())]).to_ascii_lowercase();
        if !(name == "edit" || name.starts_with("richedit")) {
            return false;
        }
        GetWindowLongW(info.hwndFocus, GWL_STYLE) & ES_PASSWORD != 0
    }
}

// ---------------------------------------------------------------------------
// Ctrl+V
// ---------------------------------------------------------------------------

fn key(vk: VIRTUAL_KEY, up: bool) -> INPUT {
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT {
                wVk: vk,
                wScan: 0,
                dwFlags: if up {
                    KEYEVENTF_KEYUP
                } else {
                    KEYBD_EVENT_FLAGS::default()
                },
                time: 0,
                dwExtraInfo: 0,
            },
        },
    }
}

/// Ctrl down, V down and up, a short hold, Ctrl up (Handy's chord).
fn send_ctrl_v() -> Result<(), String> {
    let size = std::mem::size_of::<INPUT>() as i32;
    let down = [key(VK_CONTROL, false), key(VK_V, false), key(VK_V, true)];
    // SAFETY: `down` is a valid array of keyboard INPUTs for this call.
    let sent = unsafe { SendInput(&down, size) };
    thread::sleep(CHORD_HOLD);
    // Ctrl is always let go again, whatever happened above: a Ctrl left
    // "down" by this app would change every key the owner presses next.
    // SAFETY: as above.
    let released = unsafe { SendInput(&[key(VK_CONTROL, true)], size) };
    if sent as usize != down.len() || released != 1 {
        return Err("Windows would not take the Ctrl+V keys".to_string());
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// The clipboard transaction (adapted from Handy)
// ---------------------------------------------------------------------------

struct SavedFormat {
    format: u32,
    data: Vec<u8>,
}

struct WinTxShared {
    state: Mutex<TxState>,
    text: String,
    snapshot: Mutex<Vec<SavedFormat>>,
    /// A copied HBITMAP (as a raw number), put back with SetClipboardData.
    saved_bitmap: Mutex<Option<usize>>,
    sequence: Mutex<u32>,
    /// Told once how the paste ended.
    done: Mutex<Option<Sender<Settled>>>,
}

/// The transaction holding the clipboard now, if any.
static PENDING: Mutex<Option<Arc<WinTxShared>>> = Mutex::new(None);

/// `OpenClipboard`, tried a few times: another program (very often a
/// clipboard manager) may hold it for a moment - the same short retry
/// clipboard_privacy.rs uses.
unsafe fn open_clipboard(owner: Option<HWND>) -> windows::core::Result<()> {
    let mut last = OpenClipboard(owner);
    for _ in 0..9 {
        if last.is_ok() {
            break;
        }
        thread::sleep(Duration::from_millis(15));
        last = OpenClipboard(owner);
    }
    last
}

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn lock<T>(m: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|p| p.into_inner())
}

unsafe fn shared_ptr(hwnd: HWND) -> *const WinTxShared {
    GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *const WinTxShared
}

/// Puts the promised words on the clipboard, which must already be open
/// (Windows opens it for us for WM_RENDERFORMAT).
unsafe fn render_text(shared: &WinTxShared) {
    let wide_text = wide(&shared.text);
    let Ok(hg) = GlobalAlloc(GMEM_MOVEABLE, wide_text.len() * 2) else {
        return;
    };
    let ptr = GlobalLock(hg) as *mut u16;
    if ptr.is_null() {
        let _ = GlobalFree(Some(hg));
        return;
    }
    std::ptr::copy_nonoverlapping(wide_text.as_ptr(), ptr, wide_text.len());
    let _ = GlobalUnlock(hg);
    if SetClipboardData(u32::from(CF_UNICODETEXT.0), Some(HANDLE(hg.0))).is_err() {
        let _ = GlobalFree(Some(hg));
    }
}

unsafe extern "system" fn paste_wnd_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    let shared = shared_ptr(hwnd);
    match msg {
        WM_RENDERFORMAT => {
            if !shared.is_null() {
                let shared = &*shared;
                lock(&shared.state).record_receipt(Instant::now());
                if wparam.0 as u32 == u32::from(CF_UNICODETEXT.0) {
                    render_text(shared);
                }
            }
            LRESULT(0)
        }
        WM_RENDERALLFORMATS => {
            // The window is going away with the promise still on the
            // clipboard - not a read, so no receipt. Windows does not open
            // the clipboard for us here.
            if !shared.is_null() {
                let shared = &*shared;
                if OpenClipboard(Some(hwnd)).is_ok() {
                    if GetClipboardOwner()
                        .map(|owner| owner == hwnd)
                        .unwrap_or(false)
                    {
                        render_text(shared);
                    }
                    let _ = CloseClipboard();
                }
            }
            LRESULT(0)
        }
        WM_DESTROYCLIPBOARD => {
            if !shared.is_null() {
                lock(&(*shared).state).ownership_lost = true;
            }
            LRESULT(0)
        }
        WM_TIMER => {
            if !shared.is_null() {
                on_timer(&*shared);
            }
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

fn ensure_window_class(hinstance: HINSTANCE) {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let wc = WNDCLASSW {
            lpfnWndProc: Some(paste_wnd_proc),
            hInstance: hinstance,
            lpszClassName: CLASS_NAME,
            ..Default::default()
        };
        // SAFETY: `wc` is fully initialised and its class name is 'static.
        unsafe {
            RegisterClassW(&wc);
        }
    });
}

/// A paste still holding the clipboard is settled first, so the snapshot
/// below takes the owner's own clipboard, not the earlier words.
fn flush_pending() {
    let Some(previous) = lock(&PENDING).take() else {
        return;
    };
    lock(&previous.state).cancelled = true;
    let sequence = *lock(&previous.sequence);
    // SAFETY: no preconditions.
    if unsafe { GetClipboardSequenceNumber() } == sequence {
        // SAFETY: may be called from any thread; opens and closes the
        // clipboard itself.
        unsafe { restore_snapshot(&previous, sequence) };
    }
}

/// Puts the owner's clipboard back - but only if, with the clipboard open,
/// the sequence number is still `expected`: a copy the owner made after the
/// check and before the open must win.
unsafe fn restore_snapshot(shared: &WinTxShared, expected: u32) {
    if open_clipboard(None).is_err() {
        crate::logfile::log("[talk-type] could not open the clipboard to put it back");
        return;
    }
    if GetClipboardSequenceNumber() != expected {
        let _ = CloseClipboard();
        crate::logfile::log("[talk-type] the clipboard changed meanwhile; left as it is");
        return;
    }
    let _ = EmptyClipboard();
    for saved in lock(&shared.snapshot).iter() {
        if saved.data.is_empty() {
            continue;
        }
        let Ok(hg) = GlobalAlloc(GMEM_MOVEABLE, saved.data.len()) else {
            continue;
        };
        let ptr = GlobalLock(hg) as *mut u8;
        if ptr.is_null() {
            let _ = GlobalFree(Some(hg));
            continue;
        }
        std::ptr::copy_nonoverlapping(saved.data.as_ptr(), ptr, saved.data.len());
        let _ = GlobalUnlock(hg);
        // On success Windows owns the handle.
        if SetClipboardData(saved.format, Some(HANDLE(hg.0))).is_err() {
            let _ = GlobalFree(Some(hg));
        }
    }
    if let Some(raw) = lock(&shared.saved_bitmap).take() {
        let _ = SetClipboardData(u32::from(CF_BITMAP.0), Some(HANDLE(raw as *mut _)));
    }
    let _ = CloseClipboard();
}

unsafe fn snapshot_clipboard(hwnd: HWND, shared: &WinTxShared) -> Result<(), String> {
    open_clipboard(Some(hwnd)).map_err(|e| format!("could not open the clipboard ({e})"))?;
    let mut formats = Vec::new();
    let mut format = 0u32;
    loop {
        format = EnumClipboardFormats(format);
        if format == 0 {
            break;
        }
        if format == u32::from(CF_BITMAP.0) {
            // A drawing handle, not memory: copied as a picture instead.
            if let Ok(handle) = GetClipboardData(format) {
                if let Ok(copy) =
                    CopyImage(handle, IMAGE_BITMAP_TYPE, 0, 0, LR_CREATEDIBSECTION_FLAG)
                {
                    *lock(&shared.saved_bitmap) = Some(copy.0 as usize);
                }
            }
            continue;
        }
        // Formats whose handles are not plain memory cannot be copied byte
        // for byte (Handy's list). Added here: CF_METAFILEPICT, whose memory
        // holds a metafile HANDLE that EmptyClipboard deletes - a byte copy
        // would put back a dangling handle - and the GDI-object range
        // (CF_GDIOBJFIRST..=CF_GDIOBJLAST), which is never memory at all.
        if [
            CF_ENHMETAFILE,
            CF_METAFILEPICT,
            CF_DSPENHMETAFILE,
            CF_DSPBITMAP,
            CF_DSPMETAFILEPICT,
            CF_DSPTEXT,
            CF_OWNERDISPLAY,
            CF_PALETTE,
        ]
        .iter()
        .any(|f| u32::from(f.0) == format)
            || (0x0300..=0x03FF).contains(&format)
        {
            continue;
        }
        if let Ok(handle) = GetClipboardData(format) {
            let hg = HGLOBAL(handle.0);
            let size = GlobalSize(hg);
            if size == 0 || size > MAX_FORMAT_BYTES {
                continue;
            }
            let ptr = GlobalLock(hg) as *const u8;
            if ptr.is_null() {
                continue;
            }
            let data = std::slice::from_raw_parts(ptr, size).to_vec();
            let _ = GlobalUnlock(hg);
            formats.push(SavedFormat { format, data });
        }
    }
    let _ = CloseClipboard();
    *lock(&shared.snapshot) = formats;
    Ok(())
}

/// Puts the promise and the three "keep this private" markers on the
/// clipboard. Returns the clipboard's new sequence number.
unsafe fn publish(hwnd: HWND) -> Result<u32, String> {
    open_clipboard(Some(hwnd)).map_err(|e| format!("could not open the clipboard ({e})"))?;
    let published = publish_formats();
    let closed = CloseClipboard();
    published?;
    closed.map_err(|e| format!("could not close the clipboard ({e})"))?;
    Ok(GetClipboardSequenceNumber())
}

unsafe fn publish_formats() -> Result<(), String> {
    EmptyClipboard().map_err(|e| format!("could not clear the clipboard ({e})"))?;

    // Handy's lines 374-376: not in Win+V's history, not synced to the
    // owner's other PCs, and ignored by clipboard-watching programs.
    for (name, value) in [
        ("ExcludeClipboardContentFromMonitorProcessing", 1u32),
        ("CanIncludeInClipboardHistory", 0u32),
        ("CanUploadToCloudClipboard", 0u32),
    ] {
        let name_wide = wide(name);
        let format = RegisterClipboardFormatW(PCWSTR(name_wide.as_ptr()));
        if format == 0 {
            // Without the markers the words could land in History or the
            // Cloud Clipboard: refuse rather than paste them there.
            return Err(format!("could not set up the clipboard's {name} marker"));
        }
        let Ok(hg) = GlobalAlloc(GMEM_MOVEABLE, std::mem::size_of::<u32>()) else {
            return Err("could not allocate memory for the clipboard".to_string());
        };
        let ptr = GlobalLock(hg) as *mut u32;
        if ptr.is_null() {
            let _ = GlobalFree(Some(hg));
            return Err("could not allocate memory for the clipboard".to_string());
        }
        *ptr = value;
        let _ = GlobalUnlock(hg);
        if SetClipboardData(format, Some(HANDLE(hg.0))).is_err() {
            let _ = GlobalFree(Some(hg));
            return Err(format!("could not set the clipboard's {name} marker"));
        }
    }

    // A null handle is the promise. SetClipboardData hands back the handle it
    // was given, so success is null too and the crate reports it as an
    // error; only a real thread error counts, and it is cleared first.
    SetLastError(ERROR_SUCCESS);
    if let Err(e) = SetClipboardData(u32::from(CF_UNICODETEXT.0), None) {
        if e.code().is_err() {
            return Err(format!("could not put the words on the clipboard ({e})"));
        }
    }
    Ok(())
}

fn on_timer(shared: &WinTxShared) {
    // Settled already: a last tick can arrive before the loop sees the
    // quit message, and must not settle (or log) a second time.
    if lock(&shared.done).is_none() {
        return;
    }
    let now = Instant::now();
    let finish = {
        let mut st = lock(&shared.state);
        if st.cancelled {
            true
        } else {
            match evaluate(&st, now) {
                WaitDecision::KeepWaiting => false,
                WaitDecision::Finish => {
                    st.cancelled = true;
                    true
                }
            }
        }
    };
    if !finish {
        return;
    }
    let (settled, ownership_lost) = {
        let st = lock(&shared.state);
        (Settled::from_state(&st), st.ownership_lost)
    };
    let sequence = *lock(&shared.sequence);
    // SAFETY: no preconditions.
    let still_ours = !ownership_lost && unsafe { GetClipboardSequenceNumber() } == sequence;
    if still_ours {
        // SAFETY: opens and closes the clipboard itself.
        unsafe { restore_snapshot(shared, sequence) };
    } else {
        crate::logfile::log("[talk-type] the owner copied something meanwhile; left as it is");
    }
    {
        let mut slot = lock(&PENDING);
        let is_us = slot
            .as_ref()
            .is_some_and(|p| std::ptr::eq(Arc::as_ptr(p), shared));
        if is_us {
            *slot = None;
        }
    }
    if let Some(done) = lock(&shared.done).take() {
        let _ = done.send(settled);
    }
    // SAFETY: ends this thread's message loop.
    unsafe { PostQuitMessage(0) };
}

unsafe fn destroy_window_and_shared(hwnd: HWND) {
    let ptr = shared_ptr(hwnd);
    let _ = DestroyWindow(hwnd);
    if !ptr.is_null() {
        drop(Arc::from_raw(ptr));
    }
}

fn pump_thread(shared: Arc<WinTxShared>, ready: Sender<Result<(), String>>) {
    // SAFETY: every Win32 call below runs on this one thread, which owns
    // the hidden window, its message loop and (while it holds it) the
    // clipboard. The Arc handed to the window's user data is taken back in
    // `destroy_window_and_shared`.
    unsafe {
        flush_pending();

        let hinstance = match GetModuleHandleW(PCWSTR::null()) {
            Ok(hmodule) => HINSTANCE(hmodule.0),
            Err(e) => {
                let _ = ready.send(Err(format!("could not start ({e})")));
                return;
            }
        };
        ensure_window_class(hinstance);

        let hwnd = match CreateWindowExW(
            WINDOW_EX_STYLE::default(),
            CLASS_NAME,
            w!("JarvisTalkTypePaste"),
            WINDOW_STYLE::default(),
            0,
            0,
            0,
            0,
            Some(HWND_MESSAGE),
            None,
            Some(hinstance),
            None,
        ) {
            Ok(hwnd) => hwnd,
            Err(e) => {
                let _ = ready.send(Err(format!("could not start ({e})")));
                return;
            }
        };
        SetWindowLongPtrW(
            hwnd,
            GWLP_USERDATA,
            Arc::into_raw(shared.clone()) as *const _ as isize,
        );

        let published = match snapshot_clipboard(hwnd, &shared) {
            Ok(()) => match publish(hwnd) {
                Ok(sequence) => Ok(sequence),
                Err(e) => {
                    // publish may have emptied the clipboard before it
                    // failed: put the owner's copy straight back.
                    restore_snapshot(&shared, GetClipboardSequenceNumber());
                    Err(e)
                }
            },
            Err(e) => Err(e),
        };
        let sequence = match published {
            Ok(sequence) => sequence,
            Err(e) => {
                destroy_window_and_shared(hwnd);
                let _ = ready.send(Err(e));
                return;
            }
        };
        *lock(&shared.sequence) = sequence;
        lock(&shared.state).published_at = Instant::now();
        *lock(&PENDING) = Some(shared.clone());
        let _ = SetTimer(Some(hwnd), TIMER_ID, TIMER_INTERVAL_MS, None);
        let _ = ready.send(Ok(()));

        let mut msg = MSG::default();
        while GetMessageW(&mut msg, None, 0, 0).as_bool() {
            let _ = DispatchMessageW(&msg);
        }

        let _ = KillTimer(Some(hwnd), TIMER_ID);
        destroy_window_and_shared(hwnd);
    }
}

/// Pastes `text` into the program in front and waits to hear how it went.
/// Blocking: run it on a blocking thread.
pub(crate) fn paste(text: &str) -> Result<Settled, String> {
    let (done_tx, done_rx) = mpsc::channel();
    let shared = Arc::new(WinTxShared {
        state: Mutex::new(TxState::new()),
        text: text.to_string(),
        snapshot: Mutex::new(Vec::new()),
        saved_bitmap: Mutex::new(None),
        sequence: Mutex::new(0),
        done: Mutex::new(Some(done_tx)),
    });

    let (ready_tx, ready_rx) = mpsc::channel();
    let for_pump = shared.clone();
    thread::spawn(move || pump_thread(for_pump, ready_tx));

    match ready_rx.recv() {
        Ok(Ok(())) => {}
        Ok(Err(e)) => return Err(e),
        Err(_) => return Err("the paste stopped before it began".to_string()),
    }

    // Marked BEFORE the keys go: a quick program may read while Ctrl is
    // still held.
    lock(&shared.state).injected_at = Some(Instant::now());
    if let Err(e) = send_ctrl_v() {
        lock(&shared.state).injection_failed = true;
        crate::logfile::log(&format!("[talk-type] {e}"));
    }

    // The pump settles within RESTORE_TIMEOUT of publishing; a little more
    // for the last timer tick.
    match done_rx.recv_timeout(RESTORE_TIMEOUT + Duration::from_secs(2)) {
        Ok(settled) => Ok(settled),
        Err(_) => Err("the paste did not finish in time".to_string()),
    }
}
