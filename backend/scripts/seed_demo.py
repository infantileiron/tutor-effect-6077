import random,json
from datetime import datetime,date,timedelta,timezone
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models.entities import User,Student,Plan,Report,Checkin,Calculation
from src.utils.security import hash_password
from src.services.statistics import welch,welch_actual
from src.services.tutoring import compute_calculation,normalize_obs,iso

OBS_START,OBS_END,THRESHOLD='2026-09-01','2026-11-15',720

def seed():
    Base.metadata.create_all(engine)
    rng=random.Random(20261115)
    with SessionLocal() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)): db.add(User(email=email,role=role,password_hash=hash_password('Demo123!')))
        for i in range(160):
            code=f'ZX-2026-{i+1:03}'
            group='control' if i<80 else 'intervention'
            score=round(min(100,max(0,rng.gauss(72 if group=='control' else 78,8))),1)
            absent=i%23==0
            if not db.scalar(select(Student).where(Student.code==code)):
                db.add(Student(code=code,name=f'学员{i+1:03}',campus=['城东','城西','滨江','高新'][i%4],group=group,score=None if absent else score,absent=absent))
        title='2026秋季 · 晚间小组辅导'
        plan=db.scalar(select(Plan).where(Plan.title==title))
        if not plan:
            plan=Plan(title=title,campus='全部',exclude_absent=True,description='评估每周两次小组辅导与常规自习的期末成绩差异。按签到核算实际辅导量划分实际辅导组；缺考学员排除；观察性结果不直接证明因果。');db.add(plan);db.flush()
        if not plan.obs_start:
            plan.obs_start,plan.obs_end=normalize_obs(OBS_START,OBS_END)
            plan.threshold_minutes=THRESHOLD
        db.commit()
        if not db.scalar(select(Report).where(Report.plan_id==plan.id)):
            result=welch(db.scalars(select(Student).order_by(Student.code)).all(),plan)
            db.add(Report(plan_id=plan.id,status='completed',result=result,created_at=datetime.now(timezone.utc).isoformat(),conclusion='按报名分组的历史基线检验。后续结论以实际辅导量检验为准。',published=True));db.commit()
        seed_checkins(db,plan,rng)
        seed_calculation_and_report(db,plan)
        print(json.dumps({table:db.scalar(select(func.count()).select_from(model)) for table,model in [('users',User),('students',Student),('plans',Plan),('checkins',Checkin),('calculations',Calculation),('reports',Report)]}))

def seed_checkins(db,plan,rng):
    """演示签到：常规晚辅导、跨班重叠记录、跨观察期记录、撤销拆段样例。幂等：已有签到即跳过。"""
    if db.scalar(select(Checkin).limit(1)): return
    rng=random.Random(20261116)
    students=db.scalars(select(Student).order_by(Student.code)).all()
    days=[];d=date(2026,9,7)
    while d<=date(2026,11,12):
        if d.weekday() in (0,3): days.append(d)
        d+=timedelta(days=1)
    now=iso(datetime.now(timezone.utc))
    def add(code,start,end,note='',revoked=False):
        db.add(Checkin(student_code=code,start_at=start,end_at=end,revoked=revoked,note=note,created_at=now,updated_at=now))
    def session(code,day,start,end,note='晚间小组辅导'):
        add(code,f'{day}T{start}:00+00:00',f'{day}T{end}:00+00:00',note)
    bridge_day=days[10]
    for stu in students:
        i=int(stu.code.rsplit('-',1)[1])-1
        if stu.group=='intervention': attendance=min(1,max(.05,rng.gauss(.7,.2)))
        elif i%10<3: attendance=min(1,max(.02,rng.gauss(.35,.18)))
        else: continue
        for day in days:
            if stu.code=='ZX-2026-083' and day==bridge_day: continue  # 桥接日仅保留手工两段，演示撤销拆段
            if rng.random()<attendance:
                session(stu.code,day,'19:00','20:30')
                if rng.random()<.15: session(stu.code,day,'19:30','21:00','跨班签到（与晚辅导时段重叠）')
    add('ZX-2026-081','2026-08-31T23:00:00+00:00','2026-09-01T01:00:00+00:00','暑期衔接班（跨进观察期，裁剪后计 60 分钟）')
    add('ZX-2026-082','2026-11-15T23:30:00+00:00','2026-11-16T01:00:00+00:00','期末冲刺（跨出观察期，裁剪后计 30 分钟）')
    session('ZX-2026-083',bridge_day,'19:00','20:00','第一段辅导')
    session('ZX-2026-083',bridge_day,'20:30','21:30','第二段辅导')
    db.flush()
    db.add(Checkin(student_code='ZX-2026-083',start_at=f'{bridge_day}T19:30:00+00:00',end_at=f'{bridge_day}T20:45:00+00:00',revoked=True,note='误录的桥接记录，已撤销（撤销后两段独立计时）',created_at=now,updated_at=now))
    stray=db.scalar(select(Checkin).where(Checkin.student_code=='ZX-2026-100',Checkin.revoked==False).limit(1))
    if stray: stray.revoked=True;stray.note='重复录入，已撤销';stray.updated_at=now
    plan.data_version+=1
    db.commit()

def seed_calculation_and_report(db,plan):
    students=db.scalars(select(Student).order_by(Student.code)).all()
    calc=db.scalar(select(Calculation).where(Calculation.plan_id==plan.id))
    if not calc:
        checkins=db.scalars(select(Checkin)).all()
        calc=Calculation(plan_id=plan.id,status='available',source_version=plan.data_version,
            result=compute_calculation(plan,students,checkins),created_at=iso(datetime.now(timezone.utc)))
        db.add(calc);db.commit();db.refresh(calc)
    if not db.scalar(select(Report).where(Report.calculation_id==calc.id)):
        result=welch_actual(students,plan,calc.result)
        db.add(Report(plan_id=plan.id,calculation_id=calc.id,status='completed',result=result,created_at=datetime.now(timezone.utc).isoformat(),
            conclusion='按实际辅导量分组后差异小于报名分组口径，提示报名分组掩盖了真实辅导量。建议下一轮以签到时长为准继续观察。',published=True));db.commit()

if __name__=='__main__': seed()
