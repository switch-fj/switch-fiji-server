from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.core.config import Config
from app.core.security import AdminAccessBearer
from app.modules.clients.schema import ClientRespModel, CreateClientModel
from app.modules.sites.schema import CreateSiteModel, SiteRespModel
from app.services.client import ClientService, get_client_service
from app.services.sites import SiteService, get_site_service
from app.shared.schema import (
    CursorPaginationModel,
    PaginatedRespModel,
    ServerRespModel,
)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post(
    "/client/add",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def add_client(
    data: CreateClientModel,
    client_service: ClientService = Depends(get_client_service),
    token_payload: dict = Depends(AdminAccessBearer()),
):
    client = await client_service.register_client(data=data, token_payload=token_payload)

    return JSONResponse(
        content=ServerRespModel[str](data=str(client.uid), message="client added successfully").model_dump()
    )


@admin_router.post(
    "/site/add",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def add_site(
    data: CreateSiteModel,
    site_service: SiteService = Depends(get_site_service),
    _: dict = Depends(AdminAccessBearer()),
):
    site = await site_service.create_site(data=data)

    return JSONResponse(
        content=ServerRespModel[str](data=str(site.uid), message="Site added to client successfully").model_dump()
    )


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
    _: dict = Depends(AdminAccessBearer()),
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
    _: dict = Depends(AdminAccessBearer()),
):
    sites = await site_service.get_sites_by_client_uid(client_uid=client_uid)

    return JSONResponse(
        content=ServerRespModel[list[SiteRespModel]](data=sites, message="client's sites retrieved").model_dump()
    )
