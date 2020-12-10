"""Added the created_on column in ads

Revision ID: 1a274c4ffaa9
Revises: 10dbcc4e828b
Create Date: 2020-11-18 09:17:53.549876

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1a274c4ffaa9"
down_revision = "10dbcc4e828b"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("ads", sa.Column("created_on", sa.DateTime(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("ads", "created_on")
    # ### end Alembic commands ###