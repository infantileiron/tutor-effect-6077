import os
from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
import redis
from src.models.entities import Report,Plan,Calculation
from src.services.calculations import usable_for_plan,is_stale
queue=redis.Redis.from_url(os.environ['REDIS_URL'])
def report_stale(db,item):
    """按实际辅导量的检验：其依据的核算被源数据更新超越即失效；历史报名分组检验不失效。"""
    if not item.calculation_id: return False
    calc=db.get(Calculation,item.calculation_id)
    plan=db.get(Plan,item.plan_id)
    if not calc or not plan: return True
    return calc.status!='available' or is_stale(calc,plan)
def list_reports(db):
    reports=db.scalars(select(Report).order_by(Report.id.desc())).all()
    return [(r,report_stale(db,r)) for r in reports]
def create_report(db,plan_id):
    if not db.get(Plan,plan_id): raise HTTPException(404,'辅导方案不存在')
    calc=usable_for_plan(db,plan_id)
    if not calc: raise HTTPException(409,'该方案尚无可用核算：请先完成时长核算，再按实际辅导量发起检验')
    running=db.scalars(select(Report).where(Report.status.in_(['queued','running']))).all()
    if len(running)>=10: raise HTTPException(429,'待执行任务已达10个，请稍后再试')
    item=Report(plan_id=plan_id,calculation_id=calc.id,status='queued',created_at=datetime.now(timezone.utc).isoformat())
    db.add(item);db.commit();db.refresh(item)
    queue.lpush('tutor:tasks',f'report:{item.id}')
    return item
def get_report(db,id):
    item=db.get(Report,id)
    if not item: raise HTTPException(404,'报告不存在')
    return item
def get_calculation_ref(db,calculation_id): return db.get(Calculation,calculation_id)
def save_conclusion(db,id,data,user):
    item=get_report(db,id)
    if item.status!='completed': raise HTTPException(409,'计算完成后才能起草结论')
    if data.published and report_stale(db,item): raise HTTPException(409,'源数据已更新，本次检验已失效；请重新核算并再次检验后才能签核')
    if item.published and user.role!='admin': raise HTTPException(403,'已签核报告仅管理员可更改')
    if data.published and user.role!='admin': raise HTTPException(403,'仅管理员可签核发布')
    item.conclusion=data.conclusion;item.published=data.published
    db.commit();db.refresh(item)
    return item
