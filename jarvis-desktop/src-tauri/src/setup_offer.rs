//! "Personalize Jarvis": the ONE quiet offer that the setup quiz is unfinished.
//!
//! Wave B, 2026-11-03 (Gemini's rulings Q1, Q3 and Q4; the build spec's
//! sections 5 and 7). The quiz itself is the Settings card
//! (`setup_questionnaire.rs`, `setup-settings.js`); this module is only the
//! part of it that is not the card:
//!
//! * a WINDOWS TOAST, once per app launch, only while the quiz is unfinished;
//! * a TRAY ROW, "Setup unfinished - 9 of 25", which opens Settings at the
//!   quiz card (the pure half is [`SetupState::tray_label`]);
//! * the HUD's "Not now" command ([`hud_setup_dismiss`]), the one write this
//!   whole feature needs from a window that holds no pairing token;
//! * the first-run door: after the walkthrough, Settings opens at the quiz
//!   ([`offer_after_onboarding`]).
//!
//! WHAT IT IS NOT. It never answers a question, never applies anything, never
//! approves a card and never changes a setting. The only two things that leave
//! this module are (1) a toast whose body holds nothing but two counts, and
//! (2) `POST /api/setup/progress {"dismiss": true}`, whose whole effect is one
//! timestamp in `setup.json` - the route the PC's own module owns
//! (`backend/jarvis_setup.py`, JARVIS-API section 147), cardless and
//! desktop-only.
//!
//! THE THREE GATES, in order, and why each one is there:
//!
//! 1. **The state must be KNOWN and unfinished** ([`SetupState::known`],
//!    [`SetupState::unfinished`]). `known` is false until a read of
//!    `GET /api/setup` has landed, so a backend without the route - or one
//!    that has not been updated yet - offers nothing at all. "We could not ask"
//!    is never "the quiz is unfinished": a toast invented from a failed read
//!    would be the app telling the owner about work they may have already done.
//! 2. **The notification store must say yes** (`notifications::may_post` with
//!    [`crate::notifications::Kind::Setup`]). That is the owner's own
//!    "Personalize Jarvis" switch, and quiet hours: the quiz can wait for the
//!    morning, so this is one of the four kinds quiet hours hold back.
//! 3. **"Not now" must not still be in force** ([`SetupState::may_offer_at`]):
//!    a dismissal lasts 24 hours, and the button hides the HUD banner for the
//!    whole launch on top of that.
//!
//! The launch itself is the fourth gate and it lives in the caller: the offer
//! is not considered until the app has been up for [`OFFER_AFTER`], so it
//! cannot race the HUD's own first paint. One offer per launch, held by
//! [`SetupOfferState`]'s `offered` flag - and the launch's one look at the
//! state is only SPENT once the state is really known ([`OfferStep`]): a
//! backend that is not answering at the sixtieth second used to cost the whole
//! launch its reminder, because the caller latched the flag before looking
//! (audit 2026-11-03, bug 1).
//!
//! THE TRAY ROW IS ABSENT, NOT DISABLED. As with the update row, "there is
//! nothing to do" is the row not being there at all rather than a greyed one -
//! a permanently disabled row saying "Setup unfinished" would be a nag with no
//! door.
//!
//! WHAT I COULD NOT MEASURE (stated plainly, as the project's rule asks): this
//! machine has no live backend carrying `GET /api/setup`'s new `version` /
//! `completed_version` fields while Wave B is being built, so the parse here is
//! written against the documented shape in the build spec's section 3.3 and is
//! exercised by this module's own fixtures, not by a real answer. Every field
//! it needs is checked for its type; anything missing means "not known", and
//! not known means no offer.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Manager};

/// The PC's own reading of the questionnaire - the same `GET /api/setup` both
/// apps make. A read: no card, no stale-link hold.
pub(crate) const SETUP_PATH: &str = "/api/setup";

/// Where a dismissal is recorded. The one write this module makes, and it
/// changes one timestamp: cardless, gateless and desktop-only on the PC.
pub(crate) const PROGRESS_PATH: &str = "/api/setup/progress";

/// The toast's title, and the tray row's opening words.
pub const TITLE: &str = "Personalize Jarvis";

const READ_TIMEOUT: Duration = Duration::from_secs(10);
const POST_TIMEOUT: Duration = Duration::from_secs(15);

