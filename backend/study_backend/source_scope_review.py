"""Advisory, source-bound front-matter review. Never excludes text automatically."""
from collections import OrderedDict
import re
from .source_library import folded

VERSION='20261019-front-matter-review-v1'
COPY=re.compile(r'all rights reserved|a note on the use of these (?:powerpoint )?slides|if you use these slides|if you post any slides|slides.{0,60}freely available|copyright\s*(?:©|\(c\))?\s*20\d\d|©\s*20\d\d',re.S)
EDITION=re.compile(r'\b(?:\d+(?:st|nd|rd|th)\s+edition|edition\s+\d+|pearson|springer|university press)\b')
GOALS=re.compile(r'^(?:.{0,75}:\s*)?(?:our goals|learning (?:goals|objectives)|objectives|muc tieu(?: (?:hoc tap|bai hoc|chuong))?)\s*[:.!]?$',re.S)
CONTENTS=re.compile(r'^(?:.{0,75}:\s*)?(?:table of contents|contents|chapter outline|lecture outline|agenda|roadmap|muc luc|noi dung chuong)\s*[:.!]?$')
SUBSTANTIVE=re.compile(r'\b(?:is (?:a|an)|defined as|refers to|duoc dinh nghia|vi du|for example)\b|\s=\s')
REASONS={
 'copyright_notice':('Ghi chú bản quyền/cách sử dụng','Copyright or usage notice'),
 'cover_context':('Cùng trang bìa hoặc thông tin sách','Cover or publication context'),
 'learning_goals':('Mục tiêu học tập ở đầu tài liệu','Opening learning goals'),
 'contents':('Mục lục hoặc chương trình đầu tài liệu','Opening contents or agenda'),
}

def position_key(fragment,source_id):
    loc=fragment['locator'];component=loc.get('component_source_id',source_id)
    for key in ('slide','page'):
        if type(loc.get(key)) is int:return component,key,loc[key]
    return component,'fragment',fragment['id']


def review(source):
    fragments=source['fragments'];pages=OrderedDict()
    for f in fragments:pages.setdefault(position_key(f,source['id']),[]).append(f)
    reasons={}
    for f in fragments:
        if COPY.search(folded(f['text'])):reasons[f['id']]='copyright_notice'
    for (_,kind,position),group in pages.items():
        if kind not in {'slide','page'} or not 1<=position<=3:continue
        text=[folded(' '.join(f['text'].split())) for f in group]
        cover=position==1 and (any(f['id'] in reasons for f in group) or any(EDITION.search(t) for t in text))
        goals=any(len(t)<=120 and GOALS.fullmatch(t) for t in text)
        contents=any(len(t)<=120 and CONTENTS.fullmatch(t) for t in text)
        for f,t in zip(group,text):
            if f['id'] in reasons:continue
            if SUBSTANTIVE.search(t):continue
            if cover and len(t)<=450:reasons[f['id']]='cover_context'
            elif goals and len(t)<=1200:reasons[f['id']]='learning_goals'
            elif contents and len(t)<=1200:reasons[f['id']]='contents'
    groups=[]
    for position,frags in pages.items():
        by_reason=OrderedDict()
        for f in frags:
            reason=reasons.get(f['id'])
            if reason:by_reason.setdefault(reason,[]).append(f['id'])
        for reason,ids in by_reason.items():
            locator=frags[0]['locator'];groups.append({'reason':reason,'title_vi':REASONS[reason][0],'title_en':REASONS[reason][1],
                'component_source_id':locator.get('component_source_id',source['id']),
                'component_name':locator.get('component_name',source['metadata']['name']),
                'location_kind':position[1],'position':position[2] if position[1]!='fragment' else None,'fragment_ids':ids})
    return {'version':VERSION,'source_id':source['id'],'revision':source['revision'],'reviewed':source['reviewed'],
            'total_fragments':len(fragments),'candidate_ids':[f['id'] for f in fragments if f['id'] in reasons],
            'groups':groups,'advisory_only':True,'automatic_changes':False,'ai_called':False,
            'accuracy_not_verified':True}
