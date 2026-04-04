from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.core.config import Config
from app.core.security import AccessTokenBearer
from app.modules.clients.schema import ClientRespModel
from app.modules.sites.schema import SiteRespModel
from app.services.client import ClientService, get_client_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import (
    CursorPaginationModel,
    IdentityTypeEnum,
    PaginatedRespModel,
    ServerRespModel,
    UserRoleEnum,
)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get(
    "/clients",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[PaginatedRespModel[ClientRespModel, CursorPaginationModel]],
)
async def get_clients(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=Config.DEFAULT_PAGE_LIMIT),
    next_cursor: Optional[str] = Query(default=None),
    prev_cursor: Optional[str] = Query(default=None),
    client_service: ClientService = Depends(get_client_service),
    _: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER],
            required_role=[UserRoleEnum.ADMIN],
        )
    ),
):
    result = await client_service.get_clients(q=q, limit=limit, next_cursor=next_cursor, prev_cursor=prev_cursor)

    return JSONResponse(
        content=ServerRespModel[PaginatedRespModel[ClientRespModel, CursorPaginationModel]](
            data=result, message="clients retrieved"
        ).model_dump()
    )


@admin_router.get(
    "/sites/{client_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[list[SiteRespModel]],
)
async def get_client_sites_by_uid(
    client_uid: UUID,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER],
            required_role=[UserRoleEnum.ADMIN],
        )
    ),
):
    sites = await site_service.get_sites_by_client_uid(client_uid=client_uid)

    return JSONResponse(
        content=ServerRespModel[list[SiteRespModel]](data=sites, message="client's sites retrieved").model_dump()
    )