/// How long the app is up before the offer may be raised. The HUD paints its
/// own first frame from `GET /api/initiative` and a handful of other reads; a
/// toast that arrived during that would be a toast about a page still loading.
pub(crate) const OFFER_AFTER: Duration = Duration::from_secs(60);

/// How long "Not now" silences the offer. The ruling's own number (Q4):
/// dismissing must stop the toast for a day, not for ever - "Keep current
/// settings" is the for-ever one, and it works by moving
/// `completed_version`.
pub const DISMISS_QUIET_SECS: f64 = 24.0 * 60.0 * 60.0;

/// The PC's answer to `GET /api/setup`, narrowed to the six facts this module
/// needs.
///
/// Deliberately not the whole answer: the questions, their help lines and the
/// owner's answers are the Settings card's business, and nothing about them
/// belongs in a toast or a tray menu.
///
/// `Default` is "not known" - see [`SetupState::known`].
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct SetupState {
    /// Whether a read has landed. Before that, nothing is offered: an absent
    /// answer is not "unfinished", it is "not asked yet".
    pub known: bool,
    /// The question-set version the PC is running (`QUIZ_VERSION`).
    pub version: u32,
    /// The version the owner last finished or accepted; `0` = never.
    pub completed_version: u32,
    /// How many questions are answered in the draft or the saved answers.
    pub answered: u32,
    /// How many questions the PC has.
    pub total: u32,
    /// When "Not now" was last pressed, on the PC's own clock.
    pub dismissed_at: Option<f64>,
}

impl SetupState {
    /// Is there anything left to do? A read that never landed is never
    /// unfinished.
    pub fn unfinished(&self) -> bool {
        self.known && self.completed_version < self.version
    }

    /// May the toast be raised at `now` (seconds since the epoch)?
    ///
    /// The dismissal window is the only time rule here; the launch gate and
    /// the notification store are the caller's. A `dismissed_at` of zero (or a
    /// negative one) is not a real press, so it counts as no dismissal.
    pub fn may_offer_at(&self, now: f64) -> bool {
        if !self.unfinished() {
            return false;
        }
        match self.dismissed_at {
            None => true,
            // Zero (and a negative) is not a real press, so it is no dismissal.
            Some(at) if at <= 0.0 => true,
            // A clock that went backwards is still "just pressed": the quiet
            // reading is the safe one.
            Some(at) => now - at >= DISMISS_QUIET_SECS,
        }
    }

    /// The toast's body: two counts and where the door is. No question text
    /// and no answer - the same privacy class as the lock screen's and the
    /// briefing's toasts.
    pub fn toast_body(&self) -> String {
        format!(
            "{} of {} answered. Finish now from the Settings card, or press Not now.",
            self.answered, self.total
        )
    }

    /// The tray row's words, or `None` when the row must not be in the menu.
    ///
    /// Pure on purpose: this is the whole rule, and a rule this small is the
    /// part that can be a test without a running app. `None` is "no row".
    pub fn tray_label(&self) -> Option<String> {
        if !self.unfinished() {
            return None;
        }
        Some(format!(
            "Setup unfinished \u{2014} {} of {}",
            self.answered, self.total
        ))
    }
}

/// The PC's answer as a state, or `None` when it is not one this app can read.
///
/// EVERY FAILURE IS `None`, and `None` leaves the previous state in force -
/// the same discipline `notifications_answer` follows. A 404 (a PC without the
/// route), a backend that is down, a body that is not JSON, a missing `version`
/// or `completed_version`: none of them is "the quiz is unfinished", because
/// none of them is an answer.
pub(crate) fn setup_answer(status: u16, body: &str) -> Option<SetupState> {
    if !(200..300).contains(&status) {
        return None;
    }
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    if value.get("available").and_then(|v| v.as_bool()) == Some(false) {
        return None;
    }
    let count = |name: &str| value.get(name).and_then(|v| v.as_u64());
    let version = count("version")?;
    let completed_version = count("completed_version").unwrap_or(0);
    let answered = count("answered_count").unwrap_or(0);
    // The count of questions is the list itself, so a PC that ever adds one
    // changes the words without this file knowing what a question is. The list
    // must be there AND not empty: a body with a version but no questions would
    // draw "0 of 0 answered", and a questionnaire with nothing in it is not an
    // offer - there is nothing to personalize.
    let questions = value.get("questions").and_then(|v| v.as_array())?;
    if questions.is_empty() {
        return None;
    }
    let total = questions.len() as u64;
    let dismissed_at = value.get("dismissed_at").and_then(|v| v.as_f64());
    Some(SetupState {
        known: true,
        version: u32::try_from(version).ok()?,
        completed_version: u32::try_from(completed_version).ok()?,
        answered: u32::try_from(answered).ok()?,
        total: u32::try_from(total).ok()?,
        dismissed_at,
    })
}

