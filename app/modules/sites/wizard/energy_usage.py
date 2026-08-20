class SiteEnergyUsageWizard:
    def __init__(self, telemetry_readings: list[dict], contract_type: str, system_mode: str):
        self.telmetry_readings = telemetry_readings
        self.contract_type = contract_type
        self.system_mode = system_mode

    def _ppa_off_grid(self):
        pass

    def _ppa_on_grid(self):
        pass

    def _lease(self):
        pass

    @property
    def energy_usage(self):
        pass
