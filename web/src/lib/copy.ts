import { ApiError } from '../api/client';
import type { Job, JobProgress } from '../api/types';

export interface Problem {
  title: string;
  body: string;
  canRetry: boolean;
  /** Raw backend text kept behind a disclosure for debugging, never as the headline. */
  technical?: string;
}

const AI_OFF = new Set(['CONNECTION_FAILED', 'NOT_CONFIGURED', 'PROVIDER_DISABLED', 'MODEL_REMOVED', 'CAPABILITY_UNAVAILABLE', 'UNAVAILABLE']);
const AI_BAD_OUTPUT = new Set(['INVALID_OUTPUT', 'INCOMPLETE_OUTPUT', 'OUTPUT_LIMIT_REACHED', 'PROVIDER_STREAM_ERROR', 'OUTPUT_BLOCKED']);

function byCode(code: string | undefined, message: string | undefined): Problem | null {
  if (!code) return null;
  if (AI_OFF.has(code)) {
    return {
      title: 'AI trên máy này đang tắt',
      body: 'Bài, câu hỏi và lời giải đã lưu vẫn dùng bình thường. Bật AI rồi bấm Thử lại.',
      canRetry: true,
      technical: message,
    };
  }
  if (AI_BAD_OUTPUT.has(code)) {
    return {
      title: 'AI trả kết quả chưa dùng được',
      body: 'Không có gì được lưu từ lượt này và tài liệu của bạn không bị lỗi. Thử lại thường sẽ ổn.',
      canRetry: true,
      technical: message,
    };
  }
  switch (code) {
    case 'NETWORK':
      return {
        title: 'Chưa kết nối được máy chủ học',
        body: 'Kiểm tra cửa sổ đang chạy ./run.sh rồi bấm Thử lại. Dữ liệu đã lưu không bị ảnh hưởng.',
        canRetry: true,
      };
    case 'PROVIDER_TIMEOUT':
    case 'JOB_TIMEOUT':
      return {
        title: 'AI làm quá lâu nên đã dừng',
        body: 'Phần đã xong vẫn được lưu. Bạn có thể thử lại.',
        canRetry: true,
        technical: message,
      };
    case 'RATE_LIMITED':
      return {
        title: 'Nguồn AI đang giới hạn số lượt',
        body: 'Đợi một lúc rồi thử lại. Không có gì bị mất.',
        canRetry: true,
        technical: message,
      };
    case 'AI_BUSY':
    case 'SOURCE_READER_BUSY':
      return {
        title: 'Máy đang làm một việc khác',
        body: 'Đợi việc đó xong rồi thử lại. Yêu cầu của bạn vẫn ở đây.',
        canRetry: true,
      };
    case 'SOURCE_REFERENCE_MISMATCH':
      return {
        title: 'AI dẫn sai nguồn nên kết quả bị loại',
        body: 'Tài liệu của bạn không có lỗi. Thử lại để tạo lượt mới.',
        canRetry: true,
        technical: message,
      };
    case 'SERVER_RESTARTED':
      return {
        title: 'Máy chủ vừa khởi động lại',
        body: 'Phần đã làm được giữ nguyên. Bấm Thử lại để tiếp tục.',
        canRetry: true,
      };
    case 'INSUFFICIENT_COIN':
      return {
        title: 'Chưa đủ Coin cho lượt này',
        body: 'Bài, thẻ và lời giải đã lưu vẫn dùng bình thường.',
        canRetry: false,
      };
    case 'OBSERVATION_TIMEOUT':
      return {
        title: 'Vẫn đang làm ở máy chủ',
        body: 'Mình ngừng chờ trên trang này, nhưng việc vẫn chạy và phần xong sẽ được lưu. Mở lại để xem tiếp.',
        canRetry: true,
      };
    default:
      return null;
  }
}

export function describeError(error: unknown): Problem {
  if (error instanceof ApiError) {
    const coded = byCode(error.code, error.message);
    if (coded) return coded;
    if (error.status === 409) {
      return {
        title: 'Nội dung vừa thay đổi ở nơi khác',
        body: 'Phần bạn đang làm vẫn còn. Tải lại để xem bản mới.',
        canRetry: true,
        technical: error.message,
      };
    }
    if (error.status === 404) {
      return { title: 'Không tìm thấy nội dung này', body: 'Có thể nó đã bị xóa hoặc bạn không còn quyền xem.', canRetry: false };
    }
    if (error.status === 403 || error.status === 422) {
      // These backend messages are written for learners (e.g. "Nộp hoặc hủy kiểm tra trước…").
      return { title: 'Chưa làm được lúc này', body: error.message, canRetry: false };
    }
    return { title: 'Có lỗi chưa rõ nguyên nhân', body: 'Thử lại sau. Phần đã lưu không bị mất.', canRetry: true, technical: error.message };
  }
  return {
    title: 'Có lỗi chưa rõ nguyên nhân',
    body: 'Thử lại sau. Phần đã lưu không bị mất.',
    canRetry: true,
    technical: error instanceof Error ? error.message : String(error),
  };
}