/// Seconds since the epoch, on this PC's own clock - the clock the PC's own
/// `dismissed_at` is written with, so the two are comparable.
fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// In-memory copy of [`SetupState`], plus the one-per-launch flag.
///
/// The same discipline `NotificationState` follows: a `Mutex` for the state and
/// an atomic for the flag, so the telemetry loop and a command can both touch
/// it without a lock that a poster could hold across a `.await`.
#[derive(Default)]
pub struct SetupOfferState {
    state: Mutex<SetupState>,
    offered: AtomicBool,
}

impl SetupOfferState {
    pub fn snapshot(&self) -> SetupState {
        *self
            .state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// Replaces the state. Answers whether it actually moved, so the tray is
    /// only re-labelled when there is something new to say.
    fn store(&self, next: SetupState) -> bool {
        let mut state = self
            .state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if *state == next {
            return false;
        }
        *state = next;
        true
    }

    /// Records a dismissal locally, so a toast this launch cannot fire after
    /// the owner pressed "Not now". The PC's own copy is written by the POST
    /// that precedes this.
    fn note_dismissed(&self, at: f64) {
        let mut state = self
            .state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        state.dismissed_at = Some(at);
    }

    fn was_offered(&self) -> bool {
        self.offered.load(Ordering::Relaxed)
    }

    fn mark_offered(&self) {
        self.offered.store(true, Ordering::Relaxed);
    }
}

/// Asks the PC how far the questionnaire has got, and puts the answer where the
/// toast and the tray row will see it.
///
/// SILENT ON EVERY FAILURE, by design: an older PC (404), a backend that is
/// down, a token this app cannot read - each leaves the state that is already
/// in force, which is "not known" at launch and so offers nothing. It is never
/// fatal: a failed read must not stop the telemetry loop.
pub(crate) async fn refresh_setup_state(app: AppHandle) {
    let base = crate::commands::jarvis_base(&app);
    let client = match crate::commands::jarvis_client(Some(READ_TIMEOUT)) {
        Ok(client) => client,
        Err(err) => {
            crate::logfile::log(&format!(
                "[jarvis] the setup questionnaire state was not read: {err}"
            ));
            return;
        }
    };
    let headers = match crate::commands::jarvis_headers(&app) {
        Ok(headers) => headers,
        Err(err) => {
            crate::logfile::log(&format!(
                "[jarvis] the setup questionnaire state was not read: {err}"
            ));
            return;
        }
    };
    let response = match client
        .get(format!("{base}{SETUP_PATH}"))
        .headers(headers)
        .send()
        .await
    {
        Ok(response) => response,
        Err(err) => {
            // Said in the log file and nowhere else: the event stream already
            // shows the owner that this PC cannot reach its own Jarvis, and a
            // toast about it would be a toast about notifications.
            crate::logfile::log(&format!(
                "[jarvis] the setup questionnaire state was not read: {err}"
            ));
            return;
        }
    };
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    if let Some(remote) = setup_answer(status, &body) {
        if app.state::<SetupOfferState>().store(remote) {
            // The row appears, disappears or re-counts in place. It is a pure
            // function of the state, so the tray is told every time the state
            // really moved.
            crate::tray::on_setup_state(&app);
        }
    }
}

/// Raises the one toast this launch may raise, if all four gates say yes.
///
/// Returns whether this launch's one offer is now SETTLED. `false` means the
/// PC's state has not been read yet: "we could not ask" is not an answer, so
/// nothing is offered and nothing is spent - the caller keeps its flag unset
/// and looks again on its next beat. Every state that really arrived settles
/// the launch, whether it raised a toast or not (a finished quiz, a dismissal
/// and the owner's own switch are answers too).
///
/// Called by `spawn_telemetry_loop` once the app has been up for
/// [`OFFER_AFTER`]; the state itself is refreshed on the same thirty-second
/// beat as the notification choices.
pub(crate) fn offer_once(app: AppHandle) -> bool {
    let holder = app.state::<SetupOfferState>();
    let state = holder.snapshot();
    // The notification store is only asked once there is a real state to ask
    // about: an unread state is not an answer and costs no work.
    let may_post =
        state.known && crate::notifications::may_post(&app, crate::notifications::Kind::Setup);
    match offer_step(&state, holder.was_offered(), may_post, now_secs()) {
        OfferStep::NotYetKnown => false,
        OfferStep::Settled => true,
        OfferStep::Raise => {
            holder.mark_offered();
            crate::commands::notify(&app, TITLE, &state.toast_body());
            true
        }
    }
}

/// What one look at the state decides, without an app: the pure half of
/// [`offer_once`], so "a failed read costs nothing" is a test rather than a
/// comment.
///
/// The three answers are the three things a look can mean: the PC has not
/// answered yet (nothing spent), it answered and there is nothing to post, or
/// it answered and the toast is the one this launch gets.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum OfferStep {
    /// No read has landed. Nothing is offered, and this launch's one offer is
    /// NOT spent: the caller looks again.
    NotYetKnown,
    /// The state is real and no toast is raised for it - finished, dismissed
    /// for the day, already offered, or held back by the owner's own switch
    /// and quiet hours.
    Settled,
    /// The state is real and unfinished: this launch's toast is due.
    Raise,
}

