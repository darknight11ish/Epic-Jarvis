//! "open Notion", "open settings", "open Jarvis settings": opening a program
//! or a Windows panel because the owner asked for it in his own words.
//!
//! The owner's request of 2026-10-10: *"can it control parts of my pc like if
//! i ask open notion, or open settings, or open jarvis settings. it should be
//! able to do all of that."*
//!
//! WHERE THIS SITS
//! `jarvis_open.py` (the PC's backend, SHIPPED whole) reads the sentence and
//! decides WHAT was named - an app, a Windows panel, one of Jarvis's own
//! Settings sections, or a shell target - and answers with the one plain
//! sentence plus `open_app` / `open_app_kind` / `open_place` on
//! `X-Jarvis-Route`. This module is the half that runs on the PC the owner is
//! sitting at: it opens that thing, in Rust, with no new Tauri command and no
//! new permission, reached from [`crate::commands::stream_chat`] - the same
//! place, and the same shape, as "open a chat" (the floating face, 2026-09-27).
//!
//! WHY IT IS NOT A COMMAND
//! A command is reachable from every window that holds its grant, and the
//! pages have no business starting programs. The owner's words arrive on the
//! chat stream, which Rust already owns, so the decision to open something
//! never has to cross the IPC boundary at all. That also means the ACL files
//! (`build.rs`, `surfaces.toml`, the capability grants) need no new entry for
//! this feature: there is no new command to grant.
//!
//! WHAT IT WILL AND WILL NOT OPEN
//! * A program is resolved against THIS PC's own Start menu - the same
//!   shortcuts the Start menu itself shows, read from the two folders Windows
//!   keeps them in. Nothing is downloaded, installed or searched for on the
//!   internet, and no path comes from a page or from the model.
//! * A name that matches nothing is NOT guessed at. There is no "nearest
//!   match": the owner is told plainly, and nothing opens. A name that matches
//!   two different shortcuts is a question, not a coin toss.
//! * A Windows panel is one of the fixed `ms-settings:` addresses the backend
//!   already chose from its own list (`jarvis_open.PANELS`); this module only
//!   ever passes on a string that starts with `ms-settings:`.
//! * The file explorer and the old Control Panel are the two fixed shell
//!   commands the backend's own `SHELL_TARGETS` names.
//! * Nothing is opened by the AI model: `jarvis_open.py` gives it no tool, and
//!   the phrase has to be the owner's own typed or spoken sentence to reach
//!   `jarvis_quick.py`'s fast path at all. Outside text (an email, a web page,
//!   a note) has nothing to steer.
//!
//! WINDOWS ONLY, AND HONEST WITHOUT IT
//! The index is the Start menu's own folders, and the launcher is
//! `ShellExecuteExW` - the same call this app already uses to open a link in
//! the owner's browser ([`crate::commands`] `open_with_shell`). On a developer
//! machine that is not Windows, [`open`] reports in plain words that this only
//! works on the PC, rather than pretending.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// One Start menu shortcut: the name the owner sees, and the file to launch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    /// The shortcut's file name without `.lnk`, lower-cased and with runs of
    /// whitespace collapsed - the key the owner's words are matched against.
    pub key: String,
    /// The shortcut's file name as Windows shows it ("Notion").
    pub name: String,
    /// The `.lnk` itself. `ShellExecuteExW` resolves it, so this module never
    /// has to parse the shortcut format.
    pub path: PathBuf,
}

/// What [`open`] did, in the words the caller needs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Opened {
    /// It was started.
    Started,
    /// Nothing on this PC's Start menu has that name. Never guessed at.
    NotFound,
    /// Two different shortcuts have that name, so the owner is asked which.
    Ambiguous(Vec<String>),
    /// The start menu is still being read (a first request on a cold start).
    /// Nothing has been opened; asking again in a moment works.
    NotReady,
}

/// The Start menu shortcuts, read once and kept.
///
/// `None` until [`index`] has finished. A cold read of both Start menu folders
/// on this PC takes a few milliseconds, but it happens on the chat stream's own
/// task, so it is done once and cached rather than per request.
static INDEX: OnceLock<Vec<Entry>> = OnceLock::new();

