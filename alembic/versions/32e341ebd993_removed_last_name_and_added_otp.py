"""Removed last_name and added otp

Revision ID: 32e341ebd993
Revises: caa15dfcd4b0
Create Date: 2020-09-28 14:42:37.957074

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "32e341ebd993"
down_revision = "caa15dfcd4b0"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users", sa.Column("name", sa.String(length=100), nullable=False)
    )
    op.add_column("users", sa.Column("otp", sa.Integer(), nullable=True))
    op.drop_column("users", "first_name")
    op.drop_column("users", "last_name")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column(
            "last_name",
            sa.VARCHAR(length=50),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "first_name",
            sa.VARCHAR(length=50),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.drop_column("users", "otp")
    op.drop_column("users", "name")
    # ### end Alembic commands ###
