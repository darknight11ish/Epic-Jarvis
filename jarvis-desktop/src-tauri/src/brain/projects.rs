//! Brain -> Projects (the owner's decision of 2026-09-28, "Projects, like
//! Claude's Projects and more"; docs/PROJECTS-DESIGN.md build step 3;
//! backend/jarvis_projects.py, projects.patch; JARVIS-API.md section 61).
//!
//! Three commands, Brain window only (permissions/surfaces.toml,
//! `brain-projects`):
//!
//! * [`projects_read`] - `GET /api/projects`, one project, or one
//!   benchmark with its chart points. A read, never held. While "Windows
//!   Hello for memory lists and chat history" (lock.rs) hides the Brain's
//!   private lists, the answer comes back hidden here in Rust (only how many
//!   projects there are is kept): a project's instructions and its health or
//!   money numbers are the owner's private things, like Coming up's words.
//! * [`projects_write`] - ONE change, named by an action from a fixed list
//!   (the page never names a URL): create, edit, delete a project; the
//!   Shareable switch; add, edit, delete a benchmark; log or remove one
//!   number; take a private mark off. The PC decides which of them raise a
//!   card (Shareable ON, and taking off a mark Jarvis made itself - one
//!   `change_own_config` card each); none is decided here. Every change is
//!   held while the event stream is stale (rule 4) - it acts on a project
//!   the window drew from a read that may be old - except Shareable OFF,
//!   which only lets less out (like removing a folder).
//! * [`projects_choose_folder`] - a coding project's folder: the Windows
//!   folder picker (the one "Folders Jarvis may look in" uses), then the
//!   chosen path to this PC's Jarvis, which accepts only a folder on that
//!   list or inside one. The PC only: the phone has no view of the PC's
//!   folders, and the PC refuses the folder from any other device. Held on
//!   a stale link, before the picker opens: it lets Jarvis see more.
//!
//! The answer-reading functions are plain functions of (status, body), so
//! their tests run against the real answers (`tests/fixtures/
//! projects-cases.json`, made by tools/gen_projects_cases.py) without a
//! Tauri app or a network.

use tauri::{AppHandle, Manager};

use super::{READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

pub(crate) const PROJECTS_PATH: &str = "/api/projects";

/// A PC without `jarvis_projects.py` / `projects.patch`. The phone says the
/// same (`Projects.MISSING`), and so does projects.js - all three from the
/// contract file's `words.missing`.
pub(crate) const PROJECTS_MISSING: &str =
    "Your PC's Jarvis does not have Projects yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// A folder is chosen with the picker, never typed into a change.
const FOLDER_BY_PICKER: &str = "Choose the folder with \"Choose a folder…\".";

/// Every change this window may ask for, and the route it goes to. Nothing
/// else can be sent: the page names one of these, never a path.
pub(crate) const ACTIONS: &[&str] = &[
    "create",
    "update",
    "delete",
    "shareable",
    "bench_add",
    "bench_update",
    "bench_delete",
    "log",
    "result_delete",
    "unmark",
];

/// A project, benchmark or number id: 32 lower-case hex digits, exactly what
/// jarvis_projects makes. Anything else never reaches a URL.
pub(crate) fn is_id(s: &str) -> bool {
    s.len() == 32
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn id<'a>(v: Option<&'a str>, what: &str) -> Result<&'a str, String> {
    match v {
        Some(s) if is_id(s) => Ok(s),
        _ => Err(format!("no such {what}")),
    }
}

/// The GET path for a read: the list, one project, or one benchmark (with
/// how many chart points, at most 1000).
pub(crate) fn read_path(
    project: Option<&str>,
    bench: Option<&str>,
    points: Option<u32>,
) -> Result<String, String> {
    match (project, bench) {
        (None, None) => Ok(PROJECTS_PATH.to_string()),
        (Some(_), None) => Ok(format!("/api/projects/{}", id(project, "project")?)),
        (Some(_), Some(_)) => {
            let n = points.unwrap_or(365).clamp(1, 1000);
            Ok(format!(
                "/api/projects/{}/benchmarks/{}?points={n}",
                id(project, "project")?,
                id(bench, "benchmark")?
            ))
        }
        (None, Some(_)) => Err("no such project".to_string()),
    }
}

