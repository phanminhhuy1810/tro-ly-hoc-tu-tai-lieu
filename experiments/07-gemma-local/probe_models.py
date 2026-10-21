"""Small development comparison through the real backend adapter; never a held-out benchmark."""
import argparse
import asyncio
from datetime import datetime,timezone
from fractions import Fraction
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from study_backend.ai import LocalAI
from study_backend.models import ChatReply,LessonReading,QUESTION_DRAFTS,grade
import httpx

NET=(
    'IPv4 có 32 bit, gồm bốn octet, mỗi octet có 8 bit. Prefix /26 dành 26 bit cho network và còn 6 bit host. '
    'Một block /26 có 2^6 = 64 địa chỉ, gồm 62 địa chỉ host dùng được sau khi bỏ network và broadcast. '
    'Với 192.168.1.70/26, block cuối là 64–127. Network là 192.168.1.64; broadcast là 192.168.1.127; '
    'host dùng được từ 192.168.1.65 đến 192.168.1.126.\n'
    '1. Đọc prefix và tính số bit host.\n2. Tính kích thước block.\n3. Xác định block chứa octet cuối.\n'
    '4. Lấy đầu block làm network và cuối block làm broadcast.\n5. Loại hai biên để lấy dải host dùng được.'
)
CASES=[
    ('networking','net:0',NET,'Với 192.168.1.70/26 trong nguồn, network address là gì? Chỉ dùng địa chỉ IPv4 làm các lựa chọn.','192.168.1.64'),
    ('calculus','calc:0','Với f(x)=x^2, một nguyên hàm là x^3/3. Tích phân từ 0 đến 1 của x^2 dx bằng 1/3. Diện tích dưới đường y=x^2 trên [0,1] là 1/3.',
     'Tích phân từ 0 đến 1 của x^2 dx bằng bao nhiêu? Chỉ dùng phân số dạng a/b hoặc số nguyên làm lựa chọn.','1/3'),
    ('psychology','psy:0','Working memory (trí nhớ làm việc) duy trì và xử lý thông tin tạm thời trong lúc làm nhiệm vụ. Long-term memory lưu thông tin dài hạn. Hai khái niệm này không đồng nhất.',
     'Theo nguồn, tên thuật ngữ tiếng Anh nào chỉ hệ thống duy trì và xử lý thông tin tạm thời khi làm nhiệm vụ? Chỉ dùng tên thuật ngữ tiếng Anh làm lựa chọn.','working memory'),
]


class Progress:
    def __init__(self):self.started=time.monotonic();self.first=None;self.fallbacks=0;self.tokens={};self.characters=0
    def chunk(self,text):
        if text and self.first is None:self.first=round(time.monotonic()-self.started,3)
        self.characters+=len(text)
    def fallback(self):self.fallbacks+=1
    def usage(self,value):self.tokens.update(value)
    def summary(self):
        return {'first_content_seconds':self.first,'completed_seconds':round(time.monotonic()-self.started,3),
                'protocol_fallbacks':self.fallbacks,'content_characters':self.characters,'usage':self.tokens}


def ensure_idle():
    with sqlite3.connect(ROOT/'backend/runtime/study.sqlite3') as db:
        if db.execute("select count(*) from jobs where status in ('queued','running') and task!='source_ocr'").fetchone()[0]:
            raise RuntimeError('App AI job is active; no benchmark inference or unload will be sent.')


def fragment(ref,text):return [{'id':ref,'text':text,'locator':{'type':'self_authored_development'}}]


