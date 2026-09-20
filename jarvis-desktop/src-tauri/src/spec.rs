//! The visual spec and its pattern engine, ported to Rust for the tray icon.
//!
//! DESKTOP-BUILD §6 is explicit about why this file exists:
//!
//! > **Resolve the colour, do not choose it.** There is no "thinking is gold" —
//! > the user picks a colour and a pattern per state and can re-roll all seven
//! > with Randomise. Run the bound pattern through `resolve()` exactly as a
//! > face does and use the colour it returns. A tray with constants in it is
//! > wrong the moment the user changes anything, and then the tray and the face
//! > disagree about what Jarvis is doing, which is worse than no tray colour
//! > at all.
//!
//! So there is not one hex literal in the tray. [`resolve`] below is a
//! line-by-line port of the `resolve(bind, t, amp, seed)` in
//! `docs/reference/jarvis-reactor-kit.html`, reading the same `jarvis-visual-spec.json` the
//! faces read — which the spec itself names as the contract:
//!
//! > resolve(binding, t, amp, seed) -> { a, b } is implemented identically in
//! > Kotlin and here. That function IS the contract; everything else is data.
//!
//! The spec is compiled in with `include_str!` rather than read from disk.
//! It is the same file the webview loads, so the two cannot drift, and a tray
//! that failed to colour itself because a data file was missing at runtime
//! would be a worse failure than a slightly larger binary.

use std::collections::HashMap;
use std::sync::OnceLock;

/// The bundled spec, byte-identical to the copy the webview fetches.
const SPEC_JSON: &str = include_str!("../../src/jarvis-visual-spec.json");

/// An 8-bit RGB colour. The engine works in floats and rounds once, at the end,
/// exactly where the JavaScript does.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Rgb {
    /// Fallback for a colour id the palette does not contain. Same literal the
    /// kit falls back to, and reached in the same circumstances.
    const FALLBACK: Rgb = Rgb {
        r: 0x6f,
        g: 0xe3,
        b: 0xff,
    };

    fn from_hex(hex: &str) -> Option<Self> {
        let hex = hex.strip_prefix('#')?;
        if hex.len() != 6 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
            return None;
        }
        Some(Self {
            r: u8::from_str_radix(&hex[0..2], 16).ok()?,
            g: u8::from_str_radix(&hex[2..4], 16).ok()?,
            b: u8::from_str_radix(&hex[4..6], 16).ok()?,
        })
    }
}

/// What `resolve()` returns: the two colours a face actually paints with.
/// `a` is the hot/primary, `b` the cooler/secondary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Resolved {
    pub a: Rgb,
    pub b: Rgb,
}

/// One state's binding — which pattern is on it and which colours override the
/// pattern's own parameters. Shaped like the kit's `BIND[state]`, which is
/// seeded from `spec.states[*].default` and mutated by the editor UI.
#[derive(Debug, Clone, Default)]
pub struct Binding {
    pub pattern: String,
    pub color: Option<String>,
    pub to: Option<String>,
    pub family: Option<String>,
    pub colors: Option<Vec<String>>,
    /// Per-binding overrides of the pattern's own parameters — the kit's
    /// `Object.assign({}, P.params, bind.params || {})`.
    ///
    /// Not decoration. The second face audit moved three states off the
    /// pattern defaults and expressed the difference entirely here: `thinking`
    /// is `sweep` narrowed to a 58° cool band at 246°, `speaking` is `reactive`
    /// with a `loud` slot and a gain, and `error` is `pulse` at period 1.1 and
    /// sharpness 4.0. Ignore this map and every one of them renders as the
    /// pattern's generic default — a 360° rainbow where a cool band belongs.
    pub params: serde_json::Map<String, serde_json::Value>,
}

/// The parsed spec, built once.
struct Spec {
    /// Colour id → RGB, from `palette.colors`.
    colors: HashMap<String, Rgb>,
    /// Family id → that family's ramp, in the order the palette lists it.
    /// The kit derives this with a filter over the same array, so the order is
    /// the palette's order in both.
    families: HashMap<String, Vec<Rgb>>,
    /// Pattern id → (kind, params).
    patterns: Vec<Pattern>,
    /// State id → its default binding.
    states: HashMap<String, Binding>,
    /// `limits.flash.flicker_rate_hz_max` - the one number `resolve()` itself
    /// enforces. The spec's own note calls this a hard limit, not advice, and
    /// says it is "enforced in three places: the randomiser will not generate
    /// parameters that break them, a governor inside resolve() holds the
    /// colour..., and a build check replays every pattern at both parameter
    /// extremes." None of the three existed in this file - `resolve()`'s
    /// "flicker" branch read `rate_hz` straight from the binding with no
    /// clamp and an unsafe fallback of 7.0 (the spec's own safe default is
    /// 1.2, and 1.3 is the ceiling). Falls back to the spec's documented
    /// value if the field is ever missing, never to something permissive.
    flicker_rate_hz_max: f64,
    /// `limits.flash.max_transitions_per_s` - the second of the three
    /// enforcement points the spec's note names, and [`FlashGovernor`] is
    /// what implements it. "Three opposing transitions per second is the
    /// standard [photosensitive-seizure] threshold" per the spec's own
    /// `why_these_numbers`.
    max_transitions_per_s: u32,
    /// `limits.flash.min_luma_delta` - the swing below which a colour change
    /// does not count as a transition at all, so a pattern drifting through
    /// near-identical shades cannot be held hostage by the governor.
    min_luma_delta: f64,
    /// `limits.flash.strobe_max_s` - how long a strobe may run at all, as
    /// opposed to how often it may change. The governor cannot express this:
    /// a strobe inside the transition budget passes it indefinitely, and the
    /// state most likely to carry a strobe is `error`, which lasts until
    /// someone fixes the error. [`FlashGovernor`] enforces it.
    strobe_max_s: f64,
}

struct Pattern {
    id: String,
    kind: String,
    params: serde_json::Map<String, serde_json::Value>,
}

