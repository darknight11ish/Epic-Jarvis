/*
 * Shared shapes for the Jarvis notes bridge plugin.
 *
 * Nothing here imports `obsidian`: the types are plain data so the same
 * definitions can be used by the bundled plugin and by the node tests.
 */

/** One heading as Obsidian's metadata cache knows it. `text` has no `#` marks. */
export interface HeadingRef {
  level: number;
  text: string;
}

/** A bounded, read-only context pack for the active note. */
export interface NoteContext {
  path: string;
  title: string;
  headings: HeadingRef[];
  links: string[];
  backlinks: string[];
  unresolved: string[];
  frontmatterKeys: string[];
  text: string;
  truncated: boolean;
}

/** Everything the plugin persists in data.json. The token is NOT here when SecretStorage is used. */
export interface JarvisSettings {
  backendUrl: string;
  secretName: string;
  fallbackToken: string;
  templatesFolder: string;
}

/** How a write route's answer reads to the panel. */
export type WriteKind =
  | "saved"
  | "waiting"
  | "unchanged"
  | "denied"
  | "failed"
  | "conflict"
  | "error";

export interface WriteOutcome {
  kind: WriteKind;
  /** The backend's own sentence, or this plugin's honest fallback. */
  message: string;
  /** Present when a card is waiting: poll GET /api/notes/change?id= with it. */
  jobId: string;
  /** The note's new sha256, when the backend reports one. */
  sha256: string;
  /** The note's CURRENT sha256 when a change raced this request (409). */
  currentSha256: string;
  httpStatus: number;
}

/** How the capture route's answer reads to the modal. */
export type CaptureKind = "filed" | "waiting" | "not_filed" | "error";

export interface CaptureOutcome {
  kind: CaptureKind;
  message: string;
  jobId: string;
  httpStatus: number;
}

/** Where a template name came from. `jarvis` alone means the text is not readable here. */
export type TemplateSource = "vault" | "jarvis" | "both";

export interface TemplateChoice {
  name: string;
  source: TemplateSource;
}

export interface ChatOutcome {
  kind: "ok" | "error";
  answer: string;
  message: string;
}

export interface ReadOutcome {
  kind: "ok" | "error";
  path: string;
  sha256: string;
  text: string;
  message: string;
}

export interface TemplateListOutcome {
  kind: "ok" | "error";
  names: string[];
  why: string;
  message: string;
  /** The HTTP status, so the status bar can name "route not deployed" honestly. */
  httpStatus: number;
}

/**
 * The plugin's own connection state, one value per honest status-bar sentence.
 * `unknown` means the first status check has not finished (or has not run).
 */
export type StatusKind =
  | "unknown"
  | "no-token"
  | "connected"
  | "unreachable"
  | "token-refused"
  | "not-deployed"
  | "http";

/**
 * The first-run setup checklist the panel shows until the plugin is connected.
 * Pure data, so the honesty of every state can be tested without Obsidian.
 */
export interface FirstRunChecklist {
  heading: string;
  steps: string[];
  /** The one next thing to do for the current state ("" once connected). */
  next: string;
}

/**
 * The minimal shape of an HTTP answer this plugin reasons about.
 * `requestUrl`'s response has `status`, `json` (a getter that throws on bad
 * JSON) and `text`; the client narrows it to this before parsing.
 */
export interface RawAnswer {
  status: number;
  json?: unknown;
  text?: string;
}
