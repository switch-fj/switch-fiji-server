from pydantic import BaseModel

from app.modules.devices.schema import MeterRoleEnum
from app.modules.sites.wizard.base_energy_usage import (
    BaseEnergyUsageWizard,
    EnergyUsageDataPoint,
    PPAEnergyUsageItem,
)
from app.shared.constants import TIME_FRAME


class PPAEnergyMeters(BaseModel):
    gen_meter: dict
    load_meter: dict
    micro_inv: dict
    aux_loads: dict


class PPAEnergyInverters(BaseModel):
    solar: float
    battery: float
    battery_flow: float
    battery_socs: dict[str, float]


class PPAOffGridEnergyUsageWizard(BaseEnergyUsageWizard):
    def __init__(self, telemetry_readings: list[dict]):
        self.telmetry_readings = telemetry_readings

    def _extract_meters(self, telemetry_data: dict):
        gen_meter = None
        load_meter = None
        micro_inv = None
        aux_loads = None

        meters: list[dict] = telemetry_data.get("meters", [])

        if not len(meters):
            raise ValueError("PPA Off-grid telemetry reading has empty meter data")

        for meter in meters:
            description = meter.get("description", "")
            if description == MeterRoleEnum.GEN_METER.value:
                gen_meter = meter

            if description == MeterRoleEnum.LOAD_METER.value:
                load_meter = meter

            if description == MeterRoleEnum.MICRO_INV.value:
                micro_inv = meter

            if description == MeterRoleEnum.AUX_LOADS.value:
                aux_loads = meter

        return PPAEnergyMeters(
            gen_meter=gen_meter,
            load_meter=load_meter,
            aux_loads=aux_loads,
            micro_inv=micro_inv,
        )

    def _extract_inverters(self, telemetry_data: dict):
        inverters: list[dict] = telemetry_data.get("inverters", [])

        if not len(inverters):
            raise ValueError("PPA Off-grid telemetry reading has empty inverter data")

        return inverters

    def _extract_solar_battery_battery_soc(self, inverters: list[dict]):
        solar = 0.0
        battery = 0.0
        battery_flow = 0.0
        soc_weighted_sum: dict[str, float] = {}
        soc_weight: dict[str, float] = {}

        for inverter in inverters:
            pv_total = sum(
                float(value)
                for key, value in inverter.items()
                if self.PV_POWER_PATTERN.match(key) and value is not None
            )
            solar += pv_total

            raw_battery_power_w = float(inverter.get(self.BATTERY_POWER_KEY, 0) or 0)
            battery_power_w = abs(raw_battery_power_w)  # magnitude — used for weighting

            battery += battery_power_w
            battery_flow += raw_battery_power_w  # signed — preserves direction

            for key, value in inverter.items():
                if self.BATTERY_SOC_PATTERN.match(key) and value is not None:
                    soc_weighted_sum[key] = soc_weighted_sum.get(key, 0) + battery_power_w * float(value)
                    soc_weight[key] = soc_weight.get(key, 0) + battery_power_w

        battery_socs = {k: (soc_weighted_sum[k] / soc_weight[k] if soc_weight[k] else 0.0) for k in soc_weighted_sum}

        return PPAEnergyInverters(
            solar=solar,
            battery=battery,
            battery_flow=battery_flow,
            battery_socs=battery_socs,
        )

    def compute_energy_usage(self):
        energy_usage: list[PPAEnergyUsageItem | None] = []
        for time_at, reading in zip(TIME_FRAME, self.telmetry_readings):
            if reading:
                meters = self._extract_meters(reading)
                inverters = self._extract_inverters(reading)

                solar_battery_and_soc = self._extract_solar_battery_battery_soc(inverters=inverters)
                gen = float(meters.gen_meter.get(self.TOTAL_POWER_KEY, 0))
                consumption = float(meters.load_meter.get(self.TOTAL_POWER_KEY, 0))
                aux_loads = float(meters.aux_loads.get(self.TOTAL_POWER_KEY, 0))
                micro_inv = float(meters.micro_inv.get(self.TOTAL_POWER_KEY, 0))

                energy_usage.append(
                    PPAEnergyUsageItem(
                        time_at=time_at,
                        data=EnergyUsageDataPoint(
                            solar=round(solar_battery_and_soc.solar, 0),
                            grid=round(gen, 0),
                            battery=round(solar_battery_and_soc.battery, 0),
                            battery_flow=round(solar_battery_and_soc.battery_flow, 0),
                            soc={k: round(v, 0) for k, v in solar_battery_and_soc.battery_socs.items()},
                            aux_loads=round(aux_loads, 0),
                            micro_inv=round(micro_inv, 0),
                            consumption=round(consumption, 0),
                        ),
                    )
                )

            else:
                energy_usage.append(
                    PPAEnergyUsageItem(
                        time_at=time_at,
                    )
                )

        return energy_usage