fn spec() -> &'static Spec {
    static SPEC: OnceLock<Spec> = OnceLock::new();
    SPEC.get_or_init(|| {
        let root: serde_json::Value = serde_json::from_str(SPEC_JSON)
            .expect("jarvis-visual-spec.json is bundled with the binary and must parse");

        let mut colors = HashMap::new();
        let mut families: HashMap<String, Vec<Rgb>> = HashMap::new();
        if let Some(list) = root["palette"]["colors"].as_array() {
            for entry in list {
                let (Some(id), Some(hex)) = (entry["id"].as_str(), entry["hex"].as_str()) else {
                    continue;
                };
                let Some(rgb) = Rgb::from_hex(hex) else {
                    continue;
                };
                colors.insert(id.to_string(), rgb);
                if let Some(family) = entry["family"].as_str() {
                    families.entry(family.to_string()).or_default().push(rgb);
                }
            }
        }

        let mut patterns = Vec::new();
        if let Some(list) = root["patterns"].as_array() {
            for entry in list {
                let (Some(id), Some(kind)) = (entry["id"].as_str(), entry["kind"].as_str()) else {
                    continue;
                };
                patterns.push(Pattern {
                    id: id.to_string(),
                    kind: kind.to_string(),
                    params: entry["params"].as_object().cloned().unwrap_or_default(),
                });
            }
        }

        let mut states = HashMap::new();
        if let Some(list) = root["states"].as_array() {
            for entry in list {
                let Some(id) = entry["id"].as_str() else {
                    continue;
                };
                let default = &entry["default"];
                states.insert(
                    id.to_string(),
                    Binding {
                        pattern: default["pattern"].as_str().unwrap_or("solid").to_string(),
                        // `"color": null` on `thinking` is meaningful, not
                        // missing: rainbow generates its own hue and must not
                        // be pinned to a palette entry. `as_str()` on a JSON
                        // null gives None, which is the same thing the kit's
                        // `bind.color || …` falsiness gives it.
                        color: default["color"].as_str().map(str::to_string),
                        to: default["to"].as_str().map(str::to_string),
                        family: default["family"].as_str().map(str::to_string),
                        colors: default["colors"].as_array().map(|a| {
                            a.iter()
                                .filter_map(|v| v.as_str().map(str::to_string))
                                .collect()
                        }),
                        params: default["params"].as_object().cloned().unwrap_or_default(),
                    },
                );
            }
        }

        let flicker_rate_hz_max = root["limits"]["flash"]["flicker_rate_hz_max"]
            .as_f64()
            .unwrap_or(1.3);
        let max_transitions_per_s = root["limits"]["flash"]["max_transitions_per_s"]
            .as_u64()
            .unwrap_or(3) as u32;
        let min_luma_delta = root["limits"]["flash"]["min_luma_delta"]
            .as_f64()
            .unwrap_or(0.1);
        let strobe_max_s = root["limits"]["flash"]["strobe_max_s"]
            .as_f64()
            .unwrap_or(2.0);

        Spec {
            colors,
            families,
            patterns,
            states,
            flicker_rate_hz_max,
            max_transitions_per_s,
            min_luma_delta,
            strobe_max_s,
        }
    })
}

/// The binding the spec ships for a state, or `None` if the id is not one of
/// the seven. Callers map their own vocabulary onto these ids before asking.
pub fn state_binding(state_id: &str) -> Option<Binding> {
    spec().states.get(state_id).cloned()
}

/// Every state id the spec defines, for the callers that need to prove their
/// own mapping still lands on something real.
pub fn has_state(state_id: &str) -> bool {
    spec().states.contains_key(state_id)
}

// ---------------------------------------------------------------------------
// The primitives the pattern engine is written in.
//
// Each of these is the Rust of one JavaScript function in the kit's PATTERN
// ENGINE block. They are kept separate, and named the same, so the two can be
// diffed by eye when the kit changes.
// ---------------------------------------------------------------------------

/// `hexOf(id)` — palette lookup, falling through to a literal colour, then to
/// the kit's own fallback.
fn hex_of(id: Option<&str>) -> Rgb {
    let Some(id) = id else { return Rgb::FALLBACK };
    if let Some(found) = spec().colors.get(id) {
        return *found;
    }
    Rgb::from_hex(id).unwrap_or(Rgb::FALLBACK)
}

/// `hsl2hex(h, s, l)`.
fn hsl2rgb(h: f64, s: f64, l: f64) -> Rgb {
    let h = ((h % 360.0) + 360.0) % 360.0;
    let s = s.clamp(0.0, 1.0);
    let l = l.clamp(0.0, 1.0);
    let c = (1.0 - (2.0 * l - 1.0).abs()) * s;
    let x = c * (1.0 - ((h / 60.0) % 2.0 - 1.0).abs());
    let m = l - c / 2.0;
    let (r, g, b) = match h as u32 {
        0..=59 => (c, x, 0.0),
        60..=119 => (x, c, 0.0),
        120..=179 => (0.0, c, x),
        180..=239 => (0.0, x, c),
        240..=299 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let q = |v: f64| ((v + m) * 255.0).round().clamp(0.0, 255.0) as u8;
    Rgb {
        r: q(r),
        g: q(g),
        b: q(b),
    }
}

/// `lift(hex, k)` — brighten (`k > 0`) or darken (`k < 0`).
fn lift(c: Rgb, k: f64) -> Rgb {
    let f = |v: u8| {
        let v = v as f64;
        let out = if k >= 0.0 {
            v + (255.0 - v) * k
        } else {
            v * (1.0 + k)
        };
        out.round().clamp(0.0, 255.0) as u8
    };
    Rgb {
        r: f(c.r),
        g: f(c.g),
        b: f(c.b),
    }
}

/// `mix(h1, h2, t)`.
fn mix(a: Rgb, b: Rgb, t: f64) -> Rgb {
    let lerp = |x: u8, y: u8| {
        (x as f64 + (y as f64 - x as f64) * t)
            .round()
            .clamp(0.0, 255.0) as u8
    };
    Rgb {
        r: lerp(a.r, b.r),
        g: lerp(a.g, b.g),
        b: lerp(a.b, b.b),
    }
}

/// `famRamp(fam)`.
fn fam_ramp(family: &str) -> Vec<Rgb> {
    spec().families.get(family).cloned().unwrap_or_default()
}

/// `hash01(n)` — the kit's deterministic jitter, so `flicker` reads the same
/// on both renderers. `Math.sin` and Rust's `f64::sin` are both the platform
/// double-precision sine; the fractional part of a large product will not
/// match bit-for-bit across implementations, and does not need to — this is a
/// noise source, and its *distribution* is the contract, not its exact value.
fn hash01(n: f64) -> f64 {
    let s = (n * 127.1).sin() * 43758.5453;
    s - s.floor()
}

/// `q.key ?? fallback` — nullish coalescing, so an explicit `null` in the spec
/// falls back exactly as a missing key does.
fn num(params: &serde_json::Map<String, serde_json::Value>, key: &str, fallback: f64) -> f64 {
    params.get(key).and_then(|v| v.as_f64()).unwrap_or(fallback)
}

fn text<'a>(params: &'a serde_json::Map<String, serde_json::Value>, key: &str) -> Option<&'a str> {
    params.get(key).and_then(|v| v.as_str())
}

