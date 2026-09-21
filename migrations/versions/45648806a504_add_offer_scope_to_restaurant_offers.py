"""add offer scope to restaurant offers

Revision ID: 45648806a504
Revises: 62f6f6c200d1
Create Date: 2026-09-22 01:49:34.766665

"""
from alembic import op
import sqlalchemy as sa


revision = '45648806a504'
down_revision = '62f6f6c200d1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('restaurant_offer', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('offer_scope', sa.String(length=20), nullable=False)
        )


def downgrade():
    with op.batch_alter_table('restaurant_offer', schema=None) as batch_op:
        batch_op.drop_column('offer_scope')