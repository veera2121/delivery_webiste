"""add platform_offer_id to orders

Revision ID: 2316d52327dc
Revises: 9e65ec759ff3
Create Date: 2026-01-05 21:53:26.063184
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2316d52327dc'
down_revision = '9e65ec759ff3'
branch_labels = None
depends_on = None


def upgrade():
    # Use the correct table name "order" (singular)
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform_offer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_order_platform_offer_id',  # always give a name!
            'platform_offer',
            ['platform_offer_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.drop_constraint('fk_order_platform_offer_id', type_='foreignkey')
        batch_op.drop_column('platform_offer_id')
