from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import Field, Relationship

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class StringWiring(MyAbstractSQLModel, table=True):
    __tablename__ = "string_wiring"

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True, unique=True)
    user_uid: UUID = Field(foreign_key="users.uid", nullable=False, index=True)
    string_input: str = Field(description="JSON-serialized StringsInputItemModel")
    wring_schematics: Optional[str] = Field(description="JSON-serialized StringSchematicsModel")
    mppt_fn_table: Optional[str] = Field(description="JSON-serialized StringSchematicsModel")
    expected_mppt_a_table: Optional[str] = Field(description="JSON-serialized StringSchematicsModel")

    # Relationships
    site: "Site" = Relationship(back_populates="string_wiring")
    user: "User" = Relationship(back_populates="string_wiring")
