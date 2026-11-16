import json
from fastapi import APIRouter,Depends
from fastapi.responses import Response
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import CalculationInput
from src.services import calculations
router=APIRouter()
@router.get('/calculations')
def listing(db=Depends(get_db),user=Depends(current_user)): return calculations.list_calculations(db)
@router.post('/calculations',status_code=202)
def create(data:CalculationInput,db=Depends(get_db),user=Depends(editor)):
    item=calculations.create_calculation(db,data.plan_id)
    return calculations.detail(db,item.id)
@router.get('/calculations/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)): return calculations.detail(db,id)
@router.get('/calculations/{id}/export')
def export(id:int,db=Depends(get_db),user=Depends(current_user)):
    payload=calculations.export_payload(db,id)
    return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="tutoring-time-calculation-{id}.json"'})
