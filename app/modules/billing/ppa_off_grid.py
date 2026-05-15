import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.modules.billing.schema import (
    PPAOffGridEnergyMix,
    PPAOffGridExtractedMeters,
    PPAOffGridNoBatteryEnergyData,
    PPAOnAndOffGridEnergyItem,
)
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import TariffIndexedRuleTypeEnum, TariffSlotTypeEnum
from app.modules.devices.model import Device
from app.modules.devices.schema import MeterRoleEnum
from app.modules.invoices.model import InvoiceSnapshot
from app.modules.invoices.schema import (
    BaseInvoiceLineItemModel,
    BaseInvoiceMeterDataModel,
    CreateInvoiceModel,
    InvoiceLineItemEnum,
    InvoiceMeterLabelEnum,
)
from app.modules.settings.model import ContractSettings
from app.utils import two_decimal_place


class PPAOffGridFactory:
    def __init__(
        self,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        start_meters: PPAOffGridExtractedMeters,
        end_meters: PPAOffGridExtractedMeters,
        energy_data: PPAOffGridNoBatteryEnergyData,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        self.telemetry_start_reading = telemetry_start_reading
        self.telemetry_end_reading = telemetry_end_reading
        self.start_meters = start_meters
        self.end_meters = end_meters
        self.energy_data = energy_data
        self.contract = contract
        self.devices = devices
        self.contract_settings = contract_settings

    @classmethod
    def _extract_meters(self, telemetry_data: dict):
        gen_meter = None
        load_meter = None

        meters: list[dict] = telemetry_data.get("meters", [])

        if not len(meters):
            raise ValueError("PPA Off-grid telemetry data has empty meter data")

        for meter in meters:
            if meter.get(MeterRoleEnum.GEN_METER.value, None):
                gen_meter = meter.get(MeterRoleEnum.GEN_METER.value)

            if meter.get(MeterRoleEnum.LOAD_METER.value, None):
                load_meter = meter.get(MeterRoleEnum.LOAD_METER.value)

        return PPAOffGridExtractedMeters(gen_meter=gen_meter, load_meter=load_meter)

    @classmethod
    def factory(
        cls,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        # start period
        start_meters: PPAOffGridExtractedMeters = cls._extract_meters(telemetry_data=telemetry_start_reading)

        start_gen_meter = start_meters.gen_meter
        start_load_meter = start_meters.load_meter

        # end period
        end_meters: PPAOffGridExtractedMeters = cls._extract_meters(telemetry_data=telemetry_end_reading)

        end_gen_meter = end_meters.gen_meter
        end_load_meter = end_meters.load_meter

        load = PPAOnAndOffGridEnergyItem(
            slave_id=start_load_meter["slave_id"],
            description="Site Meter",
            start_day_tariff=start_load_meter.get("tariff", 0)["kwh_t1"],
            start_night_tariff=start_load_meter.get("tariff", 0)["kwh_t2"],
            end_day_tariff=end_load_meter.get("tariff", 0)["kwh_t1"],
            end_night_tariff=end_load_meter.get("tariff", 0)["kwh_t2"],
        )

        gen = PPAOnAndOffGridEnergyItem(
            slave_id=start_gen_meter["slave_id"],
            description="Generator Meter",
            start_day_tariff=start_gen_meter.get("tariff", 0)["kwh_t1"],
            start_night_tariff=start_gen_meter.get("tariff", 0)["kwh_t2"],
            end_day_tariff=end_gen_meter.get("tariff", 0)["kwh_t1"],
            end_night_tariff=end_gen_meter.get("tariff", 0)["kwh_t2"],
        )

        energy_data = PPAOffGridNoBatteryEnergyData(load=load, gen=gen)

        return cls(
            energy_data=energy_data,
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            start_meters=start_meters,
            end_meters=end_meters,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

    def calculate_slot_rate(self, tariff_slot: dict):
        tariff_indexed_rule_type = self.contract.details.tariff_indexed_rule_type
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        if tariff_slot["slot_type"] == TariffSlotTypeEnum.FIXED:
            return Decimal(str(tariff_slot["rate"]))

        rate = Decimal(str(tariff_slot["rate"]))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:
            multiplier = (Decimal(100) + rate) / Decimal(100)
            return Decimal(efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
            raise NotImplementedError("FIXED_ANNUAL_ESCALATOR is not yet supported for PPA off-grid tariff")
        raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

    @property
    def energy_mix(self):
        load = self.energy_data.load.day_usage + self.energy_data.load.night_usage
        gen = self.energy_data.gen.day_usage + self.energy_data.gen.night_usage

        return PPAOffGridEnergyMix(
            load=float(f"{load:.2f}"),
            gen=float(f"{gen:.2f}"),
        )

    @property
    def day_tariff(self):
        return self.contract.details.active_tariff_slots[0]

    @property
    def night_tariff(self):
        return self.contract.details.active_tariff_slots[1]

    @property
    def on_solar_energy_kwh(self):
        return self.energy_data.load.day_usage - self.energy_data.gen.day_usage

    @property
    def off_solar_energy_kwh(self):
        return self.energy_data.load.night_usage - self.energy_data.gen.night_usage

    @property
    def on_solar_energy_amount(self):
        day_rate = self.calculate_slot_rate(tariff_slot=self.day_tariff)

        return two_decimal_place(self.on_solar_energy_kwh * day_rate)

    @property
    def off_solar_energy_amount(self):
        night_rate = self.calculate_slot_rate(tariff_slot=self.night_tariff)

        return two_decimal_place(self.off_solar_energy_kwh * night_rate)

    @property
    def subtotal(self):
        return two_decimal_place(self.on_solar_energy_amount + self.off_solar_energy_amount)

    def invoice(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
        contract_uid: UUID,
        invoice_ref: str,
    ):
        create_invoice_model: CreateInvoiceModel = CreateInvoiceModel(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_end_reading)),
            subtotal=self.subtotal,
            vat_rate=self.contract_settings.vat_rate,
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
        ).model_dump()

        create_invoice_model["contract_uid"] = contract_uid
        create_invoice_model["invoice_ref"] = invoice_ref

        return create_invoice_model

    def invoice_snapshot(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
    ):
        return InvoiceSnapshot(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_end_reading)),
            subtotal=self.subtotal,
            vat_rate=self.contract_settings.vat_rate,
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
        )

    @property
    def invoice_line_items(self):
        create_invoice_line_items = [
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.ON_SOLAR_ENERGY_SUPPLIED.value,
                energy_kwh=Decimal(self.on_solar_energy_kwh),
                tariff_rate=Decimal(self.day_tariff["rate"]),
                tariff_slot=self.day_tariff["slot"],
                tariff_period=int(self.day_tariff["period_number"]),
                amount=Decimal(self.on_solar_energy_amount),
            ),
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.OFF_SOLAR_ENERGY_SUPPLIED.value,
                energy_kwh=Decimal(self.off_solar_energy_kwh),
                tariff_rate=Decimal(self.night_tariff["rate"]),
                tariff_slot=self.night_tariff["slot"],
                tariff_period=int(self.night_tariff["period_number"]),
                amount=Decimal(self.off_solar_energy_amount),
            ),
        ]

        return create_invoice_line_items

    @property
    def invoice_meter_data(self):
        create_invoice_meter_data: list[BaseInvoiceMeterDataModel] = []
        for device in self.devices:
            if device.slave_id == self.energy_data.load.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.SITE_METER_DAY.value,
                            period_start_reading=Decimal(self.energy_data.load.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.load.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.SITE_METER_NIGHT.value,
                            period_start_reading=Decimal(self.energy_data.load.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.load.start_night_tariff),
                        ),
                    ]
                )

            if device.slave_id == self.energy_data.gen.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_DAY.value,
                            period_start_reading=Decimal(self.energy_data.gen.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.gen.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_NIGHT.value,
                            period_start_reading=Decimal(self.energy_data.gen.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.gen.end_night_tariff),
                        ),
                    ]
                )

        return create_invoice_meter_data
