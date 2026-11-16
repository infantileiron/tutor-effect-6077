from datetime import datetime,timezone
from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import Checkin,Student
from src.services.tutoring import parse_dt,iso
from src.services import versions
def list_checkins(db): return db.scalars(select(Checkin).order_by(Checkin.id.desc())).all()
def _validate(db,data):
    student=db.scalar(select(Student).where(Student.code==data.student_code))
    if not student: raise HTTPException(422,f'学号 {data.student_code} 不存在，请先在成绩样本中登记学员')
    try:
        start,end=parse_dt(data.start_at),parse_dt(data.end_at)
    except Exception: raise HTTPException(422,'起止时间格式不正确，应为 YYYY-MM-DDTHH:MM')
    if not start<end: raise HTTPException(422,'结束时间必须晚于开始时间')
    if (end-start).total_seconds()>24*3600: raise HTTPException(422,'单次签到时长不能超过 24 小时')
    return student,start,end
def create_checkin(db,data):
    student,start,end=_validate(db,data)
    now=iso(datetime.now(timezone.utc))
    item=Checkin(student_code=student.code,start_at=iso(start),end_at=iso(end),revoked=False,note=data.note or '',created_at=now,updated_at=now)
    db.add(item)
    versions.bump_for_checkin(db,{student.campus},[(start,end)])
    db.commit();db.refresh(item)
    return item
def update_checkin(db,id,data):
    item=db.get(Checkin,id)
    if not item: raise HTTPException(404,'签到记录不存在')
    student,start,end=_validate(db,data)
    old=db.scalar(select(Student).where(Student.code==item.student_code))
    affected=[(parse_dt(item.start_at),parse_dt(item.end_at)),(start,end)]
    campuses={student.campus}|({old.campus} if old else set())
    item.student_code=student.code;item.start_at=iso(start);item.end_at=iso(end);item.note=data.note or ''
    item.updated_at=iso(datetime.now(timezone.utc))
    versions.bump_for_checkin(db,campuses if old else None,affected)
    db.commit();db.refresh(item)
    return item
def set_revoked(db,id,value):
    item=db.get(Checkin,id)
    if not item: raise HTTPException(404,'签到记录不存在')
    if item.revoked==value: return item
    item.revoked=value;item.updated_at=iso(datetime.now(timezone.utc))
    student=db.scalar(select(Student).where(Student.code==item.student_code))
    versions.bump_for_checkin(db,{student.campus} if student else None,[(parse_dt(item.start_at),parse_dt(item.end_at))])
    db.commit();db.refresh(item)
    return item
