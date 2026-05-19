"""extend_registration

Revision ID: 62c93c91bce3
Revises: bbbf3ef366b3
Create Date: 2026-05-20 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "62c93c91bce3"
down_revision = "bbbf3ef366b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=60), nullable=True),
    )
    op.execute(
        sa.text("UPDATE users SET display_name = name WHERE display_name IS NULL")
    )
    op.alter_column(
        "users",
        "display_name",
        existing_type=sa.String(length=60),
        nullable=False,
    )

    op.add_column(
        "users",
        sa.Column(
            "default_currency",
            sa.String(length=3),
            nullable=False,
            server_default="INR",
        ),
    )

    op.add_column(
        "users",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE users SET terms_accepted_at = NOW() WHERE terms_accepted_at IS NULL"
        )
    )
    op.alter_column(
        "users",
        "terms_accepted_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade():
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "default_currency")
    op.drop_column("users", "display_name")
