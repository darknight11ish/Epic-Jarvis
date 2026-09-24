/**
 * Settings -> Voice: the words, with no page in them, so every sentence the
 * section shows is tested against the backend's real answers
 * (tests/voice-settings.mjs reads tests/fixtures/voice-status-cases.json,
 * which is jarvis_speech.status() itself).
 *
 * The desktop twin of the phone's Platform checks -> "Your voice" and
 * wake-word cards (VoiceTraining.kt, ReadinessScreen.kt). Where the phone
 * has a sentence, this uses it, changed only where the phone says "this
 * phone" and the desktop has to say "your phone". Where the phone shows
 * nothing (the per-microphone prints, the stop word, Smart Turn), the words
 * are new and say only what the status says.
 *
 * Training on this PC, the strictness and private-answer settings and the
 * guided test are in voice-training.js; how a training or a setting's card
 * ended is here (`lastTrainingLine`), because it is one line of the status.
 *
 * Every field is read defensively, the phone's way: anything missing reads
 * as the refusing answer ("not trained", "off"), never as a guess.
 *
 * @module voice-settings
 */

import { currentSetting, settingLabel } from "./voice-training.js";

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const yes = (v) => v === true;
const count = (v) => (Number.isInteger(v) && v > 0 ? v : 0);

/** "1 sample", "3 samples" - the phone's `plural`. */
export function plural(n, word) {
  return n === 1 ? `1 ${word}` : `${n} ${word}s`;
}

/** The server's own sentence, first letter raised, ending in a full stop. */
export function sentence(text) {
  const s = String(text || "").trim();
  if (!s) return "";
  const raised = s.charAt(0).toUpperCase() + s.slice(1);
  return /[.!?]$/.test(raised) ? raised : `${raised}.`;
}

/** Is Jarvis trained on the owner's voice? The phone's `trained`. */
export function isTrained(status) {
  const gate = obj(status.gate);
  return status.available !== false && yes(gate.enrolled) && !yes(gate.needs_retraining);
}

/**
 * One line: is Jarvis trained on the owner's voice. The phone's
 * `VoiceTraining.stateLine`, with "this phone" made "your phone".
 */
export function summaryLine(status, approveWhere) {
  const gate = obj(status.gate);
  const training = obj(gate.training);
  const phone = obj(obj(gate.prints).phone);
  if (status.available === false) return "The voice part of Jarvis is not running on your PC.";
  if (yes(training.pending)) return `Waiting for your approval. Approve it ${approveWhere}.`;
  if (yes(gate.needs_retraining)) {
    return "Your PC's voice check changed since you trained it. Train your voice again, below or on your phone.";
  }
  if (yes(phone.trained)) return `Trained on your phone, from ${plural(count(phone.samples), "sample")}.`;
  if (yes(gate.enrolled)) return `Trained, from ${plural(count(gate.samples), "sample")}.`;
  if (String(gate.mode || "").trim().toLowerCase() === "broad") {
    return "Not trained. Jarvis is set to listen to anyone, so this is optional.";
  }
  return "Not trained yet. Until it is, Jarvis will not act on anyone's voice.";
}

/**
 * One line per microphone's voice print (`gate.prints`, since 2026-09-24):
 * the phone's, this PC's, and the older single one when it is still there.
 * A clip is checked against its own microphone's print first, then the
 * others - so an untrained PC microphone is not "not working", it uses the
 * phone's.
 */
export function printLines(status) {
  const prints = obj(obj(status.gate).prints);
  const phone = obj(prints.phone);
  const desktop = obj(prints.desktop);
  const general = obj(prints.general);
  const state = (p) => {
    if (!yes(p.trained)) return null;
    const from = `from ${plural(count(p.samples), "sample")}`;
    return yes(p.needs_retraining)
      ? `trained ${from}, but the voice check changed since, so it needs training again.`
      : `trained, ${from}.`;
  };
  const lines = [];
  lines.push({
    id: "phone",
    name: "Your phone's microphone",
    text: state(phone) || "not trained yet.",
    tone: yes(phone.trained) && !yes(phone.needs_retraining) ? "ok" : "warn",
  });
  let pc = state(desktop);
  if (!pc) {
    pc = yes(phone.trained) || yes(general.trained)
      ? "not trained on its own. It uses your phone's voice print until it is."
      : "not trained yet.";
  }
  lines.push({
    id: "desktop",
    name: "This PC's microphone",
    text: pc,
    tone: yes(desktop.trained) && !yes(desktop.needs_retraining) ? "ok" : "",
  });
  if (yes(general.trained)) {
    lines.push({
      id: "general",
      name: "Your older voice print (from before each microphone had its own)",
      text: `${state(general)} It is used for any microphone without its own, and is replaced the next time you train on your phone.`,
      tone: yes(general.needs_retraining) ? "warn" : "",
    });
  }
  return lines;
}