async def probe(client,tag,kind,schema,prompt,fragments,report,expected=None):
    ensure_idle()
    progress=Progress();run={'model':tag,'task':kind,'source_ids':[f['id'] for f in fragments],
                             'instruction':prompt,'status':'running','expected':expected}
    report['runs'].append(run)
    try:
        value=await client.generate_stream(schema,prompt,fragments,progress)
        run.update(status='succeeded',output=value)
        if kind=='term_cold':
            assert not value['needs_more_source'] and set(value['source_refs'])=={f['id'] for f in fragments},'Missing citation or unnecessary source decline'
        if expected is not None:
            q=value['question'];assert q is not None,'Model declined a question with sufficient source'
            answer=q['answer'].strip().casefold()
            if kind=='mcq_networking':correct=ipaddress.ip_address(answer)==ipaddress.ip_network('192.168.1.70/26',strict=False).network_address
            elif kind=='mcq_calculus':correct=Fraction(answer)==Fraction(expected)
            else:correct=answer==expected
            run['fixed_fact_correct']=correct
            run['deterministic_grade']=grade(q,q['answer'])
            assert correct,'Answer differs from the known self-authored development fact'
    except Exception as exc:
        run.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:1400],
                   error_classification='known_fact_or_instruction' if isinstance(exc,AssertionError) else 'provider_or_validation')
    run.update(progress.summary());print(json.dumps({k:run.get(k) for k in ['model','task','status','first_content_seconds','completed_seconds','fixed_fact_correct','error_type']}),flush=True)


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+',default=['qwen3.5:9b','gemma4:12b-mlx']);args=parser.parse_args()
    out=ROOT/'experiments/07-gemma-local/results';out.mkdir(exist_ok=True)
    target=out/('adapter-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    report={'purpose':'Small self-authored development probes, not held-out/human/throughput benchmark',
            'started_at':datetime.now(timezone.utc).isoformat(),'models':args.models,'runs':[],
            'sampling':{'temperature':.2,'think':False,'num_ctx':16384,'limits':'unchanged LocalAI adapter'},
            'source_texts':{ref:text for _,ref,text,_,_ in CASES},'automatic_semantic_retries':0,'external_ai_calls':0}
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    try:
        async with httpx.AsyncClient(timeout=20,trust_env=False) as transport:
            tags=(await transport.get('http://127.0.0.1:11434/api/tags')).json()['models'];installed={v['name']:v for v in tags}
            if not set(args.models)<=set(installed):raise RuntimeError('Requested model is not installed; do not silently download or substitute.')
            with sqlite3.connect(ROOT/'backend/runtime/study.sqlite3') as db:
                if db.execute("select count(*) from jobs where status in ('queued','running') and task!='source_ocr'").fetchone()[0]:
                    raise RuntimeError('An app AI job is active; defer the comparison to avoid interference.')
            report['installed']={name:installed[name] for name in args.models}
            report['server_version']=(await transport.get('http://127.0.0.1:11434/api/version')).json()
            for name in args.models:
                ensure_idle()
                ps=(await transport.get('http://127.0.0.1:11434/api/ps')).json()['models']
                for loaded in ps:
                    if loaded['name'] not in args.models:raise RuntimeError('Another model is in use; not unloading it.')
                    response=await transport.post('http://127.0.0.1:11434/api/chat',json={'model':loaded['name'],'messages':[],'keep_alive':0,'stream':False});response.raise_for_status()
                client=LocalAI();client.model=name
                await probe(client,name,'term_cold',ChatReply,'Giải thích prefix /26 bằng tiếng Việt trong 60–80 từ, phân biệt bit network, bit host và tổng địa chỉ. Trả source_refs và needs_more_source theo schema.',fragment('net:0',NET),report);save()
                for subject,ref,text,question,expected in CASES:
                    prompt='Tạo MỘT câu trắc nghiệm một đáp án hỏi đúng câu sau: '+question+' question chỉ có kind=mcq, prompt, 3–4 options khác nghĩa, answer nguyên văn một option, explanation ngắn, source_refs. Không thêm left/rubric/difficulty/id, kể cả mảng rỗng. Không thay câu hỏi bằng ý khác. reason="" khi đủ nguồn.'
                    await probe(client,name,'mcq_'+subject,QUESTION_DRAFTS['mcq'],prompt,fragment(ref,text),report,expected);save()
                prompt='Viết một bài đọc tiếng Việt về IPv4 và subnet /26, đúng3 sections,2 cards và3 mindmap. Mỗi text/back dưới80 từ, giữ ví dụ IP/mask trong nguồn. Chỉ title,sections,cards,mindmap theo schema, có source_refs.'
                await probe(client,name,'reading_warm',LessonReading,prompt,fragment('net:0',NET),report);save()
                ensure_idle()
                response=await transport.post('http://127.0.0.1:11434/api/chat',json={'model':name,'messages':[],'keep_alive':0,'stream':False});response.raise_for_status()
            report['finished_at']=datetime.now(timezone.utc).isoformat()
    finally:save();print('RESULT '+str(target.relative_to(ROOT)),flush=True)


if __name__=='__main__':asyncio.run(main())
