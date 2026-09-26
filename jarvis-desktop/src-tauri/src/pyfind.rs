//! "Find it for me" — locating a Python interpreter for supervision.
//!
//! Ease-of-use audit row 19: turning on "Let Jarvis Desktop start and stop
//! Jarvis" ([`crate::sidecar`]) needs a working path to `python.exe` in the
//! `Program` field, and a beginner is unlikely to know that path offhand —
//! today the field's own hint sends them to a PowerShell one-liner
//! (`settings.html`'s `#program-hint`). This gives the same answer that
//! one-liner gives, but run for them, from a button next to the field.
//!
//! **Supervision's default stays off.** This module only makes turning it
//! ON easier and safer to get right; [`find_python`] never writes to the
//! settings store, never calls [`crate::sidecar::set_supervision`], and
//! finding a working Python does not switch anything on by itself. The
//! settings page still requires a separate, explicit Save — exactly as it
//! does for a path typed in by hand.
//!
//! ## Search order
//!
//! 1. **The `py` launcher** (`py -3`) — Python's own tool for "which
//!    interpreter is that", and on PATH by default once "Install launcher
//!    for all users" was ticked during setup. The most reliable of the
//!    three, because it is not guessing at a filesystem layout at all.
//! 2. **`python.exe` / `python3.exe` on PATH.**
//! 3. **The two folders CPython's own installer uses without being asked**:
//!    `%LocalAppData%\Programs\Python\Python3*\python.exe` (a per-user
//!    install) and `%ProgramFiles%\Python3*\python.exe` (an all-users one).
//!
//! Every candidate is *run*, never just found to exist: a stale shortcut, a
//! half-removed install, and the Microsoft Store's `python.exe` alias
//! (`sidecar.rs`'s module doc, `docs/INSTALL.md` §1.1/2.5) all look
//! identical to a plain file check, and the Store one in particular can pop
//! a Store window and then never answer at all — which is why every probe
//! below is bounded by [`PROBE_TIMEOUT`] rather than left to `Command::output`'s
//! unbounded wait.
//!
//! The probe itself is the exact command `settings.html`'s own hint already
//! tells the owner to run by hand — `-c "import sys; print(sys.executable)"`
//! — extended by two lines to also print the version, so one child process
//! answers both "does this work" and "which Python 3.x is it" at once.
//!
//! ## What is genuinely untested here
//!
//! This dev container is Linux; the search and the subprocess probe are
//! fundamentally Windows-filesystem and Windows-process behaviour, so
//! neither has run against a real Windows machine from this session. The
//! pure logic — which folders count as a Python install, in what order, and
//! how a probe's output is read — is covered by ordinary unit tests below,
//! including the search algorithm itself against a stubbed prober. The
//! `cmd.exe`-based test of the actual subprocess plumbing is real, but only
//! executes on CI's Windows runner, not here.

use std::ffi::OsStr;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use serde::Serialize;

/// How long a single candidate gets to answer before it is abandoned as
/// broken. Generous for a cold interpreter start; short enough that a
/// wedged Store alias cannot hang the button for long.
const PROBE_TIMEOUT: Duration = Duration::from_secs(4);

/// The exact question asked of every candidate: its major and minor version,
/// each on their own line, then the real path it is actually running from
/// (`sys.executable` — for the `py` launcher and a bare `python` on PATH,
/// this is the only way to turn "something answered" into a concrete path
/// worth saving; for a well-known folder it is usually the same path back).
const VERSION_SCRIPT: &str =
    "import sys; print(sys.version_info[0]); print(sys.version_info[1]); print(sys.executable)";

/// One way of trying to reach an interpreter.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Lookup {
    /// A bare name, resolved by the OS the same way a terminal would (PATH,
    /// or on Windows the App Paths registry) — never a path Rust built
    /// itself.
    Named { program: String, args: Vec<String> },
    /// A full path this search already found on disk.
    Known(PathBuf),
}

/// A [`Lookup`] plus plain words for where it came from, for the settings
/// screen's "technical detail" and the hint if nothing is found.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Candidate {
    lookup: Lookup,
    source: &'static str,
}

