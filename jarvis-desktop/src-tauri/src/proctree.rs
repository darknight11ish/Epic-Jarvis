//! Killing the process tree rather than the process.
//!
//! DESKTOP-BUILD §5 is blunt about why this file is not a call to
//! `Child::kill()`:
//!
//! > Tauri does not kill the child when the app exits. This is a known,
//! > unresolved gap… Worse for this app specifically: the Python backend spawns
//! > children of its own, so a plain `child.kill()` can leave **grandchildren**
//! > running — a model still pinned in VRAM, with no window anywhere to tell
//! > you about it.
//!
//! It also names the mechanism: "On Windows that means a Job Object; on Unix a
//! process group." Both are implemented here, directly against the platform,
//! with no community plugin in the middle — §5 says to say so in the code if
//! one is used, and the honest way to satisfy that is not to use one.
//!
//! ## The race this avoids
//!
//! Creating the child and *then* assigning it to a job leaves a window in which
//! the child can spawn a grandchild that is outside the job — which is exactly
//! the process this exists to catch. So the child is created suspended, put in
//! the job while it cannot run, and only then resumed. It has executed no
//! instructions before it is inside the job.
//!
//! Resuming needs the main thread's handle, and `std::process::Child` does not
//! expose one. Enumerating the process's threads through a ToolHelp snapshot
//! and resuming each is the documented way to get it back, and it costs less
//! than reimplementing `CreateProcess` — whose argument quoting `std` already
//! gets right, and which is not a thing to reimplement casually.

use std::process::{Child, Command};

/// A handle that kills everything under it when it is dropped or terminated.
pub struct ProcessTree {
    #[cfg(windows)]
    job: windows_sys::Win32::Foundation::HANDLE,
    #[cfg(not(windows))]
    group: i32,
}

// The Windows HANDLE is a raw pointer, which is not `Send` by default. A job
// object handle is a kernel object usable from any thread in the process, and
// this one is only ever created, assigned to, terminated and closed — never
// dereferenced. Moving it to the task that supervises the child is safe.
#[cfg(windows)]
unsafe impl Send for ProcessTree {}
#[cfg(windows)]
unsafe impl Sync for ProcessTree {}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

#[cfg(windows)]
mod platform {
    use super::*;
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD, THREADENTRY32,
    };
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, TerminateJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        OpenThread, ResumeThread, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, CREATE_SUSPENDED,
        THREAD_SUSPEND_RESUME,
    };

    /// Spawns `command` inside a fresh job object.
    ///
    /// Three creation flags, each for a reason:
    ///
    /// * `CREATE_SUSPENDED` — so the child is in the job before it runs. See
    ///   the module docs.
    /// * `CREATE_NO_WINDOW` — the backend is a Python console program, and
    ///   without this a console window appears behind the GUI.
    /// * `CREATE_NEW_PROCESS_GROUP` — so a Ctrl-C in whatever launched the
    ///   desktop app is not also delivered to the backend.
    pub fn spawn(command: &mut Command) -> std::io::Result<(Child, ProcessTree)> {
        // SAFETY: CreateJobObjectW with two nulls asks for an unnamed job with
        // default security, and returns null on failure — which is checked.
        let job: HANDLE = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if job.is_null() {
            return Err(std::io::Error::last_os_error());
        }
        let tree = ProcessTree { job };

        // KILL_ON_JOB_CLOSE is the part that makes this survive us: if the
        // desktop process dies without unwinding — a crash, a Task Manager
        // "End task" — Windows closes our handles, the job's last handle
        // closes, and the backend and everything it started go with it.
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        // SAFETY: `limits` is a correctly-typed, fully-initialised value of the
        // struct this information class expects, and the size matches.
        let set = unsafe {
            SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                std::ptr::addr_of!(limits).cast(),
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if set == 0 {
            return Err(std::io::Error::last_os_error());
        }

        let child = command
            .creation_flags(CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
            .spawn()?;

        // SAFETY: the handle comes from a live `Child` we own, so it is valid
        // for the duration of this call.
        let assigned = unsafe { AssignProcessToJobObject(job, child.as_raw_handle() as HANDLE) };
        if assigned == 0 {
            let err = std::io::Error::last_os_error();
            // The child exists but is suspended and outside the job. Leaving it
            // frozen for ever would be worse than any of this; kill it.
            let mut child = child;
            let _ = child.kill();
            return Err(err);
        }

        resume(child.id())?;
        Ok((child, tree))
    }

    /// Resumes every thread belonging to `pid` — for a freshly created
    /// suspended process that is exactly one, its main thread.
    fn resume(pid: u32) -> std::io::Result<()> {
        // SAFETY: a thread snapshot of the whole system; the handle is checked
        // and closed on every path below.
        let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
        if snapshot == INVALID_HANDLE_VALUE || snapshot.is_null() {
            return Err(std::io::Error::last_os_error());
        }

        let mut entry: THREADENTRY32 = unsafe { std::mem::zeroed() };
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;

        let mut resumed = 0usize;
        // SAFETY: `entry` is sized as the API requires; iteration stops when
        // Thread32Next reports no more entries.
        let mut ok = unsafe { Thread32First(snapshot, &mut entry) } != 0;
        while ok {
            if entry.th32OwnerProcessID == pid {
                // SAFETY: opening a thread we just created, for the one right
                // we need; the handle is closed immediately after use.
                let thread = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID) };
                if !thread.is_null() {
                    unsafe {
                        ResumeThread(thread);
                        CloseHandle(thread);
                    }
                    resumed += 1;
                }
            }
            entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
            ok = unsafe { Thread32Next(snapshot, &mut entry) } != 0;
        }
        unsafe { CloseHandle(snapshot) };

        if resumed == 0 {
            // The process is in the job but frozen, which is the one outcome
            // that must not be reported as success.
            return Err(std::io::Error::other(
                "the backend was created suspended and no thread could be resumed",
            ));
        }
        Ok(())
    }

    impl ProcessTree {
        /// Terminates every process in the job, children and grandchildren.
        pub fn kill(&self) {
            // SAFETY: `self.job` is a live job handle owned by this value.
            unsafe { TerminateJobObject(self.job, 1) };
        }
    }

    impl Drop for ProcessTree {
        fn drop(&mut self) {
            // Closing the last handle to a KILL_ON_JOB_CLOSE job kills whatever
            // is still in it, so this is both cleanup and a backstop.
            // SAFETY: the handle is owned by this value and closed once.
            unsafe { CloseHandle(self.job) };
        }
    }
}