/// Resolve a binding to the two colours a face paints with.
///
/// A direct port of `resolve(bind, t, amp, seed)`. `t` is seconds, `amp` the
/// microphone amplitude in 0..1, `seed` the per-face jitter offset. The tray
/// passes `amp: 0.0` — it has no microphone — and `seed: 0.0`.
pub fn resolve(bind: &Binding, t: f64, amp: f64, seed: f64) -> Resolved {
    let spec = spec();
    let pattern = spec
        .patterns
        .iter()
        .find(|p| p.id == bind.pattern)
        // `SPEC.patterns[0]` — the kit's own fallback for an unknown id.
        .or_else(|| spec.patterns.first());
    let Some(pattern) = pattern else {
        return Resolved {
            a: Rgb::FALLBACK,
            b: Rgb {
                r: 0x1d,
                g: 0x5f,
                b: 0x7a,
            },
        };
    };
    // `const q = Object.assign({}, P.params, bind.params || {})` — the
    // binding's own parameters win over the pattern's defaults, key by key.
    // Cloning the pattern's map per call is a few dozen bytes at 2 Hz on the
    // tray; sharing a reference would mean threading two maps through every
    // lookup below and losing the line-for-line match with the kit.
    let q = &if bind.params.is_empty() {
        pattern.params.clone()
    } else {
        let mut merged = pattern.params.clone();
        for (key, value) in &bind.params {
            merged.insert(key.clone(), value.clone());
        }
        merged
    };

    // `pick = id => hexOf(bind.color || id)` — the binding's colour overrides
    // the pattern's own, which is how one pattern serves several states.
    let pick = |param: &str| -> Rgb { hex_of(bind.color.as_deref().or_else(|| text(q, param))) };

    match pattern.kind.as_str() {
        "solid" => {
            let a = pick("color");
            Resolved {
                a,
                b: lift(a, -0.55),
            }
        }

        "hue_sweep" => {
            let span = num(q, "span_deg", 360.0);
            let off = num(q, "offset_deg", 0.0);
            let ph = (t / num(q, "period_s", 6.0)) % 1.0;
            let h = off
                + if span == 360.0 {
                    ph * 360.0
                } else {
                    (ph * std::f64::consts::TAU).sin() * span * 0.5
                };
            let sat = num(q, "sat", 0.8);
            let light = num(q, "light", 0.62);
            Resolved {
                a: hsl2rgb(h, sat, light),
                b: hsl2rgb(h + 28.0, sat * 0.9, light * 0.55),
            }
        }

        "step_cycle" => {
            let list: Vec<Rgb> = bind
                .colors
                .clone()
                .or_else(|| {
                    q.get("colors").and_then(|v| v.as_array()).map(|a| {
                        a.iter()
                            .filter_map(|v| v.as_str().map(str::to_string))
                            .collect()
                    })
                })
                .unwrap_or_default()
                .iter()
                .map(|id| hex_of(Some(id)))
                .collect();
            if list.is_empty() {
                return Resolved {
                    a: Rgb::FALLBACK,
                    b: Rgb {
                        r: 0x1d,
                        g: 0x5f,
                        b: 0x7a,
                    },
                };
            }
            let hold = num(q, "hold_s", 2.0);
            let blend = num(q, "blend_s", 0.4);
            let unit = hold + blend;
            let total = t % (unit * list.len() as f64);
            let i = (total / unit).floor();
            let into = total - i * unit;
            let i = (i as usize).min(list.len() - 1);
            let j = (i + 1) % list.len();
            let k = if into <= hold {
                0.0
            } else {
                (into - hold) / blend
            };
            let a = if k <= 0.0 {
                list[i]
            } else {
                mix(list[i], list[j], k)
            };
            Resolved {
                a,
                b: lift(a, -0.55),
            }
        }

        "breathe" => {
            let base = pick("color");
            let d = num(q, "depth", 0.45);
            let e = ((t / num(q, "period_s", 4.5) * std::f64::consts::TAU).sin() * 0.5 + 0.5) * d;
            Resolved {
                a: lift(base, e * 0.8 - d * 0.25),
                b: lift(base, -0.6 + e * 0.3),
            }
        }

        "pulse" => {
            let base = pick("color");
            let ph = (t / num(q, "period_s", 1.8) * std::f64::consts::TAU)
                .sin()
                .max(0.0);
            let e = ph.powf(num(q, "sharpness", 9.0));
            Resolved {
                a: lift(base, e * 0.75),
                b: lift(base, -0.7 + e * 0.4),
            }
        }

        // The bound colour WINS — the rule the second face audit added. Before
        // it, binding ice-5 to a gradient still swung to the pattern's own
        // magenta-4, which is why nineteen of the twenty speaking tiles came
        // out pink. A gradient with a bound colour and no explicit `to` now
        // runs between that colour and its own darker step; the pattern's
        // two-hue default applies only when nothing is bound at all.
        "gradient" => {
            let a0 = hex_of(bind.color.as_deref().or_else(|| text(q, "from")));
            let b0 = match (bind.to.as_deref(), bind.color.as_deref()) {
                (Some(to), _) => hex_of(Some(to)),
                (None, Some(_)) => lift(a0, -0.38),
                (None, None) => hex_of(text(q, "to")),
            };
            let k = (t / num(q, "period_s", 7.0) * std::f64::consts::TAU).sin() * 0.5 + 0.5;
            Resolved {
                a: mix(a0, b0, k),
                b: mix(b0, a0, k),
            }
        }

        "comet" => {
            let head = hex_of(bind.color.as_deref().or_else(|| text(q, "color")));
            let tail = hex_of(text(q, "tail"));
            let k = (t / num(q, "period_s", 2.4)) % 1.0;
            let e = (1.0 - (k * 2.0 - 1.0).abs()).powi(3);
            Resolved {
                a: mix(tail, head, e),
                b: tail,
            }
        }

        "flicker" => {
            let ramp = fam_ramp(
                bind.family
                    .as_deref()
                    .or_else(|| text(q, "family"))
                    .unwrap_or("ember"),
            );
            if ramp.is_empty() {
                return Resolved {
                    a: Rgb::FALLBACK,
                    b: lift(Rgb::FALLBACK, -0.55),
                };
            }
            // CLAMPED, where this used to read straight through with an
            // unsafe fallback. `limits.flash.flicker_rate_hz_max` (1.3) is a
            // photosensitive-seizure bound, not a style limit - the spec's
            // own note calls it a hard limit because the face fills over a
            // quarter of the visual field at reading distance, so the
            // small-area exemption in the guidance does not apply. Nothing
            // clamped it here: a hand-written or randomised binding could
            // set any rate_hz, and the FALLBACK when the field was simply
            // missing was 7.0 - itself more than five times the ceiling.
            // Reachable with no phone, no second device and no network at
            // all: the desktop's own "Randomise" button in faces.html could
            // already generate 5-11 Hz before that generator is fixed too.
            let rate = num(q, "rate_hz", 1.2).min(spec.flicker_rate_hz_max);
            let depth = num(q, "depth", 0.55);
            let n = hash01((t * rate).floor() + seed * 17.0) * 0.6
                + hash01((t * rate * 2.3).floor() + seed * 31.0) * 0.4;
            let span = (ramp.len() - 1) as f64;
            let idx = (1.0 + n * depth * span).round().clamp(0.0, span) as usize;
            Resolved {
                a: ramp[idx],
                b: ramp[idx.saturating_sub(2)],
            }
        }

        "reactive" => {
            let a0 = hex_of(bind.color.as_deref().or_else(|| text(q, "quiet")));
            let b0 = hex_of(text(q, "loud"));
            let k = (amp * num(q, "gain", 1.6)).clamp(0.0, 1.0);
            let a = mix(a0, b0, k);
            Resolved {
                a,
                b: lift(a, -0.55),
            }
        }

        "temperature" => {
            let k = (t / num(q, "period_s", 9.0) * std::f64::consts::TAU).sin() * 0.5 + 0.5;
            let a = if k < 0.5 {
                mix(hex_of(text(q, "cold")), hex_of(text(q, "warm")), k * 2.0)
            } else {
                mix(
                    hex_of(text(q, "warm")),
                    hex_of(text(q, "hot")),
                    (k - 0.5) * 2.0,
                )
            };
            Resolved {
                a,
                b: lift(a, -0.5),
            }
        }

        "strobe" => {
            // CLAMPED at the point of use, exactly as the flicker rate above
            // is, so the floor holds for a hand-written binding and not only
            // for what the spec's own params happen to say.
            //
            // 2/max_transitions_per_s, not 1/: a strobe makes TWO opposing
            // transitions per period (on->off->on). Flooring with a single
            // division allows 0.33s, which is six transitions a second
            // against a hard limit of three.
            //
            // The default is the spec's own 0.8, not 0.7. The two ports had
            // drifted apart on a number the spec states once.
            // `spec`, not `spec()`: this function binds the spec to a local
            // of the same name at its top, which shadows the accessor.
            let floor = 2.0 / f64::from(spec.max_transitions_per_s.max(1));
            let period = num(q, "period_s", 0.8).max(floor);
            let on = ((t / period) % 1.0) < 0.5;
            let a = if on {
                hex_of(bind.color.as_deref().or_else(|| text(q, "a")))
            } else {
                hex_of(text(q, "b"))
            };
            Resolved {
                a,
                b: lift(a, -0.5),
            }
        }

        _ => Resolved {
            a: Rgb::FALLBACK,
            b: Rgb {
                r: 0x1d,
                g: 0x5f,
                b: 0x7a,
            },
        },
    }
}

