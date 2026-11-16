"""端到端：登录 → 签到失效 → 重算 → 按实际辅导量检验 → 签核门禁 → 导出复算。"""
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from src.config.database import SessionLocal
from src.models.entities import Calculation,Report,Plan
from src.main import app
from src.worker import run_calculation,run_report

def drive_worker():
    with SessionLocal() as db:
        task=db.scalar(select(Calculation).where(Calculation.status=='queued').order_by(Calculation.id))
        if task: run_calculation(db,task)
        task=db.scalar(select(Report).where(Report.status=='queued').order_by(Report.id))
        if task: run_report(db,task)

@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        token=c.post('/auth/login',json={'email':'admin@demo.local','password':'Demo123!'}).json()['access_token']
        c.headers['Authorization']=f'Bearer {token}'
        yield c

def test_full_actual_tutoring_lifecycle(client):
    plans=client.get('/plans').json()
    plan=plans[0]
    assert plan['obs_start_date'] and plan['threshold_minutes']>0
    calcs=client.get('/calculations').json()
    assert len(calcs)==1 and calcs[0]['status']=='available' and calcs[0]['stale'] is False
    calc_id=calcs[0]['id']
    detail=client.get(f'/calculations/{calc_id}').json()
    assert detail['result']['students'] and detail['result']['checksum']
    reports=client.get('/reports').json()
    seeded=[r for r in reports if r['calculation_id']]
    assert seeded and seeded[0]['stale'] is False
    # ① 源数据更新：新增签到 → 核算与检验失效
    version_before=[p for p in plans if p['id']==plan['id']][0]['data_version']
    created=client.post('/checkins',json={'student_code':'ZX-2026-001','start_at':'2026-10-20T19:00','end_at':'2026-10-20T21:00','note':'补录'})
    assert created.status_code==201
    assert [p for p in client.get('/plans').json() if p['id']==plan['id']][0]['data_version']==version_before+1
    assert client.get('/calculations').json()[0]['stale'] is True
    assert [r for r in client.get('/reports').json() if r['calculation_id']][0]['stale'] is True
    # ② 失效检验拒绝签核
    stale_id=[r for r in client.get('/reports').json() if r['calculation_id']][0]['id']
    rejected=client.patch(f'/reports/{stale_id}/conclusion',json={'conclusion':'失效后试图签核','published':True})
    assert rejected.status_code==409 and '失效' in rejected.json()['detail']
    # ③ 检验被门禁：无可用核算时不能发起
    blocked=client.post('/reports',json={'plan_id':plan['id']})
    assert blocked.status_code==409
    # ④ 重算恢复：新核算 → 新检验 → 可签核
    assert client.post('/calculations',json={'plan_id':plan['id']}).status_code==202
    drive_worker()
    fresh=[c for c in client.get('/calculations').json() if c['status']=='available' and not c['stale']]
    assert fresh and fresh[0]['id']!=calc_id
    assert client.post('/reports',json={'plan_id':plan['id']}).status_code==202
    drive_worker()
    latest=client.get('/reports').json()[0]
    assert latest['status']=='completed' and latest['stale'] is False and latest['result']['grouping']=='actual'
    assert client.patch(f"/reports/{latest['id']}/conclusion",json={'conclusion':'重算复检后签核','published':True}).status_code==200
    # ⑤ 撤销与更正：撤销拆段、修订插入均使核算失效
    checkins=client.get('/checkins').json()
    target=[c for c in checkins if not c['revoked']][0]
    assert client.post(f"/checkins/{target['id']}/revoke").json()['revoked'] is True
    assert client.get('/calculations').json()[0]['stale'] is True
    assert client.post(f"/checkins/{target['id']}/restore").json()['revoked'] is False
    revised=client.put(f"/checkins/{target['id']}",json={'student_code':target['student_code'],'start_at':'2026-10-21T19:00','end_at':'2026-10-21T20:00','note':'更正插入'})
    assert revised.status_code==200
    # ⑥ 导出可复算时长
    assert client.post('/calculations',json={'plan_id':plan['id']}).status_code==202
    drive_worker()
    usable=[c for c in client.get('/calculations').json() if c['status']=='available' and not c['stale']][0]
    exported=client.get(f"/calculations/{usable['id']}/export")
    assert exported.status_code==200
    payload=exported.json()
    from src.services.tutoring import recompute_from_export
    assert recompute_from_export(payload)['checksum']==payload['checksum']
    # ⑦ 报告导出引用核算，便于复算
    assert client.post('/reports',json={'plan_id':plan['id']}).status_code==202
    drive_worker()
    newest=client.get('/reports').json()[0]
    report_export=client.get(f"/reports/{newest['id']}/export").json()
    assert report_export['calculation']['checksum']==payload['checksum']
    assert report_export['stale'] is False

def test_viewer_cannot_mutate(client):
    token=client.post('/auth/login',json={'email':'viewer@demo.local','password':'Demo123!'}).json()['access_token']
    client.headers['Authorization']=f'Bearer {token}'
    assert client.get('/checkins').status_code==200
    assert client.get('/calculations').status_code==200
    assert client.post('/checkins',json={'student_code':'ZX-2026-001','start_at':'2026-10-20T19:00','end_at':'2026-10-20T20:00'}).status_code==403
    assert client.post('/calculations',json={'plan_id':1}).status_code==403
    assert client.post('/reports',json={'plan_id':1}).status_code==403
