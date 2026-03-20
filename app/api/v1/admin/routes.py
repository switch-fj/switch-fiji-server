from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("")
async def root():
    return {"message": "admin root 🚀"}
