import uuid
from typing import TYPE_CHECKING, Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.policy_rule_book import PolicyRulebook


class PolicyChunk(SQLModel, table=True):
    __tablename__ = "policy_chunks"
    __table_args__ = {"extend_existing": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, nullable=False)
    policy_id: uuid.UUID = Field(foreign_key="policy_rulebooks.id", nullable=False, index=True)

    chunk_text: str = Field(nullable=False)
    heading_context: str = Field(
        default="",
        description="Carries parent markdown header contexts for semantic tracking.",
    )

    embedding: Any = Field(sa_column=Column(Vector(3072), nullable=False))

    policy: Optional["PolicyRulebook"] = Relationship(back_populates="chunks")
