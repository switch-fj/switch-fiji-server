from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractSystemModeEnum, ContractTypeEnum


def is_lease(contract: Contract) -> bool:
    return contract.contract_type == ContractTypeEnum.LEASE


def is_ppa(contract: Contract) -> bool:
    return contract.contract_type == ContractTypeEnum.PPA


def is_ppa_off_grid(contract: Contract) -> bool:
    return is_ppa(contract) and contract.system_mode == ContractSystemModeEnum.OFF_GRID


def is_ppa_on_grid_with_battery(contract: Contract) -> bool:
    return (
        is_ppa(contract)
        and contract.system_mode == ContractSystemModeEnum.ON_GRID
        and contract.details.with_battery == "yes"
    )


def is_ppa_on_grid_no_battery(
    contract: Contract,
) -> bool:
    return (
        is_ppa(contract)
        and contract.system_mode == ContractSystemModeEnum.ON_GRID
        and contract.details.with_battery == "no"
    )
