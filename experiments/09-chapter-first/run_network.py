"""One bounded chapter-context development trial; no failed-job regeneration."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE_ID = '052156e88ce448c29c6569576cdb5eac'
MODEL = 'local:gemma4:12b-mlx'


def stamp(): return datetime.now(timezone.utc).isoformat()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='network-local');args=parser.parse_args()
    if not args.run_id.replace('-','').isalnum():raise SystemExit('Use an alphanumeric run ID.')
    output = HERE/'results'/(args.run_id+'.json')
    if output.exists(): raise SystemExit('Trial already exists. Inspect saved job IDs instead of generating again.')
    output.parent.mkdir(parents=True, exist_ok=True)
    private = ROOT/'backend/runtime/chapter-first'/(args.run_id+'.json')
    private.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro', uri=True) as db:
        if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
            raise SystemExit('Another app job is running; no trial submitted.')
        row = db.execute('SELECT revision,content_json FROM extraction_revisions WHERE source_id=? AND reviewed_at IS NOT NULL ORDER BY revision DESC LIMIT 1', (SOURCE_ID,)).fetchone()
        fragments = json.loads(row[1]); revision = row[0]
    text = '\n'.join(f"[Trang {f['locator']['page']}] "+f['text'].replace('\n',' ') for f in fragments)
    page_numbers = sorted({f['locator']['page'] for f in fragments})
    if page_numbers != list(range(1,34)):raise SystemExit('Expected33 source pages; no silent narrower scope.')
    report = {'purpose':'Chapter-first development trial using all33 pages of the stored PDF text transcript; not an OCR or independent academic-quality evaluation.', 'run_id':args.run_id,
              'started_at':stamp(), 'origin_source_id':SOURCE_ID, 'origin_extraction_revision':revision,
              'origin_pdf_sha256':hashlib.sha256((ROOT/'backend/runtime/sources'/SOURCE_ID).read_bytes()).hexdigest(),
              'input_transcript_sha256':hashlib.sha256(text.encode()).hexdigest(), 'origin_pages':page_numbers,
              'source_limit':'The original native transcript omits image-only content, including the subnet-mask table on page24. Reading coverage is over the approved text, not proof of reading every diagram or table correctly.',
              'model':MODEL,'limits':{'jobs':8,'seconds':900,'automatic_failure_retries':0},
              'external_inference':0,'payments':0,'human_reviewed':False,'jobs':[]}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    began=time.monotonic()
    with httpx.Client(base_url='http://127.0.0.1:8770',timeout=30,trust_env=False) as client:
        def request(method,path,body=None,headers=None):
            response=client.request(method,'/api'+path,json=body,headers=headers)
            response.raise_for_status();return response.json()
        paths=client.get('/openapi.json').json()['paths']
        if '/api/courses/{course_id}/chapter-context' not in paths:raise SystemExit('Server has not loaded chapter-first code; no QA profile created.')
        profile=request('POST','/session');report['qa_owner_id']=profile['id']
        private.touch(mode=0o600);private.write_text(json.dumps(dict(client.cookies))+'\n');private.chmod(0o600)
        catalog=request('GET','/ai/models');report['default_model_before']=catalog['default_model_id']
        request('PUT','/ai/selection',{'model_id':MODEL,'expected_revision':catalog['selection_revision'],'allow_external':False})
        source=request('POST','/sources/text',{'name':'QA chương IP — bản trích chữ33trang PDF','text':text})
        source=request('POST','/sources/'+source['id']+'/review',{'expected_revision':source['revision'],'texts':[f['text'] for f in source['fragments']]})
        report.update(source_id=source['id'],source_characters=sum(len(f['text']) for f in source['fragments']),source_fragments=len(source['fragments']))
        preferences={'source_id':source['id'],'expected_extraction_revision':source['revision'],'subject':'Mạng máy tính — toàn chương IP và subnet',
                     'goal':'Hiểu quan hệ prefix, network, broadcast, số host và áp dụng tính subnet; không hỏi thuộc lòng chữ trên slide.',
                     'language':'vi','fragment_ids':[f['id'] for f in source['fragments']],'unlock_policy':'open',
                     'question_types':['mcq','cloze','short_answer'],'question_count':3,'card_count':2,'difficulty':'applied',
                     'terms_to_keep':['prefix','network','broadcast','subnet mask']}
        plan=request('POST','/plans/from-source-sections',preferences)
        # Focus the final exercise while context preparation still reads every
        # approved page, including the principles earlier in the chapter.
        units=plan['outline']['units']
        tail_id=next(f['id'] for f in reversed(source['fragments']) if '[Trang 33]' in f['text'])
        target=next(u for u in units if tail_id in u['source_refs'])
        target['title']='Vận dụng prefix để tìm subnet và số host'
        target['objective']='Vận dụng các nguyên lý đã đọc trong toàn chương để tính network, broadcast và số host dùng được, giải thích điều kiện sử dụng; lấy bài tập cuối chương làm trọng tâm.'
        edited=request('PUT','/plans/'+plan['id'],{'expected_version':plan['outline']['version'],'outline':{k:plan['outline'][k] for k in ('title','units')}})
        cid=request('POST','/plans/'+plan['id']+'/approve',{'expected_revision':edited['outline']['version']})['course_id']
        course=request('GET','/courses/'+cid+'/editor')
        unit=next(u for u in course['content']['units'] if tail_id in u['source_refs'])
        report.update(course_id=cid,unit_id=unit['id'],unit_source_refs=unit['source_refs'],wallet_before=request('GET','/wallet'))
        save()
        try:
            for batch in range(8):
                if time.monotonic()-began>660:raise RuntimeError('Wall budget reached before another200-second job.')
                body={'expected_revision':course['revision'],'unit_id':unit['id']}
                headers={'Idempotency-Key':'chapter-'+args.run_id+'-'+str(batch)}
                response=client.post('/api/courses/'+cid+'/generate',json=body,headers=headers)
                if response.status_code==402:
                    quote=response.json()['detail']
                    if quote['amount']>8:raise RuntimeError('Unexpected QA Coin quote; no confirmation.')
                    headers['Coin-Quote-Id']=quote['quote_id'];response=client.post('/api/courses/'+cid+'/generate',json=body,headers=headers)
                response.raise_for_status();jid=response.json()['job_id']
                item={'id':jid,'batch':batch+1,'submitted_at':stamp(),'events':[]};report['jobs'].append(item);save()
                last=None
                while True:
                    job=request('GET','/jobs/'+jid);p=job.get('progress') or {};chapter=p.get('chapter_context')
                    event={'status':job['status'],'phase':p.get('phase'),'chapter':chapter,'saved_stages':p.get('saved_stages')}
                    if event!=last:
                        item['events'].append({**event,'at':stamp()});last=event;save()
                        if chapter:print(json.dumps({'batch':batch+1,'status':job['status'],'reading':chapter['read_parts'],'parts':chapter['total_parts'],'context_complete':chapter['complete']},ensure_ascii=False),flush=True)
                    if job['status'] in {'succeeded','failed','cancelled'}:break
                    if time.monotonic()-began>895:
                        request('POST','/jobs/'+jid+'/cancel');raise RuntimeError('Trial wall limit; cancelled only its own job.')
                    time.sleep(.7)
                item['job']=job;save()
                if job['status']!='succeeded':raise RuntimeError('Trial job did not complete; preserved failure without retry.')
                current=request('GET','/courses/'+cid+'/editor')
                if job['result'].get('continuation_required'):
                    if current['revision']!=course['revision'] or any(u.get('data') for u in current['content']['units']):raise RuntimeError('Intermediate reading unexpectedly published content.')
                    continue
                course=current;break
            else:raise RuntimeError('Finite8-job trial bound reached; no unbounded continuation.')
            report['chapter_context']=request('GET','/courses/'+cid+'/chapter-context?unit_id='+unit['id'])
            report['course_snapshot']=course;report['wallet_after']=request('GET','/wallet')
            with sqlite3.connect('file:'+str(ROOT/'backend/runtime/study.sqlite3')+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT manifest_json,nodes_json FROM chapter_contexts WHERE id=? AND owner_id=?',(report['chapter_context']['context_id'],profile['id'])).fetchone()
                report['context_manifest']=json.loads(row[0]);report['context_nodes']=json.loads(row[1])
            root=report['context_manifest']['root'];root_at=report['context_nodes'][root]['created_at']
            question_requests=[r for item in report['jobs'] for r in item['job']['progress']['requests'] if r['schema'].endswith('Draft')]
            report['questions_started_after_full_context']=bool(question_requests) and all(r['started_at']>root_at for r in question_requests)
            report['default_model_after']=request('GET','/ai/models')['default_model_id']
            report['status']='completed';report['elapsed_seconds']=round(time.monotonic()-began,3)
        except Exception as exc:
            report.update(status='failed',error=str(exc),elapsed_seconds=round(time.monotonic()-began,3))
            raise
        finally:report['finished_at']=stamp();save()
    print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds'],'questions_after_full_context':report.get('questions_started_after_full_context')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
