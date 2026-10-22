from typing import Literal
import re
import hashlib
from fractions import Fraction
from pydantic import BaseModel, ConfigDict, Field, StrictInt, create_model, model_validator
from .question_quality import verify_mcq_options
from .source_limits import MAX_UNITS


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisionText(Model):
    text: str = Field(min_length=1, max_length=20_000)
    uncertain_spans: list[str] = Field(max_length=40)


class Section(Model):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=5000)
    source_refs: list[str] = Field(min_length=1, max_length=12)


class Card(Model):
    front: str = Field(min_length=1, max_length=1000)
    back: str = Field(min_length=1, max_length=3000)
    source_refs: list[str] = Field(min_length=1, max_length=12)


class QuestionContent(Model):
    kind: Literal["mcq", "cloze", "matching", "ordering", "short_answer"]
    prompt: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=8)
    left: list[str] = Field(default_factory=list, max_length=8)
    answer: str | list[StrictInt] = Field(description="mcq: the exact text of one option; cloze: one string for ONE blank; short_answer: reference text. matching: zero-based right-option index for each left item. ordering: zero-based option indices in correct order. Never use objects, letters, or numbers for a string answer.")
    explanation: str = Field(min_length=1, max_length=3000)
    source_refs: list[str] = Field(min_length=1, max_length=12)
    rubric: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def fixed_answer_is_valid(self):
        if any(not label.strip() or len(label)>1000 for label in self.options+self.left+self.rubric):
            raise ValueError('Labels and rubric criteria must be nonempty and bounded')
        if self.kind in {'mcq','ordering'} and self.left:
            raise ValueError('MCQ/ordering must not have matching left items')
        if self.kind in {'cloze','short_answer'} and (self.options or self.left):
            raise ValueError('Cloze/short answer uses a text response, not choice/matching payloads')
        if self.kind=='cloze' and len(re.findall(r'_{3,}', self.prompt))!=1:
            raise ValueError('Cloze requires exactly one blank written as ____')
        if self.kind=='short_answer' and not self.rubric:
            raise ValueError('Short answer requires a reference rubric')
        if self.kind == "mcq":
            if len(self.options) < 2 or len(set(self.options)) != len(self.options) or self.answer not in self.options:
                raise ValueError("MCQ must have distinct options and an answer from those options")
            verify_mcq_options({'kind': self.kind, 'prompt': self.prompt, 'options': self.options, 'answer': self.answer})
        elif self.kind in {"ordering", "matching"}:
            n = len(self.options)
            if n < 2 or len(set(self.options)) != n or not isinstance(self.answer, list) or sorted(self.answer) != list(range(n)):
                raise ValueError("Ordering/matching answer must be a permutation of option indices")
            if self.kind == "matching" and (len(self.left) != n or len(set(self.left)) != n):
                raise ValueError("Matching must have the same number of distinct left and right items")
        elif not isinstance(self.answer, str) or not self.answer.strip():
            raise ValueError("Cloze/short answer requires a nonempty reference")
        return self


class Question(QuestionContent):
    # Persisted metadata belongs to the creator/server, not the AI draft DTO.
    difficulty: Literal['basic', 'applied', 'hard'] | None = None
    difficulty_basis: Literal['creator_request_not_measured'] | None = None


class Lesson(Model):
    title: str = Field(min_length=1, max_length=200)
    sections: list[Section] = Field(min_length=1, max_length=6)
    questions: list[Question] = Field(min_length=1, max_length=8)
    cards: list[Card] = Field(min_length=1, max_length=6)
    mindmap: list[Section] = Field(min_length=1, max_length=6)


class LessonReading(Model):
    title: str = Field(min_length=1, max_length=200)
    sections: list[Section] = Field(min_length=1, max_length=6)
    cards: list[Card] = Field(min_length=1, max_length=6)
    mindmap: list[Section] = Field(min_length=1, max_length=6)


class McqQuestion(QuestionContent):
    kind: Literal["mcq"]
    options: list[str] = Field(min_length=2, max_length=8)
    left: list[str] = Field(default_factory=list, max_length=0)
    answer: str


class ClozeQuestion(QuestionContent):
    kind: Literal["cloze"]
    options: list[str] = Field(default_factory=list, max_length=0, description='Always []; a cloze uses one typed answer, never choices.')
    left: list[str] = Field(default_factory=list, max_length=0)
    answer: str


