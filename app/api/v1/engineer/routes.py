from fastapi import APIRouter

engineer_router = APIRouter(prefix="/engineer", tags=["engineer"])


@engineer_router.get("")
async def root():
    return {"message": "engineer root 🚀"}
