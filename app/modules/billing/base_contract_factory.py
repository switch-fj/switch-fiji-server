from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.invoices.model import InvoiceSnapshot
from app.modules.invoices.schema import (
    BaseInvoiceLineItemModel,
    BaseInvoiceMeterDataModel,
)
from app.modules.settings.model import ContractSettings


class BaseContractFactory(ABC):
    @classmethod
    @abstractmethod
    def factory(
        cls,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ) -> "BaseContractFactory": ...

    @property
    @abstractmethod
    def subtotal(self) -> Decimal: ...

    @property
    @abstractmethod
    def energy_mix(self): ...

    @property
    @abstractmethod
    def invoice_line_items(self) -> list[BaseInvoiceLineItemModel]: ...

    @property
    @abstractmethod
    def invoice_meter_data(self) -> list[BaseInvoiceMeterDataModel]: ...

    @abstractmethod
    def invoice(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
        contract_uid: UUID,
        invoice_ref: str,
    ) -> dict: ...

    @abstractmethod
    def invoice_snapshot(self, period_start_at: datetime, period_end_at: datetime) -> InvoiceSnapshot: ...