/// What "Find it for me" offers back — either a working interpreter, or
/// nothing, with a plain-words hint for what to do next.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FindPythonResult {
    pub found: bool,
    /// Only set when `found`.
    pub path: Option<String>,
    /// "3.12", for example. Only set when `found`.
    pub version: Option<String>,
    /// Where it was found, in plain words (e.g. "the `py` launcher"). Only
    /// set when `found`.
    pub source: Option<String>,
    /// Only set when NOT found: a one-line pointer to where to look by hand.
    pub hint: Option<String>,
}

/// Said when every candidate failed. Mirrors `settings.html`'s own
/// `#program-hint`, so the owner sees the same words whichever route they
/// take.
const NOT_FOUND_HINT: &str =
    "Couldn't find a working Python 3 on this PC. It's usually installed under \
     Programs\\Python in your user folder — or get it from python.org and tick \
     \"Add python.exe to PATH\" during setup.";

// ---------------------------------------------------------------------------
// Search order
// ---------------------------------------------------------------------------

/// The three PATH-resolved names to try, in order — see the module doc.
fn named_candidates() -> Vec<Candidate> {
    vec![
        Candidate {
            lookup: Lookup::Named {
                program: "py".to_string(),
                args: vec!["-3".to_string()],
            },
            source: "the `py` launcher",
        },
        Candidate {
            lookup: Lookup::Named {
                program: "python".to_string(),
                args: Vec::new(),
            },
            source: "`python` on PATH",
        },
        Candidate {
            lookup: Lookup::Named {
                program: "python3".to_string(),
                args: Vec::new(),
            },
            source: "`python3` on PATH",
        },
    ]
}

/// Which of `entries` (subfolder names directly under `base`) are a CPython
/// install folder, as `<base>/<entry>/python.exe`, newest first.
///
/// A folder counts if its name is `python` (any case) followed by nothing
/// but ASCII digits — `Python312`, `Python39`, `python27`. Nothing here
/// checks the *version* those digits name: `python27` passes this filter
/// exactly like `Python312` does, and is rejected later, at the probe, the
/// same way a broken `Python312` folder would be. Sorting on the digits
/// alone is enough to try the newest-looking one first without needing to
/// understand what the digits mean.
fn python_subfolders(base: &Path, entries: &[String]) -> Vec<PathBuf> {
    let mut named: Vec<(u32, &String)> = entries
        .iter()
        .filter_map(|name| {
            let digits = name
                .to_ascii_lowercase()
                .strip_prefix("python")?
                .to_string();
            if digits.is_empty() || !digits.chars().all(|c| c.is_ascii_digit()) {
                return None;
            }
            digits.parse::<u32>().ok().map(|n| (n, name))
        })
        .collect();
    named.sort_by(|a, b| b.0.cmp(&a.0));
    named
        .into_iter()
        .map(|(_, name)| base.join(name).join("python.exe"))
        .collect()
}

/// Subfolder names directly under `dir`, or empty if it cannot be read (it
/// does not exist, or is not a folder at all — both ordinary, since these
/// two base folders are guesses, not requirements).
fn list_subdirs(dir: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    entries
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().is_dir())
        .filter_map(|entry| entry.file_name().to_str().map(str::to_string))
        .collect()
}

/// The well-known install folders, expanded from the environment — empty
/// wherever the variable is unset (never the case on real Windows, always
/// the case in this Linux dev container, which is fine: it just means those
/// two candidates contribute nothing here).
fn known_path_candidates() -> Vec<Candidate> {
    let mut out = Vec::new();
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        let base = Path::new(&local_app_data).join("Programs").join("Python");
        for path in python_subfolders(&base, &list_subdirs(&base)) {
            out.push(Candidate {
                lookup: Lookup::Known(path),
                source: "found under Programs\\Python in your user folder",
            });
        }
    }
    if let Ok(program_files) = std::env::var("ProgramFiles") {
        let base = PathBuf::from(program_files);
        for path in python_subfolders(&base, &list_subdirs(&base)) {
            out.push(Candidate {
                lookup: Lookup::Known(path),
                source: "found under Program Files",
            });
        }
    }
    out
}

