import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { SourceDoc } from '../../api/types';
import { navigate } from '../../app/router';
import { useApp } from '../../app/store';
import { Icon } from '../../components/Icon';
import { Mascot } from '../../components/Mascot';
import { ProblemNotice } from '../../components/StateViews';
import { describeError, locatorLabel, type Problem } from '../../lib/copy';
import {
  addChapter,
  canMerge,
  lessonCount,
  memoryNotes,
  mergeWithPrevious,
  moveLesson,
  moveToChapter,
  planRequest,
  removeLesson,
  renameChapter,
  roadmapFrom,
  splitLesson,
  updateLesson,
  type BlueprintValue,
  type PlanChoices,
  type Roadmap,
} from './roadmap';

const TYPES: [string, string][] = [
  ['mcq', 'Trắc nghiệm'],
  ['cloze', 'Điền khuyết'],
  ['matching', 'Ghép cặp'],
  ['ordering', 'Sắp xếp'],
  ['short_answer', 'Tự luận ngắn'],
];
const LANGUAGES: [PlanChoices['language'], string][] = [
  ['vi', 'Tiếng Việt, giữ thuật ngữ Anh'],
  ['en', 'English'],
  ['source', 'Theo tài liệu'],
];

interface Saved {
  roadmap: Roadmap;
  choices: PlanChoices;
}

const editKey = (id: string) => `folio.create.edit.${id}`;

function initialChoices(source: SourceDoc, blueprint: BlueprintValue, notes: string): PlanChoices {
  return {
    sourceId: source.id,
    revision: source.revision,
    subject: blueprint.subject,
    goal: blueprint.goal,
    language: blueprint.language ?? 'vi',
    rules: [...blueprint.rules],
    extraRules: '',
    focus: [...blueprint.focus],
    terms: [...blueprint.terms_to_keep],
    notes,
    questionTypes: TYPES.map(([t]) => t),
    questionCount: 5,
    unlockPolicy: 'locked',
  };
}

function pages(refs: string[], byId: Map<string, SourceDoc['fragments'][number]>) {
  const labels = refs.map((ref) => locatorLabel(byId.get(ref)?.locator));
  if (!labels.length) return '';
  return labels[0] === labels[labels.length - 1] ? labels[0] : `${labels[0]} – ${labels[labels.length - 1]}`;
}

