"""support multiple rider settlement batches

Revision ID: a7b0da5fdb6e
Revises: 3dc179019201
Create Date: 2026-08-28 22:42:05.650268

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b0da5fdb6e'
down_revision = '3dc179019201'
branch_labels = None
depends_on = None


def upgrade():

    # ==========================================================
    # STEP 1:
    # Add batch_no as nullable first
    # Existing settlement rows would otherwise fail
    # because they don't have a batch number yet.
    # ==========================================================

    with op.batch_alter_table(
        'rider_settlements',
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                'batch_no',
                sa.Integer(),
                nullable=True
            )
        )

    # ==========================================================
    # STEP 2:
    # Existing settlements become Batch 1
    # ==========================================================

    op.execute(
        """
        UPDATE rider_settlements
        SET batch_no = 1
        WHERE batch_no IS NULL
        """
    )

    # ==========================================================
    # STEP 3:
    # Make batch_no required now that old rows are populated
    # ==========================================================

    with op.batch_alter_table(
        'rider_settlements',
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            'batch_no',
            existing_type=sa.Integer(),
            nullable=False
        )

        # Remove old rule:
        # only one settlement per rider/day
        batch_op.drop_constraint(
            'uq_rider_settlement_day',
            type_='unique'
        )

        # New rule:
        # multiple settlements per day,
        # but each batch number must be unique
        batch_op.create_unique_constraint(
            'uq_rider_settlement_batch',
            [
                'rider_id',
                'settlement_date',
                'batch_no'
            ]
        )


def downgrade():

    # ==========================================================
    # IMPORTANT:
    # Downgrade only works safely if there is only
    # one settlement per rider/day.
    # ==========================================================

    with op.batch_alter_table(
        'rider_settlements',
        schema=None
    ) as batch_op:

        batch_op.drop_constraint(
            'uq_rider_settlement_batch',
            type_='unique'
        )

        batch_op.create_unique_constraint(
            'uq_rider_settlement_day',
            [
                'rider_id',
                'settlement_date'
            ]
        )

        batch_op.drop_column(
            'batch_no'
        )