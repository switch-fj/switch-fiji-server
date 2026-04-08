from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.security import EngineerAccessBearer
from app.modules.clients.schema import UpdateClientModel
from app.modules.sites.schema import UpdateSiteModel
from app.services.client import ClientService, get_client_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import ServerRespModel

engineer_router = APIRouter(prefix="/engineer", tags=["engineer"])


@engineer_router.patch(
    "/client/{client_uid}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ServerRespModel[bool],
)
async def update_client(
    client_uid: str,
    data: UpdateClientModel = Body(...),
    client_service: ClientService = Depends(get_client_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    await client_service.update_client(client_uid=client_uid, data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="Client updated!.",
        ).model_dump(),
    )


@engineer_router.patch(
    "/site",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ServerRespModel[bool],
)
async def update_site(
    site_uid: str,
    data: UpdateSiteModel = Body(...),
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    await site_service.update_site(site_uid=site_uid, data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="Site updated!.",
        ).model_dump(),
    )
