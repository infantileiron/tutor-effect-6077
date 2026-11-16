import hashlib,json
from datetime import datetime,timezone,timedelta
FMT='%Y-%m-%dT%H:%M:%S+00:00'
def parse_dt(value):
    """解析 ISO 日期或日期时间；朴素时间按 UTC 处理，统一规范化为秒级 UTC 字符串可比较的 datetime。"""
    if value is None: raise ValueError('时间不能为空')
    text=str(value).strip()
    if not text: raise ValueError('时间不能为空')
    if len(text)==10 and text[4]=='-': text+='T00:00:00'
    dt=datetime.fromisoformat(text)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0)
def iso(dt): return dt.strftime(FMT)
def normalize_obs(start_text,end_text):
    """观察期规整为半开区间 [obs_start, obs_end)。仅日期时结束日顺延一天，表示含当日。"""
    start=parse_dt(start_text)
    end=parse_dt(end_text)
    if len(str(end_text).strip())==10: end=end+timedelta(days=1)
    if not start<end: raise ValueError('观察期开始必须早于结束')
    return iso(start),iso(end)
def merge_intervals(intervals):
    """合并重叠或相接的时段。intervals: [(start_dt,end_dt,[来源记录id])]，返回同构列表。"""
    merged=[]
    for s,e,sources in sorted(intervals,key=lambda x:x[0]):
        if merged and s<=merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],e)
            merged[-1][2]=sorted(merged[-1][2]+sources)
        else: merged.append([s,e,list(sources)])
    return merged
def compute_calculation(plan,students,checkins):
    """按方案观察期裁剪签到记录，合并重叠时段后累计时长，按门槛划分实际辅导组。
    纯函数：同一输入必然得到同一结果，重试/重算不会重复计时。"""
    if not plan.obs_start or not plan.obs_end: raise ValueError('方案尚未登记观察期，请先在辅导分组中补全')
    obs_s,obs_e=parse_dt(plan.obs_start),parse_dt(plan.obs_end)
    scope=[s for s in students if plan.campus=='全部' or s.campus==plan.campus]
    active,revoked={},{}
    for c in checkins:
        (revoked if c.revoked else active).setdefault(c.student_code,[]).append(c)
    rows=[]
    for stu in scope:
        clipped=[]
        for c in active.get(stu.code,[]):
            s,e=max(parse_dt(c.start_at),obs_s),min(parse_dt(c.end_at),obs_e)
            if s<e: clipped.append((s,e,[c.id]))
        merged=merge_intervals(clipped)
        minutes=round(sum((e-s).total_seconds()/60 for s,e,_ in merged),3)
        rows.append({'code':stu.code,'name':stu.name,'campus':stu.campus,'reg_group':stu.group,
            'minutes':minutes,'actual_group':'actual_intervention' if minutes>=plan.threshold_minutes else 'actual_control',
            'intervals':[{'start':iso(s),'end':iso(e),'minutes':round((e-s).total_seconds()/60,3),'sources':src} for s,e,src in merged],
            'active_records':len(active.get(stu.code,[])),'revoked_records':len(revoked.get(stu.code,[]))})
    rows.sort(key=lambda r:r['code'])
    canonical=[{'code':r['code'],'minutes':r['minutes'],'actual_group':r['actual_group'],'intervals':[[i['start'],i['end']] for i in r['intervals']]} for r in rows]
    checksum=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    summary={'total_students':len(rows),'with_time':sum(1 for r in rows if r['minutes']>0),
        'actual_intervention':sum(1 for r in rows if r['actual_group']=='actual_intervention'),
        'actual_control':sum(1 for r in rows if r['actual_group']=='actual_control'),
        'total_minutes':round(sum(r['minutes'] for r in rows),3),
        'revoked_records':sum(r['revoked_records'] for r in rows)}
    return {'plan_id':plan.id,'obs_start':iso(obs_s),'obs_end':iso(obs_e),'threshold_minutes':plan.threshold_minutes,
        'generated_at':iso(datetime.now(timezone.utc)),'students':rows,'summary':summary,'checksum':checksum,
        'method':'仅取未撤销签到 → 按观察期[开始,结束)裁剪 → 重叠及相接时段合并 → 累计分钟 ≥ 门槛者划入实际辅导组；原报名分组保留'}
def recompute_from_export(payload):
    """复算导出口径：用导出中的原始记录与参数重算学生汇总，用于校验 checksum。"""
    class P: pass
    plan=P();plan.id=payload['plan']['id'];plan.campus=payload['plan']['campus']
    plan.obs_start=payload['plan']['obs_start'];plan.obs_end=payload['plan']['obs_end']
    plan.threshold_minutes=payload['plan']['threshold_minutes']
    class C: pass
    checkins=[]
    for r in payload['records']:
        c=C();c.id=r['id'];c.student_code=r['student_code'];c.start_at=r['start_at'];c.end_at=r['end_at'];c.revoked=r['revoked'];checkins.append(c)
    class S: pass
    students=[]
    for s in payload['students']:
        st=S();st.code=s['code'];st.name=s.get('name','');st.campus=s['campus'];st.group=s['reg_group'];students.append(st)
    return compute_calculation(plan,students,checkins)