/// Both folders Windows keeps Start menu shortcuts in.
///
/// The per-user one is where nearly everything lives (`%APPDATA%\Microsoft\
/// Windows\Start Menu\Programs`); the all-users one holds what was installed
/// for everybody (`%ProgramData%\Microsoft\Windows\Start Menu\Programs`).
/// Neither is read recursively by more than [`MAX_DEPTH`] levels: the folders
/// are shallow by design, and a walk that follows a junction out of them could
/// take the whole disk.
fn start_menu_dirs() -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Some(appdata) = std::env::var_os("APPDATA") {
        out.push(
            Path::new(&appdata)
                .join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs"),
        );
    }
    if let Some(program_data) = std::env::var_os("ProgramData") {
        out.push(
            Path::new(&program_data)
                .join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs"),
        );
    }
    out
}

/// How deep below a Start menu folder a shortcut is still ours. The real tree
/// is `Programs\<Vendor>\<App>.lnk` and occasionally one level deeper.
const MAX_DEPTH: usize = 4;

/// How many shortcuts are read at most. A Start menu with more than this is
/// not a Start menu; the cap is here so a junction loop or a surprise cannot
/// turn one spoken sentence into an unbounded walk.
const MAX_ENTRIES: usize = 4096;

/// The key an owner's words and a shortcut's name are compared by: lower case,
/// with runs of whitespace collapsed. No fuzzy matching - see the module doc.
pub fn key_of(name: &str) -> String {
    name.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

/// Whether a Start menu file name is a program the owner might mean.
///
/// Split out of [`walk`] so the rule is testable without touching a disk; the
/// walk itself is then three lines of `read_dir` around this.
///
/// A `.lnk` and nothing else - the `readme.txt` beside it is not a program -
/// and not the repair/removal shortcuts installers leave behind ("Uninstall
/// Notion", "Remove Notion"). Those ARE shortcuts, so launching one would
/// work, and it is exactly what the owner did not mean.
pub fn is_program_shortcut(file_name: &str) -> bool {
    let lower = file_name.to_lowercase();
    let Some(stem) = lower.strip_suffix(".lnk") else {
        return false;
    };
    !stem.is_empty() && !stem.starts_with("uninstall") && !stem.starts_with("remove ")
}

fn walk(dir: &Path, depth: usize, out: &mut Vec<Entry>) {
    if depth > MAX_DEPTH || out.len() >= MAX_ENTRIES {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        if out.len() >= MAX_ENTRIES {
            return;
        }
        let path = entry.path();
        // `file_type` does not follow a symlink or a junction, which is what
        // keeps this walk inside the Start menu.
        let Ok(kind) = entry.file_type() else {
            continue;
        };
        if kind.is_dir() {
            walk(&path, depth + 1, out);
            continue;
        }
        if !kind.is_file() {
            continue;
        }
        let Some(file_name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if !is_program_shortcut(file_name) {
            continue;
        }
        let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        out.push(Entry {
            key: key_of(stem),
            name: stem.to_string(),
            path,
        });
    }
}

/// The Start menu's shortcuts, read once.
pub fn index() -> &'static Vec<Entry> {
    INDEX.get_or_init(|| {
        let mut out = Vec::new();
        for dir in start_menu_dirs() {
            walk(&dir, 0, &mut out);
        }
        out
    })
}

/// The unique shortcut `name` means, or why it does not mean one.
///
/// Exact name only, and never a guess: a key that matches one shortcut is
/// [`Opened::Started`]'s target, one that matches several is a question, and
/// one that matches none is [`Opened::NotFound`].
pub fn find<'a>(entries: &'a [Entry], name: &str) -> Result<&'a Entry, Opened> {
    let key = key_of(name);
    if key.is_empty() {
        return Err(Opened::NotFound);
    }
    let mut hits = entries.iter().filter(|e| e.key == key);
    let Some(first) = hits.next() else {
        return Err(Opened::NotFound);
    };
    let rest: Vec<&Entry> = hits.collect();
    if rest.is_empty() {
        return Ok(first);
    }
    // Two different shortcuts with the same name: the owner is asked, and
    // nothing opens. The path is never shown - it is a folder name the owner
    // does not need - only how many there are.
    let mut names: Vec<String> = vec![first.name.clone()];
    names.extend(rest.iter().map(|e| e.name.clone()));
    names.sort();
    names.dedup();
    Err(Opened::Ambiguous(names))
}

