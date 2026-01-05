"""Remove self-reference from platform_offer

Revision ID: bf48fe6d8e81
Revises: 2316d52327dc
Create Date: 2026-01-05 22:28:29.572246

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bf48fe6d8e81'
down_revision = '2316d52327dc'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the platform_offer_id column from 'order'
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.drop_column('platform_offer_id')


def downgrade():
    # Re-add the platform_offer_id column with foreign key
    with op.batch_alter_table('order', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform_offer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_order_platform_offer_id',  # explicitly name the constraint
            'platform_offer',
            ['platform_offer_id'],
            ['id']
        )
