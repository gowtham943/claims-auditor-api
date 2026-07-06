import uuid
from typing import TYPE_CHECKING, List

from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column
from sqlalchemy.types import Enum as SAEnum

from enums.system_role import SystemRole

if TYPE_CHECKING:
    from models.claim_submission import ClaimSubmission
    from models.policy_rule_book import PolicyRulebook


class User(SQLModel, table=True):
    __tablename__: str = "users"
    __table_args__ = {"extend_existing": True}

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    username: str = Field(
        max_length=255,
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: str = Field(
        max_length=255,
        nullable=False,
    )
    role: SystemRole = Field(
        sa_column=Column(SAEnum(SystemRole, native_enum=False), nullable=False)
    )

    policies: List["PolicyRulebook"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    claims: List["ClaimSubmission"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
