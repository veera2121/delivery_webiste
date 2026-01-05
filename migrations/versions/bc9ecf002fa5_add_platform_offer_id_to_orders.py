from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'bc9ecf002fa5'
down_revision = 'bf48fe6d8e81'
branch_labels = None
depends_on = None


def upgrade():
    # ✅ SQLite-safe column add (NO FK constraint)
   op.add_column(
    'order',
    sa.Column('platform_offer_id', sa.Integer(), nullable=True)
)



def downgrade():
    op.drop_column('orders', 'platform_offer_id')
