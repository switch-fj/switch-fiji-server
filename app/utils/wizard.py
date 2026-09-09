from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum
from app.modules.contracts.wizard.base import BaseContractWizard
from app.modules.contracts.wizard.ppa_off_grid import PPAOffGridContractWizard
from app.modules.contracts.wizard.ppa_on_grid_no_battery import (
    PPAOnGridNoBatteryContractWizard,
)
from app.modules.contracts.wizard.ppa_on_grid_with_battery import (
    PPAOnGridWithBatteryContractWizard,
)
from app.modules.contracts.wizard.schema import (
    OnGridNoBatteryEnergyMix,
    OnGridWithBatteryEnergyMix,
    PPAOffGridEnergyMix,
)


def get_wizard_class_for_contract(
    contract: Contract,
) -> type[BaseContractWizard] | None:
    contract_type = contract.contract_type
    system_mode = contract.system_mode
    with_battery = contract.details.with_battery

    if contract_type == ContractTypeEnum.PPA and system_mode == ContractSystemModeEnum.OFF_GRID:
        return PPAOffGridContractWizard

    if contract_type == ContractTypeEnum.PPA and system_mode == ContractSystemModeEnum.ON_GRID:
        if with_battery == "yes":
            return PPAOnGridWithBatteryContractWizard
        if with_battery == "no":
            return PPAOnGridNoBatteryContractWizard
        raise ValueError(f"Unknown with_battery value: {with_battery!r} for contract {contract.uid}")

    if contract_type == ContractTypeEnum.LEASE:
        return None

    raise ValueError(f"No wizard for contract_type={contract_type}, system_mode={system_mode}")


def extract_production_kwh(energy_mix):
    if isinstance(energy_mix, PPAOffGridEnergyMix):
        return max(0.0, energy_mix.load - energy_mix.backup_gen)
    if isinstance(energy_mix, (OnGridWithBatteryEnergyMix, OnGridNoBatteryEnergyMix)):
        return max(0.0, energy_mix.solar)
    return None


def extract_total_consumption_kwh(energy_mix):
    if isinstance(energy_mix, PPAOffGridEnergyMix):
        return energy_mix.load
    if isinstance(energy_mix, OnGridWithBatteryEnergyMix):
        return energy_mix.solar + energy_mix.generator + energy_mix.grid
    if isinstance(energy_mix, OnGridNoBatteryEnergyMix):
        return energy_mix.solar + energy_mix.grid
    return None