/// Relative luminance, 0..1, Rec. 709 coefficients — the same weighting the
/// spec's own accessibility numbers (`min_luma_delta`) are defined against.
fn luma(c: Rgb) -> f64 {
    (0.2126 * c.r as f64 + 0.7152 * c.g as f64 + 0.0722 * c.b as f64) / 255.0
}

/// The flash-safety governor the spec's `limits.flash.note` describes as the
/// second of three enforcement points: "a governor inside resolve() holds
/// the colour when a fourth opposing transition would land inside one
/// second." Verified against the CROSS-CLIENT-CONTRACT-REPLY-2 finding that
/// none of the three existed anywhere — this is the client-side one.
///
/// **One instance per rendered surface, never shared.** The spec's own
/// `scope_why` documents the exact failure a shared governor produces: fed by
/// several surfaces in turn, it "saw twenty faces with twenty clocks as one
/// face flashing between twenty colours, spent its budget on those
/// cross-surface transitions and then held one face's colour on another."
/// The tray draws one surface (the icon) and owns exactly one of these.
#[derive(Debug, Clone)]
pub struct FlashGovernor {
    /// The colour last actually shown. `None` before the first call, so the
    /// very first resolve is never held against an colour that never existed.
    held: Option<Resolved>,
    held_luma: f64,
    /// Direction of the last transition let through: `true` = luma rose.
    /// `None` before the first transition — which is treated as opposing, so
    /// the first visible change costs a budget slot. This doc used to claim
    /// the opposite ("the first one is never opposing anything"); the code
    /// was briefly changed to match it and the tests caught that the doc was
    /// the wrong half. See the note at the `opposing` binding in `resolve`.
    last_direction: Option<bool>,
    /// REAL-time seconds (the `now` argument, never the face clock `t`) of
    /// opposing transitions let through in roughly the last second, oldest
    /// first.
    recent: Vec<f64>,
    /// REAL-time second the current strobe began, or `None` when the binding
    /// is not a strobe. `limits.flash.strobe_max_s` is a cap on DURATION,
    /// which the transition budget above cannot express.
    strobe_started_at: Option<f64>,
    /// The brightest colour this strobe has shown, and its luma. A spent
    /// strobe freezes here rather than on the dark phase: the dark phase is
    /// the pattern's own neutral, and holding that reads as "the face
    /// switched off" - the wrong answer for the state most likely to be
    /// strobing. Tracked by luminance so this needs nothing from `resolve`'s
    /// internals; the lit phase is by construction the brighter of the two.
    strobe_lit: Option<Resolved>,
    strobe_lit_luma: f64,
}