/// Open what the owner named.
///
/// `kind` and `target` are `X-Jarvis-Route`'s `open_app_kind` and `open_app`
/// (`open_app_built` says whether the target is a program the backend named
/// itself), straight from `jarvis_open.py`. Anything this function does not
/// recognise opens nothing and says so in plain words - never a fallback to a
/// shell, and never a guess at a similar name.
pub fn open(kind: &str, target: &str, built: bool) -> Result<Opened, String> {
    match kind {
        // A program. Windows' own accessories arrive `built` - the backend
        // named the program itself, so there is no Start menu shortcut to look
        // up. A name in the owner's own words is resolved against this PC's
        // Start menu and never guessed at.
        "app" => {
            if built {
                shell_open(target)?;
                return Ok(Opened::Started);
            }
            match find(index(), target) {
                Ok(entry) => {
                    shell_open_path(&entry.path)?;
                    Ok(Opened::Started)
                }
                Err(why) => Ok(why),
            }
        }
        // A Windows settings page. Only ever one of the backend's own fixed
        // `ms-settings:` addresses - the prefix is checked here too, so a
        // string that arrived from anywhere else cannot become a shell target.
        "panel" => {
            if !target.starts_with("ms-settings:") {
                return Err("That is not a settings page this app opens.".to_string());
            }
            shell_open(target)?;
            Ok(Opened::Started)
        }
        // File Explorer, the old Control Panel, Task Manager and the Recycle
        // Bin: the fixed commands the backend's own `SHELL_TARGETS` names,
        // checked against that same list here.
        "other" => {
            if !matches!(
                target,
                "explorer.exe" | "control.exe" | "taskmgr.exe" | "shell:RecycleBinFolder"
            ) {
                return Err("That is not a place this app opens.".to_string());
            }
            shell_open(target)?;
            Ok(Opened::Started)
        }
        // "jarvis" is handled where it belongs, by the Settings window
        // (main.js's openSettingsFromRoute), not here: this module only ever
        // starts a program or a Windows page. Reported as started so the caller
        // says nothing extra about it.
        "jarvis" => Ok(Opened::Started),
        _ => Err("That is not something this app opens.".to_string()),
    }
}

/// Whether the Start menu has finished being read, for a caller that wants to
/// say "one moment" rather than "not found".
pub fn index_ready() -> bool {
    INDEX.get().is_some()
}

/// Read the Start menu now, so the first "open Notion" does not have to wait.
/// Called from `setup`, where a few milliseconds cost nothing.
pub fn warm_up() {
    let _ = index();
}