/// The POST path for one change.
pub(crate) fn write_path(
    action: &str,
    project: Option<&str>,
    bench: Option<&str>,
    result: Option<&str>,
) -> Result<String, String> {
    if !ACTIONS.contains(&action) {
        return Err(format!("not a projects change: {action}"));
    }
    let p = || id(project, "project");
    let b = || id(bench, "benchmark");
    Ok(match action {
        "create" => PROJECTS_PATH.to_string(),
        "update" => format!("/api/projects/{}", p()?),
        "delete" => format!("/api/projects/{}/delete", p()?),
        "shareable" => format!("/api/projects/{}/shareable", p()?),
        "bench_add" => format!("/api/projects/{}/benchmarks", p()?),
        "bench_update" => format!("/api/projects/{}/benchmarks/{}", p()?, b()?),
        "bench_delete" => format!("/api/projects/{}/benchmarks/{}/delete", p()?, b()?),
        "log" => format!("/api/projects/{}/benchmarks/{}/log", p()?, b()?),
        "result_delete" => format!(
            "{PROJECTS_PATH}/{}/benchmarks/{}/results/{}/delete",
            p()?,
            b()?,
            id(result, "number")?
        ),
        "unmark" => format!("/api/projects/{}/benchmarks/{}/unmark", p()?, b()?),
        _ => return Err(format!("not a projects change: {action}")),
    })
}

/// Whether a change waits for a live event stream: every one does, except
/// Shareable OFF - it only lets less out, like removing a folder.
pub(crate) fn held_on_stale(action: &str, body: &serde_json::Value) -> bool {
    !(action == "shareable" && body.get("on") == Some(&serde_json::Value::Bool(false)))
}