/**
 * Which voice check tells the owner from other people. The phone's
 * `basicCheckLine` word for word when it is the basic one; a plain line
 * when the better one is installed.
 */
export function checkLine(status) {
  const gate = obj(status.gate);
  if (status.available === false) return null;
  if (yes(gate.speaker_model)) {
    return { text: "Voice check: the better one is installed, so Jarvis can tell your voice from other people's.", tone: "ok" };
  }
  return {
    text: "Using the basic voice check, which cannot reliably tell two people apart. Install the better one on your PC for more reliable results.",
    tone: "warn",
  };
}

/** The four settings a card can loosen, as a sentence names them. */
const SETTING_NAMES = {
  strictness: "how strict the voice check is",
  privacy: "private answers",
  memory: "answers that use what Jarvis remembers",
  sensitive_memory: "answers that use sensitive saved facts",
};

/**
 * How the last training - or the last card to change a voice setting -
 * ended, or null. The phone's `lastLine` for the outcomes it has, and the
 * ones the stricter check (docs/JARVIS-API.md section 16) added: a
 * training cancelled or left to expire, "train more" (`added`), and a
 * strictness, privacy or memory card (`setting`, `value`), in the words
 * both apps use. `status` (the whole voice status) names the choice that
 * stayed when a card was said no to.
 */
export function lastTrainingLine(last, status) {
  const l = obj(last);
  const outcome = String(l.outcome || "");
  const reason = String(l.reason || "").trim().replace(/\.$/, "");
  const because = reason ? `: ${reason}.` : ".";
  const setting = SETTING_NAMES[l.setting];
  if (setting && outcome) {
    switch (outcome) {
      case "setting_changed": {
        const label = settingLabel(l.setting, l.value);
        return label ? `Approved: "${label}" is on now.` : "Approved: the change is on now.";
      }
      case "denied": {
        const label = settingLabel(l.setting, currentSetting(status, l.setting));
        return label ? `You said no, so "${label}" stays.` : "You said no, so nothing changed.";
      }
      case "timed_out":
        return "Nobody answered the card in time, so nothing changed.";
      case "withdrawn":
        return "You made it stricter while the card waited, so approving it changed nothing.";
      case "refused":
        return `Your PC refused the change to ${setting}${because}`;
      case "failed":
        return `The change to ${setting} failed${because}`;
      default:
        return `The change to ${setting}: ${outcome}.`;
    }
  }
  switch (outcome) {
    case "":
      return null;
    case "enrolled": {
      const wake = String(l.wake_check || "");
      let suffix = "";
      if (wake.startsWith("built")) suffix = " Its \"hey Jarvis\" check was built too.";
      else if (wake.startsWith("kept")) suffix = " Its \"hey Jarvis\" check is the one you had.";
      else if (wake.startsWith("being built")) suffix = " Its \"hey Jarvis\" check is being built from the same sentences.";
      else if (wake.trim()) {
        const why = wake.replace(/^not built/, "").replace(/^[:\s]+/, "").replace(/\.$/, "");
        suffix = ` Its "hey Jarvis" check was not built (${why}).`;
      }
      return `Last training was approved: ${plural(count(l.samples), "sample")} ${l.added === true ? "in the voice print now" : "saved"}.${suffix}`;
    }
    case "cancelled":
      return "The last training was cancelled, and its recordings were deleted.";
    case "expired":
      return "The last training was not finished in time, so its recordings were deleted.";
    case "threshold_set": {
      const bar = Number(l.threshold);
      return `The new setting was approved: voices must now score ${Number.isFinite(bar) ? bar.toFixed(2) : "?"} to pass.`;
    }
    case "denied":
      return "Last training was denied on the card. Nothing changed.";
    case "timed_out":
      return "Nobody answered the last training card in time. Nothing changed.";
    case "refused":
      return `Your PC refused the last training${because}`;
    case "failed":
      return `The last training failed${because}`;
    default:
      return `Last training: ${outcome}.`;
  }
}

