"""Versioned, non-cash Coin proposals with transactional hold/commit/release."""
import copy
import json
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

POLICY = {
    'version':'dev-proposal-20261015-v2', 'proposed':True, 'cash_payments':False,
    'initial_coin':20, 'initial_quota':{'outline':1,'lesson':1,'subject_analysis':3,'blueprint':1},
    'prices':{'outline':3,'chat':1,'inline_help':1,'correction':2,'source_vision':2,'subject_analysis':1,'short_feedback':1,'blueprint':3},
    'quote_ttl_seconds':600, 'daily_reward_cap':12, 'daily_community_cap':4,
    'rewarded_practice_rounds_per_utc_day':3, 'cards_per_round':5,
    'default_timezone':'Asia/Ho_Chi_Minh',
    'rewards':{'practice':1,'daily_practice_mission':1,'card_round':1,'daily_card_mission':1,'weak_mission':1,
               'first_session':2,'study_day_3':2,'study_day_7':3,'five_units':2,'course_complete':3,'community_positive':2},
    'partial_failure_policy':'release_all; keep usable partial data without charging the failed job',
}


def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True)
def uid(): return uuid.uuid4().hex


class Economy:
    def __init__(self,database,enabled=True,clock=None,policy=None):
        self.database=database;self.enabled=enabled
        self.clock=clock or (lambda: datetime.now(timezone.utc))
        self.policy=copy.deepcopy(policy or POLICY)

    def now(self): return self.clock().astimezone(timezone.utc)
    def stamp(self): return self.now().isoformat()

    def ensure(self,db,owner):
        if db.execute('SELECT 1 FROM wallets WHERE owner_id=?',(owner,)).fetchone():return
        amount=self.policy['initial_coin'];ledger=uid()
        db.execute('INSERT INTO wallets VALUES (?,?)',(owner,amount))
        db.execute('INSERT INTO coin_ledger VALUES (?,?,?,?,?,?)',(ledger,owner,amount,'Coin khởi đầu theo cấu hình đề xuất','initial-grant',self.stamp()))
        db.execute('INSERT INTO coin_ledger_context VALUES (?,?,?,?,?)',(ledger,'onboarding',self.now().date().isoformat(),'{}',dump(self.policy)))

    def wallet(self,db,owner):
        self.ensure(db,owner)
        balance=db.execute('SELECT balance FROM wallets WHERE owner_id=?',(owner,)).fetchone()[0]
        held=db.execute("SELECT coalesce(sum(amount),0) FROM coin_reservations WHERE owner_id=? AND status='reserved'",(owner,)).fetchone()[0]
        return {'balance':balance,'held':held,'available':balance-held,'policy_version':self.policy['version'],'policy_proposed':True,'cash_payments':False,'enforcement_enabled':self.enabled}

    def cost(self,db,task,payload):
        if task=='question_completion':
            # An append-only content proposal uses the existing proposed edit
            # price and quote/hold flow, never a new billing or free-tier claim.
            return self.policy['prices']['correction']
        if task=='lesson':
            course=db.execute('SELECT plan_id,content_json FROM course_revisions WHERE course_id=? AND revision=?',(payload.get('course_id'),payload.get('expected_revision'))).fetchone()
            count=5
            if course:
                unit = next((u for u in json.loads(course['content_json'])['units'] if u['id'] == payload.get('unit_id')), {})
                plan=db.execute('SELECT preferences_json FROM plans WHERE id=?',(unit.get('source_plan_id', course['plan_id']),)).fetchone()
                preferences=json.loads(plan[0]);count=preferences.get('question_count') or len(preferences.get('question_types') or range(5))
            reading=1;cached=0
            if payload.get('resume_job_id'):
                previous=db.execute('SELECT partial_json FROM jobs WHERE id=?',(payload['resume_job_id'],)).fetchone()
                if previous:
                    partial=json.loads(previous[0]);reading=0 if partial.get('reading') else 1
                    cached=sum(bool(q.get('question')) for q in partial.get('questions',{}).values())
            return max(1,reading+count-cached)
        return self.policy['prices'].get(task,2)

    def offer(self,db,owner,task,payload,identity):
        """Called inside the job creation transaction, before any AI/prepare."""
        if not self.enabled:return {'amount':0,'disabled_for_test':True}
        self.ensure(db,owner)
        maximum=self.policy['initial_quota'].get(task,0)
        used=db.execute("SELECT count(*) FROM ai_usage WHERE owner_id=? AND quota_group=? AND status IN ('reserved','committed')",(owner,task)).fetchone()[0]
        quota_group=task if used<maximum else None
        amount=0 if quota_group else self.cost(db,task,payload)
        quoted_id=identity.get('coin_quote_id')
        provider=dump({**identity['provenance'],'resource_versions':identity.get('resource_versions',[])})
        if quoted_id:
            row=db.execute('SELECT * FROM coin_quotes WHERE id=? AND owner_id=?',(quoted_id,owner)).fetchone()
            if not row or row['operation']!=identity['operation'] or row['digest']!=identity['digest'] or row['provider_json']!=provider:
                raise HTTPException(409,'Báo giá không thuộc đúng yêu cầu/model của bạn.')
            if row['status']!='quoted' or row['expires_at']<=self.now().timestamp():
                raise HTTPException(409,'Báo giá đã dùng/hết hạn; lấy báo giá mới trước khi xác nhận.')
            if row['amount']!=amount or json.loads(row['policy_json'])!=self.policy:
                raise HTTPException(409,'Quota hoặc cấu hình đã đổi; cần xem lại báo giá, chưa trừ Coin.')
            if not identity.get('key'):
                raise HTTPException(422,'Xác nhận dùng Coin cần Idempotency-Key để không trừ hai lần.')
            if self.wallet(db,owner)['available']<amount:
                raise HTTPException(402,{'code':'INSUFFICIENT_COIN','message':'Chưa đủ Coin khả dụng. Nội dung đã có và sửa tay vẫn dùng được.','wallet':self.wallet(db,owner)})
            return {'amount':amount,'quote_id':row['id'],'quota_group':quota_group}
        if amount==0:return {'amount':0,'quota_group':quota_group}
        # Reuse an unexpired quote for the same intent rather than creating a
        # new quote on each network retry. No balance is held at this point.
        row=db.execute("SELECT * FROM coin_quotes WHERE owner_id=? AND operation=? AND digest=? AND provider_json=? AND amount=? AND policy_json=? AND status='quoted' AND expires_at>? ORDER BY created_at DESC LIMIT 1",(owner,identity['operation'],identity['digest'],provider,amount,dump(self.policy),self.now().timestamp())).fetchone()
        quote_id=row['id'] if row else uid()
        expiry=row['expires_at'] if row else self.now().timestamp()+self.policy['quote_ttl_seconds']
        if not row:
            db.execute('INSERT INTO coin_quotes VALUES (?,?,?,?,?,?,?,?,?,?)',(quote_id,owner,identity['operation'],identity['digest'],provider,amount,dump(self.policy),'quoted',expiry,self.stamp()))
        return {'confirmation_required':True,'quote_id':quote_id,'amount':amount,'task':task,'model':identity['provenance']['model'],
                'expires_at':expiry,'policy_version':self.policy['version'],'policy_proposed':True,'wallet':self.wallet(db,owner),
                'message':f'Lượt này cần {amount} Coin theo cấu hình đề xuất. Chỉ trừ khi kết quả hợp lệ đã được lưu; một đề xuất đã tạo dùng được vẫn tính Coin nếu sau đó chọn giữ bản cũ.',
                'insufficient_coin':self.wallet(db,owner)['available']<amount}

    def reserve(self,db,owner,job_id,task,decision):
        if not self.enabled:return
        amount=decision['amount'];quote=decision.get('quote_id')
        if quote:
            changed=db.execute("UPDATE coin_quotes SET status='used' WHERE id=? AND owner_id=? AND status='quoted'",(quote,owner)).rowcount
            if changed!=1:raise HTTPException(409,'Báo giá đã được dùng ở yêu cầu khác.')
        db.execute('INSERT INTO ai_usage VALUES (?,?,?,?,?,?,?,?,?)',(job_id,owner,quote,decision.get('quota_group'),amount,dump(self.policy),'reserved',self.stamp(),self.stamp()))
        if amount:
            db.execute('INSERT INTO coin_reservations VALUES (?,?,?,?,?,?,?,?)',(job_id,owner,amount,task,job_id,'reserved',self.stamp(),self.stamp()))

    def finish(self,db,job_id,result=None):
        if not self.enabled:return
        row=db.execute('SELECT * FROM ai_usage WHERE job_id=?',(job_id,)).fetchone()
        if not row or row['status']!='reserved':return
        if result and (result.get('needs_more_source') or result.get('continuation_required')):
            self.release(db,job_id);return
        if row['amount']:
            ledger=uid();event='ai-spend:'+job_id
            changed=db.execute('UPDATE wallets SET balance=balance-? WHERE owner_id=? AND balance>=?',(row['amount'],row['owner_id'],row['amount'])).rowcount
            if changed!=1:raise RuntimeError('Coin invariant failed; result transaction must not commit.')
            db.execute('INSERT INTO coin_ledger VALUES (?,?,?,?,?,?)',(ledger,row['owner_id'],-row['amount'],'Trợ giúp AI đã lưu kết quả',event,self.stamp()))
            db.execute('INSERT INTO coin_ledger_context VALUES (?,?,?,?,?)',(ledger,'ai_spend',self.now().date().isoformat(),dump({'job_id':job_id}),row['policy_json']))
            db.execute("UPDATE coin_reservations SET status='committed',updated_at=? WHERE job_id=? AND status='reserved'",(self.stamp(),job_id))
        db.execute("UPDATE ai_usage SET status='committed',updated_at=? WHERE job_id=?",(self.stamp(),job_id))

    def release(self,db,job_id):
        db.execute("UPDATE coin_reservations SET status='released',updated_at=? WHERE job_id=? AND status='reserved'",(self.stamp(),job_id))
        db.execute("UPDATE ai_usage SET status='released',updated_at=? WHERE job_id=? AND status='reserved'",(self.stamp(),job_id))

    def reconcile(self,db):
        for row in db.execute("SELECT a.job_id,j.status,j.result_json FROM ai_usage a JOIN jobs j ON j.id=a.job_id WHERE a.status='reserved'").fetchall():
            if row['status']=='succeeded':self.finish(db,row['job_id'],json.loads(row['result_json']) if row['result_json'] else {})
            elif row['status'] in {'failed','cancelled'}:self.release(db,row['job_id'])

    def award(self,db,owner,amount,event_key,category,context=None):
        self.ensure(db,owner)
        prior=db.execute('SELECT amount FROM coin_ledger WHERE owner_id=? AND event_key=?',(owner,event_key)).fetchone()
        if prior:return {'amount':prior[0],'replayed':True,'event_key':event_key}
        day=self.now().date().isoformat()
        total=db.execute("SELECT coalesce(sum(l.amount),0) FROM coin_ledger l JOIN coin_ledger_context c ON c.ledger_id=l.id WHERE l.owner_id=? AND l.amount>0 AND c.utc_day=? AND c.category NOT IN ('onboarding','ai_spend')",(owner,day)).fetchone()[0]
        allowed=max(0,self.policy['daily_reward_cap']-total)
        if category=='community':
            community=db.execute("SELECT coalesce(sum(l.amount),0) FROM coin_ledger l JOIN coin_ledger_context c ON c.ledger_id=l.id WHERE l.owner_id=? AND c.utc_day=? AND c.category='community'",(owner,day)).fetchone()[0]
            allowed=min(allowed,max(0,self.policy['daily_community_cap']-community))
        granted=min(amount,allowed);ledger=uid()
        # A capped event is recorded with zero, so tomorrow/re-like/retry cannot
        # mint it again. The daily boundary is UTC, independent of UI timezone.
        db.execute('INSERT INTO coin_ledger VALUES (?,?,?,?,?,?)',(ledger,owner,granted,category,event_key,self.stamp()))
        db.execute('INSERT INTO coin_ledger_context VALUES (?,?,?,?,?)',(ledger,category,day,dump(context or {}),dump(self.policy)))
        db.execute('UPDATE wallets SET balance=balance+? WHERE owner_id=?',(granted,owner))
        return {'amount':granted,'requested':amount,'capped':granted<amount,'replayed':False,'event_key':event_key,'policy_version':self.policy['version']}


def register_economy(app,economy,database,user):
    @app.get('/api/coin/policy')
    def policy(owner=Depends(user)):return {**economy.policy,'enforcement_enabled':economy.enabled}

    @app.get('/api/wallet')
    def wallet(owner=Depends(user)):
        with database.connection(write=True) as db:return economy.wallet(db,owner)

    @app.get('/api/wallet/history')
    def history(owner=Depends(user)):
        with database.connection(write=True) as db:
            economy.ensure(db, owner)
            return {'ledger':[dict(r) for r in db.execute('SELECT l.amount,l.reason,l.event_key,l.created_at,c.category,c.policy_json FROM coin_ledger l LEFT JOIN coin_ledger_context c ON c.ledger_id=l.id WHERE l.owner_id=? ORDER BY l.created_at DESC LIMIT 200',(owner,))],
                    'reservations':[dict(r) for r in db.execute('SELECT amount,purpose,job_id,status,created_at,updated_at FROM coin_reservations WHERE owner_id=? ORDER BY created_at DESC LIMIT 100',(owner,))]}
