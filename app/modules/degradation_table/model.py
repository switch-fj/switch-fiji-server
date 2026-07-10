from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site


class Degradation(MyAbstractSQLModel, table=True):
    __tablename__ = "degradation"

    site_uid: UUID = Field(foreign_key="sites.uid")

    # relationship
    site: "Site" = Relationship(back_populates="degradation")
