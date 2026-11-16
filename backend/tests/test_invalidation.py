"""失效语义：源数据更新按范围使方案失效、核算生命周期、签核门禁、并发与晚完成旧核算、修订插入。"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from src.models.entities import Student,Plan,Checkin,Calculation,Report
from src.services import checkins,calculations,reports,students,plans
from src.services.tutoring import compute_calculation
from src.schemas.business import CheckinInput,StudentInput,PlanInput,ConclusionInput

def make_student(db,code='ZX-1',campus='城东',group='intervention',score=80.0):
    item=Student(code=code,name='学员'+code,campus=campus,group=group,score=score,absent=False)
    db.add(item);db.commit();return item
def make_plan(db,title='方案A',campus='城东',obs_start='2026-09-01',obs_end='2026-11-15',threshold=120):
    return plans.save_plan(db,PlanInput(title=title,campus=campus,obs_start=obs_start,obs_end=obs_end,threshold_minutes=threshold))
def ci(code,start,end,note=''):
    return CheckinInput(student_code=code,start_at=start,end_at=end,note=note)
def run_queued_calc(db,calc):
    """模拟 worker：版本先行快照后全量重算（与 src.worker.run_calculation 同语义）。"""
    plan=db.get(Plan,calc.plan_id)
    calc.status='running';db.commit()
    calc.result=compute_calculation(plan,db.scalars(select(Student)).all(),db.scalars(select(Checkin)).all())
    calc.source_version=plan.data_version;calc.status='available';db.commit()
    return calc

def test_checkin_create_bumps_only_affected_plans(db):
    make_student(db)
    hit=make_plan(db,'城东方案','城东')
    other_campus=make_plan(db,'城西方案','城西')
    other_period=make_plan(db,'城东暑期','城东',obs_start='2026-07-01',obs_end='2026-08-01')
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T20:30'))
    db.expire_all()
    assert db.get(Plan,hit.id).data_version==1
    assert db.get(Plan,other_campus.id).data_version==0  # 教学点不匹配，不受影响
    assert db.get(Plan,other_period.id).data_version==0  # 观察期不相交，不受影响

def test_checkin_revise_and_revoke_bump(db):
    make_student(db)
    plan=make_plan(db)
    item=checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T20:30'))
    checkins.update_checkin(db,item.id,ci('ZX-1','2026-10-13T19:00','2026-10-13T20:30'))
    checkins.set_revoked(db,item.id,True)
    checkins.set_revoked(db,item.id,False)
    db.expire_all()
    assert db.get(Plan,plan.id).data_version==4

def test_checkin_validation(db):
    make_student(db)
    with pytest.raises(HTTPException): checkins.create_checkin(db,ci('ZX-1','2026-10-12T20:00','2026-10-12T19:00'))
    with pytest.raises(HTTPException): checkins.create_checkin(db,ci('ZX-404','2026-10-12T19:00','2026-10-12T20:00'))

def test_student_source_edit_bumps_but_name_only_does_not(db):
    make_student(db)
    plan=make_plan(db)
    students.save_student(db,StudentInput(code='ZX-1',name='改名',campus='城东',group='intervention',score=80.0),1)
    assert db.get(Plan,plan.id).data_version==0  # 仅姓名变化不影响检验
    students.save_student(db,StudentInput(code='ZX-1',name='改名',campus='城东',group='intervention',score=81.0),1)
    assert db.get(Plan,plan.id).data_version==1  # 成绩是检验源数据

def test_plan_scope_edit_bumps_own_version(db):
    make_student(db)
    plan=make_plan(db)
    plans.save_plan(db,PlanInput(title='方案A',campus='城东',obs_start='2026-09-01',obs_end='2026-11-15',threshold_minutes=120,description='仅改描述'),plan.id)
    assert db.get(Plan,plan.id).data_version==0
    plans.save_plan(db,PlanInput(title='方案A',campus='城东',obs_start='2026-09-01',obs_end='2026-11-15',threshold_minutes=240),plan.id)
    assert db.get(Plan,plan.id).data_version==1  # 门槛变化使旧核算失效

def test_calculation_lifecycle_pending_to_available_then_stale(db):
    make_student(db)
    plan=make_plan(db)
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T21:00'))
    calc=calculations.create_calculation(db,plan.id)
    assert calc.status=='queued' and calculations.usable_for_plan(db,plan.id) is None  # 待计算
    run_queued_calc(db,calc)
    assert calculations.usable_for_plan(db,plan.id).id==calc.id  # 可用
    checkins.set_revoked(db,1,True)  # 源数据更新
    db.expire_all()
    assert calculations.usable_for_plan(db,plan.id) is None
    assert calculations.detail(db,calc.id)['stale'] is True  # 已失效，重算后才恢复

def test_report_requires_usable_calculation(db):
    make_student(db)
    plan=make_plan(db)
    with pytest.raises(HTTPException) as e: reports.create_report(db,plan.id)
    assert e.value.status_code==409

def test_signoff_rejected_until_recalculation(db):
    make_student(db)
    plan=make_plan(db)
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T21:00'))
    run_queued_calc(db,calculations.create_calculation(db,plan.id))
    report=reports.create_report(db,plan.id)
    report.status='completed';report.result={'grouping':'actual'};db.commit()
    admin=type('U',(),{'role':'admin'})
    reports.save_conclusion(db,report.id,ConclusionInput(conclusion='首轮签核',published=True),admin)
    checkins.create_checkin(db,ci('ZX-1','2026-10-14T19:00','2026-10-14T21:00'))  # 并发后的源数据更新
    db.expire_all()
    assert reports.report_stale(db,db.get(Report,report.id)) is True
    with pytest.raises(HTTPException) as e: reports.save_conclusion(db,report.id,ConclusionInput(conclusion='试图再次签核',published=True),admin)
    assert e.value.status_code==409 and '失效' in e.value.detail  # 拒绝签核
    run_queued_calc(db,calculations.create_calculation(db,plan.id))  # 重算
    followup=reports.create_report(db,plan.id)
    followup.status='completed';followup.result={'grouping':'actual'};db.commit()
    reports.save_conclusion(db,followup.id,ConclusionInput(conclusion='重算后签核恢复',published=True),admin)
    assert db.get(Report,followup.id).published is True

def test_late_finishing_old_calculation_cannot_restore_validity(db):
    make_student(db)
    plan=make_plan(db)
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T21:00'))
    old_calc=calculations.create_calculation(db,plan.id)
    stale_version=db.get(Plan,plan.id).data_version  # 旧核算启动时读到的版本
    checkins.create_checkin(db,ci('ZX-1','2026-10-13T19:00','2026-10-13T21:00'))  # 核算期间的签到修订
    run_queued_calc(db,calculations.create_calculation(db,plan.id))  # 新核算先完成
    fresh=calculations.usable_for_plan(db,plan.id)
    old_calc.status='available';old_calc.source_version=stale_version
    old_calc.result=compute_calculation(db.get(Plan,plan.id),db.scalars(select(Student)).all(),db.scalars(select(Checkin)).all())
    db.commit()  # 旧核算晚完成
    db.expire_all()
    assert calculations.usable_for_plan(db,plan.id).id==fresh.id  # 当前可用仍是新核算
    assert calculations.detail(db,old_calc.id)['stale'] is True
    report=Report(plan_id=plan.id,calculation_id=old_calc.id,status='completed',result={},created_at='2026-11-16T00:00:00+00:00')
    db.add(report);db.commit()
    assert reports.report_stale(db,report) is True  # 旧核算不能恢复报告有效性

def test_revision_insertion_visible_after_recompute(db):
    make_student(db)
    plan=make_plan(db)
    item=checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T20:00'))
    run_queued_calc(db,calculations.create_calculation(db,plan.id))
    first=calculations.usable_for_plan(db,plan.id)
    assert first.result['students'][0]['minutes']==60.0
    checkins.update_checkin(db,item.id,ci('ZX-1','2026-10-12T19:00','2026-10-12T20:00'))  # 更正原记录
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T20:30','2026-10-12T21:30'))  # 修订插入新时段
    run_queued_calc(db,calculations.create_calculation(db,plan.id))
    second=calculations.usable_for_plan(db,plan.id)
    assert second.id!=first.id and second.source_version>first.source_version
    assert second.result['students'][0]['minutes']==120.0 and len(second.result['students'][0]['intervals'])==2

def test_export_payload_roundtrip(db):
    make_student(db)
    plan=make_plan(db)
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:00','2026-10-12T20:30'))
    checkins.create_checkin(db,ci('ZX-1','2026-10-12T19:30','2026-10-12T21:00'))
    run_queued_calc(db,calculations.create_calculation(db,plan.id))
    calc=calculations.usable_for_plan(db,plan.id)
    payload=calculations.export_payload(db,calc.id)
    from src.services.tutoring import recompute_from_export
    assert recompute_from_export(payload)['checksum']==payload['checksum']  # 导出可独立复算时长
    assert payload['students'][0]['minutes']==120.0
