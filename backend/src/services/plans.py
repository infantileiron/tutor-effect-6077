from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import Plan
from src.services.tutoring import normalize_obs
from src.services import versions
TRACKED=('obs_start','obs_end','threshold_minutes','campus','exclude_absent')
def list_plans(db):
    plans=db.scalars(select(Plan).order_by(Plan.id.desc())).all()
    out=[]
    for p in plans:
        d={c.name:getattr(p,c.name) for c in p.__table__.columns}
        d['obs_start_date']=p.obs_start[:10] if p.obs_start else ''
        d['obs_end_date']=''
        if p.obs_end:
            from datetime import timedelta
            from src.services.tutoring import parse_dt,iso
            d['obs_end_date']=iso(parse_dt(p.obs_end)-timedelta(microseconds=1))[:10]
        out.append(d)
    return out
def save_plan(db,data,id=None):
    item=db.get(Plan,id) if id else Plan()
    if not item: raise HTTPException(404,'方案不存在')
    payload=data.model_dump()
    if not payload['obs_start'] and not payload['obs_end']: payload['obs_start']=payload['obs_end']=''
    else:
        try: payload['obs_start'],payload['obs_end']=normalize_obs(payload['obs_start'],payload['obs_end'])
        except ValueError as e: raise HTTPException(422,str(e))
    old={k:getattr(item,k) for k in TRACKED} if id else None
    for k,v in payload.items(): setattr(item,k,v)
    db.add(item)
    if old is not None and any(old[k]!=getattr(item,k) for k in TRACKED): versions.bump_for_plan(db,item)
    db.commit();db.refresh(item)
    return item
