//! "Jarvis is working on your screen, 0:42 - Stop" (owner's choice,
//! 2026-09-28; docs/RESEARCH-AUDIT-2026-09-28.md idea 17).
//!
//! While an approved Windows screen-control plan runs (`control_computer`,
//! backend `jarvis_ui_control.run`), the widget shows one line with how long
//! it has been going and a Stop button. The button is the same Stop as the
//! "Stop everything" hotkey and the tray item (commands.rs
//! `stop_everything_now`) - not a new, second way of stopping.
//!
//! Where "a plan is running" comes from: `GET /api/task`
//! (backend `jarvis_task_control.status()`), whose `running` list is filled
//! by `begin()` just before a plan's first step and emptied by `end()` the
//! moment `run()` returns, however it ended. So the line shows only while a
//! plan really runs - not while its approval card waits, not after it
//! finished, and not while it is paused (a paused plan is not running; the
//! widget's own task controls offer Resume then). That route carries tool
//! names, ids and times only - never a step's wording or a window's title -
//! so nothing private reaches the widget, which sits outside App lock.
//!
//! The widget asks only while the event stream says Jarvis is `working`
//! (widget.js), so an idle Jarvis costs no requests at all.

use serde::Serialize;
use tauri::AppHandle;

use crate::commands;

/// The backend's tool name for a Windows screen-control plan
/// (backend `jarvis_agent._TASK_MODULES`). Phone control and browser
/// control are other tools, and other lines if they ever get one.
pub const SCREEN_TOOL: &str = "control_computer";

/// A clock further out than this - either way - is not trusted: the
/// backend's `started` is its own clock, and a backend on another machine
/// (over Tailscale) may disagree with this one. The widget then counts from
/// when it first saw the plan instead.
const TRUSTED_SKEW_SECONDS: f64 = 12.0 * 3600.0;

/// A plan started this far "in the future" is a small clock difference
/// between two machines, counted as just started.
const SMALL_SKEW_SECONDS: f64 = 5.0;

/// What the widget needs to draw the line.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ScreenWork {
    /// A screen-control plan is running now.
    pub running: bool,
    /// Its task id, so the widget can tell one plan from the next.
    pub id: Option<String>,
    /// How long it has been running, when the backend's clock can be
    /// trusted for that. `None` means "count from now".
    pub elapsed_ms: Option<u64>,
}

impl ScreenWork {
    fn none() -> Self {
        ScreenWork {
            running: false,
            id: None,
            elapsed_ms: None,
        }
    }
}

/// Reads `GET /api/task`'s answer. `now` is this machine's clock, in
/// seconds since 1970, the unit the backend's `started` uses.
pub fn read_running(task: &serde_json::Value, now: f64) -> ScreenWork {
    let Some(entry) = task
        .get("running")
        .and_then(|r| r.as_array())
        .and_then(|list| {
            list.iter()
                .find(|e| e.get("tool").and_then(|t| t.as_str()) == Some(SCREEN_TOOL))
        })
    else {
        return ScreenWork::none();
    };
    let id = entry.get("id").and_then(|i| i.as_str()).map(str::to_string);
    let elapsed_ms = entry
        .get("started")
        .and_then(|s| s.as_f64())
        .filter(|s| s.is_finite())
        .map(|started| now - started)
        .filter(|d| (-SMALL_SKEW_SECONDS..=TRUSTED_SKEW_SECONDS).contains(d))
        .map(|d| (d.max(0.0) * 1000.0) as u64);
    ScreenWork {
        running: true,
        id,
        elapsed_ms,
    }
}

/// Whether a screen-control plan is running, and for how long.
///
/// A backend without the task routes (404) is simply "nothing running" -
/// it cannot run a plan that Stop would reach through them either. Any
/// other failure is an error, and the widget keeps what it last knew until
/// the event stream says Jarvis stopped working.
#[tauri::command]
pub async fn screen_work(app: AppHandle) -> Result<ScreenWork, String> {
    const PATH: &str = "/api/task";
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(std::time::Duration::from_secs(5)))?
        .get(format!("{base}{PATH}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status();
    if status.as_u16() == 404 {
        return Ok(ScreenWork::none());
    }
    if !status.is_success() {
        return Err(format!(
            "the server answered HTTP {} to {PATH}",
            status.as_u16()
        ));
    }
    let body: serde_json::Value = response
        .json()
        .await
        .map_err(|_| format!("the server's answer to {PATH} could not be read"))?;
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    Ok(read_running(&body, now))
}

/// The line's Stop button: exactly the "Stop everything" hotkey. Stops
/// speech here first, then asks the PC to stop the running plan and
/// everything else, and says what was stopped in a notification.
///
/// Never held - not on a stale stream, not by App lock, not by a waiting
/// card - for the reasons `stop_everything_now` gives: it approves nothing
/// and starts nothing.
#[tauri::command]
pub fn stop_everything(app: AppHandle) {
    commands::stop_everything_now(&app);
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const NOW: f64 = 1_790_000_000.0;

    #[test]
    fn nothing_running_is_no_line() {
        let got = read_running(
            &json!({"available": true, "running": [], "paused": null}),
            NOW,
        );
        assert_eq!(got, ScreenWork::none());
        assert_eq!(read_running(&json!({}), NOW), ScreenWork::none());
        assert_eq!(read_running(&json!(null), NOW), ScreenWork::none());
    }

    #[test]
    fn a_screen_plan_shows_with_its_time() {
        let got = read_running(
            &json!({"running": [{"id": "task_ab12", "tool": "control_computer", "started": NOW - 42.5}]}),
            NOW,
        );
        assert!(got.running);
        assert_eq!(got.id.as_deref(), Some("task_ab12"));
        assert_eq!(got.elapsed_ms, Some(42_500));
    }

    #[test]
    fn phone_and_browser_plans_are_not_the_screen() {
        let got = read_running(
            &json!({"running": [
                {"id": "a", "tool": "control_phone", "started": NOW - 5.0},
                {"id": "b", "tool": "browser_control", "started": NOW - 5.0}
            ]}),
            NOW,
        );
        assert!(!got.running);
    }

    #[test]
    fn the_screen_plan_is_found_among_others() {
        let got = read_running(
            &json!({"running": [
                {"id": "a", "tool": "control_phone", "started": NOW - 5.0},
                {"id": "b", "tool": "control_computer", "started": NOW - 3.0}
            ]}),
            NOW,
        );
        assert_eq!(got.id.as_deref(), Some("b"));
        assert_eq!(got.elapsed_ms, Some(3_000));
    }

    #[test]
    fn a_clock_that_disagrees_is_not_trusted() {
        // Another machine's clock a day off: count from now instead.
        let far = read_running(
            &json!({"running": [{"id": "a", "tool": "control_computer", "started": NOW - 86_400.0 * 2.0}]}),
            NOW,
        );
        assert!(far.running);
        assert_eq!(far.elapsed_ms, None);
        let future = read_running(
            &json!({"running": [{"id": "a", "tool": "control_computer", "started": NOW + 600.0}]}),
            NOW,
        );
        assert_eq!(future.elapsed_ms, None);
        // A second or two ahead is "just started".
        let slight = read_running(
            &json!({"running": [{"id": "a", "tool": "control_computer", "started": NOW + 2.0}]}),
            NOW,
        );
        assert_eq!(slight.elapsed_ms, Some(0));
    }

    #[test]
    fn a_missing_start_time_still_shows_the_line() {
        let got = read_running(
            &json!({"running": [{"id": "a", "tool": "control_computer"}]}),
            NOW,
        );
        assert!(got.running);
        assert_eq!(got.elapsed_ms, None);
    }
}
