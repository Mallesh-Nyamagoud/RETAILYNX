from fastapi import APIRouter, Depends, Query
from app.api.routes.auth import get_current_user
from app.services import soh_analysis
router=APIRouter(prefix="/soh",tags=["soh-analysis"],dependencies=[Depends(get_current_user)])
@router.get("/dates")
def dates(): return {"dates":soh_analysis.get_dates()}
@router.get("/summary")
def summary(opening:str=Query(...),ending:str=Query(...),threshold:float=Query(1.0)): return soh_analysis.get_summary(opening,ending,threshold)
