from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import CheckinInput
from src.services import checkins
from src.controllers.business import serialize,serialize_many
router=APIRouter()
@router.get('/checkins')
def listing(db=Depends(get_db),user=Depends(current_user)): return serialize_many(checkins.list_checkins(db))
@router.post('/checkins',status_code=201)
def create(data:CheckinInput,db=Depends(get_db),user=Depends(editor)): return serialize(checkins.create_checkin(db,data))
@router.put('/checkins/{id}')
def update(id:int,data:CheckinInput,db=Depends(get_db),user=Depends(editor)): return serialize(checkins.update_checkin(db,id,data))
@router.post('/checkins/{id}/revoke')
def revoke(id:int,db=Depends(get_db),user=Depends(editor)): return serialize(checkins.set_revoked(db,id,True))
@router.post('/checkins/{id}/restore')
def restore(id:int,db=Depends(get_db),user=Depends(editor)): return serialize(checkins.set_revoked(db,id,False))
