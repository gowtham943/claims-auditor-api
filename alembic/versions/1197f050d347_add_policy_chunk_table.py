"""add policy chunk table

Revision ID: 1197f050d347
Revises: d06295830475
Create Date: 2026-07-05 00:36:40.424438

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '1197f050d347'
down_revision: Union[str, Sequence[str], None] = 'd06295830475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _convert_enum_column_to_varchar(
    table_name: str,
    column_name: str,
    varchar_length: int,
    default_value: str,
    enum_type_name: str,
) -> None:
    """
    Convert a legacy PostgreSQL enum column to VARCHAR.
    Drops role/status check constraints first so PostgreSQL does not compare
    varchar literals against the old enum type during ALTER COLUMN.
    """
    op.execute(
        f"""
        DO $$
        DECLARE
            constraint_record record;
        BEGIN
            FOR constraint_record IN
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = '{table_name}'::regclass
                  AND contype = 'c'
                  AND pg_get_constraintdef(oid) ILIKE '%{column_name}%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE {table_name} DROP CONSTRAINT %I',
                    constraint_record.conname
                );
            END LOOP;
        END $$;
        """
    )
    op.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP DEFAULT"
    )
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} TYPE VARCHAR({varchar_length})
        USING {column_name}::text
        """
    )
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN {column_name} SET DEFAULT '{default_value}'
        """
    )
    op.execute(f"DROP TYPE IF EXISTS {enum_type_name}")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table(
        'policy_chunks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('policy_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_text', sa.String(), nullable=False),
        sa.Column('heading_context', sa.String(), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=3072), nullable=False),
        sa.ForeignKeyConstraint(['policy_id'], ['policy_rulebooks.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # No-op when the initial migration already created VARCHAR columns.
    bind = op.get_bind()
    role_column_type = bind.execute(
        sa.text(
            """
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'role'
            """
        )
    ).one()

    if role_column_type.udt_name == 'systemrole':
        _convert_enum_column_to_varchar(
            table_name='users',
            column_name='role',
            varchar_length=50,
            default_value='AUDITOR',
            enum_type_name='systemrole',
        )

    status_column_type = bind.execute(
        sa.text(
            """
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'claim_submissions' AND column_name = 'status'
            """
        )
    ).one()

    if status_column_type.udt_name == 'submissionstatus':
        _convert_enum_column_to_varchar(
            table_name='claim_submissions',
            column_name='status',
            varchar_length=100,
            default_value='PENDING',
            enum_type_name='submissionstatus',
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('policy_chunks')
