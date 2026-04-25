import json
from datetime import datetime, timezone
from decimal import Decimal

from celery.schedules import crontab
from sqlalchemy import text
from sqlalchemy.orm import joinedload
from sqlmodel import Session, select

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client, get_celery_db_session
from app.jobs.billing.engine import BillingEngine
from app.jobs.celery import celery_app
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum
from app.modules.devices.model import Device
from app.modules.devices.schema import DeviceType, MeterRoleEnum
from app.modules.invoices.model import (
    Invoice,
    InvoiceHistory,
    InvoiceLineItem,
    InvoiceMeterData,
)
from app.modules.invoices.repository import InvoiceRepository
from app.modules.invoices.schema import (
    CreateInvoiceHistoryModel,
    CreateInvoiceLineItemModel,
    CreateInvoiceMeterDataModel,
    CreateInvoiceModel,
    InvoiceLineItemEnum,
    InvoiceMeterLabelEnum,
)
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)

# Beat triggers at billing date (actually every day at midnight)
celery_app.conf.beat_schedule.update(
    {
        "compute-contract-bill-every-day-at_midnight": {
            "task": "compute_all_contracts_bill",
            "schedule": crontab(minute=0, hour=0),
        }
    }
)


@celery_app.task(
    name="compute_all_contracts_bill",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def compute_all_contracts_bill(self):
    """
    Beat triggers this every day at midnight.
    Fetches all active contracts and dispatches
    one compute task per contract to the worker pool.
    """
    try:
        # Worker spins up its own session
        with get_celery_db_session() as session:
            # fetch contract + site
            result = session.execute(
                text(
                    """
                SELECT
                    c.uid AS contract_uid,
                    s.gateway_id AS gateway_id,
                    s.site_id AS site_id,
                    s.uid as site_uid
                FROM contracts c
                JOIN sites s ON s.uid = c.site_uid
                JOIN contract_details cd ON cd.contract_uid = c.uid
                WHERE cd.commissioned_at IS NOT NULL
                    AND NOW() > cd.commissioned_at
                    AND NOW() < cd.end_at
                """
                )
            )
            contract_data = result.fetchall()

        for datum in contract_data:
            # Worker for individual active contracts
            compute_single_contract_bill.delay(
                contract_uid=str(datum.contract_uid),
                gateway_id=datum.gateway_id,
                site_uid=str(datum.site_uid),
                site_id=datum.site_id,
            )
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="compute_single_contract_bill", bind=True, max_retries=3, default_retry_delay=5)
def compute_single_contract_bill(self, contract_uid, gateway_id, site_uid, site_id):
    try:
        celery_dynamo_client.init()
        with get_celery_db_session() as session:
            contract = session.execute(
                select(Contract)
                .options(joinedload(Contract.details), joinedload(Contract.client))
                .where(Contract.uid == contract_uid)
            ).scalar_one_or_none()

            devices = (
                session.execute(
                    select(Device).where(
                        Device.site_uid == site_uid,
                        Device.device_type == DeviceType.METER.value,
                    )
                )
                .scalars()
                .all()
            )

            contract_settings = session.execute(select(ContractSettings)).scalars().first()

            if not contract or not devices:
                return

            # route to the correct billing function
            if contract.contract_type == ContractTypeEnum.PPA.value:
                if contract.system_mode == ContractSystemModeEnum.OFF_GRID.value:
                    _compute_ppa_off_grid(session, contract, devices, contract_settings, gateway_id)
                elif contract.system_mode == ContractSystemModeEnum.ON_GRID.value:
                    pass
                    # _compute_ppa_on_grid(
                    #     session, contract, devices, contract_settings, gateway_id
                    # )

            elif contract.contract_type == ContractTypeEnum.LEASE.value:
                pass
                # _compute_lease(
                #     session, contract, devices, contract_settings, gateway_id
                # )

    except Exception as exc:
        raise self.retry(exc=exc)