impl FlashGovernor {
    pub fn new() -> Self {
        Self {
            held: None,
            held_luma: 0.0,
            last_direction: None,
            recent: Vec::new(),
            strobe_started_at: None,
            strobe_lit: None,
            strobe_lit_luma: -1.0,
        }
    }

    /// Resolves `bind` at time `t` exactly as [`resolve`] would, except that a
    /// colour change which would be a fourth opposing transition inside one
    /// second is held at the previous colour instead of applied. Call once
    /// per surface per frame in place of a bare `resolve()` call — this reads
    /// prior state and cannot be a drop-in for a caller that needs a pure
    /// function (a build-time replay, a golden-vector test).
    ///
    /// **Two clocks, and they are not interchangeable.** `t` is the surface's
    /// own animation clock, which drives the pattern and which a speed
    /// control may scale. `now` is real, unscaled seconds, and is the only
    /// thing the one-second window is ever measured in. This tray's `clock()`
    /// is already real time so it passes the same value for both; the
    /// `faces.html` port does not, and passing its speed-scaled face clock
    /// for both was a live bug there — at the top of a 6× speed slider one
    /// governor "second" was 1/6 of a real one, so up to 18 opposing
    /// transitions per real second got through against a hard limit of 3.
    /// The parameter exists in this port so the two stay line-for-line the
    /// same algorithm, which is the rule for this pair.
    pub fn resolve(&mut self, bind: &Binding, t: f64, amp: f64, seed: f64, now: f64) -> Resolved {
        let mut candidate = resolve(bind, t, amp, seed);

        // The DURATION cap, applied before the governor and never instead of
        // it — the same order the `faces.html` port and the Android port both
        // use. The governor limits how often the screen changes; this limits
        // how long a strobe may keep changing at all. A strobe inside the
        // transition budget passes the governor for ever, so without this an
        // `error` strobe ran until the error was fixed.
        // The same lookup `resolve` does, fallback included: an unknown id
        // renders as `patterns[0]` there, so it must be judged as
        // `patterns[0]` here too. Today that is `solid` and the distinction
        // is academic; it stops being academic the moment the spec is
        // reordered, and these two ports are meant to stay line-for-line.
        let is_strobe = spec()
            .patterns
            .iter()
            .find(|p| p.id == bind.pattern)
            .or_else(|| spec().patterns.first())
            .map(|p| p.kind == "strobe")
            .unwrap_or(false);
        if is_strobe {
            let began = *self.strobe_started_at.get_or_insert(now);
            let lum = luma(candidate.a);
            if lum > self.strobe_lit_luma {
                self.strobe_lit = Some(candidate);
                self.strobe_lit_luma = lum;
            }
            if now - began > spec().strobe_max_s {
                if let Some(lit) = self.strobe_lit {
                    candidate = lit;
                }
            }
        } else {
            self.strobe_started_at = None;
            self.strobe_lit = None;
            self.strobe_lit_luma = -1.0;
        }

        let Some(held) = self.held else {
            self.held = Some(candidate);
            self.held_luma = luma(candidate.a);
            return candidate;
        };

        let candidate_luma = luma(candidate.a);
        let delta = candidate_luma - self.held_luma;
        let limits = spec();

        // Below the swing the spec defines as a real change, this is not a
        // transition at all — apply it freely and leave the window alone, or
        // a pattern drifting through near-identical shades would eventually
        // starve on transitions that were never visible in the first place.
        if delta.abs() < limits.min_luma_delta {
            self.held = Some(candidate);
            self.held_luma = candidate_luma;
            return candidate;
        }

        let direction = delta > 0.0;
        // `None` counts as opposing, and that is deliberate. It was changed
        // once, on the reasoning that a first transition opposes nothing —
        // and the change was measured and reverted, because the limit is on
        // what REACHES THE SCREEN. The first transition is a visible
        // luminance change like any other; exempting it let a fourth change
        // land inside one second, which the strobe test below and
        // `tests/flashgov.mjs` both caught by counting output changes rather
        // than internal bookkeeping. Three per second is the
        // photosensitive-seizure threshold, so the port that counts one fewer
        // is the wrong one.
        let opposing = self.last_direction != Some(direction);

        // Prune to the trailing one-second window before counting, so an old
        // transition cannot keep the budget spent long after it happened.
        // `now`, never `t` — the window is real seconds. See the doc above.
        self.recent.retain(|&at| now - at < 1.0);

        if opposing && self.recent.len() as u32 >= limits.max_transitions_per_s {
            // Letting this one through would be the (max + 1)th opposing
            // transition inside one second. Hold — the held colour is not
            // re-recorded as a transition, so a run of held frames cannot
            // itself exhaust the budget.
            return held;
        }

        if opposing {
            self.recent.push(now);
            self.last_direction = Some(direction);
        }
        self.held = Some(candidate);
        self.held_luma = candidate_luma;
        candidate
    }
}

