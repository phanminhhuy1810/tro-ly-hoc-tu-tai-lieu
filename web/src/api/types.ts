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
  course_id?: string | null;
  course_revision?: number;
  unit_id?: string;
  version: number;
  source_refs?: string[];
  origin?: { kind: string; session_id?: string; item_id?: string };
  /** remembered: null = not reviewed yet. */
  memory?: { remembered: boolean | null; version: number; updated_at?: string } | null;
}

export type NoteColor = 'white' | 'butter' | 'peach' | 'pink' | 'lilac' | 'sky' | 'mint';

export interface Note {
  id: string;
  body: string;
  label: 'user' | 'teacher' | 'ai' | string;
  source_refs: string[];
  version: number;
  updated_at: string;
  /** Chosen by the learner; null until then (see noteColor for the default). */
  color: NoteColor | null;
}

export interface HistoryEntry {
  id: string;
  revision: number;
  status: 'open' | 'completed' | 'cancelled';
  result: (SessionResult & { course_revision?: number }) | null;
  created_at: string;
}

export interface SourceSummary {
  id: string;
  metadata: { name: string; kind: string; bytes: number };
  status: string;
  created_at: string;
  revision: number;
  reviewed: boolean;
  warning_count: number;
}

export interface Lifecycle {
  type: 'course' | 'source';
  id: string;
  title: string;
  revision: number;
  lifecycle_version: number;
  deleted_at: string | null;
  blockers: { type: string; id: string; reason: string }[];
  can_delete: boolean;
  can_restore: boolean;
  effects: { jobs_to_cancel: number; sessions_to_cancel: number; rooms_to_cancel: number; sharing_revoked: boolean };
}

export interface AiModel {
  id: string;
  label: string;
  external: boolean;
  configured: boolean;
  enabled: boolean;
  selectable: boolean;
  ready: boolean;
  data_destination: 'this_machine' | 'external_provider';
  model?: string;
  provider?: string;
  last_request_status?: string;
  last_error_code?: string | null;
}

export interface AiCatalog {
  default_model_id: string;
  selected_model_id: string;
  selection_revision: number;
  models: AiModel[];
}

export interface RewardEvent {
  amount: number;
  capped?: boolean;
  replayed?: boolean;
  event_key?: string;
}

// Cộng đồng và chia sẻ -------------------------------------------------------

export type Visibility = 'private' | 'shared' | 'public';

/** GET /community, /community/{id} (`me` only on the single-course view). */
export interface CommunityCourse {
  id: string;
  title: string;
  creator_name: string;
  revision: number;
  units: { id: string; title: string; generated: boolean }[];
  likes: number;
  rating: number | null;
  rating_count: number;
  updated_at: string;
  me?: { role: 'creator' | 'learner' | null; liked: boolean; rating: number | null };
}

/** GET /courses/{id}/publication — what the creator shares right now. */
export interface PublicationState {
  course_id: string;
  visibility: Visibility;
  originals: string[];
  updated_at: string | null;
  active_members: number;
  invite_codes: number;
  open_reports: number;
  likes: number;
  rating: number | null;
  rating_count: number;
}

export interface PublicationPreview {
  publication_id: string;
  preview: {
    title: string;
    visibility: Visibility;
    course_revision: number;
    shared_material: string[];
    private_material_excluded: string[];
    originals: string[];
    warning: string;
  };
}

export interface CourseReport {
  id: string;
  unit_id: string | null;
  question_id: string | null;
  reason: string;
  status: string;
  created_at: string;
}

// Phòng đố vui ----------------------------------------------------------------

export type RoomPhase = 'lobby' | 'question_open' | 'question_closed' | 'finished' | 'cancelled';

export interface RoomPolicy {
  max_players: number;
  max_questions: number;
  reveal_seconds: number;
  host_grace_seconds: number;
  member_presence_seconds: number;
  points_per_correct: number;
  room_ttl_seconds: number;
}

export interface RoomPlayer {
  member_id: string;
  nickname: string;
  state: 'joined' | 'left';
  is_host: boolean;
  score: number;
  answered_closed_questions: number;
  connected: boolean;
  rank: number;
}

export interface RoomSolution {
  answer: string | number[];
  explanation: string;
  source_refs: string[];
}

/** GET /rooms/{id}, POST /rooms/{id}/presence and the `snapshot` SSE event. */
export interface RoomSnapshot {
  id: string;
  course_revision: number;
  title: string;
  phase: RoomPhase;
  event_index: number;
  question_index: number;
  question_event_index: number | null;
  seconds_per_question: number;
  question_count: number;
  closed_count: number;
  deadline: string | null;
  server_time: string;
  expires_at: string;
  end_reason: string | null;
  policy: RoomPolicy;
  scoreboard: RoomPlayer[];
  me: { member_id: string; state: 'joined' | 'left'; is_host: boolean };
  question: Question | null;
  own_answer: AnswerValue | null;
  own_result: { correct: boolean; points: number } | null;
  solution: RoomSolution | null;
  reference_warning: string | null;
  ai_help_available: boolean;
}

export interface RoomBank {
  course_id: string;
  revision: number;
  unit_ids: string[];
  units: { id: string; title: string; unlocked: boolean; generated: boolean }[];
  available: number;
  max_selectable: number;
  omitted: { question_id: string; reason: string }[];
  policy: RoomPolicy;
}

export interface RoomCreated {
  room_id: string;
  phase: RoomPhase;
  event_index: number;
  question_count: number;
  join_code?: string;
}

export interface RoomSummary {
  id: string;
  phase: RoomPhase;
  event_index: number;
  title: string;
  created_at: string;
}

export interface RoomResultQuestion extends Question {
  solution: RoomSolution;
  sources: SourceFragment[];
  reference_warning: string | null;
  own_answer: AnswerValue | null;
  correct: boolean;
  points: number;
}

export interface RoomResults {
  room_id: string;
  phase: RoomPhase;
  scoreboard: RoomPlayer[];
  questions: RoomResultQuestion[];
  end_reason: string | null;
}
