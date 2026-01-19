"""add category_type to restaurant

Revision ID: 478fe7a62193
Revises: ecf703c5ce7a
Create Date: 2026-01-17 11:14:29.003360

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '478fe7a62193'
down_revision = 'ecf703c5ce7a'
branch_labels = None
depends_on = None



def upgrade():
    # 1️⃣ Add column as nullable first
    op.add_column(
        'restaurant',
        sa.Column('category_type', sa.String(length=20), nullable=True)
    )

    # 2️⃣ Fill existing rows with default value
    op.execute(
        "UPDATE restaurant SET category_type = 'restaurant' WHERE category_type IS NULL"
    )

    # 3️⃣ Make column NOT NULL
    op.alter_column(
        'restaurant',
        'category_type',
        nullable=False
    )


def downgrade():
    op.drop_column('restaurant', 'category_type')
