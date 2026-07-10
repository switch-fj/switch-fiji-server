from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class PanelReference(MyAbstractSQLModel, table=True):
    """
    Panel references for sites. The "Solar Panel KWH" modal writes here
    """

    __tablename__ = "panel_reference"

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True)
    user_uid: UUID = Field(foreign_key="users.uid", nullable=False, index=True)
    panel_type: str = Field(...)
    watt: float = Field(...)
    vmp: float = Field(...)
    voc: float = Field(...)
    imp: float = Field(...)

    # Relationships
    site: "Site" = Relationship(back_populates="panel_refs")
    user: "User" = Relationship(back_populates="panel_refs")