class MatchingQuestion(QuestionContent):
    kind: Literal["matching"]
    options: list[str] = Field(min_length=2, max_length=8)
    left: list[str] = Field(min_length=2, max_length=8)
    answer: list[StrictInt]


class OrderingQuestion(QuestionContent):
    kind: Literal["ordering"]
    options: list[str] = Field(min_length=2, max_length=8)
    left: list[str] = Field(default_factory=list, max_length=0)
    answer: list[StrictInt]


class ShortQuestion(QuestionContent):
    kind: Literal["short_answer"]
    options: list[str] = Field(default_factory=list, max_length=0)
    left: list[str] = Field(default_factory=list, max_length=0)
    rubric: list[str] = Field(min_length=1, max_length=6)
    answer: str


class QuestionDraft(Model):
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def explain_insufficient_source(self):
        if self.question is None and not self.reason.strip():
            raise ValueError("Explain the missing source when a question cannot be created")
        return self


QUESTION_DRAFTS = {
    kind: create_model(kind.title().replace("_", "") + "Draft", __base__=QuestionDraft, question=(schema | None, ...))
    for kind, schema in [("mcq", McqQuestion), ("cloze", ClozeQuestion), ("matching", MatchingQuestion), ("ordering", OrderingQuestion), ("short_answer", ShortQuestion)]
}


class OutlineUnit(Model):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=1000)
    source_refs: list[str] = Field(min_length=1, max_length=12)
    # Optional grouping shown on the progress path; empty for older outlines.
    chapter: str = Field(default='', max_length=120)


class Outline(Model):
    title: str = Field(min_length=1, max_length=200)
    units: list[OutlineUnit] = Field(min_length=1, max_length=MAX_UNITS)


class ChatReply(Model):
    text: str = Field(min_length=1, max_length=4000)
    source_refs: list[str] = Field(default_factory=list, max_length=12)
    needs_more_source: bool


class SourceReferenceError(ValueError):
    code = 'SOURCE_REFERENCE_MISMATCH'

    def __init__(self, references):
        self.details = {'invalid_ref_count':len(references),
                        'candidate_ref_hashes':[hashlib.sha256(str(ref).encode()).hexdigest() for ref in references[:12]]}
        super().__init__('AI dẫn mã trích đoạn ngoài phạm vi nguồn của bài đã duyệt. Phần đã lưu vẫn còn; chưa sử dụng đầu ra này.')


def validate_refs(value, allowed):
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_refs" and (not isinstance(item, list) or any(ref not in allowed for ref in item)):
                raise SourceReferenceError([ref for ref in item if ref not in allowed] if isinstance(item,list) else ['invalid_ref_list'])
            validate_refs(item, allowed)
    elif isinstance(value, list):
        for item in value:
            validate_refs(item, allowed)


def grade(question, answer):
    kind = question["kind"]
    if kind == "short_answer":
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 3000:
            raise ValueError("Nhập câu trả lời tự luận ngắn.")
        correct = None
    elif kind in {"ordering", "matching"}:
        if not isinstance(answer, list) or any(type(x) is not int for x in answer) or sorted(answer) != list(range(len(question["options"]))):
            raise ValueError("Mỗi mục phải được chọn đúng một lần.")
        correct = answer == question["answer"]
    else:
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 3000:
            raise ValueError("Nhập hoặc chọn một câu trả lời.")
        if kind == "mcq" and answer not in question["options"]:
            raise ValueError("Đáp án không thuộc các lựa chọn.")
        correct = (answer.strip().casefold() == question["answer"].strip().casefold())
        if kind == "cloze" and not correct:
            def number(text):
                text = text.strip().replace("−", "-")
                if len(text) > 128 or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3}|/\d+)?", text):
                    return None
                exponent = re.search(r"[eE]([+-]?\d+)$", text)
                if exponent and abs(int(exponent.group(1))) > 128:
                    return None
                try:
                    return Fraction(text)
                except (ValueError, ZeroDivisionError):
                    return None
            expected, submitted = number(question["answer"]), number(answer)
            correct = expected is not None and submitted is not None and submitted == expected
    return {"correct": correct, "reference": question["answer"], "explanation": question["explanation"], "rubric": question.get("rubric", []), "source_refs": question["source_refs"], "grading": "fixed" if correct is not None else "self_review"}
