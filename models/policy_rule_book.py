import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

from enums.insurance_plan import Geography

if TYPE_CHECKING:
    from models.claim_submission import ClaimSubmission
    from models.policy_chunks import PolicyChunk
    from models.user import User


class PolicyRulebook(SQLModel, table=True):
    __tablename__: str = "policy_rulebooks"
    __table_args__ = {"extend_existing": True}

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    plan_name: str = Field(
        max_length=255,
        nullable=False,
    )
    plan_type: str = Field(
        max_length=50,
        nullable=False,
    )
    geography: str = Field(
        max_length=20,
        nullable=False,
        default=Geography.WESTERN.value,
    )
    source_url: Optional[str] = Field(
        default=None,
        max_length=512,
        nullable=True,
    )
    raw_markdown_layout: str = Field(
        nullable=False,
    )

    owner: Optional["User"] = Relationship(back_populates="policies")
    submissions: List["ClaimSubmission"] = Relationship(
        back_populates="policy",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    chunks: List["PolicyChunk"] = Relationship(
        back_populates="policy",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
