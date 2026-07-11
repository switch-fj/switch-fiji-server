from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from app.modules.pv_degradation.schema import PvDegradationSchedule
from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class PvDegradation(MyAbstractSQLModel, table=True):
    __tablename__ = "pv_degradation"

    site_uid: UUID = Field(foreign_key="sites.uid")
    user_uid: UUID = Field(foreign_key="users.uid")
    degradation: str = Field(description="JSON-serialized PvDegradationSchedule")

    site: "Site" = Relationship(back_populates="pv_degradation")
    user: "User" = Relationship(back_populates="")

    @property
    def degradation_schedule(self) -> PvDegradationSchedule:
        return PvDegradationSchedule.from_json(self.degradation)

    @degradation_schedule.setter
    def degradation_schedule(self, value: PvDegradationSchedule) -> None:
        self.degradation = value.to_json()
