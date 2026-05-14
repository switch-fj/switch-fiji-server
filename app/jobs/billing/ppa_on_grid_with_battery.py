from decimal import Decimal

from app.jobs.billing.schema import (
    PPAOnGridEnergyItem,
    PPAOnGridWithBatterExtractedMeters,
    PPAOnGridWithBatteryEnergyData,
)


class PPAOnGridWithBatteryEngine:
    def __init__(
        self,
        energy_data: PPAOnGridWithBatteryEnergyData,
        extracted_meters_t1: PPAOnGridWithBatterExtractedMeters,
        extracted_meters_t2: PPAOnGridWithBatterExtractedMeters,
        start_reading: dict,
        end_reading: dict,
    ):
        self.energy_data = energy_data
        self.extracted_meters_t1 = extracted_meters_t1
        self.extracted_meters_t2 = extracted_meters_t2
        self.start_reading = start_reading
        self.end_reading = end_reading

    def _extract_meters(self, reading: dict):
        grid_meter = None
        essential_loads_meter = None
        non_essential_loads_meter = None
        generator_meter = None
        meters = reading.get("meters", [])

        for meter in meters:
            if meter.get("grid_meter", None):
                grid_meter = meter.get("grid_meter")

            if meter.get("essential_loads_meter", None):
                essential_loads_meter = meter.get("essential_loads_meter")

            if meter.get("non_essential_loads_meter", None):
                non_essential_loads_meter = meter.get("non_essential_loads_meter")

            if meter.get("generator_meter", None):
                generator_meter = meter.get("generator_meter")

        return PPAOnGridWithBatterExtractedMeters.model_validate(
            {
                "grid_meter": grid_meter,
                "essential_loads_meter": essential_loads_meter,
                "non_essential_loads_meter": non_essential_loads_meter,
                "generator_meter": generator_meter,
            }
        )

    def _total_facility_consumption(self, essential_loads_meter: dict, non_essential_loads_meter: dict):
        essential_load_kwh = essential_loads_meter.get("kwh_total", 0)
        non_essential_load_kwh = non_essential_loads_meter.get("kwh_total", 0)

        return float(essential_load_kwh + non_essential_load_kwh)

    def _net_grid_contribution(self, grid_meter: dict):
        kwh_import = grid_meter.get("kwh_import", 0)
        kwh_export = grid_meter.get("kwh_export", 0)

        return float(kwh_import - kwh_export)

    def _net_grid_import(self, kwh_import_t1: int, kwh_import_t2: int):
        return float(kwh_import_t2 - kwh_import_t1)

    def _net_grid_export(self, kwh_export_t1: int, kwh_export_t2: int):
        return float(kwh_export_t2 - kwh_export_t1)

    def _delta_facility_consumption(self, fc_t1: float, fc_t2: float):
        return fc_t2 - fc_t1

    def _delta_net_grid_contribution(self, ngc_t1: float, ngc_t2: float):
        return ngc_t2 - ngc_t1

    def billable_energy_kwh(self):
        extracted_meters_t1 = self.extracted_meters_t1
        grid_meter_t1 = extracted_meters_t1.grid_meter
        essential_loads_meter_t1 = extracted_meters_t1.essential_loads_meter
        non_essential_loads_meter_t1 = extracted_meters_t1.non_essential_loads_meter

        fc_t1 = self._total_facility_consumption(
            essential_loads_meter=essential_loads_meter_t1,
            non_essential_loads_meter=non_essential_loads_meter_t1,
        )
        ngc_t1 = self._net_grid_contribution(grid_meter=grid_meter_t1)

        # end period (T2)
        extracted_meters_t2 = self.extracted_meters_t2
        grid_meter_t2 = extracted_meters_t2.grid_meter
        essential_loads_meter_t2 = extracted_meters_t2.essential_loads_meter
        non_essential_loads_meter_t2 = extracted_meters_t2.non_essential_loads_meter

        fc_t2 = self._total_facility_consumption(
            essential_loads_meter=essential_loads_meter_t2,
            non_essential_loads_meter=non_essential_loads_meter_t2,
        )
        ngc_t2 = self._net_grid_contribution(grid_meter=grid_meter_t2)

        # 3. Compute Deltas
        delta_fc = self._delta_facility_consumption(fc_t1=fc_t1, fc_t2=fc_t2)
        delta_ngc = self._delta_net_grid_contribution(ngc_t1=ngc_t1, ngc_t2=ngc_t2)

        energy_used_kwh = max(0.0, delta_fc - delta_ngc)

        # Data integrity check (e.g., if a meter was swapped out/reset to 0)
        if delta_fc < 0 or grid_meter_t2["kwh_import"] < grid_meter_t2["kwh_import"]:
            raise ValueError("Negative consumption detected. Meter may have been reset.")

        return energy_used_kwh

    def compute_cost(self, energy_kwh: float, tariff_rate: Decimal):
        return Decimal(Decimal(energy_kwh) * tariff_rate).quantize(Decimal("0.01"))

    @classmethod
    def factory(cls, start_reading: dict, end_reading: dict):
        # start period (T1)
        extracted_meters_t1: PPAOnGridWithBatterExtractedMeters = cls._extract_meters(reading=start_reading)
        grid_meter_t1 = extracted_meters_t1.grid_meter
        essential_loads_meter_t1 = extracted_meters_t1.essential_loads_meter
        non_essential_loads_meter_t1 = extracted_meters_t1.non_essential_loads_meter

        # end period (T2)
        extracted_meters_t2: PPAOnGridWithBatterExtractedMeters = cls._extract_meters(reading=end_reading)
        grid_meter_t2 = extracted_meters_t2.grid_meter
        essential_loads_meter_t2 = extracted_meters_t2.essential_loads_meter
        non_essential_loads_meter_t2 = extracted_meters_t2.non_essential_loads_meter

        essesntial = PPAOnGridEnergyItem(
            slave_id=essential_loads_meter_t1["slave_id"],
            description="Essential Energy",
            start_kwh=essential_loads_meter_t1["kwh_total"],
            end_kwh=essential_loads_meter_t2["kwh_total"],
        )
        non_essential = PPAOnGridEnergyItem(
            slave_id=non_essential_loads_meter_t1["slave_id"],
            description="Non-Essential Energy",
            start_kwh=non_essential_loads_meter_t1["kwh_total"],
            end_kwh=non_essential_loads_meter_t2["kwh_total"],
        )
        grid_import = PPAOnGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Grid Energy",
            start_kwh=grid_meter_t1["kwh_import"],
            end_kwh=grid_meter_t2["kwh_import"],
        )
        grid_export = PPAOnGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Fed to Grid",
            start_kwh=grid_meter_t1["kwh_export"],
            end_kwh=grid_meter_t2["kwh_export"],
        )

        energy_data = PPAOnGridWithBatteryEnergyData(
            essential=essesntial,
            non_essential=non_essential,
            grid_import=grid_import,
            grid_export=grid_export,
        )

        return cls(
            energy_data=energy_data,
            extracted_meters_t1=extracted_meters_t1,
            extracted_meters_t2=extracted_meters_t2,
            start_reading=start_reading,
            end_reading=end_reading,
        )