pub(crate) fn offer_step(
    state: &SetupState,
    was_offered: bool,
    may_post: bool,
    now: f64,
) -> OfferStep {
    if !state.known {
        return OfferStep::NotYetKnown;
    }
    if !state.unfinished() || was_offered || !state.may_offer_at(now) || !may_post {
        return OfferStep::Settled;
    }
    OfferStep::Raise
}

/// The first-run door: after the walkthrough, open Settings at the quiz.
///
/// Called ONCE, from `lib.rs`, immediately after the first-run walkthrough was
/// really shown - so it is the same "first launch" Q3 describes, not a window
/// on every start. The window opening IS the offer for this launch, so the
/// toast is marked offered too: the owner must not get both.
///
/// The state has not been read that early in startup, so this reads it first
/// and decides on the PC's own answer. A failed read opens nothing - the
/// walkthrough is over and a window that might be wrong is worse than none.
pub(crate) fn offer_after_onboarding(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        refresh_setup_state(app.clone()).await;
        let holder = app.state::<SetupOfferState>();
        let state = holder.snapshot();
        if !state.may_offer_at(now_secs()) {
            return;
        }
        holder.mark_offered();
        if let Err(err) = crate::windows::show_settings_at(&app, "personalize-jarvis") {
            crate::logfile::log(&format!(
                "[jarvis] the Personalize Jarvis window could not be opened: {err}"
            ));
        }
    });
}

