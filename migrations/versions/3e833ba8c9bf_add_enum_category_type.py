from alembic import op
import sqlalchemy as sa

revision = '3e833ba8c9bf'
down_revision = '52e550200f8b'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE restaurant 
        ALTER COLUMN category_type 
        TYPE VARCHAR(20) 
        USING category_type::text
    """)


def downgrade():
    op.execute("""
        ALTER TABLE restaurant 
        ALTER COLUMN category_type 
        TYPE VARCHAR(20)
    """)