def _compute_ppa_off_grid(
    session: Session,
    contract: Contract,
    devices: list[Device],
    contract_settings: ContractSettings,
    gateway_id: str,
):
    active_tariff_slots = contract.details.active_tariff_slots
    period_start, period_end = BillingEngine.get_current_billing_period(
        commissioned_at=contract.details.commissioned_at,
        billing_frequency=contract.details.billing_frequency,
    )

    readings = celery_dynamo_client.get_readings_for_billing_period(
        gateway_id=gateway_id,
        period_start=period_start,
        period_end=period_end,
    )
    if not readings:
        logger.warning(f"No readings found for gateway {gateway_id}")
        return

    period_start_data, period_end_data = readings

    period_start_meter = BillingEngine.get_ppa_off_grid_meter_data(period_start_data)
    period_end_meter = BillingEngine.get_ppa_off_grid_meter_data(period_end_data)

    load_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.LOAD_METER)
    gen_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.GEN_METER)

    usage = BillingEngine.compute_ppa_off_grid_day_night_usage(
        period_start_meter_tariff_reading=period_start_meter,
        period_end_meter_tariff_reading=period_end_meter,
    )
    on_solar_energy_kwh, off_solar_energy_kwh = BillingEngine.compute_ppa_off_grid_line_items(usage=usage)
    solar_energy_kwh, gen_energy_kwh = BillingEngine.compute_ppa_off_grid_energy_mix(usage=usage)
    subtotal, vat_rate, on_solar_energy_amount, off_solar_energy_amount = (
        BillingEngine.compute_ppa_off_grid_subtotal_and_vat_rate(
            on_solar_energy_kwh=on_solar_energy_kwh,
            off_solar_energy_kwh=off_solar_energy_kwh,
            efl_rate_kwh=contract_settings.efl_standard_rate_kwh,
            active_tariff=active_tariff_slots,
        )
    )

    create_invoice_dict = CreateInvoiceModel(
        period_start_at=period_start,
        period_end_at=period_end,
        subtotal=subtotal,
        vat_rate=vat_rate,
        energy_mix=json.dumps({"solar": float(solar_energy_kwh), "gen": float(gen_energy_kwh)}),
    ).model_dump()
    create_invoice_dict["contract_uid"] = contract.uid
    create_invoice_dict["invoice_ref"] = InvoiceRepository._build_invoice_ref()

    new_invoice = Invoice(**create_invoice_dict)
    session.add(new_invoice)
    session.flush()

    create_meter_data: list[CreateInvoiceMeterDataModel] = []
    for device in devices:
        if device.slave_id == load_meter.get("slave_id"):
            create_meter_data.extend(
                [
                    CreateInvoiceMeterDataModel(
                        invoice_uid=new_invoice.uid,
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.SITE_METER_1_DAY.value,
                        period_start_reading=Decimal(period_start_meter[0][0]),
                        period_end_reading=Decimal(period_end_meter[0][0]),
                    ),
                    CreateInvoiceMeterDataModel(
                        invoice_uid=new_invoice.uid,
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.SITE_METER_1_NIGHT.value,
                        period_start_reading=Decimal(period_start_meter[0][1]),
                        period_end_reading=Decimal(period_end_meter[0][1]),
                    ),
                ]
            )

        if device.slave_id == gen_meter.get("slave_id"):
            create_meter_data.extend(
                [
                    CreateInvoiceMeterDataModel(
                        invoice_uid=new_invoice.uid,
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.GEN_METER_1_DAY.value,
                        period_start_reading=Decimal(period_start_meter[1][0]),
                        period_end_reading=Decimal(period_end_meter[1][0]),
                    ),
                    CreateInvoiceMeterDataModel(
                        invoice_uid=new_invoice.uid,
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.GEN_METER_1_NIGHT.value,
                        period_start_reading=Decimal(period_start_meter[1][1]),
                        period_end_reading=Decimal(period_end_meter[1][1]),
                    ),
                ]
            )

    create_line_items = [
        CreateInvoiceLineItemModel(
            invoice_uid=new_invoice.uid,
            description=InvoiceLineItemEnum.ON_SOLAR_ENERGY_SUPPLIED,
            energy_kwh=Decimal(on_solar_energy_kwh),
            tariff_rate=Decimal(active_tariff_slots[0]["rate"]),
            tariff_slot=active_tariff_slots[0]["slot"],
            tariff_period=int(active_tariff_slots[0]["period_number"]),
            amount=Decimal(on_solar_energy_amount),
        ),
        CreateInvoiceLineItemModel(
            invoice_uid=new_invoice.uid,
            description=InvoiceLineItemEnum.OFF_SOLAR_ENERGY_SUPPLIED,
            energy_kwh=Decimal(off_solar_energy_kwh),
            tariff_rate=Decimal(active_tariff_slots[1]["rate"]),
            tariff_slot=active_tariff_slots[1]["slot"],
            tariff_period=int(active_tariff_slots[1]["period_number"]),
            amount=Decimal(off_solar_energy_amount),
        ),
    ]

    session.add_all([InvoiceMeterData(**d.model_dump()) for d in create_meter_data])
    session.add_all([InvoiceLineItem(**d.model_dump()) for d in create_line_items])
    session.add(
        InvoiceHistory(
            **CreateInvoiceHistoryModel(
                invoice_uid=new_invoice.uid,
                sent_to=contract.client.client_email,
                sent_at=datetime.now(timezone.utc),
                was_successful=True,
            ).model_dump()
        )
    )
    session.commit()


# def _compute_lease(
#     session,
#     contract,
#     devices,
#     contract_settings,
#     gateway_id,
# ):
#     pass


# def _compute_ppa_on_grid(
#     session,
#     contract,
#     devices,
#     contract_settings,
#     gateway_id,
# ):
#     pass