export function RoadmapStep({
  source,
  blueprint,
  notes,
  onReread,
  onCreated,
}: {
  source: SourceDoc;
  blueprint: BlueprintValue & { id: string };
  notes: string;
  onReread: () => void;
  onCreated: () => void;
}) {
  const { toast } = useApp();
  const [state, setState] = useState<Saved>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(editKey(blueprint.id)) ?? 'null') as Saved | null;
      if (saved?.roadmap?.chapters?.length) return saved;
    } catch {
      /* Start from the proposal. */
    }
    return { roadmap: roadmapFrom(blueprint), choices: initialChoices(source, blueprint, notes) };
  });
  const [openLesson, setOpenLesson] = useState<string | null>(null);
  const [newTerm, setNewTerm] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const byId = useMemo(() => new Map(source.fragments.map((f) => [f.id, f])), [source.fragments]);
  const { roadmap, choices } = state;

  useEffect(() => {
    try {
      localStorage.setItem(editKey(blueprint.id), JSON.stringify(state));
    } catch {
      /* Edits stay in memory. */
    }
  }, [state, blueprint.id]);

  const edit = (next: Roadmap) => setState((s) => ({ ...s, roadmap: next }));
  const choose = (patch: Partial<PlanChoices>) => setState((s) => ({ ...s, choices: { ...s.choices, ...patch } }));
  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
  const total = lessonCount(roadmap);
  let number = 0;

  const create = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const plan = await api<{ id: string; outline: { version: number } }>('/plans/from-blueprint', { body: planRequest(roadmap, choices) });
      const course = await api<{ course_id: string }>(`/plans/${plan.id}/approve`, { body: { expected_revision: plan.outline.version } });
      const notes = memoryNotes(choices, blueprint.study_tips);
      if (notes) await api(`/courses/${course.course_id}/memory`, { method: 'PUT', body: { notes, expected_version: 0 } }).catch(() => undefined);
      try {
        localStorage.removeItem(editKey(blueprint.id));
      } catch {
        /* ignore */
      }
      onCreated();
      toast('Đã tạo khóa — bắt đầu với bài 1 nhé');
      navigate({ name: 'course', courseId: course.course_id });
    } catch (error) {
      setProblem(describeError(error));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => setState({ roadmap: roadmapFrom(blueprint), choices: initialChoices(source, blueprint, notes) });

  return (
    <div className="roadmap-step">
      <section className="roadmap" aria-label="Lộ trình đề xuất">
        <div className="roadmap__intro">
          <Mascot mood="happy" size={72} />
          <div>
            <p className="eyebrow">Byte đã đọc hết {blueprint.scope_fragment_ids.length} đoạn</p>
            <p className="roadmap__summary">{blueprint.summary}</p>
          </div>
        </div>
        <label className="roadmap__title">
          <span className="eyebrow">Tên khóa</span>
          <input className="field field--title" value={roadmap.title} maxLength={200} onChange={(e) => edit({ ...roadmap, title: e.target.value })} />
        </label>

        {roadmap.chapters.map((chapter, c) => (
          <section key={chapter.key} className="roadmap-chapter">
            <header className="roadmap-chapter__head">
              <span className="roadmap-chapter__num">Chương {c + 1}</span>
              <input
                className="field roadmap-chapter__name"
                value={chapter.title}
                maxLength={120}
                aria-label={`Tên chương ${c + 1}`}
                onChange={(e) => edit(renameChapter(roadmap, chapter.key, e.target.value))}
              />
              <span className="meta">{chapter.lessons.length} bài</span>
            </header>
            <ol className="roadmap-lessons">
              {chapter.lessons.map((lesson, l) => {
                number += 1;
                const open = openLesson === lesson.key;
                return (
                  <li key={lesson.key} className={open ? 'roadmap-lesson is-open' : 'roadmap-lesson'}>
                    <div className="roadmap-lesson__row">
                      <span className="roadmap-lesson__num">{number}</span>
                      <div className="roadmap-lesson__main">
                        <input
                          className="field roadmap-lesson__title"
                          value={lesson.title}
                          maxLength={200}
                          aria-label={`Tên bài ${number}`}
                          onChange={(e) => edit(updateLesson(roadmap, lesson.key, { title: e.target.value }))}
                        />
                        <span className="meta roadmap-lesson__pages">
                          {lesson.refs.length} đoạn · {pages(lesson.refs, byId)}
                        </span>
                      </div>
                      <button type="button" className="icon-btn" aria-label="Đưa bài lên" disabled={c === 0 && l === 0} onClick={() => edit(moveLesson(roadmap, lesson.key, -1))}>
                        <Icon name="up" size={18} />
                      </button>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Đưa bài xuống"
                        disabled={c === roadmap.chapters.length - 1 && l === chapter.lessons.length - 1}
                        onClick={() => edit(moveLesson(roadmap, lesson.key, 1))}
                      >
                        <Icon name="down" size={18} />
                      </button>
                      <button type="button" className="icon-btn" aria-label="Thêm tùy chọn cho bài" aria-expanded={open} onClick={() => setOpenLesson(open ? null : lesson.key)}>
                        <Icon name="settings" size={18} />
                      </button>
                    </div>
                    {open && (
                      <div className="roadmap-lesson__more enter">
                        <label>
                          <span className="eyebrow">Mục tiêu bài</span>
                          <textarea className="field" rows={2} maxLength={1000} value={lesson.objective} onChange={(e) => edit(updateLesson(roadmap, lesson.key, { objective: e.target.value }))} />
                        </label>
                        <div className="roadmap-lesson__actions">
                          <button type="button" className="chip" disabled={!canMerge(roadmap, lesson.key)} onClick={() => edit(mergeWithPrevious(roadmap, lesson.key))}>
                            <Icon name="merge" size={15} /> Gộp với bài trên
                          </button>
                          <button type="button" className="chip" disabled={lesson.refs.length < 2} onClick={() => edit(splitLesson(roadmap, lesson.key))}>
                            <Icon name="scissors" size={15} /> Tách đôi
                          </button>
                          <button type="button" className="chip" onClick={() => edit(addChapter(roadmap, lesson.key))}>
                            <Icon name="plus" size={15} /> Mở chương mới từ bài này
                          </button>
                          {roadmap.chapters.length > 1 && (
                            <label className="chip chip--select">
                              Chuyển sang
                              <select value={chapter.key} onChange={(e) => edit(moveToChapter(roadmap, lesson.key, e.target.value))}>
                                {roadmap.chapters.map((target, i) => (
                                  <option key={target.key} value={target.key}>
                                    Chương {i + 1}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                          <button type="button" className="chip chip--danger" disabled={total <= 1} onClick={() => edit(removeLesson(roadmap, lesson.key))}>
                            <Icon name="trash" size={15} /> Bỏ bài này
                          </button>
                        </div>
                        <details className="roadmap-lesson__sources">
                          <summary>Xem các đoạn nguồn của bài</summary>
                          <ul>
                            {lesson.refs.map((ref) => (
                              <li key={ref}>
                                <span className="tag">{locatorLabel(byId.get(ref)?.locator)}</span> {(byId.get(ref)?.text ?? '').slice(0, 220)}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
        {roadmap.skipped.length > 0 && (
          <p className="notice notice--butter roadmap__skipped">
            <Icon name="flag" /> {roadmap.skipped.length} đoạn của các bài đã bỏ sẽ không được học trong khóa này.
          </p>
        )}
        <div className="roadmap__tools">
          <button type="button" className="link link--quiet" onClick={reset}>
            <Icon name="refresh" size={15} /> Quay về đề xuất ban đầu
          </button>
          <button type="button" className="link link--quiet" onClick={onReread}>
            Nhờ Byte đọc lại với mong muốn khác
          </button>
        </div>
      </section>

      <aside className="suggest" aria-label="Gợi ý cách học">
        <section className="suggest__card">
          <p className="title-m">Byte gợi ý cách học</p>
          <label>
            <span className="eyebrow">Môn học</span>
            <input className="field" value={choices.subject} maxLength={200} onChange={(e) => choose({ subject: e.target.value })} />
          </label>
          <label>
            <span className="eyebrow">Mục tiêu</span>
            <input className="field" value={choices.goal} maxLength={1000} onChange={(e) => choose({ goal: e.target.value })} />
          </label>

          <div>
            <span className="eyebrow">Ngôn ngữ nội dung</span>
            <div className="segmented segmented--stack" role="radiogroup" aria-label="Ngôn ngữ nội dung">
              {LANGUAGES.map(([value, label]) => (
                <button key={value} type="button" role="radio" aria-checked={choices.language === value} onClick={() => choose({ language: value })}>
                  {label}
                </button>
              ))}
            </div>
            {blueprint.language_note && <p className="meta">Byte: {blueprint.language_note}</p>}
          </div>

          {blueprint.focus.length > 0 && (
            <div>
              <span className="eyebrow">Nên tập trung vào · Byte sẽ nhớ khi bạn hỏi</span>
              <div className="chips">
                {blueprint.focus.map((item) => (
                  <button key={item} type="button" className="chip" aria-pressed={choices.focus.includes(item)} onClick={() => choose({ focus: toggle(choices.focus, item) })}>
                    {choices.focus.includes(item) && <Icon name="check" size={14} />} {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <span className="eyebrow">Quy tắc khi AI soạn bài</span>
            <ul className="rule-list">
              {blueprint.rules.map((rule) => (
                <li key={rule}>
                  <label className="check-row">
                    <input type="checkbox" checked={choices.rules.includes(rule)} onChange={() => choose({ rules: toggle(choices.rules, rule) })} />
                    <span>{rule}</span>
                  </label>
                </li>
              ))}
            </ul>
            <textarea
              className="field"
              rows={2}
              maxLength={1000}
              value={choices.extraRules}
              placeholder="Thêm quy tắc của bạn, mỗi dòng một ý"
              onChange={(e) => choose({ extraRules: e.target.value })}
            />
          </div>

          <div>
            <span className="eyebrow">Thuật ngữ giữ nguyên</span>
            <div className="chips">
              {choices.terms.map((term) => (
                <button key={term} type="button" className="chip" aria-label={`Bỏ thuật ngữ ${term}`} onClick={() => choose({ terms: choices.terms.filter((t) => t !== term) })}>
                  {term} <Icon name="x" size={13} />
                </button>
              ))}
              <form
                className="chip-add"
                onSubmit={(event) => {
                  event.preventDefault();
                  const value = newTerm.trim();
                  if (value && !choices.terms.includes(value)) choose({ terms: [...choices.terms, value] });
                  setNewTerm('');
                }}
              >
                <input className="field" value={newTerm} maxLength={100} placeholder="+ thêm" onChange={(e) => setNewTerm(e.target.value)} aria-label="Thêm thuật ngữ" />
              </form>
            </div>
          </div>
        </section>

        <section className="suggest__card">
          <p className="title-m">Luyện tập mỗi bài</p>
          <div className="chips">
            {TYPES.map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="chip"
                aria-pressed={choices.questionTypes.includes(value)}
                onClick={() => choices.questionTypes.length > 1 || !choices.questionTypes.includes(value) ? choose({ questionTypes: toggle(choices.questionTypes, value) }) : undefined}
              >
                {choices.questionTypes.includes(value) && <Icon name="check" size={14} />} {label}
              </button>
            ))}
          </div>
          <label className="count-row">
            <span>Số câu mỗi bài</span>
            <input
              type="range"
              aria-label="Số câu mỗi bài"
              min={Math.max(1, choices.questionTypes.length)}
              max={8}
              value={Math.max(choices.questionTypes.length, choices.questionCount)}
              onChange={(e) => choose({ questionCount: Number(e.target.value) })}
            />
            <strong>{Math.max(choices.questionTypes.length, choices.questionCount)}</strong>
          </label>
          <div className="segmented" role="radiogroup" aria-label="Cách mở bài">
            <button type="button" role="radio" aria-checked={choices.unlockPolicy === 'locked'} onClick={() => choose({ unlockPolicy: 'locked' })}>
              Mở dần sau luyện tập
            </button>
            <button type="button" role="radio" aria-checked={choices.unlockPolicy === 'open'} onClick={() => choose({ unlockPolicy: 'open' })}>
              Mở tự do
            </button>
          </div>
        </section>

        {blueprint.study_tips.length > 0 && (
          <section className="suggest__card suggest__card--tips">
            <p className="title-m">Cách ôn hiệu quả</p>
            <ul>
              {blueprint.study_tips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </section>
        )}

        {problem && <ProblemNotice problem={problem} compact />}
        <button type="button" className="btn btn--primary btn--lg btn--block" onClick={() => void create()} disabled={busy || !choices.subject.trim() || !choices.goal.trim()} aria-busy={busy}>
          Tạo khóa với {total} bài <Icon name="arrowRight" size={18} />
        </button>
        <p className="meta suggest__note">Tạo khóa chưa gọi AI. Từng bài được tạo khi bạn mở nó trên lộ trình.</p>
      </aside>
    </div>
  );
}
