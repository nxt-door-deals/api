"""Added the email_verification_timestamp column

Revision ID: c1fce2c60107
Revises: 940cbd446490
Create Date: 2020-10-01 00:20:31.497668

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1fce2c60107"
down_revision = "940cbd446490"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column("email_verification_timestamp", sa.DateTime(), nullable=True),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "email_verification_timestamp")
    # ### end Alembic commands ###
