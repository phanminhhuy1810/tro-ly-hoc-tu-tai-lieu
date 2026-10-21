"""Owned source pages and keyword selection over immutable extraction revisions."""
import base64
import binascii
import hashlib
import json
import re
import unicodedata
from typing import Literal

from fastapi import Depends, HTTPException, Query

from .source_limits import MAX_FRAGMENTS


LocationKind = Literal['page', 'slide', 'frame', 'line', 'paragraph']
ACTIVE_SOURCE = "NOT EXISTS(SELECT 1 FROM resource_lifecycle x WHERE x.resource_type='source' AND x.resource_id=s.id AND x.deleted_at IS NOT NULL)"
JOIN = '''FROM sources s JOIN source_library_entries l ON l.source_id=s.id
          LEFT JOIN extraction_revisions e ON e.source_id=s.id AND
              e.revision=(SELECT max(x.revision) FROM extraction_revisions x WHERE x.source_id=s.id)'''


def folded(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold()).replace('đ', 'd')
    return ''.join(char for char in value if not unicodedata.combining(char))


def clean_query(value):return ' '.join(value.split())
def like_literal(value):return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def scope_key(owner, query, reviewed, limit):
    value = [owner, folded(query), reviewed, limit]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def encode_cursor(upper, after, scope):
    raw = json.dumps({'v':1,'upper':upper,'after':after,'scope':scope}, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(token, scope):
    try:
        if not isinstance(token, str) or len(token)>2048 or not re.fullmatch('[A-Za-z0-9_-]+',token):raise ValueError()
        value = json.loads(base64.b64decode(token+'='*(-len(token)%4), altchars=b'-_', validate=True))
        if not isinstance(value,dict) or set(value)!={'v','upper','after','scope'} or type(value['v']) is not int or value['v']!=1 or value['scope']!=scope:raise ValueError()
        for key in ('upper','after'):
            item=value[key]
            if key=='after' and item is None:continue
            if not isinstance(item,str) or not 1<=len(item)<=128 or any(char.isspace() for char in item):raise ValueError()
        return value
    except (ValueError,TypeError,KeyError,UnicodeError,binascii.Error):
        raise HTTPException(422,{'code':'INVALID_SOURCE_CURSOR','message':'Con trỏ không khớp danh sách, từ khóa hoặc cỡ trang. Tải lại trang đầu.'}) from None


def snippet(text, tokens, size=360):
    if len(text)<=size:return text
    index=0
    if tokens:
        characters=[];mapping=[]
        for offset,char in enumerate(text):
            value=folded(char);characters.append(value);mapping.extend([offset]*len(value))
        search=''.join(characters)
        matches=[search.find(token) for token in tokens if search.find(token)>=0]
        if matches:index=mapping[min(matches)]
    start=max(0,index-90);end=min(len(text),start+size)
    while start>0 and unicodedata.combining(text[start]):start-=1
    while end<len(text) and unicodedata.combining(text[end]):end+=1
    return ('…' if start else '')+text[start:end]+('…' if end<len(text) else '')


class SourceLibrary:
    def __init__(self,database,source_snapshot):
        self.database,self.source_snapshot=database,source_snapshot

    def page(self,owner,q='',reviewed=None,limit=20,cursor=None):
        query=clean_query(q);scope=scope_key(owner,query,reviewed,limit)
        decoded=decode_cursor(cursor,scope) if cursor else None
        with self.database.connection() as db:
            db.create_function('study_fold',1,folded,deterministic=True)
            if decoded:
                upper=db.execute('SELECT l.sequence,s.id FROM source_library_entries l JOIN sources s ON s.id=l.source_id WHERE s.owner_id=? AND s.id=? AND '+ACTIVE_SOURCE,(owner,decoded['upper'])).fetchone()
                after=db.execute('SELECT l.sequence FROM source_library_entries l JOIN sources s ON s.id=l.source_id WHERE s.owner_id=? AND s.id=? AND '+ACTIVE_SOURCE,(owner,decoded['after'])).fetchone() if decoded['after'] else None
                if not upper or (decoded['after'] and (not after or after['sequence']>upper['sequence'])):
                    raise HTTPException(409,{'code':'SOURCE_CURSOR_EXPIRED','message':'Danh sách đã thay đổi. Tải lại trang đầu; tài liệu đã lưu vẫn còn.'})
            else:
                upper=db.execute('SELECT l.sequence,s.id FROM source_library_entries l JOIN sources s ON s.id=l.source_id WHERE s.owner_id=? AND '+ACTIVE_SOURCE+' ORDER BY l.sequence DESC LIMIT 1',(owner,)).fetchone()
                after=None
            if not upper:
                return {'items':[],'total':0,'library_total':0,'query':query,'reviewed':reviewed,'limit':limit,'current_cursor':None,'next_cursor':None,'has_more':False}
            clauses=['s.owner_id=?','l.sequence<=?',ACTIVE_SOURCE];args=[owner,upper['sequence']]
            for token in folded(query).split():
                clauses.append("study_fold(json_extract(s.metadata_json,'$.name')) LIKE ? ESCAPE '\\'");args.append(like_literal(token))
            if reviewed is not None:clauses.append('e.reviewed_at IS '+('NOT NULL' if reviewed else 'NULL'))
            where=' WHERE '+' AND '.join(clauses)
            total=db.execute('SELECT count(*) '+JOIN+where,args).fetchone()[0]
            library_total=db.execute('SELECT count(*) FROM sources s JOIN source_library_entries l ON l.source_id=s.id WHERE s.owner_id=? AND l.sequence<=? AND '+ACTIVE_SOURCE,(owner,upper['sequence'])).fetchone()[0]
            page_where=where+(' AND l.sequence<?' if after else '')
            page_args=args+([after['sequence']] if after else [])+[limit+1]
            rows=db.execute('''SELECT s.id,s.status,s.created_at,l.sequence,
                       json_extract(s.metadata_json,'$.name') AS name,
                       coalesce(json_extract(s.metadata_json,'$.kind'),'file') AS kind,
                       coalesce(json_extract(s.metadata_json,'$.bytes'),0) AS bytes,
                       coalesce(json_array_length(s.metadata_json,'$.warnings'),0) AS warning_count,
                       e.revision,e.reviewed_at '''+JOIN+page_where+' ORDER BY l.sequence DESC LIMIT ?',page_args).fetchall()
            has_more=len(rows)>limit;rows=rows[:limit]
            items=[{'id':row['id'],'metadata':{'name':row['name'],'kind':row['kind'],'bytes':row['bytes']},
                    'status':row['status'],'created_at':row['created_at'],'revision':row['revision'] or 0,
                    'reviewed':bool(row['reviewed_at']),'warning_count':row['warning_count']} for row in rows]
            return {'items':items,'total':total,'library_total':library_total,'query':query,'reviewed':reviewed,'limit':limit,
                    'current_cursor':encode_cursor(upper['id'],decoded['after'] if decoded else None,scope),
                    'next_cursor':encode_cursor(upper['id'],items[-1]['id'],scope) if has_more else None,'has_more':has_more}

    def excerpts(self,owner,source_id,revision,q='',location_kind=None,position=None,component_id=None,offset=0,limit=20,selection=False):
        query=clean_query(q);tokens=folded(query).split()
        with self.database.connection() as db:
            source=self.source_snapshot(db,source_id,owner,revision)
            latest=db.execute('SELECT max(revision) FROM extraction_revisions WHERE source_id=?',(source_id,)).fetchone()[0]
        found=[]
        for index,fragment in enumerate(source['fragments']):
            locator=fragment['locator']
            if component_id and locator.get('component_source_id')!=component_id:continue
            if location_kind and location_kind not in locator:continue
            if position is not None:
                positions=[locator.get(location_kind)] if location_kind else [locator.get(key) for key in ('page','slide','frame','line','paragraph')]
                if position not in positions:continue
            search=folded(fragment['text']+' '+str(locator.get('heading',''))+' '+str(locator.get('component_name','')))
            if all(token in search for token in tokens):found.append((index,fragment))
        result={'source_id':source_id,'revision':revision,'latest_revision':latest,'reviewed':source['reviewed'],
                'query':query,'location_kind':location_kind,'position':position,'component_id':component_id,
                'total_fragments':len(source['fragments']),'matched_fragments':len(found),'search_method':'literal_keywords_not_ai'}
        if selection:
            if len(found)>MAX_FRAGMENTS:raise HTTPException(422,'Phạm vi vượt giới hạn số đoạn; chia tài liệu để chọn nguồn.')
            result['fragment_ids']=[fragment['id'] for _,fragment in found]
        else:
            result.update(offset=offset,limit=limit,items=[{'id':fragment['id'],'index':index,'text':fragment['text'],
                'snippet':snippet(fragment['text'],tokens),'locator':fragment['locator'],
                'needs_review':bool(fragment.get('needs_review',True)),'edited_by_user':bool(fragment.get('edited_by_user'))}
                for index,fragment in found[offset:offset+limit]])
        return result


def register_source_library(app,database,source_snapshot,user):
    store=SourceLibrary(database,source_snapshot)
    @app.get('/api/sources/{source_id}/scope-review')
    def scope_review(source_id:str,revision:int=Query(ge=1),owner=Depends(user)):
        from .source_scope_review import review
        with database.connection() as db:
            source=source_snapshot(db,source_id,owner,revision)
            latest=db.execute('SELECT max(revision) FROM extraction_revisions WHERE source_id=?',(source_id,)).fetchone()[0]
        return {**review(source),'latest_revision':latest}

    @app.get('/api/source-library')
    def library(q:str=Query(default='',max_length=120),reviewed:bool|None=None,
                limit:int=Query(default=20,ge=1,le=100),cursor:str|None=Query(default=None,max_length=2048),owner=Depends(user)):
        return store.page(owner,q,reviewed,limit,cursor)

    @app.get('/api/sources/{source_id}/fragments')
    def excerpts(source_id:str,revision:int=Query(ge=1),q:str=Query(default='',max_length=120),
                 location_kind:LocationKind|None=None,position:int|None=Query(default=None,ge=1,le=1_000_000),
                 component_id:str|None=Query(default=None,min_length=1,max_length=128),
                 offset:int=Query(default=0,ge=0,le=MAX_FRAGMENTS),limit:int=Query(default=20,ge=1,le=100),owner=Depends(user)):
        return store.excerpts(owner,source_id,revision,q,location_kind,position,component_id,offset,limit)

    @app.get('/api/sources/{source_id}/fragment-selection')
    def selection(source_id:str,revision:int=Query(ge=1),q:str=Query(default='',max_length=120),
                  location_kind:LocationKind|None=None,position:int|None=Query(default=None,ge=1,le=1_000_000),
                  component_id:str|None=Query(default=None,min_length=1,max_length=128),owner=Depends(user)):
        return store.excerpts(owner,source_id,revision,q,location_kind,position,component_id,selection=True)
    app.state.source_library=store
    return store
