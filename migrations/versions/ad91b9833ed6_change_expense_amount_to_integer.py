"""change expense amount to integer

Revision ID: ad91b9833ed6
Revises: 52fb15060eb0
Create Date: 2026-06-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ad91b9833ed6"
down_revision = "52fb15060eb0"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "expenses",
        "amount",
        type_=sa.Integer(),
        existing_type=sa.Numeric(precision=10, scale=2),
        postgresql_using="round(amount)::integer",
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "expenses",
        "amount",
        type_=sa.Numeric(precision=10, scale=2),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
