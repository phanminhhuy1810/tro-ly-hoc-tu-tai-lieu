"""Bounded original-source support from the already-approved chapter.

Retrieval selects evidence to show the model, not citations to attach on its
behalf. IDs remain model-selected and validated. Relevance is not entailment.
"""
from collections import Counter
import hashlib
import json
import math
import re
import unicodedata

from fastapi import HTTPException

from .source_context import fits
from .reference_wire import ReferenceWire

EVIDENCE_VERSION = '20261021-approved-chapter-support-v1'
MAX_SUPPORT_FRAGMENTS = 4
MAX_INPUT_FRAGMENTS = 12


def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(dump(value).encode()).hexdigest()


def folded(text):
    text=unicodedata.normalize('NFKD',text.casefold()).replace('đ','d')
    return ''.join(c for c in text if not unicodedata.combining(c))


def tokens(text):
    normal=folded(text)
    words=re.findall(r'[a-z]{3,}',normal)
    # Short character shingles let spaced Vietnamese in notes match joined
    # letters from PDFs. Common slide footers receive low/zero IDF weight.
    packed=re.sub(r'[^a-z]','',normal)
    grams=['#'+packed[i:i+4] for i in range(len(packed)-3)]
    return set(words)|set(grams)


def exercise_only(text):
    normal=re.sub(r'\s+','',folded(text))
    exercise=any(cue in normal for cue in ('baitap','haychobiet','haytinh','exercise','question:','findthe','congtymuon','chodiachiip'))
    principle=any(cue in normal for cue in ('quytac','congthuc','dungphandinh','cobang','definedas','isdefined','formula','giunguyen','battatca','hostidve0','hostidlen1'))
    return exercise and not principle


def focus_refs(unit):
    old=unit.get('generation',{}).get('evidence_scope') or {}
    return list(old.get('focus_source_refs') or unit['source_refs'])


def payload(fragments,refs):
    by_id={f['id']:f for f in fragments}
    if len(set(refs))!=len(refs) or not set(refs)<=set(by_id):
        raise HTTPException(409,'Nguồn hỗ trợ không thuộc đúng chương đã duyệt.')
    return [f for f in fragments if f['id'] in set(refs)]


def validate(scope,fragments,unit,context_id):
    """Check an immutable evidence checkpoint before any saved stage is reused."""
    try:
        unsigned={k:v for k,v in scope.items() if k!='sha256'}
        refs=scope['input_source_refs'];focus=scope['focus_source_refs'];support=scope['support_source_refs']
        selected=payload(fragments,refs)
        valid=(scope['sha256']==digest(unsigned) and scope['context_id']==context_id and
               scope['version']==EVIDENCE_VERSION and len(set(focus))==len(focus) and len(set(support))==len(support) and
               focus==focus_refs(unit) and set(unit['source_refs'])<=set(refs) and
               set(focus)|set(support)==set(refs) and not set(focus)&set(support) and
               scope['input_sha256']==digest(selected) and len(refs)<=MAX_INPUT_FRAGMENTS and fits(selected))
    except (KeyError,TypeError,ValueError):
        valid=False
    if not valid:raise HTTPException(409,'Checkpoint nguồn hỗ trợ không khớp chương/bài. Giữ phần đã lưu; chưa thay nguồn hoặc gọi lại.')
    return selected


