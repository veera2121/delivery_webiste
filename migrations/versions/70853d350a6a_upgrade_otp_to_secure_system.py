"""upgrade otp to secure system

Revision ID: 70853d350a6a
Revises: d6c09cd3ecef
Create Date: 2025-12-27 12:04:47.460854

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70853d350a6a'
down_revision = 'd6c09cd3ecef'
branch_labels = None
depends_on = None


def upgrade():
    # Drop old insecure OTP table
    op.drop_table('otp')

    # Create new secure OTP table
    op.create_table(
        'otp',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mobile', sa.String(length=15), nullable=False),
        sa.Column('otp_hash', sa.String(length=255), nullable=False),
        sa.Column('purpose', sa.String(length=30), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('attempts', sa.Integer(), default=0),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_index('ix_otp_mobile', 'otp', ['mobile'])


    # ### end Alembic commands ###


def downgrade():
    op.drop_table('otp')

    # ### end Alembic commands ###