/// The body of a change, checked: a JSON object, and never a folder path
/// typed into it (a folder comes from the picker, [`projects_choose_folder`]).
/// Clearing the folder (`null` or `""`) is allowed - it lets Jarvis see less.
pub(crate) fn checked_body(
    action: &str,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let body = body.unwrap_or_else(|| serde_json::json!({}));
    let Some(obj) = body.as_object() else {
        return Err("send the fields to change".to_string());
    };
    if matches!(action, "create" | "update") {
        if let Some(f) = obj.get("folder") {
            let empty = f.is_null() || f.as_str().is_some_and(|s| s.trim().is_empty());
            if !empty {
                return Err(FOLDER_BY_PICKER.to_string());
            }
        }
    }
    Ok(body)
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A 404 that jarvis_projects itself sent ("no such project, benchmark or
/// number") carries `"ok": false`; a PC without the routes at all does not.
fn projects_404(body: &str) -> bool {
    parsed(body).and_then(|v| v.get("ok").and_then(|o| o.as_bool())) == Some(false)
}

/// [`projects_read`]'s reading of the answer.
///
/// * 2xx - the PC's own body, passed on as it is.
/// * 404 from a PC without the routes - `{"available": false, "why":
///   PROJECTS_MISSING}`, which the page says plainly rather than as an error.
/// * anything else (a 404 that says "no such project") - its own sentence.
pub(crate) fn read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 && !projects_404(body) {
        return Ok(serde_json::json!({ "available": false, "why": PROJECTS_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`projects_write`]'s reading of the answer: the PC's own body on a 2xx
/// (200 done, 202 a card is up - its `waiting: true` says so), with the
/// status as `http`; [`PROJECTS_MISSING`] from a PC without the routes; and
/// the PC's own sentence otherwise (403 "the PC only", 400 a limit, 409 a
/// name used twice or a card already waiting).
pub(crate) fn write_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let mut v = parsed(body).ok_or_else(|| UNREADABLE.to_string())?;
        if let Some(o) = v.as_object_mut() {
            o.insert("http".into(), serde_json::json!(status));
        }
        return Ok(v);
    }
    if status == 404 && !projects_404(body) {
        return Err(PROJECTS_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// A read's answer with the owner's things taken out, for while the
/// private lists are hidden (lock.rs). The list keeps how many projects
/// there are and says nothing else; one project or one benchmark keeps
/// nothing but `hidden`.
pub(crate) fn redact(mut answer: serde_json::Value) -> serde_json::Value {
    let Some(obj) = answer.as_object_mut() else {
        return answer;
    };
    if obj.get("available") == Some(&serde_json::Value::Bool(false)) {
        return answer;
    }
    let count = obj
        .get("projects")
        .and_then(|p| p.as_array())
        .map(|a| a.len());
    let mut out = serde_json::Map::new();
    out.insert("ok".into(), serde_json::json!(true));
    out.insert("hidden".into(), serde_json::json!(true));
    if let Some(n) = count {
        out.insert("hidden_count".into(), serde_json::json!(n));
    }
    serde_json::Value::Object(out)
}

/// A change's answer with the project or benchmark it carries taken out,
/// for while the private lists are hidden: the page is then showing only
/// "Show", and an answer must not carry the words round it. What the PC
/// said (`ok`, `message`, `waiting`, `http`) stays.
pub(crate) fn redact_change(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        for key in ["project", "benchmark"] {
            if obj.remove(key).is_some() {
                obj.insert("hidden".into(), serde_json::json!(true));
            }
        }
    }
    answer
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    write_answer(status, &text)
}

/// The projects, one project, or one benchmark with its chart points. A read.
#[tauri::command]
pub async fn projects_read(
    app: AppHandle,
    project: Option<String>,
    bench: Option<String>,
    points: Option<u32>,
) -> Result<serde_json::Value, String> {
    let path = read_path(project.as_deref(), bench.as_deref(), points)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = read_answer(status, &text)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact(answer)
    } else {
        answer
    })
}

/// ONE change to a project, a benchmark or a number (see the module note).
#[tauri::command]
pub async fn projects_write(
    app: AppHandle,
    action: String,
    project: Option<String>,
    bench: Option<String>,
    result: Option<String>,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let path = write_path(
        &action,
        project.as_deref(),
        bench.as_deref(),
        result.as_deref(),
    )?;
    let body = checked_body(&action, body)?;
    if held_on_stale(&action, &body) && stale(&app) {
        return Err(STALE.to_string());
    }
    let out = post(&app, &path, &body).await?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_change(out)
    } else {
        out
    })
}

/// Choose a coding project's folder with the Windows folder picker, then
/// send the chosen path to this PC's Jarvis. Held on a stale link.
#[tauri::command]
pub async fn projects_choose_folder(
    app: AppHandle,
    project: String,
) -> Result<serde_json::Value, String> {
    let path = write_path("update", Some(&project), None, None)?;
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let (tx, rx) = tokio::sync::oneshot::channel();
    std::thread::spawn(move || {
        let _ = tx.send(crate::folders::picker::pick(
            crate::folders::picker::What::Folder,
        ));
    });
    let chosen = rx
        .await
        .map_err(|_| "the dialog closed unexpectedly".to_string())??;
    let Some(folder) = chosen else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    post(&app, &path, &serde_json::json!({ "folder": folder })).await
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The real answers, made by `tools/gen_projects_cases.py`.
    const CASES: &str = include_str!("../../../tests/fixtures/projects-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("projects-cases.json is JSON")
    }

    #[test]
    fn every_real_read_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 8);
        for (name, view) in all {
            let got = read_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
        }
    }

    #[test]
    fn every_real_change_answer_reads_the_way_the_page_expects() {
        let doc = cases();
        for (name, post) in doc["posts"].as_object().expect("posts") {
            let status = post["status"].as_u64().unwrap() as u16;
            let got = write_answer(status, &post["body"].to_string());
            if (200..300).contains(&status) {
                let v = got.unwrap_or_else(|e| panic!("{name}: {e}"));
                assert_eq!(v["http"], status, "{name}");
            } else {
                let e = got.expect_err(name);
                let said = post["body"]["error"].as_str().unwrap();
                assert!(e.starts_with(&said[..1].to_uppercase()), "{name}: {e}");
            }
        }
        let card = write_answer(202, &doc["posts"]["unmark_card"]["body"].to_string()).unwrap();
        assert_eq!(card["waiting"], true);
        assert_eq!(card["http"], 202);
    }

    #[test]
    fn a_pc_without_projects_says_so_and_no_such_project_is_its_own_sentence() {
        let doc = cases();
        let missing = doc["missing"]["body"].to_string();
        let got = read_answer(404, &missing).unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], PROJECTS_MISSING);
        assert_eq!(doc["words"]["missing"], PROJECTS_MISSING);
        assert_eq!(write_answer(404, &missing).unwrap_err(), PROJECTS_MISSING);
        assert_eq!(write_answer(404, "").unwrap_err(), PROJECTS_MISSING);
        let gone = doc["posts"]["no_such"]["body"].to_string();
        assert_eq!(
            read_answer(404, &gone).unwrap_err(),
            "No such project, benchmark or number"
        );
        assert!(read_answer(200, "{nope").is_err());
    }

    #[test]
    fn only_real_ids_reach_a_url() {
        let p = "0".repeat(31) + "a";
        let b = "f".repeat(32);
        assert_eq!(read_path(None, None, None).unwrap(), "/api/projects");
        assert_eq!(
            read_path(Some(&p), None, None).unwrap(),
            format!("/api/projects/{p}")
        );
        assert_eq!(
            read_path(Some(&p), Some(&b), Some(5000)).unwrap(),
            format!("/api/projects/{p}/benchmarks/{b}?points=1000")
        );
        for bad in ["", "../config", "ABCDEF0123456789ABCDEF0123456789", "a b"] {
            assert!(read_path(Some(bad), None, None).is_err(), "{bad}");
            assert!(
                write_path("update", Some(bad), None, None).is_err(),
                "{bad}"
            );
        }
        assert!(read_path(None, Some(&b), None).is_err());
        assert_eq!(
            write_path("result_delete", Some(&p), Some(&b), Some(&b)).unwrap(),
            format!("/api/projects/{p}/benchmarks/{b}/results/{b}/delete")
        );
        assert_eq!(
            write_path("unmark", Some(&p), Some(&b), None).unwrap(),
            format!("/api/projects/{p}/benchmarks/{b}/unmark")
        );
        assert!(write_path("run", Some(&p), Some(&b), None).is_err());
        for a in ACTIONS {
            assert!(write_path(a, Some(&p), Some(&b), Some(&b)).is_ok(), "{a}");
        }
    }

    #[test]
    fn every_change_waits_for_a_live_link_except_shareable_off() {
        let off = serde_json::json!({ "on": false });
        let on = serde_json::json!({ "on": true });
        assert!(!held_on_stale("shareable", &off));
        assert!(held_on_stale("shareable", &on));
        for a in ACTIONS {
            if *a != "shareable" {
                assert!(held_on_stale(a, &off), "{a}");
            }
        }
    }

    #[test]
    fn a_folder_is_never_typed_into_a_change() {
        let typed = serde_json::json!({ "folder": "C:\\Windows" });
        assert_eq!(
            checked_body("update", Some(typed.clone())).unwrap_err(),
            FOLDER_BY_PICKER
        );
        assert!(checked_body("create", Some(typed)).is_err());
        assert!(checked_body("update", Some(serde_json::json!({ "folder": null }))).is_ok());
        assert!(checked_body("update", Some(serde_json::json!({ "folder": "" }))).is_ok());
        assert!(checked_body("update", Some(serde_json::json!([1]))).is_err());
        assert_eq!(checked_body("delete", None).unwrap(), serde_json::json!({}));
    }

    #[test]
    fn hidden_lists_keep_the_count_but_no_words_or_numbers() {
        let doc = cases();
        let list = redact(doc["cases"]["list_two"].clone());
        assert_eq!(list["hidden"], true);
        assert_eq!(list["hidden_count"], 2);
        let s = list.to_string();
        assert!(!s.contains("marathon") && !s.contains("Jarvis Desktop"));
        let one = redact(doc["cases"]["life"].clone());
        assert_eq!(one["hidden"], true);
        let s = one.to_string();
        assert!(!s.contains("Weight") && !s.contains("74.2") && !s.contains("honest"));
        let bench = redact(doc["cases"]["bench_weight"].clone());
        assert!(!bench.to_string().contains("73.6"));
        let missing = serde_json::json!({ "available": false, "why": PROJECTS_MISSING });
        assert_eq!(redact(missing.clone()), missing);
        let logged = write_answer(200, &doc["posts"]["log"]["body"].to_string()).unwrap();
        let hidden = redact_change(logged);
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["http"], 200);
        assert!(!hidden.to_string().contains("26.75"));
    }
}