def select(fragments,unit,preferences,brief,context_id,previous=None):
    if previous:
        return validate(previous,fragments,unit,context_id),previous
    focus=focus_refs(unit)
    existing=list(unit['source_refs'])
    selected=payload(fragments,existing)
    if not set(focus)<=set(existing) or len(existing)>MAX_INPUT_FRAGMENTS or not fits(selected):
        raise HTTPException(422,'Nguồn trọng tâm/đang dùng vượt budget; chưa bỏ nguồn để lấy đoạn hỗ trợ.')
    documents={f['id']:tokens(f['text']) for f in fragments}
    df=Counter(token for terms in documents.values() for token in terms)
    n=len(fragments)
    idf={term:math.log((n+1)/(frequency+.5)) for term,frequency in df.items()}
    local=' '.join([unit['title'],unit['objective'],preferences.get('goal',''),*[f['text'] for f in payload(fragments,focus)]])
    global_text=' '.join([brief.get('summary',''),*brief.get('key_ideas',[]),*brief.get('connections',[]),*brief.get('question_targets',[])])
    local_terms=tokens(local);global_terms=tokens(global_text)
    weights={t:idf[t]*(3 if t in local_terms else 1) for t in (local_terms|global_terms)&set(idf)}
    # Terms in every source paragraph are layout boilerplate, not useful links.
    weights={t:w for t,w in weights.items() if df[t]<n or n==1}
    ranking=[]
    for index,fragment in enumerate(fragments):
        if fragment['id'] in existing:continue
        terms=documents[fragment['id']];overlap=terms&set(weights)
        score=sum(weights[t] for t in overlap)/math.sqrt(max(1,len(terms)))
        if exercise_only(fragment['text']):score*=.25
        if score>0:ranking.append((score,index,fragment))
    chosen=[];omitted=[]
    remaining_slots=max(0,MAX_SUPPORT_FRAGMENTS-len(set(existing)-set(focus)))
    while ranking and len(chosen)<remaining_slots:
        def rank(item):
            score,index,fragment=item
            similarity=max((len(documents[fragment['id']]&documents[old['id']])/max(1,len(documents[fragment['id']]|documents[old['id']])) for old in chosen),default=0)
            return (score*(1-.65*similarity),-index)
        current=max(ranking,key=rank);ranking.remove(current)
        score,_,fragment=current
        candidate=payload(fragments,[*[f['id'] for f in selected],fragment['id']])
        if len(candidate)>MAX_INPUT_FRAGMENTS or not fits(candidate):
            omitted.append({'id':fragment['id'],'reason':'input_budget'});continue
        selected=candidate;chosen.append(fragment)
    refs=[f['id'] for f in selected]
    scope={'version':EVIDENCE_VERSION,'context_id':context_id,'focus_source_refs':focus,
           'support_source_refs':[r for r in refs if r not in focus],'input_source_refs':refs,
           'input_sha256':digest(selected),'query_sha256':digest({'local':local,'global':global_text}),
           'added_support_refs':[f['id'] for f in chosen],'omitted':omitted,
           'relevance_is_not_entailment':True,'ai_calls':0}
    scope['sha256']=digest(scope)
    validate(scope,fragments,unit,context_id)
    return selected,scope


def instruction(scope):
    # Use the same transport labels as the provider, avoiding source/plan UUIDs
    # in prose and eliminating ambiguity between metadata IDs and citations.
    wire=ReferenceWire([{'id':ref} for ref in scope['input_source_refs']])
    labels=lambda refs:[wire.encode[ref] for ref in refs]
    return ('\nPHẠM VI NGUỒN NGUYÊN VĂN CỦA LƯỢT NÀY: '+dump({'trong_tam_bai':labels(scope['focus_source_refs']),'nguyen_ly_ho_tro_trong_chuong':labels(scope['support_source_refs'])})+
            '. Mục tiêu bài và các đoạn trọng tâm quyết định điều cần hỏi; các đoạn hỗ trợ giúp giải thích/căn cứ, không tự chuyển sang dạy một bài khác. '
            'Khi giải một tình huống mới bằng nguyên lý trong nguồn hỗ trợ, source_refs cần trỏ cả nguyên lý đã dùng, không chỉ trang chứa đề bài. '
            'Chỉ trích đúng những đoạn thực sự hỗ trợ phát biểu. Thứ hạng truy hồi không chứng minh nội dung đúng; không bịa lời trích hoặc gắn thêm ID cho có vẻ có nguồn. ')
