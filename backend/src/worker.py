import time,traceback
from pathlib import Path
from sqlalchemy import select,update
from src.config.database import SessionLocal
from src.models.entities import Report,Plan,Student,Checkin,Calculation
from src.services.reports import queue
from src.services.statistics import welch_actual
from src.services.tutoring import compute_calculation
def requeue_interrupted():
    """进程中断遗留的 running 任务恢复为 queued；核算与检验均为全量重算，重试不会重复计时。"""
    with SessionLocal() as db:
        for model in (Calculation,Report):
            db.execute(update(model).where(model.status=='running').values(status='queued'))
        db.commit()
def run_calculation(db,task):
    task.status='running';db.commit()
    try:
        # 可重复读快照（PostgreSQL）：先取源数据版本再取数据，核算期间的签到修订必然体现为版本差，不会被漏掉
        if db.bind.dialect.name=='postgresql': db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
        plan=db.get(Plan,task.plan_id)
        if not plan: raise ValueError('辅导方案不存在')
        version=db.scalar(select(Plan.data_version).where(Plan.id==plan.id))
        students=db.scalars(select(Student).order_by(Student.code)).all()
        checkins=db.scalars(select(Checkin)).all()
        task.result=compute_calculation(plan,students,checkins)
        task.source_version=version
        task.status='available'
    except Exception as e:
        task.error=str(e);task.status='failed'
    db.commit()
def run_report(db,task):
    task.status='running';db.commit()
    try:
        plan=db.get(Plan,task.plan_id)
        calc=db.get(Calculation,task.calculation_id) if task.calculation_id else None
        if not plan: raise ValueError('辅导方案不存在')
        if not calc or calc.status!='available' or calc.source_version!=plan.data_version:
            raise ValueError('核算已失效：签到或成绩在检验前发生变化，请重新核算后再发起检验')
        students=db.scalars(select(Student).order_by(Student.code)).all()
        task.result=welch_actual(students,plan,calc.result)
        task.status='completed'
    except Exception as e:
        task.error=str(e);task.status='failed'
    db.commit()
def pick_queued(db,model):
    return db.scalar(select(model).where(model.status=='queued').order_by(model.id).with_for_update(skip_locked=True))
def main():
    print('tutor effect worker started',flush=True)
    requeue_interrupted()
    while True:
        Path('/tmp/worker-heartbeat').touch()
        try:
            queue.brpop('tutor:tasks',timeout=2)
            with SessionLocal() as db:
                task=pick_queued(db,Calculation)
                if task:
                    run_calculation(db,task)
                    print(f'calculation={task.id} status={task.status}',flush=True)
                    continue
                task=pick_queued(db,Report)
                if not task: continue
                run_report(db,task)
                print(f'report={task.id} status={task.status}',flush=True)
        except Exception:
            traceback.print_exc();time.sleep(2)
if __name__=='__main__': main()