// ---------------------------------------------------------------------------
// Unix
// ---------------------------------------------------------------------------

#[cfg(not(windows))]
mod platform {
    use super::*;
    use std::os::unix::process::CommandExt;

    /// Spawns `command` as the leader of a new process group.
    ///
    /// The product is a Windows app and this path exists so the crate builds
    /// and tests on a developer machine; it has not been exercised against the
    /// real backend. `process_group(0)` makes the child its own group leader,
    /// so its children inherit the group and one `killpg` reaches all of them.
    pub fn spawn(command: &mut Command) -> std::io::Result<(Child, ProcessTree)> {
        let child = command.process_group(0).spawn()?;
        let group = child.id() as i32;
        Ok((child, ProcessTree { group }))
    }

    impl ProcessTree {
        pub fn kill(&self) {
            if self.group <= 0 {
                return;
            }
            // SAFETY: killpg on a group this process created. A group that has
            // already exited returns ESRCH, which is not an error here.
            unsafe { libc::killpg(self.group, libc::SIGKILL) };
        }
    }
}

pub use platform::spawn;

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    /// Is this pid alive? `kill(pid, 0)` performs the permission and existence
    /// checks without sending anything.
    fn alive(pid: i32) -> bool {
        // SAFETY: signal 0 is the documented existence probe and sends nothing.
        unsafe { libc::kill(pid, 0) == 0 }
    }

    /// The whole point of the file: a plain kill of the child leaves the
    /// grandchild running, and this must not.
    ///
    /// Runs on Unix because that is the platform this repository can execute
    /// on. The Windows path is the same shape — the grandchild is inside the
    /// job because the child was in it before it ran — but it is exercised by
    /// the compiler here and by Windows nowhere yet.
    #[test]
    fn kills_grandchildren_not_just_the_child() {
        let dir = std::env::temp_dir().join(format!("jarvis-proctree-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let marker = dir.join("grandchild.pid");

        // A child that spawns a grandchild and then waits, which is the shape
        // of the Python backend: the thing we launch is not the thing holding
        // the GPU.
        let script = dir.join("parent.sh");
        std::fs::write(
            &script,
            format!(
                "#!/bin/sh\nsleep 300 &\necho $! > {}\nsleep 300\n",
                marker.display()
            ),
        )
        .unwrap();

        let mut command = Command::new("/bin/sh");
        command.arg(&script);
        let (mut child, tree) = spawn(&mut command).expect("spawn");

        // Wait for the grandchild to exist.
        let deadline = Instant::now() + Duration::from_secs(5);
        let grandchild = loop {
            if let Ok(text) = std::fs::read_to_string(&marker) {
                if let Ok(pid) = text.trim().parse::<i32>() {
                    break pid;
                }
            }
            assert!(Instant::now() < deadline, "the grandchild never started");
            std::thread::sleep(Duration::from_millis(50));
        };
        assert!(alive(grandchild), "the grandchild should be running");

        tree.kill();

        let deadline = Instant::now() + Duration::from_secs(5);
        while alive(grandchild) && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(50));
        }
        let _ = child.wait();
        assert!(
            !alive(grandchild),
            "killing the tree left the grandchild ({grandchild}) running"
        );

        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The child really is in its own process group, which is what makes one
    /// `killpg` reach everything it starts.
    #[test]
    fn child_leads_its_own_process_group() {
        let mut command = Command::new("/bin/sh");
        command.arg("-c").arg("sleep 5");
        let (mut child, tree) = spawn(&mut command).expect("spawn");
        let pid = child.id() as i32;
        // SAFETY: reading the group of a process we own.
        let group = unsafe { libc::getpgid(pid) };
        assert_eq!(group, pid, "the child should lead its own group");
        assert_ne!(group, unsafe { libc::getpgid(0) }, "not our own group");
        tree.kill();
        let _ = child.wait();
    }
}