/// Every place worth trying, in the order they should be tried.
fn search_order() -> Vec<Candidate> {
    let mut out = named_candidates();
    out.extend(known_path_candidates());
    out
}

// ---------------------------------------------------------------------------
// Probing (real subprocess work)
// ---------------------------------------------------------------------------

/// Runs `program args...`, waits up to [`PROBE_TIMEOUT`], and returns its
/// combined stdout and stderr. Killed and reported as an error if it does not
/// finish in time — see the module doc for why that matters here specifically.
fn run_and_capture<S: AsRef<OsStr>>(program: S, args: &[String]) -> Result<String, String> {
    use std::io::Read;

    let program_name = program.as_ref().to_string_lossy().to_string();
    let mut command = Command::new(program);
    command.args(args);
    command.stdin(Stdio::null());
    command.stdout(Stdio::piped());
    command.stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // Same flag and the same reason `commands.rs`'s GPU probe uses it: a
        // release build has no console, so without this a child that DOES
        // have one flashes a window — on a button click, not a background
        // timer, but still worth suppressing.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command
        .spawn()
        .map_err(|e| format!("could not run `{program_name}`: {e}"))?;

    let deadline = Instant::now() + PROBE_TIMEOUT;
    loop {
        match child.try_wait() {
            Ok(Some(_status)) => break,
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(format!(
                        "`{program_name}` did not answer within {}s",
                        PROBE_TIMEOUT.as_secs()
                    ));
                }
                std::thread::sleep(Duration::from_millis(25));
            }
            Err(e) => return Err(format!("could not check `{program_name}`: {e}")),
        }
    }

    let mut out = String::new();
    if let Some(mut pipe) = child.stdout.take() {
        let _ = pipe.read_to_string(&mut out);
    }
    let mut err = String::new();
    if let Some(mut pipe) = child.stderr.take() {
        let _ = pipe.read_to_string(&mut err);
    }
    if out.trim().is_empty() && !err.trim().is_empty() {
        // A real interpreter answers `-c` on stdout; something on stderr and
        // nothing on stdout is more useful reported than dropped.
        return Err(err.trim().to_string());
    }
    Ok(out)
}

/// Reads a [`VERSION_SCRIPT`] answer: `major\nminor\nexecutable\n`. Pure —
/// no process, no filesystem — so it is tested directly against strings.
fn parse_probe_output(output: &str) -> Result<(u32, u32, PathBuf), String> {
    let mut lines = output.lines();
    let major = lines
        .next()
        .and_then(|l| l.trim().parse::<u32>().ok())
        .ok_or_else(|| "did not print a usable version".to_string())?;
    let minor = lines
        .next()
        .and_then(|l| l.trim().parse::<u32>().ok())
        .ok_or_else(|| "did not print a usable version".to_string())?;
    let exe = lines
        .next()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "did not print where it lives".to_string())?;
    if major != 3 {
        return Err(format!("found Python {major}.{minor}, not Python 3"));
    }
    Ok((major, minor, PathBuf::from(exe)))
}

/// Runs a [`Lookup`] and checks its answer — the real, impure half of a
/// candidate. `search_with` below is the pure half, tested on its own with
/// a stubbed version of this function.
fn probe_lookup(lookup: &Lookup) -> Result<(u32, u32, PathBuf), String> {
    let output = match lookup {
        Lookup::Named { program, args } => {
            let mut full_args = args.clone();
            full_args.push("-c".to_string());
            full_args.push(VERSION_SCRIPT.to_string());
            run_and_capture(program, &full_args)?
        }
        Lookup::Known(path) => {
            run_and_capture(path, &["-c".to_string(), VERSION_SCRIPT.to_string()])?
        }
    };
    parse_probe_output(&output)
}

// ---------------------------------------------------------------------------
// The search algorithm — pure, tested apart from any process or filesystem
// ---------------------------------------------------------------------------

/// What "Find it for me" found, ready to show or to drop into the `Program`
/// field.
#[derive(Debug, Clone, PartialEq, Eq)]
struct FoundPython {
    path: String,
    major: u32,
    minor: u32,
    source: &'static str,
}

