from sqlalchemy import select
from src.models.entities import Student
from src.services import versions
from fastapi import HTTPException
TRACKED=('code','campus','group','score','absent')
def list_students(db): return db.scalars(select(Student).order_by(Student.id)).all()
def save_student(db,data,id=None):
    item=db.get(Student,id) if id else Student()
    if not item: raise HTTPException(404,'学员不存在')
    old={k:getattr(item,k) for k in TRACKED} if id else None
    for k,v in data.model_dump().items(): setattr(item,k,v)
    db.add(item)
    if old is None or any(old[k]!=getattr(item,k) for k in TRACKED):
        campuses={item.campus}|({old['campus']} if old else set())
        versions.bump_for_student(db,campuses)
    db.commit();db.refresh(item)
    return item
