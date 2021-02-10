"""Added the Chat table

Revision ID: 604631bd4d57
Revises: 14cf7c5f078d
Create Date: 2021-01-28 15:51:17.576627

"""
import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "604631bd4d57"
down_revision = "14cf7c5f078d"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("chats", sa.Column("ad_id", sa.Integer(), nullable=True))
    op.add_column("chats", sa.Column("buyer_id", sa.Integer(), nullable=True))
    op.add_column(
        "chats", sa.Column("chat_id", sa.String(length=64), nullable=False)
    )
    op.add_column("chats", sa.Column("seller_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "chats", "users", ["seller_id"], ["id"])
    op.create_foreign_key(None, "chats", "ads", ["ad_id"], ["id"])
    op.create_foreign_key(None, "chats", "users", ["buyer_id"], ["id"])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, "chats", type_="foreignkey")
    op.drop_constraint(None, "chats", type_="foreignkey")
    op.drop_constraint(None, "chats", type_="foreignkey")
    op.drop_column("chats", "seller_id")
    op.drop_column("chats", "chat_id")
    op.drop_column("chats", "buyer_id")
    op.drop_column("chats", "ad_id")
    # ### end Alembic commands ###