impl Default for FlashGovernor {
    fn default() -> Self {
        Self::new()
    }
}

/// Whether a pattern's output depends on `t`. The tray uses this to decide
/// whether re-resolving is worth a timer at all: `solid` never changes, so a
/// state bound to it costs one resolve for as long as it lasts.
/// The shell-level dim a state carries, from `state_transforms.states.<id>`.
///
/// The spec is explicit that these four states are transforms rather than
/// tables — a clock multiplier, a direction, a dim and at most one overlay,
/// "applied by the SHELL on top of a borrowed table … so all twenty faces
/// behave identically and each client implements this once instead of twenty
/// times". The tray is a shell like any other, so it applies the dim rather
/// than painting `banked` at the same brightness as `idle`.
///
/// Returns 1.0 for the states that carry no transform.
pub fn state_dim(state_id: &str) -> f64 {
    static DIMS: OnceLock<HashMap<String, f64>> = OnceLock::new();
    *DIMS
        .get_or_init(|| {
            let root: serde_json::Value = serde_json::from_str(SPEC_JSON).unwrap_or_default();
            let mut out = HashMap::new();
            if let Some(states) = root["state_transforms"]["states"].as_object() {
                for (id, entry) in states {
                    if let Some(dim) = entry["dim"].as_f64() {
                        out.insert(id.clone(), dim);
                    }
                }
            }
            out
        })
        .get(state_id)
        .unwrap_or(&1.0)
}

/// Whether a state draws the rim ring of notches, and how many it may draw
/// before it switches to an overflow mark — `state_transforms.states.<id>`
/// `overlay: "notches"` and its `overlay_spec.max_notches`.
pub fn notch_overlay(state_id: &str) -> Option<usize> {
    // Parsed once. This is called from `paint`, which runs on every link
    // change and twice a second while a pattern animates — re-parsing 59 KB of
    // JSON on that path was pure waste, and its two neighbours here already
    // used a `OnceLock`.
    static TRANSFORMS: std::sync::OnceLock<serde_json::Value> = std::sync::OnceLock::new();
    let root = TRANSFORMS
        .get_or_init(|| serde_json::from_str(SPEC_JSON).unwrap_or(serde_json::Value::Null));
    let entry = &root["state_transforms"]["states"][state_id];
    if entry["overlay"].as_str() != Some("notches") {
        return None;
    }
    Some(entry["overlay_spec"]["max_notches"].as_u64().unwrap_or(12) as usize)
}

