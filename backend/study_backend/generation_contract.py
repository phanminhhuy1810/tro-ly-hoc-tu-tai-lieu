"""Small per-kind model contracts; stored question/history DTOs stay unchanged."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import re
from typing import get_args

from pydantic import Field, create_model, model_validator

from .models import Model, QuestionDraft, QUESTION_DRAFTS, validate_refs
from .ordering import derive_generated_ordering, OrderingSourceError
from .cloze import ClozeSourceError, mask_source_statement, mask_source_excerpt
from .structured_output import validated_json
from .polynomial_questions import verify_composition, CompositionError


_PAYLOAD_FIELDS = {
    'mcq': {'options'},
    'cloze': set(),
    'matching': {'options', 'left'},
    'ordering': {'options'},
    'short_answer': {'rubric'},
}
GENERATION_PROCESSOR_VERSION = '20261021-polynomial-composition-proof-v13'


class GenerationEnvelope(Model):
    # Nullable reason is an empty, non-content field beside a valid question.
    # A declined question must still supply a real reason.
    reason: str | None = Field(default='',max_length=1000)

    @model_validator(mode='after')
    def decline_needs_reason(self):
        if self.question is None and (self.reason is None or not self.reason.strip()):
            raise ValueError('Explain the missing source when a question cannot be created')
        return self


class CandidateReason(ValueError):
    def __init__(self,code,message):
        super().__init__(message);self.code=code


class QuestionRejected(ValueError):
    """A bounded source-proof rejection, distinguishable from provider failure."""
    def __init__(self, cause, candidate):
        super().__init__(str(cause))
        self.code = cause.code
        self.details = {'origin':'backend_question_validation', 'code':cause.code,
                        'reason':str(cause), 'source_refs':candidate['source_refs'],
                        'candidate_sha256':hashlib.sha256(json.dumps(candidate,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


@lru_cache(maxsize=32)
def generation_schema(schema):
    """Do not ask a text-response model to fill choice/matching-only fields."""
    kind = next((k for k, value in QUESTION_DRAFTS.items() if value is schema), None)
    if kind is None:
        return schema
    question = next(cls for cls in get_args(schema.model_fields['question'].annotation) if cls is not type(None))
    omitted = {'options', 'left', 'rubric'} - _PAYLOAD_FIELDS[kind]
    if kind == 'ordering':omitted.add('answer')
    fields = {name: (field.annotation, deepcopy(field))
              for name, field in question.model_fields.items() if name not in omitted}
    if kind=='cloze':fields['prompt']=(str|None,Field(default=None,min_length=1,max_length=1000,description='Write your own question with exactly one ____ blank, grounded in the chapter principles. Null remains supported for legacy source quotations.'))
    wire_question = create_model(question.__name__ + 'Output', __base__=Model, **fields)
    return create_model(schema.__name__ + 'Output', __base__=GenerationEnvelope,
                        question=(wire_question | None, ...))


def question_fields(kind):
    schema = generation_schema(QUESTION_DRAFTS[kind])
    question = next(cls for cls in get_args(schema.model_fields['question'].annotation) if cls is not type(None))
    return tuple(question.model_fields)


def validated_generation(schema, text, progress=None, fragments=None):
    wire = generation_schema(schema)
    value = validated_json(wire, text, progress)
    # Empty non-applicable containers are domain defaults, not model content.
    # Unexpected wire fields are rejected above, including empty containers;
    # never delete an invalid model field or alter an answer to make it pass.
    if wire is schema:return value
    content = value.model_dump()
    if content['question'] is not None and content['reason'] is None:
        content['reason']=''
        if progress:progress.usage({'question_empty_reason_normalized':1})
    if schema is QUESTION_DRAFTS['mcq'] and content['question'] is not None:
        candidate=content['question']
        if fragments is not None:validate_refs(candidate,{f['id'] for f in fragments})
        if len(set(candidate['options']))!=len(candidate['options']) or candidate['answer'] not in candidate['options']:
            issue=CandidateReason('MCQ_KEY_OR_CHOICES_INVALID','Ứng viên trắc nghiệm có lựa chọn lặp hoặc đáp án không thuộc lựa chọn; chưa dùng câu này. Không tự đoán đáp án thay AI.')
            if progress:progress.usage({'mcq_candidate_rejected':1})
            raise QuestionRejected(issue,candidate)
        try:
            verify_composition(candidate)
        except CompositionError as exc:
            if progress: progress.usage({'mcq_candidate_rejected': 1})
            raise QuestionRejected(exc, candidate) from exc
    if schema is QUESTION_DRAFTS['cloze'] and content['question'] is not None:
        # Unknown/foreign references are still a hard validation failure, even
        # when this particular candidate would otherwise be declined.
        if fragments is not None:validate_refs(value, {f['id'] for f in fragments})
        prompt=content['question']['prompt']
        if prompt is None or not re.search(r'_{3,}',prompt):
            constructor=mask_source_excerpt if prompt is None else mask_source_statement
            try:
                content['question'],statement_hash=constructor(content['question'],fragments)
            except ClozeSourceError as exc:
                if progress:progress.usage({'cloze_candidate_rejected':1})
                raise QuestionRejected(exc,content['question']) from exc
            if progress:progress.usage({'cloze_source_mask_derived':1,'cloze_statement_sha256':statement_hash})
    if schema is QUESTION_DRAFTS['ordering'] and content['question'] is not None:
        if fragments is None:raise ValueError('Ordering generation requires the pinned source to derive its answer.')
        validate_refs(value,{f['id'] for f in fragments})
        raw_options = content['question']['options']
        try:
            content['question'], removed = derive_generated_ordering(content['question'], fragments)
        except OrderingSourceError as exc:
            if progress:progress.usage({'ordering_candidate_rejected':1})
            raise QuestionRejected(exc,content['question']) from exc
        if progress:progress.usage({'ordering_answer_derived':1,'ordering_answer_method':'explicit_scoped_source_steps_v2',
                                    'ordering_step_labels_removed':removed,
                                    'ordering_model_options_sha256':hashlib.sha256(json.dumps(raw_options,ensure_ascii=False).encode()).hexdigest()})
    return schema.model_validate(content)
