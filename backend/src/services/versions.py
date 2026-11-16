from sqlalchemy import select
from src.models.entities import Plan
from src.services.tutoring import parse_dt
def _overlaps(plan,intervals):
    """方案观察期（半开区间）与任一时段相交即视为受影响。"""
    if not plan.obs_start or not plan.obs_end: return False
    obs_s,obs_e=parse_dt(plan.obs_start),parse_dt(plan.obs_end)
    return any(s<obs_e and e>obs_s for s,e in intervals)
def bump_plans(db,plans):
    for plan in plans: plan.data_version=(plan.data_version or 0)+1
def bump_for_checkin(db,campuses,intervals):
    """签到新增/更正/撤销/恢复：影响“教学点匹配且观察期与时段相交”的方案。
    学员教学点未知时保守地使全部方案失效，保证并发修订不被漏掉。"""
    plans=db.scalars(select(Plan)).all()
    hit=[p for p in plans if (campuses is None or p.campus=='全部' or p.campus in campuses) and _overlaps(p,intervals)]
    bump_plans(db,hit)
def bump_for_student(db,campuses):
    """学员成绩/缺考/分组/教学点等源数据变化：影响新旧教学点命中的方案。"""
    plans=db.scalars(select(Plan)).all()
    bump_plans(db,[p for p in plans if p.campus=='全部' or p.campus in campuses])
def bump_for_plan(db,plan):
    """方案自身口径（观察期/门槛/教学点/排除规则）变化：仅使本方案失效。"""
    bump_plans(db,[plan])
