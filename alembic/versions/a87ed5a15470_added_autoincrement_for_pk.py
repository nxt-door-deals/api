"""Added autoincrement for pk

Revision ID: a87ed5a15470
Revises:
Create Date: 2020-08-26 14:40:19.031955

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "a87ed5a15470"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(
        op.f("ix_apartments_name"), "apartments", ["name"], unique=False
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_apartments_name"), table_name="apartments")
    # ### end Alembic commands ###