/// The HUD banner's "Not now": record the dismissal on the PC, so the toast is
/// silent for 24 hours.
///
/// THE ONE COMMAND WAVE B NEEDS that a window without a token could not avoid
/// (build spec section 5.4, ruling Q4). It is navigation-class: it writes one
/// timestamp and nothing else. The body is a constant, so a page cannot make it
/// carry an answer, a section or a question - `progress` in
/// `setup_questionnaire.rs` is the card's own doorway to those, and it is
/// granted to Settings alone.
///
/// It is NOT held on a stale link: a dismissal is the owner closing an offer,
/// not a change to a setting, and a stale stream must not trap a banner on
/// screen.
#[tauri::command]
pub async fn hud_setup_dismiss(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = crate::commands::jarvis_base(&app);
    let response = crate::commands::jarvis_client(Some(POST_TIMEOUT))?
        .post(format!("{base}{PROGRESS_PATH}"))
        .headers(crate::commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({ "dismiss": true }))
        .send()
        .await
        .map_err(|e| crate::commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    if !(200..300).contains(&status) {
        return Err(crate::commands::backend_refusal(status, &body));
    }
    let answer = serde_json::from_str::<serde_json::Value>(&body)
        .ok()
        .filter(|value| value.is_object())
        .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string())?;
    // The PC has taken it, so this launch's toast cannot fire after the press
    // even if the read that would have carried it back never lands.
    app.state::<SetupOfferState>().note_dismissed(now_secs());
    Ok(answer)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn known(completed_version: u32, dismissed_at: Option<f64>) -> SetupState {
        SetupState {
            known: true,
            version: 2,
            completed_version,
            answered: 9,
            total: 25,
            dismissed_at,
        }
    }

    /// One function's own text, from its definition to the next one - the same
    /// source check `notifications.rs` uses.
    fn function<'a>(src: &'a str, name: &str) -> &'a str {
        let at = src
            .find(name)
            .unwrap_or_else(|| panic!("{name} is gone from this file"));
        let rest = &src[at..];
        let mut end = rest.len();
        for next in [
            "\nfn ",
            "\npub fn ",
            "\npub(crate) fn ",
            "\nasync fn ",
            "\npub async fn ",
            "\npub(crate) async fn ",
            "\n#[cfg(test)]",
        ] {
            if let Some(i) = rest[1..].find(next) {
                end = end.min(i + 1);
            }
        }
        &rest[..end]
    }

    #[test]
    fn nothing_is_offered_until_an_answer_says_the_quiz_is_unfinished() {
        // Never read: not "unfinished", not a toast, not a row.
        let cold = SetupState::default();
        assert!(!cold.unfinished());
        assert!(!cold.may_offer_at(now_secs()));
        assert_eq!(cold.tray_label(), None);

        // Read, and the owner has already finished this question set.
        let done = known(2, None);
        assert!(!done.unfinished());
        assert!(!done.may_offer_at(now_secs()));
        assert_eq!(done.tray_label(), None);

        // Read, and the set has moved on (or was never finished).
        let behind = known(1, None);
        assert!(behind.unfinished());
        assert!(behind.may_offer_at(1_800_000_000.0));
        assert_eq!(
            behind.tray_label().as_deref(),
            Some("Setup unfinished \u{2014} 9 of 25")
        );
        // A brand-new owner: completed_version 0.
        assert!(known(0, None).unfinished());
    }

    #[test]
    fn not_now_silences_the_toast_for_a_day_and_no_longer() {
        let at = 1_800_000_000.0;
        let dismissed = known(1, Some(at));
        // A real press is inside its window, and the boundary is the window
        // itself: 24 hours after it, the offer is back.
        assert!(!dismissed.may_offer_at(at));
        assert!(!dismissed.may_offer_at(at + 1.0));
        assert!(!dismissed.may_offer_at(at + DISMISS_QUIET_SECS - 1.0));
        assert!(dismissed.may_offer_at(at + DISMISS_QUIET_SECS));
        assert!(dismissed.may_offer_at(at + DISMISS_QUIET_SECS + 60.0));
        // A clock that went backwards is still "just pressed", never "never
        // pressed": the safe reading is the quiet one.
        assert!(!dismissed.may_offer_at(at - 60.0));
        // Zero is not a real timestamp, so it is no dismissal at all.
        assert!(known(1, Some(0.0)).may_offer_at(at));
        // And a dismissal cannot revive a finished quiz.
        assert!(!known(2, Some(at)).may_offer_at(at));
    }

    #[test]
    fn the_toast_says_the_counts_and_nothing_else() {
        let body = known(1, None).toast_body();
        assert_eq!(
            body,
            "9 of 25 answered. Finish now from the Settings card, or press Not now."
        );
        // No question, no answer, no setting name: only two numbers can vary.
        for private in ["learning", "personality", "reworded", "warm", "on"] {
            assert!(
                !body.to_lowercase().contains(private),
                "the toast carries `{private}`"
            );
        }
        assert_eq!(
            SetupState {
                answered: 0,
                total: 24,
                ..known(1, None)
            }
            .toast_body(),
            "0 of 24 answered. Finish now from the Settings card, or press Not now."
        );
    }

    #[test]
    fn the_pcs_answer_is_read_only_when_it_is_one_this_app_can_use() {
        let body = r#"{"available": true, "version": 2, "completed_version": 1,
            "answered_count": 9, "dismissed_at": 1793941234.5,
            "questions": [{},{},{}]}"#;
        let got = setup_answer(200, body).expect("a real answer");
        assert_eq!(
            got,
            SetupState {
                known: true,
                version: 2,
                completed_version: 1,
                answered: 9,
                total: 3,
                dismissed_at: Some(1_793_941_234.5),
            }
        );
        // An old three-key document, a PC with the route absent, a backend
        // that is down, nonsense: none of them is an answer, so none of them
        // may become an offer.
        for (status, bad) in [
            (200, r#"{"answers": {},"completed_at": 1.0,"outcomes": []}"#),
            (200, r#"{"version": 2}"#),
            // A questionnaire with no questions is not an offer: there is
            // nothing to personalize, so "0 of 0 answered" is never drawn.
            (200, r#"{"version": 2, "questions": []}"#),
            (404, r#"{"error": "no such route"}"#),
            (503, r#"{"available": false, "why": "not here"}"#),
            (500, "{}"),
            (200, "not json"),
            (200, "[]"),
        ] {
            assert_eq!(setup_answer(status, bad), None, "{status} {bad}");
        }
        // `available: false` is the module's own "nothing here yet" answer.
        assert_eq!(
            setup_answer(
                200,
                r#"{"available": false, "version": 2, "questions": [{}]}"#
            ),
            None
        );
        // `dismissed_at: null` is no dismissal; a non-number is no dismissal.
        assert_eq!(
            setup_answer(
                200,
                r#"{"version":2,"completed_version":0,"dismissed_at":null,
                    "questions":[{}]}"#
            )
            .expect("answer")
            .dismissed_at,
            None
        );
        assert_eq!(
            setup_answer(
                200,
                r#"{"version":2,"completed_version":0,"dismissed_at":"yesterday",
                    "questions":[{}]}"#
            )
            .expect("answer")
            .dismissed_at,
            None
        );
    }

    #[test]
    fn the_post_is_one_constant_dismissal_and_nothing_a_page_can_shape() {
        // The command's body is a literal: no field reaches it from the page,
        // so a script in the HUD cannot turn a dismissal into anything else.
        let src = include_str!("setup_offer.rs");
        let body = function(src, "pub async fn hud_setup_dismiss(");
        assert!(
            body.contains(r#".json(&serde_json::json!({ "dismiss": true }))"#),
            "the dismissal body is not the constant one"
        );
        assert!(
            !body.contains("question")
                && !body.contains("draft_answers")
                && !body.contains("keep_current"),
            "the HUD's dismissal carries more than a dismissal"
        );
        // It records the press locally as well, or the toast could still fire
        // in the same launch after the owner closed the banner.
        assert!(
            body.contains("note_dismissed"),
            "the local state is not told"
        );
        // And it approves nothing, changes no setting and raises no card.
        for forbidden in [
            "decide_approval",
            "apply",
            "confirm",
            "jarvis_gate",
            "set_notification_prefs",
        ] {
            assert!(
                !body.contains(forbidden),
                "the dismissal command mentions `{forbidden}`"
            );
        }
        assert_eq!(PROGRESS_PATH, "/api/setup/progress");
        assert_eq!(SETUP_PATH, "/api/setup");
    }

    #[test]
    fn the_telemetry_loop_really_reads_the_state_and_offers_once() {
        // Source check: a refresh and an offer written here and never CALLED
        // are the exact defect this feature exists to avoid - a quiz nobody is
        // ever told about. The loop also has to keep the notification refresh
        // it already had (that one has its own pin).
        let lib = include_str!("lib.rs");
        let loop_body = function(lib, "fn spawn_telemetry_loop(");
        assert!(
            loop_body.contains("setup_offer::refresh_setup_state"),
            "the telemetry loop never reads the quiz state, so the tray row and \
             the toast can never appear"
        );
        assert!(
            loop_body.contains("setup_offer::offer_once"),
            "the telemetry loop never raises the setup offer"
        );
        assert!(
            loop_body.contains("setup_offer::OFFER_AFTER"),
            "the offer is not held back until the app has settled"
        );
        // The first-run door exists and is called from the walkthrough branch.
        assert!(
            lib.contains("setup_offer::offer_after_onboarding"),
            "the first-run walkthrough never offers the quiz"
        );
        let setup = function(lib, "if !commands::onboarding_seen(&handle)");
        assert!(
            setup.contains("offer_after_onboarding"),
            "the quiz offer is not in the branch that just showed the walkthrough"
        );
    }

    #[test]
    fn the_offer_asks_the_notification_store_and_marks_the_launch() {
        let src = include_str!("setup_offer.rs");
        let body = function(src, "pub(crate) fn offer_once(");
        // The owner's switch and quiet hours; `Kind::Other` would ignore both,
        // which Q4 explicitly refuses.
        assert!(
            body.contains("notifications::may_post(&app, crate::notifications::Kind::Setup)"),
            "the offer does not ask the notification store"
        );
        assert!(
            !body.contains("may_post(&app, crate::notifications::Kind::Other)"),
            "the offer is the kind Q4 refuses: Other ignores the switch and quiet hours"
        );
        assert!(
            body.contains("mark_offered"),
            "the launch flag is never set"
        );
        assert!(body.contains("commands::notify("), "nothing is posted");
        assert!(
            body.contains("state.toast_body()"),
            "the toast does not carry the counts"
        );
    }

    #[test]
    fn a_failed_read_never_spends_the_launchs_one_offer() {
        let at = 1_800_000_000.0;
        // No read has landed: nothing raised AND nothing spent. This is the
        // whole of bug 1 - the caller latched "considered" before looking, so
        // one failed GET /api/setup at the 60 s mark cost that launch its
        // reminder even though the tray row appeared later.
        let cold = SetupState::default();
        assert_eq!(offer_step(&cold, false, true, at), OfferStep::NotYetKnown);
        assert_eq!(offer_step(&cold, false, false, at), OfferStep::NotYetKnown);
        assert_eq!(offer_step(&cold, true, true, at), OfferStep::NotYetKnown);
        // A state that really arrived settles the launch, whether or not it
        // raises a toast: a finished quiz, a dismissal for the day, an offer
        // already made, and the owner's own switch are answers too.
        assert_eq!(
            offer_step(&known(1, None), false, true, at),
            OfferStep::Raise
        );
        assert_eq!(
            offer_step(&known(2, None), false, true, at),
            OfferStep::Settled
        );
        assert_eq!(
            offer_step(&known(1, Some(at)), false, true, at),
            OfferStep::Settled
        );
        assert_eq!(
            offer_step(&known(1, None), true, true, at),
            OfferStep::Settled
        );
        assert_eq!(
            offer_step(&known(1, None), false, false, at),
            OfferStep::Settled
        );
    }

    #[test]
    fn the_loop_spends_the_offer_on_the_answers_own_word() {
        // The caller's flag comes from `offer_once`, so a "not known" return
        // leaves the launch's one look unspent and the next beat tries again.
        let lib = include_str!("lib.rs");
        let loop_body = function(lib, "fn spawn_telemetry_loop(");
        assert!(
            loop_body.contains("offer_considered = setup_offer::offer_once("),
            "the loop no longer latches its flag from the offer's own answer"
        );
        assert!(
            !loop_body.contains("offer_considered = true;"),
            "the launch's one offer is spent before the state is known again"
        );
        // And the answer is false only for the state that has not arrived.
        let src = include_str!("setup_offer.rs");
        let body = function(src, "pub(crate) fn offer_once(");
        assert!(
            body.contains("-> bool"),
            "offer_once cannot say whether the offer was spent"
        );
        assert!(
            body.contains("OfferStep::NotYetKnown => false"),
            "an unread state settles the launch's one offer"
        );
    }

    #[test]
    fn the_tray_row_opens_the_quiz_place_and_nothing_else() {
        let tray = include_str!("tray.rs");
        assert!(
            tray.contains("ID_SETUP"),
            "the tray has no setup row handle"
        );
        assert!(
            tray.contains("setup_offer::SetupState"),
            "the tray row is not driven by the state this module reads"
        );
        let row = function(tray, "pub fn on_setup_state(");
        assert!(
            row.contains("setup_label") || row.contains("tray_label"),
            "the row's words are not the state's own"
        );
        let event = function(tray, "fn handle_menu_event(");
        assert!(
            event.contains("show_settings_at(app, \"personalize-jarvis\")"),
            "the tray row does not open the quiz card"
        );
    }
}
