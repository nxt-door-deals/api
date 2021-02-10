"""Added the active column to the Ad table

Revision ID: 14cf7c5f078d
Revises: bbd61da32aac
Create Date: 2021-01-25 21:48:55.719244

"""
import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "14cf7c5f078d"
down_revision = "bbd61da32aac"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("ads", sa.Column("active", sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("ads", "active")
    # ### end Alembic commands ###
