from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.device.schema import DeviceModel
from app.core.security import AccessTokenBearer
from app.services.devices import DeviceService, get_device_service
from app.shared.schema import ServerRespModel

device_router = APIRouter(prefix="/device", tags=["device"])


@device_router.get(
    "/site/{site_uid}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[List[DeviceModel]],
)
async def get_devices_by_site(
    site_uid: UUID,
    device_service: DeviceService = Depends(get_device_service),
    _: dict = Depends(AccessTokenBearer()),
):
    devices = await device_service.get_devices_by_site(site_uid=site_uid)

    return ServerRespModel[List[DeviceModel]](
        data=[DeviceModel.model_validate(device.model_dump()) for device in devices],
        message="Site devices retrieved.",
    )
