from fastapi import APIRouter

client_router = APIRouter(prefix="/client", tags=["client"])


@client_router.get("")
async def root():
    return {"message": "client root 🚀"}