export function describeJobFailure(job: Pick<Job, 'status' | 'error'>): Problem {
  if (job.status === 'cancelled') {
    return { title: 'Đã dừng theo yêu cầu', body: 'Phần đã làm xong vẫn được lưu.', canRetry: true };
  }
  return (
    byCode(job.error?.code, job.error?.message) ?? {
      title: 'Lượt này chưa xong',
      body: 'Phần đã làm xong vẫn được lưu. Bạn có thể thử lại.',
      canRetry: true,
      technical: job.error?.message,
    }
  );
}

// Waiting copy -------------------------------------------------------------------

export type StageState = 'done' | 'active' | 'waiting';

export interface StageView {
  key: 'read' | 'write' | 'questions' | 'save';
  label: string;
  detail?: string;
  state: StageState;
}

export interface WaitingView {
  headline: string;
  stages: StageView[];
  saved?: string;
}

const QUESTION_SCHEMA = /Draft$/;

/** Learner wording for a lesson job, derived only from what the server reports. */
export function lessonWaiting(progress: JobProgress | null | undefined): WaitingView {
  const requests = progress?.requests ?? [];
  const has = (test: (schema: string) => boolean) => requests.filter((r) => test(r.schema));
  const reading = has((s) => s === 'ChapterBrief');
  const writing = has((s) => s === 'LessonReading');
  const questions = has((s) => QUESTION_SCHEMA.test(s));
  const last = requests[requests.length - 1];
  const phase = progress?.phase ?? 'queued';

  let current: StageView['key'] = 'read';
  if (last && QUESTION_SCHEMA.test(last.schema)) current = 'questions';
  else if (last?.schema === 'LessonReading') current = 'write';
  if (phase === 'succeeded') current = 'save';

  const order: StageView['key'][] = ['read', 'write', 'questions', 'save'];
  const position = order.indexOf(current);
  const state = (key: StageView['key']): StageState => {
    const i = order.indexOf(key);
    if (phase === 'succeeded') return 'done';
    return i < position ? 'done' : i === position ? 'active' : 'waiting';
  };

  const chapter = progress?.chapter_context;
  const readDetail =
    chapter?.total_parts ? `${chapter.read_parts ?? 0}/${chapter.total_parts} phần` : reading.length ? `${reading.length} lượt đọc` : undefined;
  const doneQuestions = questions.filter((r) => r.phase === 'received').length;

  const stages: StageView[] = [
    { key: 'read', label: 'Đọc phần nguồn của bài', detail: readDetail, state: state('read') },
    { key: 'write', label: 'Viết giải thích và ví dụ', detail: writing.some((r) => r.phase === 'received') ? 'xong' : undefined, state: state('write') },
    { key: 'questions', label: 'Soạn câu kiểm tra', detail: doneQuestions ? `${doneQuestions} câu` : undefined, state: state('questions') },
    { key: 'save', label: 'Đối chiếu nguồn và lưu', state: state('save') },
  ];

  const headline =
    phase === 'queued'
      ? 'Đang chờ máy AI rảnh…'
      : current === 'read'
        ? 'Đang đọc phần nguồn của bài…'
        : current === 'write'
          ? 'Đang viết phần giải thích…'
          : current === 'questions'
            ? 'Đang soạn câu kiểm tra…'
            : 'Đang lưu bài…';

  const saved =
    progress?.planned_stages && progress.saved_stages
      ? `Đã lưu ${progress.saved_stages}/${progress.planned_stages} phần — rời trang vẫn giữ.`
      : 'Phần nào xong sẽ được lưu ngay — rời trang vẫn giữ.';
  return { headline, stages, saved };
}

/** "dòng 3", "trang 12"… for a source fragment locator. */
export function locatorLabel(locator: Record<string, unknown> | undefined | null): string {
  if (!locator) return 'trích đoạn';
  const number = (key: string) => (typeof locator[key] === 'number' ? (locator[key] as number) : null);
  const type = typeof locator.type === 'string' ? locator.type : '';
  const page = number('page');
  const slide = number('slide');
  const line = number('line');
  const paragraph = number('paragraph');
  if (type === 'user_transcription') return 'phần chép tay';
  if (slide !== null) return `slide ${slide}`;
  if (page !== null) return `trang ${page}`;
  if (line !== null) return `dòng ${line}`;
  if (paragraph !== null) return `đoạn ${paragraph}`;
  if (type === 'table') return 'bảng';
  return 'trích đoạn';
}

export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} giây`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} phút ${rest} giây` : `${minutes} phút`;
}
