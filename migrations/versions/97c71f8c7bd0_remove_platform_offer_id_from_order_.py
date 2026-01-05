"""Remove platform_offer_id from order table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_platform_offer_id'
down_revision = 'bc9ecf002fa5'  # replace with your latest working head
branch_labels = None
depends_on = None

def upgrade():
    # Remove the column safely
    with op.batch_alter_table('order') as batch_op:
        batch_op.drop_column('platform_offer_id')


def downgrade():
    # Re-add the column if rolling back
    with op.batch_alter_table('order') as batch_op:
        batch_op.add_column(sa.Column('platform_offer_id', sa.Integer(), nullable=True))
