import os,json
from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
import redis
from src.models.entities import Calculation,Plan,Checkin,Student
from src.services.tutoring import iso
queue=redis.Redis.from_url(os.environ['REDIS_URL'])
def is_stale(calc,plan):
    """可用核算在源数据版本前进后失效；待算/算中/失败不参与有效性判断。"""
    return calc.status=='available' and calc.source_version!=plan.data_version
def annotate(db,calcs):
    plans={p.id:p for p in db.scalars(select(Plan)).all()}
    out=[]
    for c in calcs:
        plan=plans.get(c.plan_id)
        d={k:getattr(c,k) for k in ('id','plan_id','status','source_version','error','created_at')}
        d['current_version']=plan.data_version if plan else None
        d['stale']=bool(plan) and is_stale(c,plan)
        d['summary']=(c.result or {}).get('summary')
        d['threshold_minutes']=(c.result or {}).get('threshold_minutes')
        out.append(d)
    return out
def list_calculations(db):
    calcs=db.scalars(select(Calculation).order_by(Calculation.id.desc())).all()
    return annotate(db,calcs)
def get_calculation(db,id):
    item=db.get(Calculation,id)
    if not item: raise HTTPException(404,'核算记录不存在')
    return item
def detail(db,id):
    item=get_calculation(db,id)
    plan=db.get(Plan,item.plan_id)
    d={k:getattr(item,k) for k in ('id','plan_id','status','source_version','error','created_at')}
    d['result']=item.result
    d['current_version']=plan.data_version if plan else None
    d['stale']=bool(plan) and is_stale(item,plan)
    return d
def usable_for_plan(db,plan_id):
    """方案当前可用的最近一次核算：状态可用且源数据版本一致。"""
    plan=db.get(Plan,plan_id)
    if not plan: return None
    calcs=db.scalars(select(Calculation).where(Calculation.plan_id==plan_id,Calculation.status=='available').order_by(Calculation.id.desc())).all()
    for c in calcs:
        if not is_stale(c,plan): return c
    return None
def create_calculation(db,plan_id):
    plan=db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,'辅导方案不存在')
    if not plan.obs_start or not plan.obs_end: raise HTTPException(409,'方案尚未登记观察期，请先在辅导分组中补全')
    pending=db.scalars(select(Calculation).where(Calculation.status.in_(['queued','running']))).all()
    if len(pending)>=10: raise HTTPException(429,'待执行核算已达10个，请稍后再试')
    item=Calculation(plan_id=plan_id,status='queued',created_at=iso(datetime.now(timezone.utc)))
    db.add(item);db.commit();db.refresh(item)
    queue.lpush('tutor:tasks',f'calc:{item.id}')
    return item
def export_payload(db,id):
    """导出可独立复算的核算档案：原始签到记录 + 口径参数 + 合并结果 + 校验码。"""
    item=get_calculation(db,id)
    if item.status!='available': raise HTTPException(409,'核算尚未可用，暂不能导出')
    plan=db.get(Plan,item.plan_id)
    codes=[s['code'] for s in item.result['students']]
    records=db.scalars(select(Checkin).where(Checkin.student_code.in_(codes)).order_by(Checkin.id)).all() if codes else []
    students=db.scalars(select(Student).where(Student.code.in_(codes))).all() if codes else []
    names={s.code:s.name for s in students}
    return {'calculation_id':item.id,'source_version':item.source_version,'generated_at':item.result['generated_at'],
        'plan':{'id':plan.id,'title':plan.title,'campus':plan.campus,'obs_start':item.result['obs_start'],'obs_end':item.result['obs_end'],'threshold_minutes':item.result['threshold_minutes']},
        'algorithm':'1) 仅取 revoked=false 的签到 2) 按观察期[obs_start,obs_end)半开区间裁剪 3) 重叠及相接时段合并 4) 累计分钟>=threshold_minutes 划入 actual_intervention，否则 actual_control',
        'checksum_rule':'sha256(json.dumps([{code,minutes,actual_group,intervals:[[start,end]}...] 按 code 排序],ensure_ascii=False,sort_keys=True,separators=(",",":")))',
        'records':[{'id':c.id,'student_code':c.student_code,'start_at':c.start_at,'end_at':c.end_at,'revoked':c.revoked} for c in records],
        'students':[{'code':s['code'],'name':names.get(s['code'],''),'campus':s['campus'],'reg_group':s['reg_group'],'minutes':s['minutes'],'actual_group':s['actual_group'],'intervals':[[i['start'],i['end']] for i in s['intervals']]} for s in item.result['students']],
        'summary':item.result['summary'],'checksum':item.result['checksum']}