#[cfg(target_os = "windows")]
fn shell_open(target: &str) -> Result<(), String> {
    // The same call, and the same reasoning, as `commands::open_with_shell`:
    // `ShellExecuteExW` returns a real error and is not the `rundll32` LOLBin.
    // `open_with_shell` itself is private to `commands`, and duplicating four
    // lines is cheaper than widening that module's surface for one caller -
    // both are the one Win32 call, and both are tested the same way.
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::Shell::{
        ShellExecuteExW, SEE_MASK_FLAG_NO_UI, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    fn wide(value: &std::ffi::OsStr) -> Vec<u16> {
        value.encode_wide().chain(std::iter::once(0)).collect()
    }

    let verb = wide(std::ffi::OsStr::new("open"));
    let file = wide(std::ffi::OsStr::new(target));

    let mut info: SHELLEXECUTEINFOW = unsafe { std::mem::zeroed() };
    info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
    info.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
    info.lpVerb = verb.as_ptr();
    info.lpFile = file.as_ptr();
    info.nShow = SW_SHOWNORMAL;

    let ok = unsafe { ShellExecuteExW(&mut info) };
    if ok == 0 {
        let err = std::io::Error::last_os_error();
        return Err(format!(
            "Windows could not open {target}: {err}. A policy may be blocking it, \
             or nothing on this PC is set up for it."
        ));
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn shell_open(target: &str) -> Result<(), String> {
    Err(format!(
        "Opening {target} is a Windows-only thing; this build is not running on \
         the owner's PC."
    ))
}

#[cfg(target_os = "windows")]
fn shell_open_path(path: &Path) -> Result<(), String> {
    // `ShellExecuteExW` resolves a `.lnk` itself, arguing for just handing it
    // the shortcut. It also takes a `&OsStr` where `shell_open` takes a `&str`,
    // and a Start menu shortcut's folder can hold characters that are not
    // valid UTF-8 - so the file name is passed as an OS string and never
    // round-tripped through a `String`.
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::Shell::{
        ShellExecuteExW, SEE_MASK_FLAG_NO_UI, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

    fn wide(value: &std::ffi::OsStr) -> Vec<u16> {
        value.encode_wide().chain(std::iter::once(0)).collect()
    }

    let verb = wide(std::ffi::OsStr::new("open"));
    let file = wide(path.as_os_str());

    let mut info: SHELLEXECUTEINFOW = unsafe { std::mem::zeroed() };
    info.cbSize = std::mem::size_of::<SHELLEXECUTEINFOW>() as u32;
    info.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
    info.lpVerb = verb.as_ptr();
    info.lpFile = file.as_ptr();
    info.nShow = SW_SHOWNORMAL;

    let ok = unsafe { ShellExecuteExW(&mut info) };
    if ok == 0 {
        let err = std::io::Error::last_os_error();
        return Err(format!(
            "Windows could not open {}: {err}. A policy may be blocking it.",
            path.display()
        ));
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn shell_open_path(path: &Path) -> Result<(), String> {
    Err(format!(
        "Opening {} is a Windows-only thing; this build is not running on the \
         owner's PC.",
        path.display()
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(name: &str, path: &str) -> Entry {
        Entry {
            key: key_of(name),
            name: name.to_string(),
            path: PathBuf::from(path),
        }
    }

    #[test]
    fn a_name_is_matched_exactly_and_case_insensitively() {
        let entries = vec![entry("Notion", r"C:\sm\Notion.lnk")];
        assert_eq!(
            find(&entries, "Notion").map(|e| e.name.as_str()),
            Ok("Notion")
        );
        assert_eq!(
            find(&entries, "  notion  ").map(|e| e.name.as_str()),
            Ok("Notion")
        );
    }

    #[test]
    fn a_name_that_matches_nothing_is_not_guessed_at() {
        let entries = vec![entry("Notion", r"C:\sm\Notion.lnk")];
        // "Notion Calendar" is NOT "Notion": no prefix or nearest match.
        assert_eq!(find(&entries, "Notion Calendar"), Err(Opened::NotFound));
        assert_eq!(find(&entries, "Notepad"), Err(Opened::NotFound));
        assert_eq!(find(&entries, ""), Err(Opened::NotFound));
    }

    #[test]
    fn two_shortcuts_with_the_same_name_are_a_question_not_a_coin_toss() {
        let entries = vec![
            entry("Teams", r"C:\sm\Teams.lnk"),
            entry("Teams", r"C:\sm\work\Teams.lnk"),
        ];
        match find(&entries, "teams") {
            Err(Opened::Ambiguous(names)) => assert_eq!(names, vec!["Teams".to_string()]),
            other => panic!("expected a question, got {other:?}"),
        }
    }

    #[test]
    fn the_key_collapses_whitespace_and_lower_cases() {
        assert_eq!(key_of("  Windows   Terminal "), "windows terminal");
        assert_eq!(key_of("Notion"), "notion");
    }

    #[test]
    fn only_a_program_shortcut_is_a_program() {
        // The rule the walker asks about each file it finds, tested where it
        // lives rather than through a temp directory: the "uninstaller" case
        // is the one that matters, because launching one WOULD work and is
        // exactly what the owner did not mean.
        assert!(is_program_shortcut("Notion.lnk"));
        assert!(is_program_shortcut("Windows Terminal.lnk"));
        assert!(is_program_shortcut("notion.LNK"));
        assert!(!is_program_shortcut("Uninstall Notion.lnk"));
        assert!(!is_program_shortcut("Remove Notion.lnk"));
        assert!(!is_program_shortcut("readme.txt"));
        assert!(!is_program_shortcut("Notion"));
        assert!(!is_program_shortcut(".lnk"));
    }

    #[test]
    fn a_panel_that_is_not_a_settings_address_is_refused() {
        // The prefix check is what keeps a string that came from anywhere but
        // the backend's own list from becoming a shell target.
        for target in ["http://example.com", "calc.exe", ""] {
            let got = open("panel", target, true);
            assert!(
                matches!(got, Err(ref why) if why.contains("not a settings page")),
                "{target:?} should be refused, got {got:?}"
            );
        }
    }

    #[test]
    fn a_shell_target_outside_the_backends_own_list_is_refused() {
        for target in ["cmd.exe", "powershell.exe", r"C:\Windows\System32\calc.exe"] {
            let got = open("other", target, true);
            assert!(
                matches!(got, Err(ref why) if why.contains("not a place")),
                "{target:?} should be refused, got {got:?}"
            );
        }
    }

    #[test]
    fn an_unknown_kind_opens_nothing() {
        assert!(open("everything", "notepad.exe", true).is_err());
    }
}
