from fastapi import APIRouter
router = APIRouter()

@router.get("")
async def system_status():
    return {"status": "running", "version": "0.1.0"}
