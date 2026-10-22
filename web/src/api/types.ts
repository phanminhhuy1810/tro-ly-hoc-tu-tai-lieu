// Shapes observed from the live backend (GET/POST responses), not only the
// OpenAPI snapshot: many routes there have no response_model.

export type QuestionKind = 'mcq' | 'cloze' | 'matching' | 'ordering' | 'short_answer';

export interface Section {
  title: string;
  text: string;
  source_refs: string[];
}

export interface Card {
  front: string;
  back: string;
  source_refs: string[];
}

export interface PayloadItem {
  id: string;
  text: string;
}

export interface Question {
  id: string;
  unit_id: string;
  kind: QuestionKind;
  prompt: string;
  options: string[];
  left: string[];
  source_refs: string[];
  question_revision_id: string;
  difficulty?: string | null;
  payload: { options: PayloadItem[]; left: PayloadItem[] };
}

export interface UnitData {
  title: string;
  sections: Section[];
  questions: Question[];
  cards: Card[];
  mindmap: Section[];
}

export interface Unit {
  id: string;
  title: string;
  objective?: string;
  /** Chapter name from the confirmed roadmap; empty for older courses. */
  chapter?: string;
  source_refs: string[];
  data: UnitData | null;
  completed?: boolean;
  unlocked?: boolean;
}

export interface Course {
  id: string;
  revision: number;
  plan_id: string;
  creator_id: string;
  access_role: 'creator' | 'learner' | string;
  content: { title: string; unlock_policy: 'locked' | 'open' | string; units: Unit[] };
}

export interface Position {
  mode: 'learn' | 'cards' | 'practice';
  unit_id: string;
  session_id?: string | null;
  item_id?: string | null;
  card_id?: string | null;
  section_index?: number;
  expected_revision: number;
}

export interface Progress extends Partial<Position> {
  version: number;
  mode_positions?: Partial<Record<'learn' | 'cards' | 'practice', Position>>;
  updated_at?: string;
}

export interface ResumeEntry {
  course_id: string;
  title: string;
  position: Position;
  version: number;
  updated_at: string;
}

export type AnswerValue = string | string[] | Record<string, string>;

export interface GradeResult {
  correct: boolean | null;
  reference: string | number[];
  explanation: string;
  rubric: string[];
  source_refs: string[];
  grading: 'fixed' | 'self_review';
}

export interface SessionAnswer {
  answer: AnswerValue;
  feedback: GradeResult | null;
  assisted: boolean;
}

export interface PracticeSession {
  id: string;
  revision: number;
  mode: string;
  exam: boolean;
  status: 'open' | 'completed' | 'cancelled';
  scope: { unit_id: string | null; unit_ids: string[] };
  questions: Question[];
  answers?: Record<string, SessionAnswer>;
  drafts?: Record<string, { answer: AnswerValue; version: number }>;
  result?: SessionResult | null;
}

export interface SessionResult {
  score: number;
  fixed_total: number;
  self_review_count: number;
  assisted_count?: number;
  rewards?: RewardEvent[] | null;
}

export interface Wallet {
  balance: number;
  held: number;
  available: number;
  enforcement_enabled: boolean;
}

export interface SourceFragment {
  id: string;
  text: string;
  kind?: string;
  locator?: Record<string, unknown>;
  original_text?: string;
}

export interface SourceDoc {
  id: string;
  metadata: { name: string; warnings: string[]; kind?: string; bytes?: number };
  status: string;
  revision: number;
  reviewed: boolean;
  created_at?: string;
  fragments: SourceFragment[];
}

// Inline help ---------------------------------------------------------------
export interface HelpReply {
  text?: string;
  action?: string;
  step?: number;
  ai_generated?: boolean;
  reference?: string | number[];
  rubric?: string[];
  criteria?: string[];
  eliminated_option_ids?: string[];
  prefix?: string;
  ordered_option_ids?: string[];
  pairs?: Record<string, string>;
  source_refs?: string[];
  needs_more_source?: boolean;
  reference_warning?: { state: string; reason: string } | null;
}

export interface HelpMessage {
  id: string;
  role: 'user' | 'assistant';
  action: string;
  content: HelpReply & { student?: unknown };
  created_at: string;
}

export interface HelpThread {
  id: string;
  course_id: string;
  revision: number;
  context: { kind: 'question' | 'section' | 'mindmap'; unit_id: string; unit_title: string };
  messages: HelpMessage[];
  source_excerpts: SourceFragment[];
  draft: { text: string; version: number };
  pending_jobs: string[];
  reference_warning: { state: string; reason: string } | null;
}

export interface HelpActionResponse {
  thread_id?: string;
  reply?: HelpReply;
  ai_called?: boolean;
  cached?: boolean;
  job_id?: string;
}

// Jobs ----------------------------------------------------------------------
export interface JobRequestProgress {
  index: number;
  schema: string;
  phase: string;
  elapsed_ms?: number;
}

export interface ChapterProgress {
  status?: string;
  read_parts?: number;
  total_parts?: number;
  covered_fragments?: number;
  total_fragments?: number;
  complete?: boolean;
}

export interface JobProgress {
  version?: number;
  phase: string;
  requests: JobRequestProgress[];
  planned_stages: number | null;
  saved_stages: number;
  reused_stages?: number;
  started_at?: string | null;
  chapter_context?: ChapterProgress | null;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  task: string;
  status: JobStatus;
  result: Record<string, unknown> | null;
  error: { code?: string; message?: string; retryable?: boolean } | null;
  progress: JobProgress | null;
  feedback_deferred?: boolean;
}

export interface CoinPolicy {
  prices: Record<string, number>;
  initial_quota?: Record<string, number>;
  enforcement_enabled: boolean;
}

export interface CoinQuote {
  code: 'COIN_CONFIRMATION_REQUIRED';
  quote_id: string;
  amount: number;
  task: string;
  model?: string;
  message?: string;
  insufficient_coin?: boolean;
  wallet?: Wallet;
}

// Course chat ---------------------------------------------------------------
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  revision?: number;
  source_refs?: string[];
}

export interface StudyCard {
  id: string;
  front: string;
  back: string;
  kind: 'generated' | 'personal';
  unit_id?: string;
  memory?: { remembered: boolean } | null;
}

export interface RewardEvent {
  amount: number;
  capped?: boolean;
  replayed?: boolean;
  event_key?: string;
}