pub fn is_animated(bind: &Binding) -> bool {
    spec()
        .patterns
        .iter()
        .find(|p| p.id == bind.pattern)
        .map(|p| p.kind != "solid")
        // An unknown pattern falls back to `SPEC.patterns[0]`, which is solid.
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The spec must parse and carry the seven states DESKTOP-BUILD §6 names,
    /// because the tray's state mapping resolves against these ids.
    #[test]
    fn spec_parses_with_its_eight_states() {
        for id in [
            "idle",
            "listening",
            "thinking",
            "speaking",
            "approval",
            "standby",
            "error",
            // Added by the second face audit. Not a mood: things are waiting
            // and Jarvis is not going to say them out loud.
            "banked",
        ] {
            assert!(has_state(id), "spec is missing the `{id}` state");
        }
        assert_eq!(spec().states.len(), 8, "spec should carry 8 states");
        assert_eq!(spec().patterns.len(), 12, "spec should carry 12 patterns");
        assert_eq!(spec().colors.len(), 50, "spec should carry 50 colours");
    }

    /// The three states the audit moved off their pattern's defaults express
    /// the whole difference in `default.params`. If the merge is dropped they
    /// still resolve to *something*, which is why this asserts the parameters
    /// arrived rather than that a colour looks right.
    #[test]
    fn state_params_reach_the_binding() {
        let thinking = state_binding("thinking").expect("thinking is a state");
        assert_eq!(thinking.pattern, "sweep");
        assert_eq!(num(&thinking.params, "offset_deg", -1.0), 246.0);
        assert_eq!(num(&thinking.params, "span_deg", -1.0), 58.0);

        let error = state_binding("error").expect("error is a state");
        assert_eq!(num(&error.params, "sharpness", -1.0), 4.0);

        let speaking = state_binding("speaking").expect("speaking is a state");
        assert_eq!(text(&speaking.params, "loud"), Some("ice-5"));
    }

    /// A bound parameter must beat the pattern's own. `pulse` ships
    /// `sharpness: 9`; `error` binds 4.0, which is a visibly slower, fatter
    /// pulse. Resolving the two must not agree at the same phase.
    #[test]
    fn binding_params_override_the_pattern() {
        let bound = state_binding("error").expect("error is a state");
        let unbound = Binding {
            pattern: bound.pattern.clone(),
            color: bound.color.clone(),
            ..Default::default()
        };
        // A quarter through `pulse`'s own 1.8 s period the two sharpnesses are
        // far apart; if `params` were ignored these would be identical.
        let t = 0.45;
        assert_ne!(
            resolve(&bound, t, 0.0, 0.0),
            resolve(&unbound, t, 0.0, 0.0),
            "error's bound pulse params were ignored"
        );
    }

    /// The gradient rule the second face audit added: a bound colour wins over
    /// the pattern's own two hues. `gradient` ships `from: azure-4`,
    /// `to: magenta-4`; binding ice-5 with no `to` must never reach magenta.
    #[test]
    fn a_bound_gradient_colour_never_swings_to_magenta() {
        let bind = Binding {
            pattern: "gradient".to_string(),
            color: Some("ice-5".to_string()),
            ..Default::default()
        };
        let magenta = hex_of(Some("magenta-4"));
        for i in 0..200 {
            let t = i as f64 * 0.07;
            let out = resolve(&bind, t, 0.0, 0.0);
            for c in [out.a, out.b] {
                // Magenta's defining feature here is that red and blue both
                // sit far above green. ice-5 can never produce that.
                let (r, g, b) = (c.r as i16, c.g as i16, c.b as i16);
                assert!(
                    !(r > g + 40 && b > g + 40),
                    "a bound gradient reached the pattern's magenta at t={t}: {c:?} \
                     (magenta-4 is {magenta:?})"
                );
            }
        }

        // …and an explicit `to` still wins, because that is a deliberate
        // two-hue binding rather than a leftover default.
        let two_hue = Binding {
            to: Some("magenta-4".to_string()),
            ..bind.clone()
        };
        assert_ne!(
            resolve(&bind, 1.75, 0.0, 0.0),
            resolve(&two_hue, 1.75, 0.0, 0.0),
            "an explicit `to` should still be honoured"
        );
    }

    /// `idle` is `breathe` on `ice-3` (#2ea8cc). Breathe only lifts and darkens
    /// one base colour, so the resolved hue must stay recognisably that colour
    /// at every phase — this is the check that would fail if `lift` were ported
    /// with the wrong sign or the palette lookup silently fell back.
    #[test]
    fn idle_resolves_within_its_bound_colour() {
        let bind = state_binding("idle").expect("idle is a spec state");
        assert_eq!(bind.pattern, "breathe");
        for step in 0..40 {
            let c = resolve(&bind, step as f64 * 0.25, 0.0, 0.0);
            assert!(
                c.a.b > c.a.r && c.a.g > c.a.r,
                "ice must stay blue-green at t={step}, got {:?}",
                c.a
            );
            assert!(c.b.b <= c.a.b, "b is the cooler of the pair at t={step}");
        }
    }

    /// `thinking` is `rainbow`, whose whole point is that it does not sit on a
    /// palette entry. Resolving it across one period must actually travel.
    #[test]
    fn rainbow_sweeps_the_circle() {
        let bind = state_binding("thinking").expect("thinking is a spec state");
        assert!(
            bind.color.is_none(),
            "rainbow must not be pinned to a colour"
        );
        let a = resolve(&bind, 0.0, 0.0, 0.0).a;
        let b = resolve(&bind, 2.0, 0.0, 0.0).a;
        let c = resolve(&bind, 4.0, 0.0, 0.0).a;
        assert!(
            a != b && b != c && a != c,
            "rainbow stalled: {a:?} {b:?} {c:?}"
        );
        assert!(is_animated(&bind));
    }

    /// `listening` is `solid`, which is the case the tray's timer skips.
    #[test]
    fn solid_is_not_animated() {
        let bind = state_binding("listening").expect("listening is a spec state");
        assert!(!is_animated(&bind));
        let a = resolve(&bind, 0.0, 0.0, 0.0);
        let b = resolve(&bind, 97.3, 0.0, 0.0);
        assert_eq!(a, b, "solid must not depend on t");
    }

    /// The palette lookup, the literal-hex path and the fallback, which between
    /// them decide whether a mistyped colour id shows as black or as the kit's
    /// own default.
    #[test]
    fn colour_lookup_falls_through_in_order() {
        assert_eq!(
            hex_of(Some("ice-1")),
            Rgb {
                r: 10,
                g: 58,
                b: 74
            }
        );
        assert_eq!(
            hex_of(Some("#123456")),
            Rgb {
                r: 18,
                g: 52,
                b: 86
            }
        );
        assert_eq!(hex_of(Some("not-a-colour")), Rgb::FALLBACK);
        assert_eq!(hex_of(None), Rgb::FALLBACK);
    }

    /// `strobe`'s own spec entry says it: "period_s below 0.4 would exceed
    /// the transition budget" (`rose-4` against `neutral-1`, a stark enough
    /// pair that every alternation clears `min_luma_delta`). 0.2s is exactly
    /// twice that, so the governor MUST intervene or this test is not
    /// exercising it at all.
    fn fast_strobe() -> Binding {
        let mut params = serde_json::Map::new();
        params.insert("period_s".into(), serde_json::json!(0.2));
        Binding {
            pattern: "strobe".to_string(),
            params,
            ..Default::default()
        }
    }

    /// The bug this whole type exists to fix: nothing stopped a fast strobe
    /// (or a mis-set flicker, before that got its own clamp) from alternating
    /// past the standard three-opposing-transitions-per-second threshold.
    /// Sampled every 50ms across 2 real seconds — coarser than a real frame
    /// rate, deliberately, so the assertion is not tuned to one animation
    /// tick length.
    #[test]
    fn governor_holds_a_fast_strobe_under_the_transition_budget() {
        let bind = fast_strobe();
        let mut gov = FlashGovernor::new();
        let mut transitions = 0u32;
        let mut worst_in_any_window = 0u32;
        let mut window: Vec<f64> = Vec::new();
        let mut last: Option<Resolved> = None;

        let mut t = 0.0;
        while t < 2.0 {
            let out = gov.resolve(&bind, t, 0.0, 0.0, t);
            match last {
                // The very first frame is an appearance, not a transition —
                // there is nothing on screen yet for it to oppose, and the
                // real photosensitive-seizure guidance this limit is drawn
                // from (a pair of opposing luminance changes) agrees.
                None => last = Some(out),
                Some(prev) if prev != out => {
                    transitions += 1;
                    window.push(t);
                    window.retain(|&at| t - at < 1.0);
                    worst_in_any_window = worst_in_any_window.max(window.len() as u32);
                    last = Some(out);
                }
                Some(_) => {}
            }
            t += 0.05;
        }

        assert!(
            worst_in_any_window <= spec().max_transitions_per_s,
            "governor let {worst_in_any_window} transitions land inside one \
             second; the spec's limit is {}",
            spec().max_transitions_per_s
        );
        // The strobe is genuinely fast (10 raw transitions/s): if the
        // governor were a no-op this would be far higher, so a low count
        // proves it actually held frames rather than the pattern coincidentally
        // resolving to the same output.
        assert!(
            transitions < 12,
            "expected the governor to hold most of a 10 Hz strobe's \
             transitions over 2s, saw {transitions} distinct outputs"
        );
    }

    /// `limits.flash.strobe_max_s` — the DURATION cap, which the transition
    /// budget above cannot express. A strobe slow enough to sit inside the
    /// budget passes the governor for ever, and `error` is both the state
    /// most likely to carry a strobe and the state that lasts until someone
    /// fixes the error. The spec has said "never more than strobe_max_s at
    /// full face width" since the beginning; nothing on this side enforced
    /// it until this test existed.
    #[test]
    fn a_strobe_stops_changing_once_it_passes_strobe_max_s() {
        let bind = fast_strobe();
        let mut gov = FlashGovernor::new();
        let mut after_cap: Vec<Resolved> = Vec::new();

        let mut t = 0.0;
        while t < 6.0 {
            let out = gov.resolve(&bind, t, 0.0, 0.0, t);
            // Half a second of slack past the cap, so this is not asserting
            // on the exact frame the budget runs out.
            if t > spec().strobe_max_s + 0.5 {
                after_cap.push(out);
            }
            t += 0.05;
        }

        assert!(!after_cap.is_empty(), "the drive must reach past the cap");
        let first = after_cap[0];
        assert!(
            after_cap.iter().all(|r| r.a == first.a),
            "after {}s a strobe must hold one colour, but it kept changing",
            spec().strobe_max_s
        );
    }

    /// And it must freeze LIT. Freezing on the dark phase would leave the
    /// face looking switched off, which is the wrong answer for the state
    /// most likely to be strobing.
    #[test]
    fn a_spent_strobe_freezes_on_its_lit_phase() {
        let bind = fast_strobe();
        let mut gov = FlashGovernor::new();
        let mut brightest = f64::MIN;
        let mut last = Rgb::FALLBACK;

        let mut t = 0.0;
        while t < 6.0 {
            let out = gov.resolve(&bind, t, 0.0, 0.0, t);
            brightest = brightest.max(luma(out.a));
            last = out.a;
            t += 0.05;
        }

        assert!(
            (luma(last) - brightest).abs() < f64::EPSILON,
            "a spent strobe must hold its brightest phase, held luma {} \
             against a brightest of {brightest}",
            luma(last)
        );
    }

    /// The period floor, clamped inside `resolve` at the point of use so it
    /// holds for a hand-written binding and not only for the spec's own
    /// params. `2/max_transitions_per_s`, because a strobe makes two
    /// opposing transitions per period — flooring with a single division
    /// still allows six a second against a limit of three.
    #[test]
    fn resolve_floors_a_too_fast_strobe_period() {
        let mut params = serde_json::Map::new();
        // Absurd on purpose, and an explicit 0 would have been read as
        // "absent" by the `||` this replaced.
        params.insert("period_s".into(), serde_json::json!(0.0));
        let bind = Binding {
            pattern: "strobe".to_string(),
            params,
            ..Default::default()
        };

        // Measured as the gap between changes, not as a count inside a
        // window: the floor lands the rate at exactly the limit, so a window
        // straddling that boundary legitimately sees one more.
        let floor_gap = 1.0 / f64::from(spec().max_transitions_per_s);
        let step = 0.005;
        let mut last: Option<Rgb> = None;
        let mut last_at: Option<f64> = None;
        let mut shortest = f64::MAX;

        let mut t = 0.0;
        while t < 2.0 {
            let a = resolve(&bind, t, 0.0, 0.0).a;
            if let Some(prev) = last {
                if prev != a {
                    if let Some(at) = last_at {
                        shortest = shortest.min(t - at);
                    }
                    last_at = Some(t);
                }
            }
            last = Some(a);
            t += step;
        }

        assert!(
            shortest >= floor_gap - step,
            "period_s: 0 must be floored, but changes were {shortest}s apart \
             against a floor of {floor_gap}s"
        );
    }

    /// The other side of the same fix: a slow, ordinary transition must never
    /// be held. A governor that clamps everything would "solve" flashing by
    /// making Jarvis look broken instead.
    #[test]
    fn governor_does_not_touch_a_slow_transition() {
        let bind = state_binding("error").expect("error is a state"); // pulse, ~1.8s period
        let mut gov = FlashGovernor::new();
        for i in 0..20 {
            let t = i as f64 * 0.3;
            assert_eq!(
                gov.resolve(&bind, t, 0.0, 0.0, t),
                resolve(&bind, t, 0.0, 0.0),
                "a slow pattern should never be held at t={t}"
            );
        }
    }

    /// `limits.flash.scope_why` names the exact failure of a governor shared
    /// across surfaces: one surface's transitions spend a budget another
    /// surface then has to live under. Two independent instances resolving
    /// the same fast pattern must not affect each other at all.
    #[test]
    fn governor_instances_are_independent() {
        let bind = fast_strobe();
        let mut a = FlashGovernor::new();
        let mut b = FlashGovernor::new();
        // Drive `a` hard first, as if it had already spent its budget.
        for i in 0..40 {
            a.resolve(&bind, i as f64 * 0.05, 0.0, 0.0, i as f64 * 0.05);
        }
        // `b` has seen nothing yet, so its very first call must go through
        // exactly as a fresh governor's would — unaffected by `a`'s history.
        let fresh = FlashGovernor::new().resolve(&bind, 0.0, 0.0, 0.0, 0.0);
        assert_eq!(b.resolve(&bind, 0.0, 0.0, 0.0, 0.0), fresh);
    }

    /// A pattern with no real colour change (here, two `solid` calls at
    /// different times) must never be held — `min_luma_delta` exists so a
    /// governor cannot be starved by transitions that were never visible.
    #[test]
    fn governor_ignores_changes_below_the_luma_threshold() {
        let bind = state_binding("listening").expect("listening is a spec state"); // solid
        let mut gov = FlashGovernor::new();
        for i in 0..10 {
            let t = i as f64 * 0.05;
            assert_eq!(
                gov.resolve(&bind, t, 0.0, 0.0, t),
                resolve(&bind, t, 0.0, 0.0),
                "solid has no transition to hold against at t={t}"
            );
        }
    }
}
