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
//! `jarvis-reactor-kit.html`, reading the same `jarvis-visual-spec.json` the
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
                    },
                );
            }
        }

        Spec {
            colors,
            families,
            patterns,
            states,
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
    let q = &pattern.params;

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

        "gradient" => {
            let a0 = hex_of(bind.color.as_deref().or_else(|| text(q, "from")));
            let b0 = hex_of(bind.to.as_deref().or_else(|| text(q, "to")));
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
            let rate = num(q, "rate_hz", 7.0);
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
            let on = ((t / num(q, "period_s", 0.7)) % 1.0) < 0.5;
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

/// Whether a pattern's output depends on `t`. The tray uses this to decide
/// whether re-resolving is worth a timer at all: `solid` never changes, so a
/// state bound to it costs one resolve for as long as it lasts.
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
    fn spec_parses_with_its_seven_states() {
        for id in [
            "idle",
            "listening",
            "thinking",
            "speaking",
            "approval",
            "standby",
            "error",
        ] {
            assert!(has_state(id), "spec is missing the `{id}` state");
        }
        assert_eq!(spec().patterns.len(), 12, "spec should carry 12 patterns");
        assert_eq!(spec().colors.len(), 50, "spec should carry 50 colours");
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
}