/**
 * The talk button (push to talk): can a held-down recording get an answer
 * end to end? `listening.push_to_talk_why` is the server's own reason.
 */
export function talkLine(status) {
  const listening = obj(status.listening);
  if (yes(listening.push_to_talk)) {
    return { text: "Talk button (hold to talk): ready.", tone: "ok" };
  }
  const why = sentence(listening.push_to_talk_why);
  return { text: `Talk button (hold to talk): not ready yet.${why ? ` ${why}` : ""}`, tone: "warn" };
}

/**
 * The PC's "hey Jarvis" switch, as the phone's WakeWordCard shows it:
 * `on`, `waiting` (a card to turn it on is up) or `off`. The state is the
 * one the server last reported, never the one just asked for.
 */
export function wakeInfo(status, approveWhere) {
  const listening = obj(status.listening);
  const wake = obj(status.wake);
  const on = status.available !== false && yes(listening.wake_word);
  const waiting = !on && (yes(listening.wake_word_pending) || yes(wake.pending));
  if (on) {
    const spotter = obj(wake.spotter);
    const cannot = Object.keys(spotter).length && !yes(spotter.available)
      ? ` But this PC cannot hear it yet: ${String(spotter.why || "its wake-word model is not installed").trim().replace(/\.$/, "")}.`
      : "";
    return {
      state: "on",
      word: "On",
      text: `On. Your PC takes "hey Jarvis". It checks the phrase and your voice again before it writes down a word.${cannot}`,
    };
  }
  if (waiting) {
    return {
      state: "waiting",
      word: "Waiting",
      text: `A card to turn it on is waiting. Approve it ${approveWhere}. Nothing listens until you do.`,
    };
  }
  return {
    state: "off",
    word: "Off",
    text: "Off. Nothing can wake Jarvis by speaking a phrase; the talk button still works.",
  };
}

/**
 * The owner's own "hey Jarvis" check (`wake.verifier`): a small second
 * check, built from the "hey Jarvis" sentences of the owner's training,
 * that turns away other people saying the phrase. Null from a server that
 * does not report it.
 */
export function verifierLine(status) {
  const wake = obj(status.wake);
  if (!wake.verifier || typeof wake.verifier !== "object") return null;
  const v = obj(wake.verifier);
  if (yes(v.trained)) {
    return { text: "Your own \"hey Jarvis\" check: built from your training, so other people saying the phrase are turned away.", tone: "ok" };
  }
  const why = sentence(v.why);
  return { text: `Your own "hey Jarvis" check: not built.${why ? ` ${why}` : ""}`, tone: "" };
}

/** Saying "stop" while Jarvis talks (`wake.stop_word`). */
export function stopWordLine(status) {
  const wake = obj(status.wake);
  if (!wake.stop_word || typeof wake.stop_word !== "object") return null;
  const s = obj(wake.stop_word);
  if (yes(s.available)) {
    return { text: "The word \"stop\": this PC can hear it, to silence Jarvis while it talks.", tone: "ok" };
  }
  const why = sentence(s.why);
  return { text: `The word "stop": this PC cannot hear it yet.${why ? ` ${why}` : ""}`, tone: "" };
}

/**
 * Smart Turn (`turn`): a small model that tells "I have finished" from "I
 * am only pausing", so Jarvis does not cut in at the first pause.
 */
export function turnLine(status) {
  if (!status.turn || typeof status.turn !== "object") return null;
  const t = obj(status.turn);
  const what = "Knowing when you have finished speaking (Smart Turn)";
  if (!yes(t.enabled)) {
    return { text: `${what}: switched off in the PC's settings. Jarvis waits for a fixed pause instead.`, tone: "" };
  }
  if (yes(t.available)) {
    return { text: `${what}: on. Jarvis waits until you have finished, not just paused.`, tone: "ok" };
  }
  const why = sentence(t.why);
  return { text: `${what}: not installed on this PC, so Jarvis waits for a fixed pause instead.${why ? ` ${why}` : ""}`, tone: "" };
}