/// Tries each candidate in order and returns the first whose probe succeeds.
/// Generic over the prober so the ordering and stop-at-first-success logic
/// can be checked with a stub, with no real process or filesystem involved.
fn search_with<F>(candidates: &[Candidate], mut prober: F) -> Option<FoundPython>
where
    F: FnMut(&Lookup) -> Result<(u32, u32, PathBuf), String>,
{
    for candidate in candidates {
        if let Ok((major, minor, path)) = prober(&candidate.lookup) {
            return Some(FoundPython {
                path: path.display().to_string(),
                major,
                minor,
                source: candidate.source,
            });
        }
    }
    None
}

/// The real search: every candidate in [`search_order`], checked for real.
fn search_installed_pythons() -> Option<FoundPython> {
    search_with(&search_order(), probe_lookup)
}

// ---------------------------------------------------------------------------
// Tauri command
// ---------------------------------------------------------------------------

/// "Find it for me": searches this PC for a working Python 3 interpreter.
///
/// Read-only and side-effect free — it writes nothing to the settings
/// store and never touches supervision's on/off switch (`sidecar.rs` §5,
/// CLAUDE.md). The settings page decides what to do with the answer: fill
/// the `Program` field and let the owner still confirm it with Save, or,
/// if nothing was found, show [`NOT_FOUND_HINT`] instead.
///
/// Runs on a blocking worker, like [`crate::commands::capture_screen`]: the
/// search can spawn up to five child processes, each with its own
/// [`PROBE_TIMEOUT`], and none of that should be able to stall the app's
/// message loop.
#[tauri::command]
pub async fn find_python() -> Result<FindPythonResult, String> {
    tauri::async_runtime::spawn_blocking(|| {
        Ok(match search_installed_pythons() {
            Some(python) => FindPythonResult {
                found: true,
                path: Some(python.path),
                version: Some(format!("{}.{}", python.major, python.minor)),
                source: Some(python.source.to_string()),
                hint: None,
            },
            None => FindPythonResult {
                found: false,
                path: None,
                version: None,
                source: None,
                hint: Some(NOT_FOUND_HINT.to_string()),
            },
        })
    })
    .await
    .map_err(|e| format!("the search could not finish: {e}"))?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_only_python_n_folders_newest_first() {
        let base = Path::new("C:/Users/you/AppData/Local/Programs/Python");
        let entries = vec![
            "Python39".to_string(),
            "Python312".to_string(),
            "PythonLauncher".to_string(), // not all digits after "python" - excluded
            "Scripts".to_string(),        // does not start with "python" at all
            "python27".to_string(),       // different case, still matches the pattern
        ];
        let found = python_subfolders(base, &entries);
        assert_eq!(
            found,
            vec![
                base.join("Python312").join("python.exe"),
                base.join("Python39").join("python.exe"),
                base.join("python27").join("python.exe"),
            ]
        );
    }

    #[test]
    fn empty_or_unrelated_folder_list_finds_nothing() {
        let base = Path::new("C:/whatever");
        assert!(python_subfolders(base, &[]).is_empty());
        assert!(python_subfolders(base, &["Scripts".to_string(), "Lib".to_string()]).is_empty());
    }

    #[test]
    fn parses_a_real_python_3_answer() {
        let (major, minor, exe) = parse_probe_output("3\n12\nC:\\Python312\\python.exe\n").unwrap();
        assert_eq!((major, minor), (3, 12));
        assert_eq!(exe, PathBuf::from("C:\\Python312\\python.exe"));
    }

    #[test]
    fn rejects_python_2() {
        let err = parse_probe_output("2\n7\nC:\\Python27\\python.exe\n").unwrap_err();
        assert!(err.contains("Python 2.7"), "unexpected message: {err}");
    }

    #[test]
    fn rejects_output_that_is_not_the_expected_three_lines() {
        assert!(parse_probe_output("").is_err());
        assert!(parse_probe_output("not a number\n12\nC:\\x\\python.exe").is_err());
        assert!(parse_probe_output("3\n12\n").is_err()); // no path line at all
        assert!(parse_probe_output("3\n12\n   \n").is_err()); // blank path line
    }

    /// The algorithm's own logic - stop at the first success, in order,
    /// `None` only when every candidate failed - checked with a stub prober
    /// so no process or filesystem is involved.
    #[test]
    fn search_stops_at_the_first_candidate_that_answers() {
        let candidates = vec![
            Candidate {
                lookup: Lookup::Named {
                    program: "py".to_string(),
                    args: vec!["-3".to_string()],
                },
                source: "the `py` launcher",
            },
            Candidate {
                lookup: Lookup::Named {
                    program: "python".to_string(),
                    args: Vec::new(),
                },
                source: "`python` on PATH",
            },
            Candidate {
                lookup: Lookup::Known(PathBuf::from("C:/Python312/python.exe")),
                source: "found under Programs\\Python in your user folder",
            },
        ];

        let found = search_with(&candidates, |lookup| match lookup {
            // "py" is missing entirely (no launcher installed).
            Lookup::Named { program, .. } if program == "py" => {
                Err("could not run `py`: not found".to_string())
            }
            // Bare `python` answers, but as the Store alias would: nothing
            // usable, so it should be skipped rather than accepted.
            Lookup::Named { program, .. } if program == "python" => {
                Err("did not answer within 4s".to_string())
            }
            // The known folder is a real, working Python 3.12.
            Lookup::Known(path) => Ok((3, 12, path.clone())),
            _ => panic!("search_with reached a candidate it should have stopped before"),
        });

        assert_eq!(
            found,
            Some(FoundPython {
                path: "C:/Python312/python.exe".to_string(),
                major: 3,
                minor: 12,
                source: "found under Programs\\Python in your user folder",
            })
        );
    }

    #[test]
    fn search_returns_none_when_every_candidate_fails() {
        let candidates = named_candidates();
        let found = search_with(&candidates, |_| Err("nope".to_string()));
        assert_eq!(found, None);
    }

    #[test]
    fn search_prefers_an_earlier_success_over_a_later_one() {
        // Both candidates would succeed; the first in the list must win, so
        // the `py` launcher is trusted over a later PATH guess even when
        // both happen to work.
        let candidates = vec![
            Candidate {
                lookup: Lookup::Named {
                    program: "py".to_string(),
                    args: vec!["-3".to_string()],
                },
                source: "the `py` launcher",
            },
            Candidate {
                lookup: Lookup::Named {
                    program: "python3".to_string(),
                    args: Vec::new(),
                },
                source: "`python3` on PATH",
            },
        ];
        let found = search_with(&candidates, |lookup| match lookup {
            Lookup::Named { program, .. } if program == "py" => {
                Ok((3, 12, PathBuf::from("C:/Python312/python.exe")))
            }
            _ => Ok((3, 9, PathBuf::from("C:/Other/python3.exe"))),
        });
        assert_eq!(found.unwrap().source, "the `py` launcher");
    }

    /// The real subprocess plumbing, exercised for real - but only on
    /// Windows, and only where `cmd.exe` exists, which is every CI runner
    /// this repository builds on (`.github/workflows/ci.yml` runs the Rust
    /// job on `windows-latest`) but not this Linux dev container. It stands
    /// in for a Python interpreter with `cmd /c echo`, so it needs no real
    /// Python installed to prove that spawning, the timeout loop and
    /// reading stdout back all work together correctly.
    #[test]
    #[cfg(windows)]
    fn run_and_capture_reads_a_real_child_processs_stdout() {
        let output = run_and_capture(
            "cmd",
            &[
                "/c".to_string(),
                "echo 3&&echo 12&&echo C:\\Fake\\python.exe".to_string(),
            ],
        )
        .expect("cmd.exe should always be available on a Windows runner");
        let (major, minor, exe) = parse_probe_output(&output).unwrap();
        assert_eq!((major, minor), (3, 12));
        assert_eq!(exe, PathBuf::from("C:\\Fake\\python.exe"));
    }

    #[test]
    #[cfg(windows)]
    fn run_and_capture_reports_a_program_that_does_not_exist() {
        let err = run_and_capture(
            "this-program-does-not-exist-anywhere.exe",
            &["-3".to_string()],
        )
        .unwrap_err();
        assert!(err.contains("could not run"), "unexpected message: {err}");
    }
}
