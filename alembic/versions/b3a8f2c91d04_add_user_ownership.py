"""add user ownership to policies and claims

Revision ID: b3a8f2c91d04
Revises: 1197f050d347
Create Date: 2026-07-05 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3a8f2c91d04"
down_revision: Union[str, Sequence[str], None] = "1197f050d347"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("policy_rulebooks", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("claim_submissions", sa.Column("user_id", sa.Uuid(), nullable=True))

    # Assign legacy rows to the earliest registered user when present.
    op.execute(
        """
        UPDATE policy_rulebooks
        SET user_id = (SELECT id FROM users ORDER BY username LIMIT 1)
        WHERE user_id IS NULL
          AND EXISTS (SELECT 1 FROM users)
        """
    )
    op.execute(
        """
        UPDATE claim_submissions cs
        SET user_id = pr.user_id
        FROM policy_rulebooks pr
        WHERE cs.policy_id = pr.id
          AND cs.user_id IS NULL
          AND pr.user_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE claim_submissions
        SET user_id = (SELECT id FROM users ORDER BY username LIMIT 1)
        WHERE user_id IS NULL
          AND EXISTS (SELECT 1 FROM users)
        """
    )

    # Remove orphaned rows that cannot be attributed to an owner.
    op.execute("DELETE FROM claim_submissions WHERE user_id IS NULL")
    op.execute("DELETE FROM policy_chunks WHERE policy_id IN (SELECT id FROM policy_rulebooks WHERE user_id IS NULL)")
    op.execute("DELETE FROM policy_rulebooks WHERE user_id IS NULL")

    op.alter_column("policy_rulebooks", "user_id", nullable=False)
    op.alter_column("claim_submissions", "user_id", nullable=False)

    op.create_foreign_key(
        "fk_policy_rulebooks_user_id_users",
        "policy_rulebooks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_claim_submissions_user_id_users",
        "claim_submissions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_policy_rulebooks_user_id", "policy_rulebooks", ["user_id"])
    op.create_index("ix_claim_submissions_user_id", "claim_submissions", ["user_id"])
    op.create_index("ix_policy_chunks_policy_id", "policy_chunks", ["policy_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_chunks_policy_id", table_name="policy_chunks")
    op.drop_index("ix_claim_submissions_user_id", table_name="claim_submissions")
    op.drop_index("ix_policy_rulebooks_user_id", table_name="policy_rulebooks")
    op.drop_constraint("fk_claim_submissions_user_id_users", "claim_submissions", type_="foreignkey")
    op.drop_constraint("fk_policy_rulebooks_user_id_users", "policy_rulebooks", type_="foreignkey")
    op.drop_column("claim_submissions", "user_id")
    op.drop_column("policy_rulebooks", "user_id")
