from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status

from app.api.v1.engineer.schema import (
    EngineeringDashboardClientModel,
    EngineeringDashboardSiteModel,
    ResourceStatsModel,
)
from app.core.config import Config
from app.core.security import EngineerAccessBearer
from app.modules.clients.schema import UpdateClientModel
from app.modules.sites.schema import UpdateSiteModel
from app.services.client import ClientService, get_client_service
from app.services.engineer import EngineeringService, get_engr_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import CursorPaginationModel, PaginatedRespModel, ServerRespModel

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

    return ServerRespModel[bool](
        data=True,
        message="Client updated!.",
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

    return ServerRespModel[bool](
        data=True,
        message="Site updated!.",
    )


@engineer_router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[ResourceStatsModel],
)
async def stats(
    engineering_service: EngineeringService = Depends(get_engr_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    stat = await engineering_service.stat()

    return ServerRespModel[ResourceStatsModel](
        data=stat,
        message="Stats retrieved",
    )


@engineer_router.get(
    "/clients",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[EngineeringDashboardClientModel, CursorPaginationModel]],
)
async def clients(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=Config.DEFAULT_PAGE_LIMIT),
    next_cursor: Optional[str] = Query(default=None),
    prev_cursor: Optional[str] = Query(default=None),
    client_service: ClientService = Depends(get_client_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    resp = await client_service.engineers_get_clients(
        q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor
    )

    return ServerRespModel[PaginatedRespModel[EngineeringDashboardClientModel, CursorPaginationModel]](
        data=resp,
        message="clients retrieved",
    )


@engineer_router.get(
    "/client/{client_uid}/sites",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[List[EngineeringDashboardSiteModel]],
)
async def client_sites(
    client_uid: UUID,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(EngineerAccessBearer()),
):
    resp = await site_service.engineers_get_site_details_by_client_uid(client_uid=client_uid)

    return ServerRespModel[List[EngineeringDashboardSiteModel]](
        data=resp,
        message="clients retrieved",
    )
