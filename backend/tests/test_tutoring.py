"""时长核算纯函数：跨期裁剪、跨班重叠合并、撤销拆段、门槛分组、重试一致性、导出复算。"""
from src.services.tutoring import compute_calculation,recompute_from_export,merge_intervals,parse_dt,normalize_obs

class Obj:
    def __init__(self,**kw): self.__dict__.update(kw)
def plan(**kw):
    base=dict(id=1,campus='全部',obs_start='2026-09-01T00:00:00+00:00',obs_end='2026-11-16T00:00:00+00:00',threshold_minutes=120)
    return Obj(**{**base,**kw})
def student(code='S1',campus='城东',group='intervention'):
    return Obj(code=code,name='学员'+code,campus=campus,group=group)
def checkin(id,code,start,end,revoked=False):
    return Obj(id=id,student_code=code,start_at=start,end_at=end,revoked=revoked)

def test_cross_period_clipping():
    s=student()
    records=[checkin(1,'S1','2026-08-31T23:00:00+00:00','2026-09-01T01:00:00+00:00'),
        checkin(2,'S1','2026-11-15T23:30:00+00:00','2026-11-16T01:00:00+00:00'),
        checkin(3,'S1','2026-08-01T10:00:00+00:00','2026-08-01T12:00:00+00:00')]
    result=compute_calculation(plan(),[s],records)
    row=result['students'][0]
    assert row['minutes']==90.0  # 60(跨入) + 30(跨出)，期外记录不计
    assert [(i['start'],i['end']) for i in row['intervals']]==[('2026-09-01T00:00:00+00:00','2026-09-01T01:00:00+00:00'),('2026-11-15T23:30:00+00:00','2026-11-16T00:00:00+00:00')]

def test_overlap_merge_no_double_count():
    s=student()
    records=[checkin(1,'S1','2026-10-12T19:00:00+00:00','2026-10-12T20:30:00+00:00'),
        checkin(2,'S1','2026-10-12T19:30:00+00:00','2026-10-12T21:00:00+00:00')]
    result=compute_calculation(plan(),[s],records)
    row=result['students'][0]
    assert row['minutes']==120.0  # 并集 19:00-21:00，而非 90+90
    assert len(row['intervals'])==1 and sorted(row['intervals'][0]['sources'])==[1,2]

def test_touching_intervals_merge():
    merged=merge_intervals([(parse_dt('2026-10-12T19:00'),parse_dt('2026-10-12T20:00'),[1]),(parse_dt('2026-10-12T20:00'),parse_dt('2026-10-12T21:00'),[2])])
    assert len(merged)==1 and merged[0][1]==parse_dt('2026-10-12T21:00')

def test_revocation_splits_interval():
    s=student()
    base=[checkin(1,'S1','2026-10-12T19:00:00+00:00','2026-10-12T20:00:00+00:00'),
        checkin(2,'S1','2026-10-12T20:30:00+00:00','2026-10-12T21:30:00+00:00')]
    bridge=checkin(3,'S1','2026-10-12T19:30:00+00:00','2026-10-12T20:45:00+00:00')
    merged=compute_calculation(plan(),[s],base+[bridge])['students'][0]
    assert len(merged['intervals'])==1 and merged['minutes']==150.0  # 桥接记录把两段连成一段
    bridge.revoked=True
    split=compute_calculation(plan(),[s],base+[bridge])['students'][0]
    assert len(split['intervals'])==2 and split['minutes']==120.0  # 撤销后拆成两段独立计时
    assert split['revoked_records']==1

def test_threshold_grouping_boundary():
    p=plan(threshold_minutes=120)
    at=compute_calculation(p,[student('A')],[checkin(1,'A','2026-10-12T19:00:00+00:00','2026-10-12T21:00:00+00:00')])['students'][0]
    below=compute_calculation(p,[student('B')],[checkin(2,'B','2026-10-12T19:00:00+00:00','2026-10-12T20:59:00+00:00')])['students'][0]
    none=compute_calculation(p,[student('C')],[])['students'][0]
    assert at['actual_group']=='actual_intervention' and below['actual_group']=='actual_control' and none['actual_group']=='actual_control'

def test_retry_is_deterministic_no_double_count():
    s=student()
    records=[checkin(1,'S1','2026-10-12T19:00:00+00:00','2026-10-12T20:30:00+00:00'),checkin(2,'S1','2026-10-12T19:30:00+00:00','2026-10-12T21:00:00+00:00')]
    first=compute_calculation(plan(),[s],records)
    second=compute_calculation(plan(),[s],records)
    assert first['checksum']==second['checksum'] and first['students'][0]['minutes']==120.0

def test_export_payload_recomputes_same_checksum():
    s=student()
    records=[checkin(1,'S1','2026-08-31T23:00:00+00:00','2026-09-01T01:00:00+00:00'),
        checkin(2,'S1','2026-10-12T19:00:00+00:00','2026-10-12T20:30:00+00:00'),
        checkin(3,'S1','2026-10-12T19:30:00+00:00','2026-10-12T21:00:00+00:00'),
        checkin(4,'S1','2026-10-13T19:00:00+00:00','2026-10-13T20:00:00+00:00',revoked=True)]
    p=plan()
    result=compute_calculation(p,[s],records)
    payload={'plan':{'id':p.id,'campus':p.campus,'obs_start':result['obs_start'],'obs_end':result['obs_end'],'threshold_minutes':p.threshold_minutes},
        'records':[{'id':c.id,'student_code':c.student_code,'start_at':c.start_at,'end_at':c.end_at,'revoked':c.revoked} for c in records],
        'students':[{'code':'S1','campus':'城东','reg_group':'intervention'}]}
    assert recompute_from_export(payload)['checksum']==result['checksum']

def test_normalize_obs_half_open():
    start,end=normalize_obs('2026-09-01','2026-11-15')
    assert start=='2026-09-01T00:00:00+00:00' and end=='2026-11-16T00:00:00+00:00'
