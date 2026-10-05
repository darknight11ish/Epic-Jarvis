/**
 * The Brain — everything Jarvis knows and everything it can do.
 *
 * Six views over one Rust command. `brain_read` fans out across a fixed
 * allowlist of read-only endpoints in parallel and returns them keyed by
 * section; this window renders them. Nothing here opens a stream, polls an
 * endpoint or holds its own idea of the link state — it subscribes to the one
 * connection Rust owns, like every other surface.
 *
 * ## The rule about server text
 *
 * Almost everything rendered here was written by somebody else: repository
 * descriptions from GitHub, skill names from disk, job labels, model
 * identifiers, ledger hashes. All of it reaches the DOM through `textContent`
 * or through the `el()` helper, which uses `textContent`. There is no
 * `innerHTML` in this file that touches server data. The one place the
 * window renders model text as Markdown is a deep question's answer, in
 * deep.js, through the quickbar's own renderer (markdown.js), which escapes
 * everything before it adds any markup - see that module's note.
 *
 * @module brain
 */

import {
  announce,
  APPROVE_WHERE,
  currentLink,
  followTheme,
  followZoom,
  linkWords,
  normaliseTheme,
  reconnect,
  THEMES,
  surfaceState,
  currentQueue,
  onEvent,
  onLink,
  onQueue,
  start as startLink,
} from "./jarvis-link.js";
import { addToWiki, readWiki, renderWiki } from "./wiki.js";
import { mountCardLink } from "./card-link.js";
import { createMenuManager, WORDS } from "./menu-visibility.js";
const menuManager = createMenuManager();
import { fallbackTitle } from "./card-words.js";
import { stepText } from "./step-words.js";
import { validToFromText } from "./valid-to.js";
// Whether a model can chat, and the words when it cannot (shared with the
// phone through tests/fixtures/model-chat-cases.json).
import { CANNOT_CHAT, canChat } from "./model-chat.js";
// Brain -> Projects: its own module (projects-panel.js, projects.js).
import { readAtMs as projectsReadAt, showProjects } from "./projects-panel.js";
// Brain -> Tutorials and the FAQ: its own module (tutorials.js), its own three
// commands (brain/tutorials.rs), progress kept on this PC (JARVIS-API 114).
import { showTutorials } from "./tutorials.js";
import { tellChatsGone } from "./chat-history.js";
// Brain -> History -> "Forget a time frame": its own module too.
import { openForgetRange, showForgetRange, takeAnyPlace, takePlaceExtras } from "./forget-range-panel.js";
import { BRAIN_PLACE_KEY, HISTORY_CHANGED, HISTORY_PLACE, PLACE as FORGET_RANGE_PLACE } from "./forget-range.js";
import {
  actionsOf as focusActionsOf,
  BAD_MINUTES as FOCUS_BAD_MINUTES,
  clock as focusClock,
  driftWords,
  FOCUS_MISSING,
  INTENT_HIDDEN as FOCUS_INTENT_HIDDEN,
  LABELS as FOCUS_LABELS,
  LAST_TITLE as FOCUS_LAST_TITLE,
  leftNow as focusLeftNow,
  minutesOf as focusMinutesOf,
  readFocus,
  toneOf as focusToneOf,
} from "./focus.js";
import {
  actionsOf as chatbotActionsOf,
  chatbotGroups,
  moneyLine as chatbotMoneyLine,
  usageLine as chatbotUsageLine,
  compareFormProblem,
  compareProgress,
  compareStatusLine,
  compareTalkingLine,
  memberLine as chatbotMemberLine,
  pickLine as chatbotPickLine,
  formProblem as chatbotFormProblem,
  historyLine as chatbotHistoryLine,
  limitOf as chatbotLimitOf,
  neverWords,
  POLL_MS as CHATBOT_POLL_MS,
  progressLine as chatbotProgress,
  readChatbot,
  statusLine as chatbotStatusLine,
  talkingLine as chatbotTalkingLine,
  versionLine as chatbotVersionLine,
  WORDS as CHATBOT,
} from "./chatbot.js";
import {
  actionsOf as supportActionsOf,
  detailRows as supportDetailRows,
  formProblem as supportFormProblem,
  holdingLine as supportHoldingLine,
  limitOf as supportLimitOf,
  MAX_DETAILS as SUPPORT_MAX_DETAILS,
  offerActions as supportOfferActions,
  POLL_MS as SUPPORT_POLL_MS,
  progressLine as supportProgress,
  readSupport,
  savedLine as supportSavedLine,
  statusLine as supportStatusLine,
  talkingLine as supportTalkingLine,
  versionLine as supportVersionLine,
  whoOf as supportWhoOf,
  WORDS as SUPPORT,
} from "./support.js";
import { pcLine as handoffPcLine } from "./handoff.js";
import {
  actionsOf,
  addPlaceholder,
  anyTicking,
  CLEAR_LIST_LABEL,
  clearListQuestion,
  EMPTY_JOBS,
  EMPTY_TODO,
  labelOf,
  metaOf,
  namedLists,
  readSchedule,
  SCHEDULE_MISSING,
  SNOOZE_SECONDS,
  STANDBY_BAD_TIMES,
  standbyOf,
  standbyTimes,
  tagOf,
  titleOf,
  todoItems,
  WAITING,
  WENT_OFF_ACTIONS,
  wentOffMeta,
} from "./coming-up.js";
import {
  ACCEPT_LABEL,
  ADD_STEP_LABEL,
  BY_PLACEHOLDER,
  checkinJobFor,
  checkinLines,
  EMPTY_GOALS,
  FOLLOWS_LABEL,
  GOAL_WORDS,
  GOALS_MISSING,
  benchProjectIds,
  MEASURE_LABEL,
  MEASURE_EMPTY,
  MEASURE_NONE,
  MEASURE_UNDER,
  measureChoices,
  NEEDS_CLEANED,
  NEEDS_FULL,
  NEEDS_LABEL,
  NEEDS_NONE,
  NEEDS_UNDER,
  needChoices,
  newStep,
  openCount,
  planBody,
  planIsValid,
  readGoals,
  REACHED_TAG,
  REMOVE_STEP_LABEL,
  removeStepAt,
  setNeed,
  statusLabel,
  STEP_PLACEHOLDER,
  stepRow,
  STOP_LABEL,
  UNDO_LABEL,
  UNDO_TICKED,
  UNTICKED,
} from "./goals.js";
import { fill as goalFill } from "./projects.js";
import {
  AGAIN_EMPTY as QUIZ_AGAIN_EMPTY,
  AGAIN_HEADING as QUIZ_AGAIN_HEADING,
  ANSWER_LABEL as QUIZ_ANSWER_LABEL,
  againLine as quizAgainLine,
  ANSWER_PLACEHOLDER as QUIZ_ANSWER_PLACEHOLDER,
  CLOSE_LABEL as QUIZ_CLOSE,
  answerCount as quizAnswerCount,
  CHECKING as QUIZ_CHECKING,
  countsLine as quizCountsLine,
  crisisParagraphs as quizCrisisParagraphs,
  errorWords as quizErrorWords,
  FINISH_LABEL as QUIZ_FINISH,
  GUESS_LABEL as QUIZ_GUESS,
  isCrisis as quizIsCrisis,
  isRefusal,
  KIND_LABELS as QUIZ_KIND_LABELS,
  LIMITS as QUIZ_LIMITS,
  levelLabel as quizLevelLabel,
  nextQuestion as quizNextQuestion,
  NEXT_LABEL as QUIZ_NEXT,
  progressLine as quizProgressLine,
  readCrisis as quizReadCrisis,
  readQuiz,
  readSummary,
  SOURCE_LABEL as QUIZ_SOURCE,
  STOP_LABEL as QUIZ_STOP,
  textCount as quizTextCount,
  WRITING as QUIZ_WRITING,
  QUIZ_INTRO as QUIZ_INTRO_TEXT,
  ACCENT_ROW_LABEL as QUIZ_ACCENT_ROW,
  ACCENTS as QUIZ_ACCENTS,
  DEFAULT_EXERCISE as QUIZ_DEFAULT_EXERCISE,
  DEFAULT_LEVEL as QUIZ_DEFAULT_LEVEL,
  EXERCISES as QUIZ_EXERCISES,
  insertAtCursor as quizInsertAtCursor,
  LEVEL_IDS as QUIZ_LEVEL_IDS,
  levelLine as quizLevelLine,
  markLines as quizMarkLines,
  OLD_PC_SPANISH as QUIZ_OLD_PC_SPANISH,
  SPANISH_INTRO as QUIZ_SPANISH_INTRO,
  SPANISH_TEXT_PLACEHOLDER as QUIZ_SPANISH_PLACEHOLDER,
  SPANISH_WRITING as QUIZ_SPANISH_WRITING,
  spanishStartArgs as quizSpanishStartArgs,
  topicCount as quizTopicCount,
  OUTSIDE_LINE as QUIZ_OUTSIDE_LINE,
  YT_LABEL,
  YT_OUTSIDE,
  ytFromCaptions,
  QC_BUTTON,
  QC_CANCEL,
  QC_INTRO,
  QC_LEAVES,
  QC_POLL_SECONDS,
  QC_SENDING,
  QC_CANCELLING,
  qcGiveUpOnUnknown,
  qcIsKnown,
  qcKeepPolling,
  qcOutcome,
  qcReadInfo,
} from "./quiz.js";
import { createYoutubeBlock } from "./youtube.js";
import * as Decks from "./decks.js";
import * as Topics from "./topics.js";
import { createRetirementCard } from "./retirement.js";
import {
  BUILDING as BRIEFING_BUILDING,
  EMPTY as BRIEFING_EMPTY,
  KEPT as BRIEFING_KEPT,
  lateLine,
  NOW_BUSY as BRIEFING_NOW_BUSY,
  NOW_LABEL as BRIEFING_NOW_LABEL,
  outsideLine as briefingOutsideLine,
  MISSED_BUSY,
  MISSED_DETAIL,
  MISSED_LABEL,
  MISSED_MISSING,
  readBriefing,
  readMissed,
} from "./briefing.js";
import {
  addArgs as todayAddArgs,
  briefingCards,
  cardMeta as todayCardMeta,
  cardsOf,
  cardTitle as todayCardTitle,
  DELETE_LABEL as TODAY_DELETE_LABEL,
  EMPTY_CARDS as TODAY_EMPTY,
  FROM_BRIEFING as TODAY_FROM_BRIEFING,
  LATER_TITLE as TODAY_LATER_TITLE,
  MISSING as TODAY_MISSING,
  NO_BRIEFING_TODAY,
  TAG as TODAY_TAG,
  todayCards,
} from "./today.js";
import {
  ADD_LABEL as WIDGETS_ADD_LABEL,
  DELETE_LABEL as WIDGETS_DELETE_LABEL,
  DISCARD_LABEL as WIDGETS_DISCARD_LABEL,
  draftArgs as widgetDraftArgs,
  EMPTY as WIDGETS_EMPTY,
  MAKE_LABEL as WIDGETS_MAKE_LABEL,
  MAKING_LABEL as WIDGETS_MAKING_LABEL,
  MISSING as WIDGETS_MISSING,
  PREVIEW_TITLE as WIDGETS_PREVIEW_TITLE,
  readList as readWidgets,
} from "./widget-board.js";
import {
  CHOOSE_NOTE as PHOTO_NOTE,
  mountProposal as mountPhotoProposal,
  READING as PHOTO_READING,
  shrinkPicture,
} from "./photo-reminder.js";
import { HISTORY_IMPORT, mountHistoryImport } from "./history-import.js";
import {
  HISTORY_BUTTON,
  HISTORY_BUTTON_TITLE,
  hasOtherVersions,
  readFactHistory,
  renderFactHistory,
  REPLACED_MARK,
} from "./fact-history.js";
import { createGalaxyPanel } from "./galaxy-panel.js";
import {
  buildEntityGraph,
  findNames,
  findStatus,
  groupWords,
  sharedWords,
} from "./galaxy-view.js";
import {
  addPage,
  COPIED as HISTORY_COPIED,
  CONTINUE as HISTORY_CONTINUE,
  CONTINUE_TITLE as HISTORY_CONTINUE_TITLE,
  DELETE_SUPPORT,
  FILTER_LABEL as HISTORY_FILTER_LABEL,
  FILTER_NONE as HISTORY_FILTER_NONE,
  FILTERS as HISTORY_FILTERS,
  FORGET_RANGE_LINK,
  FORGET_RANGE_LINK_TITLE,
  KEEP_SUPPORT_NOTE,
  KIND_TAG,
  KIND_TITLE,
  NO_TITLE,
  chatFactsHiddenLine,
  chatFactsIntro,
  deleteAndForgetQuestion,
  deleteChatButton,
  deleteDoneWords,
  deleteQuestion,
  readChatFacts,
  DENIED_REPLY,
  deviceTag,
  FIND_LABEL,
  FIND_PLACEHOLDER,
  findCountWords,
  findMatches,
  hitsWords,
  chatFactsTaught,
  chatFactsTaughtHidden,
  keepConfirm,
  keepLabel,
  keepNeedsConfirm,
  keepReply,
  KEEP_CHOICES,
  notRecordingLine,
  OFF_REPLY,
  olderThan,
  ON_REPLY,
  PAGE as HISTORY_PAGE,
  readConversation,
  readHistory,
  readSearch,
  refreshRows,
  renderSnippet,
  renderTranscript,
  rowMeta,
  SEARCH_MIN,
  SEARCH_NONE,
  SEARCH_NOTE,
  SEARCHING,
  searchMoreWords,
  SWITCH_DETAIL,
  forkDoneWords,
  forkedRow,
  forkErrorWords,
  MARK_BUSY,
  markDoneWords,
  markErrorWords,
  readMarks,
  withForkedRow,
  SWITCH_LABEL,
  TAINT_TITLE,
  whenLine,
  whenWords,
} from "./history-view.js";
import {
  ADD_TAG,
  ALL as TAG_ALL,
  bannerText as tagBannerText,
  BANNER_CANCEL,
  clipTagName,
  COLOURS as TAG_COLOURS,
  deleteConfirm as tagDeleteConfirm,
  DELETE_TAG,
  errorWords as tagErrorWords,
  filedWords,
  fileUnderWords,
  groupRows,
  headerText as tagHeaderText,
  iconNode,
  ICONS as TAG_ICONS,
  isOpen as sectionIsOpen,
  MAX_TAGS,
  MOVE_DOWN,
  MOVE_PLACEHOLDER,
  MOVE_TO,
  MOVE_UP,
  NAME_LABEL,
  NO_TAG,
  NO_TAG_CHATS,
  NOT_LOADED_LINE,
  readFilePlace,
  readOpenFlags,
  readTags,
  RENAME as TAG_RENAME,
  saveOpenFlag,
  sectionLabel,
  SUGGEST_ASKING,
  SUGGEST_LABEL,
  SUGGEST_OLD_PC,
  SUGGEST_READING,
  readSuggest,
  suggestErrorWords,
  suggestStateLine,
  suggestWaitingLine,
  suggestWriteResult,
  tagById,
  TAG_CHIPS_LABEL,
  TAGS_EDITOR_NOTE,
  TAGS_TITLE,
  UNFILED_WORDS,
  UNTAGGED,
  validTagName,
} from "./history-tags.js";
import {
  addPage as addAutoPage,
  AUTO_MISSING,
  AUTO_OFF,
  CANCEL_LABEL,
  CANCEL_TITLE,
  EMPTY as AUTO_EMPTY,
  ERASE_ALSO_CHAT_CONFIRM,
  otherFactsInChat,
  ERASE_LABEL,
  ERASE_TITLE,
  ERASED,
  ERASED_AND_CHAT_DELETED,
  ERASED_NO_CHAT,
  eraseAlsoChatNamedConfirm,
  readFactChat,
  erasedAt,
  erasedLine,
  eraseQuestion,
  factMeta,
  FORGOTTEN,
  forgetQuestion,
  lastLineNow,
  LEARNING_OFF_NOTE,
  olderThan as olderAuto,
  PAGE as AUTO_PAGE,
  readAuto,
  refreshRows as refreshAutoRows,
  rememberedLine,
  savedIds,
  SENSITIVE_NEEDS_AUTO,
  stillOffLine,
  SWITCHES as AUTO_SWITCHES,
  VOICE_MARK,
  VOICE_TITLE,
} from "./auto-learn.js";
import {
  cardLines,
  plainDateOf,
  statusRows,
  WORDS as MEMORY_WORDS,
} from "./memory-words.js";
import {
  isPinned,
  PIN_LABEL,
  PIN_TITLE,
  PINNED,
  PROFILE_DETAIL,
  PROFILE_EMPTY,
  PROFILE_MISSING,
  readProfile,
  UNPIN_LABEL,
  UNPIN_TITLE,
  UNPINNED,
  usedLine,
} from "./memory-profile.js";
import {
  isShared,
  readShared,
  SHARE_LABEL,
  SHARE_TITLE,
  SHARED,
  SHARED_EMPTY,
  SHARED_MISSING,
  UNSHARE_LABEL,
  UNSHARE_TITLE,
  UNSHARED,
} from "./memory-shared.js";
import {
  missingLine,
  NOT_CURRENT_MARK,
  PINNED_MARK,
  readUsed,
  REMEMBERED_LINE_TITLE,
  REMEMBERED_TITLE,
  rowActions,
  SHOW_ALL,
} from "./memory-used.js";
import {
  ABOUT_EMPTY,
  ABOUT_MAX,
  aboutTitle,
  alsoLine,
  calledLine,
  entitiesFor,
  entityById,
  LINKED_LABEL,
  MERGE_JOINED,
  MERGE_KEPT,
  MERGE_NO,
  MERGE_NO_TITLE,
  MERGE_NOTE,
  MERGE_SOURCE,
  MERGE_TAG,
  MERGE_YES,
  MERGE_YES_TITLE,
  moreLine,
  readEntities,
} from "./memory-entities.js";
import {
  askDeep,
  leadLine as deepLead,
  POLL_MS as DEEP_POLL_MS,
  readDeep,
  renderJobs as renderDeepJobs,
  RUNNING as DEEP_RUNNING,
  runningCount,
} from "./deep.js";
import { loadModelsCache, saveModelsCache } from "./models-cache.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/**
 * Every view, and what the topbar says about it.
 *
 * Order here is the rail's order (see `TAB_ORDER` below), and it has to match
 * the order of the `<li>`s in brain.html: the arrow keys, `Home` and `End`
 * all count through this list, so a view named here that has no button over
 * there is a tab the keyboard walks onto and cannot land on. The everyday
 * views come first, then the four behind "Advanced" — galaxy, now (called
 * Live until 2026-09-28), trust and watch, unchanged and still fully wired,
 * just not on the rail by default. `tests/rail-tabs.mjs` holds the two lists
 * equal, and `tests/a11y.mjs` holds the roving tabindex they feed.
 */
const VIEWS = {
  memory: { title: "Memory", sub: "what Jarvis has learned about you" },
  history: { title: "History", sub: "your conversations, kept on this PC" },
  faculties: { title: "Model", sub: "models, compute, skills, memory" },
  work: { title: "Work", sub: "coming up, jobs in flight and what can be put back" },
  projects: { title: "Projects", sub: "what you are working on, and the numbers you track" },
  // The owner's own request (2026-10-05): a skippable intro and a tutorial for
  // each major part, the same ones the phone shows, with reading progress kept
  // on this PC and shared by both apps (JARVIS-API section 114).
  tutorials: { title: "Tutorials", sub: "how Jarvis works, step by step - and the answers to the usual questions" },
  galaxy: { title: "Galaxy", sub: "the people and things Jarvis knows about" },
  // "Now" - called "Live" until 2026-09-28, renamed by the owner so it is
  // not confused with Jarvis Live (the voice conversation).
  now: { title: "Now", sub: "what Jarvis is doing" },
  trust: { title: "Trust", sub: "the audit chain and what outside text tried" },
  watch: { title: "Watch", sub: "the GitHub watchlist" },
};

/** Views tucked behind the "Advanced" disclosure until it is opened. */
const ADVANCED_VIEWS = ["galaxy", "now", "trust", "watch"];

/** Which sections each view needs, so a switch reads only what it will show. */
const VIEW_SECTIONS = {
  // The people and things facts name (galaxy-view.js) - the same list, and
  // the same Windows Hello rule, as "About <name>" on the Memory tab. Not
  // `graph` any more: privacy finding B1 (brain/routes.rs).
  galaxy: ["memory_entities"],
  now: ["attention", "status"],
  faculties: ["models", "compute", "skills", "memory", "memory_pending"],
  // memory_entities: the names under each fact, for "About <name>"
  // (memory-entities.js). Hidden with the other memory lists.
  memory: ["memory_facts", "memory_pending", "memory_entities"],
  // Read through its own commands (brain/history.rs), not brain_read.
  history: [],
  // "Activity" (past approvals, read-only): the same `/api/pending` the
  // stream already polls for the live queue, read again here for its
  // `history` half - see brain/routes.rs's own comment on why one more GET
  // to that route is the right way to reach it.
  work: ["jobs", "undo", "gate_history"],
  // Read through its own command (brain/projects.rs), by projects-panel.js.
  projects: [],
  trust: ["content_risk", "ledger"],
  watch: ["watch", "watch_report"],
};

// The theme ids come from jarvis-link.js, the one list every window shares.

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  title: $("view-title"),
  sub: $("view-sub"),
  banner: $("banner"),
  linkPill: $("link-pill"),
  linkText: $("link-text"),
  refresh: $("refresh"),
  reconnectLink: $("reconnect-link"),
  freshness: $("freshness"),
  rushStrip: $("rush-strip"),
  toast: $("toast"),
  themePicker: $("theme-picker"),
  rail: $("rail-nav"),
  advancedToggle: $("rail-advanced-toggle"),
  countAdvanced: $("count-advanced"),

  canvas: $("graph-canvas"),
  graphEmpty: $("graph-empty"),
  graphEmptyText: $("graph-empty-text"),
  graphStat: $("graph-stat"),
  graphSearch: $("graph-search"),
  graphFind: $("graph-find"),
  graphEmptyActions: $("graph-empty-actions"),
  nodeActions: $("node-actions"),
  galaxyFacts: $("galaxy-facts"),
  galaxyFactsTitle: $("galaxy-facts-title"),
  galaxyFactsNote: $("galaxy-facts-note"),
  galaxyFactsList: $("galaxy-facts-list"),
  galaxyFactsCount: $("galaxy-facts-count"),
  galaxyFactsLive: $("galaxy-facts-live"),
  galaxyFactsFoot: $("galaxy-facts-foot"),
  graphRefit: $("graph-refit"),
  legend: $("legend"),
  inspector: $("inspector"),
  inspectorClose: $("inspector-close"),
  nodeKind: $("node-kind"),
  nodeLabel: $("node-label"),
  nodeFacts: $("node-facts"),
  nodeLinks: $("node-links"),

  nowFace: $("now-face"),
  nowActivity: $("now-activity"),
  nowPower: $("now-power"),
  nowKv: $("now-kv"),
  budget: $("budget"),
  budgetNote: $("budget-note"),
  trace: $("trace"),
  traceClear: $("trace-clear"),

  models: $("models"),
  compute: $("compute"),
  skills: $("skills"),
  memory: $("memory"),
  memoryLearning: $("memory-learning"),
  memoryProposals: $("memory-proposals"),
  memoryFacts: $("memory-facts"),
  memoryFactsFilter: $("memory-facts-filter"),
  memoryAuto: $("memory-auto"),
  memoryAutoList: $("memory-auto-list"),
  memorySavedLine: $("memory-saved-line"),
  memoryProfile: $("memory-profile"),
  memoryShared: $("memory-shared"),
  memoryAboutCard: $("memory-about-card"),
  memoryAboutTitle: $("memory-about-title"),
  memoryAbout: $("memory-about"),
  jobs: $("jobs"),
  undo: $("undo"),
  activity: $("activity"),
  activityFilters: $("activity-filters"),
  focus: $("focus"),
  focusForm: $("focus-form"),
  focusMinutes: $("focus-minutes"),
  focusOn: $("focus-on"),
  focusStart: $("focus-start"),
  focusReport: $("focus-report"),
  chatbot: $("chatbot"),
  chatbotLimits: $("chatbot-limits"),
  chatbotLog: $("chatbot-log"),
  chatbotVersion: $("chatbot-version"),
  chatbotForm: $("chatbot-form"),
  chatbotWhich: $("chatbot-which"),
  chatbotGoal: $("chatbot-goal"),
  chatbotMessages: $("chatbot-messages"),
  chatbotMinutes: $("chatbot-minutes"),
  chatbotNever: $("chatbot-never"),
  chatbotStart: $("chatbot-start"),
  chatbotCompare: $("chatbot-compare"),
  chatbotCompareToggle: $("chatbot-compare-toggle"),
  chatbotCompareDetail: $("chatbot-compare-detail"),
  chatbotCompareNote: $("chatbot-compare-note"),
  chatbotWhichLabel: $("chatbot-which-label"),
  chatbotMoney: $("chatbot-money"),
  chatbotSeveral: $("chatbot-several"),
  chatbotSeveralLegend: $("chatbot-several-legend"),
  chatbotSeveralList: $("chatbot-several-list"),
  support: $("support"),
  supportLog: $("support-log"),
  supportVersion: $("support-version"),
  supportForm: $("support-form"),
  supportCompany: $("support-company"),
  supportTerms: $("support-terms"),
  supportAddressLabel: $("support-address-label"),
  supportAddress: $("support-address"),
  supportGoal: $("support-goal"),
  supportRows: $("support-rows"),
  supportAdd: $("support-add"),
  supportMessages: $("support-messages"),
  supportMinutes: $("support-minutes"),
  supportQueue: $("support-queue"),
  supportStart: $("support-start"),
  comingUp: $("coming-up"),
  photoFile: $("photo-file"),
  photoChoose: $("photo-choose"),
  photoNote: $("photo-note"),
  photoProposal: $("photo-proposal"),
  historyImportWords: $("history-import-words"),
  historyImportStart: $("history-import-start"),
  historyImportStop: $("history-import-stop"),
  historyImportHow: $("history-import-how"),
  todoList: $("todo-list"),
  todoForm: $("todo-form"),
  todoText: $("todo-text"),
  todoAdd: $("todo-add"),
  wentOffPart: $("went-off-part"),
  wentOff: $("went-off"),
  namedLists: $("named-lists"),
  listsNote: $("lists-note"),
  standbyForm: $("standby-form"),
  standbyStart: $("standby-start"),
  standbyEnd: $("standby-end"),
  standbyAdd: $("standby-add"),
  standbyIsSet: $("standby-is-set"),
  goalsList: $("goals-list"),
  goalsNewForm: $("goals-new-form"),
  goalsNewText: $("goals-new-text"),
  goalsNewAdd: $("goals-new-add"),
  quizStartForm: $("quiz-start-form"),
  quizText: $("quiz-text"),
  quizTextCount: $("quiz-text-count"),
  quizStart: $("quiz-start"),
  quizRun: $("quiz-run"),
  quizMode: $("quiz-mode"),
  quizSpanish: $("quiz-spanish"),
  quizNotice: $("quiz-notice"),
  quizLevel: $("quiz-level"),
  quizExercise: $("quiz-exercise"),
  quizTopic: $("quiz-topic"),
  quizTopicCount: $("quiz-topic-count"),
  quizIntro: $("quiz-intro"),
  quizOutside: $("quiz-outside"),
  decksIntro: $("decks-intro"),
  decksBody: $("decks-body"),
  today: $("today"),
  widgets: $("widgets"),
  widgetsForm: $("widgets-form"),
  widgetsWords: $("widgets-words"),
  widgetsMake: $("widgets-make"),
  todayForm: $("today-form"),
  todayText: $("today-text"),
  todayAt: $("today-at"),
  todayDays: $("today-days"),
  todayAdd: $("today-add"),
  briefing: $("briefing"),
  briefingNow: $("briefing-now"),
  briefingMissed: $("briefing-missed"),
  contentRisk: $("content-risk"),
  ledger: $("ledger"),
  watch: $("watch"),
  watchReport: $("watch-report"),

  watchForm: $("watch-form"),
  watchAddOpen: $("watch-add-open"),
  watchCancel: $("watch-cancel"),
  watchSeen: $("watch-seen"),
  countLive: $("count-now"),
  countWork: $("count-work"),
  countTrust: $("count-trust"),
  countWatch: $("count-watch"),
  countMemory: $("count-memory"),
};

const state = {
  view: "memory",
  /** Section name → last body read. */
  data: {},
  /** True while a read is in flight, so a repaint cannot stack them. */
  loading: false,
  /** Section name → `{ why, at }` for a read that failed while an older good
   *  read is still being shown. The phone keeps the last read that worked,
   *  and so does this: a failed re-read used to overwrite it. */
  failed: {},
  /** Section name → when it last read successfully (ms). */
  readAt: {},
  /** A model switch or install sent and waiting on its approval card. */
  modelAsk: null,
  /** What became of the last model request whose card left the queue
   *  without a `model` event: shown in its place until the next ask. */
  modelAskEnded: null,
  graph: null,
  trace: [],
};

/** Whether the four views behind "Advanced" are on the rail right now. */
let advancedOpen = false;

/**
 * Seeds the Model pane from disk before the first live read comes back
 * (or fails), so a cold start with Jarvis not running has something to
 * paint at once instead of a blank pane while the request times out
 * (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md). `state.readAt.models` is set
 * to when the cache was actually read, not to now, so the "as of" wording
 * in `renderModels` is honest from the very first paint.
 *
 * If the first live read of "models" then succeeds, `load()` overwrites
 * both in the ordinary way. If it fails, `load()`'s existing "keep the last
 * good read, mark it stale" logic (`state.failed`) takes over unchanged -
 * this cache is just that "last good read" surviving a restart.
 */
(function seedModelsFromDisk() {
  const cached = loadModelsCache();
  if (!cached) return;
  state.data.models = { available: true, ...cached.models };
  state.readAt.models = cached.at;
})();

/* "Bring in old chats" (history-import.js; JARVIS-API.md section 85): a
   ChatGPT, Claude, Gemini or DeepSeek export, picked on this PC by the Windows dialog
   in Rust, read in the background by the PC, which only PROPOSES - every
   fact waits under "Waiting for you", one card each. Mounted here, before
   the first render, so render("memory") can ask it where a run is. */
const historyImport = dom.historyImportStart && dom.historyImportStop && dom.historyImportWords
  ? mountHistoryImport({
    words: dom.historyImportWords,
    start: dom.historyImportStart,
    stop: dom.historyImportStop,
  }, {
    invoke,
    canAct: () => linkWords(currentLink()).canAct,
    showing: () => state.view === "memory" && !document.hidden,
    say: (said, tone) => toast(said, tone),
    // New cards were made: re-read "Waiting for you" (the queue itself -
    // never anything from the import).
    onWaiting: () => load(["memory_pending"], { quiet: true }).then(() => {
      if (state.view === "memory") renderProposals();
    }),
  })
  : null;
if (dom.historyImportHow) dom.historyImportHow.textContent = HISTORY_IMPORT.how;
let historyImportAt = 0;

/** Ask the PC where an import is: on opening Memory, at most every 5 s. */
function renderHistoryImport() {
  if (!historyImport || !IS_TAURI) return;
  if (Date.now() - historyImportAt < 5000) return;
  historyImportAt = Date.now();
  historyImport.refresh();
}

/* ==========================================================================
   Plumbing
   ========================================================================== */

async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[brain] invoke("${command}") skipped — no desktop backend`);
    return null;
  }
  return TAURI.core.invoke(command, args);
}

let toastTimer = null;
function toast(message, tone = "") {
  announce(String(message), tone === "bad" ? "assertive" : "polite");
  dom.toast.textContent = String(message);
  dom.toast.dataset.tone = tone;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.hidden = true;
  }, tone === "bad" ? 9000 : 4200);
}

/** Builds an element. Text always goes in as text — see the module note. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function rows(container, items, render, emptyText) {
  container.replaceChildren();
  if (!items || !items.length) {
    // A node (whyNode) goes in as it is: it may carry a Retry button.
    container.append(emptyText instanceof Node ? emptyText : el("p", "empty", emptyText));
    return;
  }
  const list = el("div", "rows");
  for (const item of items) list.append(render(item));
  container.append(list);
}

/** A row: a tag, a title with meta beneath it, and optional actions. */
function row({ tag, state: tagState, title, meta, actions }) {
  const item = el("div", "row-item");
  const t = el("span", "row-tag", tag || "");
  if (tagState) t.dataset.state = tagState;
  item.append(t);

  const main = el("div", "row-main");
  main.append(el("span", "row-title", title));
  for (const line of [].concat(meta || []).filter(Boolean)) {
    main.append(el("span", "row-meta", line));
  }
  item.append(main);

  const box = el("div", "row-actions");
  for (const action of actions || []) box.append(action);
  item.append(box);
  return item;
}

/** Buttons that act on the server, re-synced whenever the link changes. */
const liveButtons = new Set();

const STALE_TITLE = "Waiting for the link to catch up. Nothing can be sent until it does.";

/** The retirement what-if (brain.work.retirement, retirement.js): the numbers
 *  typed there live in its boxes only and go when the tab, the window or the
 *  private lists go. */
const retirementCard = createRetirementCard({
  root: document.getElementById("retirement-body"),
  titleEl: document.getElementById("retirement-title"),
  invoke,
  isTauri: IS_TAURI,
  canAct: () => linkWords(currentLink()).canAct,
  live: {
    add: (b) => { liveButtons.add(b); syncLiveButton(b); },
    sync: (b) => syncLiveButton(b),
  },
  announce,
  listen: IS_TAURI && TAURI.event && TAURI.event.listen
    ? (name, fn) => TAURI.event.listen(name, fn) : null,
  view: () => state.view,
});

/** Greys a `live` button while the link cannot be confirmed (rule 4). */
function syncLiveButton(b) {
  const blocked = !linkWords(currentLink()).canAct;
  b.disabled = blocked || b.dataset.busy === "true";
  b.title = blocked ? STALE_TITLE : b.dataset.title || "";
}

function syncLiveButtons() {
  for (const b of liveButtons) {
    if (!b.isConnected) liveButtons.delete(b);
    else syncLiveButton(b);
  }
}

/**
 * `live: true` for anything that sends a decision or a change: it is greyed,
 * with the reason as its title, while the link is stale or down - the
 * phone's `canAct`. Before this every Brain button stayed clickable on a stale
 * link and failed afterwards with a toast. Rust refuses the same calls too
 * (brain.rs require_link_live); this only stops the click being offered.
 */
function button(label, onClick, { danger = false, title = "", live = false } = {}) {
  const b = el("button", `btn small${danger ? " danger" : ""}`, label);
  b.type = "button";
  if (title) b.title = title;
  b.dataset.title = title;
  if (live) {
    liveButtons.add(b);
    syncLiveButton(b);
  }
  b.addEventListener("click", async () => {
    b.disabled = true;
    b.dataset.busy = "true";
    try {
      await onClick();
    } finally {
      b.dataset.busy = "false";
      if (live) syncLiveButton(b);
      else b.disabled = false;
    }
  });
  return b;
}

/** Model files are gigabytes; "4863.7 MB" is a number nobody reads as 4.7 GB. */
const bytes = (n) => {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 ** 2) return `${(v / 1024).toFixed(1)} kB`;
  if (v < 1024 ** 3) return `${(v / 1024 ** 2).toFixed(1)} MB`;
  return `${(v / 1024 ** 3).toFixed(1)} GB`;
};

function ago(epochSeconds) {
  const t = Number(epochSeconds);
  if (!Number.isFinite(t) || t <= 0) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/**
 * What is known about one section, in the phone's four states (SectionRead):
 *
 * - `reading`: nothing has come back yet.
 * - `absent`: a 404 or 503, or the backend's own `{available: false}` - this
 *   machine does not have the module. A fact, not a fault, so no Retry.
 * - `failed`: the read failed and there is nothing older to show. Amber, with
 *   a Retry.
 * - `stale`: the read failed, and the last read that worked is still shown.
 * - `data`: the last read worked.
 *
 * All four used to be one faint grey line.
 */
function sectionState(section) {
  const body = state.data[section];
  const failure = state.failed[section];
  if (!body) return failure ? { kind: "failed", why: failure.why } : { kind: "reading" };
  if (body.available === false) {
    return body.read === "failed"
      ? { kind: "failed", why: String(body.error || "no reason given") }
      : { kind: "absent" };
  }
  return failure ? { kind: "stale", why: failure.why, at: failure.at } : { kind: "data" };
}

/** The line a pane shows instead of its content, or null when it has some. */
function unavailable(section) {
  const s = sectionState(section);
  if (s.kind === "reading") return "Reading…";
  if (s.kind === "absent") return "Not on this backend.";
  if (s.kind === "failed") return `Could not read this: ${s.why}`;
  return null;
}

/** Reads one section again. Changes nothing on the server. */
function retryButton(section) {
  const b = el("button", "btn small", "Retry");
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    await load([section], { quiet: true });
    render(state.view);
  });
  return b;
}

/** `unavailable`, as a node: amber with a Retry for a failure, grey otherwise. */
function whyNode(section, tag = "p") {
  const s = sectionState(section);
  const node = el(tag, "empty", unavailable(section) || "");
  if (s.kind === "failed") {
    node.classList.add("failed");
    node.append(" ", retryButton(section));
  }
  return node;
}

/** Every view also reads the rush latch, so it is never out of sight. */
function sectionsFor(view) {
  const sections = VIEW_SECTIONS[view] || [];
  return sections.includes("content_risk") ? sections : [...sections, "content_risk"];
}

/* ==========================================================================
   Reading
   ========================================================================== */

async function load(sections, { quiet = false } = {}) {
  if (!IS_TAURI) {
    dom.banner.hidden = false;
    dom.banner.textContent =
      "No desktop backend — this is a browser preview, so nothing is being read.";
    return;
  }
  if (state.loading) return;
  state.loading = true;
  dom.refresh.disabled = true;
  try {
    const body = await invoke("brain_read", { sections });
    const now = Date.now();
    for (const [section, value] of Object.entries(body || {})) {
      const failedRead = value && value.available === false && value.read === "failed";
      const had = state.data[section];
      const hadGood = had && had.available !== false;
      if (failedRead && hadGood) {
        // Keep what worked last time on screen, and say it is old. The rush
        // latch above all: a latch seen a minute ago must not vanish because
        // the next check failed.
        state.failed[section] = { why: String(value.error || "no reason given"), at: now };
      } else {
        state.data[section] = value;
        // The overnight-tidy card is handed out once a day, to the first
        // read that asks for it - which may be the Faculties view's, not
        // the Memory tab's. Noted here so it is not lost either way.
        if (section === "memory_pending" && value) noteSleepOffer(value.setup);
        // Every good models read is written to disk (never on a failed or
        // "absent" one - `value.available` covers both), so the Model pane
        // has something honest to show after a restart, not only within
        // this window's lifetime. See models-cache.js for what is kept.
        if (section === "models" && value && value.available !== false) {
          saveModelsCache(value, now);
        }
        if (failedRead) {
          state.failed[section] = { why: String(value.error || "no reason given"), at: now };
        } else {
          delete state.failed[section];
          state.readAt[section] = now;
        }
      }
    }
    // One banner for the window, for FAILURES only - a module this backend
    // does not have is said in its own pane, in grey, and is not a fault.
    // Each failure gets its own Retry, which only reads again.
    const failed = sections.filter((s) => {
      const k = sectionState(s).kind;
      return k === "failed" || k === "stale";
    });
    dom.banner.hidden = failed.length === 0;
    dom.banner.replaceChildren();
    for (const s of failed) {
      const st = sectionState(s);
      const line = el(
        "span",
        "banner-item",
        st.kind === "stale"
          ? `Could not read ${s.replace(/_/g, " ")}: ${st.why}. What is shown is from the last read that worked.`
          : `Could not read ${s.replace(/_/g, " ")}: ${st.why}.`
      );
      line.append(" ", retryButton(s));
      dom.banner.append(line);
    }
  } catch (error) {
    dom.banner.hidden = false;
    dom.banner.textContent = String((error && error.message) || error);
    if (!quiet) toast(String((error && error.message) || error), "bad");
  } finally {
    state.loading = false;
    dom.refresh.disabled = false;
    paintFreshness();
  }
}

async function showView(name, { reload = true } = {}) {
  if (!VIEWS[name]) return;
  state.view = name;
  dom.root.dataset.view = name;
  dom.title.textContent = VIEWS[name].title;
  dom.sub.textContent = VIEWS[name].sub;

  const visible = visibleTabOrder();
  const focusedTab = visible.includes(name) ? name : (visible[0] || name);
  for (const key of Object.keys(VIEWS)) {
    const tab = $(`tab-${key}`);
    const view = $(`view-${key}`);
    if (tab) {
      tab.setAttribute("aria-selected", String(key === name));
      // Roving tabindex: exactly one tab is in the document's tab order, and
      // it is the selected one (or first visible if current is not in visible order).
      tab.tabIndex = key === focusedTab ? 0 : -1;
    }
    if (view) view.hidden = key !== name;
  }

  if (reload) await load(sectionsFor(name));
  render(name);
  if (name === "galaxy") fitCanvas();
}

/** Paints whichever view is showing from `state.data`. */
function render(name) {
  if (name !== "work") retirementCard.leave();
  switch (name) {
    case "galaxy":
      renderGraph();
      break;
    case "now":
      renderLive();
      break;
    case "faculties":
      renderModels();
      renderCompute();
      renderSkills();
      renderMemory();
      break;
    case "memory":
      renderLearning();
      renderTopics();
      renderHistoryImport();
      renderProfile();
      renderShared();
      renderAuto();
      renderProposals();
      renderFacts();
      renderWikiPlate();
      renderDeepPlate();
      break;
    case "history":
      renderHistory();
      showForgetRange();
      break;
    case "work":
      renderFocus();
      renderChatbot();
      renderSupport();
      renderComingUp();
      renderGoals();
      renderQuiz();
      renderDecks();
      retirementCard.enter();
      renderBriefing();
      renderJobs();
      renderUndo();
      renderActivity();
      break;
    case "projects":
      // Its own read; the status line is painted again once it is in.
      showProjects().then(() => paintFreshness(), () => paintFreshness());
      break;
    case "trust":
      renderContentRisk();
      renderLedger();
      break;
    case "watch":
      renderWatch();
      renderWatchReport();
      break;
    case "tutorials":
      // Its own read of the catalogue and the FAQ, and it draws itself: the
      // steps, where the owner has read to, and the search box (tutorials.js).
      // Nothing here is held on a stale link - reading a tutorial acts on
      // nothing - so there is no freshness wait before it can be shown.
      showTutorials($("tutorials-root")).catch((error) => {
        $("tutorials-root").textContent = `The tutorials could not be opened: ${error.message}`;
      });
      break;
  }
  renderRushStrip();
  renderCounts();
  paintFreshness();
}

/**
 * The rush latch, at the top of every view. The phone puts it first on Mind
 * and keeps the last latch it saw when a check fails (BrainScreen.kt); this
 * does the same. Nothing here clears a latch - Retry only reads again.
 */
function renderRushStrip() {
  const s = sectionState("content_risk");
  const risk = state.data.content_risk;
  const rush = risk && risk.available !== false ? risk.rush : null;
  dom.rushStrip.replaceChildren();
  dom.rushStrip.dataset.tone = "";
  if (rush) {
    dom.rushStrip.dataset.tone = "bad";
    const line = el(
      "span",
      "",
      "A rush latch is active: outside text tried to hurry a decision. It expires on its own."
    );
    dom.rushStrip.append(line);
    // `phrase` or `quote`: jarvis_content_risk is only on the owner's PC, the
    // phone read `quote` and this read `phrase`, so both apps read both.
    const said = rush.phrase || rush.quote;
    if (said) dom.rushStrip.append(" ", el("span", "rush-quote", `“${said}”`));
    if (s.kind === "stale") {
      const mins = Math.max(0, Math.round((Date.now() - (state.readAt.content_risk || Date.now())) / 60000));
      dom.rushStrip.append(
        " ",
        el("span", "rush-age", `Last seen ${mins} min ago — the newest check failed: ${s.why}.`),
        " ",
        retryButton("content_risk")
      );
    }
    dom.rushStrip.hidden = false;
    return;
  }
  if (s.kind === "failed" || s.kind === "stale") {
    dom.rushStrip.dataset.tone = "warn";
    dom.rushStrip.append(
      el("span", "", `Could not check for a rush latch: ${s.why}.`),
      " ",
      retryButton("content_risk")
    );
    dom.rushStrip.hidden = false;
    return;
  }
  dom.rushStrip.hidden = true;
}

/** "3 min ago" from a millisecond time. */
function agoMs(ms) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

/**
 * How old the numbers on screen are - the phone's Freshness line. Reads
 * "Refreshing…" while a read runs, and says everything is last known while
 * the link is stale or down.
 */
function paintFreshness() {
  if (!dom.freshness) return;
  const sections = (VIEW_SECTIONS[state.view] || []).filter((s) => state.readAt[s]);
  let oldest = sections.length ? Math.min(...sections.map((s) => state.readAt[s])) : 0;
  // History and Projects are read through their own commands, not
  // brain_read, so VIEW_SECTIONS lists nothing for them - and the line used
  // to say "reading…" for ever (the chat audit, 2026-09-28, desktop B3).
  const own = OWN_READS[state.view];
  if (!sections.length && own) oldest = own() || 0;
  const what = (VIEWS[state.view] && VIEWS[state.view].title.toLowerCase()) || "this";
  const words = linkWords(currentLink());
  dom.freshness.dataset.tone = words.canAct ? "" : "warn";
  if (!words.canAct) {
    dom.freshness.textContent = oldest
      ? `${words.short}. Everything below is last known, read ${agoMs(oldest)}.`
      : `${words.short}. Nothing has been read yet.`;
  } else if (state.loading) {
    dom.freshness.textContent = "Refreshing…";
  } else if (oldest) {
    dom.freshness.textContent = `Link live · ${what} read ${agoMs(oldest)}`;
  } else {
    dom.freshness.textContent = "Link live · reading…";
  }
}
setInterval(paintFreshness, 15000);

/** When a view read through its own command last read successfully. */
const OWN_READS = {
  history: () => chats.readOkAt,
  projects: () => projectsReadAt(),
};

function renderCounts() {
  const set = (node, n) => {
    node.hidden = !n;
    node.textContent = String(n || "");
  };
  const jobs = (state.data.jobs && state.data.jobs.jobs) || [];
  set(
    dom.countWork,
    jobs.filter((j) => j.state === "running" || j.state === "queued").length
  );
  // Kept at 1 while the last latch seen is still on screen, even if the
  // newest check failed - a failed read is not an all-clear.
  const risk = state.data.content_risk;
  const trustCount = risk && risk.available !== false && risk.rush ? 1 : 0;
  set(dom.countTrust, trustCount);
  const watch = state.data.watch;
  const watchCount = (watch && watch.waiting_for_you) || 0;
  set(dom.countWatch, watchCount);
  const attention = currentLink().attention;
  const liveCount = attention.known ? attention.pending : 0;
  set(dom.countLive, liveCount);
  // Proposals waiting. This is the badge that matters most, because the
  // extractor fills that queue on its own - nobody asked for the thing that
  // is waiting, so nothing else would tell you it is there.
  const proposed = state.data.memory_pending;
  set(dom.countMemory, waitingCount(proposed));

  // Live, Trust and Watch carry their own badges but sit behind "Advanced"
  // by default, where nobody sees them. Rolled into one count on the
  // toggle itself while it is collapsed, so closing it cannot make
  // something waiting on the user go quiet.
  set(dom.countAdvanced, advancedOpen ? 0 : liveCount + trustCount + watchCount);
}

/* ==========================================================================
   Faculties
   ========================================================================== */

/** Shown when there is no data at all - never a good read this session,
 *  and nothing cached from an earlier one either. Not "Could not read
 *  this": that would read as a fault on a machine that has simply never
 *  once been connected to Jarvis while it was running. */
const MODELS_NEVER_CONNECTED =
  "There's nothing to show yet — open this once while Jarvis is running on your PC.";

/** The offline banner's "as of" time, in the same short form the rest of
 *  the window uses for a moment in the past (not a duration - the owner
 *  asked for a real time here, not "3h ago", since it may be days old). */
function asOfWords(atMs) {
  if (!atMs) return "an earlier connection";
  try {
    return new Date(atMs).toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "an earlier connection";
  }
}

function renderModels() {
  const live = sectionState("models");
  const body = state.data.models;
  // A body of `{available: false, ...}` (never read, or read but failed
  // with nothing older to show, or an explicit "this backend does not have
  // it") counts the same as no body at all here: none of them are data to
  // draw the pane from. Checking `body` alone would treat a failed read's
  // own `{available: false}` shape as "there is something to show" - it
  // very nearly did.
  const haveGoodData = Boolean(body) && body.available !== false;

  if (!haveGoodData) {
    // The backend itself says it has no models module (a 404/503, not "no
    // answer at all") - a fact about this machine, not a stale read, so the
    // cache (if load() kept one) is not shown in its place.
    if (live.kind === "absent") return rows(dom.models, [], null, whyNode("models"));
    // 'reading' or 'failed', and there is nothing to fall back to - not
    // even a disk cache: never a good read, this session or any earlier
    // one on this PC. Saying "could not read" would blame a fault where
    // there has simply never once been a connection.
    const node = el("p", "empty", live.kind === "reading" ? "Reading…" : MODELS_NEVER_CONNECTED);
    if (live.kind === "failed") node.append(" ", retryButton("models"));
    return rows(dom.models, [], null, node);
  }

  // The most recent read failed and this is the last one that worked -
  // whether that was earlier this session or, via models-cache.js, from
  // before the app last restarted. Either way it must never be painted as
  // if it were live: rule 4, and the design doc's whole point.
  const stale = live.kind === "stale";

  const current = body.current || body.active || "";
  const previous = body.previous || "";
  const installed = Array.isArray(body.installed) ? body.installed : [];

  const items = installed.length
    ? installed.map((m) => (typeof m === "string" ? { ref: m } : m))
    : current
      ? [{ ref: current }]
      : [];

  rows(
    dom.models,
    items,
    (m) => {
      const ref = String(m.ref || m.name || m.model || "");
      // Which model is current is honestly cacheable, but only labelled as
      // of the cache's own time, never drawn as "this is running now" -
      // that claim needs a live read (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md
      // section 5). The quieter note below the list carries it while stale.
      const isCurrent = ref && ref === current;
      const showAsLiveCurrent = isCurrent && !stale;
      const chats = canChat(m, ref);
      const actions = [];
      if (ref && !isCurrent && chats) {
        actions.push(
          button("Use", () => modelAction("switch", ref), {
            title: `Ask to switch to this model. You approve it ${APPROVE_WHERE}.`,
            live: true,
          })
        );
      }
      return row({
        tag: showAsLiveCurrent ? "active" : "installed",
        state: showAsLiveCurrent ? "present" : "",
        title: ref || "(unnamed)",
        meta: [
          m.size ? bytes(m.size) : "",
          m.family || "",
          ref && ref === previous ? "the previous model" : "",
          // Said rather than a greyed-out button: why there is no "Use".
          chats ? "" : CANNOT_CHAT,
        ],
        actions,
      });
    },
    "No models reported."
  );

  if (stale) {
    // The one clearly-labelled sentence this whole feature is for: what is
    // shown below is old, roughly how old, and what is deliberately not
    // shown because only a running Jarvis could know it.
    dom.models.prepend(
      el(
        "p",
        "banner models-offline",
        `Jarvis isn't running right now, so this list is from the last time it was: ` +
          `${asOfWords(state.readAt.models)}. Sizes and names are probably still right. ` +
          `What's actually loaded right now isn't shown, since only a running Jarvis knows that.`
      )
    );
    if (current) {
      dom.models.append(
        el("p", "note", `As of that last connection, ${current} was the one in use.`)
      );
    }
  }

  // Is the model actually ON the graphics card, and how fast have answers
  // been? Both are live measurements of what Ollama is doing right now, not
  // facts about a file on disk - shown stale they would read as "this is
  // happening now" and be wrong, so they are skipped outright while stale
  // rather than guessed at (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md section
  // 5). `speed` is also never written to the disk cache in the first place
  // (models-cache.js), so there would be nothing to show here even for a
  // read this window never actually saw fail.
  const speed = stale ? { line: "", slowdown: "", lastSwitch: "" } : modelSpeed(body.speed, current);
  if (!stale) {
    // llama.cpp spills layers to the CPU silently and Ollama still reports
    // the model as loaded and healthy, so the only symptom is that
    // everything got slow - and the owner blames Jarvis rather than the fit.
    //
    // Prepended after `rows()` rather than composed before it, because
    // `rows()` calls replaceChildren on whatever it is given, and the
    // rollback button below appends to the same element.
    const off = body.offload || {};
    if (off.status === "cpu" || off.status === "partial") {
      dom.models.prepend(
        el("p", "banner", String(off.note || "The model is not on the graphics card."))
      );
    }

    // How fast answers have been (speed-record.patch). docs/JARVIS-API.md
    // says show exactly three things: one line for the current model, the
    // backend's own note only when it got slower, and its own old-vs-new
    // sentence beside the rollback button. The phone does the same
    // (ApiModels.kt ModelSpeed); this window ignored the block entirely.
    if (speed.line) dom.models.append(el("p", "model-speed", speed.line));
    if (speed.slowdown) dom.models.append(el("p", "banner", speed.slowdown));
  }

  if (previous && previous !== current) {
    if (speed.lastSwitch) dom.models.append(el("p", "model-speed", speed.lastSwitch));
    const back = el("div", "row-actions");
    back.style.paddingTop = "10px";
    back.append(
      button(`Roll back to ${previous}`, () => modelAction("rollback"), {
        title: "Goes back to the previous model at once. Rollback never waits for approval.",
        live: true,
      })
    );
    dom.models.append(back);
  }

  // A switch or install that raised a card and is waiting on it. Said here
  // until the next `model` event or until its card leaves the queue,
  // because the toast is gone in seconds and "switched" was never true - the
  // server only raised an approval card (JARVIS-API: tier `ask`, "success
  // means a card was raised").
  if (state.modelAsk) {
    dom.models.append(
      el(
        "p",
        "banner model-ask",
        state.modelAsk.action === "install"
          ? `Waiting for your approval: installing ${state.modelAsk.ref}. Approve it ${APPROVE_WHERE} — nothing downloads until you do.`
          : `Waiting for your approval: switching to ${state.modelAsk.ref}. Approve it ${APPROVE_WHERE} — nothing changes until you do.`
      )
    );
  } else if (state.modelAskEnded) {
    // Its card left the queue without the model changing: what happened,
    // in the words the phone uses, instead of a line that silently vanished
    // (or, before this, one that kept claiming a card was waiting).
    dom.models.append(el("p", "banner model-ask-ended", state.modelAskEnded));
  }

  dom.models.append(installForm());

  const comp = state.data.compute || {};
  const compPlan = comp.plan && typeof comp.plan === "object" ? comp.plan : comp;
  const devices = Array.isArray(compPlan.devices) ? compPlan.devices : [];
  const firstMb = Number(devices[0]?.total_mb ?? compPlan.total_mb ?? comp.total_mb ?? 0);
  if (firstMb >= 15360 && firstMb <= 35000) {
    dom.models.append(
      el("p", "note model-preset-suggestion", "Your card can hold the 14B at 32K — try the Smartest preset in Settings > Hardware and models.")
    );
  }
}

/**
 * "Install a model": the name typed by hand, the way it would be given to
 * Ollama (`ollama pull <name>`). No catalogue, no list of what could be
 * installed - the same shape the phone has (BrainScreen.kt ModelsPlate) and
 * the owner's 2026-09-20 rule. Posting it only raises an approval card
 * (tier `ask`); nothing downloads until that is approved.
 */
function installForm() {
  const wrap = el("div", "model-install");
  wrap.append(
    el(
      "p",
      "model-speed",
      "Install a model this computer does not have yet. Type its name the way you " +
        "would give it to Ollama, for example llama3.1:8b. This only asks: nothing " +
        `downloads until you approve its card ${APPROVE_WHERE}.`
    )
  );
  const line = el("div", "row-actions");
  const input = el("input", "field");
  input.id = "model-install-ref";
  input.type = "text";
  input.placeholder = "model:tag";
  input.spellcheck = false;
  input.autocomplete = "off";
  input.setAttribute("aria-label", "Model to install");
  const go = button(
    "Install",
    async () => {
      const ref = input.value.trim();
      if (!ref) {
        toast("Type the model's name first, for example llama3.1:8b.", "bad");
        return;
      }
      await modelAction("install", ref);
    },
    { title: `Ask to install this model. You approve it ${APPROVE_WHERE}.`, live: true }
  );
  go.id = "model-install";
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") go.click();
  });
  line.append(input, go);
  wrap.append(line);
  return wrap;
}

/**
 * The `speed` block of /api/models, in the same three pieces the phone shows
 * (ApiModels.kt ModelSpeed.from, ported line for line). Numbers only - the
 * block carries no conversation text.
 */
function modelSpeed(speed, current) {
  const out = { line: "", slowdown: "", lastSwitch: "" };
  if (!speed || typeof speed !== "object" || speed.available === false) return out;
  const num = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);
  const text = (v) => (typeof v === "string" && v.trim() ? v : "");
  const byModel = speed.by_model && typeof speed.by_model === "object" ? speed.by_model : {};
  const bare = (name) => String(name || "").replace(/:latest$/, "");
  const key = current && (byModel[current] ? current
    : Object.keys(byModel).find((k) => bare(k) === bare(current)));
  const mine = key ? byModel[key] : null;
  if (mine && typeof mine === "object") {
    const parts = [];
    const wps = num(mine.median_words_per_s);
    const firstMs = num(mine.median_first_word_ms);
    if (wps !== null) parts.push(`about ${Math.round(wps)} words a second`);
    if (firstMs !== null) {
      const tenths = Math.round(firstMs / 100);
      parts.push(`first word after ${Math.floor(tenths / 10)}.${tenths % 10} s`);
    }
    // Milestone 7: the share of the conversation Ollama already had read
    // from the last question and did not read again (its prompt cache;
    // jarvis_speed.reused_percent). Missing on older rows and older Ollamas.
    const reused = num(mine.median_reused_percent);
    if (reused !== null) {
      parts.push(`${Math.round(Math.min(100, reused))}% of the conversation reused, not read again`);
    }
    if (parts.length) {
      const n = num(mine.answers);
      const over = n ? ` (middle of the last ${Math.round(n)} answers)` : "";
      out.line = `Recent answers: ${parts.join(", ")}${over}.`;
    }
  }
  if (speed.slowdown && speed.slowdown.slower === true) out.slowdown = text(speed.note);
  if (speed.last_switch && typeof speed.last_switch === "object") {
    out.lastSwitch = text(speed.last_switch_note);
  }
  return out;
}

/**
 * How long a model request whose card has left the queue waits for the
 * `model` event an approval brings, before saying it was not approved. An
 * approval on the phone reaches this window only as the card disappearing,
 * a moment before the `model` event - so "gone" alone is not "denied".
 */
const MODEL_ASK_GRACE_MS = 3000;

/** The card raised by the ask, found by difference like the phone's
 *  `noteModelRequest`: the one waiting now that was not waiting before.
 *  Anything other than exactly one new card is `null` - the line then lasts
 *  until the next `model` event, as it always did. */
async function findNewCard(waitingBefore) {
  try {
    const payload = await invoke("get_pending_approvals");
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    const fresh = items
      .map((row) => (row && row.id !== undefined && row.id !== null ? String(row.id) : ""))
      .filter((id) => id && !waitingBefore.has(id));
    return fresh.length === 1 ? fresh[0] : null;
  } catch (error) {
    return null;
  }
}

/** The model line's words once its card is no longer waiting. */
function modelAskEndedWords(ask, outcome) {
  const what = ask.action === "install" ? `installing ${ask.ref}` : `switching to ${ask.ref}`;
  if (outcome === "denied") {
    return `You denied ${what}. Nothing changed.`;
  }
  return `The request for ${what} is no longer waiting: it was denied or ran out of time. Nothing changed.`;
}

/** Its card left the queue: settle the "Waiting for your approval" line. */
function modelCardGone(ask) {
  if (state.modelAsk !== ask || ask.gone) return;
  ask.gone = true;
  if (ask.decided === "denied") {
    state.modelAsk = null;
    state.modelAskEnded = modelAskEndedWords(ask, "denied");
    if (state.view === "faculties") renderModels();
    return;
  }
  // Approved here, or decided elsewhere, or expired: an approval brings a
  // `model` event, which clears the line on its own. Only when none comes
  // is it said that the request was not approved.
  setTimeout(() => {
    if (state.modelAsk !== ask) return;
    state.modelAsk = null;
    if (ask.decided !== "approved") state.modelAskEnded = modelAskEndedWords(ask, "gone");
    if (state.view === "faculties") renderModels();
  }, MODEL_ASK_GRACE_MS);
}

/** Whether the approval queue holds a card to turn learning on, wherever it
 *  was raised (`learning_enable`, docs/JARVIS-API.md `/api/memory/learning`). */
function learningCardWaiting(queue = currentQueue()) {
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  return items.some((item) => item && item.action === "learning_enable");
}
let learningCardSeen = false;

/** The learning card left the queue: read the switch after the backend has
 *  had a moment to apply an approval. On: the line goes (renderLearning).
 *  Still off: it was denied or ran out of time, and that is said. */
onQueue((queue) => {
  // A learning card raised elsewhere (the phone, or another window) came
  // or went: the waiting line follows it, as History's does.
  const waitingNow = learningCardWaiting(queue);
  if (waitingNow !== learningCardSeen) {
    learningCardSeen = waitingNow;
    if (state.view === "memory") renderLearning();
  }
  const ask = state.learningAsk;
  if (!ask || !ask.cardId || ask.gone) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (items.some((item) => item && item.id === ask.cardId)) return;
  ask.gone = true;
  setTimeout(async () => {
    if (state.learningAsk !== ask) return;
    await refreshMemory();
    if (state.learningAsk === ask) {
      state.learningAsk = null;
      const facts = state.data.memory_facts || {};
      if (facts.learning !== true) {
        toast("Background learning stays off: the card was denied or ran out of time.", "bad");
      }
      renderLearning();
    }
  }, MODEL_ASK_GRACE_MS);
});

onQueue((queue) => {
  const ask = state.modelAsk;
  if (!ask || !ask.cardId) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (!items.some((item) => item && item.id === ask.cardId)) modelCardGone(ask);
});

// Decided on THIS PC (the Jarvis bar or the widget): Rust says which way
// the moment it is accepted, so "denied" can be said as a fact rather than
// as "denied or ran out of time".
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  TAURI.event.listen("approval-resolved", (event) => {
    const resolved = (event && event.payload) || {};
    const ask = state.modelAsk;
    if (!ask || !ask.cardId || String(resolved.id) !== ask.cardId) return;
    ask.decided = resolved.approved ? "approved" : "denied";
    modelCardGone(ask);
  });
}

async function modelAction(action, reference) {
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke("brain_model", { action, reference: reference || null });
    // Switch and install are tier `ask`: success means an approval card was
    // raised, not that anything changed. This used to toast "Model
    // switched." Rollback is tier `auto` and really has happened.
    state.modelAskEnded = null;
    if (action === "rollback") {
      toast("Rolled back.", "ok");
    } else {
      const ask = { action, ref: String(reference || ""), cardId: null };
      state.modelAsk = ask;
      ask.cardId = await findNewCard(waitingBefore);
      toast(
        action === "install"
          ? `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing downloads until you do.`
          : `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing changes until you do.`,
        "ok"
      );
    }
    if (out) await load(["models"], { quiet: true });
    render("faculties");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
}

/**
 * The compute plan. Reads the keys `jarvis_compute.Plan.as_dict()` really
 * sends - text_model, text_on, vision_resident, tts_resident, simulated,
 * prefer, devices[], why, total_mb (backend/rebuilt/jarvis_compute.py) -
 * checked by backend/test_connection_contract.py. It used to read only
 * plan/mode/gpu/vram_total_mb/gpu_layers/context/note, none of which that
 * module sends, so this pane always said "No compute plan reported." The old
 * names are still read as a fallback for a differently-built backend, and a
 * body wrapped as {plan: {...}} is unwrapped.
 */
function renderCompute() {
  const raw = state.data.compute || {};
  const body = raw.plan && typeof raw.plan === "object" ? raw.plan : raw;
  const why = unavailable("compute");
  dom.compute.replaceChildren();
  if (why) return dom.compute.append(whyNode("compute"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", String(v)));
  };
  const gb = (mb) => `${(Number(mb) / 1024).toFixed(1)} GB`;
  const yesNo = (v) => (v === true ? "kept loaded" : v === false ? "loaded when needed" : undefined);
  const where = (on) => {
    if (typeof on !== "string" || !on) return on;
    if (on === "cpu") return "the processor (no graphics card in use)";
    return on.replace(/cuda:(\d+)/g, "graphics card $1").replace(/\+/g, " + ");
  };

  add("Model", body.text_model);
  add("Runs on", where(body.text_on));
  add("Picture model", yesNo(body.vision_resident));
  add("Voice model", yesNo(body.tts_resident));
  add("Aims for", body.prefer === "speed" ? "speed" : body.prefer === "capability"
    ? "capability (spread over every card)" : body.prefer);
  const devices = Array.isArray(body.devices) ? body.devices : [];
  devices.forEach((d) => {
    if (!d || typeof d !== "object") return;
    const free = d.free_mb != null ? `${gb(d.free_mb)} free of ` : "";
    add(`Card ${d.index ?? ""}`.trim(),
      `${d.name || "graphics card"} - ${free}${d.total_mb != null ? gb(d.total_mb) : "?"}`);
  });
  if (!devices.length && Number(body.total_mb) > 0) add("Graphics memory", gb(body.total_mb));
  add("Why", body.why);
  if (body.simulated === true) {
    add("Measured?", "No - no graphics card could be asked, so this is a guess");
  }

  // Older / other backends.
  add("Plan", body.mode || body.strategy);
  add("GPU", body.gpu || body.device);
  add(
    "VRAM",
    body.vram_total_mb
      ? `${((body.vram_used_mb || 0) / 1024).toFixed(1)} / ${(body.vram_total_mb / 1024).toFixed(1)} GB`
      : body.vram
  );
  add("Layers on GPU", body.gpu_layers ?? body.n_gpu_layers);
  add("Context", body.context ?? body.n_ctx);
  add("Note", body.note || body.reason);
  if (!dl.childElementCount) {
    return dom.compute.append(el("p", "empty", "No compute plan reported."));
  }
  dom.compute.append(dl);
  const firstMb = Number(devices[0]?.total_mb ?? body.total_mb ?? 0);
  if (firstMb >= 15360 && firstMb <= 35000) {
    dom.compute.append(
      el("p", "note model-preset-suggestion", "Your card can hold the 14B at 32K — try the Smartest preset in Settings > Hardware and models.")
    );
  }
}

function renderSkills() {
  const body = state.data.skills || {};
  const why = unavailable("skills");
  if (why) return rows(dom.skills, [], null, whyNode("skills"));
  const list = Array.isArray(body.skills) ? body.skills : Array.isArray(body) ? body : [];

  rows(
    dom.skills,
    list,
    (s) => {
      const name = String(s.name || s.id || "(unnamed)");
      const verdict = String(s.verdict || s.scan || (s.ok === false ? "flagged" : "clean"));
      // skill-notes.patch sends each skill's notes: short lines Jarvis wrote
      // for itself about the skill, which go into the model's context with
      // the skill every time it is used. Anything that steers an answer has
      // to be readable here. Strings, or objects carrying the words in
      // `note`/`text` - whichever the backend's jarvis_skills.py stores.
      const notes = (Array.isArray(s.notes) ? s.notes : [])
        .map((n) => (typeof n === "string" ? n : n && (n.note || n.text)))
        .filter((n) => typeof n === "string" && n.trim())
        .map((n) => `Jarvis's note: “${n.trim()}”`);
      return row({
        tag: verdict,
        state: /clean|ok|pass/i.test(verdict) ? "ok" : "warn",
        title: name,
        meta: [s.description || s.summary || "", s.path || "", ...notes],
        actions: [
          button(
            "Remove",
            async () => {
              // Removal is not undoable from here: there is deliberately no
              // route that installs a skill, because installing runs the
              // scanner and the gate. So it asks, in those words.
              if (
                !confirm(
                  `Remove the skill "${name}"?\n\n` +
                    "This cannot be undone from the desktop. There is no route " +
                    "that installs a skill — installing runs the scanner and " +
                    "the gate, and a client that bypassed both would be the " +
                    "whole attack. Putting it back means putting the file back " +
                    "on the machine."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_remove_skill", { name });
                toast(`Removed ${name}.`, "ok");
                await load(["skills"], { quiet: true });
                render("faculties");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      });
    },
    "No skills installed, or the scanner has quarantined them all."
  );
}

function renderMemory() {
  const body = state.data.memory || {};
  const pending = state.data.memory_pending || {};
  dom.memory.replaceChildren();
  const why = unavailable("memory");
  if (why) return dom.memory.append(whyNode("memory"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  // The names jarvis_memory's MemoryStore.status() really sends (checked by
  // backend/test_memory_honesty.py against the real store). This used to
  // read path/model/documents/chunks, which status() never sends, so Store
  // and Embedding never showed - and "Facts" was the total, retired ones
  // included, while the pane said nothing about how many were retired.
  // The rows are memory-words.js's statusRows, the phone's
  // MemoryCounts.fields word for word (one fixture holds both, the memory
  // review's I8): the re-ranker's state and "Said again" are among them.
  // The store's file path is the PC's own, so only this window shows it.
  for (const [k, v] of statusRows(body)) add(k, v);
  if (typeof body.db === "string") add("Store", body.db);
  if (dl.childElementCount) dom.memory.append(dl);
  // The overnight tidy (2026-09-28, backend/jarvis_tidy.py): once it is on,
  // turning it off is one tap, at once - it only makes Jarvis ask less, so
  // it is not held on a stale link (brain.rs brain_memory_sleep_time).
  // Turning it ON stays the daily offer's Enable.
  if (body.sleep_time && body.sleep_time.enabled === true) {
    const box = el("div", "row-actions");
    box.append(button("Turn off overnight tidying", async () => {
      await memoryWrite("brain_memory_sleep_time", { enabled: false }, OVERNIGHT_OFF_SAID);
      if (state.data.memory && state.data.memory.sleep_time) {
        state.data.memory.sleep_time.enabled = false;
      }
      renderMemory();
    }, { title: "No more \u201cStill true?\u201d or \u201cWhich is true now?\u201d cards. "
               + "Cards already waiting stay until you answer them." }));
    dom.memory.append(box);
  }

  const proposed = Array.isArray(pending.pending) ? pending.pending : [];
  if (pending.hidden === true && waitingCount(pending)) {
    dom.memory.append(el("h3", "inspector-sub", "Proposed facts"));
    dom.memory.append(el("p", "note",
      `${waitingCount(pending)} waiting, hidden. Press Show on the Memory tab to see them.`));
  }
  if (proposed.length) {
    dom.memory.append(el("h3", "inspector-sub", "Proposed facts"));
    const list = el("div", "rows");
    for (const p of proposed.slice(0, 12)) {
      list.append(
        row({
          tag: "proposed",
          state: "warn",
          // Decided in the Memory tab, one card at a time, where each card
          // shows what it would replace and any warning. This pane says a
          // decision is waiting; it does not offer to make it.
          title: String(p.text || "(no text)"),
          meta: [p.source ? `from ${p.source}` : "", ago(p.created)],
          actions: [],
        })
      );
    }
    dom.memory.append(list);
    dom.memory.append(
      el(
        "p",
        "note",
        // This used to say "decided in the approval gate, one at a time - not
        // from here", which sent the owner somewhere that can never hold the
        // item: memory proposals live in jarvis_extract's table and never
        // enter jarvis_gate's queue. The Memory tab of this window is where
        // they are decided (the HUD only points there); this pane cannot.
        "Decide these in the Memory tab, one at a time. The approval gate " +
          "never sees them — memory proposals live in their own queue."
      )
    );
  }
  if (!dom.memory.childElementCount) {
    dom.memory.append(el("p", "empty", "The memory store reported nothing."));
  }
}

/* ==========================================================================
   Memory — what Jarvis has learned, and every way to change it

   Every write here is one fact and one decision. There is no select-all, no
   "keep the rest", no bulk anything, and that is not an omission: the server
   takes a single integer id per call and forgetting cannot be undone.
   ========================================================================== */

/* The "as of" view.
 *
 * `null` means the normal, live pane. A number is epoch seconds, and while it
 * is set the facts list shows what Jarvis BELIEVED then rather than what is
 * true now, with every editing control gone — the past is not editable, and a
 * Forget button that silently acted on today's store would be a trap.
 *
 * Held here rather than in `state.data` because it is a question this window
 * is asking, not an answer the server sent, and `load()` overwrites the
 * latter on every refresh. */
let memoryAsOf = null;
let memoryAsOfRows = null;

/**
 * The daily overnight-tidy card, cached client-side once seen.
 *
 * The server marks the day's offer as made the moment this window reads
 * `/api/memory/pending?...&sleep_offer=1` (routes.rs) - not when the owner
 * acts on it - so a second read the same day, from ANY write on this pane
 * refreshing the section, comes back with the card already gone. (Only
 * clients that show the card send `sleep_offer=1`; the HUD page does not,
 * so it no longer uses the offer up.) `load()` notes it whichever view read
 * the section. Without this cache the card would flash once
 * and vanish the instant the owner clicked Keep or Discard on an unrelated
 * proposal, before they had a chance to read it.
 *
 * `dismissed` is a second, separate flag rather than just clearing the cache:
 * `state.data` can still be holding the very same non-null offer from the
 * last real fetch (nothing forced a re-read since), so a plain
 * `cachedSleepOffer = null` followed by this function's own re-render would
 * immediately re-adopt the exact offer just turned down. Both flags reset
 * only on a fresh launch of this window - matching what "not now" and "stop
 * asking" actually promise, which is today, not forever.
 */
let cachedSleepOffer = null;
let sleepOfferDismissed = false;

/** What turning the overnight tidy on and off says (2026-09-28): the
 *  phone's MemoryWords.OVERNIGHT_ON_SAID / OVERNIGHT_OFF_SAID, word for word. */
const OVERNIGHT_ON_SAID = "Overnight tidying is on. Once a day Jarvis may ask about facts that "
  + "look out of date, with review cards. Nothing changes without your yes.";
const OVERNIGHT_OFF_SAID = "Overnight tidying is off. No more cards from it.";

function noteSleepOffer(setup) {
  if (setup && setup.sleep_time_offer && !cachedSleepOffer && !sleepOfferDismissed) {
    cachedSleepOffer = setup.sleep_time_offer;
  }
}

function dismissSleepOffer() {
  cachedSleepOffer = null;
  sleepOfferDismissed = true;
}

/**
 * Asks, optionally, for the date a fact stopped being true — the bi-temporal
 * correction `jarvis_memory.retire()` has supported since `bitemporal.patch`
 * but that neither Reword nor Forget had any way to ask for until now.
 *
 * Returns a unix-seconds timestamp, `null` for "just now" (the field left
 * blank — the common case, and identical to the old behaviour), or
 * `undefined` if the owner cancelled. `undefined` is a distinct answer from
 * `null` on purpose: the caller must abort the whole action on a cancel,
 * not quietly fall back to "just now" for a date the owner never confirmed.
 *
 * An answer that is not a usable date ("last week", a day next month) asks
 * again, with the reason above the question and the typed words kept. It
 * used to show an error and return `undefined` - so a Forget the owner had
 * already confirmed was dropped without a word (play tester, 2026-09-27).
 * What counts as a date is `validToFromText` (valid-to.js).
 */
function promptValidTo(message) {
  let typed = "";
  let problem = "";
  for (;;) {
    const raw = window.prompt(problem ? `${problem}\n\n${message}` : message, typed);
    if (raw === null) return undefined;
    const answer = validToFromText(raw);
    if (!("error" in answer)) return answer.seconds;
    typed = raw;
    problem = answer.error;
  }
}

/** Dates before this are refused by "What did you know on…". The server
 * ignores a moment before September 2001 and answers with today's facts
 * instead; no Jarvis existed then anyway. The phone uses the same year. */
const AS_OF_EARLIEST_YEAR = 2002;

/**
 * "What did Jarvis know on YYYY-MM-DD?" as the moment to ask the server
 * about: the LAST second of that day, local time, so "the 1st" includes
 * everything learned on the 1st - or null for a date that cannot be asked
 * (not a real date, before AS_OF_EARLIEST_YEAR, or after today).
 *
 * `new Date("2026-06-01")` would be UTC midnight - the START of the day, in
 * the wrong zone. The phone's `MemoryDates.knownAt` (net/Learning.kt) is the
 * same rule, and backend/test_memory_honesty.py runs this function against
 * the numbers the phone's unit test pins, so the same typed date means the
 * same moment on both apps.
 */
function asOfSeconds(typed, now) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(typed == null ? "" : typed).trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const end = new Date(y, mo - 1, d, 23, 59, 59);
  // new Date() quietly rolls 31 February into March; a date that does not
  // exist is refused instead. (And years 0-99 into the 1900s.)
  if (end.getFullYear() !== y || end.getMonth() !== mo - 1 || end.getDate() !== d) return null;
  if (y < AS_OF_EARLIEST_YEAR) return null;
  const today = now instanceof Date ? now : new Date();
  const lastOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59, 59);
  if (end.getTime() > lastOfToday.getTime()) return null;
  return Math.floor(end.getTime() / 1000);
}

/** Re-read the pane's own sections and repaint. Used after every write. */
async function refreshMemory() {
  // The "Saved automatically" list is read through its own command
  // (brain/auto_learn.rs), next to the pane's sections: a Forget or a
  // decision changes it too.
  await Promise.all([load(VIEW_SECTIONS.memory, { quiet: true }), loadAuto(), loadProfile(),
    loadShared(), loadSavedFacts(), loadTopics()]);
  render("memory");
  reloadShown();
}

/** Turn a write into a toast, so no handler swallows a failure silently. */
async function memoryWrite(command, args, okText) {
  // Nothing may be written while the pane is showing a past moment. Every
  // caller already hides its buttons in that state, so reaching here means a
  // code path was added that forgot to — which is exactly when a guard earns
  // its keep, because the write would have landed on TODAY'S store while the
  // owner was looking at last June.
  if (memoryAsOf !== null) {
    toast("This is what Jarvis believed then. Return to now to change anything.", "bad");
    return null;
  }
  try {
    const out = await invoke(command, args);
    // The server can refuse while still answering 200 — the learning switch
    // does exactly that when JARVIS_EXTRACT is off in the environment. Render
    // what came back, never what was asked for.
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else {
      toast(typeof okText === "function" ? okText(out) : okText, "ok");
      // Forgotten, reworded or erased, from either list: no longer current, so not
      // "saved automatically" any more - even on a page "Load older" brought
      // in, which the re-read below does not replace.
      if (command === "brain_memory_forget" || command === "brain_memory_edit"
          || command === "brain_memory_erase") {
        autoL.rows = autoL.rows.filter((r) => r.id !== args.id);
      }
    }
    await refreshMemory();
    return out;
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
    return null;
  }
}

/* ==========================================================================
   Private answers - Settings' "Windows Hello for memory lists and chat history"

   While it is on, brain_read hands the two memory lists back EMPTY, with
   `hidden: true` and how many there were (lock.rs redact_private). The
   entries never reach this page until Show has passed Windows Hello, so
   nothing here can be read round: this only draws the count and the button.
   ========================================================================== */

/** How many proposals are waiting, whether or not they are shown. */
function waitingCount(pending) {
  if (!pending) return 0;
  if (pending.hidden === true) return Number(pending.hidden_count) || 0;
  return (Array.isArray(pending.pending) && pending.pending.length) || 0;
}

function hiddenNode(count, what) {
  const n = Number(count) || 0;
  const box = el("div", "private-hidden");
  box.append(el("p", "empty", n
    ? `${n} ${what === "facts" ? (n === 1 ? "fact" : "facts") : "waiting"}, hidden until Windows Hello confirms it is you.`
    : "Hidden until Windows Hello confirms it is you."));
  box.append(button("Show", revealPrivate,
    { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
  return box;
}

async function revealPrivate() {
  try {
    await invoke("reveal_private_answers");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
    return;
  }
  await refreshMemory();
  // The deep questions, on the Memory tab, come back with the lists.
  deep.at = 0;
  fx.at = 0;
  cb.at = 0;
  if (state.view !== "memory") render(state.view);
  else loadDeep();
}

// Settings changed, or the owner was away long enough that a Show ended:
// read the lists again - Rust decides whether they come back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const reread = async () => {
    // The chatbot card's goal and conversation are hidden with the lists too,
    // and the support chat's goal, details and transcript.
    cb.at = 0;
    sp.at = 0;
    await load(VIEW_SECTIONS.memory, { quiet: true });
    render(state.view);
  };
  TAURI.event.listen("security-changed", reread);
  TAURI.event.listen("private-hidden", reread);
}

function renderLearning() {
  const facts = state.data.memory_facts || {};
  const pending = state.data.memory_pending || {};
  dom.memoryLearning.replaceChildren();
  const why = unavailable("memory_facts");
  if (why) return dom.memoryLearning.append(whyNode("memory_facts"));

  // A past view's rows came from a Show; hidden again, it goes back to now.
  if (facts.hidden === true) {
    memoryAsOf = null;
    memoryAsOfRows = null;
  }
  const on = facts.learning === true;
  if (on) state.learningAsk = null;    // the card was approved
  const setup = pending.setup || {};
  noteSleepOffer(setup);

  if (cachedSleepOffer) {
    const offer = cachedSleepOffer;
    const list = el("div", "rows");
    list.append(
      row({
        tag: "offer",
        state: "warn",
        title: String(offer.title || "Overnight memory tidying"),
        meta: [String(offer.body || "")],
        actions: [
          // Dismissed BEFORE the write, not after: `memoryWrite`'s own
          // success path calls `refreshMemory()` internally, before this
          // handler gets a chance to run anything of its own, and that
          // re-render has to see `sleepOfferDismissed` already set - or
          // `noteSleepOffer` re-adopts the very offer this click is
          // answering, from whatever `pending.setup` that fetch still holds.
          // Rolled back below only if the write actually fails, so a network
          // hiccup never costs the owner their only way to act on this until
          // tomorrow's offer. The immediate `render("memory")` also closes
          // the double-click window that dismissing-after left open: the
          // card leaves the DOM right away, taking its buttons with it,
          // instead of staying clickable for the length of the write.
          button("Enable", async () => {
            const answered = cachedSleepOffer;
            dismissSleepOffer();
            render("memory");
            // The truth, which is short (2026-09-28, backend/jarvis_tidy.py):
            // it only ASKS, with review cards, and changes nothing by itself.
            const out = await memoryWrite("brain_memory_sleep_time", { enabled: true },
              OVERNIGHT_ON_SAID);
            if (!out || out.ok === false) {
              cachedSleepOffer = answered;
              sleepOfferDismissed = false;
              render("memory");
            }
          }, { title: "Once a day, Jarvis may ask you about facts that look out of date, "
                     + "with review cards - at most five a night. No fact changes without "
                     + "your yes on that one fact.", live: true }),
          button("Not now", async () => {
            dismissSleepOffer();
            render("memory");
            // A real answer since 2026-09-25 (jarvis_backoff.py): the PC keeps
            // this offer quiet for a day, then a week, then a month. Not held
            // on a stale link - it only makes Jarvis quieter - and a failure
            // only means the offer may come back tomorrow, as before.
            try {
              const out = await invoke("brain_memory_sleep_time", { notNow: true });
              if (out && out.said) toast(String(out.said), "ok");
            } catch {
              /* dismissed here either way */
            }
          }, { title: "Not now. Jarvis waits a day before offering this again, then a week, "
                     + "then a month. Turning it on stays one tap away." }),
          button("Stop asking", async () => {
            const answered = cachedSleepOffer;
            dismissSleepOffer();
            render("memory");
            const out = await memoryWrite("brain_memory_sleep_time", { remind: false },
              "Won't ask again.");
            if (!out || out.ok === false) {
              cachedSleepOffer = answered;
              sleepOfferDismissed = false;
              render("memory");
            }
          }, { title: "Never offer this again. (The choice is saved in sleep_time.json "
                     + "in Jarvis's config folder; deleting that file brings the offer back.)",
               live: true }),
        ],
      })
    );
    dom.memoryLearning.append(list);
  }

  const dl = el("dl", "kv");
  dl.append(el("dt", "", "Background learning"), el("dd", "", on ? "on" : "off"));
  dl.append(el("dt", "", "Waiting"), el("dd", "",
    String(facts.pending ?? waitingCount(pending))));
  if (setup.note) dl.append(el("dt", "", "Note"), el("dd", "", String(setup.note)));
  // memory-intake.patch: why the last "Remember:" did NOT become a card (a
  // queued one is already a card, marked "your own words"), or that it was
  // saved without one (`auto_saved`, JARVIS-API.md section 19), and how many
  // repeat cards were dropped - the backend's own sentences, as the phone's
  // MemoryCards.setupNotes shows them.
  const last = setup.remember_last;
  if (last && (last.queued === false || last.auto_saved === true) && last.note) {
    dl.append(el("dt", "", "Last “Remember:”"), el("dd", "", String(last.note)));
  }
  if (setup.near_duplicates_note) {
    dl.append(el("dt", "", MEMORY_WORDS.repeats),
      el("dd", "", String(setup.near_duplicates_note)));
  }
  dom.memoryLearning.append(dl);

  // Our own click, or a card raised elsewhere - the history switch's rule
  // (`chats.ask || v.waiting`), read from the queue.
  if (state.learningAsk || (!on && learningCardWaiting())) {
    dom.memoryLearning.append(el("p", "hint learning-waiting",
      `Waiting for your approval to turn background learning on. Approve it ${APPROVE_WHERE}.`));
  }
  const box = el("div", "row-actions");
  box.append(
    button(on ? "Pause background learning" : "Start background learning", async () => {
      const waitingBefore = new Set(
        (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
      );
      const out = await memoryWrite(
        "brain_memory_learning",
        { enabled: !on },
        (out) =>
          out && out.waiting
            // Turning learning ON raises an approval card (learning-asks.patch):
            // it is NOT on yet, and it is not "off" as a result of this either.
            ? String(out.message || `Waiting for your approval. Approve it ${APPROVE_WHERE}.`)
            : out && out.note
              ? String(out.note)
              : out && out.enabled
                ? "Background learning is on."
                : "Background learning is off. Nothing new will be proposed."
      );
      state.learningAsk = out && out.waiting ? { cardId: await findNewCard(waitingBefore) } : null;
      renderLearning();
    }, { title: on
        ? "Stop reading conversations for facts. Nothing already proposed is lost. "
          + "A message that starts “Remember:” still makes a card."
        : "Read conversations for facts again. With “Learn automatically” on, facts in "
          + "your own words are saved straight away; everything else waits for your yes." })
  );
  box.append(
    button("Export everything", async () => {
      try {
        // To a file the owner picks, never the clipboard. Windows can sync
        // the clipboard to other devices ("Sync across your devices"), so a
        // clipboard copy of everything Jarvis knows about the owner could
        // leave this machine with nobody deciding that it should. The save
        // dialog is opened by the app itself (brain.rs); this window gets no
        // file access of its own.
        const out = await invoke("brain_memory_export");
        if (!out || out.cancelled) return;
        const n = Number(out.facts) || 0;
        toast(`Saved ${n} fact${n === 1 ? "" : "s"} to ${out.saved}. `
          + "Keep that file private: it holds everything Jarvis knows about you.", "ok");
      } catch (error) {
        toast(String((error && error.message) || error), "bad");
      }
    }, { title: "Save every fact, current and retired, to a file you choose. "
        + "Nothing is sent anywhere." })
  );
  box.append(
    button(memoryAsOf === null ? "What did you know on\u2026" : "Back to now", async () => {
      if (memoryAsOf !== null) {
        memoryAsOf = null;
        memoryAsOfRows = null;
        render("memory");
        return;
      }
      // A date, not a datetime. Nobody remembers the hour they told their
      // assistant something, and asking for one would make the feature feel
      // like a database console.
      const typed = window.prompt(
        "What did Jarvis know on this date?\n\nYYYY-MM-DD",
        new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10)
      );
      if (typed === null) return;
      const day = typed.trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
        toast("A date like 2026-06-01.", "bad");
        return;
      }
      const when = asOfSeconds(day, new Date());
      if (when === null) {
        toast(`Pick a real date from ${AS_OF_EARLIEST_YEAR} up to today.`, "bad");
        return;
      }
      try {
        const out = await invoke("brain_memory_as_of", { when });
        // The server answers a date it cannot use with TODAY's facts and no
        // `known_at` - which this screen would then have labelled "what
        // Jarvis believed on" the typed date. Refused instead.
        if (!out || typeof out.known_at !== "number") {
          toast("Jarvis answered without using that date, so nothing is shown "
            + "rather than today's facts under the wrong heading.", "bad");
          return;
        }
        memoryAsOf = when;
        memoryAsOfRows = Array.isArray(out && out.facts) ? out.facts : [];
        render("memory");
      } catch (error) {
        toast(String((error && error.message) || error), "bad");
      }
    }, { title: memoryAsOf === null
        ? "Show what Jarvis believed on a past date, including things it has since stopped believing. Read-only."
        : "Go back to what is true now." })
  );
  dom.memoryLearning.append(box);
}

function renderProposals() {
  const body = state.data.memory_pending || {};
  const why = unavailable("memory_pending");
  if (why) {
    dom.memoryProposals.replaceChildren(whyNode("memory_pending"));
    return;
  }
  if (body.hidden === true) {
    dom.memoryProposals.replaceChildren(hiddenNode(body.hidden_count, "waiting"));
    return;
  }
  const items = Array.isArray(body.pending) ? body.pending : [];
  rows(
    dom.memoryProposals,
    items,
    (p) => proposalRow(p),
    "Nothing is waiting. Either Jarvis has not heard anything worth keeping, or background learning is off."
  );
}

/**
 * One review card. Three kinds, each labelled for what its buttons really do:
 *
 * - an ordinary proposal: Keep / Discard, plus "Both are true" when the
 *   server says the card corrects an older fact and both can stand
 *   (`keep_both_ok`, memory-intake.patch);
 * - a "stop using this fact?" card (`source == "feedback_retire"`,
 *   feedback.patch): accepting RETIRES the fact it names, so its buttons say
 *   "Stop using this fact" / "Keep using it", never "Keep" - which on this
 *   card would do the opposite of what it says;
 * - any card whose text reads like a planted instruction (`flags`) carries
 *   a plain-words warning. The warning drops nothing; the owner decides.
 *
 * Still one card, one decision. Nothing here decides more than one.
 */
function proposalRow(p) {
  const id = Number(p.id);
  // memory-entities.js: "are these the same?" (memory wave 3). Its own two
  // answers - never Keep / Discard, never "Both are true".
  if (p.source === MERGE_SOURCE) return mergeRow(p, id);
  const flags = Array.isArray(p.flags) ? p.flags.filter((f) => f && typeof f === "object") : [];
  const retire = p.source === "feedback_retire";
  // Topic controls: a card that asks about a topic set to not learn keeps
  // its two decisions, worded for what they do ("Save under Unsorted" /
  // "Skip it"); nothing else about the card changes.
  const ask = retire ? null : Topics.askLabels(p);
  const meta = retire
    ? [
        p.replaces_text || p.replaces ? `The fact: “${p.replaces_text || p.replaces}”` : "",
        "Stopping it does not delete it: the fact stays in Jarvis's history, marked as no longer used.",
        // The phone shows why this stayed a card on a retire card too
        // (MemoryCards.from); so does this window now (the memory review's
        // fit audit, 2026-09-27).
        ...reasonLines(p),
        ago(p.created),
      ]
    : [
        // Only a card that names the stored fact BY ID replaces anything:
        // jarvis_extract._accept() retires by `replaces_id` and nothing else
        // (memory-safety.patch). `replaces` alone is the model's own
        // description of some fact, and a card with words but no id retires
        // nothing - so it must not say it would. Same rule as the phone's
        // MemoryCards.from. The stored fact's own words, when the server
        // sent them, rather than the model's description of it.
        p.replaces_id
          ? `would replace: ${p.replaces_text || p.replaces || `fact #${p.replaces_id}`}`
          : "",
        p.verbatim ? "your own words" : "",
        p.confidence != null ? `confidence ${Number(p.confidence).toFixed(2)}` : "",
        p.source ? `from ${p.source}` : "",
        // Why automatic learning left this one for your yes (section 2 of
        // JARVIS-API.md section 19): "from pasted text", "sensitive:
        // health"... in the PC's own words. Then, on its own line, the PC's
        // "it sounds older than what Jarvis knows" warning with plain dates
        // (memory-words.js cardLines; the memory review's I9).
        ...reasonLines(p),
        ago(p.created),
      ];
  const actions = retire
    ? [
        button("Stop using this fact", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: true },
            "Jarvis will stop using that fact. It stays in the history.");
        }, { title: "Jarvis stops recalling this fact. It is not deleted.", live: true }),
        button("Keep using it", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: false },
            "Kept. Jarvis will go on using that fact.");
        }, { title: "Leave the fact exactly as it is.", live: true }),
      ]
    : [
        button(ask ? ask.accept : "Keep", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: true },
            ask ? "Saved under Unsorted. Jarvis can recall it now." : "Kept. Jarvis can recall it now.");
        }, { title: ask ? "Save it under Unsorted. It can be reworded or forgotten later."
          : "Add it to memory. It can be reworded or forgotten later.", live: true }),
        ...(p.keep_both_ok === true
          ? [button("Both are true", async () => {
              await memoryWrite("brain_memory_keep_both", { id },
                "Kept both. The older fact stays current too.");
            }, { title: "Keep this AND the fact it would replace. Nothing is retired.", live: true })]
          : []),
        button(ask ? ask.decline : "Discard", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: false },
            ask ? "Skipped. Nothing was saved." : "Discarded. It was never in memory.");
        }, { title: "Throw the proposal away. Nothing is removed from memory, because it was never there.", live: true }),
      ];
  const item = row({
    tag: retire ? "stop using?" : "proposed",
    state: retire || flags.length ? "bad" : "warn",
    title: String(p.text || "(no text)"),
    meta,
    actions,
  });
  if (flags.length) {
    const warn = el("div", "row-warning");
    warn.append(el("strong", "", "Careful: this reads like an instruction someone slipped in, not a fact about you. "));
    warn.append(el("span", "", "Only keep it if you really said this. "));
    for (const f of flags) {
      if (f.why) warn.append(el("span", "row-warning-why", String(f.why)));
    }
    const main = item.querySelector(".row-main");
    (main || item).append(warn);
  }
  return item;
}

/**
 * An "are these the same?" card (memory-entities.patch): the PC saw a new
 * name that is likely a typo of one it knows. Yes joins the two (a question
 * about one then finds the other's facts); no keeps them apart, and the PC
 * never asks about that pair again. One card, one decision - like every
 * other card here - and no fact is added, changed or forgotten either way.
 */
function mergeRow(p, id) {
  return row({
    tag: MERGE_TAG,
    state: "warn",
    title: String(p.text || "(no text)"),
    meta: [MERGE_NOTE, ago(p.created)],
    actions: [
      button(MERGE_YES, async () => {
        await memoryWrite("brain_memory_decide", { id, accept: true }, MERGE_JOINED);
      }, { title: MERGE_YES_TITLE, live: true }),
      button(MERGE_NO, async () => {
        await memoryWrite("brain_memory_decide", { id, accept: false }, MERGE_KEPT);
      }, { title: MERGE_NO_TITLE, live: true }),
    ],
  });
}

/* ==========================================================================
   "About <name>" (memory wave 3, 2026-09-25; memory-entities.js)

   Under a fact still in use: the people and things the PC linked it to,
   each a small button. It opens "About <name>": that entry's facts, word
   for word, read by id (memory_used - hidden like every memory list), with
   what the owner calls them. A read only; changes stay on the fact lists.
   ========================================================================== */

const aboutL = { id: null, view: null, error: "", loading: false };

function entitiesView() {
  return readEntities(state.data.memory_entities);
}

/** The "About: Priya, Lisbon" line under one fact, or null. */
function linkedNode(f) {
  const ents = entitiesFor(entitiesView(), f.id);
  if (!ents.length) return null;
  const line = el("span", "row-meta entity-links");
  line.append(el("span", "", `${LINKED_LABEL} `));
  for (const e of ents) {
    const b = button(e.name, () => openAbout(e.id), { title: aboutTitle(e.name) });
    b.classList.add("entity-link");
    b.dataset.entity = String(e.id);
    line.append(b, " ");
  }
  return line;
}

function withLinks(item, f) {
  const links = linkedNode(f);
  if (links) {
    const main = item.querySelector(".row-main");
    (main || item).append(links);
  }
  return item;
}

async function openAbout(entityId) {
  aboutL.id = Number(entityId);
  aboutL.view = null;
  aboutL.error = "";
  paintAbout();
  if (dom.memoryAboutCard) dom.memoryAboutCard.scrollIntoView({ block: "nearest" });
  const e = entityById(entitiesView(), aboutL.id);
  if (!e || !e.factIds.length || !IS_TAURI) return paintAbout();
  aboutL.loading = true;
  try {
    aboutL.view = readUsed(await invoke("memory_used", { ids: e.factIds.slice(0, ABOUT_MAX) }));
  } catch (error) {
    aboutL.error = errorText(error);
  } finally {
    aboutL.loading = false;
  }
  paintAbout();
}

function closeAbout() {
  aboutL.id = null;
  aboutL.view = null;
  paintAbout();
}

function paintAbout() {
  const card = dom.memoryAboutCard;
  const box = dom.memoryAbout;
  if (!card || !box) return;
  const ents = entitiesView();
  const e = aboutL.id === null ? null : entityById(ents, aboutL.id);
  if (!e || ents.hidden) {
    card.hidden = true;
    box.replaceChildren();
    return;
  }
  card.hidden = false;
  if (dom.memoryAboutTitle) dom.memoryAboutTitle.textContent = aboutTitle(e.name);
  box.replaceChildren();
  for (const line of [calledLine(e.aliases), alsoLine(e.also)].filter(Boolean)) {
    box.append(el("p", "about-line", line));
  }
  const v = aboutL.view;
  if (!e.factIds.length) {
    box.append(el("p", "empty", ABOUT_EMPTY));
  } else if (!v) {
    box.append(el("p", `empty${aboutL.error ? " failed" : ""}`, aboutL.error
      ? `Could not read these facts: ${aboutL.error}` : "Reading…"));
  } else if (!v.available) {
    box.append(el("p", "empty", v.why));
  } else if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount || e.factIds.length, "facts"));
  } else {
    const list = el("div", "rows about-rows");
    for (const f of v.facts) {
      const marks = [];
      if (f.pinned) marks.push(PINNED_MARK);
      if (!f.current && !f.erasedAt) marks.push(NOT_CURRENT_MARK);
      const item = row({
        tag: "fact",
        state: f.current ? "ok" : "idle",
        title: f.erasedAt ? erasedLine(f.erasedAt)
          : f.leftOut ? Topics.WORDS.used_left_out : (f.text || "(no text)"),
        meta: marks,
        actions: [],
      });
      item.dataset.id = String(f.id);
      list.append(item);
    }
    box.append(list);
    const more = moreLine(e.factIds.length - Math.min(e.factIds.length, ABOUT_MAX));
    if (more) box.append(el("p", "empty", more));
  }
  const foot = el("div", "row-actions");
  foot.append(button("Close", closeAbout));
  box.append(foot);
}

/* ==========================================================================
   "History of this fact" (the owner's choice of 2026-09-28; JARVIS-API.md
   section 71; fact-history.js). A History button on a fact that has another
   wording opens every version under its row, the changed words marked. A
   read (brain_fact_history), hidden like every memory list.
   ========================================================================== */

const factHist = { id: null, view: null, error: "", loading: false };

async function toggleFactHistory(id) {
  if (factHist.id === id) {
    factHist.id = null;
    factHist.view = null;
    renderFacts();
    return;
  }
  factHist.id = id;
  factHist.view = null;
  factHist.error = "";
  factHist.loading = true;
  renderFacts();
  try {
    const v = readFactHistory(await invoke("brain_fact_history", { id }));
    if (factHist.id === id) factHist.view = v;
  } catch (error) {
    if (factHist.id === id) factHist.error = errorText(error);
  } finally {
    if (factHist.id === id) factHist.loading = false;
  }
  renderFacts();
}

/** The open history, under its fact's row. */
function factHistoryNode() {
  const box = el("div", "fact-history");
  box.id = "fact-history";
  const v = factHist.view;
  if (factHist.error) {
    box.append(el("p", "empty failed", `Could not read this fact's history: ${factHist.error}`));
  } else if (!v) {
    box.append(el("p", "empty", "Reading…"));
  } else if (!v.available) {
    box.append(el("p", "empty", v.why));
  } else if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
  } else {
    renderFactHistory(box, v, { el });
  }
  const foot = el("div", "row-actions");
  foot.append(button("Close", () => toggleFactHistory(factHist.id)));
  box.append(foot);
  return box;
}

function renderFacts() {
  paintAbout();
  const body = state.data.memory_facts || {};
  const why = unavailable("memory_facts");
  if (why) {
    dom.memoryFacts.replaceChildren(whyNode("memory_facts"));
    return;
  }
  if (body.hidden === true) {
    memoryAsOf = null;
    memoryAsOfRows = null;
    // An open "History of this fact" goes with the list it was opened from.
    factHist.id = null;
    factHist.view = null;
    dom.memoryFacts.replaceChildren(hiddenNode(body.hidden_count, "facts"));
    return;
  }
  const past = memoryAsOf !== null;
  const loaded = past
    ? (memoryAsOfRows || [])
    : (Array.isArray(body.facts) ? body.facts : []);
  // The filter box (ease-of-use audit #7): the list already loaded, by its
  // words. An erased fact has no words left, so a filter never matches it.
  const needle = (dom.memoryFactsFilter?.value || "").trim().toLowerCase();
  const facts = needle
    ? loaded.filter((f) => erasedAt(f) === null && String(f.text || "").toLowerCase().includes(needle))
    : loaded;
  // `rows()` calls replaceChildren on whatever it is given, so the banner
  // cannot share a parent with it. The list goes in its own box and the pane
  // is assembled afterwards.
  const list = el("div", "");
  rows(
    list,
    facts,
    (f) => {
      // `current` is computed server-side, but do not depend on it being
      // there: a retired fact rendered as live is a fact the owner thinks
      // Jarvis still uses, offered a Forget button that does nothing. Fall
      // back to the bi-temporal field the flag is derived from.
      // The server computes `current` against the moment being asked about —
      // now, or the "as of" date — so the fallback has to use the same moment,
      // not Date.now(). Getting that wrong would render a fact as live in a
      // view of last June because it happens to be live today.
      const asOfSeconds = past ? memoryAsOf : Date.now() / 1000;
      const current =
        f.current === true ? true
        : f.current === false ? false
        : f.valid_to === null || f.valid_to === undefined
          || Number(f.valid_to) > asOfSeconds;
      // "Erase the words" (the owner's decision, 2026-09-24): an erased fact
      // is drawn as the date it was erased, never its words - the server
      // sends a marker as its text, and that marker is not shown either.
      const erased = erasedAt(f);
      const actions = [];
      if (current && !past && erased === null) {
        actions.push(
          button("Reword", async () => {
            // A prompt rather than an inline editor: this is the one place the
            // owner rewrites something the model will be told, and a
            // full-width text box that autosaves is how a stray keystroke
            // becomes a fact. A dialog makes the change deliberate.
            const next = window.prompt("Reword this fact:", String(f.text || ""));
            if (next === null) return;
            const text = next.trim();
            if (!text || text === String(f.text || "")) return;
            const validTo = promptValidTo(
              "When did the old wording stop being true?\n\n" +
              "Leave blank for \"just now\" — the usual case. Only answer this " +
              "if the change is really old news, like correcting an address " +
              "you moved out of months ago."
            );
            if (validTo === undefined) return; // the date prompt was cancelled
            const args = { id: Number(f.id), text };
            if (validTo !== null) args.valid_to = validTo;
            await memoryWrite("brain_memory_edit", args,
              "Reworded. The old wording is kept as history.");
          }, { title: "Replace the wording. The old one is retired, not erased." }),
          button("Forget", async () => {
            if (!window.confirm(forgetQuestion(f))) return;
            const validTo = promptValidTo(
              "When did this actually stop being true?\n\n" +
              "Leave blank for \"just now\" — the usual case. Only answer this " +
              "if it stopped being true a while ago and you are only telling " +
              "Jarvis about it now."
            );
            if (validTo === undefined) {
              // Cancel on the date box after "yes, forget it": say so, so
              // the owner is not left thinking the fact is gone.
              toast("Nothing was forgotten.");
              return;
            }
            const args = { id: Number(f.id) };
            if (validTo !== null) args.valid_to = validTo;
            await memoryWrite("brain_memory_forget", args, FORGOTTEN);
          }, { danger: true, title: "Stop this being recalled. There is no undo." })
        );
      }
      // "Always keep in mind": Pin / Unpin on a fact still in use, first -
      // before the buttons that cannot be undone, as in Saved automatically.
      // "Between us" sits right beside it, same reasoning.
      if (current && !past && erased === null) {
        const share = shareButton(f);
        if (share) actions.unshift(share);
        const pin = pinButton(f);
        if (pin) actions.unshift(pin);
      }
      // Erase is offered on a forgotten fact too: forgetting kept its words,
      // and this is how they go. Never in the past view, like every write.
      if (!past && erased === null) {
        actions.push(button(ERASE_LABEL, () => eraseFact(f),
          { danger: true, live: true, title: ERASE_TITLE }));
      }
      // "History of this fact" (section 71): a read, first of the buttons,
      // on any fact that has another wording on the list - an erased one
      // too (its history shows the dates, never its words).
      const withHistory = !past && hasOtherVersions(f, loaded);
      if (withHistory) {
        const open = factHist.id === Number(f.id);
        const h = button(open ? "Close history" : HISTORY_BUTTON,
          () => toggleFactHistory(Number(f.id)), { title: HISTORY_BUTTON_TITLE });
        h.setAttribute("aria-expanded", String(open));
        actions.unshift(h);
      }
      const item = row({
        tag: erased !== null ? "erased" : current ? "fact" : "retired",
        state: current && erased === null ? "ok" : undefined,
        title: erased !== null ? erasedLine(erased) : String(f.text || "(no text)"),
        meta: [
          f.source === "auto" ? "saved automatically"
            : f.source ? `from ${f.source}` : "",
          // One wording in both apps (the memory review's I11): today,
          // a fact no longer in use is "no longer used", like the count
          // above; on a past date, "true then" / "no longer true", as the
          // phone's "What did Jarvis know on this date?" says it.
          past
            ? (current ? MEMORY_WORDS.true_then : MEMORY_WORDS.no_longer_true)
            : (current ? "" : MEMORY_WORDS.no_longer_used),
          // `retired_by` is the column the store writes: the id of the fact
          // that replaced this one. (It used to read `supersedes`, which is
          // an argument to add(), not a column, so this never showed.)
          // Said in words since 2026-09-28; History shows which wording.
          f.retired_by ? REPLACED_MARK : "",
          whenTrue(f),
          // The two axes, and the only place the difference is visible. They
          // are usually the same day and this says nothing; when they are not,
          // it is because the fact was corrected after the fact — "true until
          // January, found out in March" — and that is precisely the case the
          // second column was added for, so it must not be inferable only
          // from the JSON export.
          whenLearned(f),
          whenNoticed(f),
          // Topic controls: this fact's topic may not be used in answers.
          topicMark(f),
        ],
        actions,
      });
      // The names it is linked to, each opening "About <name>" - on a fact
      // in use, in today's view only (the links are today's).
      const shown = current && !past && erased === null ? withLinks(item, f) : item;
      if (!withHistory || factHist.id !== Number(f.id)) return shown;
      const both = el("div", "fact-with-history");
      both.append(shown, factHistoryNode());
      return both;
    },
    needle && loaded.length
      ? "No fact on this list has those words."
      : past
        ? "Jarvis knew nothing on that date."
        : "Nothing yet. Facts arrive from the queue above, once you keep one."
  );
  if (past) {
    // Before the list, not after it: the difference between "these are your
    // facts" and "these WERE your facts" is the whole meaning of the screen,
    // and a footnote is read second.
    const when = new Date(memoryAsOf * 1000);
    dom.memoryFacts.replaceChildren(
      el("p", "banner",
         `What Jarvis believed on ${when.toLocaleDateString()} \u2014 right or ` +
         "wrong. Nothing here can be changed; use \u201cBack to now\u201d first."),
      list
    );
  } else {
    // Topic controls: facts of a topic switched Off are left out of this
    // list; how many is said, with a way to the Topics.
    const kept = topicsHiddenNode(body.topics_hidden);
    dom.memoryFacts.replaceChildren(...(kept ? [kept, list] : [list]));
  }
}

/* ==========================================================================
   Topics (the owner's request of 2026-09-30; docs/TOPIC-CONTROLS-DESIGN.md,
   Slice contract C1-C10; JARVIS-API.md section 107; topics.js).

   Every saved fact sits under one topic, and each topic has one of four
   modes: learn and use, use but don't learn, learn but don't use, or off. The
   PC enforces the modes and decides which changes need an approval card; this
   window carries the owner's taps to it through brain/topics.rs (its own
   commands, not brain_read). A change that raises a card comes back "waiting":
   the row says so, and this window reads the topics again every two seconds
   until the card has ended, then shows the PC's own sentence about how it
   ended. Undo is just another change, sent the same way.

   Topic names are the owner's words: only ever set as text, never stored in
   this window (not in localStorage, not as a draft), and taken out by Rust
   while "Hide memory lists and chat history" is on or App lock has locked -
   the rows then read "Topic N, X facts, mode", and "Check these", "Show them"
   and the row menus are not drawn at all. The picker still works then.
   ========================================================================== */

const tp = {
  view: null, missing: false, error: "", loading: false, again: false, at: 0,
  // {text, undo: {id, mode} | null}: the quiet line above the rows.
  notice: null,
  // The card being waited on: polled until it ends (topics.js LIMITS.pollMs).
  timer: null, sawWaiting: false, pollUntil: 0,
  // The topic whose "More" is open (an id, 0 for none).
  menu: 0,
  // "Check these": {facts, next, total, loading, error} or null.
  review: null,
  // "Show them": topic id -> {facts, next, loading, error}.
  shown: {},
  // The one dialog open (an element) and the control that had the keyboard.
  dlg: null, dlgReturn: "",
  focusNext: "", lastFocus: "",
};
const TOPICS_READ_MS = 15000;
const TOPICS_POLL_MAX_MS = 10 * 60 * 1000;

function takeTopics(view) {
  if (view.listsHidden) {
    // Nothing the owner wrote stays drawn: the check list, "Show them" and
    // every open form go with the names.
    tp.review = null;
    tp.shown = {};
    tp.menu = 0;
    closeTopicDialog();
  }
  tp.view = view;
  if (view.waiting) {
    tp.sawWaiting = true;
  } else if (tp.sawWaiting) {
    // The card that was up has ended: say how, in the PC's own sentence, and
    // read the lists again (a mode may have changed under them).
    tp.sawWaiting = false;
    const words = Topics.endedWords(view);
    if (words) setTopicsNotice(words, null);
    refreshMemory();
  }
  ensureTopicsPoll();
  if (state.view === "memory") paintTopics();
}

function ensureTopicsPoll() {
  const need = Boolean(tp.view && tp.view.waiting) || tp.sawWaiting;
  if (need && !tp.timer) {
    tp.pollUntil = Date.now() + TOPICS_POLL_MAX_MS;
    tp.timer = setInterval(() => {
      if (Date.now() > tp.pollUntil) {
        tp.sawWaiting = false;
        ensureTopicsPoll();
        return;
      }
      if (!tp.loading) loadTopics();
    }, Topics.LIMITS.pollMs);
  } else if (!need && tp.timer) {
    clearInterval(tp.timer);
    tp.timer = null;
  }
}

async function loadTopics() {
  if (!IS_TAURI) return;
  if (tp.loading) {
    tp.again = true;
    return;
  }
  tp.loading = true;
  try {
    const out = await invoke("brain_topics");
    const view = Topics.readTopics(out);
    if (view) {
      tp.missing = false;
      tp.error = "";
      takeTopics(view);
    } else if (Topics.isRefusal(out) && out.error === "unavailable") {
      tp.missing = true;
      tp.view = null;
      tp.error = "";
    } else {
      tp.error = Topics.isRefusal(out) ? Topics.refusalWords(out) : Topics.WORDS.missing;
    }
  } catch (error) {
    const words = errorText(error);
    if (words === Topics.WORDS.missing) {
      tp.missing = true;
      tp.view = null;
      tp.error = "";
    } else {
      tp.error = words;
    }
  } finally {
    tp.loading = false;
    tp.at = Date.now();
  }
  if (tp.again) {
    tp.again = false;
    await loadTopics();
    return;
  }
  if (state.view === "memory") paintTopics();
}

function renderTopics() {
  paintTopics();
  if (IS_TAURI && !tp.loading && Date.now() - tp.at > TOPICS_READ_MS) loadTopics();
}

function setTopicsNotice(text, undo) {
  tp.notice = text ? { text, undo: undo || null } : null;
  if (text) announce(text, "polite");
  if (state.view === "memory") paintTopics();
}

/** One write. Refused on a stale link, the PC's own words for a refusal.
 *  Returns {out} or {error, code}. */
async function topicsCall(cmd, args) {
  if (!linkWords(currentLink()).canAct) return { error: STALE_TITLE, code: "stale" };
  try {
    const out = await invoke(cmd, args);
    if (Topics.isRefusal(out)) return { error: Topics.refusalWords(out), code: out.error };
    return { out };
  } catch (error) {
    return { error: errorText(error), code: "failed" };
  }
}

/** A write's answer: 202 (a card is up: nothing changed yet) or the new view.
 *  Returns "waiting" or "done". */
async function takeTopicsWrite(out) {
  if (Topics.isWaitingAnswer(out)) {
    tp.sawWaiting = true;
    tp.notice = null;
    ensureTopicsPoll();
    await loadTopics();
    return "waiting";
  }
  const view = Topics.readTopics(out);
  if (view) takeTopics(view);
  else await loadTopics();
  return "done";
}

/** Changes one topic's mode. `undo` false for an Undo itself. */
async function topicSetMode(id, mode, { undo = true } = {}) {
  const before = Topics.topicById(tp.view, id);
  const r = await topicsCall("brain_topics_mode", { id, mode });
  if (r.error) return r;
  const kind = await takeTopicsWrite(r.out);
  if (kind === "waiting") return { waiting: true };
  const now = Topics.topicById(tp.view, id);
  if (r.out.changed !== false && now) {
    const name = Topics.displayName(tp.view, now);
    const said = undo
      ? `${name} is now: ${Topics.modeName(now.mode)}.`
      : `${name} is back to: ${Topics.modeName(now.mode)}.`;
    setTopicsNotice(said, undo && before ? { id, mode: before.mode } : null);
  }
  await refreshMemory();
  return { done: true };
}

/** One change to the list (add, rename, style, move, words, private, delete). */
async function topicEdit(edit) {
  const r = await topicsCall("brain_topics_edit", { edit });
  if (r.error) return r;
  const kind = await takeTopicsWrite(r.out);
  if (kind === "waiting") return { waiting: true, out: r.out };
  if (edit.op === "delete") await refreshMemory();
  return { done: true, out: r.out };
}

/* ---- The dialog every form uses ----------------------------------------- */

let topicDialogSeq = 0;

function closeTopicDialog() {
  const dlg = tp.dlg;
  if (!dlg) return;
  tp.dlg = null;
  if (typeof dlg.close === "function" && dlg.open) dlg.close();
  else dlg.remove();
}

/** Opens a modal dialog with a title, a body and footer buttons. `build`
 *  gets the body element and returns the footer's buttons. The dialog sits on
 *  the page, outside the section, so a repaint of the rows never destroys it.
 *  Escape and Cancel close it and the keyboard goes back to where it was. */
function openTopicDialog(title, build) {
  closeTopicDialog();
  const dlg = document.createElement("dialog");
  dlg.className = "topics-dialog";
  const titleId = `topics-dialog-title-${++topicDialogSeq}`;
  const h = el("h3", "topics-dialog-title", title);
  h.id = titleId;
  dlg.setAttribute("aria-labelledby", titleId);
  const body = el("div", "topics-dialog-body");
  const error = el("p", "topics-dialog-error failed");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const foot = el("div", "row-actions topics-dialog-foot");
  const api = {
    dlg,
    body,
    say(words) {
      error.textContent = words || "";
      error.hidden = !words;
    },
    close: () => closeTopicDialog(),
  };
  const buttons = build(body, api) || [];
  for (const b of buttons) foot.append(b);
  dlg.append(h, body, error, foot);
  tp.dlgReturn = tp.lastFocus || "";
  dlg.addEventListener("close", () => {
    if (tp.dlg === dlg) tp.dlg = null;
    dlg.remove();
    tp.focusNext = tp.focusNext || tp.dlgReturn;
    paintTopics();
  });
  document.body.append(dlg);
  tp.dlg = dlg;
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "");
  const first = dlg.querySelector("input:checked, input, select, textarea") || dlg.querySelector("button");
  if (first) first.focus({ preventScroll: true });
  return api;
}

/** A dialog's main button: off while nothing is chosen yet, while it works, and
 *  while the link cannot be confirmed (rule 4) - a choice never re-enables it. */
function topicGoState(go, nothingChosen) {
  go.disabled = nothingChosen || go.dataset.busy === "true" || !linkWords(currentLink()).canAct;
}

function cancelButton() {
  return button(Topics.APP_WORDS.cancel, () => closeTopicDialog());
}

/* ---- The four-choice picker (contract C4) ------------------------------- */

function openModePicker(id) {
  const v = tp.view;
  const t = Topics.topicById(v, id);
  if (!t || Topics.isWaitingOn(v, id)) return;
  const name = Topics.displayName(v, t);
  let token = 0;
  let chosen = t.mode;
  const preview = { line: "", card: "" };
  openTopicDialog(name, (body, api) => {
    body.append(el("p", "note", Topics.fill(Topics.WORDS.pick_line, { name })));
    const set = el("fieldset", "topics-choices");
    set.append(el("legend", "sr-only", name));
    const lines = el("p", "topics-preview");
    lines.setAttribute("aria-live", "polite");
    const card = el("p", "topics-card-line");
    card.setAttribute("aria-live", "polite");
    let go = null;
    const paintLines = () => {
      lines.textContent = preview.line;
      card.textContent = preview.card;
      lines.hidden = !preview.line;
      card.hidden = !preview.card;
    };
    Topics.MODES.forEach((m) => {
      const label = el("label", "topics-choice");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "topics-mode";
      input.value = m.id;
      input.checked = m.id === t.mode;
      const said = el("span", "topics-choice-name", m.name);
      const sentence = el("span", "topics-choice-sentence", m.sentence);
      sentence.id = `topics-choice-${topicDialogSeq}-${m.id}`;
      input.setAttribute("aria-describedby", sentence.id);
      label.append(input, said, sentence);
      input.addEventListener("change", async () => {
        chosen = m.id;
        api.say("");
        preview.line = "";
        preview.card = "";
        paintLines();
        if (go) topicGoState(go, m.id === t.mode);
        if (m.id === t.mode) return;
        const mine = ++token;
        try {
          const out = await invoke("brain_topics_preview", { id, mode: m.id });
          if (mine !== token) return;
          if (Topics.isRefusal(out)) {
            api.say(Topics.refusalWords(out));
            return;
          }
          const got = Topics.previewLines(out, name);
          preview.line = got.line;
          preview.card = got.cardLine;
          paintLines();
        } catch (error) {
          if (mine === token) api.say(errorText(error));
        }
      });
      set.append(label);
    });
    body.append(set, lines, card);
    paintLines();
    go = button(Topics.APP_WORDS.change, async () => {
      if (chosen === t.mode) return;
      api.say("");
      const r = await topicSetMode(id, chosen);
      if (r.error) {
        api.say(r.error);
        return;
      }
      closeTopicDialog();
    }, { live: true });
    topicGoState(go, true);
    go.dataset.fkey = "topics-change";
    return [go, cancelButton()];
  });
}

/* ---- Add, rename, colour and icon, keywords ----------------------------- */

function colourPicker(current) {
  const set = el("fieldset", "topics-palette");
  set.append(el("legend", "", Topics.APP_WORDS.colour_label));
  Topics.COLOURS.forEach((c) => {
    const label = el("label", "topics-swatch-choice");
    label.dataset.colour = String(c.slot);
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "topics-colour";
    input.value = String(c.slot);
    input.checked = c.slot === current;
    const dot = el("span", "topics-swatch");
    dot.setAttribute("aria-hidden", "true");
    label.append(input, dot, el("span", "topics-swatch-name", c.name));
    set.append(label);
  });
  return set;
}

function iconPicker(current) {
  const set = el("fieldset", "topics-icons");
  set.append(el("legend", "", Topics.APP_WORDS.icon_label));
  Topics.ICONS.forEach((name) => {
    const label = el("label", "topics-icon-choice");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "topics-icon";
    input.value = name;
    input.checked = name === current;
    label.append(input, Topics.topicIconNode(name), el("span", "topics-icon-name", name));
    set.append(label);
  });
  return set;
}

const pickedValue = (root, name) => {
  const on = root.querySelector(`input[name="${name}"]:checked`);
  return on ? on.value : null;
};

/** add | rename | style | words. Names and keywords are typed here and go to
 *  the PC; nothing is kept in this window. */
function openTopicForm(kind, id) {
  const v = tp.view;
  const t = kind === "add" ? null : Topics.topicById(v, id);
  if (kind !== "add" && !t) return;
  if (v && v.listsHidden) return;
  const title = kind === "add" ? Topics.WORDS.add_title
    : kind === "rename" ? Topics.APP_WORDS.rename
      : kind === "style" ? Topics.APP_WORDS.colour_icon : Topics.APP_WORDS.keywords;
  openTopicDialog(title, (body, api) => {
    let nameBox = null;
    let wordsBox = null;
    if (kind === "add" || kind === "rename") {
      const label = el("label", "lbl", Topics.WORDS.name_label);
      nameBox = document.createElement("input");
      nameBox.type = "text";
      nameBox.className = "field";
      nameBox.maxLength = Topics.LIMITS.nameMax;
      nameBox.autocomplete = "off";
      nameBox.spellcheck = false;
      nameBox.value = t ? t.name : "";
      label.append(nameBox);
      body.append(label);
    }
    if (kind === "add" || kind === "style") {
      body.append(colourPicker(t ? t.colour : Topics.nextColour(v)));
      body.append(iconPicker(t ? t.icon : "folder"));
    }
    if (kind === "add" || kind === "words") {
      const label = el("label", "lbl", Topics.WORDS.words_label);
      wordsBox = document.createElement("textarea");
      wordsBox.className = "field";
      wordsBox.rows = 3;
      wordsBox.spellcheck = false;
      wordsBox.value = t ? t.words.join(", ") : "";
      label.append(wordsBox);
      body.append(label);
    }
    const save = button(Topics.APP_WORDS.save, async () => {
      api.say("");
      const edit = { op: kind, id: t ? t.id : undefined };
      if (nameBox) {
        const clean = Topics.cleanName(nameBox.value);
        if (!clean) {
          api.say(Topics.ERRORS.bad_name);
          return;
        }
        edit.name = clean;
      }
      if (wordsBox) {
        const words = Topics.cleanWords(wordsBox.value);
        if (words === null) {
          api.say(Topics.ERRORS.bad_words);
          return;
        }
        edit.words = words;
      }
      if (kind === "add" || kind === "style") {
        edit.colour = Number(pickedValue(body, "topics-colour"));
        edit.icon = pickedValue(body, "topics-icon");
      }
      const r = await topicEdit(edit);
      if (r.error) {
        api.say(r.error);
        return;
      }
      if (kind === "add" && r.out && Number.isInteger(r.out.id)) tp.focusNext = `mode-${r.out.id}`;
      closeTopicDialog();
    }, { live: true });
    save.dataset.fkey = "topics-save";
    if (nameBox) {
      nameBox.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          save.click();
        }
      });
    }
    return [save, cancelButton()];
  });
}

/* ---- Delete: its facts are kept, and go to a topic the owner picks ------- */

function openDeleteDialog(id) {
  const v = tp.view;
  const t = Topics.topicById(v, id);
  if (!t || t.system || (v && v.listsHidden)) return;
  const homes = Topics.deleteDestinations(v, id);
  openTopicDialog(Topics.displayName(v, t), (body, api) => {
    body.append(el("p", "note", Topics.WORDS.confirm_delete));
    const set = el("fieldset", "topics-choices");
    set.append(el("legend", "", Topics.WORDS.delete_where));
    const warn = el("p", "topics-card-line");
    warn.setAttribute("aria-live", "polite");
    warn.hidden = true;
    let chosen = 0;
    let go = null;
    homes.forEach((home) => {
      const label = el("label", "topics-choice");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "topics-home";
      input.value = String(home.id);
      const said = el("span", "topics-choice-name", Topics.displayName(v, home));
      label.append(input, said, el("span", "topics-choice-sentence", Topics.modeName(home.mode)));
      input.addEventListener("change", () => {
        chosen = home.id;
        const words = Topics.deleteWarning(v, t, home);
        warn.textContent = words;
        warn.hidden = !words;
        if (go) topicGoState(go, false);
      });
      set.append(label);
    });
    body.append(set, warn);
    go = button(Topics.APP_WORDS.delete, async () => {
      if (!chosen) {
        api.say(Topics.ERRORS.needs_destination);
        return;
      }
      api.say("");
      const r = await topicEdit({ op: "delete", id, moveTo: chosen });
      if (r.error) {
        api.say(r.error);
        return;
      }
      tp.menu = 0;
      closeTopicDialog();
    }, { live: true, danger: true });
    topicGoState(go, true);
    return [go, cancelButton()];
  });
}

/* ---- "Check these": the facts Jarvis sorted by guessing ----------------- */

async function loadReview(after) {
  const r = tp.review;
  if (!r) return;
  r.loading = true;
  r.error = "";
  paintTopics();
  try {
    const args = { limit: Topics.LIMITS.batch };
    if (after) args.after = after;
    const out = await invoke("brain_topics_review", args);
    const got = Topics.readFacts(out);
    if (!tp.review) return;
    if (got && got.listsHidden) {
      tp.review = null;
    } else if (got) {
      r.facts = got.facts;
      r.next = got.next;
      r.total = got.total;
    } else {
      r.error = Topics.isRefusal(out) ? Topics.refusalWords(out) : Topics.WORDS.missing;
    }
  } catch (error) {
    r.error = errorText(error);
  } finally {
    r.loading = false;
  }
  paintTopics();
}

function openReview() {
  tp.review = { facts: [], next: null, total: 0, loading: true, error: "", from: "" };
  tp.focusNext = "review-close";
  loadReview(null);
}

function closeReview() {
  tp.review = null;
  tp.focusNext = "check";
  paintTopics();
}

async function confirmBatch() {
  const r = tp.review;
  if (!r || !r.facts.length) return;
  const ids = r.facts.map((f) => f.id);
  const res = await topicsCall("brain_topics_file", { ids, confirm: true });
  if (res.error) {
    r.error = res.error;
    paintTopics();
    return;
  }
  const view = Topics.readTopics(res.out);
  if (view) takeTopics(view);
  // The confirmed facts are off the list now: read it again from the top.
  await loadReview(null);
}

async function fileFact(fact, topicId) {
  const r = tp.review;
  if (!r) return;
  const res = await topicsCall("brain_topics_file", { ids: [fact.id], topicId });
  if (res.error) {
    r.error = res.error;
    paintTopics();
    return;
  }
  const view = Topics.readTopics(res.out);
  if (view) takeTopics(view);
  r.facts = r.facts.filter((f) => f.id !== fact.id);
  r.error = "";
  if (!r.facts.length) await loadReview(null);
  else paintTopics();
  await refreshMemory();
}

function reviewNode(v) {
  const r = tp.review;
  const box = el("section", "topics-review");
  box.setAttribute("aria-label", Topics.checkButtonLabel(v.unchecked));
  const head = el("div", "topics-review-head");
  head.append(el("h3", "topics-review-title", Topics.checkButtonLabel(v.unchecked)));
  box.append(head);
  if (r.error) box.append(el("p", "empty failed", r.error));
  if (r.loading && !r.facts.length) {
    box.append(el("p", "empty", Topics.APP_WORDS.reading));
  } else if (!r.facts.length && !r.error) {
    box.append(el("p", "empty", Topics.APP_WORDS.nothing_to_check));
  }
  for (const group of Topics.groupByTopic(r.facts)) {
    const topic = Topics.topicById(v, group.topic) || Topics.topicById(v, Topics.LIMITS.unsortedId);
    const name = topic ? Topics.displayName(v, topic) : Topics.WORDS.unsorted_name;
    const gh = el("h4", "topics-review-group");
    if (topic) gh.dataset.colour = String(topic.colour);
    gh.append(Topics.topicIconNode(topic ? topic.icon : "flag"), el("span", "", name));
    box.append(gh);
    const list = el("ul", "topics-review-list");
    for (const f of group.facts) {
      const li = el("li", "topics-review-fact");
      li.dataset.id = String(f.id);
      li.append(el("span", "topics-review-text", f.text || "(no text)"));
      const tags = el("span", "topics-tags");
      if (f.how === "model") tags.append(el("span", "topics-tag", Topics.WORDS.check_guessed));
      if (f.heldBack) tags.append(el("span", "topics-tag topics-tag-held", Topics.heldWords(name)));
      if (tags.childNodes.length) li.append(tags);
      const pick = document.createElement("select");
      pick.className = "field topics-file-under";
      pick.setAttribute("aria-label", `${Topics.APP_WORDS.file_under_label} (${(f.text || "").slice(0, 40)})`);
      pick.append(new Option(Topics.APP_WORDS.file_under, ""));
      for (const other of v.topics) {
        if (other.id === f.topic) continue;
        pick.append(new Option(Topics.displayName(v, other), String(other.id)));
      }
      liveButtons.add(pick);
      syncLiveButton(pick);
      pick.addEventListener("change", async () => {
        const to = Number(pick.value);
        if (!to) return;
        pick.disabled = true;
        await fileFact(f, to);
      });
      li.append(pick);
      list.append(li);
    }
    box.append(list);
  }
  const foot = el("div", "row-actions");
  if (r.facts.length) {
    const right = button(Topics.WORDS.check_right, confirmBatch, { live: true });
    right.dataset.fkey = "review-right";
    foot.append(right);
    if (r.next) {
      foot.append(button(Topics.APP_WORDS.next_ten, () => loadReview(r.next)));
    }
  }
  const close = button("Close", closeReview);
  close.dataset.fkey = "review-close";
  foot.append(close);
  box.append(foot);
  return box;
}

/* ---- "Show them": an Off topic's facts, read-only ------------------------ */

async function loadShown(id, more = false) {
  const s = tp.shown[id];
  if (!s) return;
  s.loading = true;
  s.error = "";
  paintTopics();
  try {
    // "Show more" asks for the page after the last one shown (`next`).
    const after = more && s.next !== null && Number.isInteger(Number(s.next)) ? Number(s.next) : null;
    const out = await invoke("brain_topics_hidden", after ? { id, after } : { id });
    const got = Topics.readFacts(out);
    if (!tp.shown[id]) return;
    if (got && got.listsHidden) {
      delete tp.shown[id];
    } else if (got) {
      s.facts = after ? s.facts.concat(got.facts.filter((f) => !s.facts.some((o) => o.id === f.id))) : got.facts;
      s.next = got.next;
    } else {
      s.error = Topics.isRefusal(out) ? Topics.refusalWords(out) : Topics.WORDS.missing;
    }
  } catch (error) {
    s.error = errorText(error);
  } finally {
    s.loading = false;
  }
  paintTopics();
}

function toggleShown(id) {
  if (tp.shown[id]) {
    delete tp.shown[id];
    tp.focusNext = `show-${id}`;
    paintTopics();
    return;
  }
  tp.shown[id] = { facts: [], next: null, loading: true, error: "" };
  tp.focusNext = `show-${id}`;
  loadShown(id);
}

/** After a Forget or an Erase anywhere: the open "Show them" lists are read
 *  again, so a fact just forgotten is not left on them. */
function reloadShown() {
  for (const id of Object.keys(tp.shown)) loadShown(Number(id));
}

function shownNode(id) {
  const s = tp.shown[id];
  const box = el("div", "topics-shown");
  if (s.error) box.append(el("p", "empty failed", s.error));
  if (s.loading && !s.facts.length) {
    box.append(el("p", "empty", Topics.APP_WORDS.reading));
    return box;
  }
  if (!s.facts.length && !s.error) {
    box.append(el("p", "empty", Topics.APP_WORDS.no_facts));
    return box;
  }
  const list = el("div", "rows");
  for (const f of s.facts) {
    const item = row({
      tag: "hidden",
      state: "idle",
      title: f.text || "(no text)",
      meta: [Topics.APP_WORDS.hidden_from_answers],
      actions: [
        button("Forget", async () => {
          if (!window.confirm(forgetQuestion(f))) return;
          await memoryWrite("brain_memory_forget", { id: f.id }, FORGOTTEN);
        }, { danger: true, live: true, title: "Stop this being recalled. There is no undo." }),
        button(ERASE_LABEL, () => eraseFact(f), { danger: true, live: true, title: ERASE_TITLE }),
      ],
    });
    item.classList.add("topics-hidden-fact");
    item.dataset.id = String(f.id);
    list.append(item);
  }
  box.append(list);
  if (s.next !== null && s.next !== undefined) {
    const more = button(Topics.APP_WORDS.show_more, () => loadShown(id, true), { live: true });
    more.dataset.fkey = `show-more-${id}`;
    if (s.loading) more.disabled = true;
    box.append(more);
  }
  return box;
}

/* ---- The section ---------------------------------------------------------- */

function topicRow(v, t) {
  const item = el("div", "topics-row");
  item.setAttribute("role", "listitem");
  item.dataset.colour = String(t.colour);
  item.dataset.topic = String(t.id);
  item.dataset.mode = t.mode;
  const name = Topics.displayName(v, t);

  const head = el("div", "topics-row-head");
  const mark = el("span", "topics-mark");
  mark.append(Topics.topicIconNode(t.icon));
  head.append(mark, el("span", "topics-name", name), el("span", "topics-count", Topics.factCount(t.facts)));
  item.append(head);

  const tags = el("div", "topics-tags");
  for (const tag of Topics.rowTags(t)) tags.append(el("span", `topics-tag topics-tag-${tag.kind}`, tag.text));
  if (tags.childNodes.length) item.append(tags);

  const acts = el("div", "topics-row-actions");
  if (Topics.isWaitingOn(v, t.id)) {
    const waiting = el("span", "topics-waiting", Topics.WORDS.waiting);
    waiting.setAttribute("role", "status");
    acts.append(waiting);
  } else {
    const modeBtn = button(Topics.modeName(t.mode), () => openModePicker(t.id));
    modeBtn.classList.add("topics-mode");
    modeBtn.setAttribute("aria-label", Topics.rowSpeech(v, t));
    modeBtn.dataset.fkey = `mode-${t.id}`;
    acts.append(modeBtn);
  }
  if (!v.listsHidden && t.mode === "off") {
    const open = Boolean(tp.shown[t.id]);
    const show = button(Topics.WORDS.show_them, () => toggleShown(t.id));
    show.dataset.fkey = `show-${t.id}`;
    show.setAttribute("aria-expanded", String(open));
    acts.append(show);
  }
  if (!v.listsHidden && !t.system) {
    const open = tp.menu === t.id;
    const more = button(Topics.APP_WORDS.edit, () => {
      tp.menu = open ? 0 : t.id;
      tp.focusNext = `more-${t.id}`;
      paintTopics();
    });
    more.dataset.fkey = `more-${t.id}`;
    more.setAttribute("aria-expanded", String(open));
    more.setAttribute("aria-label", `${Topics.APP_WORDS.edit}: ${name}`);
    acts.append(more);
  }
  item.append(acts);

  if (!v.listsHidden && !t.system && tp.menu === t.id) item.append(topicMenu(v, t));
  if (!v.listsHidden && t.mode === "off" && tp.shown[t.id]) item.append(shownNode(t.id));
  return item;
}

function topicMenu(v, t) {
  const menu = el("div", "topics-menu");
  menu.setAttribute("role", "group");
  menu.setAttribute("aria-label", `${Topics.APP_WORDS.edit}: ${t.name}`);
  const add = (label, fn, { title = "", danger = false, key = "" } = {}) => {
    const b = button(label, fn, { live: true, title, danger });
    if (key) b.dataset.fkey = `${key}-${t.id}`;
    menu.append(b);
    return b;
  };
  add(Topics.APP_WORDS.rename, () => openTopicForm("rename", t.id));
  add(Topics.APP_WORDS.colour_icon, () => openTopicForm("style", t.id));
  const up = Topics.moveTarget(v, t.id, -1);
  const down = Topics.moveTarget(v, t.id, 1);
  const mover = (label, before, key) => add(label, async () => {
    const r = await topicEdit({ op: "move", id: t.id, before });
    if (r.error) setTopicsNotice(r.error, null);
  }, { key });
  if (up !== undefined) mover(Topics.APP_WORDS.move_up, up, "up");
  if (down !== undefined) mover(Topics.APP_WORDS.move_down, down, "down");
  add(t.private ? Topics.APP_WORDS.not_private : Topics.APP_WORDS.mark_private, async () => {
    const r = await topicEdit({ op: "private", id: t.id, private: !t.private });
    if (r.error) setTopicsNotice(r.error, null);
  }, { title: t.private ? Topics.WORDS.private_asks : "", key: "private" });
  add(Topics.APP_WORDS.keywords, () => openTopicForm("words", t.id));
  add(Topics.APP_WORDS.delete, () => openDeleteDialog(t.id), { danger: true, key: "delete" });
  return menu;
}

function paintTopics() {
  const root = $("topics-body");
  if (!root) return;
  const intro = $("topics-intro");
  if (intro) intro.textContent = Topics.WORDS.intro;
  const key = fkeyBefore(root, tp);
  root.replaceChildren();
  const done = () => {
    fkeyAfter(root, tp.focusNext || key);
    tp.focusNext = "";
  };
  if (tp.notice) {
    const line = el("div", "topics-notice");
    line.setAttribute("role", "status");
    line.append(el("span", "", tp.notice.text));
    if (tp.notice.undo) {
      const undo = tp.notice.undo;
      const b = button(Topics.APP_WORDS.undo, async () => {
        tp.notice = null;
        const r = await topicSetMode(undo.id, undo.mode, { undo: false });
        if (r.error) setTopicsNotice(r.error, null);
      }, { live: true });
      b.dataset.fkey = "undo";
      line.append(b);
    }
    root.append(line);
  }
  if (tp.missing) {
    root.append(el("p", "empty", Topics.WORDS.missing));
    return done();
  }
  const v = tp.view;
  if (!v) {
    const line = el("p", `empty${tp.error ? " failed" : ""}`,
      tp.error ? `Could not read your topics: ${tp.error}` : Topics.APP_WORDS.reading);
    if (tp.error) line.append(" ", button("Retry", loadTopics));
    root.append(line);
    return done();
  }
  if (tp.error) root.append(el("p", "empty failed", tp.error));
  if (v.listsHidden) {
    const hid = el("div", "private-hidden");
    hid.append(el("p", "hint", Topics.APP_WORDS.hidden_note));
    hid.append(button("Show", revealPrivate,
      { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
    root.append(hid);
  }
  const sorting = Topics.sortingLine(v);
  if (sorting) root.append(el("p", "note topics-sorting", sorting));
  const guess = Topics.sortedGuessLine(v);
  if (guess && !v.listsHidden) {
    const line = el("div", "topics-guess");
    line.append(el("p", "note", guess));
    const check = button(Topics.checkButtonLabel(v.unchecked), openReview);
    check.dataset.fkey = "check";
    line.append(check);
    root.append(line);
  }
  if (tp.review && !v.listsHidden) root.append(reviewNode(v));

  const list = el("div", "topics-rows");
  list.setAttribute("role", "list");
  for (const t of v.topics) list.append(topicRow(v, t));
  root.append(list);

  const foot = el("div", "topics-foot");
  if (!v.listsHidden) {
    const atLimit = !Topics.canAdd(v);
    const add = button(Topics.WORDS.add_button, () => openTopicForm("add"),
      { live: true, title: atLimit ? Topics.APP_WORDS.at_limit : "" });
    add.dataset.fkey = "add";
    if (atLimit) {
      add.disabled = true;
      add.dataset.busy = "true";
      add.title = Topics.APP_WORDS.at_limit;
    }
    foot.append(add);
  }
  const help = el("label", "lbl check topics-model-help");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = v.modelHelp;
  box.dataset.fkey = "model-help";
  liveButtons.add(box);
  syncLiveButton(box);
  box.addEventListener("change", async () => {
    const want = box.checked;
    box.disabled = true;
    const r = await topicsCall("brain_topics_settings", { modelHelp: want });
    if (r.error) {
      box.checked = !want;
      setTopicsNotice(r.error, null);
      return;
    }
    const view = Topics.readTopics(r.out);
    if (view) takeTopics(view);
    else await loadTopics();
    paintTopics();
  });
  help.append(box, el("span", "", Topics.WORDS.model_help));
  foot.append(help);
  root.append(foot);
  root.append(el("p", "hint topics-model-note", Topics.WORDS.model_help_note));
  root.append(el("p", "hint topics-help", Topics.WORDS.help_plain));
  done();
}

if (IS_TAURI) trackFkeys($("topics-body"), tp);

// Private answers turned on or off, or a Show ran out: read the topics again.
// Rust decides whether the names come back.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadTopics = () => {
    tp.at = 0;
    if (state.view === "memory") loadTopics();
  };
  TAURI.event.listen("security-changed", rereadTopics);
  TAURI.event.listen("private-hidden", rereadTopics);
}

// The approvals list changed (a card was decided on this PC or the phone, or
// timed out): while one of ours waits, read the topics now rather than at the
// next tick, so the row does not say "waiting" longer than it has to.
onQueue(() => {
  if (tp.view && tp.view.waiting && !tp.loading) loadTopics();
});

/** The Jarvis bar sent the owner here (`open_brain: "topics"`), maybe with a
 *  topic to open the picker for. Changes nothing until Change is tapped. */
async function goToTopics(topicId) {
  await showView("memory");
  tp.at = 0;
  await loadTopics();
  const card = $("topics-card");
  if (card) {
    card.scrollIntoView({ block: "start" });
    const h = $("topics-title");
    if (h) h.focus({ preventScroll: true });
  }
  if (topicId && Topics.topicById(tp.view, topicId)) openModePicker(topicId);
}

/** The small tag on a fact whose topic is "Learn, but don't use". */
function topicMark(f) {
  return Topics.factTag(tp.view, f && f.topic);
}

/** "3 facts kept, hidden" over the facts list, with a way to the Topics. */
function topicsHiddenNode(n) {
  const words = Topics.keptHiddenLine(n);
  if (!words) return null;
  const line = el("p", "hint topics-hidden-line", `${words} `);
  line.append(button(Topics.WORDS.title, () => {
    const card = $("topics-card");
    if (card) card.scrollIntoView({ block: "start" });
    const h = $("topics-title");
    if (h) h.focus({ preventScroll: true });
  }));
  return line;
}

/** The line on a pinned fact whose topic may not be used: names the topic the
 *  PC said (`f.topic`) and says whether it is Off or "Learn, but don't use". */
function pinPausedFor(f) {
  let t = f && Number.isInteger(f.topic) ? Topics.topicById(tp.view, f.topic) : null;
  if (!t && f) {
    // An older PC sends no topic id: fall back to the fact in a list.
    const rows = (state.data.memory_facts && state.data.memory_facts.facts) || [];
    const found = rows.find((r) => r && Number(r.id) === Number(f.id))
      || autoL.rows.find((r) => r && Number(r.id) === Number(f.id));
    t = found ? Topics.topicById(tp.view, found.topic) : null;
  }
  return Topics.pinPausedLine(t ? Topics.displayName(tp.view, t) : "this topic", t ? t.mode : "off");
}

/* ==========================================================================
   Wiki - backend/wiki.patch. Its own plate on the Memory tab, read through
   its own commands (not brain_read); the plate itself is wiki.js.
   ========================================================================== */

const wiki = { view: null, error: "", job: null, at: 0, loading: false };
/** The Memory tab repaints often; the list is re-read at most this often. */
const WIKI_READ_MS = 15000;

async function loadWiki() {
  if (wiki.loading) return;
  wiki.loading = true;
  try {
    wiki.view = readWiki(await invoke("wiki_status"));
    wiki.error = "";
  } catch (error) {
    wiki.error = String((error && error.message) || error);
  } finally {
    wiki.loading = false;
    wiki.at = Date.now();
  }
  paintWiki();
}

function paintWiki() {
  const box = $("wiki");
  if (!box) return;
  renderWiki(box, { ...wiki, onAdd: addWiki, onOpen: openWikiFolder }, { el, row, button });
}

function renderWikiPlate() {
  paintWiki();
  if (IS_TAURI && !wiki.loading && Date.now() - wiki.at > WIKI_READ_MS) loadWiki();
}

/** "Add to wiki": one card is raised on the PC; this follows it to the end. */
async function addWiki(source) {
  wiki.job = { source, said: { text: "Asking the PC…", tone: null, final: false } };
  paintWiki();
  // With the link to the PC down, polls are skipped rather than failed: the
  // job carries on there, and following it resumes when the link does.
  const last = await addToWiki(invoke, source, (said) => {
    wiki.job = { source, said };
    paintWiki();
  }, { linkDown: () => !currentLink().connected });
  announce(`${source}: ${last.text}`, last.tone === "bad" ? "assertive" : "polite");
  await loadWiki();
}

async function openWikiFolder() {
  try {
    await invoke("wiki_open_folder");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
}

/* ==========================================================================
   Deep questions - backend/big-model.patch. Their own plate on the Memory
   tab, beside the wiki (the big model's other job), read through their own
   commands; the list itself is deep.js.

   Refreshed by the `deep` event (a question finished) - see the onEvent
   handler at the bottom - and, only while a question is still going, by a
   gentle poll in case that event is missed.
   ========================================================================== */

const deep = { view: null, error: "", at: 0, loading: false, openId: undefined,
  asking: false, pollTimer: null, going: new Set() };
/** The Memory tab repaints often; the list is re-read at most this often. */
const DEEP_READ_MS = 15000;

async function loadDeep() {
  if (deep.loading) return;
  deep.loading = true;
  try {
    deep.view = readDeep(await invoke("get_deep"));
    deep.error = "";
  } catch (error) {
    deep.error = String((error && error.message) || error);
  } finally {
    deep.loading = false;
    deep.at = Date.now();
  }
  // Say when one this window saw going has finished.
  if (deep.view) {
    for (const job of deep.view.jobs) {
      if (deep.going.has(job.id) && !DEEP_RUNNING.has(job.state)) {
        announce(job.state === "done" ? "A deep question has been answered."
          : `A deep question was not answered. ${job.why}`);
      }
    }
    deep.going = new Set(deep.view.jobs.filter((j) => DEEP_RUNNING.has(j.state)).map((j) => j.id));
  }
  paintDeep();
  scheduleDeepPoll();
}

function paintDeep() {
  const lead = $("deep-state");
  if (!lead) return;
  const v = deep.view;
  const ask = $("deep-ask");
  if (!v) {
    lead.textContent = deep.error ? `Could not read the deep questions: ${deep.error}` : "Reading…";
    lead.dataset.ready = "false";
    ask.hidden = true;
  } else {
    lead.textContent = deepLead(v);
    lead.dataset.ready = String(v.available);
    // Only when GET /api/deep says available; otherwise the line says why.
    ask.hidden = !v.available;
    const box = $("deep-question");
    box.maxLength = v.questionChars;
    paintDeepCount();
  }
  renderDeepJobs($("deep-jobs"), {
    view: v, error: v ? deep.error : "", openId: deep.openId,
    onToggle: (id, open) => {
      if (open) deep.openId = id;
      else if (deep.openId === id || deep.openId === undefined) deep.openId = null;
    },
  }, { el, row, hiddenNode });
}

function paintDeepCount() {
  const v = deep.view;
  const box = $("deep-question");
  const count = $("deep-count");
  if (!v || !box || !count) return;
  const n = box.value.length;
  const going = runningCount(v);
  count.textContent = `${n.toLocaleString("en-US")} / ${v.questionChars.toLocaleString("en-US")} characters` +
    (going >= v.queue ? ` · ${going} questions are already waiting or running; ask again when one has finished.` : "");
}

function renderDeepPlate() {
  paintDeep();
  if (IS_TAURI && !deep.loading && Date.now() - deep.at > DEEP_READ_MS) loadDeep();
}

/** Only while a question is going, and only while the Memory tab shows. */
function scheduleDeepPoll() {
  clearTimeout(deep.pollTimer);
  deep.pollTimer = null;
  if (!deep.view || runningCount(deep.view) === 0) return;
  deep.pollTimer = setTimeout(() => {
    deep.pollTimer = null;
    if (state.view === "memory" && !document.hidden) loadDeep();
    else scheduleDeepPoll();
  }, DEEP_POLL_MS);
}

/** "Ask slowly": one question, queued in the background. No card. */
async function askDeepNow() {
  if (deep.asking) return;
  const box = $("deep-question");
  const said = $("deep-said");
  deep.asking = true;
  said.textContent = "Asking…";
  delete said.dataset.tone;
  try {
    const out = await askDeep(invoke, box.value);
    said.textContent = out.text;
    said.dataset.tone = out.tone;
    announce(out.text, out.tone === "bad" ? "assertive" : "polite");
    if (out.queued) {
      box.value = "";
      paintDeepCount();
    }
  } finally {
    deep.asking = false;
  }
  await loadDeep();
}

function setupDeepAsk() {
  const rowBox = $("deep-ask-row");
  const box = $("deep-question");
  if (!rowBox || !box) return;
  const go = button("Ask slowly", askDeepNow, {
    live: true,
    title: "The big model answers in the background, on this PC - expect minutes. No approval " +
      "card per question: you approved the Deep questions switch.",
  });
  go.id = "deep-ask-button";
  rowBox.prepend(go);
  box.addEventListener("input", paintDeepCount);
  box.addEventListener("keydown", (event) => {
    // Ctrl+Enter asks; a plain Enter is a new line in the question.
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (!go.disabled) go.click();
    }
  });
}
setupDeepAsk();

/* ==========================================================================
   History - chat history on the PC (JARVIS-API.md section 18). Its own tab,
   next to Memory, read through its own commands (brain/history.rs), not
   brain_read; the words and the transcript are history-view.js.

   The switch is the learning switch's shape: ON raises one approval card
   and shows "Waiting for your approval" until the card leaves the queue;
   OFF is immediate. Rust holds ON (and a keep change) on a stale link, and
   the controls are greyed then. Delete is one conversation, after a
   confirm. There is no "delete all".
   ========================================================================== */

const chats = {
  /** readHistory() of the first page, or null before the first read. */
  view: null,
  /** Every conversation shown, newest first: the first page, then older. */
  rows: [],
  /** The last page was full, so there may be older ones. */
  more: false,
  error: "",
  at: 0,
  loading: false,
  older: false,
  /** A successful read's time, for the status line (paintFreshness). */
  readOkAt: 0,
  /** "Show": one kind of conversation, or "" for every kind (the chat
   *  audit, 2026-09-28 - "History can be filtered to Live sessions only"). */
  kind: "",
  /** Chat tags (docs/CHAT-TAGS-DESIGN.md): the tag chip chosen ("" is All,
   *  "none" is Untagged, else a tag id as digits), the PC's tags
   *  (readTags), which sections are open on this device, the Tags editor,
   *  and an older chat being found to file (`filing`, from "label my chat
   *  about the boiler as Home"; `filingPending` waits for the names). */
  tag: "",
  tags: null,
  sectionFlags: readOpenFlags(),
  editor: { open: false, error: "", drafts: { add: { name: "", colour: 0, icon: "folder" }, names: {} } },
  filing: null,
  filingPending: null,
  /** Which tag control had the keyboard (`data-fkey` names, first choice
   *  first), so a repaint can give it back; and whether a repaint was held
   *  back because a menu or the editor was in use. */
  focus: null,
  paintPending: false,
  /** True while paintHistory paints everything: focus is given back once, at the end. */
  batch: false,
  /** The conversation open below its row, and its transcript. */
  openId: null,
  open: null,
  openError: "",
  /** "Fork from here" in flight: `{ id, idx }`, one at a time. */
  forking: null,
  /** "New section here" in flight: `{ id, idx }`, one at a time. */
  marking: null,
  /** "Suggest tags overnight" (JARVIS-API.md section 104): what the PC last
   *  said (readSuggest), whether a read or a change is running, and the one
   *  plain sentence the last change left. Nothing of it is kept on this device. */
  suggest: { state: null, loaded: false, reading: false, busy: false, said: "", isError: false },
  /** The chat a fork just made, `{ id, row }`: kept open (and drawn above the
   *  list if its row is not in it) until the owner opens or closes something. */
  forked: null,
  /** What the open chat taught (readChatFacts), or null while it is read or
   *  when this PC cannot say (the second chat audit, 2026-09-28, finding 9). */
  openFacts: null,
  /** `{ cardId, gone }` while an ON card waits (like `learningAsk`). */
  ask: null,
  /**
   * "Search what was said" (JARVIS-API.md section 71). `query` is what is
   * in the box; `view` the PC's answer (readSearch), dropped when the box
   * is cleared. Nothing of it is kept anywhere else. `oldPc` is the
   * sentence of a PC that cannot search the words - then the box narrows
   * the loaded list by title, as it did before. `seq` drops an answer
   * that arrives after a newer search was started.
   */
  search: { query: "", view: null, loading: false, error: "", seq: 0, timer: null, oldPc: "" },
  /** "Find in this chat", over the conversation open: the words, which
   *  match is current, and how many there are. Asks the PC nothing. */
  find: { needle: "", current: 0, total: 0 },
  /**
   * Deleting a chat offers to forget the facts it taught (JARVIS-API.md
   * section 79, 2026-09-28): the conversation being deleted, the facts it
   * taught (brain_conversation_facts, hidden like every memory list), and
   * the ones the owner ticked - NONE to start with. Kept here so the
   * 15-second repaint keeps the ticks.
   */
  deleting: null,
};
/** The tab repaints often; the list is re-read at most this often. */
const HISTORY_READ_MS = 15000;
/** How long typing must pause before the PC is asked to search. */
const HISTORY_SEARCH_WAIT_MS = 350;

const errorText = (error) => String((error && error.message) || error);

async function loadHistory({ background = false } = {}) {
  if (chats.loading) return;
  chats.loading = true;
  let hold = false;
  try {
    const kind = chats.kind;
    const tag = chats.tag;
    // The chats and the tags are two reads; an older PC (or app build) with
    // no tags leaves the list flat, exactly as before.
    const [listRead, tagsRead] = await Promise.allSettled([
      invoke("brain_history_list",
        { before: null, limit: HISTORY_PAGE, kind: kind || null, tag: tag || null }),
      invoke("brain_history_tags"),
    ]);
    if (listRead.status === "rejected") throw listRead.reason;
    const v = readHistory(listRead.value);
    if (kind !== chats.kind || tag !== chats.tag) return;   // the filter changed while this read ran
    chats.tags = readTags(tagsRead.status === "fulfilled" ? tagsRead.value : { available: false });
    if (chats.tag && chats.tag !== "none" && chats.tags.available && !chats.tags.hidden
        && !tagById(chats.tags, Number(chats.tag))) {
      // The tag was deleted elsewhere: back to every chat, read again.
      chats.tag = "";
      chats.rows = [];
      chats.more = false;
      chats.tags = null;
      setTimeout(loadHistory, 0);
      return;
    }
    chats.view = v;
    chats.readOkAt = Date.now();
    paintFreshness();
    // The re-read every 15 seconds replaces the newest page only: pages
    // "Load older" brought in stay, and so does a conversation opened
    // from one of them. A hidden list (Windows Hello) keeps nothing.
    const kept = v.hidden ? { rows: v.conversations, more: false }
      : refreshRows(chats.rows, v.conversations, HISTORY_PAGE, chats.more);
    chats.rows = kept.rows;
    chats.more = kept.more;
    chats.error = "";
    if (v.enabled) chats.ask = null; // the card was approved
    // A conversation opened from the search results may be older than
    // every page loaded; it stays open while it is still a result.
    const inSearch = (chats.search.view?.conversations || []).some((c) => c.id === chats.openId);
    if (chats.forked && chats.rows.some((c) => c.id === chats.forked.id)) chats.forked = null;
    const justForked = !v.hidden && chats.forked && chats.forked.id === chats.openId;
    if (chats.openId && !justForked
        && (v.hidden || (!chats.rows.some((c) => c.id === chats.openId) && !inSearch))) {
      chats.openId = null;
      chats.open = null;
    }
    if (v.hidden) { chats.search.view = null; chats.forked = null; }
    // The 15-second re-read must not close a menu or the editor the owner
    // is using: the data is in, the repaint waits until they let go.
    hold = background && tagControlBusy();
  } catch (error) {
    chats.error = errorText(error);
  } finally {
    chats.loading = false;
    chats.at = Date.now();
  }
  if (hold) {
    chats.paintPending = true;
    return;
  }
  paintHistory();
  // The waiting-suggestions count follows the same re-read (no push).
  if (chats.suggest.loaded) refreshSuggest();
}

async function loadOlderHistory() {
  const before = olderThan(chats.rows);
  if (before === null || chats.older) return;
  chats.older = true;
  try {
    const v = readHistory(await invoke("brain_history_list",
      { before, limit: HISTORY_PAGE, kind: chats.kind || null, tag: chats.tag || null }));
    chats.rows = addPage(chats.rows, v.conversations);
    chats.more = v.conversations.length >= HISTORY_PAGE;
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    chats.older = false;
  }
  paintHistory();
}

/**
 * Opens (or closes) one conversation below its row. `needle`: the words to
 * find in it at once - the search words, when it was opened from a search
 * result; nothing when it was opened from the list.
 */
async function toggleConversation(id, needle = "") {
  if (!(chats.forked && chats.forked.id === id)) chats.forked = null;
  if (chats.openId === id) {
    chats.openId = null;
    chats.open = null;
    chats.openFacts = null;
    paintHistory();
    return;
  }
  chats.openId = id;
  chats.open = null;
  chats.openFacts = null;
  chats.openError = "";
  chats.find = { needle: String(needle || ""), current: 0, total: 0 };
  paintHistory();
  try {
    const conv = readConversation(await invoke("brain_history_open", { id }));
    if (chats.openId === id) chats.open = conv;
  } catch (error) {
    if (chats.openId === id) chats.openError = errorText(error);
  }
  paintHistory();
  if (chats.openId === id && chats.open && CONTINUABLE_KINDS.includes(chats.open.kind)) {
    loadOpenFacts(id);
  }
}

const CONTINUABLE_KINDS = ["chat", "live"];

/** The facts an opened chat taught and Jarvis still uses (section 79), read
 *  only - Delete offers to forget them, the Memory tab has Forget. */
async function loadOpenFacts(id) {
  let got = null;
  try {
    got = readChatFacts(await invoke("brain_conversation_facts", { conversationId: id }));
  } catch {
    got = null;
  }
  if (chats.openId !== id) return;
  chats.openFacts = got && got.available ? got : null;
  paintHistory();
}

/** Under an opened chat: what it taught, or that nothing it taught is in use. */
function factsTaughtNode(got) {
  const box = el("div", "history-facts-taught");
  if (got.hiddenCount) {
    box.append(el("p", "hint", chatFactsTaughtHidden(got.hiddenCount)));
    return box;
  }
  box.append(el("p", "hint", chatFactsTaught(got.facts.length)));
  if (got.facts.length) {
    const list = el("ul", "history-taught-list");
    for (const f of got.facts) list.append(el("li", "", f.text));
    box.append(list);
  }
  return box;
}

/**
 * Delete, on a conversation's row. Since 2026-09-28 (JARVIS-API.md section
 * 79) it first asks the PC which facts in use this chat taught. None, or a
 * PC that cannot say: the same "are you sure?" as before. Some: a list
 * under the row with a tick box each - none ticked - and "Delete the chat"
 * (or "... and forget 2 facts"), then the usual "are you sure?". Hidden
 * memory lists: the facts are not shown, and are kept.
 */
async function deleteConversation(c) {
  if (chats.deleting && chats.deleting.id === c.id) {
    chats.deleting = null;
    paintHistory();
    return;
  }
  // A customer-support chat's record is the owner's record of what a company
  // agreed to: it asks once more, saying so (the chat audit, 2026-09-28).
  if (c.kind === "support" && !window.confirm(DELETE_SUPPORT)) return;
  let got = null;
  try {
    got = readChatFacts(await invoke("brain_conversation_facts", { conversationId: c.id }));
  } catch {
    got = null;          // an older app build, or the PC out of reach: ask as before
  }
  if (got && got.facts.length) {
    chats.deleting = { id: c.id, facts: got.facts, ticked: new Set(), busy: false };
    paintHistory();
    return;
  }
  const note = got && got.hiddenCount ? chatFactsHiddenLine(got.hiddenCount) : "";
  if (!window.confirm(deleteQuestion(c, note))) return;
  await finishDelete(c, []);
}

/** The list under a row being deleted: each fact with a tick box, none
 *  ticked; Delete (naming how many will be forgotten) and Cancel. */
function deletingNode(c) {
  const d = chats.deleting;
  const box = el("div", "history-delete-facts");
  box.id = "history-delete-facts";
  box.append(el("p", "hint", chatFactsIntro(d.facts.length)));
  const list = el("ul", "history-delete-list");
  for (const f of d.facts) {
    const li = el("li");
    const label = el("label", "history-delete-fact");
    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.checked = d.ticked.has(f.id);
    tick.disabled = d.busy;
    tick.dataset.factId = String(f.id);
    tick.addEventListener("change", () => {
      if (tick.checked) d.ticked.add(f.id);
      else d.ticked.delete(f.id);
      // Only the button's words change - no repaint, so the keyboard stays
      // on this tick box.
      const go = $("history-delete-go");
      if (go) go.textContent = deleteChatButton(d.ticked.size);
    });
    label.append(tick, el("span", "", f.text));
    li.append(label);
    list.append(li);
  }
  box.append(list);
  const actions = el("div", "row-actions");
  const go = button(d.busy ? "Deleting…" : deleteChatButton(d.ticked.size), async () => {
    // Read at the click, not when drawn: the ticks may have changed since.
    const chosen = d.facts.filter((f) => d.ticked.has(f.id));
    if (d.busy || !window.confirm(deleteAndForgetQuestion(c, chosen))) return;
    d.busy = true;
    paintHistory();
    await finishDelete(c, chosen.map((f) => f.id));
  }, { danger: true, live: true,
       title: "Delete this conversation from this PC, and forget only the facts ticked above." });
  go.id = "history-delete-go";
  actions.append(
    go,
    button("Cancel", () => {
      chats.deleting = null;
      paintHistory();
    }, { title: "Keep the conversation and every fact." }),
  );
  box.append(actions);
  return box;
}

/** Delete the chat, then forget each ticked fact - ONE brain_memory_forget
 *  per fact (held on a stale link in Rust, like every Forget). There is no
 *  list form of Forget. */
async function finishDelete(c, factIds) {
  try {
    const out = await invoke("brain_history_delete", { id: c.id });
    let forgot = 0;
    let failed = 0;
    for (const id of factIds) {
      try {
        const r = await invoke("brain_memory_forget", { id });
        if (r && r.ok === false) failed += 1;
        else {
          forgot += 1;
          autoL.rows = autoL.rows.filter((row) => row.id !== id);
        }
      } catch {
        failed += 1;
      }
    }
    toast(deleteDoneWords({ gone: Boolean(out && out.gone), forgot, failed }), failed ? "bad" : "ok");
    // The Jarvis bar may be in this chat: it starts a new one, and says so.
    tellChatsGone([c.id]);
    if (factIds.length) refreshMemory();
    chats.deleting = null;
    chats.rows = chats.rows.filter((r) => r.id !== c.id);
    if (chats.search.view) {
      chats.search.view.conversations = chats.search.view.conversations.filter((r) => r.id !== c.id);
    }
    if (chats.openId === c.id) {
      chats.openId = null;
      chats.open = null;
    }
  } catch (error) {
    if (chats.deleting) chats.deleting.busy = false;
    toast(errorText(error), "bad");
  }
  paintHistory();
}

async function setHistoryEnabled(on) {
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke("brain_history_settings", { enabled: on, keepDays: null });
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else if (on && out && out.waiting) {
      // Turning history ON raises an approval card: it is NOT on yet.
      chats.ask = { cardId: await findNewCard(waitingBefore) };
      toast(String(out.message || `Waiting for your approval. Approve it ${APPROVE_WHERE}.`), "ok");
    } else if (on) {
      chats.ask = null;
      toast(out && out.enabled === true ? ON_REPLY : String((out && out.message) || "Chat history is still off."),
        out && out.enabled === true ? "ok" : "bad");
    } else {
      chats.ask = null;
      toast(OFF_REPLY, "ok");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.at = 0;
  await loadHistory();
}

async function setKeepDays(days) {
  try {
    const out = await invoke("brain_history_settings", { enabled: null, keepDays: days });
    if (out && out.ok === false) toast(String(out.error || out.reason || "Refused."), "bad");
    else toast(keepReply(days, out), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.at = 0;
  await loadHistory();
}

async function revealHistory() {
  try {
    await invoke("reveal_private_answers");
  } catch (error) {
    toast(errorText(error), "bad");
    return;
  }
  chats.at = 0;
  await loadHistory();
  // A search typed before the list was hidden runs again, now it may.
  if (chats.search.query.length >= SEARCH_MIN) onHistorySearch();
  // An older chat to file was waiting for the tag names to be shown.
  if (chats.filingPending) await resolveFilingPending();
}

/* ---- "Search what was said" and "Find in this chat" (section 71) -------- */

/**
 * The search box. Two letters or more: after a short pause the PC searches
 * what was said in the kept chats (brain_history_search); one letter, or a
 * PC that cannot search the words, narrows the loaded list by title, as the
 * box did before. The words are held in this window only while they are in
 * the box.
 */
function onHistorySearch() {
  const s = chats.search;
  const q = ($("history-filter")?.value || "").trim();
  clearTimeout(s.timer);
  s.query = q;
  s.seq += 1;          // an answer still on its way is for older words
  s.error = "";
  if (q.length < SEARCH_MIN || s.oldPc || !IS_TAURI || (chats.view && chats.view.hidden)) {
    s.view = null;
    s.loading = false;
    paintHistoryList();
    return;
  }
  s.loading = true;
  paintHistoryList();
  s.timer = setTimeout(() => runHistorySearch(q, s.seq), HISTORY_SEARCH_WAIT_MS);
}

async function runHistorySearch(q, seq) {
  const s = chats.search;
  let v = null;
  let error = "";
  try {
    // The kind chosen in "Show" narrows the search too, so "Live only" and
    // a typed search combine (the second chat audit, 2026-09-28, finding 8).
    v = readSearch(await invoke("brain_history_search",
      { query: q, limit: null, kind: chats.kind || null }));
  } catch (e) {
    error = errorText(e);
  }
  if (seq !== s.seq) return;
  s.loading = false;
  s.error = error;
  if (v && !v.available) {
    // An older PC: say so once, and narrow the loaded list by title.
    s.oldPc = v.why;
    s.view = null;
  } else {
    s.view = v;
  }
  paintHistoryList();
}

/** Re-draws only the open transcript and the count, so the find box keeps
 *  the keyboard while the owner types in it. */
function paintFound() {
  const box = $("history-transcript-turns");
  if (!box || !chats.open) return;
  const f = chats.find;
  const matches = f.needle.trim() ? findMatches(chats.open, f.needle) : [];
  f.total = matches.length;
  if (f.current >= matches.length) f.current = 0;
  renderTranscript(box, chats.open,
    { el, onCopy: copyOldAnswer, fork: forkHelpers(chats.open), mark: markHelpers(chats.open) },
    { matches, current: f.current, needle: f.needle.trim() });
  const count = $("history-find-count");
  if (count) count.textContent = f.needle.trim() ? findCountWords(f.current, matches.length) : "";
  for (const id of ["history-find-prev", "history-find-next"]) {
    const b = $(id);
    if (b) b.disabled = matches.length < 2;
  }
}

function stepFind(delta) {
  const f = chats.find;
  if (!f.total) return;
  f.current = (f.current + delta + f.total) % f.total;
  paintFound();
  $("history-transcript-turns")?.querySelector(".find-current")?.scrollIntoView({ block: "nearest" });
}

/** "Find in this chat": a box, Previous, Next, and "2 of 7". */
function findBar() {
  const bar = el("div", "history-find");
  bar.setAttribute("role", "search");
  const input = el("input", "field search history-find-input");
  input.type = "search";
  input.id = "history-find";
  input.placeholder = FIND_PLACEHOLDER;
  input.spellcheck = false;
  input.autocomplete = "off";
  input.setAttribute("aria-label", FIND_LABEL);
  input.setAttribute("aria-describedby", "history-find-count");
  input.value = chats.find.needle;
  input.addEventListener("input", () => {
    chats.find.needle = input.value;
    chats.find.current = 0;
    paintFound();
    $("history-transcript-turns")?.querySelector(".find-current")?.scrollIntoView({ block: "nearest" });
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      stepFind(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape" && input.value) {
      e.preventDefault();
      e.stopPropagation();
      input.value = "";
      chats.find.needle = "";
      paintFound();
    }
  });
  const prev = button("Previous", () => stepFind(-1), { title: "The match before this one (Shift+Enter)." });
  prev.id = "history-find-prev";
  const next = button("Next", () => stepFind(1), { title: "The next match (Enter)." });
  next.id = "history-find-next";
  const count = el("span", "history-find-count");
  count.id = "history-find-count";
  count.setAttribute("aria-live", "polite");
  bar.append(input, prev, next, count);
  return bar;
}

/** The open conversation, below its row: the find bar, then the words. */
function transcriptNode() {
  const t = el("div", "history-transcript");
  t.id = "history-transcript";
  if (chats.openError) t.append(el("p", "empty failed", chats.openError));
  else if (!chats.open) t.append(el("p", "empty", "Reading…"));
  else {
    t.append(continueNode(chats.open));
    if (chats.open.forkWhy && !(chats.view && chats.view.hidden)) {
      t.append(el("p", "hint history-fork-why", chats.open.forkWhy));
    }
    if (chats.openFacts) t.append(factsTaughtNode(chats.openFacts));
    t.append(findBar());
    const turns = el("div", "history-transcript-turns");
    turns.id = "history-transcript-turns";
    t.append(turns);
  }
  return t;
}

/**
 * "Continue this chat" (the owner's decision, 2026-09-28): the Jarvis bar
 * carries this conversation on - the same conversation id, the newest kept
 * messages that fit, its "read outside text" mark carried over by the PC.
 * A support, chatbot or comparison record cannot be, and says why.
 */
function continueNode(conv) {
  const box = el("div", "row-actions history-continue");
  if (!conv.continuable) {
    box.append(el("p", "hint history-continue-why", conv.continueWhy));
    return box;
  }
  const go = button(HISTORY_CONTINUE, async () => {
    try {
      await invoke("brain_continue_chat", { id: conv.id });
    } catch (error) {
      toast(errorText(error), "bad");
    }
  }, { title: HISTORY_CONTINUE_TITLE });
  go.classList.add("history-continue-go");
  box.append(go);
  return box;
}

/**
 * "Fork from here" (JARVIS-API.md section 110): what renderTranscript needs to
 * draw the button on each message of the opened chat. Nothing while the
 * private lists are hidden or when the PC did not say the chat is forkable.
 * The buttons are held (greyed, with the usual stale-link reason) while the
 * link is stale, and all wait while one fork runs.
 */
function forkHelpers(conv) {
  if (!conv || !conv.forkable || (chats.view && chats.view.hidden)) return null;
  const busy = chats.forking && chats.forking.id === conv.id ? chats.forking : null;
  return {
    forkable: true,
    busy: busy || (chats.forking ? { idx: -1 } : null),
    decorate: (b) => { liveButtons.add(b); syncLiveButton(b); },
    onFork: (idx) => forkFrom(conv.id, idx),
  };
}

/** Sends the fork, then opens the new chat (the same open as its row) and
 *  refreshes the list. A refusal leaves the original chat open, with the
 *  PC's sentence. No card: nothing leaves the PC. */
async function forkFrom(id, idx) {
  if (chats.forking || !IS_TAURI) return;
  chats.forking = { id, idx };
  chats.focus = { keys: [`fork:${id}:${idx}`, `open:${id}`], at: Date.now() };
  paintHistory();
  let made = null;
  try {
    const out = await invoke("brain_history_fork", { id, upto: idx });
    if (out && out.ok === true && typeof out.id === "string" && out.id) made = out;
    else toast(forkErrorWords(out), "bad");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.forking = null;
  if (!made) {
    paintHistory();
    return;
  }
  // The new chat must be visible whatever was narrowing the list: the kind
  // ("Live only"), the tag chip and the search words are cleared, and its row
  // is put in from the answer (the list read that follows replaces it).
  const clearing = !!(chats.kind || chats.tag || chats.search.query);
  const sourceRow = chats.rows.find((c) => c.id === id) || null;
  const row = forkedRow(made, sourceRow, Date.now() / 1000);
  clearHistoryNarrowing();
  chats.rows = withForkedRow(clearing ? [] : chats.rows, row);
  chats.forked = { id: made.id, row };
  chats.focus = { keys: [`open:${made.id}`], at: Date.now() };
  chats.at = 0;
  if (chats.openId !== made.id) await toggleConversation(made.id);
  await loadHistory();
  toast(forkDoneWords(made.title), "ok");
}

/**
 * "New section here" (JARVIS-API.md section 106): what renderTranscript needs
 * to draw the buttons and dividers of the opened chat. Nothing while the
 * private lists are hidden. Dividers stay drawn when the PC says the chat is
 * no longer markable (they can still be removed); the button only shows when
 * it is. Held (greyed, the usual stale-link reason) while the link is stale,
 * and all wait while one request runs.
 */
function markHelpers(conv) {
  if (!conv || (chats.view && chats.view.hidden)) return null;
  if (!conv.markable && !conv.marks.length) return null;
  const busy = chats.marking && chats.marking.id === conv.id ? chats.marking : null;
  return {
    markable: conv.markable,
    marks: conv.marks,
    busy: busy || (chats.marking ? { idx: -1 } : null),
    decorate: (b) => { liveButtons.add(b); syncLiveButton(b); },
    onMark: (idx, on) => markSection(conv.id, idx, on),
  };
}

/** Sends one section break (or takes it off), then draws the PC's whole list.
 *  No card: it is the owner's own layout of a chat already kept. */
async function markSection(id, idx, on) {
  if (chats.marking || !IS_TAURI) return;
  chats.marking = { id, idx };
  chats.focus = { keys: [`${on ? "unmark" : "mark"}:${id}:${idx}`, `${on ? "mark" : "unmark"}:${id}:${idx}`, `open:${id}`], at: Date.now() };
  paintHistory();
  try {
    const out = await invoke("brain_history_mark", { id, idx, on });
    if (out && out.ok === true) {
      if (chats.open && chats.open.id === id) chats.open.marks = readMarks(out.marks);
      toast(markDoneWords(typeof out.on === "boolean" ? out.on : on), "ok");
    } else {
      toast(markErrorWords(out), "bad");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.marking = null;
  paintHistory();
}

/** Back to every chat: no kind, no tag chip, no search words (a fork's new
 *  chat is shown whatever the owner had narrowed the list to). */
function clearHistoryNarrowing() {
  const s = chats.search;
  clearTimeout(s.timer);
  s.query = "";
  s.view = null;
  s.loading = false;
  s.error = "";
  s.seq += 1;
  chats.kind = "";
  chats.tag = "";
  chats.more = false;
  const box = $("history-filter");
  if (box) box.value = "";
  const kind = $("history-kind");
  if (kind) kind.value = "";
}

/** Copy on an opened old answer: the bar's own private copy (kept out of
 *  Windows' clipboard history), or a plain one from an older build. */
async function copyOldAnswer(text, btn) {
  try {
    await invoke("write_clipboard_private", { text });
  } catch {
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      toast(errorText(error), "bad");
      return;
    }
  }
  const was = btn.textContent;
  btn.textContent = HISTORY_COPIED;
  setTimeout(() => { btn.textContent = was; }, 1200);
}

/** One conversation's row, in the list or in the search results. */
function conversationRow(c, { needle = "", snippet = null } = {}) {
  const open = chats.openId === c.id;
  const device = deviceTag(c.device);
  const item = row({
    tag: device.tag,
    title: c.title || NO_TITLE,
    meta: [rowMeta(c), snippet ? hitsWords(c.hits) : ""],
    actions: [
      button(open ? "Close" : "Open", () => toggleConversation(c.id, needle),
        { title: open ? "Close the conversation." : "Read the conversation. Nothing changes." }),
      button("Delete", () => deleteConversation(c),
        { danger: true, live: true, title: "Delete this conversation from this PC. There is no undo." }),
    ],
  });
  item.dataset.id = c.id;
  // Chat tags: the tag pill under the title, a "Move to" menu, and - while
  // an older chat is being found to file - a button (and a tap on the row)
  // that files this one.
  const tagView = chats.tags && chats.tags.available && !chats.tags.hidden ? chats.tags : null;
  const tagOf = tagView ? tagById(tagView, c.tagId) : null;

  if (device.words) item.querySelector(".row-tag").title = device.words;
  // Every row's buttons say WHICH chat they are for (the second chat audit,
  // 2026-09-28, desktop A1): "Open" ten times over names nothing.
  const named = c.title || NO_TITLE;
  const buttons = item.querySelectorAll(".row-actions button");
  if (buttons[0]) {
    buttons[0].setAttribute("aria-label", `${open ? "Close" : "Open"} ${named}`);
    buttons[0].dataset.fkey = `open:${c.id}`;
  }
  if (buttons[1]) {
    buttons[1].setAttribute("aria-label", `Delete ${named}`);
    buttons[1].dataset.fkey = `delete:${c.id}`;
  }
  const main = item.querySelector(".row-main");
  if (tagOf) main.append(tagPillNode(tagOf));
  const actionsBox = item.querySelector(".row-actions");
  if (chats.filing && tagView) {
    const go = button(fileUnderWords(chats.filing.name), () => {
      chats.focus = { keys: [`move:${c.id}`, `open:${c.id}`, "editor-toggle"], at: Date.now() };
      return fileChat(c.id, chats.filing.tagId);
    },
      { live: true, title: tagBannerText(chats.filing.name) });
    go.classList.add("history-file-here");
    // The label starts with the words on the button, so Voice Access can say them.
    go.setAttribute("aria-label", `${fileUnderWords(chats.filing.name)}: ${named}`);
    go.dataset.fkey = `file:${c.id}`;
    actionsBox.prepend(go);
    item.dataset.filing = "true";
    item.addEventListener("click", (e) => {
      if (e.target.closest("button, select, input, a, textarea")) return;
      go.click();
    });
  }
  const move = moveControl(c, tagView);
  if (move) actionsBox.insertBefore(move, actionsBox.lastElementChild);
  if (snippet) {
    const p = el("p", "search-snippet");
    renderSnippet(p, snippet, { el });
    main.append(p);
  }
  const kindTag = KIND_TAG[c.kind] || "";
  if (c.hasVoice || c.tainted || (kindTag && c.kind !== "live")) {
    const marks = el("span", "history-marks");
    // What kind of conversation it is (the chat audit, 2026-09-28). A Live
    // session says so in its line ("Live · 12 min · Today 14:05").
    if (kindTag && c.kind !== "live") {
      const kind = el("span", "history-mark history-mark-kind", kindTag);
      kind.dataset.kind = c.kind;
      kind.title = KIND_TITLE[c.kind] || "";
      marks.append(kind);
    }
    if (c.hasVoice) {
      const mic = el("span", "history-mark history-mark-voice", "voice");
      mic.title = "Some of it was said aloud to Jarvis.";
      marks.append(mic);
    }
    if (c.tainted) {
      const taint = el("span", "history-mark history-mark-taint", "read outside text");
      taint.title = TAINT_TITLE;
      marks.append(taint);
    }
    main.append(marks);
  }
  return item;
}

/** The PC's search results, in place of the list, while words are in the box. */
function paintSearchResults(box) {
  const s = chats.search;
  box.append(el("p", "hint history-search-note", SEARCH_NOTE));
  const status = el("p", "empty history-search-status");
  status.setAttribute("role", "status");
  box.append(status);
  const v = s.view;
  if (s.error) {
    status.classList.add("failed");
    status.textContent = `Could not search: ${s.error}`;
    return;
  }
  if (!v) {
    status.textContent = SEARCHING;
    return;
  }
  if (!v.queryOk) {
    status.textContent = v.why;
    return;
  }
  if (s.loading) status.textContent = SEARCHING;
  else if (!v.conversations.length) status.textContent = v.whyNot || SEARCH_NONE;
  else {
    const n = v.conversations.length;
    status.textContent = `${n} ${n === 1 ? "conversation matches" : "conversations match"}.`;
  }
  const list = el("div", "rows history-rows history-search-rows");
  for (const c of v.conversations.filter(matchesTagChip)) {
    list.append(conversationRow(c, { needle: s.query, snippet: c.snippet }));
    if (chats.deleting && chats.deleting.id === c.id) list.append(deletingNode(c));
    if (chats.openId === c.id) list.append(transcriptNode());
  }
  box.append(list);
  const more = searchMoreWords(v);
  if (more) box.append(el("p", "empty", more));
}

/** The ON card left the queue: read the switch again after the backend has
 *  had a moment to apply an approval. Still off: it was denied or ran out
 *  of time, and that is said - the learning switch's handler, for history. */
onQueue((queue) => {
  const ask = chats.ask;
  if (!ask || !ask.cardId || ask.gone) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (items.some((item) => item && item.id === ask.cardId)) return;
  ask.gone = true;
  setTimeout(async () => {
    if (chats.ask !== ask) return;
    chats.at = 0;
    await loadHistory();
    if (chats.ask === ask) {
      chats.ask = null;
      if (!(chats.view && chats.view.enabled)) toast(DENIED_REPLY, "bad");
      paintHistory();
    }
  }, MODEL_ASK_GRACE_MS);
});

// Private answers turned on or off, or a Show ran out: read the list again -
// Rust decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadHistory = () => {
    chats.at = 0;
    if (state.view === "history") loadHistory();
  };
  TAURI.event.listen("security-changed", rereadHistory);
  TAURI.event.listen("private-hidden", rereadHistory);
}

function paintHistorySettings() {
  const box = $("history-settings");
  if (!box) return;
  box.replaceChildren();
  const v = chats.view;
  if (!v) {
    const line = el("p", "empty", chats.error ? `Could not read the chat history: ${chats.error}` : "Reading…");
    if (chats.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadHistory));
    }
    box.append(line);
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", v.why));
    return;
  }

  const label = el("label", "history-switch");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = "history-enabled";
  input.setAttribute("role", "switch");
  input.setAttribute("aria-describedby", "history-switch-detail");
  input.checked = v.enabled;
  label.append(input, el("span", "history-switch-label", SWITCH_LABEL));
  const detail = el("p", "note history-switch-detail", SWITCH_DETAIL);
  detail.id = "history-switch-detail";
  box.append(label, detail);
  // Turning it ON waits for a live link (rule 4); OFF never does.
  if (!v.enabled) {
    input.dataset.title = "Asks you first, with an approval card.";
    liveButtons.add(input);
    syncLiveButton(input);
  }
  input.addEventListener("change", async () => {
    const want = input.checked;
    // Show what the PC says, never what was clicked: ON is only a card.
    input.checked = v.enabled;
    input.disabled = true;
    input.dataset.busy = "true";
    await setHistoryEnabled(want);
  });

  if (chats.ask || v.waiting) {
    box.append(el("p", "hint learning-waiting history-waiting",
      `Waiting for your approval to turn chat history on. Approve it ${APPROVE_WHERE}.`));
  }
  const why = notRecordingLine(v);
  if (why) box.append(el("p", "history-why-not", why));

  const keep = el("label", "history-keep");
  keep.append(el("span", "history-keep-label", "Delete conversations older than"));
  const select = document.createElement("select");
  select.id = "history-keep";
  select.className = "field";
  const choices = KEEP_CHOICES.some((c) => c.days === v.keepDays)
    ? KEEP_CHOICES
    : [...KEEP_CHOICES, { days: v.keepDays, label: keepLabel(v.keepDays) }];
  for (const c of choices) {
    const option = document.createElement("option");
    option.value = String(c.days);
    option.textContent = c.label;
    select.append(option);
  }
  select.value = String(v.keepDays);
  select.dataset.title = "Older conversations are deleted from this PC. There is no undo.";
  liveButtons.add(select);
  syncLiveButton(select);
  select.addEventListener("change", async () => {
    const days = Number(select.value);
    select.value = String(v.keepDays);
    // A shorter period (or any, from "Never") deletes conversations now,
    // with no undo: asked first, the phone's question word for word.
    if (keepNeedsConfirm(v.keepDays, days)
        && !window.confirm(`${keepConfirm(days)}\n\n${KEEP_SUPPORT_NOTE}`)) return;
    select.disabled = true;
    select.dataset.busy = "true";
    await setKeepDays(days);
  });
  keep.append(select);
  box.append(keep);
}

function paintHistoryList() {
  const box = $("history-list");
  if (!box) return;
  // The find box is drawn afresh with the list (the 15-second re-read
  // repaints it): the keyboard and the caret stay where the owner left them.
  const active = document.activeElement;
  const refocus = active && active.id === "history-find"
    ? [active.selectionStart, active.selectionEnd] : null;
  rememberTagFocus();
  paintHistoryListNow(box);
  if (chats.open && $("history-transcript-turns")) paintFound();
  if (refocus) {
    const input = $("history-find");
    if (input) {
      input.focus({ preventScroll: true });
      try { input.setSelectionRange(refocus[0], refocus[1]); } catch { /* type=search may refuse */ }
    }
  }
  if (!chats.batch) giveBackTagFocus();
}

function paintHistoryListNow(box) {
  box.replaceChildren();
  const v = chats.view;
  if (!v) {
    box.append(el("p", "empty", chats.error ? "Nothing to show until the chat history can be read." : "Reading…"));
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", "Nothing to show until this PC keeps chat history."));
    return;
  }
  if (v.hidden) {
    const hidden = el("div", "private-hidden");
    const n = v.hiddenCount;
    hidden.append(el("p", "empty", n
      ? `${n} ${n === 1 ? "conversation" : "conversations"}, hidden until Windows Hello confirms it is you.`
      : "Hidden until Windows Hello confirms it is you."));
    hidden.append(button("Show", revealHistory,
      { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
    // The search box above does nothing while the list is hidden, and used to
    // say nothing about it (the second chat audit, 2026-09-28, desktop C6).
    hidden.append(el("p", "hint", "Searching, and Continue this chat, work again after you press Show."));
    box.append(hidden);
    return;
  }
  // "Search what was said" (section 71; the owner's answer of 2026-09-27:
  // "shown on screen only; nothing saved, nothing handed to the AI"): two
  // letters or more, and the PC's results are shown instead of the list.
  const s = chats.search;
  if (s.query.length >= SEARCH_MIN && !s.oldPc && IS_TAURI) {
    paintSearchResults(box);
    return;
  }
  // A chat just forked whose row is in no list yet (the list read is still
  // on its way): its row and transcript are drawn above, as the phone does.
  const fk = chats.forked;
  if (fk && chats.openId === fk.id && !chats.rows.some((c) => c.id === fk.id)
      && !(s.view?.conversations || []).some((c) => c.id === fk.id)) {
    const top = el("div", "rows history-rows history-forked");
    top.append(conversationRow(fk.row));
    top.append(transcriptNode());
    box.append(top);
  }
  if (!chats.rows.length) {
    box.append(el("p", "empty", chats.tag ? NO_TAG_CHATS : chats.kind ? HISTORY_FILTER_NONE : v.enabled
      ? "No conversations kept yet."
      : "No conversations kept. Chat history is off."));
    return;
  }
  // One letter, or a PC that cannot search the words: the list already
  // loaded, narrowed by its title only - nothing is asked of the PC. The
  // same shape as "What Jarvis knows about you"'s filter (renderFacts).
  const needle = s.query.toLowerCase();
  if (needle && s.oldPc) box.append(el("p", "hint history-search-note", s.oldPc));
  const shown = needle
    ? chats.rows.filter((c) => String(c.title || "").toLowerCase().includes(needle))
    : chats.rows;
  if (needle && !shown.length) {
    box.append(el("p", "empty", chats.more
      ? "No loaded conversations match that search. \"Load older\" may bring in more to search."
      : "No conversations match that search."));
  }
  const appendRow = (list, c) => {
    list.append(conversationRow(c));
    if (chats.deleting && chats.deleting.id === c.id) list.append(deletingNode(c));
    if (chats.openId === c.id) list.append(transcriptNode());
  };
  const tagView = chats.tags && chats.tags.available && !chats.tags.hidden ? chats.tags : null;
  if (tagView && tagView.tags.length && !chats.tag) {
    // Sections, one per tag in the owner's order, "Untagged" last
    // (docs/CHAT-TAGS-DESIGN.md sections 1 and 6). Each header is a button.
    // With no tags at all the list stays flat, as on the phone.
    const exact = !chats.kind && !needle;
    for (const sec of groupRows(shown, tagView, { exact })) {
      box.append(sectionNode(sec, appendRow));
    }
  } else {
    const list = el("div", "rows history-rows");
    for (const c of shown.filter(matchesTagChip)) appendRow(list, c);
    box.append(list);
  }
  if (chats.more) {
    const more = el("div", "row-actions history-more");
    more.append(button(chats.older ? "Loading…" : "Load older", loadOlderHistory,
      { title: "Show the next page of older conversations." }));
    box.append(more);
  }
}

/* ---- Chat tags and sections (history-tags.js; docs/CHAT-TAGS-DESIGN.md) --- */

/** Whether a row belongs under the chip chosen ("" is every chat). */
function matchesTagChip(c) {
  if (!chats.tag) return true;
  if (chats.tag === "none") return c.tagId === null || c.tagId === undefined;
  return c.tagId === Number(chats.tag);
}

/** A tag's small pill: its icon and its name, in its colour. */
function tagPillNode(tag) {
  const pill = el("span", "history-tagpill");
  pill.dataset.colour = String(tag.colour);
  pill.append(iconNode(tag.icon), el("span", "", tag.name));
  pill.title = `Tag: ${tag.name}`;
  return pill;
}

/** One collapsible section: a header button (icon, name, count, chevron)
 *  and the rows below it. Open or closed is remembered on this device. */
function sectionNode(sec, appendRow) {
  const wrap = el("div", "history-section");
  wrap.dataset.key = sec.key;
  if (sec.tag) wrap.dataset.colour = String(sec.tag.colour);
  const name = sec.tag ? sec.tag.name : UNTAGGED;
  let open = sectionIsOpen(chats.sectionFlags, sec.key);
  const head = el("button", "history-section-head");
  head.type = "button";
  const bodyId = `history-section-${sec.key}`;
  head.setAttribute("aria-controls", bodyId);
  head.dataset.fkey = `sec:${sec.key}`;
  head.append(
    iconNode(sec.tag ? sec.tag.icon : "folder"),
    el("span", "history-section-name", tagHeaderText(name, sec.count)),
    el("span", "history-section-chevron"),
  );
  head.querySelector(".history-section-chevron").setAttribute("aria-hidden", "true");
  const body = el("div", "history-section-body");
  body.id = bodyId;
  if (sec.rows.length) {
    const list = el("div", "rows history-rows");
    for (const c of sec.rows) appendRow(list, c);
    body.append(list);
  } else {
    body.append(el("p", "empty", NOT_LOADED_LINE));
  }
  const apply = () => {
    head.setAttribute("aria-expanded", String(open));
    // The state is aria-expanded's to say; the label is the name and count.
    head.setAttribute("aria-label", sectionLabel(name, sec.count));
    body.hidden = !open;
  };
  apply();
  head.addEventListener("click", () => {
    open = !open;
    chats.sectionFlags = saveOpenFlag(sec.key, open);
    apply();
  });
  wrap.append(head, body);
  return wrap;
}

/** "Move to": a menu of the tags and "No tag", on a row. Null when there
 *  are no tags to move to (an older PC, or the list is hidden). */
function moveControl(c, tagView) {
  if (!tagView || !tagView.tags.length) return null;
  const select = document.createElement("select");
  select.className = "field history-move";
  select.dataset.fkey = `move:${c.id}`;
  select.setAttribute("aria-label", `${MOVE_TO}: ${c.title || NO_TITLE}`);
  const first = document.createElement("option");
  first.value = "";
  first.textContent = MOVE_PLACEHOLDER;
  select.append(first);
  for (const t of tagView.tags) {
    const o = document.createElement("option");
    o.value = String(t.id);
    o.textContent = t.name;
    o.disabled = t.id === c.tagId;
    select.append(o);
  }
  const none = document.createElement("option");
  none.value = "none";
  none.textContent = NO_TAG;
  none.disabled = c.tagId === null || c.tagId === undefined;
  select.append(none);
  select.value = "";
  select.dataset.title = `${MOVE_TO}… Files this chat under a tag, or takes its tag off. Nothing else changes.`;
  liveButtons.add(select);
  syncLiveButton(select);
  select.addEventListener("change", async () => {
    const value = select.value;
    select.value = "";
    if (!value) return;
    select.disabled = true;
    // The row moves to another section: keep the keyboard on it if it is
    // still on screen, else on the header of the section it landed under.
    chats.focus = {
      keys: [`move:${c.id}`, `sec:${value === "none" ? "none" : value}`, `open:${c.id}`,
        `chip:${chats.tag}`, "editor-toggle"],
      at: Date.now(),
    };
    await fileChat(c.id, value === "none" ? null : Number(value));
  });
  return select;
}

/** Files ONE chat under a tag (tagId a number) or takes its tag off (null).
 *  No card; Rust holds it on a stale link. Returns whether it worked. */
async function fileChat(id, tagId) {
  let ok = false;
  try {
    const out = await invoke("brain_history_tag", { id, tagId });
    if (out && out.ok === false) {
      toast(tagErrorWords(out), "bad");
    } else {
      ok = true;
      const t = tagById(chats.tags, tagId);
      toast(tagId === null ? UNFILED_WORDS : filedWords(t ? t.name : "that tag"), "ok");
      const setTag = (r) => { if (r.id === id) r.tagId = tagId; };
      chats.rows.forEach(setTag);
      if (chats.search.view) chats.search.view.conversations.forEach(setTag);
      // Filing from the banner is done: the banner goes, the search stays.
      if (chats.filing && chats.filing.tagId === tagId) chats.filing = null;
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.at = 0;
  await loadHistory();
  return ok;
}

/** The chip row, the Tags editor and the banner, above the search box. */
function paintHistoryTagBar() {
  paintTagBarNow();
  if (!chats.batch) giveBackTagFocus();
}

function paintTagBarNow() {
  const box = $("history-tagbar");
  if (!box) return;
  const v = chats.view;
  const tv = chats.tags;
  const show = Boolean(v && v.available && !v.hidden && tv && tv.available && !tv.hidden);
  // "Suggest tags overnight" holds no chat words, so its row still shows while
  // the private lists are hidden (JARVIS-API.md section 104.4); nothing else does.
  const sg = chats.suggest;
  const rowOnly = !show && Boolean(v && v.available && tv && tv.available && tv.hidden
    && !(sg.loaded && !(sg.state && sg.state.available)));
  box.hidden = !show && !rowOnly;
  // Typing in the editor survives a repaint: the control that had the
  // keyboard is found again by its `data-fkey` (giveBackTagFocus, after paint).
  rememberTagFocus();
  box.replaceChildren();
  if (rowOnly) {
    box.append(suggestRowNode());
    if (!chats.suggest.loaded && !chats.suggest.reading) refreshSuggest();
    return;
  }
  if (!show) return;

  if (chats.filing) {
    const t = tagById(tv, chats.filing.tagId);
    const banner = el("div", "history-file-banner");
    banner.setAttribute("role", "status");
    if (t) banner.dataset.colour = String(t.colour);
    banner.append(el("p", "", tagBannerText(chats.filing.name)));
    const cancel = button(BANNER_CANCEL, () => { chats.filing = null; paintHistory(); });
    cancel.dataset.fkey = "banner-cancel";
    banner.append(cancel);
    box.append(banner);
  }

  const chips = el("div", "tag-chips");
  chips.setAttribute("role", "group");
  chips.setAttribute("aria-label", TAG_CHIPS_LABEL);
  const chip = (value, label, count, tag) => {
    const b = el("button", "tag-chip");
    b.type = "button";
    if (tag) {
      b.dataset.colour = String(tag.colour);
      b.append(iconNode(tag.icon));
    }
    b.append(el("span", "", label));
    if (count !== null) b.append(el("span", "tag-chip-count", String(count)));
    b.setAttribute("aria-pressed", String(chats.tag === value));
    b.dataset.fkey = `chip:${value}`;
    b.addEventListener("click", () => setTagChip(value));
    return b;
  };
  chips.append(chip("", TAG_ALL, null, null));
  for (const t of tv.tags) chips.append(chip(String(t.id), t.name, t.count, t));
  chips.append(chip("none", UNTAGGED, tv.untagged, null));
  const edit = el("button", "btn small tag-editor-toggle", TAGS_TITLE);
  edit.type = "button";
  edit.id = "tag-editor-toggle";
  edit.dataset.fkey = "editor-toggle";
  edit.setAttribute("aria-expanded", String(chats.editor.open));
  edit.setAttribute("aria-controls", "tag-editor");
  edit.addEventListener("click", () => {
    chats.editor.open = !chats.editor.open;
    chats.editor.error = "";
    paintHistoryTagBar();
    // The switch's state is read when the editor opens (no push).
    if (chats.editor.open) refreshSuggest();
  });
  chips.append(edit);
  box.append(chips);
  if (chats.editor.open) box.append(tagEditorNode(tv));
}

/* ---- Keeping the keyboard where it was (docs/CHAT-TAGS-DESIGN.md section 10) ----
 *
 * Every interactive tag control carries a stable `data-fkey` (chip:3, sec:none,
 * move:<chat id>, up:<tag id>...). The list and the tag bar are drawn afresh
 * on each repaint, so the control that had the keyboard is remembered by that
 * key and found again afterwards - even when pressing it disabled it for a
 * moment (which drops focus). A control that is gone hands the keyboard to a
 * named neighbour (a moved row to the header it landed under). */

const FOCUS_KEEP_MS = 30_000;

/** The keys to try after `key`, in order, when the control itself is gone. */
function focusFallbacks(key) {
  const [kind, id] = [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)];
  switch (kind) {
    case "up": return [`down:${id}`, `name:${id}`];
    case "down": return [`up:${id}`, `name:${id}`];
    case "del": return ["add-name", "editor-toggle"];
    case "rename": return [`name:${id}`];
    case "move": return [`open:${id}`];
    case "file": return [`move:${id}`, `open:${id}`];
    case "fork": return [`open:${id.slice(0, id.lastIndexOf(":"))}`];
    case "chip": return ["chip:"];
    default: return key === "add-btn" ? ["add-name"] : [];
  }
}

function inTagBoxes(node) {
  return Boolean(node && node.closest && node.closest("#history-tagbar, #history-list"));
}

/** Notes which tag control has the keyboard (and its caret). */
function noteTagFocus(node) {
  const key = node && node.dataset ? node.dataset.fkey : "";
  if (!key) return;
  const caret = typeof node.selectionStart === "number" && node.type !== "search";
  chats.focus = {
    keys: [key, ...focusFallbacks(key)],
    start: caret ? node.selectionStart : null,
    end: caret ? node.selectionEnd : null,
    at: Date.now(),
  };
}

/** Called just before a repaint: the caret has moved since the last focus event. */
function rememberTagFocus() {
  const a = document.activeElement;
  if (a && a.dataset && a.dataset.fkey && inTagBoxes(a)) noteTagFocus(a);
}

let givingBackFocus = false;

/** Called after a repaint: puts the keyboard back on the control it was on. */
function giveBackTagFocus() {
  const f = chats.focus;
  if (!f || Date.now() - f.at > FOCUS_KEEP_MS) return;
  const a = document.activeElement;
  if (a && a !== document.body && a.isConnected) return;   // the keyboard is somewhere real
  const boxes = ["history-tagbar", "history-list"].map((id) => $(id)).filter(Boolean);
  for (const [i, key] of f.keys.entries()) {
    let found = null;
    for (const box of boxes) {
      for (const n of box.querySelectorAll("[data-fkey]")) {
        if (n.dataset.fkey === key) { found = n; break; }
      }
      if (found) break;
    }
    if (!found || found.disabled || found.closest("[hidden]")) continue;
    givingBackFocus = true;
    try {
      found.focus({ preventScroll: true });
      if (i === 0 && f.start !== null && f.start !== undefined) {
        try { found.setSelectionRange(f.start, f.end); } catch { /* a select has no caret */ }
      }
    } finally {
      givingBackFocus = false;
    }
    return;
  }
}

/** A tag menu, the editor or a text box in it is in use: no repaint under the hand. */
function tagControlBusy() {
  const a = document.activeElement;
  if (!a || !a.closest) return false;
  if (a.closest("#tag-editor")) return true;
  return a.tagName === "SELECT" && inTagBoxes(a);
}

if (typeof document !== "undefined") {
  document.addEventListener("focusin", (e) => {
    if (givingBackFocus) return;
    if (inTagBoxes(e.target) && e.target.dataset && e.target.dataset.fkey) noteTagFocus(e.target);
    else chats.focus = null;
  });
  // A click on empty space (or anything that is not a tag control) lets go.
  document.addEventListener("pointerdown", (e) => {
    if (!(e.target && e.target.closest && e.target.closest("[data-fkey]"))) chats.focus = null;
  }, true);
  // A repaint held back while a menu was open happens once it is closed.
  document.addEventListener("focusout", () => {
    if (!chats.paintPending) return;
    setTimeout(() => {
      if (chats.paintPending && !tagControlBusy() && state.view === "history") paintHistory();
    }, 0);
  });
}

/** A chip was pressed: show one tag's chats (the PC filters), or all. */
function setTagChip(value) {
  chats.tag = chats.tag === value ? "" : value;
  chats.rows = [];
  chats.more = false;
  chats.openId = null;
  chats.open = null;
  chats.openFacts = null;
  chats.view = chats.view ? { ...chats.view, conversations: [] } : null;
  paintHistory();
  loadHistory();
  if (chats.search.query.length >= SEARCH_MIN) onHistorySearch();
}

/** One edit to the tags (add, rename, style, move, delete). Says the PC's
 *  refusal as one plain sentence, in the editor. */
async function editTags(args) {
  const editor = chats.editor;
  editor.error = "";
  try {
    const out = await invoke("brain_history_tags_edit", {
      op: args.op, id: args.id ?? null, name: args.name ?? null, colour: args.colour ?? null,
      icon: args.icon ?? null, before: args.before ?? null,
    });
    if (out && out.ok === false) {
      editor.error = tagErrorWords(out);
      paintHistoryTagBar();
      return false;
    }
  } catch (error) {
    editor.error = errorText(error);
    paintHistoryTagBar();
    return false;
  }
  chats.at = 0;
  await loadHistory();
  return true;
}

function optionsFor(select, items, current) {
  for (const [value, label] of items) {
    const o = document.createElement("option");
    o.value = String(value);
    o.textContent = label;
    select.append(o);
  }
  select.value = String(current);
}

/** A name box's value cut to NAME_MAX code points (never inside a surrogate
 *  pair), the caret kept. The browser's own maxLength counts UTF-16 units. */
function limitNameField(input) {
  const clipped = clipTagName(input.value);
  if (clipped !== input.value) {
    const caret = Math.min(input.selectionStart ?? clipped.length, clipped.length);
    queueMicrotask(() => { try { input.setSelectionRange(caret, caret); } catch { /* no caret */ } });
  }
  return clipped;
}

const COLOUR_ITEMS = TAG_COLOURS.map((c) => [c.slot, c.name[0].toUpperCase() + c.name.slice(1)]);
const ICON_ITEMS = TAG_ICONS.map((n) => [n, n[0].toUpperCase() + n.slice(1)]);

/** The Tags editor: add, rename, recolour, pick an icon, reorder, delete. */
function tagEditorNode(tv) {
  const editor = chats.editor;
  const box = el("div", "tag-editor");
  box.id = "tag-editor";
  box.append(el("h3", "", TAGS_TITLE), el("p", "note", TAGS_EDITOR_NOTE));
  tv.tags.forEach((t, i) => {
    const line = el("div", "tag-editor-row");
    line.dataset.colour = String(t.colour);
    line.dataset.tag = String(t.id);
    line.append(tagPillNode(t));
    const input = document.createElement("input");
    input.className = "field";
    input.id = `tag-name-${t.id}`;
    input.dataset.fkey = `name:${t.id}`;
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("aria-label", `${NAME_LABEL}: ${t.name}`);
    input.value = editor.drafts.names[t.id] ?? t.name;
    input.addEventListener("input", () => {
      input.value = limitNameField(input);
      editor.drafts.names[t.id] = input.value;
    });
    const rename = async () => {
      const name = validTagName(input.value);
      if (name === t.name) { delete editor.drafts.names[t.id]; return; }
      if (name === null) {
        editor.error = tagErrorWords({ error: "bad_name" });
        paintHistoryTagBar();
        return;
      }
      if (await editTags({ op: "rename", id: t.id, name })) delete editor.drafts.names[t.id];
    };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); rename(); } });
    const colour = document.createElement("select");
    colour.className = "field";
    colour.setAttribute("aria-label", `Colour for ${t.name}`);
    colour.dataset.fkey = `colour:${t.id}`;
    optionsFor(colour, COLOUR_ITEMS, t.colour);
    colour.addEventListener("change", () => editTags({ op: "style", id: t.id, colour: Number(colour.value) }));
    const icon = document.createElement("select");
    icon.className = "field";
    icon.setAttribute("aria-label", `Icon for ${t.name}`);
    icon.dataset.fkey = `icon:${t.id}`;
    optionsFor(icon, ICON_ITEMS, t.icon);
    icon.addEventListener("change", () => editTags({ op: "style", id: t.id, icon: icon.value }));
    for (const s of [colour, icon]) { liveButtons.add(s); syncLiveButton(s); }
    const up = button(MOVE_UP,
      () => (i === 0 ? null : editTags({ op: "move", id: t.id, before: tv.tags[i - 1].id })),
      { live: true, title: `${MOVE_UP}: ${t.name}` });
    up.disabled = i === 0;
    up.setAttribute("aria-label", `${MOVE_UP}: ${t.name}`);
    up.dataset.fkey = `up:${t.id}`;
    const down = button(MOVE_DOWN,
      () => editTags({ op: "move", id: t.id, before: tv.tags[i + 2] ? tv.tags[i + 2].id : null }),
      { live: true, title: `${MOVE_DOWN}: ${t.name}` });
    down.setAttribute("aria-label", `${MOVE_DOWN}: ${t.name}`);
    down.dataset.fkey = `down:${t.id}`;
    down.disabled = i === tv.tags.length - 1;
    const del = button(DELETE_TAG, async () => {
      if (!window.confirm(tagDeleteConfirm(t.name, t.count))) return;
      // If its chip was chosen, the re-read finds the tag gone and shows All.
      await editTags({ op: "delete", id: t.id });
    }, { danger: true, live: true, title: `${DELETE_TAG}: ${t.name}` });
    del.setAttribute("aria-label", `${DELETE_TAG}: ${t.name}`);
    del.dataset.fkey = `del:${t.id}`;
    const renameBtn = button(TAG_RENAME, rename, { live: true, title: `${TAG_RENAME}: ${t.name}` });
    renameBtn.setAttribute("aria-label", `${TAG_RENAME}: ${t.name}`);
    renameBtn.dataset.fkey = `rename:${t.id}`;
    line.append(input, renameBtn, colour, icon, up, down, del);
    box.append(line);
  });

  // Add a tag.
  const add = el("div", "tag-editor-row tag-editor-add");
  const draft = editor.drafts.add;
  const name = document.createElement("input");
  name.className = "field";
  name.id = "tag-add-name";
  name.dataset.fkey = "add-name";
  name.type = "text";
  name.autocomplete = "off";
  name.spellcheck = false;
  name.placeholder = ADD_TAG;
  name.setAttribute("aria-label", `${ADD_TAG}: ${NAME_LABEL}`);
  name.value = draft.name;
  name.addEventListener("input", () => {
    name.value = limitNameField(name);
    draft.name = name.value;
  });
  const colour = document.createElement("select");
  colour.className = "field";
  colour.id = "tag-add-colour";
  colour.dataset.fkey = "add-colour";
  colour.setAttribute("aria-label", `${ADD_TAG}: colour`);
  optionsFor(colour, COLOUR_ITEMS, draft.colour);
  colour.addEventListener("change", () => { draft.colour = Number(colour.value); });
  const icon = document.createElement("select");
  icon.className = "field";
  icon.id = "tag-add-icon";
  icon.dataset.fkey = "add-icon";
  icon.setAttribute("aria-label", `${ADD_TAG}: icon`);
  optionsFor(icon, ICON_ITEMS, draft.icon);
  icon.addEventListener("change", () => { draft.icon = icon.value; });
  const addNow = async () => {
    const wanted = validTagName(draft.name);
    if (!wanted) { editor.error = tagErrorWords({ error: "bad_name" }); paintHistoryTagBar(); return; }
    if (await editTags({ op: "add", name: wanted, colour: draft.colour, icon: draft.icon })) {
      draft.name = "";
      paintHistoryTagBar();
    }
  };
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addNow(); } });
  const addBtn = button(ADD_TAG, addNow, { live: true, title: `${ADD_TAG}. Up to ${MAX_TAGS} tags.` });
  addBtn.disabled = tv.tags.length >= MAX_TAGS;
  addBtn.dataset.fkey = "add-btn";
  add.append(name, colour, icon, addBtn);
  liveButtons.add(colour); liveButtons.add(icon); syncLiveButton(colour); syncLiveButton(icon);
  box.append(add);
  if (tv.tags.length >= MAX_TAGS) {
    box.append(el("p", "hint", tagErrorWords({ error: "too_many_tags" })));
  }
  const err = el("p", "tag-editor-error failed", editor.error);
  err.setAttribute("role", "alert");
  err.hidden = !editor.error;
  box.append(err);
  box.append(suggestRowNode());
  if (!chats.suggest.loaded && !chats.suggest.reading) refreshSuggest();
  return box;
}

/* ---- Suggest tags overnight (JARVIS-API.md section 104; the owner, 2026-09-30) ----
 *
 * A switch, a one-line state and how many suggestion cards wait. NOTHING is
 * filed without a tap on Approve: each suggestion is an ordinary approval
 * card (action chat_tag_suggest), shown by the same approvals flow as every
 * other card, with the chat's title taken out while the private lists are
 * hidden (stream.rs hide_private_cards). Turning it ON raises ONE card on the
 * PC, so the switch stays OFF here - and says it is waiting - until a later
 * read says it is enabled; OFF is at once. Read when the editor opens and
 * after every change; there is no push. Nothing about it is kept on this
 * device. Writes wait for a live link (rule 4). */

/** Reads the switch's state from the PC and redraws the row if it moved. */
async function refreshSuggest() {
  const sg = chats.suggest;
  if (sg.reading || !IS_TAURI) return;
  sg.reading = true;
  let next = null;
  try {
    next = readSuggest(await invoke("brain_history_tag_suggest", { enabled: null }));
  } catch {
    next = readSuggest({ available: false });
  }
  sg.reading = false;
  sg.loaded = true;
  const moved = JSON.stringify(next) !== JSON.stringify(sg.state);
  sg.state = next;
  // A read that says it is on ends the "waiting for your approval" line.
  const cleared = Boolean(next.enabled && !sg.isError && sg.said);
  if (cleared) sg.said = "";
  if (moved || cleared) paintHistoryTagBar();
}

/** Turns it on (a card) or off (at once), then reads what the PC now says. */
async function setSuggest(want) {
  const sg = chats.suggest;
  if (sg.busy || !IS_TAURI) return;
  sg.busy = true;
  sg.said = "";
  sg.isError = false;
  paintHistoryTagBar();
  try {
    const w = suggestWriteResult(await invoke("brain_history_tag_suggest", { enabled: want }));
    if (!w.ok) sg.isError = true;
    sg.said = w.said;
  } catch (error) {
    sg.isError = true;
    sg.said = errorText(error);
  }
  sg.busy = false;
  sg.reading = false;
  await refreshSuggest();
  paintHistoryTagBar();
}

function suggestRowNode() {
  const sg = chats.suggest;
  const box = el("div", "tag-suggest");
  box.id = "tag-suggest";
  const s = sg.state;
  if (!sg.loaded) {
    box.append(el("p", "note", SUGGEST_READING));
    return box;
  }
  if (!s || !s.available) {
    box.append(el("p", "note", SUGGEST_OLD_PC));
    return box;
  }
  const label = el("label", "history-switch");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = "tag-suggest-enabled";
  input.dataset.fkey = "suggest-switch";
  input.setAttribute("role", "switch");
  input.setAttribute("aria-describedby", "tag-suggest-state");
  // What the PC says, never what was clicked: ON is only a card.
  input.checked = s.enabled;
  label.append(input, el("span", "history-switch-label", SUGGEST_LABEL));
  const state = el("p", "note tag-suggest-state", sg.busy ? SUGGEST_ASKING : suggestStateLine(s));
  state.id = "tag-suggest-state";
  box.append(label, state);
  // A write, so a live link is needed either way (rule 4).
  input.dataset.title = s.enabled ? "" : "Asks you first, with an approval card.";
  liveButtons.add(input);
  syncLiveButton(input);
  if (sg.busy) input.disabled = true;
  input.addEventListener("change", () => {
    const want = input.checked;
    input.checked = s.enabled;
    setSuggest(want);
  });
  const waiting = suggestWaitingLine(s.waiting);
  if (waiting) box.append(el("p", "hint learning-waiting tag-suggest-waiting", waiting));
  if (sg.said) {
    const said = el("p", `hint tag-suggest-said${sg.isError ? " failed" : ""}`, sg.said);
    said.setAttribute("role", sg.isError ? "alert" : "status");
    box.append(said);
  }
  return box;
}

/* ---- Filing an older chat: "label my chat about the boiler as Home" ------- */

/**
 * The Jarvis bar left `open_brain: "history"` with `file_under` (a tag id)
 * and `history_q` (search words). Open History with the words in the search
 * box and the banner "Tap the chat to file it under {name}."; nothing is
 * filed until the owner taps a chat.
 */
async function applyHistoryFilePlace(extras) {
  const place = readFilePlace(extras);
  if (!place) return;
  chats.filingPending = place;
  await resolveFilingPending();
}

async function resolveFilingPending() {
  const pending = chats.filingPending;
  if (!pending || !IS_TAURI) return;
  let tv = null;
  try {
    tv = readTags(await invoke("brain_history_tags"));
  } catch (error) {
    toast(errorText(error), "bad");
    chats.filingPending = null;
    return;
  }
  // The tag names are hidden with the list: wait for Show, then come back.
  if (tv.hidden) return;
  chats.filingPending = null;
  const t = tagById(tv, pending.tagId);
  if (!t) {
    toast(tagErrorWords({ error: "tag_not_found" }), "bad");
    return;
  }
  chats.tags = tv;
  chats.filing = { tagId: t.id, name: t.name };
  const box = $("history-filter");
  if (box) box.value = pending.q;
  if (chats.tag) {
    chats.tag = "";
    chats.rows = [];
    chats.more = false;
    loadHistory();
  }
  onHistorySearch();
  paintHistory();
}

/**
 * Above the list: "Show" (every kind, or Live only, and the rest) and a
 * way to "Forget a time frame" from the top of History - it used to be at
 * the very bottom (the chat audit, 2026-09-28).
 */
function paintHistoryTools() {
  const box = $("history-tools");
  if (!box) return;
  const v = chats.view;
  box.hidden = !v || !v.available || v.hidden;
  if (box.hidden) return;
  if (box.dataset.built === "true") {
    const select = $("history-kind");
    if (select && select.value !== chats.kind) select.value = chats.kind;
    return;
  }
  box.dataset.built = "true";
  box.replaceChildren();
  const label = el("label", "history-kind-label");
  label.append(el("span", "", HISTORY_FILTER_LABEL));
  const select = document.createElement("select");
  select.id = "history-kind";
  select.className = "field";
  for (const [value, words] of HISTORY_FILTERS) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = words;
    select.append(option);
  }
  select.value = chats.kind;
  select.addEventListener("change", () => {
    chats.kind = select.value;
    chats.rows = [];
    chats.more = false;
    chats.openId = null;
    chats.open = null;
    chats.openFacts = null;
    chats.view = chats.view ? { ...chats.view, conversations: [] } : null;
    paintHistoryList();
    loadHistory();
    // A typed search runs again for the kind now chosen.
    if (chats.search.query.length >= SEARCH_MIN) onHistorySearch();
  });
  label.append(select);
  const link = button(FORGET_RANGE_LINK, () => openForgetRange(), { title: FORGET_RANGE_LINK_TITLE });
  link.classList.add("history-forget-range-link");
  box.append(label, link);
}

/** Chats were removed or put back somewhere else (an Undo, "Forget a time
 *  frame", "Erase the words" with its chat): read the list again now. */
function historyChanged() {
  chats.at = 0;
  if (state.view === "history") loadHistory();
}
window.addEventListener(HISTORY_CHANGED, historyChanged);

function paintHistory() {
  chats.paintPending = false;
  chats.batch = true;
  try {
    paintHistoryTools();
    paintHistoryTagBar();
    paintHistorySettings();
    paintHistoryList();
  } finally {
    chats.batch = false;
  }
  giveBackTagFocus();
}

function renderHistory() {
  // A tag menu or the editor in use is not repainted under the owner's hand.
  if (tagControlBusy()) chats.paintPending = true;
  else paintHistory();
  if (IS_TAURI && !chats.loading && Date.now() - chats.at > HISTORY_READ_MS) {
    loadHistory({ background: true });
  }
}

/* ==========================================================================
   Automatic learning (JARVIS-API.md section 19). On the Memory tab, next to
   the learning switch; the words are auto-learn.js, the commands
   brain/auto_learn.rs.

   The two switches are the learning switch's shape: ON raises one approval
   card and shows "Waiting for your approval" until the card leaves the
   queue - including a card raised on the phone; OFF is immediate. Rust
   holds ON on a stale link, and the switch is greyed then; OFF never is.
   While a card waits the switch is greyed too (a second ON would only ask
   for the same card), and "Cancel the request" in the waiting line sends
   OFF, which withdraws the card on the PC (FIXLIST 8, R6). Under each
   switch: how its newest card ended (`auto_last` / `sensitive_last`, in
   the PC's plain words when it refused), and for "Learn automatically" the
   PC's sentence when its settings file was damaged (`why`).
   "Saved automatically" lists what was saved without a card, newest first,
   with Forget on each (brain_memory_forget, one fact, after a confirm) and
   "Load older". A `memory_saved` event is a quiet line that opens the list.
   ========================================================================== */

const autoL = {
  /** readAuto() of the first page, or null before the first read. */
  view: null,
  /** Every fact shown, newest first: the first page, then older ones. */
  rows: [],
  more: false,
  error: "",
  /** The list alone could not be read (the switches could). */
  listError: "",
  at: 0,
  loading: false,
  /** A read was asked for while one was in flight: read once more after. */
  again: false,
  older: false,
  /** `{ cardId, gone }` while an ON card waits, per switch. */
  ask: { auto: null, sensitive: null },
  /** Whether each switch's card was in the queue at the last look. */
  seen: { auto: false, sensitive: false },
  /** Ids of ON cards withdrawn by turning the switch OFF while they waited
   *  (R6). The PC has let go of them - approving one changes nothing - but
   *  the card stays in the queue until it is answered or runs out, so the
   *  switch must not keep saying "waiting" for it. */
  withdrawn: { auto: new Set(), sensitive: new Set() },
  /** Ids from `memory_saved` events the owner has not looked at yet. */
  unseen: new Set(),
};
const AUTO_READ_MS = 15000;

async function loadAuto() {
  if (autoL.loading) {
    autoL.again = true;
    return;
  }
  autoL.loading = true;
  try {
    // The switches come from GET /api/memory/learning, the list from GET
    // /api/memory/auto; an older PC without the first is read from the
    // second (readAuto). Both failing is the one error worth a Retry.
    const [list, status] = await Promise.allSettled([
      invoke("brain_memory_auto_list", { before: null, limit: AUTO_PAGE }),
      invoke("brain_memory_learning_status"),
    ]);
    if (list.status === "rejected" && status.status === "rejected") throw list.reason;
    autoL.listError = list.status === "rejected" ? errorText(list.reason) : "";
    const v = readAuto(list.status === "fulfilled" ? list.value : null,
      status.status === "fulfilled" ? status.value : null);
    autoL.view = v;
    // Pages "Load older" brought in stay; a hidden list keeps nothing.
    const kept = v.hidden ? { rows: [], more: false }
      : refreshAutoRows(autoL.rows, v.facts, AUTO_PAGE, autoL.more);
    autoL.rows = kept.rows;
    autoL.more = kept.more;
    autoL.error = "";
    if (v.auto) autoL.ask.auto = null;           // the card was approved
    if (v.sensitive) autoL.ask.sensitive = null;
  } catch (error) {
    autoL.error = errorText(error);
  } finally {
    autoL.loading = false;
    autoL.at = Date.now();
  }
  if (autoL.again) {
    autoL.again = false;
    await loadAuto();
    return;
  }
  if (state.view === "memory") paintAuto();
}

async function loadOlderAuto() {
  const before = olderAuto(autoL.rows);
  if (before === null || autoL.older) return;
  autoL.older = true;
  try {
    const v = readAuto(await invoke("brain_memory_auto_list", { before, limit: AUTO_PAGE }), null);
    autoL.rows = addAutoPage(autoL.rows, v.facts);
    autoL.more = v.facts.length >= AUTO_PAGE;
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    autoL.older = false;
  }
  paintAuto();
}

/** Whether the approval queue holds this switch's ON card, wherever it was
 *  raised - this window, the phone, or anywhere else. */
function autoCardWaiting(which, queue = currentQueue()) {
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  const action = AUTO_SWITCHES[which].action;
  const gone = autoL.withdrawn[which];
  return items.some((item) => item && item.action === action && !gone.has(item.id));
}

async function setAutoSwitch(which, on) {
  const sw = AUTO_SWITCHES[which];
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke(sw.command, { enabled: on });
    const said = out && typeof out.message === "string" ? out.message.trim() : "";
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else if (on && out && out.waiting) {
      // ON raises an approval card: it is NOT on yet.
      autoL.ask[which] = { cardId: await findNewCard(waitingBefore) };
      toast(said || sw.waiting(APPROVE_WHERE), "ok");
    } else {
      autoL.ask[which] = null;
      // OFF withdraws a waiting ON card on the PC (R6): the card is not
      // counted as waiting any more, even while it is still in the queue.
      if (!on) {
        for (const item of currentQueue().items || []) {
          if (item && item.action === sw.action && item.id) autoL.withdrawn[which].add(item.id);
        }
      }
      // The PC's own sentence first, both ways (FIXLIST 5).
      toast(said || (on ? sw.on : sw.off), "ok");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  autoL.at = 0;
  await loadAuto();
}

/** "Erase the words" on one fact, from either list: asks first, then one
 *  brain_memory_erase for that id (held on a stale link in Rust, like
 *  Forget). An erased fact is no longer current, so it leaves "Saved
 *  automatically" too.
 *
 *  "Also delete the chat it came from" (the owner's decision, 2026-09-27):
 *  a second yes/no, asked right after the first - `window.confirm` has no
 *  room for a checkbox, so the option is its own confirm. Cancelling it
 *  still erases the fact; it only skips deleting the chat too. */
async function eraseFact(f) {
  if (!window.confirm(eraseQuestion(f))) return;
  // Since the chat audit (2026-09-28) the second question names the chat
  // (its title and when), and is not asked at all when no chat is on record
  // for this fact. A PC that cannot say asks as before.
  let chat;
  try {
    chat = readFactChat(await invoke("brain_fact_chat", { id: Number(f.id) }));
  } catch {
    chat = undefined;
  }
  const others = chat ? await otherFactsInChat(invoke, chat, f.id) : 0;
  const alsoChat = chat === undefined ? window.confirm(ERASE_ALSO_CHAT_CONFIRM)
    : chat ? window.confirm(eraseAlsoChatNamedConfirm(chat, whenLine(chat.updated), others))
      : false;
  const out = await memoryWrite(
    "brain_memory_erase",
    { id: Number(f.id), also_delete_conversation: alsoChat },
    (reply) => (reply && reply.chat_deleted ? ERASED_AND_CHAT_DELETED
      : alsoChat || chat === null ? ERASED_NO_CHAT : ERASED),
  );
  if (out && out.ok !== false) {
    autoL.rows = autoL.rows.filter((r) => r.id !== Number(f.id));
    paintAuto();
    if (out.chat_deleted) {
      window.dispatchEvent(new CustomEvent(HISTORY_CHANGED));
      if (chat) tellChatsGone([chat.id]);
    }
  }
}

async function forgetAuto(f) {
  if (!window.confirm(forgetQuestion(f))) return;
  const out = await memoryWrite("brain_memory_forget", { id: f.id }, FORGOTTEN);
  if (out && out.ok !== false) {
    autoL.rows = autoL.rows.filter((r) => r.id !== f.id);
    paintAuto();
  }
}

/** A `memory_saved` event: count what was saved, and read the list again. */
function noteMemorySaved(data) {
  const ids = savedIds(data);
  if (!ids.length) return;
  for (const id of ids) autoL.unseen.add(id);
  autoL.at = 0;
  paintSavedLine();
  if (state.view === "memory") loadAuto();
}

/** The whole "Saved automatically" list: shown and scrolled to. */
async function showSavedList() {
  if (state.view !== "memory") await showView("memory");
  const card = $("memory-auto-card");
  if (card) {
    card.scrollIntoView({ block: "start" });
    dom.memoryAutoList.focus({ preventScroll: true });
  }
}

/* "Jarvis remembered 2 things" opens the facts themselves (the owner's
   decision, 2026-09-25; JARVIS-API.md section 19.5): their words read from
   the PC by id (memory-used.js, brain/used.rs memory_used - hidden like
   every memory list under Windows Hello), each with Forget and "Erase the
   words", the same one-fact commands and confirms as the list below. */
const savedFacts = { ids: [], open: false, view: null, error: "", loading: false };

async function loadSavedFacts() {
  if (!savedFacts.open || !savedFacts.ids.length || !IS_TAURI) return;
  savedFacts.loading = true;
  paintSavedLine();
  try {
    savedFacts.view = readUsed(await invoke("memory_used", { ids: savedFacts.ids }));
    savedFacts.error = "";
  } catch (error) {
    savedFacts.view = null;
    savedFacts.error = errorText(error);
  } finally {
    savedFacts.loading = false;
  }
  paintSavedLine();
}

/** The quiet line opens those facts, and the line goes - here and in
 *  Rust's copy of the count (below). */
async function openSavedList() {
  savedFacts.ids = [...autoL.unseen];
  savedFacts.open = true;
  savedFacts.view = null;
  autoL.unseen.clear();
  if (IS_TAURI) invoke("brain_memory_saved_unseen", { seen: true }).catch(() => {});
  if (state.view !== "memory") await showView("memory");
  paintSavedLine();
  await loadSavedFacts();
  const box = dom.memorySavedLine;
  if (box) box.scrollIntoView({ block: "nearest" });
}

function savedFactsNode() {
  const box = el("div", "memory-saved-facts");
  box.append(el("h3", "memory-saved-title", REMEMBERED_TITLE));
  const v = savedFacts.view;
  if (!v) {
    box.append(el("p", `empty${savedFacts.error ? " failed" : ""}`, savedFacts.error
      ? `Could not read these facts: ${savedFacts.error}` : "Reading…"));
  } else if (!v.available) {
    box.append(el("p", "empty", v.why));
  } else if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount || savedFacts.ids.length, "facts"));
  } else {
    const list = el("div", "rows saved-fact-rows");
    const past = memoryAsOf !== null;
    for (const f of v.facts) {
      const acts = rowActions(f);
      const marks = [];
      if (f.pinned) marks.push(PINNED_MARK);
      if (!f.current && !f.erasedAt) marks.push(NOT_CURRENT_MARK);
      const item = row({
        tag: "auto",
        state: f.current ? "ok" : "idle",
        title: f.erasedAt ? erasedLine(f.erasedAt)
          : f.leftOut ? Topics.WORDS.used_left_out : (f.text || "(no text)"),
        meta: marks,
        actions: past ? [] : [
          ...(acts.forget ? [button("Forget", () => forgetSaved(f),
            { danger: true, live: true, title: "Stop this being recalled. There is no undo." })] : []),
          ...(acts.erase ? [button(ERASE_LABEL, () => eraseSaved(f),
            { danger: true, live: true, title: ERASE_TITLE })] : []),
        ],
      });
      item.dataset.id = String(f.id);
      list.append(item);
    }
    box.append(list);
    const gone = missingLine(v.missing.length);
    if (gone) box.append(el("p", "empty", gone));
  }
  const foot = el("div", "row-actions");
  foot.append(
    button(SHOW_ALL, showSavedList, { title: "The whole list, newest first." }),
    button("Close", () => { savedFacts.open = false; paintSavedLine(); }),
  );
  box.append(foot);
  return box;
}

async function forgetSaved(f) {
  await forgetAuto(f);
  await loadSavedFacts();
}

async function eraseSaved(f) {
  await eraseFact(f);
  await loadSavedFacts();
}

/** The ON card left the queue: read the switch again after the backend has
 *  had a moment to apply an approval. Still off: it was denied or ran out
 *  of time, and that is said - the learning switch's handler. */
onQueue((queue) => {
  let changed = false;
  for (const which of Object.keys(AUTO_SWITCHES)) {
    const waitingNow = autoCardWaiting(which, queue);
    if (waitingNow !== autoL.seen[which]) {
      autoL.seen[which] = waitingNow;
      changed = true;
    }
    const ask = autoL.ask[which];
    if (!ask || !ask.cardId || ask.gone) continue;
    const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
    if (items.some((item) => item && item.id === ask.cardId)) continue;
    ask.gone = true;
    setTimeout(async () => {
      if (autoL.ask[which] !== ask) return;
      autoL.at = 0;
      await loadAuto();
      if (autoL.ask[which] === ask) {
        autoL.ask[which] = null;
        const v = autoL.view;
        // Still off: how the card ended, as the PC says it (`*_last`) -
        // never a guess that it was denied (FIXLIST 2, 28).
        if (!(v && v[AUTO_SWITCHES[which].field])) {
          toast((v && lastLineNow(which, v)) || stillOffLine(which), "bad");
        }
        if (state.view === "memory") paintAuto();
      }
    }, MODEL_ASK_GRACE_MS);
  }
  // A withdrawn card that has left the queue is forgotten.
  const ids = new Set(((queue && Array.isArray(queue.items)) ? queue.items : [])
    .map((item) => item && item.id));
  for (const gone of Object.values(autoL.withdrawn)) {
    for (const id of gone) if (!ids.has(id)) gone.delete(id);
  }
  // A card came or went: the line follows the queue at once, and the PC's
  // own `*_waiting` is read again so it does not hold the line up.
  if (changed && state.view === "memory") {
    paintAutoSettings();
    autoL.at = 0;
    loadAuto();
  }
});

// Private answers turned on or off, or a Show ran out: read the list again -
// Rust decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadAuto = () => {
    autoL.at = 0;
    if (state.view === "memory") loadAuto();
    // The facts "Jarvis remembered N things" opened are a memory list too.
    loadSavedFacts();
  };
  TAURI.event.listen("security-changed", rereadAuto);
  TAURI.event.listen("private-hidden", rereadAuto);
}

// The Brain window is destroyed when it is closed, and a `memory_saved`
// that came while it was closed never reached it. Rust counts them for it
// (brain/auto_learn.rs note_saved), ids only: picked up here when the
// window opens, and cleared when the owner opens the list.
if (IS_TAURI) {
  invoke("brain_memory_saved_unseen", { seen: false }).then((out) => {
    const before = autoL.unseen.size;
    for (const id of savedIds(out)) autoL.unseen.add(id);
    if (autoL.unseen.size !== before) paintSavedLine();
  }).catch(() => {});
}

function autoSwitchNode(which, v) {
  const sw = AUTO_SWITCHES[which];
  const on = v[sw.field] === true;
  // Our own click, or a card raised elsewhere (the phone): the queue says,
  // and so does the PC (`auto_waiting` / `sensitive_waiting`).
  const waiting = !on && Boolean(autoL.ask[which] || v[sw.waitingField] || autoCardWaiting(which));
  const box = el("div", "auto-switch-box");
  const label = el("label", "history-switch auto-switch");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = `memory-${which}-on`;
  input.setAttribute("role", "switch");
  input.setAttribute("aria-describedby", `memory-${which}-detail`);
  input.checked = on;
  label.append(input, el("span", "history-switch-label", sw.label));
  const detail = el("p", "note history-switch-detail", sw.detail);
  detail.id = `memory-${which}-detail`;
  box.append(label, detail);
  if (waiting) {
    // Greyed while its card waits (FIXLIST 8): pressing it again would only
    // ask for the same card. Turning it back OFF is the Cancel button in
    // the waiting line, which withdraws the card (R6).
    input.disabled = true;
    input.title = "A card to turn this on is waiting for your approval.";
  } else if (!on) {
    // Turning it ON waits for a live link (rule 4); OFF never does.
    input.dataset.title = "Asks you first, with an approval card.";
    liveButtons.add(input);
    syncLiveButton(input);
  }
  input.addEventListener("change", async () => {
    const want = input.checked;
    // Show what the PC says, never what was clicked: ON is only a card.
    input.checked = on;
    input.disabled = true;
    input.dataset.busy = "true";
    await setAutoSwitch(which, want);
  });
  // The settings file was damaged, so the PC treats this as off and says
  // why (FIXLIST 1).
  if (which === "auto" && v.fileWhy) {
    box.append(el("p", "history-why-not auto-file-why", v.fileWhy));
  }
  // The sensitive switch does nothing without the first (FIXLIST 3).
  if (which === "sensitive" && !v.auto) {
    box.append(el("p", "hint auto-needs-auto", SENSITIVE_NEEDS_AUTO));
  }
  if (waiting) {
    const line = el("p", "hint learning-waiting history-waiting auto-waiting", sw.waiting(APPROVE_WHERE));
    // OFF, so never held on a stale link.
    line.append(" ", button(CANCEL_LABEL, () => setAutoSwitch(which, false), { title: CANCEL_TITLE }));
    box.append(line);
  } else {
    // How the newest card ended, in the PC's words (FIXLIST 2).
    const words = lastLineNow(which, v);
    if (words) {
      const line = el("p", "hint auto-last", words);
      const last = v[sw.lastField];
      if (last && last.why) line.title = last.why;
      box.append(line);
    }
  }
  return box;
}

function paintAutoSettings() {
  const box = dom.memoryAuto;
  if (!box) return;
  box.replaceChildren();
  const v = autoL.view;
  if (!v) {
    const line = el("p", "empty", autoL.error
      ? `Could not read automatic learning: ${autoL.error}` : "Reading…");
    if (autoL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadAuto));
    }
    box.append(line);
    return;
  }
  if (!v.switches) {
    box.append(el("p", "empty", v.why));
    return;
  }
  box.append(autoSwitchNode("auto", v), autoSwitchNode("sensitive", v));
  // "Learn automatically" means something only while learning is on. The
  // learning route says; an older PC's answer is the facts list's flag.
  const facts = state.data.memory_facts || {};
  const learning = v.learning ?? (typeof facts.learning === "boolean" ? facts.learning : null);
  if (learning === false && v.auto) {
    box.append(el("p", "history-why-not auto-learning-off", LEARNING_OFF_NOTE));
  }
}

function paintSavedLine() {
  const box = dom.memorySavedLine;
  if (!box) return;
  box.replaceChildren();
  const words = rememberedLine(autoL.unseen.size);
  if (words) {
    const b = el("button", "btn small ghost memory-saved", words);
    b.type = "button";
    b.title = REMEMBERED_LINE_TITLE;
    b.addEventListener("click", openSavedList);
    box.append(b);
  }
  // The facts the line opened, with Forget beside each.
  if (savedFacts.open) box.append(savedFactsNode());
}

function paintAutoList() {
  const box = dom.memoryAutoList;
  if (!box) return;
  box.tabIndex = -1;
  box.replaceChildren();
  const v = autoL.view;
  if (!v) {
    box.append(el("p", "empty", autoL.error
      ? "Nothing to show until automatic learning can be read." : "Reading…"));
    return;
  }
  if (!v.available) {
    // The switches' box already says why when nothing is there at all.
    if (v.switches) box.append(el("p", "empty", AUTO_MISSING));
    return;
  }
  if (autoL.listError) {
    const line = el("p", "empty failed", `Could not read what was saved automatically: ${autoL.listError}`);
    line.append(" ", button("Retry", loadAuto));
    box.append(line);
    return;
  }
  if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
    return;
  }
  if (!autoL.rows.length) {
    box.append(el("p", "empty", v.auto ? AUTO_EMPTY : `${AUTO_EMPTY} ${AUTO_OFF}`));
    return;
  }
  const past = memoryAsOf !== null;
  const list = el("div", "rows auto-rows");
  for (const f of autoL.rows) {
    const item = row({
      tag: "auto",
      state: "ok",
      title: f.text || "(no text)",
      meta: [factMeta(f), topicMark(f)],
      // Nothing is changed while the pane shows a past moment (memoryWrite).
      actions: past ? [] : [
        ...[pinButton(f)].filter(Boolean),
        ...[shareButton(f)].filter(Boolean),
        button("Forget", () => forgetAuto(f),
          { danger: true, live: true, title: "Stop this being recalled. There is no undo." }),
        button(ERASE_LABEL, () => eraseFact(f),
          { danger: true, live: true, title: ERASE_TITLE }),
      ],
    });
    item.dataset.id = String(f.id);
    if (!past) withLinks(item, f);
    if (f.provenance === "voice") {
      const marks = el("span", "history-marks");
      const mic = el("span", "history-mark history-mark-voice", VOICE_MARK);
      mic.title = VOICE_TITLE;
      marks.append(mic);
      const main = item.querySelector(".row-main");
      (main || item).append(marks);
    }
    list.append(item);
  }
  box.append(list);
  if (autoL.more) {
    const more = el("div", "row-actions history-more");
    more.append(button(autoL.older ? "Loading…" : "Load older", loadOlderAuto,
      { title: "Show the next page of older facts saved automatically." }));
    box.append(more);
  }
}

function paintAuto() {
  paintAutoSettings();
  paintSavedLine();
  paintAutoList();
}

function renderAuto() {
  paintAuto();
  if (IS_TAURI && !autoL.loading && Date.now() - autoL.at > AUTO_READ_MS) loadAuto();
}

/* ==========================================================================
   "Always keep in mind" (the owner's decision, 2026-09-24; memory-profile.js)

   A short list of facts the owner pins, which Jarvis reads with every
   question, word for word. Its own section, with how many of the list's
   1,200 characters are used and an Unpin on each; a Pin / Unpin on every
   fact still in use in "Saved automatically" and "What Jarvis knows about
   you". One fact per call (brain_memory_pin), no card - the owner's own
   tap, like Forget - held on a stale link in Rust and greyed here. No
   event: the list is read again after every memory write, and when the
   Memory tab is shown.
   ========================================================================== */

const profileL = {
  /** readProfile() of the last read, or null before the first. */
  view: null,
  error: "",
  loading: false,
  again: false,
  at: 0,
};
const PROFILE_READ_MS = 15000;

async function loadProfile() {
  if (!IS_TAURI) return;
  if (profileL.loading) {
    profileL.again = true;
    return;
  }
  profileL.loading = true;
  try {
    profileL.view = readProfile(await invoke("brain_memory_profile"));
    profileL.error = "";
  } catch (error) {
    profileL.error = errorText(error);
  } finally {
    profileL.loading = false;
    profileL.at = Date.now();
  }
  if (profileL.again) {
    profileL.again = false;
    await loadProfile();
    return;
  }
  if (state.view === "memory") {
    // The Pin / Unpin on the fact lists follow the list.
    paintProfile();
    paintAutoList();
    renderFacts();
  }
}

/** Pin or Unpin for one fact, by what the PC last said - or nothing while
 *  that is not known (not read yet, an older PC, or the list hidden). */
function pinButton(f) {
  const v = profileL.view;
  if (!v || !v.available || v.hidden || !Number.isInteger(Number(f.id))) return null;
  const on = isPinned(v, f.id);
  return button(on ? UNPIN_LABEL : PIN_LABEL, () => setPinned(f, !on),
    { live: true, title: on ? UNPIN_TITLE : PIN_TITLE });
}

/** One fact on or off the list. memoryWrite shows the PC's refusal in its
 *  own words ("That would make the list too long - unpin something first")
 *  and reads the pane again, this list included. */
async function setPinned(f, on) {
  return memoryWrite("brain_memory_pin", { id: Number(f.id), pinned: on },
    on ? PINNED : UNPINNED);
}

function paintProfile() {
  const box = dom.memoryProfile;
  if (!box) return;
  box.replaceChildren();
  const v = profileL.view;
  if (!v) {
    const line = el("p", "empty", profileL.error
      ? `Could not read the list: ${profileL.error}` : "Reading…");
    if (profileL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadProfile));
    }
    box.append(line);
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", v.why || PROFILE_MISSING));
    return;
  }
  if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
    return;
  }
  box.append(el("p", "hint profile-used", usedLine(v.chars, v.limit)));
  if (profileL.error) {
    box.append(el("p", "empty failed", `Could not read it again: ${profileL.error}`));
  }
  if (!v.facts.length) {
    box.append(el("p", "empty", PROFILE_EMPTY));
    return;
  }
  // Nothing is changed while the pane shows a past moment (memoryWrite).
  const past = memoryAsOf !== null;
  const list = el("div", "rows profile-rows");
  for (const f of v.facts) {
    const item = row({
      tag: "pinned",
      state: "ok",
      title: f.text || "(no text)",
      meta: [
        f.added ? `pinned ${ago(f.added)}` : "",
        // Topic controls: a pin in a topic that may not be used is not read.
        f.paused ? pinPausedFor(f) : "",
      ],
      actions: past ? [] : [
        button(UNPIN_LABEL, () => setPinned(f, false), { live: true, title: UNPIN_TITLE }),
      ],
    });
    item.dataset.id = String(f.id);
    list.append(item);
  }
  box.append(list);
}

function renderProfile() {
  paintProfile();
  if (IS_TAURI && !profileL.loading && Date.now() - profileL.at > PROFILE_READ_MS) loadProfile();
}

// Private answers turned on or off, or a Show ran out: read it again - Rust
// decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadProfile = () => {
    profileL.at = 0;
    if (state.view === "memory") loadProfile();
  };
  TAURI.event.listen("security-changed", rereadProfile);
  TAURI.event.listen("private-hidden", rereadProfile);
}

/* ==========================================================================
   "Between us" (the owner's decision, 2026-09-27; memory-shared.js)

   Facts the owner tagged as a shared joke or nickname - a label on an
   ordinary fact, meta.kind = "shared" - which Jarvis may bring up when it
   fits, in Warm manner only (never Plain). Its own section, with a "Between
   us" toggle on every fact still in use in "Saved automatically" and "What
   Jarvis knows about you". One fact per call (brain_memory_share), no card
   - the owner's own tap, like Pin - held on a stale link in Rust and greyed
   here. No event: the list is read again after every memory write, and
   when the Memory tab is shown.
   ========================================================================== */

const sharedL = {
  /** readShared() of the last read, or null before the first. */
  view: null,
  error: "",
  loading: false,
  again: false,
  at: 0,
};
const SHARED_READ_MS = 15000;

async function loadShared() {
  if (!IS_TAURI) return;
  if (sharedL.loading) {
    sharedL.again = true;
    return;
  }
  sharedL.loading = true;
  try {
    sharedL.view = readShared(await invoke("brain_memory_shared"));
    sharedL.error = "";
  } catch (error) {
    sharedL.error = errorText(error);
  } finally {
    sharedL.loading = false;
    sharedL.at = Date.now();
  }
  if (sharedL.again) {
    sharedL.again = false;
    await loadShared();
    return;
  }
  if (state.view === "memory") {
    // The "Between us" toggle on the fact lists follows the list.
    paintShared();
    paintAutoList();
    renderFacts();
  }
}

/** "Between us" / "Not between us" for one fact, by what the PC last said -
 *  or nothing while that is not known (not read yet, an older PC, or the
 *  list hidden). */
function shareButton(f) {
  const v = sharedL.view;
  if (!v || !v.available || v.hidden || !Number.isInteger(Number(f.id))) return null;
  const on = isShared(v, f.id);
  return button(on ? UNSHARE_LABEL : SHARE_LABEL, () => setShared(f, !on),
    { live: true, title: on ? UNSHARE_TITLE : SHARE_TITLE });
}

/** One fact on or off "Between us". memoryWrite shows the PC's refusal in
 *  its own words and reads the pane again, this list included. */
async function setShared(f, on) {
  return memoryWrite("brain_memory_share", { id: Number(f.id), shared: on },
    on ? SHARED : UNSHARED);
}

function paintShared() {
  const box = dom.memoryShared;
  if (!box) return;
  box.replaceChildren();
  const v = sharedL.view;
  if (!v) {
    const line = el("p", "empty", sharedL.error
      ? `Could not read the list: ${sharedL.error}` : "Reading…");
    if (sharedL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadShared));
    }
    box.append(line);
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", v.why || SHARED_MISSING));
    return;
  }
  if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
    return;
  }
  if (sharedL.error) {
    box.append(el("p", "empty failed", `Could not read it again: ${sharedL.error}`));
  }
  if (!v.facts.length) {
    box.append(el("p", "empty", SHARED_EMPTY));
    return;
  }
  // Nothing is changed while the pane shows a past moment (memoryWrite).
  const past = memoryAsOf !== null;
  const list = el("div", "rows shared-rows");
  for (const f of v.facts) {
    const item = row({
      tag: "shared",
      state: "ok",
      title: f.text || "(no text)",
      meta: [f.created ? whenTrue(f) : ""],
      actions: past ? [] : [
        button(UNSHARE_LABEL, () => setShared(f, false), { live: true, title: UNSHARE_TITLE }),
        button("Forget", () => forgetAuto(f), { live: true,
          title: "Stop this being recalled. There is no undo." }),
      ],
    });
    item.dataset.id = String(f.id);
    list.append(item);
  }
  box.append(list);
}

function renderShared() {
  paintShared();
  if (IS_TAURI && !sharedL.loading && Date.now() - sharedL.at > SHARED_READ_MS) loadShared();
}

// Private answers turned on or off, or a Show ran out: read it again - Rust
// decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadShared = () => {
    sharedL.at = 0;
    if (state.view === "memory") loadShared();
  };
  TAURI.event.listen("security-changed", rereadShared);
  TAURI.event.listen("private-hidden", rereadShared);
}

/**
 * When a fact became true, in words: "true from 1 January 2021" when that is
 * more than a day away from when Jarvis learned it (the owner's words gave a
 * date, or history was recorded), else "saved 3 h ago" / "saved 12 Sept
 * 2026". This used to be a bare `ago(valid_from)` - "2825d ago" on a fact
 * true since 2019, with nothing saying what the number was (the memory
 * review's I10).
 */
function whenTrue(f) {
  const learned = Number(f.created);
  const from = Number(f.valid_from);
  const has = (v) => Number.isFinite(v) && v > 0;
  if (has(from) && (!has(learned) || Math.abs(learned - from) >= 86400)) {
    const day = plainDateOf(from);
    return day ? `${MEMORY_WORDS.true_from} ${day}` : "";
  }
  const saved = whenWords(has(learned) ? learned : from);
  return saved ? `saved ${saved}` : "";
}

/** "learned 12 September 2026" only when that differs from when the fact
 *  became true.
 *
 * valid_from and created are stamped together for anything typed or accepted
 * in the moment, so saying both every time would be noise on every row. A gap
 * of more than a day means someone recorded history, and that is worth a line.
 */
function whenLearned(f) {
  const learned = Number(f.created);
  const from = Number(f.valid_from);
  if (!Number.isFinite(learned) || !Number.isFinite(from)) return "";
  if (Math.abs(learned - from) < 86400) return "";
  const day = plainDateOf(learned);
  return day ? `learned ${day}` : "";
}

/** The same gap at the other end: stopped being true then, found out later.
 *
 * "I moved in January" told in March gives valid_to = January and
 * retired_at = March. Facts retired before the retired_at column existed have
 * it backfilled equal to valid_to, so they correctly say nothing here.
 */
function whenNoticed(f) {
  const until = Number(f.valid_to);
  const noticed = Number(f.retired_at);
  if (!Number.isFinite(until) || !Number.isFinite(noticed)) return "";
  if (Math.abs(noticed - until) < 86400) return "";
  const a = plainDateOf(until);
  const b = plainDateOf(noticed);
  return a && b ? `true until ${a}, noticed ${b}` : "";
}

/** A review card's reason and older-news lines, whichever there are. */
function reasonLines(p) {
  const { reason, older } = cardLines(p);
  return [reason || "", older || ""];
}

/* ==========================================================================
   Work
   ========================================================================== */

/* ==========================================================================
   Focus session (the owner's decision of 2026-09-25; JARVIS-API.md section
   26; focus.js, brain/focus.rs).

   Start one (minutes, and optionally what it is on), then the countdown -
   counted down here once a second from what the PC last said - the PC's own
   line, the drift count, and Pause / Resume, +10 minutes and Stop: ONE
   thing per tap, no card. Start, Resume and +10 minutes are held on a stale
   link (greyed here, refused in Rust); Pause and Stop are not. After a
   session, its report card. The PC never sends what was in front. The
   `focus` event (a state word, or a callout's number) reads it again.
   ========================================================================== */

const fx = { view: null, error: "", loading: false, again: false, at: 0, readAt: 0, timer: null };
const FOCUS_READ_MS = 15000;

async function loadFocus() {
  if (!IS_TAURI) return;
  if (fx.loading) {
    fx.again = true;
    return;
  }
  fx.loading = true;
  try {
    fx.view = readFocus(await invoke("focus_status"));
    fx.error = "";
    fx.readAt = Date.now();
  } catch (error) {
    fx.error = errorText(error);
  } finally {
    fx.loading = false;
    fx.at = Date.now();
  }
  if (fx.again) {
    fx.again = false;
    await loadFocus();
    return;
  }
  if (state.view === "work") paintFocus();
}

async function focusAct(action) {
  try {
    const out = await invoke("focus_act", { action, minutes: null });
    toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadFocus();
}

async function focusStart() {
  const minutes = focusMinutesOf(dom.focusMinutes && dom.focusMinutes.value);
  if (minutes === null) {
    toast(FOCUS_BAD_MINUTES, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("focus_start", { minutes, on: dom.focusOn ? dom.focusOn.value : "" });
    toast(String((out && out.said) || "Started."), "ok");
    if (dom.focusOn) dom.focusOn.value = "";
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadFocus();
}

function focusTick() {
  if (state.view !== "work" || !fx.view || !fx.view.on || fx.view.paused) return;
  const clockNode = dom.focus && dom.focus.querySelector(".focus-clock");
  if (!clockNode) return;
  const left = focusLeftNow(fx.view, Date.now() - fx.readAt);
  clockNode.textContent = focusClock(left);
  // The PC says when it ended; read again once the count reaches zero.
  if (left <= 0 && !fx.loading && Date.now() - fx.at > 2000) loadFocus();
}

function paintFocus() {
  const box = dom.focus;
  if (!box) return;
  const v = fx.view;
  if (dom.focusReport) dom.focusReport.replaceChildren();
  if (!v) {
    const line = el("p", "empty", fx.error ? `Could not read the focus session: ${fx.error}` : "Reading…");
    if (fx.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadFocus));
    }
    box.replaceChildren(line);
    if (dom.focusForm) dom.focusForm.hidden = true;
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || FOCUS_MISSING));
    if (dom.focusForm) dom.focusForm.hidden = true;
    return;
  }
  if (dom.focusForm) dom.focusForm.hidden = v.on;
  if (!v.on) {
    box.replaceChildren(el("p", "empty", v.line || "No focus session."));
    if (v.report && dom.focusReport) {
      const card = el("div", "focus-report");
      card.append(el("h3", "subhead", FOCUS_LAST_TITLE));
      const title = el("p", "focus-report-title", v.report.title);
      if (v.report.clean) title.dataset.state = "ok";
      card.append(title);
      for (const line of v.report.lines) card.append(el("p", "note", line));
      dom.focusReport.replaceChildren(card);
    }
  } else {
    const wrap = el("div", "focus-now");
    wrap.dataset.tone = focusToneOf(v);
    wrap.append(el("span", "focus-clock mono", focusClock(focusLeftNow(v, Date.now() - fx.readAt))));
    if (v.intent) wrap.append(el("p", "note", `On: ${v.intent}`));
    else if (v.intentHidden) wrap.append(el("p", "note", FOCUS_INTENT_HIDDEN));
    wrap.append(el("p", "focus-line", v.line));
    wrap.append(el("p", "note", driftWords(v.drifts)));
    if (v.note) wrap.append(el("p", "note", v.note));
    const actions = el("div", "row-actions");
    for (const a of focusActionsOf(v, "brain")) {
      actions.append(button(FOCUS_LABELS[a], () => focusAct(a),
        { live: a === "resume" || a === "extend", danger: a === "stop" }));
    }
    wrap.append(actions);
    box.replaceChildren(wrap);
  }
  if (fx.error) box.prepend(el("p", "empty failed", `Could not read it again: ${fx.error}`));
  const ticking = v.on && !v.paused;
  if (ticking && !fx.timer) fx.timer = setInterval(focusTick, 1000);
  if (!ticking && fx.timer) {
    clearInterval(fx.timer);
    fx.timer = null;
  }
}

function renderFocus() {
  paintFocus();
  if (IS_TAURI && !fx.loading && Date.now() - fx.at > FOCUS_READ_MS) loadFocus();
}

if (dom.focusForm) {
  dom.focusForm.addEventListener("submit", (event) => {
    event.preventDefault();
    focusStart();
  });
}
if (dom.focusStart) {
  liveButtons.add(dom.focusStart);
  syncLiveButton(dom.focusStart);
}

/* ==========================================================================
   Talk to a chatbot for me (the owner's decisions of 2026-09-27 and
   2026-09-28; JARVIS-API.md section 87; chatbot.js, brain/chatbot.rs).

   The form (which chatbot, the goal - "these words will be sent" - the
   most messages and minutes within the version's caps, never-send words)
   asks the PC for ONE approval card; nothing is sent before a yes. Then the
   conversation: its state in the PC's words, the counts, Pause / Resume /
   Stop, Change limits (a NEW card), the transcript with the chatbot's words
   in the outside-text style, and at the end the summary - kept on screen,
   never read aloud (nothing in this window speaks). There is no event of
   its own: it is read again every few seconds while a conversation is
   live, and on every activity event. The last conversation's id is kept
   here so its summary stays on screen after it ends.

   "Ask several and compare" (jarvis_chatbot_compare.py): the same form with
   a tick box per chatbot asks the PC for ONE card listing every one. While
   it runs: each chatbot's line, Pause / Resume / Stop for the whole
   comparison, each conversation under its chatbot's name, and at the end
   ONE summary - where they agree and disagree (who said what), the sources
   each gave (not checked by Jarvis), who dropped out and why - kept on
   screen in the outside-text style, never read aloud.
   ========================================================================== */

const cb = { view: null, error: "", loading: false, again: false, at: 0, id: "", gone: false,
  timer: null, filled: false, starting: false, limitsKey: "", logKey: "", limitsInFlight: false,
  cmpId: "", cmpGone: false, lastKind: "", several: new Set(), severalKey: "" };
const CHATBOT_READ_MS = 15000;

/* The last conversation's and comparison's ids outlive this window (the
   chat audit, 2026-09-28, desktop B2: a finished summary vanished when the
   Brain was closed, because the ids lived in the page alone). The ids only -
   never a goal, a message or a summary - in this app's own storage; the PC
   still answers "gone" once it restarts, and the finished conversation is
   then in History. */
const CHATBOT_LAST_KEY = "jarvis.chatbot.last";
try {
  const left = JSON.parse(localStorage.getItem(CHATBOT_LAST_KEY) || "null");
  if (left && typeof left.id === "string") cb.id = left.id;
  if (left && typeof left.cmp === "string") cb.cmpId = left.cmp;
} catch {
  /* no storage: the summary shows while this window is open, as before */
}

function keepChatbotIds() {
  try {
    if (cb.id || cb.cmpId) {
      localStorage.setItem(CHATBOT_LAST_KEY, JSON.stringify({ id: cb.id, cmp: cb.cmpId }));
    } else {
      localStorage.removeItem(CHATBOT_LAST_KEY);
    }
  } catch {
    /* no storage */
  }
}

async function loadChatbot() {
  if (!IS_TAURI) return;
  if (cb.loading) {
    cb.again = true;
    return;
  }
  cb.loading = true;
  try {
    // The latest live conversation first (it may have been started on the
    // phone); else the one this window last showed, for its summary.
    let view = readChatbot(await invoke("chatbot_status", { id: null, compare: null }));
    cb.gone = false;
    cb.cmpGone = false;
    if (view.available && !view.session && cb.id) {
      const named = readChatbot(await invoke("chatbot_status", { id: cb.id, compare: null }));
      if (named.available && named.session) view = { ...view, session: named.session, limits: named.limits };
      else if (named.available) {
        cb.gone = true;
        cb.id = "";
      }
    }
    // The same for a comparison: the latest one still going, else the one
    // this window last showed, for its summary.
    if (view.available && !view.compare && cb.cmpId) {
      const named = readChatbot(await invoke("chatbot_status", { id: null, compare: cb.cmpId }));
      if (named.available && named.compare) view = { ...view, compare: named.compare };
      else if (named.available) {
        cb.cmpGone = true;
        cb.cmpId = "";
      }
    }
    if (view.available && view.session) cb.id = view.session.id;
    if (view.available && view.compare) cb.cmpId = view.compare.id;
    keepChatbotIds();
    if (view.available && view.session && view.session.live) cb.lastKind = "session";
    if (view.available && view.compare && view.compare.live) cb.lastKind = "compare";
    cb.view = view;
    cb.error = "";
  } catch (error) {
    cb.error = errorText(error);
  } finally {
    cb.loading = false;
    cb.at = Date.now();
  }
  if (cb.again) {
    cb.again = false;
    await loadChatbot();
    return;
  }
  if (state.view === "work") paintChatbot();
}

/** The PC's refusals are sometimes lower-case fragments ("nothing is running"). */
function asSentence(text) {
  const t = String(text || "").trim();
  if (!t) return "Not changed.";
  const s = t[0].toUpperCase() + t.slice(1);
  return /[.!?]$/.test(s) ? s : `${s}.`;
}

async function chatbotAct(cmd, args = {}) {
  try {
    const out = await invoke(cmd, args);
    const said = out && (out.message || out.said);
    toast(asSentence(said || "Done."), "ok");
  } catch (error) {
    toast(asSentence(errorText(error)), "bad");
  }
  await loadChatbot();
}

/** "Ask several and compare" is ticked. */
function compareMode() {
  return Boolean(dom.chatbotCompare && dom.chatbotCompare.checked
    && dom.chatbotCompareToggle && !dom.chatbotCompareToggle.hidden);
}

async function chatbotStart() {
  const v = cb.view;
  const several = compareMode();
  const form = {
    chatbot: dom.chatbotWhich ? dom.chatbotWhich.value : "",
    // Ticked, in the order the list shows them (grouped by kind).
    chatbots: v && v.available ? chatbotGroups(v).flatMap((g) => g.chatbots).filter((c) => cb.several.has(c.id)).map((c) => c.id) : [],
    goal: dom.chatbotGoal ? dom.chatbotGoal.value : "",
    messages: dom.chatbotMessages ? dom.chatbotMessages.value : "",
    minutes: dom.chatbotMinutes ? dom.chatbotMinutes.value : "",
  };
  if (cb.starting) return;
  const problem = several ? compareFormProblem(v, form) : chatbotFormProblem(v, form);
  if (problem) {
    toast(problem, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  // One start at a time: a double press must not ask the PC twice.
  cb.starting = true;
  if (dom.chatbotStart) {
    dom.chatbotStart.dataset.busy = "true";
    syncLiveButton(dom.chatbotStart);
  }
  try {
    const limits = {
      goal: form.goal,
      maxMessages: chatbotLimitOf(form.messages, v.tier.turnsMax),
      maxMinutes: chatbotLimitOf(form.minutes, v.tier.minutesMax),
      neverSend: neverWords(dom.chatbotNever ? dom.chatbotNever.value : ""),
    };
    let out;
    if (several) {
      out = await invoke("chatbot_compare_start", { chatbots: form.chatbots, ...limits });
      if (out && out.compare) cb.cmpId = out.compare;
      cb.lastKind = "compare";
    } else {
      out = await invoke("chatbot_start", { chatbot: form.chatbot, ...limits });
      if (out && out.session) cb.id = out.session;
      cb.lastKind = "session";
    }
    toast(asSentence((out && out.message) || CHATBOT.start_note), "ok");
    if (dom.chatbotGoal) dom.chatbotGoal.value = "";
  } catch (error) {
    toast(asSentence(errorText(error)), "bad");
  } finally {
    cb.starting = false;
  }
  await loadChatbot();
  // paintChatbotForm sets busy again only when nothing is built.
  if (dom.chatbotStart && cb.view && cb.view.available) paintChatbotForm(cb.view);
}

function chatbotTurn(t, name) {
  const item = el("div", `chatbot-turn${t.outside ? " chatbot-outside" : ""}`);
  item.dataset.who = t.who;
  const head = el("div", "chatbot-turn-head");
  head.append(el("span", "chatbot-who", t.who === "jarvis" ? `Jarvis, message ${t.n}` : name));
  if (t.outside) head.append(el("span", "history-mark history-mark-taint", "outside text"));
  item.append(head);
  item.append(el("p", "chatbot-text", t.text));
  if (t.cutOff) item.append(el("p", "note chatbot-cut-off", CHATBOT.cut_off));
  return item;
}

/** "Kept in your encrypted chat history" - or why not - and, when kept, a
 *  way to it (the second chat audit, 2026-09-28, desktop C5). Nothing when
 *  the PC did not say. */
function historyNote(h) {
  const line = chatbotHistoryLine(h);
  if (!line) return null;
  const p = el("p", "note chatbot-history-line", line);
  if (h && h.kept) {
    p.append(" ", button(CHATBOT.history_open, () => showView("history"),
      { title: CHATBOT.history_open_title }));
  }
  return p;
}

function chatbotSummary(s) {
  const box = el("div", "chatbot-summary chatbot-outside");
  const head = el("div", "chatbot-turn-head");
  head.append(el("h3", "subhead", CHATBOT.summary_title));
  head.append(el("span", "history-mark history-mark-taint", "outside text"));
  box.append(head);
  box.append(el("p", "note", CHATBOT.summary_note));
  const kept = historyNote(s.history);
  if (kept) box.append(kept);
  if (s.summary.answer) box.append(el("p", "chatbot-text", s.summary.answer));
  if (s.summary.claims.length) {
    const list = el("ul", "chatbot-claims");
    for (const c of s.summary.claims) {
      list.append(el("li", "", `${c.claim} - ${c.sourced ? CHATBOT.claim_sourced : CHATBOT.claim_unsourced}`));
    }
    box.append(list);
  }
  if (s.summary.open.length) {
    box.append(el("p", "note", CHATBOT.open_title));
    const list = el("ul", "chatbot-open");
    for (const o of s.summary.open) list.append(el("li", "", o));
    box.append(list);
  }
  return box;
}

function chatbotLimitsRow(v, s) {
  const wrap = el("div", "");
  const row = el("div", "row");
  const field = (label, value, max, id) => {
    const lab = el("label", "lbl", label);
    const input = el("input", "field");
    input.type = "number";
    input.min = "1";
    input.max = String(max);
    input.value = String(value);
    input.id = id;
    lab.append(input);
    row.append(lab);
    return input;
  };
  const msgs = field(CHATBOT.messages_label, s.max, v.tier.turnsMax, "chatbot-new-messages");
  const mins = field(CHATBOT.minutes_label, s.maxMinutes, v.tier.minutesMax, "chatbot-new-minutes");
  wrap.append(row);
  const neverLab = el("label", "lbl", CHATBOT.never_label);
  const never = el("input", "field");
  never.type = "text";
  never.id = "chatbot-new-never";
  never.value = s.never.join(", ");
  never.disabled = s.hidden;
  neverLab.append(never);
  wrap.append(neverLab);
  const go = button(CHATBOT.change_limits, async () => {
    const m = chatbotLimitOf(msgs.value, v.tier.turnsMax);
    const n = chatbotLimitOf(mins.value, v.tier.minutesMax);
    if (m === null || n === null) {
      toast(`Most messages: 1 to ${v.tier.turnsMax}; most minutes: 1 to ${v.tier.minutesMax}.`, "bad");
      return;
    }
    cb.limitsInFlight = true;
    try {
      await chatbotAct("chatbot_limits", {
        id: s.id, maxMessages: m, maxMinutes: n,
        // While the words are hidden the box shows none: keep the PC's list.
        neverSend: s.hidden ? null : neverWords(never.value),
      });
    } finally {
      cb.limitsInFlight = false;
    }
  }, { live: true });
  go.id = "chatbot-limits-go";
  wrap.append(go);
  wrap.append(el("p", "note", CHATBOT.limits_note));
  wrap.append(el("p", "note chatbot-limits-said"));
  return wrap;
}

/**
 * The limits row: rebuilt only when the conversation, its limits or what may
 * be shown change - never by the 4-second re-read, which would wipe numbers
 * being typed and take the focus away. Its last line is updated each time.
 */
function paintChatbotLimits(v, s) {
  const box = dom.chatbotLimits;
  if (!box) return;
  const show = Boolean(s && (s.state === "running" || s.state === "paused"));
  box.hidden = !show;
  if (!show) {
    box.replaceChildren();
    cb.limitsKey = "";
    return;
  }
  const key = JSON.stringify([s.id, s.max, s.maxMinutes, s.never, s.hidden, v.tier.turnsMax,
    v.tier.minutesMax]);
  if (key !== cb.limitsKey) {
    box.replaceChildren(chatbotLimitsRow(v, s));
    cb.limitsKey = key;
  }
  // Greyed while a card for new limits waits; its own click greys it while
  // the request is on its way (button()), and that is left alone here.
  const go = box.querySelector("#chatbot-limits-go");
  if (go && !cb.limitsInFlight) {
    go.dataset.busy = v.limits.waiting ? "true" : "false";
    syncLiveButton(go);
  }
  const said = box.querySelector(".chatbot-limits-said");
  if (said) {
    said.textContent = v.limits.waiting ? "A card for new limits is waiting for your answer."
      : v.limits.said;
  }
}

/** The summary and the transcript: rebuilt only when they change. */
function paintChatbotLog(s) {
  const box = dom.chatbotLog;
  if (!box) return;
  const shown = s && !s.hidden ? s : null;
  const key = shown ? "s" + JSON.stringify([shown.id, shown.summary, shown.transcript, shown.history]) : "";
  if (key === cb.logKey) return;
  cb.logKey = key;
  const out = [];
  if (shown && shown.summary) out.push(chatbotSummary(shown));
  if (shown && shown.transcript.length) {
    const tr = el("div", "chatbot-transcript");
    tr.append(el("h3", "subhead", CHATBOT.transcript_title));
    tr.append(el("p", "note", CHATBOT.outside_note));
    for (const t of shown.transcript) tr.append(chatbotTurn(t, shown.name));
    out.push(tr);
  }
  box.replaceChildren(...out);
}

/** A list under a small heading, for the comparison's summary. */
function summaryList(box, title, items, cls) {
  if (!items.length) return;
  box.append(el("p", "note", title));
  const list = el("ul", cls);
  for (const item of items) list.append(typeof item === "string" ? el("li", "", item) : item);
  box.append(list);
}

function compareSummary(c) {
  const sm = c.summary;
  const box = el("div", "chatbot-summary chatbot-outside chatbot-compare-summary");
  const head = el("div", "chatbot-turn-head");
  head.append(el("h3", "subhead", CHATBOT.compare_summary_title));
  head.append(el("span", "history-mark history-mark-taint", "outside text"));
  box.append(head);
  box.append(el("p", "note", CHATBOT.compare_summary_note));
  const kept = historyNote(c.history);
  if (kept) box.append(kept);
  if (sm.answer) box.append(el("p", "chatbot-text", sm.answer));
  summaryList(box, CHATBOT.agree_title, sm.agree, "chatbot-agree");
  summaryList(box, CHATBOT.disagree_title, sm.disagree.map((d) => {
    const li = el("li", "", d.point);
    const views = el("ul", "");
    for (const v of d.views) views.append(el("li", "", `${v.who}: ${v.said}`));
    li.append(views);
    return li;
  }), "chatbot-disagree");
  summaryList(box, CHATBOT.sources_title, sm.sources.map((x) => `${x.who}: ${x.items.join("; ")}`),
    "chatbot-sources");
  summaryList(box, CHATBOT.dropped_title, sm.dropped.map((x) => `${x.who} - ${x.why}`),
    "chatbot-dropped");
  summaryList(box, CHATBOT.open_title, sm.open, "chatbot-open");
  return box;
}

/** The comparison's summary and each conversation: rebuilt only when they change. */
function paintCompareLog(c) {
  const box = dom.chatbotLog;
  if (!box) return;
  const shown = c && !c.hidden ? c : null;
  const key = shown ? "c" + JSON.stringify([shown.id, shown.summary, shown.history,
    shown.members.map((m) => m.transcript)]) : "";
  if (key === cb.logKey) return;
  cb.logKey = key;
  const out = [];
  if (shown && shown.summary) out.push(compareSummary(shown));
  const talked = shown ? shown.members.filter((m) => m.transcript.length) : [];
  if (talked.length) {
    const tr = el("div", "chatbot-transcript");
    tr.append(el("h3", "subhead", CHATBOT.conversations_title));
    tr.append(el("p", "note", CHATBOT.outside_note));
    for (const m of talked) {
      const part = el("div", "chatbot-member-log");
      part.dataset.chatbot = m.chatbot;
      part.append(el("h4", "subhead", m.name));
      for (const t of m.transcript) part.append(chatbotTurn(t, m.name));
      tr.append(part);
    }
    out.push(tr);
  }
  box.replaceChildren(...out);
}

function hiddenBlock(title, words = CHATBOT.hidden) {
  const hid = el("div", "private-hidden");
  hid.append(el("p", "empty", words));
  hid.append(button("Show", revealPrivate, { title }));
  return hid;
}

function compareNow(c) {
  const now = el("div", "chatbot-now chatbot-compare-now");
  now.dataset.state = c.state;
  now.append(el("p", "chatbot-head", c.live ? compareTalkingLine(c)
    : `${CHATBOT.compare_title}: ${compareStatusLine(c)}`));
  if (c.live) now.append(el("p", "chatbot-line", compareStatusLine(c)));
  if (c.state !== "refused") now.append(el("p", "note", compareProgress(c)));
  if (c.tierName) now.append(el("p", "note", `${CHATBOT.version}: ${c.tierName}`));
  if (c.hidden) {
    now.append(hiddenBlock("Asks Windows Hello - your PIN, fingerprint or face - then shows the comparison."));
  } else if (c.goal) {
    now.append(el("p", "note", `Your goal (sent word for word to each): ${c.goal}`));
  }
  if (c.members.length) {
    const list = el("ul", "chatbot-members");
    for (const m of c.members) {
      const li = el("li", "", chatbotMemberLine(m, c));
      li.dataset.state = m.state;
      // An API conversation's counts, per chatbot.
      if (m.usage) li.append(el("p", "note chatbot-usage", chatbotUsageLine(m.usage)));
      list.append(li);
    }
    now.append(list);
  }
  for (const m of c.hidden ? [] : c.members) {
    if (!m.question) continue;
    const q = el("div", "chatbot-question chatbot-outside");
    q.append(el("p", "subhead", `${CHATBOT.question_title}: ${m.name}`));
    q.append(el("p", "chatbot-text", m.question));
    q.append(el("p", "note", CHATBOT.question_note));
    now.append(q);
  }
  const actions = el("div", "row-actions");
  for (const a of chatbotActionsOf(c)) {
    if (a === "pause") actions.append(button(CHATBOT.pause, () => chatbotAct("chatbot_pause")));
    if (a === "resume") actions.append(button(CHATBOT.resume, () => chatbotAct("chatbot_resume"), { live: true }));
    if (a === "stop") actions.append(button(CHATBOT.stop, () => chatbotAct("chatbot_compare_stop", { id: c.id }), { danger: true }));
  }
  if (actions.childElementCount) now.append(actions);
  return now;
}

function paintChatbot() {
  const box = dom.chatbot;
  if (!box) return;
  const v = cb.view;
  if (dom.chatbotVersion) dom.chatbotVersion.textContent = v ? chatbotVersionLine(v) : "";
  if (!v) {
    const line = el("p", "empty", cb.error ? `Could not read it: ${cb.error}` : "Reading…");
    if (cb.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadChatbot));
    }
    box.replaceChildren(line);
    if (dom.chatbotForm) dom.chatbotForm.hidden = true;
    paintChatbotLimits(null, null);
    paintChatbotLog(null);
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || CHATBOT.missing));
    if (dom.chatbotForm) dom.chatbotForm.hidden = true;
    paintChatbotLimits(null, null);
    paintChatbotLog(null);
    return;
  }
  const c = v.compare;
  // A comparison going is shown; else the one this window started last.
  const showCompare = Boolean(c && (c.live || (!(v.session && v.session.live)
    && (cb.lastKind === "compare" || !v.session))));
  const s = showCompare ? null : v.session;
  const out = [];
  if (cb.error) out.push(el("p", "empty failed", `Could not read it again: ${cb.error}`));
  if (!v.anyBuilt) out.push(el("p", "note chatbot-none", CHATBOT.none_built));
  if (cb.gone && !showCompare) out.push(el("p", "note", CHATBOT.gone));
  if (cb.cmpGone && !s) out.push(el("p", "note", CHATBOT.compare_gone));
  if (showCompare) {
    out.push(compareNow(c));
  } else if (s) {
    const now = el("div", "chatbot-now");
    now.dataset.state = s.state;
    now.append(el("p", "chatbot-head", s.live ? chatbotTalkingLine(s) : `${s.name}: ${chatbotStatusLine(s)}`));
    if (s.live) now.append(el("p", "chatbot-line", chatbotStatusLine(s)));
    // "Solve it here" (handoff.js): paused at a captcha, a sign-in page or
    // an "unusual activity" page - the window is right here on the PC.
    const waitsForYou = s.state === "paused" ? handoffPcLine(v.handoff, "chatbot", s.id) : null;
    if (waitsForYou) now.append(handoffAlert(waitsForYou));
    if (s.state !== "refused") now.append(el("p", "note", chatbotProgress(s)));
    if (s.usage) now.append(el("p", "note chatbot-usage", chatbotUsageLine(s.usage)));
    if (s.tierName) now.append(el("p", "note", `${CHATBOT.version}: ${s.tierName}`));
    if (s.hidden) {
      now.append(hiddenBlock("Asks Windows Hello - your PIN, fingerprint or face - then shows the conversation."));
    } else if (s.goal) {
      now.append(el("p", "note", `Your goal (sent word for word): ${s.goal}`));
    }
    if (s.question) {
      const q = el("div", "chatbot-question chatbot-outside");
      q.append(el("p", "subhead", CHATBOT.question_title));
      q.append(el("p", "chatbot-text", s.question));
      q.append(el("p", "note", CHATBOT.question_note));
      now.append(q);
    }
    const actions = el("div", "row-actions");
    for (const a of chatbotActionsOf(s)) {
      if (a === "pause") actions.append(button(CHATBOT.pause, () => chatbotAct("chatbot_pause")));
      if (a === "resume") actions.append(button(CHATBOT.resume, () => chatbotAct("chatbot_resume"), { live: true }));
      if (a === "stop") actions.append(button(CHATBOT.stop, () => chatbotAct("chatbot_stop", { id: s.id }), { danger: true }));
    }
    if (actions.childElementCount) now.append(actions);
    out.push(now);
  } else if (v.anyBuilt) {
    out.push(el("p", "empty", "No conversation yet."));
  }
  // The poll repaints this box every few seconds while a conversation runs;
  // a keyboard user sitting on Pause or Stop was thrown back to the page each
  // time. Note which button had focus and give it back (bug audit 2026-09-29).
  const focusedLabel = box.contains(document.activeElement)
    && document.activeElement.closest(".row-actions")
    ? document.activeElement.textContent : null;
  box.replaceChildren(...out);
  if (focusedLabel) {
    const again = [...box.querySelectorAll(".row-actions button")]
      .find((b) => b.textContent === focusedLabel);
    if (again) again.focus();
  }
  paintChatbotLimits(v, s);
  if (showCompare) paintCompareLog(c);
  else paintChatbotLog(s);
  paintChatbotForm(v);
  const live = Boolean((v.session && v.session.live) || (c && c.live));
  if (live && !cb.timer) {
    cb.timer = setInterval(() => {
      if (state.view === "work" && !cb.loading) loadChatbot();
    }, CHATBOT_POLL_MS);
  }
  if (!live && cb.timer) {
    clearInterval(cb.timer);
    cb.timer = null;
  }
}

/** The tick boxes, one per chatbot: rebuilt only when the list changes. */
function paintChatbotSeveral(v) {
  if (dom.chatbotSeveralLegend) {
    dom.chatbotSeveralLegend.textContent = v.canCompare ? chatbotPickLine(v) : CHATBOT.compare_not_enough;
  }
  const list = dom.chatbotSeveralList;
  if (!list) return;
  const key = JSON.stringify(v.chatbots);
  if (key === cb.severalKey) return;
  cb.severalKey = key;
  for (const id of [...cb.several]) {
    if (!v.chatbots.some((c) => c.id === id && c.built)) cb.several.delete(id);
  }
  // Grouped by how each is reached, like the single chooser; a chatbot
  // that cannot be used yet says why under its name.
  const rows = [];
  for (const g of chatbotGroups(v)) {
    if (g.title) rows.push(el("p", "note chatbot-kind", g.title));
    for (const c of g.chatbots) {
      const lab = el("label", "");
      const box = el("input", "");
      box.type = "checkbox";
      box.value = c.id;
      box.disabled = !c.built;
      box.checked = c.built && cb.several.has(c.id);
      box.addEventListener("change", () => {
        if (box.checked) cb.several.add(c.id);
        else cb.several.delete(c.id);
      });
      lab.append(box, ` ${c.name}`);
      rows.push(lab);
      if (!c.built) rows.push(el("p", "note chatbot-not-ready", c.note || "Not built yet."));
      // An API service: how much of its monthly money limit is left.
      const money = chatbotMoneyLine(c);
      if (money) rows.push(el("p", "note chatbot-money-line", money));
    }
    if (g.kind === "api") rows.push(el("p", "note chatbot-money-note", CHATBOT.money_pc_only));
  }
  list.replaceChildren(...rows);
}

/**
 * Under the single chooser: the chosen API service's money left this month
 * (the PC's own amounts), and that limits and prices are set on the PC.
 * Hidden for a website or the second AI on this PC.
 */
function paintChatbotMoney(v) {
  const box = dom.chatbotMoney;
  if (!box) return;
  const id = dom.chatbotWhich ? dom.chatbotWhich.value : "";
  const bot = v && v.available ? v.chatbots.find((c) => c.id === id) : null;
  const several = compareMode();
  if (!bot || bot.kind !== "api" || several) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.textContent = [chatbotMoneyLine(bot), CHATBOT.money_pc_only].filter(Boolean).join(" ");
  box.hidden = false;
}

function paintChatbotForm(v) {
  const form = dom.chatbotForm;
  if (!form) return;
  form.hidden = Boolean((v.session && v.session.live) || (v.compare && v.compare.live));
  if (form.hidden) return;
  // An older PC has no comparisons: no tick box then.
  if (dom.chatbotCompareToggle) dom.chatbotCompareToggle.hidden = !(v.tier.compareMax > 0);
  const several = compareMode();
  if (dom.chatbotCompareDetail) dom.chatbotCompareDetail.hidden = !several;
  if (dom.chatbotCompareNote) dom.chatbotCompareNote.hidden = !several;
  if (dom.chatbotWhichLabel) dom.chatbotWhichLabel.hidden = several;
  if (dom.chatbotSeveral) dom.chatbotSeveral.hidden = !several;
  if (several) paintChatbotSeveral(v);
  const which = dom.chatbotWhich;
  if (which) {
    const was = which.value;
    // Grouped by how each is reached: websites, with a key, on this PC.
    const option = (c) => {
      const o = el("option", "", c.built ? c.name : `${c.name} - ${c.note || "Not built yet."}`);
      o.value = c.id;
      o.disabled = !c.built;
      return o;
    };
    which.replaceChildren(...chatbotGroups(v).map((g) => {
      if (!g.title) return g.chatbots.map(option);
      const group = el("optgroup", "");
      group.label = g.title;
      group.append(...g.chatbots.map(option));
      return [group];
    }).flat());
    // The first usable one as the list shows it (grouped), not as the PC sent it.
    const shown = chatbotGroups(v).flatMap((g) => g.chatbots);
    const pick = shown.find((c) => c.id === was && c.built) || shown.find((c) => c.built)
      || shown[0];
    if (pick) which.value = pick.id;
  }
  paintChatbotMoney(v);
  if (dom.chatbotMessages) dom.chatbotMessages.max = String(v.tier.turnsMax);
  if (dom.chatbotMinutes) dom.chatbotMinutes.max = String(v.tier.minutesMax);
  if (!cb.filled) {
    if (dom.chatbotMessages) dom.chatbotMessages.value = String(v.tier.turnsDefault);
    if (dom.chatbotMinutes) dom.chatbotMinutes.value = String(v.tier.minutesDefault);
    cb.filled = true;
  }
  if (dom.chatbotStart) {
    // Nothing built: Start stays greyed, with the reason as its title.
    dom.chatbotStart.dataset.title = v.anyBuilt ? "" : CHATBOT.none_built;
    dom.chatbotStart.dataset.busy = v.anyBuilt ? "false" : "true";
    syncLiveButton(dom.chatbotStart);
    if (!v.anyBuilt) dom.chatbotStart.title = CHATBOT.none_built;
  }
}

function renderChatbot() {
  paintChatbot();
  if (IS_TAURI && !cb.loading && Date.now() - cb.at > CHATBOT_READ_MS) loadChatbot();
}

if (dom.chatbotForm) {
  dom.chatbotForm.addEventListener("submit", (event) => {
    event.preventDefault();
    chatbotStart();
  });
}
if (dom.chatbotCompare) {
  dom.chatbotCompare.addEventListener("change", () => {
    if (cb.view && cb.view.available) paintChatbotForm(cb.view);
  });
}
if (dom.chatbotWhich) {
  dom.chatbotWhich.addEventListener("change", () => {
    if (cb.view && cb.view.available) paintChatbotMoney(cb.view);
  });
}
if (dom.chatbotStart) {
  liveButtons.add(dom.chatbotStart);
  syncLiveButton(dom.chatbotStart);
}

/* ==========================================================================
   Chat with customer support for me (the owner's decisions of 2026-09-28;
   JARVIS-API.md section 65; support.js, brain/support.rs).

   The form (the company - Groupon, or another company's help page typed by
   the owner - its terms risk, the goal, the details Jarvis may give as
   name-and-value rows, and the limits) asks the PC for ONE approval card;
   nothing is sent before a yes. Then the chat: its state in the PC's words
   (waiting for the owner to open the chat in the window, the queue, the
   agent's name), Take over / Resume / Stop, a waiting offer with its words
   and the exact reply its card would send (accepting is ONLY that card;
   here: Decline, Say something else, Take over), a question handed to the
   owner, the transcript with the company's words marked outside text, and
   at the end the summary, the reference number, whether it was kept in the
   encrypted history, and "Export transcript" (a file the owner picks). Kept
   on screen, never read aloud (nothing in this window speaks). Read again
   every few seconds while a chat is going, and on every activity event.
   ========================================================================== */

const sp = { view: null, error: "", loading: false, again: false, at: 0, id: "", gone: false,
  timer: null, filled: false, starting: false, logKey: "", rows: [{ name: "", value: "" }],
  rowsKey: "", sayOpen: false, companiesKey: "" };
const SUPPORT_READ_MS = 15000;

async function loadSupport() {
  if (!IS_TAURI) return;
  if (sp.loading) {
    sp.again = true;
    return;
  }
  sp.loading = true;
  try {
    let view = readSupport(await invoke("support_status", { id: null }));
    sp.gone = false;
    // The latest chat still going first (it may have been started on the
    // phone); else the one this window last showed, for its summary.
    if (view.available && !view.chat && sp.id) {
      const named = readSupport(await invoke("support_status", { id: sp.id }));
      if (named.available && named.chat) view = { ...view, chat: named.chat };
      else if (named.available) {
        sp.gone = true;
        sp.id = "";
      }
    }
    if (view.available && view.chat) sp.id = view.chat.id;
    sp.view = view;
    sp.error = "";
  } catch (error) {
    sp.error = errorText(error);
  } finally {
    sp.loading = false;
    sp.at = Date.now();
  }
  if (sp.again) {
    sp.again = false;
    await loadSupport();
    return;
  }
  if (state.view === "work") paintSupport();
}

async function supportAct(cmd, args = {}) {
  try {
    const out = await invoke(cmd, args);
    const said = out && (out.message || out.said);
    if (out && out.cancelled) toast("Not saved.", "ok");
    else if (out && out.saved) toast(`Saved to ${out.saved}. ${SUPPORT.export_note}`, "ok");
    else toast(asSentence(said || "Done."), "ok");
  } catch (error) {
    toast(asSentence(errorText(error)), "bad");
  }
  await loadSupport();
}

async function supportStart() {
  const v = sp.view;
  const form = {
    company: dom.supportCompany ? dom.supportCompany.value : "",
    address: dom.supportAddress ? dom.supportAddress.value : "",
    goal: dom.supportGoal ? dom.supportGoal.value : "",
    rows: sp.rows,
    messages: dom.supportMessages ? dom.supportMessages.value : "",
    minutes: dom.supportMinutes ? dom.supportMinutes.value : "",
    queue: dom.supportQueue ? dom.supportQueue.value : "",
  };
  if (sp.starting) return;
  const problem = supportFormProblem(v, form);
  if (problem) {
    toast(problem, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  sp.starting = true;
  if (dom.supportStart) {
    dom.supportStart.dataset.busy = "true";
    syncLiveButton(dom.supportStart);
  }
  try {
    const typed = v.companies.find((c) => c.id === form.company);
    const out = await invoke("support_start", {
      company: form.company,
      address: typed && typed.typed ? form.address.trim() : null,
      goal: form.goal,
      details: supportDetailRows(form.rows),
      maxMessages: supportLimitOf(form.messages, v.tier.messagesMax),
      maxMinutes: supportLimitOf(form.minutes, v.tier.minutesMax),
      maxQueueMinutes: supportLimitOf(form.queue, v.tier.queueMax),
    });
    if (out && out.support) sp.id = out.support;
    toast(asSentence((out && out.message) || SUPPORT.start_note), "ok");
    if (dom.supportGoal) dom.supportGoal.value = "";
    sp.rows = [{ name: "", value: "" }];
    sp.rowsKey = "";
  } catch (error) {
    toast(asSentence(errorText(error)), "bad");
  } finally {
    sp.starting = false;
    if (dom.supportStart) {
      dom.supportStart.dataset.busy = "false";
      syncLiveButton(dom.supportStart);
    }
  }
  await loadSupport();
}

/** The details rows: rebuilt only when rows are added or removed, so typing is kept. */
function paintSupportRows() {
  const box = dom.supportRows;
  if (!box) return;
  const key = String(sp.rows.length);
  if (key === sp.rowsKey) return;
  sp.rowsKey = key;
  const out = sp.rows.map((r, i) => {
    const line = el("div", "row support-row");
    const name = el("input", "field");
    name.type = "text";
    name.maxLength = 40;
    name.value = r.name;
    name.placeholder = SUPPORT.detail_name;
    name.setAttribute("aria-label", `${SUPPORT.detail_name}, row ${i + 1}`);
    name.addEventListener("input", () => { sp.rows[i].name = name.value; });
    const value = el("input", "field");
    value.type = "text";
    value.maxLength = 200;
    value.spellcheck = false;
    value.value = r.value;
    value.placeholder = SUPPORT.detail_value;
    value.setAttribute("aria-label", `${SUPPORT.detail_value}, row ${i + 1}`);
    value.addEventListener("input", () => { sp.rows[i].value = value.value; });
    const remove = button(SUPPORT.remove_detail, () => {
      sp.rows.splice(i, 1);
      if (!sp.rows.length) sp.rows.push({ name: "", value: "" });
      sp.rowsKey = "";
      paintSupportRows();
    });
    remove.setAttribute("aria-label", `${SUPPORT.remove_detail} row ${i + 1}`);
    line.append(name, value, remove);
    return line;
  });
  box.replaceChildren(...out);
}

function paintSupportForm(v) {
  const form = dom.supportForm;
  if (!form) return;
  form.hidden = Boolean(v.chat && v.chat.live);
  if (form.hidden) return;
  const which = dom.supportCompany;
  if (which) {
    const key = JSON.stringify(v.companies.map((c) => [c.id, c.name]));
    if (key !== sp.companiesKey) {
      const was = which.value;
      which.replaceChildren(...v.companies.map((c) => {
        const o = el("option", "", c.name);
        o.value = c.id;
        return o;
      }));
      which.value = v.companies.some((c) => c.id === was) ? was : (v.companies[0] || {}).id || "";
      sp.companiesKey = key;
    }
  }
  const co = v.companies.find((c) => c.id === (which ? which.value : ""));
  if (dom.supportTerms) {
    dom.supportTerms.textContent = co && co.terms ? `${SUPPORT.terms_title}: ${co.terms}` : "";
  }
  if (dom.supportAddressLabel) dom.supportAddressLabel.hidden = !(co && co.typed);
  if (dom.supportMessages) dom.supportMessages.max = String(v.tier.messagesMax);
  if (dom.supportMinutes) dom.supportMinutes.max = String(v.tier.minutesMax);
  if (dom.supportQueue) dom.supportQueue.max = String(v.tier.queueMax);
  if (!sp.filled) {
    if (dom.supportMessages) dom.supportMessages.value = String(v.tier.messagesDefault);
    if (dom.supportMinutes) dom.supportMinutes.value = String(v.tier.minutesDefault);
    if (dom.supportQueue) dom.supportQueue.value = String(v.tier.queueDefault);
    sp.filled = true;
  }
  paintSupportRows();
}

function supportTurn(t, c) {
  const item = el("div", `chatbot-turn${t.outside ? " chatbot-outside" : ""}`);
  item.dataset.who = t.who;
  const head = el("div", "chatbot-turn-head");
  head.append(el("span", "chatbot-who", supportWhoOf(t, c)));
  if (t.outside) head.append(el("span", "history-mark history-mark-taint", "outside text"));
  item.append(head);
  item.append(el("p", t.who === "note" ? "note" : "chatbot-text", t.text));
  return item;
}

function supportSummaryBox(c) {
  const sm = c.summary;
  const box = el("div", "chatbot-summary chatbot-outside");
  const head = el("div", "chatbot-turn-head");
  head.append(el("h3", "subhead", SUPPORT.summary_title));
  head.append(el("span", "history-mark history-mark-taint", "outside text"));
  box.append(head);
  box.append(el("p", "note", SUPPORT.summary_note));
  if (sm.answer) box.append(el("p", "chatbot-text", sm.answer));
  summaryList(box, SUPPORT.agreed_title, sm.agreed, "support-agreed");
  summaryList(box, SUPPORT.open_title, sm.open, "chatbot-open");
  return box;
}

/** The summary and the transcript: rebuilt only when they change. */
function paintSupportLog(c) {
  const box = dom.supportLog;
  if (!box) return;
  const shown = c && !c.hidden ? c : null;
  const key = shown ? JSON.stringify([shown.id, shown.summary, shown.transcript, shown.reference,
    shown.saved, shown.live]) : "";
  if (key === sp.logKey) return;
  sp.logKey = key;
  const out = [];
  if (shown && shown.summary) out.push(supportSummaryBox(shown));
  if (shown && !shown.live) {
    if (shown.reference) {
      out.push(el("p", "note support-reference",
        SUPPORT.reference_line.replace("{reference}", shown.reference)));
    }
    const saved = supportSavedLine(shown);
    if (saved) {
      const p = el("p", "note support-saved", saved);
      // Kept: a way to it (the second chat audit, 2026-09-28, desktop C5).
      if (shown.saved === "yes") {
        p.append(" ", button(CHATBOT.history_open, () => showView("history"),
          { title: CHATBOT.history_open_title }));
      }
      out.push(p);
    }
  }
  if (shown && shown.transcript.length) {
    const tr = el("div", "chatbot-transcript");
    tr.append(el("h3", "subhead", SUPPORT.transcript_title));
    tr.append(el("p", "note", SUPPORT.outside_note));
    for (const t of shown.transcript) tr.append(supportTurn(t, shown));
    const ex = button(SUPPORT.export, () => supportAct("support_export", { id: shown.id }));
    ex.id = "support-export";
    tr.append(ex, el("p", "note", SUPPORT.export_note));
    out.push(tr);
  }
  box.replaceChildren(...out);
}

/** The waiting offer: its words, the exact reply its card would send, the owner's other choices. */
function supportOfferBox(c) {
  const o = c.offer;
  const box = el("div", "chatbot-question chatbot-outside support-offer");
  box.append(el("p", "subhead", SUPPORT.offer_title));
  box.append(el("p", "chatbot-text", o.words));
  box.append(el("p", "note", `If you approve the card, Jarvis sends: "${o.reply}"`));
  box.append(el("p", "note", SUPPORT.offer_note));
  if (o.card === "no") box.append(el("p", "note support-card-no", SUPPORT.offer_card_no));
  const hold = supportHoldingLine(c);
  if (hold) box.append(el("p", "note", hold));
  if (o.said) box.append(el("p", "note failed", o.said));
  const actions = el("div", "row-actions");
  for (const a of supportOfferActions(c)) {
    if (a === "decline") {
      actions.append(button(SUPPORT.decline, () => supportAct("support_answer", {
        id: c.id, offer: o.id, choice: "decline", text: null }), { live: true }));
    }
    if (a === "say_else") {
      actions.append(button(SUPPORT.say_else, () => {
        sp.sayOpen = !sp.sayOpen;
        paintSupport();
      }));
    }
    if (a === "take_over") {
      actions.append(button(SUPPORT.take_over, () => supportAct("support_answer", {
        id: c.id, offer: o.id, choice: "takeover", text: null })));
    }
  }
  box.append(actions);
  if (sp.sayOpen) {
    const lab = el("label", "lbl", SUPPORT.say_else);
    const input = el("input", "field");
    input.type = "text";
    input.maxLength = 1200;
    input.id = "support-say";
    lab.append(input);
    const send = button(SUPPORT.say_send, async () => {
      await supportAct("support_answer", { id: c.id, offer: o.id, choice: "say",
        text: input.value });
      sp.sayOpen = false;
    }, { live: true });
    send.id = "support-say-send";
    box.append(lab, send, el("p", "note", SUPPORT.say_note));
  }
  return box;
}

/**
 * "Solve it here" on the PC: the same alert the phone gets, pointing at the
 * browser window on this PC (handoff.js). Only a site and a reason - never
 * a picture or a word from the page.
 */
function handoffAlert(line) {
  const box = el("div", "chatbot-handoff");
  box.setAttribute("role", "status");
  box.append(el("p", "subhead", line.title), el("p", "note", line.text));
  return box;
}

function paintSupport() {
  const box = dom.support;
  if (!box) return;
  const v = sp.view;
  if (dom.supportVersion) dom.supportVersion.textContent = v ? supportVersionLine(v) : "";
  if (!v) {
    const line = el("p", "empty", sp.error ? `Could not read it: ${sp.error}` : "Reading…");
    if (sp.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadSupport));
    }
    box.replaceChildren(line);
    if (dom.supportForm) dom.supportForm.hidden = true;
    paintSupportLog(null);
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || SUPPORT.missing));
    if (dom.supportForm) dom.supportForm.hidden = true;
    paintSupportLog(null);
    return;
  }
  const c = v.chat;
  const out = [];
  if (sp.error) out.push(el("p", "empty failed", `Could not read it again: ${sp.error}`));
  if (sp.gone) out.push(el("p", "note", SUPPORT.gone));
  if (c) {
    const now = el("div", "chatbot-now support-now");
    now.dataset.state = c.state;
    now.append(el("p", "chatbot-head", c.live ? supportTalkingLine(c)
      : `${c.companyName}: ${supportStatusLine(c)}`));
    if (c.live) now.append(el("p", "chatbot-line", supportStatusLine(c)));
    const waitsForYou = c.state === "paused" ? handoffPcLine(v.handoff, "support", c.id) : null;
    if (waitsForYou) now.append(handoffAlert(waitsForYou));
    if (c.state !== "refused") now.append(el("p", "note", supportProgress(c)));
    if (c.tierName) now.append(el("p", "note", `${SUPPORT.version}: ${c.tierName}`));
    if (c.hidden) {
      now.append(hiddenBlock("Asks Windows Hello - your PIN, fingerprint or face - then shows the chat.",
        SUPPORT.hidden));
    } else {
      if (c.goal) now.append(el("p", "note", `Your goal: ${c.goal}`));
      if (c.details.length) {
        now.append(el("p", "note support-details-line", "Jarvis may give: "
          + c.details.map((d) => `${d.name}: ${d.value}`).join("; ")));
      }
      if (c.question) {
        const q = el("div", "chatbot-question chatbot-outside");
        q.append(el("p", "subhead", SUPPORT.question_title));
        q.append(el("p", "chatbot-text", c.question));
        q.append(el("p", "note", SUPPORT.question_note));
        now.append(q);
      }
      if (c.offer) now.append(supportOfferBox(c));
    }
    const actions = el("div", "row-actions");
    for (const a of supportActionsOf(c)) {
      if (a === "take_over") {
        const b = button(SUPPORT.take_over, () => supportAct("support_takeover", { id: c.id }));
        b.title = SUPPORT.take_over_note;
        actions.append(b);
      }
      if (a === "resume") actions.append(button(SUPPORT.resume, () => supportAct("chatbot_resume"), { live: true }));
      if (a === "stop") actions.append(button(SUPPORT.stop, () => supportAct("support_stop", { id: c.id }), { danger: true }));
    }
    if (actions.childElementCount) now.append(actions);
    out.push(now);
  } else {
    out.push(el("p", "empty", "No support chat yet."));
  }
  box.replaceChildren(...out);
  paintSupportLog(c);
  paintSupportForm(v);
  const live = Boolean(c && c.live);
  if (!live) sp.sayOpen = false;
  if (live && !sp.timer) {
    sp.timer = setInterval(() => {
      if (state.view === "work" && !sp.loading) loadSupport();
    }, SUPPORT_POLL_MS);
  }
  if (!live && sp.timer) {
    clearInterval(sp.timer);
    sp.timer = null;
  }
}

function renderSupport() {
  paintSupport();
  if (IS_TAURI && !sp.loading && Date.now() - sp.at > SUPPORT_READ_MS) loadSupport();
}

if (dom.supportForm) {
  dom.supportForm.addEventListener("submit", (event) => {
    event.preventDefault();
    supportStart();
  });
}
if (dom.supportCompany) {
  dom.supportCompany.addEventListener("change", () => {
    if (sp.view && sp.view.available) paintSupportForm(sp.view);
  });
}
if (dom.supportAdd) {
  dom.supportAdd.addEventListener("click", () => {
    if (sp.rows.length >= SUPPORT_MAX_DETAILS) {
      toast(`At most ${SUPPORT_MAX_DETAILS} details.`, "bad");
      return;
    }
    sp.rows.push({ name: "", value: "" });
    sp.rowsKey = "";
    paintSupportRows();
  });
}
if (dom.supportStart) {
  liveButtons.add(dom.supportStart);
  syncLiveButton(dom.supportStart);
}

/* ==========================================================================
   Coming up - timers, alarms, reminders and the to-do list (the owner's
   decisions of 2026-09-25; JARVIS-API.md section 21; coming-up.js).

   Read through its own command (brain/schedule.rs), not brain_read: while
   the private lists are hidden Rust takes the words out. Every change is
   ONE job (Pause / Resume / Delete / Done) or one new to-do item, held on a
   stale link, with no card - none of them can make Jarvis do more. There is
   no "delete all". The `schedule` event (ids and the kind only) reads the
   list again; a running timer counts down here once a second from what the
   PC last said.
   ========================================================================== */

const upL = { view: null, error: "", loading: false, again: false, at: 0, readAt: 0 };
const SCHEDULE_READ_MS = 15000;
/** id -> {span, job} for the countdowns the ticker repaints. */
const ticking = new Map();
let tickTimer = null;

async function loadComingUp() {
  if (!IS_TAURI) return;
  if (upL.loading) {
    upL.again = true;
    return;
  }
  upL.loading = true;
  try {
    upL.view = readSchedule(await invoke("brain_schedule"));
    upL.error = "";
    upL.readAt = Date.now();
  } catch (error) {
    upL.error = errorText(error);
  } finally {
    upL.loading = false;
    upL.at = Date.now();
  }
  if (upL.again) {
    upL.again = false;
    await loadComingUp();
    return;
  }
  if (state.view === "work") {
    paintComingUp();
    // A goal's weekly check-in lives on this very list (goals.js's own
    // module doc says why) - repaint it too, so its "waiting"/"paused"/next
    // note stays in step with Coming up rather than needing its own read.
    paintGoals();
  }
}

async function scheduleAct(job, action) {
  try {
    // Snooze says how long (10 minutes), so the PC and this button agree.
    const args = action === "snooze" ? { id: job.id, action, seconds: SNOOZE_SECONDS }
      : { id: job.id, action };
    const out = await invoke("brain_schedule_act", args);
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/**
 * One new item, on the to-do list or (with `list`) a named list - the
 * list's own Add box. Held on a stale link.
 */
async function addTodo(input = dom.todoText, list = null, title = "To-do list") {
  const words = input ? input.value.trim() : "";
  if (!words) return;
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  const where = title.charAt(0).toLowerCase() + title.slice(1);
  try {
    const out = await invoke("brain_schedule_add_todo", list ? { text: words, list } : { text: words });
    if (out && out.ok === false) {
      toast(String(out.error || "Refused."), "bad");
    } else {
      toast(out && out.job && out.job.already ? `That is already on your ${where}.`
        : `Added to your ${where}.`, "ok");
      input.value = "";
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/**
 * "Clear list" under a NAMED list: "are you sure?" first, like Forget, then
 * ONE request naming the list and how many items this page showed - the PC
 * clears nothing if that number is no longer right. Held on a stale link.
 */
async function clearList(l) {
  if (!window.confirm(clearListQuestion(l.title, l.items.length))) return;
  try {
    const out = await invoke("brain_schedule_clear_list", { list: l.name, count: l.items.length });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Cleared."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/** Something that went off in the last hour: its words, when, and Snooze. */
function wentOffRow(job) {
  const item = row({
    tag: tagOf(job),
    state: "warn",
    title: titleOf(job),
    meta: wentOffMeta(job),
    actions: WENT_OFF_ACTIONS.map((a) =>
      button(labelOf(a), () => scheduleAct(job, a), { live: true })),
  });
  item.dataset.id = job.id;
  return item;
}

/**
 * The named lists, each under its own heading: its items (Done / Delete),
 * an Add box, and Clear list. While the private lists are hidden the names
 * and words are gone (Rust took them out) and nothing is offered but Show.
 */
function paintNamedLists(v) {
  const box = dom.namedLists;
  if (!box) return;
  const out = [];
  for (const l of namedLists(v)) {
    const part = el("div", "named-list");
    part.dataset.list = l.name;
    part.append(el("h3", "subhead", l.title));
    const list = el("div", "rows");
    for (const j of l.items) list.append(scheduleRow(j));
    part.append(list);
    if (!v.hidden) {
      const form = el("form", "todo-form");
      form.autocomplete = "off";
      const input = el("input", "field todo-text");
      input.type = "text";
      input.maxLength = 300;
      input.placeholder = addPlaceholder(l.title);
      input.setAttribute("aria-label", addPlaceholder(l.title));
      const add = el("button", "btn small", "Add");
      add.type = "submit";
      liveButtons.add(add);
      syncLiveButton(add);
      form.append(input, add);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        addTodo(input, l.name, l.title);
      });
      part.append(form);
      const actions = el("div", "row");
      actions.append(button(CLEAR_LIST_LABEL, () => clearList(l), { live: true, danger: true }));
      part.append(actions);
    }
    out.push(part);
  }
  box.replaceChildren(...out);
}

/**
 * The standby schedule: two times, set up at once on the PC with no card
 * (since 2026-09-26; the PC's answer says the next night). It then sits in
 * the list above like any repeating job. Held on a stale link, like every
 * change here; Rust refuses it too.
 */
async function addStandby() {
  const times = standbyTimes(dom.standbyStart && dom.standbyStart.value,
    dom.standbyEnd && dom.standbyEnd.value);
  if (!times) {
    toast(STANDBY_BAD_TIMES, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("brain_schedule_add_standby", { start: times.at, end: times.until });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

function scheduleRow(job) {
  const since = Date.now() - upL.readAt;
  const item = row({
    tag: tagOf(job),
    state: job.state === "waiting" ? "warn" : job.state === "paused" ? "" : "ok",
    title: titleOf(job),
    meta: metaOf(job, since),
    actions: actionsOf(job).map((a) =>
      button(labelOf(a), () => scheduleAct(job, a), { live: true, danger: a === "delete" })),
  });
  item.dataset.id = job.id;
  if (job.kind === "timer" && job.state === "active") {
    const span = item.querySelector(".row-meta");
    if (span) {
      span.classList.add("countdown");
      ticking.set(job.id, { span, job });
    }
  }
  return item;
}

function tick() {
  if (state.view !== "work" || !ticking.size) return;
  const since = Date.now() - upL.readAt;
  let finished = false;
  for (const [id, { span, job }] of ticking) {
    if (!span.isConnected) {
      ticking.delete(id);
      continue;
    }
    span.textContent = metaOf(job, since)[0] || "";
    if (job.left !== null && job.left - since / 1000 <= 0) finished = true;
  }
  // The PC says when it went off; read again once the count reaches zero.
  if (finished && !upL.loading && Date.now() - upL.at > 2000) loadComingUp();
}

function paintComingUp() {
  paintToday();
  const box = dom.comingUp;
  if (!box) return;
  ticking.clear();
  const v = upL.view;
  if (!v) {
    const line = el("p", "empty", upL.error ? `Could not read Coming up: ${upL.error}` : "Reading…");
    if (upL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadComingUp));
    }
    box.replaceChildren(line);
    if (dom.todoList) dom.todoList.replaceChildren();
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || SCHEDULE_MISSING));
    if (dom.todoList) dom.todoList.replaceChildren();
    if (dom.namedLists) dom.namedLists.replaceChildren();
    if (dom.wentOffPart) dom.wentOffPart.hidden = true;
    if (dom.listsNote) dom.listsNote.hidden = true;
    if (dom.todoForm) dom.todoForm.hidden = true;
    if (dom.standbyForm) dom.standbyForm.hidden = true;
    if (dom.standbyIsSet) dom.standbyIsSet.hidden = true;
    return;
  }
  if (dom.todoForm) dom.todoForm.hidden = false;
  // One standby schedule at most: the form while there is none, a pointer
  // to its row while there is.
  const hasStandby = Boolean(standbyOf(v));
  if (dom.standbyForm) dom.standbyForm.hidden = hasStandby;
  if (dom.standbyIsSet) dom.standbyIsSet.hidden = !hasStandby;
  rows(box, v.jobs, scheduleRow, EMPTY_JOBS);
  if (upL.error) box.prepend(el("p", "empty failed", `Could not read it again: ${upL.error}`));
  // Just went off (the last hour): Snooze, ONE job per tap.
  if (dom.wentOffPart) dom.wentOffPart.hidden = !v.wentOff.length;
  if (dom.wentOff) rows(dom.wentOff, v.wentOff, wentOffRow, "");
  if (dom.todoList) rows(dom.todoList, todoItems(v), scheduleRow, EMPTY_TODO);
  paintNamedLists(v);
  // Its example says "milk": nothing of that shape shows while hidden.
  if (dom.listsNote) dom.listsNote.hidden = v.hidden;
  if (v.hidden) {
    box.append(hiddenNode(0, "words"));
  }
  if (anyTicking(v) && !tickTimer) tickTimer = setInterval(tick, 1000);
  if (!anyTicking(v) && tickTimer) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}

/* ==========================================================================
   Widgets (widget-board.js; JARVIS-API.md section 86; brain/widgets.rs)

   The owner's words become a PREVIEW on the PC (its AI model makes a small
   description from a fixed menu, never code, and the PC checks it); Add
   keeps it exactly as shown, Discard drops it, Delete removes a widget at
   once. No approval card - the PC's own `no_card` sentence says why. Add
   and Delete are held on a stale link; making a preview is not (it adds
   nothing). Words pasted into the box are sent as pasted, which the PC
   refuses: only the owner's own typed or spoken words make a widget.
   ========================================================================== */

const wid = { view: null, error: "", loading: false, at: 0, making: false, pasted: false };
const WIDGETS_READ_MS = 15000;

async function loadWidgets() {
  if (!IS_TAURI || wid.loading) return;
  wid.loading = true;
  try {
    wid.view = readWidgets(await invoke("brain_widgets"));
    wid.error = "";
  } catch (error) {
    wid.error = errorText(error);
  } finally {
    wid.loading = false;
    wid.at = Date.now();
  }
  if (state.view === "work") paintWidgets();
}

function widgetRow(w, draft) {
  const actions = draft
    ? [button(WIDGETS_DISCARD_LABEL, () => widgetAct("brain_widgets_discard", { draft: w.id })),
      button(WIDGETS_ADD_LABEL, () => widgetAct("brain_widgets_add", { draft: w.id }),
        { live: true })]
    : [button(WIDGETS_DELETE_LABEL, () => widgetAct("brain_widgets_delete", { id: w.id }),
      { live: true, danger: true })];
  const item = row({
    tag: draft ? "preview" : "widget",
    state: draft ? "warn" : "ok",
    title: w.name || (wid.view && wid.view.hidden ? "(hidden) widget" : "Widget"),
    meta: [w.said, ...w.parts],
    actions,
  });
  item.dataset.id = w.id;
  return item;
}

function paintWidgets() {
  const box = dom.widgets;
  if (!box) return;
  const v = wid.view;
  const out = [];
  if (!v) {
    const line = el("p", "empty", wid.error ? `Could not read Widgets: ${wid.error}` : "Reading…");
    if (wid.error) line.append(" ", button("Retry", loadWidgets));
    out.push(line);
  } else if (!v.available) {
    out.push(el("p", "empty", v.why || WIDGETS_MISSING));
  } else {
    if (v.drafts.length) {
      out.push(el("h3", "subhead", WIDGETS_PREVIEW_TITLE));
      const list = el("div", "rows");
      for (const d of v.drafts) list.append(widgetRow(d, true));
      out.push(list);
      if (v.noCard) out.push(el("p", "note", v.noCard));
    }
    const list = el("div", "rows");
    for (const w of v.widgets) list.append(widgetRow(w, false));
    out.push(v.widgets.length ? list : el("p", "empty", WIDGETS_EMPTY));
    if (v.hidden) out.push(hiddenNode(0, "words"));
  }
  if (dom.widgetsForm) dom.widgetsForm.hidden = Boolean(v && !v.available);
  if (dom.widgetsMake) {
    dom.widgetsMake.disabled = wid.making;
    dom.widgetsMake.textContent = wid.making ? WIDGETS_MAKING_LABEL : WIDGETS_MAKE_LABEL;
  }
  box.replaceChildren(...out);
}

async function widgetAct(command, args) {
  if (command !== "brain_widgets_discard" && !linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke(command, args);
    if (out && out.said) toast(String(out.said), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadWidgets();
}

async function makeWidget() {
  if (wid.making) return;
  const args = widgetDraftArgs(dom.widgetsWords && dom.widgetsWords.value, wid.pasted);
  if (args.error) {
    toast(args.error, "bad");
    return;
  }
  wid.making = true;
  paintWidgets();
  try {
    const out = await invoke("brain_widgets_draft", args);
    toast(String((out && out.said) || "Preview made."), "ok");
    if (dom.widgetsWords) dom.widgetsWords.value = "";
    wid.pasted = false;
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    wid.making = false;
  }
  await loadWidgets();
}

if (dom.widgetsForm) {
  dom.widgetsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    makeWidget();
  });
}
if (dom.widgetsWords) {
  // Pasted words are not the owner's own (ARCHITECTURE section 3): said to
  // the PC as pasted, which refuses them. Emptying the box starts again.
  dom.widgetsWords.addEventListener("paste", () => { wid.pasted = true; });
  dom.widgetsWords.addEventListener("input", () => {
    if (!dom.widgetsWords.value) wid.pasted = false;
  });
}

function renderComingUp() {
  paintWidgets();
  if (IS_TAURI && !wid.loading && Date.now() - wid.at > WIDGETS_READ_MS) loadWidgets();
  paintComingUp();
  if (IS_TAURI && !upL.loading && Date.now() - upL.at > SCHEDULE_READ_MS) loadComingUp();
}

/* "Photo to reminder" (photo-reminder.js; JARVIS-API.md section 83): a
   picture file, shrunk here to a screen capture's limits, goes to the PC,
   which reads its words and PROPOSES a reminder. Nothing is set up until
   "Add a Jarvis reminder" (ONE photo_add_reminder, held on a stale link).
   The picture and its words live only in this page's memory, and go when
   the proposal is closed. */
let photoView = null;

async function findDateInFile(file) {
  if (!dom.photoProposal) return;
  if (photoView) photoView.close();
  photoView = null;
  dom.photoProposal.hidden = false;
  dom.photoProposal.textContent = PHOTO_READING;
  dom.photoChoose.disabled = true;
  let out;
  try {
    const image = await shrinkPicture(file, window);
    out = await invoke("photo_scan", { image });
  } catch (error) {
    dom.photoProposal.textContent = errorText(error);
    return;
  } finally {
    dom.photoChoose.disabled = false;
  }
  photoView = mountPhotoProposal(dom.photoProposal, out, {
    invoke,
    canAct: () => linkWords(currentLink()).canAct,
    say: (said) => toast(said, "ok"),
    onDone: () => loadComingUp(),
    onClose: () => { photoView = null; },
  });
}

if (dom.photoNote) dom.photoNote.textContent = PHOTO_NOTE;
if (dom.photoChoose && dom.photoFile) {
  dom.photoChoose.addEventListener("click", () => dom.photoFile.click());
  dom.photoFile.addEventListener("change", () => {
    const file = dom.photoFile.files && dom.photoFile.files[0];
    // Cleared at once, so the same file can be chosen again and no
    // reference to it is left on the input.
    dom.photoFile.value = "";
    if (file) findDateInFile(file);
  });
}

if (dom.todoForm) {
  dom.todoForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addTodo();
  });
}
if (dom.todoAdd) {
  liveButtons.add(dom.todoAdd);
  syncLiveButton(dom.todoAdd);
}
if (dom.standbyForm) {
  dom.standbyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addStandby();
  });
}
if (dom.standbyAdd) {
  liveButtons.add(dom.standbyAdd);
  syncLiveButton(dom.standbyAdd);
}

/* ==========================================================================
   Goals - a plan the owner edits, one card per acting step (the owner's
   "build it now", 2026-09-27; JARVIS-API.md section 59; goals.js).

   Read through its own command (brain/goals.rs), not brain_read - the words
   are taken out while the private lists are hidden, same as Coming up. A new
   draft and marking a step raise no card; Stop tracking is one tap,
   immediate, no confirm. Accepting a draft is the only place this can raise
   a card, and it is the backend's own weekly-check-in card, never one this
   window invents - see goals.js's own module doc for why that check-in's
   live state is read from the very same Coming up list rather than a second
   source of truth.
   ========================================================================== */

const gl = { view: null, error: "", loading: false, again: false, at: 0,
  // The life benchmarks a step can follow (goals.js measureChoices), read
  // from Projects only while a draft is open; `undo` is the last tick.
  measures: [], measuresAt: 0, undo: null };
const GOALS_READ_MS = 20000;

/** goal id -> its working plan while it is still a draft, edited but not yet
 *  sent to Accept. Cleared once accepted (or the goal is gone). */
const draftPlans = new Map();

/** goal id -> the id of the weekly check-in job accept() handed back for
 *  it, so a later read can find that SAME job even if its text ever
 *  changed - a reload of the app still falls back to matching by text
 *  (goals.js checkinJobFor). */
const checkinJobIds = new Map();

async function loadGoals() {
  if (!IS_TAURI) return;
  if (gl.loading) {
    gl.again = true;
    return;
  }
  gl.loading = true;
  try {
    gl.view = readGoals(await invoke("brain_goals"));
    gl.error = "";
  } catch (error) {
    gl.error = errorText(error);
  } finally {
    gl.loading = false;
    gl.at = Date.now();
  }
  if (gl.again) {
    gl.again = false;
    await loadGoals();
    return;
  }
  if (state.view === "work") paintGoals();
}

/** The working copy of a draft's plan - made once, from what the PC sent,
 *  then edited in place so typing does not get wiped by the next read. */
function workingPlan(goal) {
  if (!draftPlans.has(goal.id)) {
    const copy = goal.plan.map((s) => ({ ...s }));
    // While the private lists are hidden the PC sends the steps with their
    // words taken out. Keeping THAT copy meant the blanks stayed after Show
    // and Accept refused an empty plan (bug audit 2026-09-29). Not kept.
    if (goal.hidden) return copy;
    draftPlans.set(goal.id, copy);
  }
  return draftPlans.get(goal.id);
}

async function createGoal() {
  const input = dom.goalsNewText;
  const words = input ? input.value.trim() : "";
  if (!words) return;
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("brain_goals_create", { text: words });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else {
      toast("Added as a draft.", "ok");
      input.value = "";
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadGoals();
}

async function acceptGoal(goal) {
  const limits = gl.view ? gl.view.limits : undefined;
  const plan = workingPlan(goal);
  if (!planIsValid(plan, limits)) {
    toast("Add at least one step, each with some words, none of them too long.", "bad");
    return;
  }
  try {
    const out = await invoke("brain_goals_accept", { id: goal.id, plan: planBody(plan) });
    if (out && out.ok === false) {
      toast(String(out.error || "Refused."), "bad");
    } else {
      toast("Accepted - Jarvis will check in once a week.", "ok");
      draftPlans.delete(goal.id);
      if (out && out.goal && out.goal.checkin && out.goal.checkin.id) {
        checkinJobIds.set(goal.id, out.goal.checkin.id);
      }
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadGoals();
  // The new job is on Coming up's own list, not this read - fetch it too,
  // straight away, so the check-in's state shows without a second visit.
  await loadComingUp();
}

/** The number benchmarks with a target (life and coding), for "Follows a number" (a read of
 *  Projects; nothing is written). Once a minute at most, and only when a
 *  draft is on screen. */
async function loadMeasures() {
  if (!IS_TAURI) return;
  gl.measuresAt = Date.now();
  try {
    const list = await invoke("projects_read", {});
    const answers = await Promise.all(benchProjectIds(list).map((project) =>
      invoke("projects_read", { project }).catch(() => null)));
    gl.measures = measureChoices(list, answers);
  } catch {
    gl.measures = [];
  }
  if (state.view === "work") paintGoals();
}

async function goalStep(goal, step, index, done, undoing = false) {
  try {
    // By the step's id when the PC gave one (it stays put when steps move),
    // else by position, as before.
    const args = step && step.id
      ? { id: goal.id, stepId: step.id, done }
      : { id: goal.id, index, done };
    const out = await invoke("brain_goals_step", args);
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else if (done && !undoing) {
      gl.undo = { goalId: goal.id, stepId: step && step.id ? step.id : "", index,
        name: goal.hidden ? "" : String((step && step.step) || "") };
    } else gl.undo = null;
  } catch (error) {
    // A locked step ticked from a stale screen: the PC answers 409 with its
    // own sentence, which is shown as it is. Nothing changed.
    toast(errorText(error), "bad");
  }
  await loadGoals();
}

async function stopGoal(goal) {
  try {
    const out = await invoke("brain_goals_stop", { id: goal.id });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast("Stopped tracking.", "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  checkinJobIds.delete(goal.id);
  await loadGoals();
  await loadComingUp();
}

function goalStepEditorRow(plan, index) {
  const wrap = el("div", "goal-editor-step");
  const line = el("div", "goal-editor-row");
  const step = el("input", "field goal-step-field");
  step.type = "text";
  step.maxLength = (gl.view && gl.view.limits.text) || 300;
  step.value = plan[index].step;
  step.placeholder = STEP_PLACEHOLDER;
  step.setAttribute("aria-label", STEP_PLACEHOLDER);
  step.addEventListener("input", () => {
    plan[index].step = step.value;
  });
  const by = el("input", "field goal-by-field");
  by.type = "text";
  by.maxLength = (gl.view && gl.view.limits.by) || 40;
  by.value = plan[index].by;
  by.placeholder = BY_PLACEHOLDER;
  by.setAttribute("aria-label", BY_PLACEHOLDER);
  by.addEventListener("input", () => {
    plan[index].by = by.value;
  });
  line.append(step, by, button(REMOVE_STEP_LABEL, () => {
    const name = String(plan[index].step || "").trim();
    const { touched } = removeStepAt(plan, index);
    // The PC does not clean other steps' "Do these first" for the app: it
    // was done above, and the owner is told before anything is saved.
    if (touched) toast(goalFill(NEEDS_CLEANED, { step: name || "the step" }), "ok");
    paintGoals();
  }, { danger: true }));
  wrap.append(line);
  if (gl.view && gl.view.locks) wrap.append(goalLockEditor(plan, index));
  return wrap;
}

/** "Do these first" (up to 3 other steps) and "Follows a number", for one
 *  step of a draft. Plain checkboxes and a list, so a keyboard and a screen
 *  reader reach them; the PC checks circles and the rest when Accept is
 *  pressed and its sentence is shown as sent. */
function goalLockEditor(plan, index) {
  const s = plan[index];
  const max = (gl.view && gl.view.limits.needs) || 3;
  const box = el("div", "goal-lock-editor");
  const group = el("fieldset", "goal-needs");
  group.append(el("legend", "goal-lock-legend", NEEDS_LABEL));
  const choices = needChoices(plan, index);
  if (!choices.length) group.append(el("span", "goal-note", NEEDS_NONE));
  else group.append(el("span", "goal-note", NEEDS_UNDER));
  const boxes = [];
  const sync = () => {
    const full = (s.needs || []).length >= max;
    for (const [cb, id] of boxes) cb.disabled = full && !cb.checked && !(s.needs || []).includes(id);
    note.hidden = !full;
  };
  const note = el("span", "goal-note", goalFill(NEEDS_FULL, { max }));
  for (const c of choices) {
    const label = el("label", "goal-need");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = (s.needs || []).includes(c.id);
    cb.addEventListener("change", () => {
      if (!setNeed(s, c.id, cb.checked, max)) cb.checked = (s.needs || []).includes(c.id);
      sync();
    });
    boxes.push([cb, c.id]);
    label.append(cb, el("span", "", c.label));
    group.append(label);
  }
  group.append(note);
  sync();
  box.append(group);

  const pick = el("label", "goal-measure");
  pick.append(el("span", "goal-lock-legend", MEASURE_LABEL));
  const sel = el("select", "field goal-measure-select");
  const none = el("option", "", MEASURE_NONE);
  none.value = "";
  sel.append(none);
  const key = (m) => `${m.project}:${m.bench}`;
  const current = s.measure ? key(s.measure) : "";
  const known = gl.measures.map((m) => key(m));
  const list = [...gl.measures];
  if (current && !known.includes(current)) {
    // The number is not in the list read just now (still reading, or the
    // Projects tab is hidden): keep the choice, name it as the PC did.
    list.unshift({ project: s.measure.project, bench: s.measure.bench,
      label: s.measureName || FOLLOWS_LABEL.replace(/:\s*$/, "") });
  }
  for (const m of list) {
    const o = el("option", "", m.label);
    o.value = key(m);
    sel.append(o);
  }
  sel.value = current;
  sel.addEventListener("change", () => {
    if (!sel.value) {
      s.measure = null;
      return;
    }
    const [project, bench] = sel.value.split(":");
    s.measure = { project, bench };
    const m = list.find((x) => key(x) === sel.value);
    s.measureName = m ? m.label : s.measureName;
  });
  pick.append(sel);
  box.append(pick);
  box.append(el("p", "goal-note", list.length ? MEASURE_UNDER : MEASURE_EMPTY));
  return box;
}

function draftGoalBlock(goal) {
  const plan = workingPlan(goal);
  const block = el("div", "goal-block");
  const head = el("div", "goal-head");
  head.append(el("span", "goal-title", goal.hidden ? "" : goal.text));
  head.append(el("span", "row-tag", statusLabel(goal.status)));
  block.append(head);
  const steps = el("div", "goal-steps");
  plan.forEach((_, i) => steps.append(goalStepEditorRow(plan, i)));
  block.append(steps);
  const maxSteps = (gl.view && gl.view.limits.steps) || 7;
  const actions = el("div", "goal-actions");
  actions.append(button(ADD_STEP_LABEL, () => {
    if (plan.length >= maxSteps) {
      toast(`A plan can have at most ${maxSteps} steps - keep the big ones and drop the rest.`, "bad");
      return;
    }
    plan.push(newStep(plan, Boolean(gl.view && gl.view.locks)));
    paintGoals();
  }));
  actions.append(button(ACCEPT_LABEL, () => acceptGoal(goal), { live: true }));
  block.append(actions);
  return block;
}

function goalStepRow(goal, step, index) {
  const row = stepRow(step, { hideWords: goal.hidden });
  const line = el("div", "goal-step");
  if (row.locked) line.dataset.state = "locked";
  const label = el("label", "goal-step-label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = step.done;
  const active = goal.status === "active";
  // A locked step's tick is shown but disabled, with the reason beside it
  // (a stale screen that ticks it anyway gets the PC's 409 sentence).
  box.disabled = !active || row.locked;
  if (active && !row.locked) {
    liveButtons.add(box);
    syncLiveButton(box);
  }
  const why = el("p", "goal-note goal-lock-line");
  why.id = `goal-why-${goal.id}-${index}`;
  const lines = [];
  if (row.reachedLine) lines.push(row.reachedLine);
  if (row.lockLine) lines.push(row.lockLine);
  if (row.goneLine) lines.push(row.goneLine);
  if (row.follows) lines.push(row.follows);
  if (row.label && row.label !== step.step) box.setAttribute("aria-label", row.label);
  if (row.locked) box.setAttribute("aria-describedby", why.id);
  box.addEventListener("change", async () => {
    const want = box.checked;
    box.disabled = true;
    await goalStep(goal, step, index, want);
  });
  label.append(box, el("span", "goal-step-text", step.step));
  line.append(label);
  if (row.locked) {
    // A padlock glyph plus the word - the word is what is said and read.
    const tag = el("span", "row-tag goal-locked-tag");
    const glyph = el("span", "", "\u{1F512} ");
    glyph.setAttribute("aria-hidden", "true");
    tag.append(glyph, GOAL_WORDS.locked);
    line.append(tag);
  }
  if (row.reached) line.append(el("span", "row-tag goal-reached-tag", REACHED_TAG));
  if (step.by) line.append(el("span", "goal-step-by", step.by));
  if (lines.length) {
    why.textContent = lines.join(" ");
    line.append(why);
  }
  return line;
}

function activeGoalBlock(goal, jobs) {
  const block = el("div", "goal-block");
  const head = el("div", "goal-head");
  head.append(el("span", "goal-title", goal.hidden ? "" : goal.text));
  const tag = el("span", "row-tag", statusLabel(goal.status));
  if (goal.status === "active") tag.dataset.state = "running";
  head.append(tag);
  block.append(head);
  const steps = el("div", "goal-steps");
  goal.plan.forEach((s, i) => steps.append(goalStepRow(goal, s, i)));
  block.append(steps);
  if (gl.undo && gl.undo.goalId === goal.id) {
    // Undo of the last tick: one tap, no card. Unticking clears only that
    // step; a later step stays done and then reads "(open again)".
    const u = gl.undo;
    const said = u.name ? goalFill(UNDO_TICKED, { step: u.name }) : "Ticked a step.";
    const row = el("p", "goal-note goal-undo");
    row.append(said, " ", button(UNDO_LABEL, async () => {
      const target = goal.plan.find((x) => u.stepId && x.id === u.stepId) || goal.plan[u.index];
      if (!target) {
        gl.undo = null;
        paintGoals();
        return;
      }
      const idx = goal.plan.indexOf(target);
      await goalStep(goal, target, idx, false, true);
      if (!goal.hidden) announce(goalFill(UNTICKED, { step: target.step }), "polite");
    }, { live: true }));
    block.append(row);
  }
  if (goal.status === "active") {
    const job = checkinJobFor(goal, jobs, checkinJobIds.get(goal.id));
    if (job) checkinJobIds.set(goal.id, job.id);
    for (const line of checkinLines(job, WAITING)) block.append(el("p", "goal-note", line));
    block.append(button(STOP_LABEL, () => stopGoal(goal), { live: true, danger: true }));
  }
  return block;
}

function paintGoals() {
  const box = dom.goalsList;
  if (!box) return;
  const v = gl.view;
  if (!v) {
    const line = el("p", "empty", gl.error ? `Could not read Goals: ${gl.error}` : "Reading…");
    if (gl.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadGoals));
    }
    box.replaceChildren(line);
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || GOALS_MISSING));
    if (dom.goalsNewForm) dom.goalsNewForm.hidden = true;
    return;
  }
  const full = openCount(v) >= v.limits.goals;
  if (dom.goalsNewForm) dom.goalsNewForm.hidden = full;
  // "Follows a number" needs Projects' benchmarks, read only while a draft
  // is showing and at most once a minute.
  if (v.locks && v.goals.some((g) => g.status === "draft") && IS_TAURI
    && Date.now() - gl.measuresAt > 60000) loadMeasures();
  if (!v.goals.length) {
    box.replaceChildren(el("p", "empty", EMPTY_GOALS));
  } else {
    const jobs = (upL.view && upL.view.jobs) || [];
    box.replaceChildren(...v.goals.map((g) =>
      (g.status === "draft" ? draftGoalBlock(g) : activeGoalBlock(g, jobs))));
  }
  // The rows above already carry no words while the private lists are
  // hidden (Rust blanked them, same as Coming up) - this only adds the
  // "Show" prompt underneath, exactly as paintComingUp does.
  if (v.hidden) box.append(hiddenNode(0, "words"));
  if (full) {
    box.append(el("p", "empty", `${v.limits.goals} goals are already open - stop tracking one before adding another.`));
  }
}

function renderGoals() {
  paintGoals();
  if (IS_TAURI && !gl.loading && Date.now() - gl.at > GOALS_READ_MS) loadGoals();
}

if (dom.goalsNewForm) {
  dom.goalsNewForm.addEventListener("submit", (event) => {
    event.preventDefault();
    createGoal();
  });
}
if (dom.goalsNewAdd) {
  liveButtons.add(dom.goalsNewAdd);
  syncLiveButton(dom.goalsNewAdd);
}

/* ==========================================================================
   Quiz me on a text (the owner's "go ahead", 2026-09-30; docs/STUDY-FROM-
   TEXT-DESIGN.md section 11; JARVIS-API.md section 98; quiz.js).

   The pasted text, the questions, the answers and the marks live in this
   window's memory and on the PC's - NEVER in localStorage or anywhere else
   this app writes (not even a draft). No card: the text is the owner's own
   and only the PC's local model sees it. Every change is held on a stale
   link. While the private lists are hidden Rust takes the questions, the
   comments and the source passages out (brain/quiz.rs), and this section
   shows the "Show" prompt instead.
   ========================================================================== */

const qz = { quiz: null, summary: null, shown: null, busy: "", error: "", last: null, crisis: "",
  // Spanish practice (JARVIS-API 102.4): the chosen mode, the PC's own Spanish
  // notice once it has been seen, and whether the PC is too old for Spanish.
  mode: "text", notice: "", textOnly: false, refusal: "",
  // What the owner typed for each answered question, in this window's memory
  // only, until the quiz ends - it fills the Keep sheet's backs for a "Got it"
  // mark. Never a crisis answer, never stored anywhere.
  answers: new Map(),
  // The PC's sentence above a captions quiz that covers only the first part
  // ({id, note}); the YouTube block hands it over (youtube.js).
  ytNote: null,
  // The Keep sheet (decks.js keepRows) while it is open, and the count kept.
  keep: null, kept: null,
  // Cloud grading (QC_*, JARVIS-API 113)
  cloudInfo: null, cloudRequest: null, cloudUnknownSince: null, cloudTimer: null,
  cloudGen: 0, cloudSaid: "",
  // The control that should have the keyboard after the next paint, and the
  // last one that had it (trackFkeys).
  focusNext: "", lastFocus: "" };

function quizReset() {
  qz.quiz = null;
  qz.summary = null;
  qz.shown = null;
  qz.busy = "";
  qz.error = "";
  qz.last = null;
  qz.crisis = "";
  qz.answers = new Map();
  qz.keep = null;
  qz.kept = null;
  qz.ytNote = null;
  if (qz.cloudTimer) clearTimeout(qz.cloudTimer);
  qz.cloudTimer = null;
  qz.cloudRequest = null;
  qz.cloudUnknownSince = null;
  qz.cloudSaid = "";
}

/** "Quiz me on a YouTube video" under the paste box (youtube.js, JARVIS-API 112). */
const youtubeBlock = createYoutubeBlock({
  root: document.getElementById("youtube-block"),
  invoke,
  canAct: () => linkWords(currentLink()).canAct,
  staleLine: STALE_TITLE,
  live: { add: (b) => { liveButtons.add(b); syncLiveButton(b); }, sync: (b) => syncLiveButton(b) },
  listen: IS_TAURI && TAURI.event && TAURI.event.listen ? (name, fn) => TAURI.event.listen(name, fn) : null,
  view: () => state.view,
  covered: () => Boolean(qz.quiz || qz.summary),
  spanish: () => qz.mode === "spanish",
  errorText: (error) => errorText(error),
  hiddenNode: () => hiddenNode(0, "words"),
  announce: (words, mode) => announce(words, mode),
  adopt: (quiz, note) => {
    takeQuiz(quiz);
    qz.summary = null;
    qz.shown = null;
    qz.answers = new Map();
    qz.keep = null;
    qz.kept = null;
    qz.error = "";
    qz.crisis = "";
    qz.ytNote = note ? { id: quiz.id, note } : null;
    paintQuiz();
  },
});

/** The keyboard's place (a `data-fkey`) inside `root`, noted just before a repaint.
 *  A button that greys itself while it works drops the keyboard, so the last
 *  place noted by `trackFkeys` counts when nothing has it. */
function fkeyBefore(root, holder) {
  const a = document.activeElement;
  if (a && root && root.contains(a) && a.dataset && a.dataset.fkey) return a.dataset.fkey;
  return holder && (!a || a === document.body) ? holder.lastFocus || "" : "";
}

/** Remembers which `data-fkey` control inside `root` had the keyboard last, until
 *  the keyboard or a click goes somewhere else. */
function trackFkeys(root, holder) {
  if (!root) return;
  root.addEventListener("focusin", (event) => {
    const key = event.target && event.target.dataset && event.target.dataset.fkey;
    if (key) holder.lastFocus = key;
  });
  document.addEventListener("focusin", (event) => {
    if (!root.contains(event.target)) holder.lastFocus = "";
  });
  document.addEventListener("pointerdown", (event) => {
    if (!root.contains(event.target)) holder.lastFocus = "";
  }, true);
}

/** Puts the keyboard back on the control with that `data-fkey` after a repaint. */
function fkeyAfter(root, key) {
  if (!key || !root) return;
  const a = document.activeElement;
  if (a && a !== document.body && a.isConnected) return;
  for (const n of root.querySelectorAll("[data-fkey]")) {
    if (n.dataset.fkey === key && !n.disabled) {
      n.focus({ preventScroll: true });
      return;
    }
  }
}

/** Takes the PC's quiz as the open one, and remembers its Spanish notice. */
function takeQuiz(quiz) {
  qz.quiz = quiz;
  if (quiz.mode === "spanish" && quiz.notice) qz.notice = quiz.notice;
}

/** Puts words to a refusal or a thrown error; a quiz the PC no longer holds
 *  ends the session here. Returns true when it was a problem. */
function quizProblem(out) {
  if (isRefusal(out)) {
    qz.error = quizErrorWords(out);
    qz.refusal = out.error || "";
    if (out.error === "not_found") {
      qz.quiz = null;
      qz.summary = null;
      qz.shown = null;
      qz.keep = null;
    }
    return true;
  }
  return false;
}

async function quizCall(cmd, args, busyWords) {
  if (!linkWords(currentLink()).canAct) {
    qz.error = STALE_TITLE;
    paintQuiz();
    return null;
  }
  qz.busy = busyWords;
  qz.error = "";
  qz.crisis = "";
  paintQuiz();
  try {
    const out = await invoke(cmd, args);
    qz.busy = "";
    if (quizProblem(out)) {
      paintQuiz();
      return null;
    }
    return out;
  } catch (error) {
    qz.busy = "";
    qz.error = errorText(error);
    paintQuiz();
    return null;
  }
}

/** Switches between Text and Spanish practice: the choices, the box's words
 *  and the count line. Nothing is sent. */
function setQuizMode(mode) {
  qz.mode = mode === "spanish" && !qz.textOnly ? "spanish" : "text";
  const spanish = qz.mode === "spanish";
  if (dom.quizMode) {
    for (const r of dom.quizMode.querySelectorAll("input[type=radio]")) {
      r.checked = r.value === qz.mode;
      if (r.value === "spanish") {
        r.disabled = qz.textOnly;
        r.title = qz.textOnly ? QUIZ_OLD_PC_SPANISH : "";
      }
    }
  }
  if (dom.quizSpanish) dom.quizSpanish.hidden = !spanish;
  if (dom.quizText) {
    dom.quizText.placeholder = spanish ? QUIZ_SPANISH_PLACEHOLDER : "Paste the text here";
    dom.quizText.setAttribute("aria-label", spanish ? QUIZ_SPANISH_PLACEHOLDER : "The text to be quizzed on");
  }
  if (dom.quizIntro) dom.quizIntro.textContent = spanish ? QUIZ_SPANISH_INTRO : QUIZ_INTRO_TEXT;
  paintQuizNotice();
  paintQuizCount();
  youtubeBlock.sync();
}

/** The PC's own Spanish notice under the mode chooser, once it has been seen. */
function paintQuizNotice() {
  if (!dom.quizNotice) return;
  const words = qz.mode === "spanish" ? qz.notice : "";
  dom.quizNotice.textContent = words;
  dom.quizNotice.hidden = !words;
}

async function startQuiz() {
  const box = dom.quizText;
  const value = box ? box.value : "";
  const spanish = qz.mode === "spanish";
  let args;
  if (spanish) {
    const made = quizSpanishStartArgs({
      text: value,
      level: dom.quizLevel ? dom.quizLevel.value : "",
      exercise: dom.quizExercise ? dom.quizExercise.value : "",
      topic: dom.quizTopic ? dom.quizTopic.value : "",
    });
    if (made.error) {
      qz.error = made.error;
      paintQuiz();
      return;
    }
    args = made.args;
  } else {
    const c = quizTextCount(value);
    if (!c.ok) {
      qz.error = quizErrorWords({ error: c.n < QUIZ_LIMITS.textMin ? "text_too_short" : "text_too_long" });
      paintQuiz();
      return;
    }
    args = { text: value };
  }
  qz.refusal = "";
  const out = await quizCall("brain_quiz_start", args, spanish ? QUIZ_SPANISH_WRITING : QUIZ_WRITING);
  if (!out) {
    // A PC with Spanish practice never says "too short" to a Spanish start with
    // no text at all (the model writes the sentences): this one is an older PC.
    if (spanish && !args.text && qz.refusal === "text_too_short") {
      qz.textOnly = true;
      qz.error = QUIZ_OLD_PC_SPANISH;
      setQuizMode("text");
      paintQuiz();
    }
    return;
  }
  const quiz = readQuiz(out.quiz);
  if (!quiz) {
    qz.error = "Jarvis answered, but not with a quiz this app can read.";
    paintQuiz();
    return;
  }
  if (!quiz.mode) {
    // No `mode` in the reply: an older PC (JARVIS-API 102.4). Text mode only.
    qz.textOnly = true;
    if (spanish) {
      // It ignored the Spanish choices; let go of the quiz it made.
      try { await invoke("brain_quiz_stop", { id: quiz.id }); } catch { /* it times out on the PC */ }
      qz.error = QUIZ_OLD_PC_SPANISH;
      setQuizMode("text");
      paintQuiz();
      return;
    }
    setQuizMode("text");
  }
  takeQuiz(quiz);
  qz.summary = null;
  qz.shown = null;
  qz.answers = new Map();
  qz.keep = null;
  qz.kept = null;
  // The pasted text is not kept here once the questions exist.
  box.value = "";
  if (dom.quizTopic) dom.quizTopic.value = "";
  paintTopicCount();
  paintQuizCount();
  paintQuizNotice();
  paintQuiz();
}

async function checkAnswer(question, box) {
  const c = quizAnswerCount(box.value);
  if (!c.ok) {
    qz.error = quizErrorWords({ error: c.n < 1 || !box.value.trim() ? "answer_empty" : "answer_too_long" });
    paintQuiz();
    return;
  }
  const value = box.value;
  const out = await quizCall("brain_quiz_answer", { id: qz.quiz.id, n: question.n, answer: value }, QUIZ_CHECKING);
  if (!out) return;
  if (quizIsCrisis(out)) {
    // A crisis answer is not marked (JARVIS-API 98.4): show the PC's own help
    // words calmly, keep the question open, and let go of what was typed.
    // (The busy repaint made a new box that carries the typed words over, so
    // that one is emptied too.)
    box.value = "";
    const liveBox = dom.quizRun ? dom.quizRun.querySelector(".quiz-answer") : null;
    if (liveBox) liveBox.value = "";
    qz.answers.delete(question.n);
    qz.crisis = quizReadCrisis(out);
    if (!qz.crisis) qz.error = "Jarvis answered, but not with words this app can read.";
    const open = readQuiz(out.quiz);
    if (open) takeQuiz(open);
    qz.shown = null;
    paintQuiz();
    return;
  }
  const quiz = readQuiz(out.quiz);
  if (quiz) {
    takeQuiz(quiz);
    qz.shown = question.n;
    qz.focusNext = "next";
    // Held in memory only, until the quiz ends, for the Keep sheet.
    qz.answers.set(question.n, value);
  }
  paintQuiz();
}

async function finishQuiz() {
  const questions = qz.quiz;
  const out = await quizCall("brain_quiz_finish", { id: qz.quiz.id }, "");
  if (!out) return;
  qz.summary = readSummary(out.summary);
  // The PC has forgotten the quiz by now; the words shown in the summary are
  // the ones this window already held (empty while the lists are hidden).
  qz.last = questions;
  qz.quiz = null;
  qz.shown = null;
  qz.keep = null;
  qz.answers = new Map();
  paintQuiz();
}

async function stopQuiz() {
  const id = qz.quiz && qz.quiz.id;
  if (!id) return;
  const out = await quizCall("brain_quiz_stop", { id }, "");
  if (!out) return;
  quizReset();
  toast("Quiz forgotten.", "ok");
  paintQuiz();
}

/* ── Grade this better (docs/STUDY-FROM-TEXT-DESIGN.md §15, JARVIS-API 113) ── */

async function loadQuizCloudInfo() {
  try {
    const res = await invoke("brain_quiz_cloud_info");
    qz.cloudInfo = qcReadInfo(res);
    paintQuiz();
  } catch (_) {
    qz.cloudInfo = null;
  }
}

async function startQuizCloud() {
  const q = qz.quiz;
  if (!q || qz.busy || q.mode === "spanish") return;
  if (!qz.cloudInfo || !qz.cloudInfo.ready) return;
  qz.busy = QC_SENDING;
  qz.cloudSaid = "";
  qz.error = "";
  paintQuiz();
  try {
    const res = await invoke("brain_quiz_cloud_start", { quizId: q.id });
    if (res && res.ok === false) {
      qz.error = qcOutcome(res, "Refused.").said;
      qz.busy = "";
      paintQuiz();
      return;
    }
    const out = qcOutcome(res, "Not started.");
    if (!out.ok || !out.request) {
      qz.error = out.said;
      qz.busy = "";
      paintQuiz();
      return;
    }
    qz.cloudRequest = out.request;
    qz.busy = "";
    qz.cloudSaid = out.said;
    qz.cloudGen++;
    paintQuiz();
    pollQuizCloud();
  } catch (e) {
    qz.error = errorText(e);
    qz.busy = "";
    paintQuiz();
  }
}

async function cancelQuizCloud() {
  const r = qz.cloudRequest;
  if (!r) return;
  qz.busy = QC_CANCELLING;
  paintQuiz();
  try {
    const res = await invoke("brain_quiz_cloud_cancel", { id: r.id });
    const out = qcOutcome(res, "Not cancelled.");
    if (out.request) {
      qz.cloudRequest = out.request;
      qz.cloudSaid = out.said;
    }
  } catch (e) {
    qz.cloudSaid = errorText(e);
  } finally {
    qz.busy = "";
    paintQuiz();
  }
}

async function pollQuizCloud() {
  if (qz.cloudTimer) {
    clearTimeout(qz.cloudTimer);
    qz.cloudTimer = null;
  }
  const cur = qz.cloudRequest;
  if (!cur || !qcKeepPolling(cur.phase)) return;
  const gen = qz.cloudGen;
  let answer;
  try {
    answer = await invoke("brain_quiz_cloud_get", { id: cur.id });
  } catch (e) {
    if (gen !== qz.cloudGen) return;
    qz.cloudSaid = errorText(e);
    paintQuiz();
    scheduleQuizCloudPoll();
    return;
  }
  if (gen !== qz.cloudGen) return;
  const out = qcOutcome(answer, "Not read.");
  if (!out.ok || !out.request) {
    qz.cloudRequest = null;
    qz.cloudSaid = out.said;
    paintQuiz();
    return;
  }
  const req = out.request;
  qz.cloudRequest = req;
  qz.cloudSaid = out.said;
  if (req.phase === "ready") {
    if (req.quiz) {
      takeQuiz(req.quiz);
    } else {
      try {
        const q = await invoke("brain_quiz_get", { id: cur.quizId });
        if (q && q.quiz) takeQuiz(q.quiz);
      } catch (_) {}
    }
    qz.cloudRequest = null;
    paintQuiz();
    return;
  }
  if (req.phase === "ended") {
    qz.cloudRequest = null;
    paintQuiz();
    return;
  }
  if (qcIsKnown(req.state)) {
    qz.cloudUnknownSince = null;
  } else {
    const now = Date.now();
    qz.cloudUnknownSince = qz.cloudUnknownSince == null ? now : qz.cloudUnknownSince;
    if (qcGiveUpOnUnknown(qz.cloudUnknownSince, now)) {
      qz.cloudRequest = null;
      paintQuiz();
      return;
    }
  }
  paintQuiz();
  scheduleQuizCloudPoll();
}

function scheduleQuizCloudPoll() {
  if (qz.cloudTimer) clearTimeout(qz.cloudTimer);
  qz.cloudTimer = setTimeout(pollQuizCloud, QC_POLL_SECONDS * 1000);
}

/* The Keep sheet (docs/QUIZ-DECKS-DESIGN.md C3): every answered question with
   a tick, its passage and a box for the back. Nothing is sent until "Keep and
   finish"; the PC takes each question's own words and passage from its open
   quiz - this app sends only the number and the back. */

async function openKeep() {
  const q = qz.quiz;
  if (!q || q.hidden || q.provenance === "outside") return;
  qz.error = "";
  qz.crisis = "";
  qz.keep = {
    rows: Decks.keepRows(q, qz.answers),
    choice: "",
    newName: Decks.defaultDeckName(q.title),
    decks: null,
    why: "",
    error: "",
    nameProblem: false,
    loading: true,
    busy: false,
  };
  qz.focusNext = qz.keep.rows[0] ? `tick:${qz.keep.rows[0].n}` : "keep-cancel";
  paintQuiz();
  await loadKeepDecks();
}

/** Reads the decks the sheet can keep into. */
async function loadKeepDecks() {
  const k = qz.keep;
  if (!k) return;
  k.loading = true;
  k.why = "";
  try {
    const out = await invoke("brain_decks");
    const view = Decks.readDecks(out);
    if (!view) {
      k.decks = null;
      k.why = isRefusal(out) ? Decks.refusalWords(out) : Decks.MISSING;
    } else {
      k.decks = view;
      k.why = view.available ? "" : (view.why || Decks.MISSING);
      if (!view.decks.some((d) => d.id === k.choice)) k.choice = "";
    }
  } catch (error) {
    k.decks = null;
    k.why = errorText(error);
  }
  k.loading = false;
  if (qz.keep === k) paintQuiz();
}

async function keepAndFinish() {
  const k = qz.keep;
  const questions = qz.quiz;
  if (!k || !questions) return;
  const made = Decks.keepPayload(k.rows, k.choice, k.newName);
  if (made.error) {
    k.error = made.error;
    k.nameProblem = Boolean(made.nameProblem);
    paintQuiz();
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    k.error = STALE_TITLE;
    paintQuiz();
    return;
  }
  k.error = "";
  k.nameProblem = false;
  k.busy = true;
  qz.error = "";
  qz.crisis = "";
  paintQuiz();
  let out;
  try {
    out = await invoke("brain_quiz_finish", { id: questions.id, keep: made.keep });
  } catch (error) {
    k.busy = false;
    k.error = errorText(error);
    paintQuiz();
    return;
  }
  k.busy = false;
  if (quizIsCrisis(out)) {
    // Nothing was kept and the quiz is still open (JARVIS-API 102.1): the PC's
    // own words, shown calmly, and the sheet stays as it was.
    qz.crisis = quizReadCrisis(out);
    const open = readQuiz(out.quiz);
    if (open) takeQuiz(open);
    paintQuiz();
    return;
  }
  if (isRefusal(out)) {
    if (out.error === "not_found") {
      qz.error = quizErrorWords(out);
      qz.quiz = null;
      qz.keep = null;
      qz.shown = null;
      paintQuiz();
      return;
    }
    k.error = Decks.refusalWords(out);
    k.nameProblem = out.error === "bad_deck_name";
    if (out.error === "deck_not_found") {
      k.choice = "";
      paintQuiz();
      await loadKeepDecks();
      return;
    }
    paintQuiz();
    return;
  }
  qz.summary = readSummary(out.summary);
  qz.kept = Number.isInteger(out.kept) && out.kept >= 0 ? out.kept : 0;
  qz.last = questions;
  qz.quiz = null;
  qz.shown = null;
  qz.keep = null;
  qz.answers = new Map();
  qz.focusNext = "close";
  paintQuiz();
  // The deck list has new cards in it.
  dk.at = 0;
  if (state.view === "work") loadDecks();
}

function keepSheet(q) {
  const k = qz.keep;
  const box = el("div", "goal-block");
  box.append(el("h3", "subhead", Decks.KEEP_BUTTON));
  box.append(el("p", "note", Decks.KEEP_INTRO));
  // The backend's check for a crisis phrase reads English only: say so where the
  // owner types the words that will be kept (the quiz's own notice, word for word).
  if (q.mode === "spanish" && q.notice) box.append(el("p", "note", q.notice));
  if (k.loading) box.append(el("p", "note", Decks.LOADING));
  if (k.why) box.append(el("p", "empty failed", k.why));
  k.rows.forEach((r, i) => {
    const row = el("div", "keep-row");
    const label = el("label", "keep-tick");
    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.checked = r.tick;
    tick.dataset.fkey = `tick:${r.n}`;
    tick.addEventListener("change", () => { k.rows[i].tick = tick.checked; });
    label.append(tick, el("span", "", r.prompt));
    row.append(label);
    if (r.passage) {
      row.append(el("p", "goal-note", quizMarkLines(null, q).passageHeading));
      row.append(el("p", "quiz-passage", r.passage));
    }
    const back = document.createElement("textarea");
    back.className = "field keep-back";
    back.rows = 3;
    back.maxLength = Decks.LIMITS.back;
    back.spellcheck = true;
    back.placeholder = Decks.KEEP_BACK_PLACEHOLDER;
    back.setAttribute("aria-label", `${Decks.KEEP_BACK_PLACEHOLDER}: question ${r.n}`);
    back.dataset.fkey = `back:${r.n}`;
    back.value = r.back;
    const count = el("p", "note", Decks.backCount(r.back).note);
    back.addEventListener("input", () => {
      k.rows[i].back = back.value;
      count.textContent = Decks.backCount(back.value).note;
    });
    row.append(back, count);
    box.append(row);
  });
  // Where the questions go: an existing deck, or a new one.
  const where = el("div", "quiz-spanish-row");
  const choose = document.createElement("select");
  choose.className = "field";
  choose.id = "keep-deck";
  choose.dataset.fkey = "deck";
  choose.append(new Option(Decks.NEW_DECK, ""));
  for (const d of (k.decks && k.decks.decks) || []) choose.append(new Option(d.name || Decks.HIDDEN_NAME, d.id));
  choose.value = k.choice;
  choose.addEventListener("change", () => {
    k.choice = choose.value;
    paintQuiz();
  });
  const chooseLabel = el("label", "quiz-lab", Decks.CHOOSE_DECK);
  chooseLabel.htmlFor = "keep-deck";
  where.append(chooseLabel, choose);
  if (!k.choice) {
    const name = document.createElement("input");
    name.type = "text";
    name.className = "field";
    name.maxLength = Decks.LIMITS.name;
    name.id = "keep-name";
    name.dataset.fkey = "name";
    name.setAttribute("aria-label", Decks.DECK_NAME);
    name.placeholder = Decks.DECK_NAME;
    name.value = k.newName;
    if (k.nameProblem) name.setAttribute("aria-invalid", "true");
    name.addEventListener("input", () => { k.newName = name.value; });
    where.append(name);
  }
  box.append(where);
  if (k.error) {
    const err = el("p", "empty failed", k.error);
    err.setAttribute("role", "alert");
    box.append(err);
  }
  const actions = el("div", "goal-actions");
  const go = button(Decks.KEEP_FINISH, keepAndFinish, { live: true });
  go.dataset.fkey = "keep-go";
  if (k.busy || k.loading || Boolean(k.why) || !k.rows.length) {
    go.dataset.busy = "true";
    go.disabled = true;
  }
  const cancel = button(Decks.KEEP_CANCEL, () => {
    qz.keep = null;
    qz.focusNext = "keep";
    paintQuiz();
  });
  cancel.dataset.fkey = "keep-cancel";
  actions.append(go, cancel);
  box.append(actions);
  return box;
}

function markBlock(mark, quiz) {
  const lines = quizMarkLines(mark, quiz);
  const box = el("div", "quiz-mark");
  const head = el("div", "goal-head");
  head.append(el("span", "goal-title", quizLevelLabel(mark.level)));
  if (lines.cloudLabel) head.append(el("span", "row-tag", lines.cloudLabel));
  if (lines.showGuess) head.append(el("span", "row-tag", QUIZ_GUESS));
  box.append(head);
  if (mark.comment) box.append(el("p", "", mark.comment));
  if (lines.answerLine) box.append(el("p", "quiz-prompt", lines.answerLine));
  if (lines.answerLine && lines.keyLabel) box.append(el("p", "goal-note", lines.keyLabel));
  if (mark.passage) {
    box.append(el("p", "goal-note", lines.passageHeading));
    box.append(el("p", "quiz-passage", mark.passage));
  }
  return box;
}

function paintQuizCount() {
  if (!dom.quizTextCount || !dom.quizText) return;
  const value = dom.quizText.value;
  // Spanish practice takes no text at all: the model writes the sentences.
  dom.quizTextCount.textContent = qz.mode === "spanish" && !value.trim()
    ? `0 / ${QUIZ_LIMITS.textMax.toLocaleString("en-US")} characters`
    : quizTextCount(value).note;
}

function paintTopicCount() {
  if (dom.quizTopicCount && dom.quizTopic) dom.quizTopicCount.textContent = quizTopicCount(dom.quizTopic.value).note;
}

/** The row of Spanish letters under an answer box: each inserts at the cursor. */
function accentRow(answer, count) {
  const row = el("div", "quiz-accents");
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", QUIZ_ACCENT_ROW);
  for (const ch of QUIZ_ACCENTS) {
    const b = el("button", "btn small", ch);
    b.type = "button";
    b.setAttribute("aria-label", `Insert ${ch}`);
    b.dataset.fkey = `accent:${ch}`;
    // A mouse press must not take the cursor out of the answer box.
    b.addEventListener("mousedown", (event) => event.preventDefault());
    b.addEventListener("click", () => {
      const at = quizInsertAtCursor(answer.value, answer.selectionStart, answer.selectionEnd, ch, QUIZ_LIMITS.answerMax);
      answer.value = at.value;
      answer.focus();
      answer.setSelectionRange(at.caret, at.caret);
      count.textContent = quizAnswerCount(answer.value).note;
    });
    row.append(b);
  }
  return row;
}

function paintQuiz() {
  const run = dom.quizRun;
  if (!run) return;
  const focusKey = qz.focusNext || fkeyBefore(run, qz);
  qz.focusNext = "";
  // A repaint from elsewhere (the tab shown again, a link change) must not
  // wipe an answer being typed: carry it over to the same question. It stays
  // in this window's memory only.
  const typing = run.querySelector(".quiz-answer");
  const typed = typing ? { n: typing.dataset.n, value: typing.value } : null;
  if (dom.quizStartForm) dom.quizStartForm.hidden = Boolean(qz.quiz || qz.summary);
  // A quiz made from a video's captions has its own outside-text line.
  if (dom.quizOutside) dom.quizOutside.textContent = ytFromCaptions(qz.quiz) ? YT_OUTSIDE : QUIZ_OUTSIDE_LINE;
  const parts = [];
  if (qz.busy) parts.push(el("p", "note", qz.busy));
  if (qz.error) parts.push(el("p", "empty failed", qz.error));
  if (qz.crisis) {
    // The PC's help words, shown calmly in place of a mark: no colour, no
    // mark label, no "Jarvis's guess". Text only; kept until the next action.
    const calm = el("div", "quiz-crisis");
    calm.setAttribute("role", "status");
    for (const para of quizCrisisParagraphs(qz.crisis)) {
      const p = el("p", "");
      for (const run of para) {
        if (run.bold) p.append(el("strong", "", run.text));
        else p.append(document.createTextNode(run.text));
      }
      calm.append(p);
    }
    parts.push(calm);
  }
  const q = qz.quiz;
  if (qz.summary) {
    const s = qz.summary;
    const block = el("div", "goal-block");
    block.append(el("h3", "subhead", QUIZ_AGAIN_HEADING));
    block.append(el("p", "note", quizCountsLine(s)));
    if (qz.kept !== null) block.append(el("p", "note", Decks.keptLine(qz.kept)));
    if (s.again.length) {
      const list = el("div", "quiz-again");
      for (const n of s.again) list.append(el("p", "", quizAgainLine(n, qz.last)));
      block.append(list);
    } else {
      block.append(el("p", "empty", QUIZ_AGAIN_EMPTY));
    }
    const close = button(QUIZ_CLOSE, () => {
      quizReset();
      paintQuiz();
    });
    close.dataset.fkey = "close";
    block.append(close);
    parts.push(block);
  } else if (q && qz.keep && !q.hidden) {
    parts.push(keepSheet(q));
  } else if (q) {
    const block = el("div", "goal-block");
    if (ytFromCaptions(q)) {
      block.append(el("p", "goal-note", YT_LABEL));
      if (qz.ytNote && qz.ytNote.id === q.id) block.append(el("p", "goal-note", qz.ytNote.note));
    }
    if (!q.hidden) block.append(el("p", "goal-note", quizProgressLine(q)));
    if (q.mode === "spanish" && q.level) block.append(el("p", "goal-note", quizLevelLine(q.level)));
    if (q.hidden) {
      block.append(hiddenNode(0, "words"));
    } else {
      const shown = qz.shown != null ? q.questions.find((x) => x.n === qz.shown) : null;
      const next = quizNextQuestion(q);
      if (shown && shown.mark) {
        block.append(el("p", "quiz-prompt", shown.prompt));
        block.append(markBlock(shown.mark, q));
        const more = quizNextQuestion(q);
        const actions = el("div", "goal-actions");
        if (more) {
          const nextButton = button(QUIZ_NEXT, () => {
            qz.shown = null;
            qz.focusNext = "answer";
            paintQuiz();
          });
          nextButton.dataset.fkey = "next";
          actions.append(nextButton);
        }
        block.append(actions);
      } else if (next) {
        block.append(el("span", "row-tag", QUIZ_KIND_LABELS[next.kind]));
        block.append(el("p", "quiz-prompt", next.prompt));
        // Under the answer box too: the PC's own words about Spanish crisis phrases.
        if (q.mode === "spanish" && q.notice) block.append(el("p", "note", q.notice));
        const answer = document.createElement("textarea");
        answer.className = "field quiz-answer";
        answer.rows = 4;
        answer.maxLength = QUIZ_LIMITS.answerMax;
        answer.spellcheck = q.mode !== "spanish";
        if (q.mode === "spanish") answer.lang = "es";
        answer.placeholder = QUIZ_ANSWER_PLACEHOLDER;
        answer.setAttribute("aria-label", `Your answer to question ${next.n}`);
        answer.dataset.n = String(next.n);
        answer.dataset.fkey = "answer";
        if (typed && typed.n === answer.dataset.n) answer.value = typed.value;
        const count = el("p", "note", quizAnswerCount(answer.value).note);
        answer.addEventListener("input", () => {
          count.textContent = quizAnswerCount(answer.value).note;
        });
        block.append(answer, count);
        if (q.mode === "spanish") block.append(accentRow(answer, count));
        const actions = el("div", "goal-actions");
        actions.append(button(QUIZ_ANSWER_LABEL, () => checkAnswer(next, answer), { live: true }));
        block.append(actions);
      } else {
        block.append(el("p", "note", quizProgressLine(q)));
      }
    }
    const foot = el("div", "goal-actions");
    // Finish and Stop reveal nothing (numbers only), so both stay while hidden.
    foot.append(button(QUIZ_FINISH, finishQuiz, { live: true }));
    // Cloud "Grade this better" button (docs/STUDY-FROM-TEXT-DESIGN.md §15)
    // Shown once at least one question is answered and the quiz is a text quiz. Beside Finish.
    if (q.mode !== "spanish" && q.questions.some((x) => x.mark) && qz.cloudInfo && qz.cloudInfo.available) {
      const isWaiting = qz.cloudRequest && qz.cloudRequest.phase === "waiting";
      const isWorking = qz.cloudRequest && qz.cloudRequest.phase === "working";
      if (isWaiting) {
        const cancelBtn = button(QC_CANCEL, cancelQuizCloud, { danger: true });
        cancelBtn.dataset.fkey = "qc-cancel";
        foot.append(cancelBtn);
      } else if (!isWorking) {
        const canGrade = qz.cloudInfo.ready;
        const gradeBtn = button(QC_BUTTON, startQuizCloud, { live: true });
        gradeBtn.dataset.fkey = "qc-grade";
        if (!canGrade) {
          gradeBtn.disabled = true;
          gradeBtn.title = QC_INTRO;
        }
        foot.append(gradeBtn);
      }
    }
    // Keep lists the owner's words, so it is never offered while they are hidden,
    // and quizzes made from outside text (like YouTube) cannot be saved to review decks.
    if (q.provenance !== "outside") {
      const keep = button(Decks.KEEP_BUTTON, openKeep);
      keep.dataset.fkey = "keep";
      if (q.hidden || !q.questions.some((x) => x.mark)) keep.disabled = true;
      if (q.hidden) keep.title = Decks.KEEP_HIDDEN;
      foot.append(keep);
    }
    foot.append(button(QUIZ_STOP, stopQuiz, { live: true, danger: true }));
    block.append(foot);
    if (qz.cloudSaid) {
      block.append(el("p", "note", qz.cloudSaid));
    }
    if (q.mode !== "spanish" && q.questions.some((x) => x.mark) && qz.cloudInfo && qz.cloudInfo.available) {
      block.append(el("p", "note", QC_LEAVES));
    }
    if (q.hidden && q.provenance !== "outside") block.append(el("p", "note", Decks.KEEP_HIDDEN));
    parts.push(block);
  }
  run.replaceChildren(...parts);
  fkeyAfter(run, focusKey);
  youtubeBlock.sync();
}

/** A hidden quiz read again after Show (or a setting change): Rust decides
 *  whether the words come back. Nothing is asked of the PC when no quiz is
 *  open. */
async function rereadQuiz() {
  if (!IS_TAURI || !qz.quiz) return;
  try {
    const out = await invoke("brain_quiz_get", { id: qz.quiz.id });
    if (quizProblem(out)) {
      paintQuiz();
      return;
    }
    const quiz = readQuiz(out.quiz);
    if (quiz) {
      takeQuiz(quiz);
      // The Keep sheet lists the owner's words: closed while they are hidden.
      if (quiz.hidden) qz.keep = null;
    }
  } catch (error) {
    qz.error = errorText(error);
  }
  paintQuiz();
}

let quizFormReady = false;

/** The Spanish choices' options, filled once, from the shared lists. */
function readyQuizForm() {
  if (quizFormReady) return;
  quizFormReady = true;
  if (dom.quizLevel) {
    for (const id of QUIZ_LEVEL_IDS) dom.quizLevel.append(new Option(id, id));
    dom.quizLevel.value = QUIZ_DEFAULT_LEVEL;
  }
  if (dom.quizExercise) {
    for (const e of QUIZ_EXERCISES) dom.quizExercise.append(new Option(e.label, e.id));
    dom.quizExercise.value = QUIZ_DEFAULT_EXERCISE;
  }
}

function renderQuiz() {
  readyQuizForm();
  setQuizMode(qz.mode);
  paintTopicCount();
  paintQuiz();
  youtubeBlock.enter();
  loadQuizCloudInfo();
}

if (dom.quizMode) {
  dom.quizMode.addEventListener("change", (event) => {
    const t = event.target;
    if (t && t.name === "quiz-mode") setQuizMode(t.value);
  });
}
if (dom.quizTopic) dom.quizTopic.addEventListener("input", paintTopicCount);
if (dom.quizStartForm) {
  dom.quizStartForm.addEventListener("submit", (event) => {
    event.preventDefault();
    startQuiz();
  });
}
if (dom.quizText) dom.quizText.addEventListener("input", paintQuizCount);
if (dom.quizStart) {
  liveButtons.add(dom.quizStart);
  syncLiveButton(dom.quizStart);
}

/* ==========================================================================
   My study decks (the owner's decision of 2026-09-30; docs/QUIZ-DECKS-DESIGN.md,
   Slice contract C3-C6; JARVIS-API.md section 102; decks.js).

   Questions kept from a quiz, asked again on a schedule the PC works out.
   Read and changed through their own commands (brain/decks.rs), not
   brain_read. No card anywhere: the owner's own tap saves the owner's own
   words, sealed on the PC. Every change is held on a stale link. While the
   private lists are hidden Rust takes the names and every card's words out
   and does not fetch a review card at all; this section shows the counts and
   the line, and the "Show" prompt.

   Nothing is stored in this window: no name, no card, no typed answer - not
   in localStorage, not as a draft.
   ========================================================================== */

const dk = {
  view: null, error: "", loading: false, again: false, at: 0,
  // The deck whose cards are open, and the cards read for it.
  opening: "", cards: null, cardsError: "", cardsLoading: false,
  // What is being renamed / edited / confirmed / added (ids only, no words).
  renaming: "", editing: "", confirm: "", adding: false,
  // The review session: null when not reviewing.
  review: null,
  // The control that should have the keyboard after the next paint, and the
  // last one that had it (trackFkeys).
  focusNext: "", lastFocus: "",
};
const DECKS_READ_MS = 20000;

async function loadDecks() {
  if (!IS_TAURI) return;
  if (dk.loading) {
    dk.again = true;
    return;
  }
  dk.loading = true;
  try {
    const out = await invoke("brain_decks");
    const view = Decks.readDecks(out);
    if (view) {
      dk.view = view;
      dk.error = "";
    } else {
      dk.error = isRefusal(out) ? Decks.refusalWords(out) : Decks.MISSING;
    }
  } catch (error) {
    dk.error = errorText(error);
  } finally {
    dk.loading = false;
    dk.at = Date.now();
  }
  if (dk.again) {
    dk.again = false;
    await loadDecks();
    return;
  }
  // Hidden lists end a review and close the cards: nothing of them stays drawn.
  if (dk.view && dk.view.hidden) {
    dk.review = null;
    dk.cards = null;
    dk.opening = "";
    dk.renaming = "";
    dk.editing = "";
  }
  if (dk.opening && !dk.cardsLoading) await loadDeckCards(dk.opening, false);
  if (state.view === "work") paintDecks();
}

async function loadDeckCards(id, repaint = true) {
  dk.cardsLoading = true;
  dk.cardsError = "";
  try {
    const out = await invoke("brain_decks_cards", { id });
    const cards = Decks.readCards(out);
    if (cards) {
      dk.cards = cards;
    } else {
      dk.cards = null;
      dk.cardsError = isRefusal(out) ? Decks.refusalWords(out) : Decks.MISSING;
      if (isRefusal(out) && out.error === "deck_not_found") dk.opening = "";
    }
  } catch (error) {
    dk.cards = null;
    dk.cardsError = errorText(error);
  }
  dk.cardsLoading = false;
  if (repaint && state.view === "work") paintDecks();
}

/** One change to a deck or card. Refused on a stale link; the PC's own words
 *  for a refusal. Returns the answer, or null. */
async function decksCall(cmd, args) {
  if (!linkWords(currentLink()).canAct) {
    dk.error = STALE_TITLE;
    paintDecks();
    return null;
  }
  try {
    const out = await invoke(cmd, args);
    if (isRefusal(out)) {
      dk.error = Decks.refusalWords(out);
      if (out.error === "deck_not_found" || out.error === "card_not_found") {
        dk.opening = out.error === "deck_not_found" ? "" : dk.opening;
        dk.at = 0;
        loadDecks();
      }
      paintDecks();
      return null;
    }
    dk.error = "";
    return out;
  } catch (error) {
    dk.error = errorText(error);
    paintDecks();
    return null;
  }
}

async function deckAct(id, action, name) {
  const out = await decksCall("brain_decks_act", name === undefined ? { id, action } : { id, action, name });
  if (!out) return false;
  if (action === "delete" && dk.opening === id) {
    dk.opening = "";
    dk.cards = null;
  }
  dk.renaming = "";
  dk.confirm = "";
  await loadDecks();
  return true;
}

async function cardAct(id, cid, action, front, back) {
  const args = { id, cid, action };
  if (action === "edit") {
    args.front = front;
    args.back = back;
  }
  const out = await decksCall("brain_decks_card_act", args);
  if (!out) return false;
  dk.editing = "";
  dk.confirm = "";
  await loadDeckCards(id, false);
  dk.at = 0;
  await loadDecks();
  return true;
}

async function addDeck(name) {
  const out = await decksCall("brain_decks_create", { name });
  if (!out) return false;
  dk.adding = false;
  dk.at = 0;
  await loadDecks();
  return true;
}

async function setNewPerDay(value, input) {
  const n = Number(value);
  const max = (dk.view && dk.view.limits.newPerDay) || Decks.LIMITS.newPerDay;
  if (!Number.isInteger(n) || n < 0 || n > max) {
    dk.error = `New cards a day is a whole number from 0 to ${max}.`;
    if (dk.view) input.value = String(dk.view.newPerDay);
    paintDecks();
    return;
  }
  const out = await decksCall("brain_decks_settings", { newPerDay: n });
  if (!out) {
    if (dk.view) input.value = String(dk.view.newPerDay);
    return;
  }
  dk.at = 0;
  await loadDecks();
}

/* ── The review session ────────────────────────────────────────────────── */

async function startReview(deck) {
  dk.review = { deck: deck || "", data: null, reveal: null, typed: "", error: "", busy: false, comes: "" };
  paintDecks();
  await fetchReview();
}

/** Ends the session and goes back to the deck list, read again. */
function leaveReview() {
  dk.review = null;
  dk.at = 0;
  paintDecks();
  loadDecks();
}

/** Takes the PC's review answer into the session. */
function takeReview(out, comes) {
  const r = dk.review;
  if (!r) return;
  if (Decks.isHiddenReview(out)) {
    r.error = Decks.REVIEW_HIDDEN;
    r.data = null;
    r.reveal = null;
    return;
  }
  if (isRefusal(out)) {
    r.error = Decks.refusalWords(out);
    return;
  }
  const data = Decks.readReview(out);
  if (!data) {
    r.error = Decks.MISSING;
    return;
  }
  r.error = "";
  r.data = data;
  r.reveal = null;
  r.typed = "";
  r.comes = comes || "";
  dk.focusNext = data.state === "card" ? "typed" : "screen-title";
}

async function fetchReview() {
  const r = dk.review;
  if (!r) return;
  r.busy = true;
  try {
    const out = await invoke("brain_review", { deck: r.deck || null });
    takeReview(out);
  } catch (error) {
    r.error = errorText(error);
  }
  r.busy = false;
  if (r.data && r.data.state === "no_decks") {
    leaveReview();
    return;
  }
  paintDecks();
  if (r.data && r.data.state !== "card") {
    // Empty / enough / paused: the next-ready day comes from the deck list.
    dk.at = 0;
    loadDecks();
  }
}

async function revealCard() {
  const r = dk.review;
  if (!r || !r.data || !r.data.card || r.busy) return;
  if (!linkWords(currentLink()).canAct) {
    r.error = STALE_TITLE;
    paintDecks();
    return;
  }
  r.busy = true;
  try {
    const out = await invoke("brain_review_reveal", { card: r.data.card.id });
    if (Decks.isHiddenReview(out)) {
      r.error = Decks.REVIEW_HIDDEN;
    } else if (isRefusal(out)) {
      r.error = Decks.refusalWords(out);
      if (out.error === "card_not_found") {
        r.busy = false;
        await fetchReview();
        return;
      }
    } else {
      const back = Decks.readReveal(out);
      if (back) {
        r.reveal = back;
        dk.focusNext = "answer-heading";
        r.error = "";
        // What was typed was only for the owner: dropped, never sent.
        r.typed = "";
      } else {
        r.error = Decks.MISSING;
      }
    }
  } catch (error) {
    r.error = errorText(error);
  }
  r.busy = false;
  paintDecks();
}

async function rateCard(rating) {
  const r = dk.review;
  if (!r || !r.data || !r.data.card || !r.reveal) return;
  // One rating at a time: a second tap while the first is on its way would
  // rate the next card from the first card's answer.
  if (r.busy) return;
  if (!linkWords(currentLink()).canAct) {
    r.error = STALE_TITLE;
    paintDecks();
    return;
  }
  r.busy = true;
  try {
    const out = await invoke("brain_review_rate", { card: r.data.card.id, rating, deck: r.deck || "" });
    if (isRefusal(out) && (out.error === "card_not_found" || out.error === "not_revealed")) {
      // The card is gone or no longer up, or the PC no longer remembers that its
      // back was shown (it restarted): drop the reveal and ask for the card
      // again, so the owner can show the answer and rate it.
      r.busy = false;
      r.reveal = null;
      await fetchReview();
      return;
    }
    const before = r.error;
    const read = Decks.readReview(out);
    takeReview(out, read && read.comesBack ? `Comes back on ${Decks.formatDay(read.comesBack)}` : "");
    if (!r.error && before) r.error = "";
  } catch (error) {
    r.error = errorText(error);
  }
  r.busy = false;
  if (r.data && r.data.state === "no_decks") {
    leaveReview();
    return;
  }
  paintDecks();
  if (r.data && r.data.state !== "card") {
    dk.at = 0;
    loadDecks();
  }
}

async function moreCards() {
  const r = dk.review;
  if (!r || r.busy) return;
  if (!linkWords(currentLink()).canAct) {
    r.error = STALE_TITLE;
    paintDecks();
    return;
  }
  r.busy = true;
  try {
    const out = await invoke("brain_review_more", { deck: r.deck || null });
    takeReview(out);
  } catch (error) {
    r.error = errorText(error);
  }
  r.busy = false;
  if (r.data && r.data.state === "no_decks") {
    leaveReview();
    return;
  }
  paintDecks();
}

function paintReview(box) {
  const r = dk.review;
  const view = dk.view;
  const top = el("div", "goal-block");
  if (r.error) {
    const err = el("p", "empty failed", r.error);
    err.setAttribute("role", "alert");
    top.append(err);
  }
  if (r.comes) top.append(el("p", "note", r.comes));
  const data = r.data;
  if (!data) {
    if (r.busy) top.append(el("p", "note", Decks.LOADING));
    const stop = button(Decks.STOP, leaveReview);
    stop.dataset.fkey = "review-stop";
    top.append(stop);
    box.append(top);
    return;
  }
  const screen = Decks.reviewScreen(data, view ? view.nextReadyDay : null);
  if (screen.kind === "card" && data.card) {
    const card = data.card;
    const head = el("div", "goal-head");
    if (QUIZ_KIND_LABELS[card.kind]) head.append(el("span", "row-tag", QUIZ_KIND_LABELS[card.kind]));
    const level = Decks.cardLevelLine(card.level);
    if (level) head.append(el("span", "goal-note", level));
    top.append(head);
    top.append(el("p", "review-front", card.front));
    if (!r.reveal) {
      const typed = document.createElement("textarea");
      typed.className = "field review-typed";
      typed.rows = 3;
      typed.maxLength = Decks.LIMITS.back;
      typed.placeholder = Decks.TYPED_PLACEHOLDER;
      typed.setAttribute("aria-label", Decks.TYPED_PLACEHOLDER);
      typed.dataset.fkey = "typed";
      // Kept only so a repaint does not wipe it; never sent, dropped on Show answer.
      typed.value = r.typed;
      typed.addEventListener("input", () => { r.typed = typed.value; });
      top.append(typed);
      const actions = el("div", "goal-actions");
      const show = button(Decks.SHOW_ANSWER, revealCard, { live: true });
      show.dataset.fkey = "show";
      actions.append(show);
      top.append(actions);
    } else {
      const back = el("div", "review-back");
      const heading = el("h3", "subhead", Decks.BACK_HEADING);
      heading.tabIndex = -1;
      heading.dataset.fkey = "answer-heading";
      back.append(heading);
      back.append(el("p", "", r.reveal.answer || Decks.NO_CARD_ANSWER));
      if (r.reveal.passage) {
        back.append(el("p", "goal-note", Decks.backPassageHeading(r.reveal)));
        back.append(el("p", "quiz-passage", r.reveal.passage));
      }
      if (r.reveal.keyLabel) back.append(el("p", "goal-note", r.reveal.keyLabel));
      top.append(back);
      const ratings = el("div", "review-ratings");
      ratings.setAttribute("role", "group");
      ratings.setAttribute("aria-label", Decks.RATING_GROUP);
      for (const rating of Decks.RATINGS) {
        const b = button(rating.label, () => rateCard(rating.id), { live: true });
        b.dataset.fkey = `rate:${rating.id}`;
        b.dataset.rating = rating.id;
        ratings.append(b);
      }
      top.append(ratings);
    }
    const stop = button(Decks.STOP, leaveReview);
    stop.dataset.fkey = "review-stop";
    const foot = el("div", "goal-actions");
    foot.append(stop);
    top.append(foot);
  } else {
    if (screen.title) {
      const title = el("h3", "subhead", screen.title);
      title.tabIndex = -1;
      title.dataset.fkey = "screen-title";
      top.append(title);
    }
    if (screen.note) top.append(el("p", "note", screen.note));
    const actions = el("div", "goal-actions");
    if (screen.actions.includes("more")) {
      const more = button(Decks.MORE, moreCards, { live: true });
      more.dataset.fkey = "more";
      actions.append(more);
    }
    const stop = button(Decks.STOP, leaveReview);
    stop.dataset.fkey = "review-stop";
    actions.append(stop);
    top.append(actions);
  }
  box.append(top);
}

/* ── The deck list ─────────────────────────────────────────────────────── */

function labelled(b, words, name) {
  // The visible words stay in the name; the deck is added for a screen reader.
  b.setAttribute("aria-label", name ? `${words}: ${name}` : words);
  return b;
}

function deckRow(deck, view) {
  const hidden = view.hidden;
  const item = el("div", "deck-row");
  const head = el("div", "goal-head");
  head.append(el("span", "deck-name", hidden ? Decks.HIDDEN_NAME : deck.name));
  if (deck.paused) head.append(el("span", "row-tag", Decks.PAUSED_TAG));
  item.append(head);
  item.append(el("p", "note", Decks.deckMeta(deck)));
  const name = hidden ? "" : deck.name;
  if (dk.renaming === deck.id && !hidden) {
    item.append(nameForm(deck.name, (value) => deckAct(deck.id, "rename", value), () => {
      dk.renaming = "";
      paintDecks();
    }, `rename:${deck.id}`));
    return item;
  }
  const actions = el("div", "goal-actions");
  if (!hidden) {
    const review = labelled(button(Decks.REVIEW, () => startReview(deck.id)), Decks.REVIEW, name);
    review.dataset.fkey = `review:${deck.id}`;
    if (!Decks.canReview(view, deck)) review.disabled = true;
    actions.append(review);
  }
  const pause = labelled(
    button(deck.paused ? Decks.RESUME : Decks.PAUSE, () => deckAct(deck.id, deck.paused ? "resume" : "pause"), { live: true }),
    deck.paused ? Decks.RESUME : Decks.PAUSE, name);
  pause.dataset.fkey = `pause:${deck.id}`;
  actions.append(pause);
  if (!hidden) {
    const cards = labelled(button(Decks.CARDS_LINK, async () => {
      if (dk.opening === deck.id) {
        dk.opening = "";
        dk.cards = null;
        paintDecks();
        return;
      }
      dk.opening = deck.id;
      dk.cards = null;
      dk.editing = "";
      dk.confirm = "";
      paintDecks();
      await loadDeckCards(deck.id);
    }), Decks.CARDS_LINK, name);
    cards.dataset.fkey = `cards:${deck.id}`;
    cards.setAttribute("aria-expanded", String(dk.opening === deck.id));
    actions.append(cards);
    const edit = labelled(button(Decks.EDIT, () => {
      dk.renaming = deck.id;
      dk.focusNext = `rename:${deck.id}`;
      paintDecks();
    }, { live: true }), Decks.EDIT, name);
    edit.dataset.fkey = `edit:${deck.id}`;
    actions.append(edit);
    const del = labelled(button(Decks.DELETE_DECK, () => {
      dk.confirm = `deck:${deck.id}`;
      dk.focusNext = `confirm-delete:${deck.id}:cancel`;
      paintDecks();
    }, { live: true, danger: true }), Decks.DELETE_DECK, name);
    del.dataset.fkey = `delete:${deck.id}`;
    actions.append(del);
  }
  item.append(actions);
  if (dk.confirm === `deck:${deck.id}` && !hidden) {
    item.append(confirmBox(() => deckAct(deck.id, "delete"), `confirm-delete:${deck.id}`));
  }
  if (dk.opening === deck.id && !hidden) item.append(cardsBox(deck));
  return item;
}

/** "Are you sure? ..." with Delete and Cancel. */
function confirmBox(onDelete, fkey) {
  const box = el("div", "deck-confirm");
  box.setAttribute("role", "group");
  box.append(el("p", "", Decks.DELETE_CONFIRM));
  const actions = el("div", "goal-actions");
  const yes = button(Decks.DELETE, onDelete, { live: true, danger: true });
  yes.dataset.fkey = fkey;
  const no = button(Decks.CANCEL, () => {
    dk.confirm = "";
    paintDecks();
  });
  no.dataset.fkey = `${fkey}:cancel`;
  actions.append(yes, no);
  box.append(actions);
  return box;
}

/** A name box with Save and Cancel (a new deck, or a rename). */
function nameForm(value, onSave, onCancel, fkey) {
  const form = el("form", "todo-form");
  form.autocomplete = "off";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "field todo-text";
  input.maxLength = Decks.LIMITS.name;
  input.placeholder = Decks.DECK_NAME;
  input.setAttribute("aria-label", Decks.DECK_NAME);
  input.value = value;
  input.dataset.fkey = fkey;
  const save = el("button", "btn small", Decks.SAVE);
  save.type = "submit";
  liveButtons.add(save);
  syncLiveButton(save);
  const cancel = button(Decks.CANCEL, onCancel);
  cancel.dataset.fkey = `${fkey}:cancel`;
  form.append(input, save, cancel);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!Decks.deckNameOk(input.value)) {
      dk.error = "A deck name is 1 to 60 characters.";
      paintDecks();
      return;
    }
    onSave(input.value.trim());
  });
  return form;
}

function cardsBox(deck) {
  const box = el("div", "deck-cards");
  if (dk.cardsLoading && !dk.cards) box.append(el("p", "note", Decks.LOADING));
  if (dk.cardsError) box.append(el("p", "empty failed", dk.cardsError));
  const list = dk.cards && dk.cards.deckId === deck.id ? dk.cards : null;
  if (!list) return box;
  if (list.hidden) {
    box.append(hiddenNode(0, "words"));
    return box;
  }
  if (!list.cards.length) box.append(el("p", "empty", Decks.NO_CARDS));
  for (const card of list.cards) {
    const item = el("div", "deck-card");
    if (dk.editing === card.id) {
      const front = document.createElement("input");
      front.type = "text";
      front.className = "field";
      front.maxLength = Decks.LIMITS.front;
      front.setAttribute("aria-label", Decks.FRONT_LABEL);
      front.dataset.fkey = `front:${card.id}`;
      front.value = card.front;
      const back = document.createElement("textarea");
      back.className = "field keep-back";
      back.rows = 3;
      back.maxLength = Decks.LIMITS.back;
      back.setAttribute("aria-label", Decks.BACK_LABEL);
      back.dataset.fkey = `back:${card.id}`;
      back.value = card.back;
      const actions = el("div", "goal-actions");
      const save = button(Decks.SAVE, () => {
        if (!front.value.trim()) {
          dk.error = "The front of a card is 1 to 500 characters.";
          paintDecks();
          return;
        }
        return cardAct(deck.id, card.id, "edit", front.value, back.value);
      }, { live: true });
      save.dataset.fkey = `save:${card.id}`;
      const cancel = button(Decks.CANCEL, () => {
        dk.editing = "";
        paintDecks();
      });
      cancel.dataset.fkey = `cancel:${card.id}`;
      actions.append(save, cancel);
      item.append(front, back, actions);
    } else {
      item.append(el("p", "deck-front", card.front));
      item.append(el("p", "deck-back", card.back || Decks.NO_CARD_ANSWER));
      if (card.passage) {
        const heading = card.keySource === "model" ? Decks.EXAMPLE_SENTENCE : Decks.FROM_TEXT;
        item.append(el("p", "goal-note", heading));
        item.append(el("p", "quiz-passage", card.passage));
      }
      if (card.keyLabel) item.append(el("p", "goal-note", card.keyLabel));
      const actions = el("div", "goal-actions");
      const edit = labelled(button(Decks.EDIT, () => {
        dk.editing = card.id;
        dk.confirm = "";
        dk.focusNext = `front:${card.id}`;
        paintDecks();
      }, { live: true }), Decks.EDIT, card.front);
      edit.dataset.fkey = `edit-card:${card.id}`;
      const del = labelled(button(Decks.DELETE_CARD, () => {
        dk.confirm = `card:${card.id}`;
        dk.focusNext = `confirm-delete-card:${card.id}:cancel`;
        paintDecks();
      }, { live: true, danger: true }), Decks.DELETE_CARD, card.front);
      del.dataset.fkey = `delete-card:${card.id}`;
      actions.append(edit, del);
      item.append(actions);
      if (dk.confirm === `card:${card.id}`) {
        item.append(confirmBox(() => cardAct(deck.id, card.id, "delete"), `confirm-delete-card:${card.id}`));
      }
    }
    box.append(item);
  }
  return box;
}

function paintDecks() {
  const box = dom.decksBody;
  if (!box) return;
  const focusKey = dk.focusNext || fkeyBefore(box, dk);
  dk.focusNext = "";
  const parts = [];
  const view = dk.view;
  if (dk.error) {
    const err = el("p", "empty failed", dk.error);
    err.setAttribute("role", "alert");
    parts.push(err);
  }
  if (dk.review && view && !view.hidden) {
    const wrap = el("div", "");
    paintReview(wrap);
    parts.push(wrap);
    box.replaceChildren(...parts);
    fkeyAfter(box, focusKey);
    return;
  }
  if (!view) {
    if (!dk.error) parts.push(el("p", "note", Decks.LOADING));
    box.replaceChildren(...parts);
    return;
  }
  const top = Decks.sectionTop(view);
  if (!view.available) parts.push(el("p", "empty failed", view.why || Decks.MISSING));
  const ready = el("div", "goal-block");
  ready.append(el("h3", "subhead", Decks.CARDS_READY_HEADING));
  if (top.line) ready.append(el("p", "", top.line));
  const nextLine = Decks.nextReadyLine(view.nextReadyDay);
  if (nextLine && view.ready === 0) ready.append(el("p", "note", nextLine));
  if (top.empty) ready.append(el("p", "empty", Decks.EMPTY_STATE));
  // One review over every deck (the phone has the same button).
  if (view.available && !view.hidden && view.ready > 0) {
    const all = labelled(button(Decks.REVIEW, () => startReview("")), Decks.REVIEW_ALL, "");
    all.dataset.fkey = "review-all";
    if (!Decks.canReviewAll(view)) all.disabled = true;
    const allRow = el("div", "goal-actions");
    allRow.append(all);
    ready.append(allRow);
  }
  parts.push(ready);
  // New cards a day: a number from 0 to the PC's limit.
  const perDay = el("div", "goal-block");
  const perLabel = el("label", "quiz-lab", Decks.NEW_PER_DAY_LABEL);
  perLabel.htmlFor = "decks-per-day";
  const per = document.createElement("input");
  per.type = "number";
  per.id = "decks-per-day";
  per.className = "field deck-per-day";
  per.min = "0";
  per.max = String(view.limits.newPerDay);
  per.step = "1";
  per.value = String(view.newPerDay);
  per.dataset.fkey = "per-day";
  liveButtons.add(per);
  syncLiveButton(per);
  per.addEventListener("change", () => setNewPerDay(per.value, per));
  perDay.append(perLabel, per);
  parts.push(perDay);
  if (view.available && view.decks.length) {
    const list = el("div", "");
    for (const deck of view.decks) list.append(deckRow(deck, view));
    parts.push(list);
    // Each row counts what that deck alone would offer today; the day's new
    // cards are shared, so the rows can add up to more than the total above.
    if (Decks.perDeckNoteShown(view)) parts.push(el("p", "note", Decks.PER_DECK_NOTE));
  }
  if (view.hidden) {
    parts.push(el("p", "note", Decks.REVIEW_HIDDEN));
    parts.push(hiddenNode(0, "words"));
  }
  // A new deck: an empty one, named here.
  if (view.available) {
    const add = el("div", "goal-actions");
    if (dk.adding) {
      parts.push(nameForm("", (value) => addDeck(value), () => {
        dk.adding = false;
        paintDecks();
      }, "new-deck"));
    } else {
      const b = button(Decks.NEW_DECK, () => {
        dk.adding = true;
        dk.focusNext = "new-deck";
        paintDecks();
      }, { live: true });
      b.dataset.fkey = "new-deck-open";
      if (view.decks.length >= view.limits.decks) b.disabled = true;
      add.append(b);
      parts.push(add);
    }
  }
  box.replaceChildren(...parts);
  fkeyAfter(box, focusKey);
}

function renderDecks() {
  if (dom.decksIntro) dom.decksIntro.textContent = Decks.DECKS_INTRO;
  paintDecks();
  if (IS_TAURI && !dk.loading && Date.now() - dk.at > DECKS_READ_MS) loadDecks();
}

/** The private lists were turned on or off, or a Show ran out: read again. */
function rereadDecks() {
  dk.at = 0;
  if (state.view === "work") loadDecks();
}

trackFkeys(dom.decksBody, dk);
trackFkeys(dom.quizRun, qz);

// Private answers turned on or off, or a Show ran out: read it again - Rust
// decides whether the words come back.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadSchedule = () => {
    upL.at = 0;
    wid.at = 0;
    if (state.view === "work") {
      loadComingUp();
      loadWidgets();
    }
  };
  TAURI.event.listen("security-changed", rereadSchedule);
  TAURI.event.listen("private-hidden", rereadSchedule);
  // Goals hides its words the same way (brain/goals.rs redact_goals).
  const rereadGoals = () => {
    gl.measuresAt = 0;
    gl.at = 0;
    if (state.view === "work") loadGoals();
  };
  TAURI.event.listen("security-changed", rereadGoals);
  TAURI.event.listen("private-hidden", rereadGoals);
  // A quiz's questions and marks are hidden the same way (brain/quiz.rs).
  TAURI.event.listen("security-changed", rereadQuiz);
  TAURI.event.listen("private-hidden", rereadQuiz);
  // Deck names and card words are hidden the same way (brain/decks.rs).
  TAURI.event.listen("security-changed", rereadDecks);
  TAURI.event.listen("private-hidden", rereadDecks);
  // The deep questions are hidden with the lists too (commands.rs get_deep).
  const rereadDeep = () => {
    deep.at = 0;
    if (state.view === "memory") loadDeep();
  };
  TAURI.event.listen("security-changed", rereadDeep);
  TAURI.event.listen("private-hidden", rereadDeep);
  // And what a focus session is on (brain/focus.rs hide_intent).
  const rereadFocus = () => {
    fx.at = 0;
    if (state.view === "work") loadFocus();
  };
  TAURI.event.listen("security-changed", rereadFocus);
  TAURI.event.listen("private-hidden", rereadFocus);
}

/* ==========================================================================
   Today (the owner's choice of 2026-09-28; JARVIS-API.md section 82;
   today.js).

   The owner's own cards that show today (jobs of kind "today" on the one
   scheduler, from the Coming up read) and the parts of the latest briefing
   made today (from the Morning briefing read). Nothing new is read here.
   Delete is ONE card; Add is one card - both held on a stale link, neither
   raises a card. While the private lists are hidden, Rust already took the
   words out of both reads.
   ========================================================================== */

function todayDays() {
  const boxes = dom.todayDays ? [...dom.todayDays.querySelectorAll("input[type=checkbox]")] : [];
  return boxes.filter((b) => b.checked).map((b) => Number(b.value));
}

async function addToday() {
  const args = todayAddArgs(dom.todayText && dom.todayText.value,
    dom.todayAt && dom.todayAt.value, todayDays());
  if (args.error) {
    toast(args.error, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("brain_schedule_add_today", args);
    if (out && out.ok === false) {
      toast(String(out.error || "Refused."), "bad");
    } else {
      toast(String((out && out.said) || "Done."), "ok");
      if (dom.todayText) dom.todayText.value = "";
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

function todayRow(card) {
  const item = row({
    tag: TODAY_TAG,
    state: card.today === "showing" ? "ok" : "",
    title: todayCardTitle(card),
    meta: [todayCardMeta(card)],
    actions: [button(TODAY_DELETE_LABEL, () => scheduleAct(card, "delete"),
      { live: true, danger: true })],
  });
  item.dataset.id = card.id;
  return item;
}

function paintToday() {
  const box = dom.today;
  if (!box) return;
  const out = [];
  const v = upL.view;
  if (!v) {
    out.push(el("p", "empty", upL.error ? `Could not read Today: ${upL.error}` : "Reading…"));
  } else if (!v.available) {
    out.push(el("p", "empty", v.why || TODAY_MISSING));
  } else {
    const { showing, later } = todayCards(cardsOf(v));
    const list = el("div", "rows");
    for (const c of showing) list.append(todayRow(c));
    out.push(showing.length ? list : el("p", "empty", TODAY_EMPTY));
    if (later.length) {
      out.push(el("h3", "subhead", TODAY_LATER_TITLE));
      const rest = el("div", "rows");
      for (const c of later) rest.append(todayRow(c));
      out.push(rest);
    }
    if (v.hidden) out.push(hiddenNode(0, "words"));
  }
  if (dom.todayForm) dom.todayForm.hidden = Boolean(v && !v.available);
  // The briefing's own parts, from the latest one made today - never a new read.
  const bv = brief.view;
  if (bv && bv.available) {
    out.push(el("h3", "subhead", TODAY_FROM_BRIEFING));
    const parts = briefingCards(bv);
    if (!parts) {
      out.push(el("p", "empty", NO_BRIEFING_TODAY));
    } else {
      const list = el("div", "rows");
      for (const s of parts) {
        list.append(row({
          tag: s.title,
          state: s.state === "ok" ? "ok" : s.state === "empty" ? "" : "warn",
          title: s.summary,
          meta: s.items,
        }));
      }
      out.push(list);
    }
  }
  box.replaceChildren(...out);
}

if (dom.todayForm) {
  dom.todayForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addToday();
  });
}
if (dom.todayAdd) {
  liveButtons.add(dom.todayAdd);
  syncLiveButton(dom.todayAdd);
}

/* ==========================================================================
   Morning briefing (the owner's decisions of 2026-09-25; JARVIS-API.md
   section 22; briefing.js).

   The latest briefing, read through its own command (brain/briefing.rs), so
   while the private lists are hidden Rust takes every line out and only the
   counts reach this page. "Brief me now" only READS - the PC puts one
   together without the model - so, like every read, it is not held on a
   stale link. When it arrives each morning is set in Settings. The
   `schedule` event with kind "briefing" (ids only) reads it again; the
   toast is Rust's (toast_ready), with the fixed words only.
   ========================================================================== */

const brief = { view: null, error: "", loading: false, at: 0, asking: false, missedAsking: false };
const BRIEFING_READ_MS = 15000;

async function loadBriefing() {
  if (!IS_TAURI || brief.loading) return;
  brief.loading = true;
  try {
    brief.view = readBriefing(await invoke("brain_briefing"));
    brief.error = "";
  } catch (error) {
    brief.error = errorText(error);
  } finally {
    brief.loading = false;
    brief.at = Date.now();
  }
  if (state.view === "work") paintBriefing();
}

/**
 * "What did I miss?": the briefing's builder since the owner last talked to
 * Jarvis. A read, like "Brief me now" - not held on a stale link. Shown in
 * place of the briefing until the next read; the PC keeps nothing of it.
 */
async function briefMissed() {
  if (brief.asking) return;
  brief.asking = true;
  brief.missedAsking = true;
  paintBriefing();
  try {
    const v = readMissed(await invoke("brain_briefing_now", { missed: true }));
    if (v) {
      brief.view = { ...(brief.view || v), ...v, setups: (brief.view && brief.view.setups) || v.setups };
      brief.error = "";
    } else {
      toast(MISSED_MISSING, "bad");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    brief.asking = false;
    brief.missedAsking = false;
    brief.at = Date.now();
  }
  paintBriefing();
}

async function briefNow() {
  if (brief.asking) return;
  brief.asking = true;
  paintBriefing();
  try {
    brief.view = readBriefing(await invoke("brain_briefing_now"));
    brief.error = "";
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    brief.asking = false;
    brief.at = Date.now();
  }
  paintBriefing();
}

function paintBriefing() {
  paintToday();
  const box = dom.briefing;
  if (!box) return;
  if (dom.briefingNow) {
    dom.briefingNow.disabled = brief.asking;
    dom.briefingNow.textContent = brief.asking && !brief.missedAsking ? BRIEFING_NOW_BUSY
      : BRIEFING_NOW_LABEL;
  }
  if (dom.briefingMissed) {
    dom.briefingMissed.disabled = brief.asking;
    dom.briefingMissed.textContent = brief.missedAsking ? MISSED_BUSY : MISSED_LABEL;
  }
  const v = brief.view;
  if (!v) {
    const line = el("p", "empty", brief.error ? `Could not read the briefing: ${brief.error}` : "Reading…");
    if (brief.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadBriefing));
    }
    box.replaceChildren(line);
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why));
    if (dom.briefingNow) dom.briefingNow.hidden = true;
    if (dom.briefingMissed) dom.briefingMissed.hidden = true;
    return;
  }
  if (dom.briefingNow) dom.briefingNow.hidden = false;
  if (dom.briefingMissed) dom.briefingMissed.hidden = false;
  const b = v.briefing;
  const out = [];
  if (v.building || (brief.asking && !brief.missedAsking)) out.push(el("p", "empty", BRIEFING_BUILDING));
  if (!b) {
    if (!v.building && !brief.asking) out.push(el("p", "empty", BRIEFING_EMPTY));
    box.replaceChildren(...out);
    return;
  }
  out.push(el("p", "briefing-heading", b.heading));
  const late = lateLine(b);
  if (late) out.push(el("p", "empty", late));
  const list = el("div", "rows");
  for (const s of b.sections) {
    list.append(row({
      tag: s.title,
      state: s.state === "ok" ? "ok" : s.state === "empty" ? "" : "warn",
      title: s.summary,
      meta: b.hidden ? [] : s.items,
    }));
  }
  out.push(list);
  const missed = b.source === "missed";
  // "What did I miss?" fetches nothing from the internet and is not kept.
  // The last line is the PC's own (the weather from Home Assistant, or not).
  if (!missed) out.push(el("p", "note", briefingOutsideLine(b)));
  for (const n of b.notIncluded) out.push(el("p", "note", n));
  if (b.hidden) out.push(hiddenNode(0, "lines"));
  out.push(el("p", "note", missed ? MISSED_DETAIL : BRIEFING_KEPT));
  box.replaceChildren(...out);
}

function renderBriefing() {
  paintBriefing();
  if (IS_TAURI && !brief.loading && Date.now() - brief.at > BRIEFING_READ_MS) loadBriefing();
}

if (dom.briefingNow) dom.briefingNow.addEventListener("click", briefNow);
if (dom.briefingMissed) dom.briefingMissed.addEventListener("click", briefMissed);

// Hiding turned on or off, or a Show ran out: read it again - Rust decides
// whether the lines come back.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadBriefing = () => {
    brief.at = 0;
    if (state.view === "work") loadBriefing();
  };
  TAURI.event.listen("security-changed", rereadBriefing);
  TAURI.event.listen("private-hidden", rereadBriefing);
}

function renderJobs() {
  const body = state.data.jobs || {};
  const why = unavailable("jobs");
  if (why) return rows(dom.jobs, [], null, whyNode("jobs"));
  const list = Array.isArray(body.jobs) ? body.jobs : [];

  rows(
    dom.jobs,
    list,
    (j) => {
      const jobState = String(j.state || "queued");
      const live = jobState === "running" || jobState === "queued";
      // Either set of names: this window's (caps, tainted, created) or the
      // phone's (capabilities, private, progress). jarvis_jobs.py is only on
      // the owner's PC, so both apps read both.
      const caps = Array.isArray(j.caps) && j.caps.length ? j.caps
        : Array.isArray(j.capabilities) ? j.capabilities : [];
      const progress = typeof j.progress === "number" ? `${Math.round(j.progress * 100)}% done` : "";
      return row({
        tag: jobState,
        state: jobState,
        title: String(j.label || j.handler || j.id || "(job)"),
        meta: [
          // The frozen capability set, shown because it is the promise: it was
          // fixed when the job was created and it cannot grow.
          caps.length ? `frozen capabilities: ${caps.join(", ")}` : "no capabilities",
          j.tainted ? "tainted — this job read private data and stays local" : "",
          j.private ? "private — the phone is not shown what this is working on" : "",
          [ago(j.created), j.result_summary || j.error || "", progress].filter(Boolean).join(" · "),
        ],
        actions: live
          ? [
              button(
                "Cancel",
                async () => {
                  if (
                    !confirm(
                      `Cancel "${j.label || j.id}"?\n\n` +
                        "Cancelling works mid-step and a cancelled job is not " +
                        "resumable — it starts again from the beginning or not at all."
                    )
                  ) {
                    return;
                  }
                  try {
                    await invoke("brain_cancel_job", { id: String(j.id) });
                    toast("Cancelled.", "ok");
                    await load(["jobs"], { quiet: true });
                    render("work");
                  } catch (error) {
                    toast(String((error && error.message) || error), "bad");
                  }
                },
                { danger: true }
              ),
            ]
          : [],
      });
    },
    "No background jobs."
  );
}

function renderUndo() {
  const body = state.data.undo || {};
  const why = unavailable("undo");
  if (why) return rows(dom.undo, [], null, whyNode("undo"));
  const shelf = Array.isArray(body.shelf) ? body.shelf : [];

  rows(
    dom.undo,
    shelf,
    (e) => {
      // Either set of names: this window's (action/kind, revertible, ts) or
      // the phone's (label/what, reversible, at_ms). jarvis_undo.py is only on
      // the owner's PC, so both apps read both.
      const revertible = e.revertible === true || e.reversible === true;
      const when = e.ts ?? (Number(e.at_ms) > 0 ? Number(e.at_ms) / 1000 : undefined);
      const actions = [];
      if (revertible) {
        actions.push(
          button("Put it back", async () => {
            try {
              await invoke("brain_revert_undo", { id: String(e.id) });
              toast("Reverted.", "ok");
              await load(["undo"], { quiet: true });
              render("work");
            } catch (error) {
              toast(String((error && error.message) || error), "bad");
            }
          })
        );
      }
      // A hold is a message inside its send window: cancellable now, gone in a
      // moment, and never unsendable afterwards.
      if (e.category === "hold" && e.detail && e.detail.handle) {
        actions.push(
          button(
            "Stop sending",
            async () => {
              try {
                await invoke("brain_cancel_hold", { handle: String(e.detail.handle) });
                toast("Stopped before it went.", "ok");
                await load(["undo"], { quiet: true });
                render("work");
              } catch (error) {
                const message = String((error && error.message) || error);
                toast(
                  /409/.test(message)
                    ? "That one has already gone — there is no unsend."
                    : message,
                  "bad"
                );
              }
            },
            { danger: true }
          )
        );
      }
      // A hold inside its send window is the one entry that is neither
      // revertible nor final: it has not happened yet. Tagging it "final" next
      // to a live "Stop sending" button made the tag contradict the action.
      const holding = e.category === "hold" && e.detail && e.detail.handle;
      return row({
        tag: holding ? "holding" : revertible ? "revertible" : "final",
        state: holding ? "warn" : revertible ? "ok" : "bad",
        title: String(e.action || e.kind || e.label || e.what || "(action)"),
        meta: [
          e.target || "",
          holding
            ? e.reason || "still inside its send window — it can still be stopped"
            : revertible
              ? ""
              : e.reason || "cannot be undone",
          [ago(when), e.before_bytes ? `${bytes(e.before_bytes)} held` : ""]
            .filter(Boolean)
            .join(" · "),
        ],
        actions,
      });
    },
    "Nothing on the shelf."
  );
}

/**
 * "Activity" - past approvals, read-only (ease-of-use audit, 2026-09-27,
 * row 11): title, Approved/Denied/Timed out, when, and which device. Next
 * to the Undo shelf, on purpose, and never sharing a list with a WAITING
 * card - this reads `gate_history`, its own section (brain/routes.rs), which
 * is the SAME `/api/pending` the stream already polls for the live queue,
 * asked for again so this pane can show the `history` half of that answer -
 * the half the stream's own polling loop reads and discards, because an
 * already-decided row must never be mistaken for one still waiting.
 *
 * What each row shows, and what could and could not be confirmed against
 * this repository (`jarvis_gate.py` itself is not in it - see the module
 * note on this file's `history` handling, and JARVIS-API.md section 3):
 *
 * - title: `notice.title`, else the same action-name fallback a live card
 *   with no notice uses ([fallbackTitle], card-words.js) - confirmed safe
 *   for a lock screen either way, since neither reads `detail` or `prompt`.
 * - outcome: the row's `state` (confirmed values: `approved`, `denied`,
 *   `expired` - backend/test_gate_outcome.py's docstring) or `outcome`
 *   (`timed_out`, the Verdict-level name for the same event); anything else
 *   reads as "Not reported" rather than a guess.
 * - device: `decided_by` (a real column - backend/gate-outcome.patch reads
 *   `row["decided_by"]`), else `device`, else `by`; ASSUMED to be "this PC"
 *   or "another device", the two words every other approval-adjacent route
 *   in this codebase already sends (focus.patch, power-mode.patch,
 *   task-control.patch, note-capture.patch) - not confirmed for the gate's
 *   own history rows. A row with none of the three says nothing about a
 *   device rather than inventing one.
 */
function renderActivity() {
  const body = state.data.gate_history || {};
  const why = unavailable("gate_history");
  if (why) return rows(dom.activity, [], null, whyNode("gate_history"));
  const history = Array.isArray(body.history) ? body.history : [];
  const sorted = [...history].sort((a, b) => activityWhen(b) - activityWhen(a));

  const filterDecision = state.activityFilterDecision || "all";
  const filtered = sorted.filter((h) => {
    if (filterDecision === "all") return true;
    const outcome = activityOutcome(h).toLowerCase().replace(" ", "_");
    return outcome === filterDecision;
  });

  if (dom.activityFilters) {
    const filterRow = el("div", "activity-filters", "");
    filterRow.style.display = "flex";
    filterRow.style.gap = "8px";
    filterRow.style.marginBottom = "8px";
    const decisions = [
      { id: "all", label: "All" },
      { id: "approved", label: "Approved" },
      { id: "denied", label: "Denied" },
      { id: "timed_out", label: "Timed out" },
    ];
    for (const d of decisions) {
      const btn = el("button", "btn btn-subtle", d.label);
      if (filterDecision === d.id) {
        btn.style.fontWeight = "bold";
        btn.dataset.active = "true";
      }
      btn.onclick = () => {
        state.activityFilterDecision = d.id;
        renderActivity();
      };
      filterRow.append(btn);
    }
    dom.activityFilters.replaceChildren(filterRow);
  }

  rows(
    dom.activity,
    filtered,
    (h) => {
      const outcome = activityOutcome(h);
      const device = String(h.decided_by || h.device || h.by || "");
      const when = activityWhen(h);
      const summary = (h.notice && h.notice.summary) || h.summary || h.detail_one_line || h.what || "";
      const meta = [outcome];
      if (summary) meta.push(summary);
      meta.push([device, when ? ago(when) : ""].filter(Boolean).join(" · "));
      return row({
        tag: outcome.toLowerCase(),
        state: outcome === "Approved" ? "ok" : outcome === "Denied" ? "bad" : "warn",
        title: (h.notice && h.notice.title) || fallbackTitle(h.action),
        meta: meta,
      });
    },
    "Nothing decided yet."
  );
}

/** `approved` / `denied` / `expired` (approvals.state) or `timed_out`
 * (Verdict.outcome) - both accepted, since which one `history()` rows
 * actually carry could not be confirmed. Anything else: "Not reported",
 * never a guess. */
function activityOutcome(h) {
  const state = String(h.state || h.outcome || "").toLowerCase();
  if (state === "approved") return "Approved";
  if (state === "denied") return "Denied";
  if (state === "expired" || state === "timed_out") return "Timed out";
  return "Not reported";
}

/** When to show: the decision time if the row has one, else when it was raised. */
function activityWhen(h) {
  const decided = Number(h.decided_at);
  if (Number.isFinite(decided) && decided > 0) return decided;
  const created = Number(h.created);
  return Number.isFinite(created) && created > 0 ? created : 0;
}

/* ==========================================================================
   Trust
   ========================================================================== */

function renderContentRisk() {
  const body = state.data.content_risk || {};
  const why = unavailable("content_risk");
  dom.contentRisk.replaceChildren();
  if (why) return dom.contentRisk.append(whyNode("content_risk"));

  const rush = body.rush;
  const banner = el(
    "div",
    "row-item",
    ""
  );
  banner.replaceChildren();
  const tag = el("span", "row-tag", rush ? "latched" : "clear");
  tag.dataset.state = rush ? "bad" : "ok";
  banner.append(tag);
  const main = el("div", "row-main");
  if (rush) {
    main.append(
      el(
        "span",
        "row-title",
        "A rush latch is active — outside text tried to hurry a decision."
      )
    );
    // The attacker's own words, quoted, because showing them is the point.
    const said = rush.phrase || rush.quote; // either name, as in the rush strip
    if (said) main.append(el("span", "row-meta", `“${said}”`));
    if (rush.source) main.append(el("span", "row-meta", `from ${rush.source}`));
    main.append(
      el(
        "span",
        "row-meta",
        "It expires on its own. There is deliberately no control here that clears it."
      )
    );
  } else {
    main.append(el("span", "row-title", "No rush latch active."));
  }
  banner.append(main, el("div", "row-actions"));
  const wrap = el("div", "rows");
  wrap.append(banner);
  dom.contentRisk.append(wrap);

  const pins = Array.isArray(body.pins) ? body.pins : [];
  dom.contentRisk.append(el("h3", "inspector-sub", "Pinned text"));
  const pinBox = el("div");
  rows(
    pinBox,
    pins,
    (p) =>
      row({
        tag: "pinned",
        state: "ok",
        title: String(p.name || p.source || "(pinned)"),
        meta: [p.kind || "", p.at ? ago(p.at) : "", p.digest ? `digest ${String(p.digest).slice(0, 12)}` : ""],
        actions: [],
      }),
    "Nothing pinned. A skill or MCP tool description is pinned when a person has read its full current text."
  );
  dom.contentRisk.append(pinBox);
}

function renderLedger() {
  const body = state.data.ledger || {};
  const why = unavailable("ledger");
  dom.ledger.replaceChildren();
  if (why) return dom.ledger.append(whyNode("ledger"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  add("Entries", body.entries);
  add("Head", body.head ? String(body.head).slice(0, 20) + "…" : "");
  add("Head sequence", body.head_seq);
  add("Last entry", body.head_ts ? ago(body.head_ts) : "");
  add("With payload", body.with_payload);
  add("Metadata only", body.no_payload);
  add("Redacted", body.redacted);
  add("Expired", body.expired);
  dom.ledger.append(dl);

  const anchors = Array.isArray(body.anchors) ? body.anchors : [];
  dom.ledger.append(el("h3", "inspector-sub", "Anchors"));
  const box = el("div");
  rows(
    box,
    anchors.slice(-8).reverse(),
    (a) =>
      row({
        tag: a.mac_ok ? "verified" : "unverified",
        state: a.mac_ok ? "ok" : "bad",
        title: `seq ${a.seq ?? "—"}`,
        meta: [a.hash ? String(a.hash).slice(0, 24) + "…" : "", a.ts ? ago(a.ts) : ""],
        actions: [],
      }),
    "No anchors written yet."
  );
  dom.ledger.append(box);
}

/* ==========================================================================
   Watch
   ========================================================================== */

function renderWatch() {
  const body = state.data.watch || {};
  const why = unavailable("watch");
  if (why) return rows(dom.watch, [], null, whyNode("watch"));

  const head = el("p", "note");
  head.textContent = [
    `${body.topics ?? 0} topics · ${body.tracking ?? 0} repositories known`,
    body.rate_limit || "",
  ]
    .filter(Boolean)
    .join(" · ");

  const list = Array.isArray(body.list) ? body.list : [];
  const box = el("div");
  rows(
    box,
    list,
    (t) =>
      row({
        tag: t.error ? "error" : "watching",
        state: t.error ? "bad" : "ok",
        title: String(t.name || ""),
        meta: [
          t.query && t.query !== t.name ? `query: ${t.query}` : "",
          t.error ? String(t.error) : "",
          [t.checked ? `checked ${ago(t.checked)}` : "never checked",
           t.notify ? "notify on" : "notify off"].join(" · "),
        ],
        actions: [
          button(
            "Forget",
            async () => {
              if (
                !confirm(
                  `Forget "${t.name}"?\n\nEverything remembered about this topic ` +
                    "goes with it — which repositories were already seen, and what " +
                    "was already reported. Adding it back starts from nothing."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_watch_remove", { name: String(t.name) });
                toast(`Forgot ${t.name}.`, "ok");
                await load(["watch", "watch_report"], { quiet: true });
                render("watch");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      }),
    "No topics watched."
  );
  dom.watch.replaceChildren(head, box);
}

function renderWatchReport() {
  const body = state.data.watch_report || {};
  const why = unavailable("watch_report");
  if (why) return rows(dom.watchReport, [], null, whyNode("watch_report"));
  const findings = Array.isArray(body.findings)
    ? body.findings
    : Array.isArray(body.items)
      ? body.items
      : [];

  dom.watchSeen.disabled = findings.length === 0;

  rows(
    dom.watchReport,
    findings,
    (f) => {
      // "none stated" means no permission, not "probably fine" — so an absent
      // licence is rendered as a warning, not as a blank.
      const licence = String(f.licence || f.license || "").trim();
      const stated = licence && !/^(none|unknown|null)$/i.test(licence);
      return row({
        tag: stated ? licence : "no licence",
        state: stated ? "ok" : "warn",
        title: String(f.full_name || f.name || "(repository)"),
        meta: [
          String(f.descr || f.description || ""),
          [
            f.stars !== undefined ? `★ ${f.stars}` : "",
            f.topic ? `topic: ${f.topic}` : "",
            f.archived ? "archived" : "",
            stated ? "" : "no licence stated - no permission to use it",
          ]
            .filter(Boolean)
            .join(" · "),
          f.note ? `scanner: ${f.note}` : "",
        ],
        actions: [],
      });
    },
    "Nothing new since you last marked the list read."
  );
}

/* ==========================================================================
   Live
   ========================================================================== */

function renderLive() {
  const link = currentLink();
  const attention = link.attention;

  // The same answer the tray paints, from the same function — including
  // `approval` and `standby`, which the arbiter's own `face_state` does not
  // compose because they are UI precedence rather than its business.
  const face = surfaceState(link);
  dom.nowFace.dataset.face = face;
  dom.nowActivity.textContent = face;
  dom.nowPower.textContent = link.connected
    ? `power: ${link.power}${link.powerSetBy ? ` · ${link.powerSetBy}` : ""}`
    : link.error || "offline";

  const status = state.data.status || {};
  dom.nowKv.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nowKv.append(el("dt", "", k), el("dd", "", v));
  };
  add("Model", status.model || status.current_model);
  add("Lane", status.lane || status.route);
  add("Approvals waiting", link.approvals);
  add("Stream", link.connected ? (link.stale ? "connected, stale" : "live") : "down");
  add("Last event", link.lastId || "");

  // The budget as pips, one per interruption. Spent ones go flat; when the
  // budget is blocked outright — Quiet, Standby, a locked session, muted — the
  // remaining pips go grey too, because "four left" is not true then.
  dom.budget.replaceChildren();
  if (attention.known) {
    const blocked = Boolean(attention.blockedBy);
    dom.budget.dataset.blocked = String(blocked);
    for (let i = 0; i < Math.max(attention.limit, 1); i++) {
      const pip = el("span", "pip");
      pip.dataset.spent = String(i < attention.spent);
      dom.budget.append(pip);
    }
    dom.budgetNote.textContent = blocked
      ? `Silent — ${attention.blockedBy}. ${attention.pending} waiting to be told.`
      : `${attention.remaining} of ${attention.limit} spoken interruptions left today · ` +
        `${attention.pending} waiting to be told`;
  } else {
    dom.budgetNote.textContent = "The interruption budget has not been read yet.";
  }
}

function pushTrace(frame) {
  const now = new Date();
  const time =
    String(now.getHours()).padStart(2, "0") +
    ":" +
    String(now.getMinutes()).padStart(2, "0") +
    ":" +
    String(now.getSeconds()).padStart(2, "0");

  const kind = String((frame && frame.kind) || "event");
  let body = "";
  const data = (frame && frame.data) || {};
  if (kind === "activity") {
    // Two shapes are in the wild: the state at the top level, and the rebuilt
    // bus's `note()` shape, `{key, value: {state, detail}}`. The detail is
    // what the tool loop announces ("Using calculator..."), so show it.
    const value = data.value && typeof data.value === "object" ? data.value : {};
    const state = String(data.state || value.state || "");
    const detail = String(data.detail || data.activity_detail || value.detail || "");
    body = detail ? `${state} · ${detail}` : state;
  } else if (kind === "step") body = stepText(data);
  else if (kind === "attention") {
    body = `remaining ${data.remaining ?? "?"} · pending ${data.pending ?? "?"}` +
      (data.banked ? " · banked" : "") +
      (data.blocked_by ? ` · ${data.blocked_by}` : "");
  } else if (kind === "approval") body = `${data.count ?? "?"} waiting`;
  else if (kind === "proposal") {
    // The extractor now runs on its own, after a conversation goes quiet, so
    // the review queue fills having asked nobody. Without this branch the
    // event landed in the generic `else` below and read as a raw id array —
    // a doorbell ringing into an empty room, which is the exact defect the
    // backend patch that added the event was written to fix elsewhere.
    //
    // Count only. The event deliberately carries no fact text (a proposal
    // quotes whatever produced it), so there is nothing here to render but
    // the number, and the memory pane is where you go to read them.
    const n = data.count ?? (Array.isArray(data.value) ? data.value.length : "?");
    body = n === 0 ? "review queue empty" : `${n} to review`;
  } else if (kind === "memory_saved") {
    // Automatic learning saved something: how many, never the words (the
    // event carries ids only - JARVIS-API.md section 19).
    const n = savedIds(data).length;
    body = rememberedLine(n) || "saved nothing";
  } else if (kind === "deep") {
    // The id and how it ended - never the question or the answer.
    body = `question ${String(data.id || "?")} ${String(data.state || "")}`.trim();
  } else if (kind === "live") {
    // Jarvis Live's session (jarvis_live.status(): fixed words and numbers,
    // never anything said), in one readable line rather than raw JSON (the
    // Live review, 2026-09-28).
    body = liveTraceLine(data);
  } else if (kind === "hello") {
    body = `resumed from ${data.resumed_from ?? 0}${data.stale ? " · STALE" : ""}`;
  } else {
    const value = data.value !== undefined ? data.value : data.title || data.key;
    body = value === undefined ? JSON.stringify(data).slice(0, 120) : String(value);
  }

  state.trace.push({ time, kind, body });
  // Bounded: this window can be left open for a day, and an unbounded list of
  // DOM nodes is a leak with a nice name.
  if (state.trace.length > 300) state.trace.splice(0, state.trace.length - 300);

  if (state.view !== "now") return;
  const li = el("li");
  li.append(
    el("span", "trace-time", time),
    el("span", "trace-kind", kind),
    el("span", "trace-body", body)
  );
  dom.trace.append(li);
  while (dom.trace.childElementCount > 300) dom.trace.firstElementChild.remove();
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

/** A `live` event (Jarvis Live's status) as one line. */
function liveTraceLine(s) {
  const d = s && typeof s === "object" ? s : {};
  if (d.on === true) {
    const where = d.device === "desktop" ? "this PC" : d.device === "phone" ? "the phone" : "a device";
    const parts = [`Jarvis Live on ${where}`];
    if (Number.isInteger(d.minutes_left)) parts.push(`${d.minutes_left} min left`);
    const why = d.muted ? d.muted_words : d.paused ? d.pause_words : d.hint_words;
    if (why) parts.push(String(why));
    return parts.join(" · ");
  }
  if (d.state === "ended") return `Jarvis Live ended${d.ended_words ? `: ${d.ended_words}` : ""}`;
  return "Jarvis Live off";
}

// stepText now lives in step-words.js, shared with the Jarvis bar
// (item 10, UI-AUDIT-2026-09-26.md).

function repaintTrace() {
  dom.trace.replaceChildren();
  for (const t of state.trace) {
    const li = el("li");
    li.append(
      el("span", "trace-time", t.time),
      el("span", "trace-kind", t.kind),
      el("span", "trace-body", t.body)
    );
    dom.trace.append(li);
  }
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

/* ==========================================================================
   The galaxy
   --------------------------------------------------------------------------
   A force-directed layout, simulated to a stop and then drawn statically.

   Two decisions worth stating. First, the layout runs for a bounded number of
   cooling ticks and then freezes: a graph that jiggles for ever is harder to
   read and burns a core on a window that may be left open all day. The
   assembly is visible while it settles, which is the one moment of spectacle
   this view gets.

   Second, repulsion uses a uniform grid rather than every-pair. The node count
   is set by how much the owner's memory store knows, not by anything the UI
   controls, so O(n²) is a cliff somebody eventually falls off.
   ========================================================================== */

/**
 * A group is a hue AND a form, because ten hues cannot encode ten categories.
 *
 * The old ten-colour map measured CIEDE2000 6.0 between `core` and `cluster`
 * in normal vision — under the visual spec's own "obviously different at arm's
 * length" line before any colour blindness — and 1.0 under deuteranopia, which
 * is the spec's own word for indistinguishable. High contrast gave the two the
 * same hex outright.
 *
 * Five hues each carry two groups, told apart by whether the node is a filled
 * disc or a hollow ring. The pairs are semantically adjacent, so a misread
 * costs the least: a pet mistaken for a person is a smaller error than a
 * person mistaken for a place. Form is not a theme concern — it is a fact
 * about what the group is — so it lives here and not in theme.css.
 *
 * Since 2026-09-28 the groups are the kinds of people and things
 * (galaxy-view.js); the same five hues and two forms, so every contrast and
 * colour-blindness check on them (themecheck.mjs, distinct.mjs) still holds.
 */
const GROUP_STYLE = {
  person: ["--node-h1", "disc"],
  pet: ["--node-h1", "ring"],
  place: ["--node-h2", "disc"],
  organisation: ["--node-h2", "ring"],
  project: ["--node-h3", "disc"],
  thing: ["--node-h3", "ring"],
  other: ["--node-h5", "ring"],
};

/** Unknown groups get the last hue as a ring, which reads as "other". */
function styleFor(group) {
  return GROUP_STYLE[group] || ["--node-h5", "ring"];
}

const view = { x: 0, y: 0, scale: 1 };
let sim = null;
let hovered = null;
let selected = null;
const hiddenGroups = new Set();
/** "Find a name": every match, and which one is shown (findInGalaxy). */
const galaxyFind = { hits: [], at: 0 };

/**
 * Node colours, cached.
 *
 * This is called once per node inside `draw()`, and `draw()` can run many times
 * per displayed frame. `getComputedStyle` per node per frame was a style query,
 * a string allocation and a trim for every dot on screen. The cache is cleared
 * whenever the theme changes and whenever a new graph is loaded, which are the
 * only two moments the answer can move.
 */
const colourCache = new Map();
function colourFor(group) {
  let hit = colourCache.get(group);
  if (hit !== undefined) return hit;
  const token = styleFor(group)[0];
  hit = getComputedStyle(dom.root).getPropertyValue(token).trim() || "#888";
  colourCache.set(group, hit);
  return hit;
}

/** Draws one node in its group's form. A ring is stroked, a disc is filled. */
function drawNode(ctx, x, y, r, group, colour) {
  if (styleFor(group)[1] === "ring") {
    // Stroked inside the radius so a ring and a disc of the same group read as
    // the same size — otherwise the ring looks like a bigger node.
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(1.4, r * 0.42);
    ctx.beginPath();
    ctx.arc(x, y, Math.max(1, r - ctx.lineWidth / 2), 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 1;
    return;
  }
  ctx.fillStyle = colour;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * Coalesces redraws onto the frame.
 *
 * `pointermove` fires at the mouse's polling rate — 125Hz typically, 1000Hz on
 * a gaming mouse — and every handler used to call `draw()` directly, so the
 * renderer could be asked to draw sixteen times per displayed frame. Every
 * input path goes through here instead.
 */
let drawQueued = false;
// The four theme tokens the canvas paints with. Cached because reading them
// is a forced style recalc and they change only when the theme does.
let _ink = null;
function themeInk() {
  if (_ink) return _ink;
  const css = getComputedStyle(dom.root);
  const edge = css.getPropertyValue("--edge").trim() || "rgba(140,165,190,0.22)";
  _ink = {
    edge,
    edgeActive: css.getPropertyValue("--edge-active").trim() || edge,
    text: css.getPropertyValue("--text").trim() || "#fff",
    faint: css.getPropertyValue("--text-faint").trim() || "#888",
  };
  return _ink;
}

function invalidate() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => {
    drawQueued = false;
    draw();
  });
}

/** An empty canvas with a sentence, and a button when there is one to press. */
function graphEmptyWith(words, action = null) {
  if (sim) cancelAnimationFrame(sim);
  sim = null;
  dom.graphEmpty.hidden = false;
  dom.graphEmptyText.textContent = words;
  dom.graphEmptyActions?.replaceChildren(...(action ? [action] : []));
  dom.graphStat.textContent = "—";
  dom.legend.replaceChildren();
  dom.inspector.hidden = true;
  galaxyPanel.clear();
  selected = null;
  state.graph = null;
  draw();
}

function renderGraph() {
  const why = unavailable("memory_entities");
  if (why) {
    graphEmptyWith(why);
    return;
  }
  const view = readEntities(state.data.memory_entities);
  if (view.hidden) {
    // "Windows Hello for memory lists and chat history": Rust took the
    // names out (lock/rules.rs); nothing of them reaches this page.
    const n = view.hiddenCount;
    graphEmptyWith(n
      ? `${n} ${n === 1 ? "name" : "names"}, hidden until Windows Hello confirms it is you.`
      : "Hidden until Windows Hello confirms it is you.",
      button("Show", revealPrivate,
        { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows the names." }));
    return;
  }
  if (!view.available) {
    graphEmptyWith("This PC's Jarvis cannot list the people and things in its memory yet. " +
      "Run apply-patches.ps1 on the PC to update it.");
    return;
  }
  const { nodes, links } = buildEntityGraph(view);
  if (!nodes.length) {
    graphEmptyWith("No people or things yet. They appear here as Jarvis saves facts that name them.");
    return;
  }
  dom.graphEmpty.hidden = true;
  dom.graphEmptyActions?.replaceChildren();

  const byId = new Map();
  const N = nodes.map((n, i) => {
    // A deterministic ring start rather than random: the same graph lays out
    // the same way twice, so the picture the owner learns stays learnable.
    const a = (i / nodes.length) * Math.PI * 2;
    const r = 40 + (i % 9) * 26;
    const node = {
      id: n.id,
      entityId: n.entityId,
      label: n.label,
      group: n.group,
      // Dot size: how many saved facts name it (radiusOf).
      weight: Math.max(1, n.weight),
      facts: n.weight,
      // Newest first: "Facts behind this dot" reads their words by id.
      factIds: n.factIds,
      aliases: n.aliases,
      also: n.also,
      // Most facts first: the names worth labelling at a glance.
      rank: i,
      x: Math.cos(a) * r,
      y: Math.sin(a) * r,
      vx: 0,
      vy: 0,
      deg: 0,
    };
    byId.set(node.id, node);
    return node;
  });
  const L = [];
  for (const l of links) {
    const s = byId.get(l.source);
    const t = byId.get(l.target);
    if (!s || !t || s === t) continue;
    s.deg++;
    t.deg++;
    L.push({ s, t, shared: l.shared, kind: sharedWords(l.shared) });
  }

  colourCache.clear();
  // Same node set as last time? Keep the settled positions. Clicking Galaxy
  // used to replay 1.3s of assembly on every visit, which is charming once and
  // an obstacle by the tenth time. Refresh still re-lays it out, so the
  // spectacle is one click away and never imposed.
  const signature = nodes.map((n) => n.id).join("\u0000");
  const settled = state.graph && state.graph.signature === signature
    ? new Map(state.graph.nodes.map((n) => [n.id, n]))
    : null;
  if (settled) {
    for (const n of N) {
      const was = settled.get(n.id);
      if (was) { n.x = was.x; n.y = was.y; }
    }
  }

  state.graph = { nodes: N, links: L, byId, signature };
  selected = null;
  dom.inspector.hidden = true;
  galaxyPanel.clear();
  buildLegend();
  dom.graphStat.textContent =
    `${N.length} ${N.length === 1 ? "name" : "names"} · ${L.length} ${L.length === 1 ? "link" : "links"}`;
  // A search typed before this read finds its matches in the new picture.
  galaxyFind.hits = [];
  if (dom.graphSearch.value.trim()) findInGalaxy({ keepAt: true });
  if (settled) {
    fitCanvas();
    draw();
  } else {
    startLayout();
  }
}

function countGroups(nodes) {
  const counts = {};
  for (const n of nodes) counts[n.group] = (counts[n.group] || 0) + 1;
  return counts;
}

function buildLegend() {
  const present = countGroups(state.graph.nodes);
  dom.legend.replaceChildren();
  const order = Object.keys(GROUP_STYLE);
  for (const group of Object.keys(present).sort((a, b) => order.indexOf(a) - order.indexOf(b))) {
    const item = el("button", "legend-item");
    item.type = "button";
    item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
    const sw = el("span", "legend-swatch");
    const [, form] = styleFor(group);
    sw.dataset.form = form;
    if (form === "ring") {
      sw.style.background = "transparent";
      sw.style.borderColor = colourFor(group);
    } else {
      sw.style.background = colourFor(group);
      sw.style.borderColor = "transparent";
    }
    item.append(sw, el("span", "", groupWords(group)), el("span", "legend-count", present[group]));
    item.title = `Show or hide the ${groupWords(group)} on the picture.`;
    item.addEventListener("click", () => {
      if (hiddenGroups.has(group)) hiddenGroups.delete(group);
      else hiddenGroups.add(group);
      item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
      draw();
    });
    dom.legend.append(item);
  }
}

function startLayout() {
  if (sim) cancelAnimationFrame(sim);
  const g = state.graph;
  if (!g) return;

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const total = 320;
  // Ticks are driven by elapsed time, not by frames. Four ticks per frame meant
  // 80 frames of assembly: 1.33s at 60Hz, 0.67s at 120Hz, 0.49s at 165Hz — the
  // animation ran at whatever speed the monitor happened to be. The visual spec
  // already wrote this bug report for the reactor (`state_transforms.phase`:
  // never multiply the clock by a rate, integrate it) and this is the
  // frame-count version of the same mistake.
  const SIM_HZ = 240;
  let tick = 0;
  let carried = 0;
  let last = 0;

  // Reduced motion means no visible ASSEMBLY. It does not mean no time.
  //
  // This used to run all 320 ticks in one synchronous `while` loop, which is
  // the same total work the animated path does — delivered as a frozen window.
  // The node count is set by how much the owner's memory store knows, so on a
  // large graph that is a multi-second hang, and the person who gets it is the
  // one who asked for less motion because motion makes them unwell.
  //
  // Same chunking, same yielding, nothing drawn until it has settled.
  if (reduced) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = "Laying out the graph…";
    const slice = () => {
      const until = performance.now() + 8;
      while (tick < total && performance.now() < until) {
        step(g, 1 - tick / total);
        tick++;
      }
      if (tick < total) {
        sim = requestAnimationFrame(slice);
        return;
      }
      sim = null;
      dom.graphEmpty.hidden = true;
      fitToContent();
      draw();
    };
    sim = requestAnimationFrame(slice);
    return;
  }

  const frame = (now) => {
    if (!last) last = now;
    // Clamped: a background tab or a stalled frame must not deliver a hundred
    // ticks at once and detonate the layout.
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    carried += dt * SIM_HZ;
    const steps = Math.min(8, Math.floor(carried));
    carried -= steps;
    for (let i = 0; i < steps && tick < total; i++, tick++) {
      step(g, 1 - tick / total);
    }

    // The camera follows the whole way and eases in, rather than tracking for
    // twelve frames and then teleporting to the final fit. `k` is derived from
    // dt so the glide is the same on any refresh rate.
    fitToContent({ ease: 1 - Math.exp(-dt / 0.35) });
    draw();

    if (tick < total) sim = requestAnimationFrame(frame);
    else {
      sim = null;
      fitToContent();
      // Labels are only placed once the nodes have stopped. Re-running the
      // collision test every frame made names flicker in and out as the
      // packing resolved differently each time — the ugliest part of the
      // assembly, and removing it is also cheaper.
      draw();
    }
  };
  sim = requestAnimationFrame(frame);
}

/** One cooling tick: repulsion by grid, springs along links, pull to centre. */
function step(g, heat) {
  const nodes = g.nodes;
  // Tuned away from a lattice. The first pass used uniform repulsion with a
  // short cutoff and a uniform spring rest length, and uniform forces reach a
  // uniform equilibrium: 165 nodes settled into a visible grid, which reads as
  // a diagram of nothing.
  //
  // Two changes break it. Repulsion is longer-range and weaker per pair, so it
  // separates whole clusters rather than spacing individual nodes; and the
  // springs are four times stronger, so anything linked clumps hard. What you
  // see then is the shape of the connections, which is the only thing this
  // view is for.
  const REPEL = 2600;
  // CELL must be at least the reach radius, or the 3x3 neighbourhood below
  // does not contain everything the force is supposed to touch. It used to be
  // 130 against a 286px reach, so repulsion was silently truncated AND
  // direction-dependent: whether a node 200px east pushed you depended on
  // where the cell boundaries happened to fall. The layout still looked
  // plausible, which is why it survived — but it was not the force field the
  // constants describe.
  const REACH_R = 286;
  const CELL = REACH_R;
  const REACH = REACH_R ** 2;
  const SPRING = 0.035;
  const REST = 42;
  const CENTRE = 0.0009;
  const DAMP = 0.86;

  // Bucket by cell so repulsion is over neighbours rather than everybody.
  // Integer keys, not template strings. The string form cost one allocation
  // and one hash per node to insert plus nine more to look up — ten per node
  // per tick, times 320 ticks. At a few hundred nodes the garbage collector
  // was the bottleneck long before the geometry was.
  const key = (cx, cy) => (cx + 4096) * 8192 + (cy + 4096);
  const grid = new Map();
  for (const n of nodes) {
    const k = key(Math.floor(n.x / CELL), Math.floor(n.y / CELL));
    let cell = grid.get(k);
    if (!cell) grid.set(k, (cell = []));
    cell.push(n);
  }
  for (const n of nodes) {
    const cx = Math.floor(n.x / CELL);
    const cy = Math.floor(n.y / CELL);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const cell = grid.get(key(cx + dx, cy + dy));
        if (!cell) continue;
        for (const m of cell) {
          if (m === n) continue;
          let ex = n.x - m.x;
          let ey = n.y - m.y;
          let d2 = ex * ex + ey * ey;
          if (d2 > REACH) continue;
          if (d2 < 0.01) {
            // Two nodes exactly on top of each other have no direction to
            // separate along; nudge deterministically by id so the layout
            // stays reproducible.
            ex = (n.id.charCodeAt(0) % 7) - 3 || 1;
            ey = (n.id.charCodeAt(1 % n.id.length) % 7) - 3 || 1;
            d2 = ex * ex + ey * ey;
          }
          const f = (REPEL * (1 + m.deg * 0.12)) / d2;
          const d = Math.sqrt(d2);
          n.vx += (ex / d) * f;
          n.vy += (ey / d) * f;
        }
      }
    }
  }

  for (const l of g.links) {
    const ex = l.t.x - l.s.x;
    const ey = l.t.y - l.s.y;
    const d = Math.hypot(ex, ey) || 0.01;
    const f = (d - REST) * SPRING;
    const ux = (ex / d) * f;
    const uy = (ey / d) * f;
    l.s.vx += ux;
    l.s.vy += uy;
    l.t.vx -= ux;
    l.t.vy -= uy;
  }

  for (const n of nodes) {
    n.vx -= n.x * CENTRE;
    n.vy -= n.y * CENTRE;
    n.vx *= DAMP;
    n.vy *= DAMP;
    const cap = 30 * heat;
    n.x += Math.max(-cap, Math.min(cap, n.vx));
    n.y += Math.max(-cap, Math.min(cap, n.vy));
  }
}

function radiusOf(n) {
  return 3 + Math.min(9, Math.sqrt(n.weight * 2 + n.deg));
}

function visible(n) {
  return !hiddenGroups.has(n.group);
}

/// Device pixels per CSS pixel for the graph canvas.
///
/// One function because there used to be two numbers: `fitCanvas` sized the
/// backing store at one cap and `draw` set its transform with another. Every
/// caller now reads the same value.
///
/// Capped at 3 rather than 2: the cap is a memory guard — a backing store
/// grows with its square — but `devicePixelRatio` also carries the webview
/// zoom, so on a 2x display at 150% the honest ratio is 3 and clamping to 2
/// renders the graph soft for exactly the person who enlarged it to see it.
function canvasScale() {
  return Math.min(3, window.devicePixelRatio || 1);
}

function fitCanvas() {
  const c = dom.canvas;
  const rect = c.getBoundingClientRect();
  // 3, not 2. The cap is a memory guard — a backing store grows with its
  // square — but it is also what a reader who has zoomed to 200% runs into:
  // `devicePixelRatio` carries the webview zoom, so on a 2x display at 150%
  // the honest ratio is 3 and clamping to 2 renders the graph soft for exactly
  // the person who enlarged it in order to see it.
  const dpr = canvasScale();
  c.width = Math.max(1, Math.round(rect.width * dpr));
  c.height = Math.max(1, Math.round(rect.height * dpr));
  draw();
}

function fitToContent({ ease = 1 } = {}) {
  const g = state.graph;
  if (!g || !g.nodes.length) return;
  const shown = g.nodes.filter(visible);
  const list = shown.length ? shown : g.nodes;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of list) {
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }
  const rect = dom.canvas.getBoundingClientRect();
  const pad = 60;
  const sx = (rect.width - pad * 2) / Math.max(1, maxX - minX);
  const sy = (rect.height - pad * 2) / Math.max(1, maxY - minY);
  const scale = Math.max(0.12, Math.min(2.4, Math.min(sx, sy)));
  const x = rect.width / 2 - ((minX + maxX) / 2) * scale;
  const y = rect.height / 2 - ((minY + maxY) / 2) * scale;
  const k = Math.max(0, Math.min(1, ease));
  view.scale += (scale - view.scale) * k;
  view.x += (x - view.x) * k;
  view.y += (y - view.y) * k;
}

function draw() {
  const c = dom.canvas;
  const ctx = c.getContext("2d");
  if (!ctx) return;
  // The SAME cap `fitCanvas` sizes the backing store with. They disagreed —
  // 3 there, 2 here — from the moment the cap was raised, so on any display
  // where `devicePixelRatio` exceeds 2 (a 300% Windows scale, or Ctrl+= up to
  // the 2.5 zoom step) the graph drew into the top-left two thirds of its own
  // buffer while the hit test went on using the full width. Clicking a visible
  // node selected nothing.
  const dpr = canvasScale();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, c.width / dpr, c.height / dpr);

  const g = state.graph;
  if (!g) return;

  // getComputedStyle forces a style recalc, and this ran inside draw() - so
  // every interaction frame, at up to one per displayed frame while dragging,
  // paid for one. The values are four theme tokens that change only when the
  // theme does, so they are read once and refreshed from followTheme below.
  const { edge, edgeActive, text, faint } = themeInk();

  const T = (n) => [n.x * view.scale + view.x, n.y * view.scale + view.y];
  const focus = selected || hovered;
  const near = new Set();
  if (focus) {
    near.add(focus.id);
    for (const l of g.links) {
      if (l.s === focus) near.add(l.t.id);
      if (l.t === focus) near.add(l.s.id);
    }
  }

  // Two passes, two paths, two strokes — not one path per link. Each
  // beginPath/stroke pair is a separate Skia draw call, and at a couple of
  // thousand links that was the single most expensive thing on the canvas.
  // Links only ever come in two appearances (lit, or not), so two batches
  // covers every case.
  ctx.lineWidth = 1;
  for (const lit of [false, true]) {
    if (lit && !focus) continue;
    ctx.strokeStyle = lit ? edgeActive : edge;
    ctx.globalAlpha = focus ? (lit ? 1 : 0.18) : 1;
    ctx.beginPath();
    let drew = false;
    for (const l of g.links) {
      if (!visible(l.s) || !visible(l.t)) continue;
      const isLit = Boolean(focus && (l.s === focus || l.t === focus));
      if (isLit !== lit) continue;
      const [x1, y1] = T(l.s);
      const [x2, y2] = T(l.t);
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      drew = true;
    }
    if (drew) ctx.stroke();
  }
  ctx.globalAlpha = 1;

  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const [x, y] = T(n);
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale));
    const dim = focus && !near.has(n.id);
    // 0.45, not 0.2. At 0.2 a dimmed node measured 1.11:1 against the canvas —
    // invisible, while `nodeAt` still hit-tested it, so you could click a node
    // you could not see. De-emphasis, not erasure.
    ctx.globalAlpha = dim ? 0.45 : 1;
    drawNode(ctx, x, y, r, n.group, colourFor(n.group));
    if (n === selected) {
      ctx.strokeStyle = text;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
  }
  ctx.globalAlpha = 1;

  // Labels only where they can be read: the core, the heavy nodes, and
  // whatever is focused. Every node labelled at any zoom is a grey smear.
  ctx.font = '11px "Segoe UI", system-ui, sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  // Drawn in importance order and skipped where one would land on another
  // already placed. Overlapping labels are worse than missing ones: two names
  // on top of each other are unreadable AND hide that there are two things.
  // Not while it is still settling: see the note in `startLayout`.
  if (sim) return;
  const placed = [];
  // The names named by the most facts (the first LABELLED_NAMES), and
  // whatever is focused and next to it.
  const LABELLED_NAMES = 24;
  const ordered = g.nodes
    .filter(visible)
    .filter((n) => n.rank < LABELLED_NAMES || near.has(n.id))
    .sort((a, b) => {
      const pull = (n) => (n === focus ? 4 : 0) + (near.has(n.id) ? 2 : 0);
      return pull(b) - pull(a) || a.rank - b.rank;
    });

  for (const n of ordered) {
    if (view.scale < 0.35 && !near.has(n.id) && n.rank >= 6) continue;
    const [x, y] = T(n);
    const label = n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label;
    const w = ctx.measureText(label).width;
    const top = y + radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 3;
    const box = { x1: x - w / 2 - 2, x2: x + w / 2 + 2, y1: top - 1, y2: top + 13 };
    if (placed.some((p) => box.x1 < p.x2 && box.x2 > p.x1 && box.y1 < p.y2 && box.y2 > p.y1)) {
      continue;
    }
    placed.push(box);
    ctx.fillStyle = near.has(n.id) || !focus ? text : faint;
    // 0.55, not 0.25: at 0.25 these measured 1.43:1 and simply vanished — and
    // they are the orientation landmarks, so they disappeared exactly when
    // someone was exploring.
    ctx.globalAlpha = focus && !near.has(n.id) ? 0.55 : 1;
    ctx.fillText(label, x, top);
  }
  ctx.globalAlpha = 1;
}

function nodeAt(clientX, clientY) {
  const g = state.graph;
  if (!g) return null;
  const rect = dom.canvas.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  let best = null;
  let bestD = Infinity;
  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const x = n.x * view.scale + view.x;
    const y = n.y * view.scale + view.y;
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 4;
    const d = (x - px) ** 2 + (y - py) ** 2;
    if (d <= r * r && d < bestD) {
      best = n;
      bestD = d;
    }
  }
  return best;
}

// The panel under a picked dot (galaxy-panel.js). Read-only; "Open in Memory"
// is the same "About <name>" page the button above it opens.
const galaxyPanel = createGalaxyPanel({
  invoke: IS_TAURI ? invoke : null,
  dom: {
    root: dom.galaxyFacts,
    title: dom.galaxyFactsTitle,
    note: dom.galaxyFactsNote,
    list: dom.galaxyFactsList,
    count: dom.galaxyFactsCount,
    live: dom.galaxyFactsLive,
    foot: dom.galaxyFactsFoot,
  },
  onOpen: (entityId) => openAboutFromGalaxy(entityId),
});

function select(node) {
  selected = node;
  if (!node) {
    dom.inspector.hidden = true;
    galaxyPanel.clear();
    draw();
    return;
  }
  dom.nodeKind.textContent = groupWords(node.group, { plural: false });
  dom.nodeLabel.textContent = node.label;

  // What the list says about this name - never a fact's words: those are
  // one click away, in "About <name>", read by id and hidden like every
  // memory list.
  dom.nodeFacts.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nodeFacts.append(el("dt", "", k), el("dd", "", v));
  };
  add("Facts that name it", node.facts);
  if (node.aliases.length) add("You call it", node.aliases.join(", "));
  if (node.also.length) add("Also known as", node.also.join(", "));
  add("Shares facts with", `${node.deg} ${node.deg === 1 ? "name" : "names"}`);

  dom.nodeActions?.replaceChildren(
    button(aboutTitle(node.label), () => openAboutFromGalaxy(node.entityId),
      { title: "Opens the Memory tab at this name: its facts, word for word." }));

  // "Facts behind this dot": their words, read by id, newest 20 first.
  galaxyPanel.show(node);

  const g = state.graph;
  const neighbours = [];
  for (const l of g.links) {
    if (l.s === node) neighbours.push([l.t, l.kind]);
    else if (l.t === node) neighbours.push([l.s, l.kind]);
  }
  dom.nodeLinks.replaceChildren();
  if (!neighbours.length) {
    dom.nodeLinks.append(el("li", "empty", "No other name shares a fact with it."));
  }
  for (const [other, kind] of neighbours.slice(0, 60)) {
    const li = el("li");
    const b = el("button", "", `${other.label}${kind ? ` · ${kind}` : ""}`);
    b.type = "button";
    b.addEventListener("click", () => {
      select(other);
      centreOn(other);
      // `select` calls `replaceChildren` on this list, so the button that was
      // just activated is removed from the document while it holds focus and
      // focus falls to <body>. A keyboard user lost their place on every hop
      // and had to tab from the top of the window again.
      dom.nodeLabel.focus({ preventScroll: true });
    });
    li.append(b);
    dom.nodeLinks.append(li);
  }
  dom.inspector.hidden = false;
  // A canvas has no accessibility tree, so selecting a node is otherwise a
  // silent event. This is the only thing that tells a screen-reader user
  // anything happened.
  announce(
    `${node.label}, ${groupWords(node.group, { plural: false })}, named in ${node.facts} ` +
      `${node.facts === 1 ? "fact" : "facts"}, shares facts with ${node.deg} ` +
      `${node.deg === 1 ? "name" : "names"}.`
  );
  draw();
}

/** "About <name>", from the Galaxy: the Memory tab, opened at that name. */
async function openAboutFromGalaxy(entityId) {
  await showView("memory");
  await openAbout(entityId);
}

/* ---- Finding a name (the research audit's B3) ---------------------------
   It used to jump to the first match only, and said nothing when there was
   none. Now every match is counted, Enter steps to the next (Shift+Enter
   back), and the line beside the box says "2 of 5" or "No name matches". */

function findInGalaxy({ keepAt = false } = {}) {
  const q = dom.graphSearch.value.trim();
  const g = state.graph;
  if (!q || !g) {
    galaxyFind.hits = [];
    galaxyFind.at = 0;
    if (dom.graphFind) dom.graphFind.textContent = "";
    return;
  }
  galaxyFind.hits = findNames(g.nodes.filter(visible), q);
  if (!keepAt || galaxyFind.at >= galaxyFind.hits.length) galaxyFind.at = 0;
  if (dom.graphFind) dom.graphFind.textContent = findStatus(galaxyFind.at, galaxyFind.hits.length);
  const hit = galaxyFind.hits[galaxyFind.at];
  if (hit) {
    select(hit);
    centreOn(hit);
  }
}

function stepGalaxyFind(delta) {
  const n = galaxyFind.hits.length;
  if (!n) return;
  galaxyFind.at = (galaxyFind.at + delta + n) % n;
  if (dom.graphFind) dom.graphFind.textContent = findStatus(galaxyFind.at, n);
  const hit = galaxyFind.hits[galaxyFind.at];
  select(hit);
  centreOn(hit);
}

function centreOn(node) {
  const rect = dom.canvas.getBoundingClientRect();
  view.x = rect.width / 2 - node.x * view.scale;
  view.y = rect.height / 2 - node.y * view.scale;
  draw();
}

/* ---- Canvas interaction -------------------------------------------------- */

let dragging = null;

dom.canvas.addEventListener("pointerdown", (e) => {
  dom.canvas.setPointerCapture(e.pointerId);
  dragging = { x: e.clientX, y: e.clientY, moved: false };
});

dom.canvas.addEventListener("pointermove", (e) => {
  if (dragging) {
    const dx = e.clientX - dragging.x;
    const dy = e.clientY - dragging.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging.moved = true;
    view.x += dx;
    view.y += dy;
    dragging.x = e.clientX;
    dragging.y = e.clientY;
    invalidate();
    return;
  }
  const hit = nodeAt(e.clientX, e.clientY);
  if (hit !== hovered) {
    hovered = hit;
    dom.canvas.style.cursor = hit ? "pointer" : "grab";
    invalidate();
  }
});

dom.canvas.addEventListener("pointerup", (e) => {
  const wasDrag = dragging && dragging.moved;
  dragging = null;
  if (wasDrag) return;
  select(nodeAt(e.clientX, e.clientY));
});

dom.canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const rect = dom.canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0016);
    const next = Math.max(0.08, Math.min(4, view.scale * factor));
    // Zoom about the cursor rather than the origin, so the thing under the
    // pointer stays under the pointer.
    view.x = px - ((px - view.x) / view.scale) * next;
    view.y = py - ((py - view.y) / view.scale) * next;
    view.scale = next;
    invalidate();
  },
  { passive: false }
);

// The canvas is focusable, so the graph is pannable and zoomable without a
// mouse. Selecting a node without one goes through the search field, which is
// also what makes the view usable with a screen reader.
dom.canvas.addEventListener("keydown", (e) => {
  const stepPx = e.shiftKey ? 120 : 40;
  const keys = {
    ArrowLeft: () => (view.x += stepPx),
    ArrowRight: () => (view.x -= stepPx),
    ArrowUp: () => (view.y += stepPx),
    ArrowDown: () => (view.y -= stepPx),
    "+": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "=": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "-": () => (view.scale = Math.max(0.08, view.scale / 1.2)),
    "0": () => fitToContent(),
    Escape: () => select(null),
  };
  const fn = keys[e.key];
  if (!fn) return;
  e.preventDefault();
  fn();
  invalidate();
});

/* ==========================================================================
   Theme
   ========================================================================== */

function applyTheme(name, { persist = true } = {}) {
  const theme = normaliseTheme(name);
  dom.root.setAttribute("data-theme", theme);
  dom.themePicker.value = theme;
  try {
    localStorage.setItem("jarvis.theme", theme);
  } catch (error) {
    /* the store below is the source of truth; this is only the anti-flash cache */
  }
  if (persist) {
    invoke("set_theme", { theme }).catch((error) =>
      console.error("[brain] could not persist the theme:", error)
    );
  }
  // The graph reads its colours from the computed style, so a theme change has
  // to repaint it — nothing else on the page needs telling.
  colourCache.clear();
  if (state.graph) draw();
}

/* ==========================================================================
   Wiring
   ========================================================================== */

const TAB_ORDER = Object.keys(VIEWS);

for (const key of TAB_ORDER) {
  const tab = $(`tab-${key}`);
  if (tab) tab.addEventListener("click", () => showView(key));
}

/**
 * The rail is a `tablist`, and a tablist is one Tab stop with the arrows moving
 * inside it. It shipped as six separate Tab stops, which is the pattern the
 * role explicitly is not: a screen reader announces "tab, 1 of 6" and then the
 * arrows do nothing, and a keyboard user has to press Tab six times to get past
 * the navigation to the thing they came for.
 *
 * Vertical rail, so Up/Down are the axis and Left/Right are accepted too —
 * costs nothing and saves the reader guessing which one this rail thinks it is.
 *
 * Cycles only the tabs currently on the rail: while "Advanced" is collapsed
 * its four tabs are `hidden` and cannot take focus, so including them here
 * would let arrowing past Work land nowhere.
 */
function visibleTabOrder() {
  return TAB_ORDER.filter((key) => {
    if (!advancedOpen && ADVANCED_VIEWS.includes(key)) return false;
    if (menuManager.isHidden(`brain.tab.${key}`)) return false;
    return true;
  });
}

function updateMenuVisibility() {
  const visible = visibleTabOrder();
  for (const key of TAB_ORDER) {
    const tab = $(`tab-${key}`);
    const item = tab?.closest("li");
    if (item) {
      const isAdv = ADVANCED_VIEWS.includes(key);
      const advHidden = isAdv && !advancedOpen;
      const menuHidden = menuManager.isHidden(`brain.tab.${key}`);
      item.hidden = advHidden || menuHidden;
    }
  }

  if (!visible.includes(state.view) && visible.length > 0) {
    showView(visible[0]);
  }

  const cards = document.querySelectorAll("[data-menu-id]");
  for (const card of cards) {
    const mid = card.dataset.menuId;
    if (!mid) continue;
    card.hidden = menuManager.isHidden(mid);
    if (menuManager.isCollapsed(mid)) {
      card.classList.add("card-collapsed");
    } else {
      card.classList.remove("card-collapsed");
    }
  }

  const count = menuManager.hiddenCount("desktop");
  const railHidden = $("rail-hidden-menus");
  const railCount = $("rail-hidden-count");
  if (railHidden && railCount) {
    if (count > 0) {
      railHidden.hidden = false;
      railCount.textContent =
        count === 1 ? WORDS.hidden_line_one : WORDS.hidden_line_many.replace("{n}", count);
    } else {
      railHidden.hidden = true;
    }
  }
}

dom.rail?.addEventListener("keydown", (event) => {
  const STEP = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  const order = visibleTabOrder();
  const here = order.indexOf(state.view);
  let next = null;
  if (event.key in STEP) next = (here + STEP[event.key] + order.length) % order.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = order.length - 1;
  if (next === null || here < 0) return;
  event.preventDefault();
  // Selection follows focus, which is the right choice for a tablist whose
  // panels are already loaded: it is what a reader expects, and the alternative
  // (arrow to move, Enter to open) makes them press two keys for every view.
  showView(order[next]);
  $(`tab-${order[next]}`)?.focus();
});

/**
 * "Advanced" reveals the four views this window used to always show —
 * Galaxy, Live, Trust, Watch — unchanged, just not on the rail by default.
 * Collapsing it again hides the tabs but never touches `state.view`: a view
 * that was open when the rail collapsed stays open, it just has no visible
 * tab until Advanced is reopened.
 */
dom.advancedToggle?.addEventListener("click", () => {
  advancedOpen = !advancedOpen;
  dom.advancedToggle.setAttribute("aria-expanded", String(advancedOpen));
  for (const key of ADVANCED_VIEWS) {
    const item = $(`tab-${key}`)?.closest("li");
    if (item) {
      const menuHidden = menuManager.isHidden(`brain.tab.${key}`);
      item.hidden = !advancedOpen || menuHidden;
    }
  }
  // Roving tabindex needs exactly one reachable stop at all times. showView()
  // already keeps that true whenever the active view is on the visible rail;
  // the one gap is collapsing Advanced while one of ITS views is the active
  // one, which would otherwise leave every tab at -1 and the rail untabbable.
  if (!advancedOpen && ADVANCED_VIEWS.includes(state.view)) {
    const first = visibleTabOrder()[0] || "memory";
    for (const key of TAB_ORDER) {
      const tab = $(`tab-${key}`);
      if (tab) tab.tabIndex = key === first ? 0 : -1;
    }
  }
  renderCounts();
});

dom.refresh.addEventListener("click", async () => {
  // Drop the cached layout so a refresh really re-lays out — and note that
  // `render` calls `startLayout` itself, so calling it again here started the
  // simulation twice and cancelled the first one mid-flight.
  if (state.view === "galaxy") state.graph = null;
  if (state.view === "history") chats.at = 0;
  if (state.view === "memory") autoL.at = 0;
  await load(sectionsFor(state.view));
  render(state.view);
});

dom.graphRefit.addEventListener("click", () => {
  fitToContent();
  draw();
});

dom.inspectorClose.addEventListener("click", () => select(null));

dom.memoryFactsFilter?.addEventListener("input", () => renderFacts());
$("history-filter")?.addEventListener("input", () => onHistorySearch());

dom.graphSearch.addEventListener("input", () => findInGalaxy());
dom.graphSearch.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  stepGalaxyFind(e.shiftKey ? -1 : 1);
});

dom.traceClear.addEventListener("click", () => {
  state.trace = [];
  dom.trace.replaceChildren();
});

dom.themePicker.addEventListener("change", () => applyTheme(dom.themePicker.value));

dom.watchAddOpen.addEventListener("click", () => {
  dom.watchForm.hidden = !dom.watchForm.hidden;
  if (!dom.watchForm.hidden) $("watch-name").focus();
});
dom.watchCancel.addEventListener("click", () => {
  dom.watchForm.hidden = true;
});

dom.watchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("watch-name").value.trim();
  if (!name) return;
  const stars = $("watch-stars").value.trim();
  try {
    await invoke("brain_watch_add", {
      name,
      query: $("watch-query").value.trim() || null,
      minStars: stars ? Number(stars) : null,
      language: $("watch-language").value.trim() || null,
      notify: $("watch-notify").checked,
    });
    toast(`Watching ${name}.`, "ok");
    dom.watchForm.reset();
    dom.watchForm.hidden = true;
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

dom.watchSeen.addEventListener("click", async () => {
  try {
    await invoke("brain_watch_seen", { topic: null });
    toast("Marked read.", "ok");
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

window.addEventListener("resize", () => {
  if (state.view === "galaxy") fitCanvas();
});

// Toggling the OS setting used to have no effect until the next refresh,
// because `matchMedia` was read once inside `startLayout`.
matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => {
  if (state.view === "galaxy" && state.graph) startLayout();
});

// Applied at boot AND on every change. The Brain read `get_theme` once and
// then ignored `theme-changed` for the life of the window, so picking a theme
// in Settings left the largest coloured surface in the product on the old
// palette until it was reopened. `tests/themes-all.mjs` only measured the
// boot path, so it passed while claiming "every window follows the theme".
// The cached ink has to die with the old palette, or the graph keeps painting
// the previous theme's edges until something else forces a reload.
followTheme((theme) => {
  dom.themePicker.value = theme;
  _ink = null;
  if (state.view === "galaxy" && state.graph) invalidate();
});

// The canvas is sized in device pixels from its CSS box, so a zoom step has to
// re-measure it or the graph is drawn at the old scale inside the new box.
followZoom(() => {
  if (state.view === "galaxy") fitCanvas();
});

/* ---- The one stream ------------------------------------------------------ */

startLink();
// "Open the card": one line while an approval card waits (card-link.js).
mountCardLink(document.getElementById("card-link"));

onLink((link) => {
  // The same words as every other window. "stream live · stale" used to sit
  // in the same green pill as "stream live", so stale looked fully live.
  const words = linkWords(link);
  dom.linkPill.dataset.connected = String(link.connected);
  dom.linkPill.dataset.tone = words.tone;
  dom.linkText.textContent = words.short;
  dom.linkPill.title = link.error || `${link.base} · last event ${link.lastId}`;
  dom.reconnectLink.hidden = link.connected;
  syncLiveButtons();
  youtubeBlock.linkChanged();
  retirementCard.sync();
  if (historyImport) historyImport.sync();
  paintFreshness();
  if (state.view === "now") renderLive();
  renderCounts();
});

dom.reconnectLink.addEventListener("click", () => {
  reconnect();
  dom.linkText.textContent = "Reconnecting…";
  announce("Reconnecting.");
});

onEvent((frame) => {
  pushTrace(frame);
  // A doorbell for the pane that is open. Reading everything on every frame
  // would put the graph's multi-second walk on the event path.
  const kind = String((frame && frame.kind) || "");
  // The next `model` event is the card being answered (or the download
  // moving), so the "waiting for your approval" line has done its job.
  if (kind === "model" && (state.modelAsk || state.modelAskEnded)) {
    state.modelAsk = null;
    state.modelAskEnded = null;
    if (state.view === "faculties") renderModels();
  }
  // A deep question finished (`{id, state}` only - a doorbell): read the
  // list again, so the answer shows without polling. Off the Memory tab it
  // is only marked old, and read when the tab is next shown.
  if (kind === "deep") {
    deep.at = 0;
    if (state.view === "memory") loadDeep();
  }
  // Automatic learning saved something (`{ids}` only, never the text): the
  // quiet line, and the list read again. Never a pop-up.
  if (kind === "memory_saved") noteMemorySaved(frame && frame.data);
  // A timer, alarm or reminder went off, or Coming up changed (`{id, kind,
  // state}` only - a doorbell): read the list again. The toast itself is
  // Rust's (brain/schedule.rs toast_fired), so it shows with the Brain shut.
  // A focus session started, changed or ended, or has a line to say
  // (`{state}` or `{state: "callout", seq}` - never what was in front): read
  // it again. The line itself is played by the Jarvis bar, fetched by Rust.
  if (kind === "focus") {
    fx.at = 0;
    if (state.view === "work") loadFocus();
  }
  // A chatbot conversation has no event of its own: its progress travels on
  // the one activity line ("Talking to Gemini: message 3 of 5."). Read it
  // again on every activity change while the Work tab is showing.
  if (kind === "activity") {
    cb.at = 0;
    sp.at = 0;
    if (state.view === "work") {
      loadChatbot();
      // A support chat's progress rides on the same activity line ("Chat
      // with Groupon: message 2 of 15.").
      loadSupport();
    }
  }
  if (kind === "schedule") {
    upL.at = 0;
    if (state.view === "work") loadComingUp();
    // A briefing went off or is ready (`{id, kind: "briefing", state}`):
    // read the briefing again, its lines by the authenticated route only.
    if (frame && frame.data && frame.data.kind === "briefing") {
      brief.at = 0;
      if (state.view === "work") loadBriefing();
    }
    // A goal's weekly check-in was approved, paused or changed (`{id, kind:
    // "goal_checkin", state}`): Goals reads its state from the very same
    // Coming up list (goals.js's own module doc says why), so loadComingUp()
    // above already reads the job again - it repaints Goals itself once done.
  }

  const refreshes = {
    model: ["models"],
    finding: ["watch", "watch_report"],
    job: ["jobs"],
    // The learner filled the review queue on its own (or a "Remember:"
    // made a card). Without this the Memory tab showed an old queue until
    // something else refreshed it.
    proposal: ["memory_pending"],
    // ...or saved some on its own (automatic learning): the facts list too.
    memory_saved: ["memory_facts"],
  };
  const sections = refreshes[kind];
  if (!sections) return;
  const showing = VIEW_SECTIONS[state.view] || [];
  if (!sections.some((s) => showing.includes(s))) return;
  load(sections, { quiet: true }).then(() => render(state.view));
});

/* ---- Boot ---------------------------------------------------------------- */

(async () => {
  // The inline bootstrap already painted from localStorage; this reconciles
  // with the store, which is what the other windows read.
  try {
    const stored = await invoke("get_theme");
    if (stored && stored !== dom.root.getAttribute("data-theme")) {
      applyTheme(stored, { persist: false });
    } else {
      dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
    }
  } catch (error) {
    dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
  }

  repaintTrace();
  // "Forget what you learned last week", said or typed in the Jarvis bar:
  // main.js left the place, so the Brain opens at History -> "Forget a time
  // frame" with the list filled in (forget-range-panel.js). "Earlier chats"
  // in the bar, and "Chat history…" in the tray (`#history`), open History
  // itself (the chat audit, 2026-09-28). Navigation only.
  updateMenuVisibility();
  const visible = visibleTabOrder();
  const landing = visible.includes("memory") ? "memory" : (visible[0] || "memory");
  const place = takeAnyPlace() || (location.hash === `#${HISTORY_PLACE}` ? HISTORY_PLACE : "");
  if (place === FORGET_RANGE_PLACE) {
    await showView("history");
    await openForgetRange();
  } else if (place === HISTORY_PLACE) {
    await showView("history");
    await applyHistoryFilePlace(takePlaceExtras());
  } else if (place === Topics.TOPICS_PLACE) {
    // "Switch off my work topic", said or typed: the picker opens for that
    // topic (topic controls). Nothing changes until Change is tapped.
    await goToTopics(Topics.readTopicPlace(takePlaceExtras()).topicId);
  } else {
    await showView(landing);
  }
})();

/** The Brain was already open when the Jarvis bar asked for a place. */
async function goToPlace(place = takeAnyPlace()) {
  if (place === FORGET_RANGE_PLACE) {
    await showView("history");
    await openForgetRange();
  } else if (place === HISTORY_PLACE) {
    await showView("history");
    await applyHistoryFilePlace(takePlaceExtras());
  } else if (place === Topics.TOPICS_PLACE) {
    await goToTopics(Topics.readTopicPlace(takePlaceExtras()).topicId);
  }
}
window.addEventListener("focus", () => goToPlace());
window.addEventListener("storage", (e) => {
  if (e.key === BRAIN_PLACE_KEY && e.newValue) goToPlace();
  if (e.key && e.key.startsWith("jarvis.menus.")) {
    menuManager.reload();
    updateMenuVisibility();
  }
});

$("btn-rail-hidden-menus")?.addEventListener("click", () => {
  // The place travels in storage, not in the call: open_fix_place opens the
  // Settings window and accepts only "settings", "brain" and "history"
  // (plain_errors.rs), and settings.js's goToPlace() reads this key on load,
  // on focus and on the storage event. Exactly what the Jarvis bar's own "open
  // <a section>" does (main.js openSettingsFromRoute). Bug audit 2026-10-05,
  // R5: with no grant for this window, and "menu-visibility" asked for as the
  // place, this button did nothing at all.
  try {
    localStorage.setItem("jarvis.settings.place", JSON.stringify({ place: "menu-visibility", at: Date.now() }));
  } catch {}
  if (IS_TAURI) {
    TAURI.core.invoke("open_fix_place", { place: "settings" });
  } else {
    window.location.href = "settings.html#menu-visibility";
  }
});
// "Chat history…" in the tray, with the Brain already open (windows.rs
// show_brain_at): the place's name only.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  TAURI.event.listen("brain-place", (event) => {
    if (event && event.payload === HISTORY_PLACE) goToPlace(HISTORY_PLACE);
  });
}

console.info(
  `[brain] ready — backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
