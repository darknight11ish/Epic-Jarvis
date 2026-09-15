//! Start with Windows, or do not. One registry value, written by hand.
//!
//! ## Why not `tauri-plugin-autostart`
//!
//! It would work, and on Windows it writes the same registry value this file
//! writes. It is a new crate in the dependency graph, a new plugin to
//! initialise, a new permission in the ACL, and — the part that decided it —
//! it also carries a Linux `.desktop` writer and a macOS launch-agent writer
//! for a product that ships only a Windows installer. Fourteen lines of
//! `RegSetValueExW` against bindings already compiled into this binary is
//! less to audit than all of that.
//!
//! ## The key
//!
//! ```text
//! HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
//!   JarvisDesktop = "C:\path\to\Jarvis Desktop.exe" --autostart
//! ```
//!
//! `HKEY_CURRENT_USER`, never `HKEY_LOCAL_MACHINE`: per-user needs no
//! elevation, and the installer runs `installMode: "currentUser"` anyway, so a
//! machine-wide entry would point at an executable other users do not have.
//!
//! ## `--autostart`
//!
//! The flag is not decoration. Launched at login the app must come up quiet —
//! no quickbar, no stolen focus while Windows is still painting the desktop —
//! and the only way to know a launch came from the Run key is to be told.
//! [`launched_at_login`] reads it back.
//!
//! ## What this does not fix
//!
//! The `Alt+Space` race. Registering a global hotkey at login competes with
//! every other Run-key program doing the same, and the Run key has no ordering
//! guarantee. Autostart makes Jarvis *present* after a reboot; it does not
//! make it first. That is a separate problem and this file does not claim it.

#[cfg(windows)]
use std::path::PathBuf;

/// The value name under `Run`. Stable: changing it would orphan the old entry
/// and the app would start twice.
#[cfg(windows)]
const VALUE_NAME: &str = "JarvisDesktop";

#[cfg(windows)]
const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";

/// The argument added to the autostart command line, and looked for on boot.
pub const AUTOSTART_FLAG: &str = "--autostart";

/// Was this process started by the Run key rather than by a person?
///
/// Read from the real command line rather than remembered in the store,
/// because the store records what we *asked* Windows to do and this asks what
/// Windows actually did — they differ after a failed write, and after the user
/// removes the entry with Task Manager's Startup tab, which is where most
/// people turn these off.
pub fn launched_at_login() -> bool {
    std::env::args().any(|a| a == AUTOSTART_FLAG)
}

/// Is the Run entry present, and does it point at *this* executable?
///
/// The path check matters: after the owner reinstalls somewhere else, or runs
/// a build from `target\release` having installed the MSI, a stale entry
/// starts the *other* copy at login. Reporting "on" then would be a lie, and
/// the fix — toggle off, toggle on — is only discoverable if the UI says off.
#[cfg(windows)]
pub fn is_enabled() -> bool {
    match (read_value(), command_line()) {
        (Some(stored), Some(want)) => paths_match(&stored, &want),
        _ => false,
    }
}

#[cfg(not(windows))]
pub fn is_enabled() -> bool {
    false
}

/// Turn it on or off. Returns what the state is afterwards, read back rather
/// than assumed.
#[cfg(windows)]
pub fn set(enabled: bool) -> Result<bool, String> {
    if enabled {
        let line = command_line()
            .ok_or_else(|| "could not work out where this program is installed".to_string())?;
        write_value(&line)?;
    } else {
        delete_value()?;
    }
    Ok(is_enabled())
}

#[cfg(not(windows))]
pub fn set(_enabled: bool) -> Result<bool, String> {
    Err("starting with the computer is a Windows feature; this build is not Windows".to_string())
}

/// `"<exe>" --autostart`, quoted because Program Files has a space in it.
///
/// An unquoted path with a space is the classic Windows service-path bug: the
/// loader tries `C:\Program` first.
#[cfg(windows)]
fn command_line() -> Option<String> {
    let exe = std::env::current_exe().ok()?;
    Some(format!("\"{}\" {AUTOSTART_FLAG}", exe.display()))
}

/// Compare a stored command line with the one we would write.
///
/// Not a string equality: Windows paths are case-insensitive, and an entry
/// written by an older build might carry different arguments after the path.
/// Only the executable is compared, and only after unquoting it.
#[cfg(windows)]
fn paths_match(stored: &str, want: &str) -> bool {
    fn exe_of(line: &str) -> Option<PathBuf> {
        let line = line.trim();
        let path = if let Some(rest) = line.strip_prefix('"') {
            rest.split('"').next()?
        } else {
            line.split_whitespace().next()?
        };
        Some(PathBuf::from(path))
    }
    match (exe_of(stored), exe_of(want)) {
        (Some(a), Some(b)) => a
            .to_string_lossy()
            .eq_ignore_ascii_case(&b.to_string_lossy()),
        _ => false,
    }
}

// ---------------------------------------------------------------------------
// The three registry calls
// ---------------------------------------------------------------------------

