import math,hashlib,json
from scipy import stats

def _welch_math(control,treatment):
    n0,n1=len(control),len(treatment)
    if min(n0,n1)<2: raise ValueError('每组至少需要 2 个有效成绩；请调整教学点或补录样本')
    m0,m1=sum(control)/n0,sum(treatment)/n1
    v0=sum((x-m0)**2 for x in control)/(n0-1)
    v1=sum((x-m1)**2 for x in treatment)/(n1-1)
    se2=v0/n0+v1/n1
    if se2<=0: raise ValueError('两组方差均为零，无法进行 Welch 检验')
    df=se2**2/((v0/n0)**2/(n0-1)+(v1/n1)**2/(n1-1))
    se=math.sqrt(se2);delta=m1-m0;t=delta/se
    p=float(2*stats.t.sf(abs(t),df))
    margin=float(stats.t.ppf(.975,df))*se
    pooled=math.sqrt(((n0-1)*v0+(n1-1)*v1)/(n0+n1-2))
    return {'control_n':n0,'intervention_n':n1,'control_mean':m0,'intervention_mean':m1,'difference':delta,'t':t,'df':df,'p_value':p,'ci_low':delta-margin,'ci_high':delta+margin,'cohen_d':delta/pooled if pooled else None,'significant':p<.05}

def welch(students,plan):
    selected=[s for s in students if plan.campus=='全部' or s.campus==plan.campus]
    kept=[s for s in selected if s.score is not None and (not plan.exclude_absent or not s.absent)]
    control=[s.score for s in kept if s.group=='control']
    treatment=[s.score for s in kept if s.group=='intervention']
    result=_welch_math(control,treatment)
    digest=hashlib.sha256(json.dumps([(s.code,s.score,s.group,s.absent) for s in kept],ensure_ascii=False).encode()).hexdigest()
    return {**result,'excluded':len(selected)-len(kept),'total_selected':len(selected),'checksum':digest,'sample_snapshot':[{'code':s.code,'group':s.group,'score':s.score,'campus':s.campus} for s in kept],'method':'Welch 独立样本 t 检验；双侧 α=0.05；干预组减对照组；95% CI'}

def welch_actual(students,plan,calc):
    """按实际辅导量分组：分组来自时长核算结果，报名分组仅作对照保留。"""
    amap={s['code']:s for s in calc['students']}
    selected=[s for s in students if plan.campus=='全部' or s.campus==plan.campus]
    kept=[s for s in selected if s.score is not None and (not plan.exclude_absent or not s.absent)]
    classified=[s for s in kept if s.code in amap]
    control=[s.score for s in classified if amap[s.code]['actual_group']=='actual_control']
    treatment=[s.score for s in classified if amap[s.code]['actual_group']=='actual_intervention']
    result=_welch_math(control,treatment)
    reg_control=[s.score for s in classified if s.group=='control']
    reg_intervention=[s.score for s in classified if s.group=='intervention']
    snapshot=[{'code':s.code,'reg_group':s.group,'actual_group':amap[s.code]['actual_group'],'minutes':amap[s.code]['minutes'],'score':s.score,'campus':s.campus} for s in classified]
    digest=hashlib.sha256(json.dumps([(s['code'],s['score'],s['actual_group'],s['minutes']) for s in snapshot],ensure_ascii=False).encode()).hexdigest()
    return {**result,'grouping':'actual','threshold_minutes':calc['threshold_minutes'],'calc_checksum':calc['checksum'],
        'excluded':len(selected)-len(kept),'unclassified':len(kept)-len(classified),'total_selected':len(selected),
        'reg_group_summary':{'control_n':len(reg_control),'control_mean':sum(reg_control)/len(reg_control) if reg_control else None,
            'intervention_n':len(reg_intervention),'intervention_mean':sum(reg_intervention)/len(reg_intervention) if reg_intervention else None},
        'checksum':digest,'sample_snapshot':snapshot,
        'method':'Welch 独立样本 t 检验（按实际辅导量分组）；双侧 α=0.05；实际辅导组减实际对照组；95% CI'}
