import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel

from enums.submission_status import SubmissionStatus

if TYPE_CHECKING:
    from models.policy_rule_book import PolicyRulebook
    from models.user import User


class ClaimSubmission(SQLModel, table=True):
    __tablename__: str = "claim_submissions"
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
    policy_id: uuid.UUID = Field(
        foreign_key="policy_rulebooks.id",
        ondelete="CASCADE",
        nullable=False,
    )
    patient_name: str = Field(
        max_length=255,
        nullable=False,
    )
    claim_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        nullable=False,
    )
    status: SubmissionStatus = Field(
        sa_column=Column(SAEnum(SubmissionStatus, native_enum=False), nullable=False)
    )


    owner: Optional["User"] = Relationship(back_populates="claims")
    policy: Optional["PolicyRulebook"] = Relationship(
        back_populates="submissions",
    )