#[cfg(windows)]
mod imp {
    use super::{RUN_KEY, VALUE_NAME};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_SUCCESS};
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW, RegSetValueExW, HKEY,
        HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ,
    };

    /// A NUL-terminated UTF-16 buffer, which is what every `*W` call wants.
    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    struct Key(HKEY);

    impl Drop for Key {
        fn drop(&mut self) {
            // Closed on every path, including the error ones. A leaked HKEY
            // holds the key open for the life of the process, which blocks
            // nothing visible and so would never be noticed.
            unsafe { RegCloseKey(self.0) };
        }
    }

    fn open(access: u32) -> Result<Key, String> {
        let mut key: HKEY = std::ptr::null_mut();
        // The Run key always exists on a working Windows install, so this
        // opens rather than creates: if it is genuinely absent, something is
        // wrong that writing a value will not fix, and the error says so.
        let rc = unsafe {
            RegOpenKeyExW(
                HKEY_CURRENT_USER,
                wide(RUN_KEY).as_ptr(),
                0,
                access,
                &mut key,
            )
        };
        if rc != ERROR_SUCCESS {
            return Err(format!(
                "could not open the Windows startup list (error {rc})"
            ));
        }
        Ok(Key(key))
    }

    pub fn read() -> Option<String> {
        let key = open(KEY_READ).ok()?;
        let name = wide(VALUE_NAME);
        let mut kind: u32 = 0;
        let mut len: u32 = 0;
        // First call with a null buffer asks for the size, in BYTES.
        let rc = unsafe {
            RegQueryValueExW(
                key.0,
                name.as_ptr(),
                std::ptr::null(),
                &mut kind,
                std::ptr::null_mut(),
                &mut len,
            )
        };
        if rc != ERROR_SUCCESS || kind != REG_SZ || len == 0 {
            return None;
        }
        let mut buf = vec![0u16; (len as usize).div_ceil(2)];
        let mut len2 = len;
        let rc = unsafe {
            RegQueryValueExW(
                key.0,
                name.as_ptr(),
                std::ptr::null(),
                &mut kind,
                buf.as_mut_ptr().cast(),
                &mut len2,
            )
        };
        if rc != ERROR_SUCCESS {
            return None;
        }
        // The stored length includes the terminator, and REG_SZ is not
        // required to be terminated at all — trimming to the first NUL handles
        // both, where assuming one would leave a NUL inside the String.
        let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
        Some(
            std::ffi::OsString::from_wide(&buf[..end])
                .to_string_lossy()
                .into_owned(),
        )
    }

    pub fn write(value: &str) -> Result<(), String> {
        let key = open(KEY_SET_VALUE)?;
        let name = wide(VALUE_NAME);
        let data = wide(value);
        let bytes = std::mem::size_of_val(&data[..]) as u32;
        let rc =
            unsafe { RegSetValueExW(key.0, name.as_ptr(), 0, REG_SZ, data.as_ptr().cast(), bytes) };
        if rc != ERROR_SUCCESS {
            return Err(format!(
                "could not add Jarvis to the Windows startup list (error {rc})"
            ));
        }
        Ok(())
    }

    pub fn delete() -> Result<(), String> {
        let key = open(KEY_SET_VALUE)?;
        let rc = unsafe { RegDeleteValueW(key.0, wide(VALUE_NAME).as_ptr()) };
        // Already gone is the state the caller asked for, not a failure. This
        // is also the path taken when the owner turned it off in Task Manager
        // and then toggled it off here too.
        if rc != ERROR_SUCCESS && rc != ERROR_FILE_NOT_FOUND {
            return Err(format!(
                "could not remove Jarvis from the Windows startup list (error {rc})"
            ));
        }
        Ok(())
    }
}

#[cfg(windows)]
fn read_value() -> Option<String> {
    imp::read()
}

#[cfg(windows)]
fn write_value(v: &str) -> Result<(), String> {
    imp::write(v)
}

#[cfg(windows)]
fn delete_value() -> Result<(), String> {
    imp::delete()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_flag_is_read_from_the_command_line() {
        // Not asserting a value — the test binary's own argv decides it. What
        // matters is that it answers without panicking and without touching
        // the registry, because `is_enabled` is called on every settings read.
        let _ = launched_at_login();
    }

    #[cfg(windows)]
    #[test]
    fn a_stale_entry_pointing_elsewhere_does_not_count_as_on() {
        assert!(paths_match(
            r#""C:\Program Files\Jarvis\Jarvis Desktop.exe" --autostart"#,
            r#""c:\program files\jarvis\Jarvis Desktop.exe" --autostart"#,
        ));
        assert!(!paths_match(
            r#""C:\old\Jarvis Desktop.exe" --autostart"#,
            r#""C:\Program Files\Jarvis\Jarvis Desktop.exe" --autostart"#,
        ));
        // An unquoted path with a space is the bug this guards: taking the
        // first whitespace-delimited token gives `C:\Program`, which matches
        // nothing, so the UI says off rather than claiming a working entry.
        assert!(!paths_match(
            r"C:\Program Files\Jarvis\Jarvis Desktop.exe --autostart",
            r#""C:\Program Files\Jarvis\Jarvis Desktop.exe" --autostart"#,
        ));
        // Different arguments after the same executable still count as on:
        // an older build wrote a different flag and the entry still works.
        assert!(paths_match(
            r#""C:\Jarvis\Jarvis Desktop.exe" --silent"#,
            r#""C:\Jarvis\Jarvis Desktop.exe" --autostart"#,
        ));
    }

    #[cfg(not(windows))]
    #[test]
    fn it_refuses_politely_off_windows() {
        assert!(!is_enabled());
        assert!(set(true).is_err());
    }
}
