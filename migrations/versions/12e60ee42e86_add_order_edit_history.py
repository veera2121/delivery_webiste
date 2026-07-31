"""add order edit history

Revision ID: 12e60ee42e86
Revises: c748bb1eeb83
Create Date: 2026-07-30 22:03:24.292125

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "12e60ee42e86"
down_revision = "c748bb1eeb83"
branch_labels = None
depends_on = None


def upgrade():

    # =====================================================
    # CREATE ORDER EDIT HISTORY TABLE
    # =====================================================

    op.create_table(
        "order_edit_history",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "action",
            sa.String(length=100),
            nullable=False
        ),

        sa.Column(
            "old_items",
            sa.Text(),
            nullable=True
        ),

        sa.Column(
            "new_items",
            sa.Text(),
            nullable=True
        ),

        sa.Column(
            "old_items_total",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "new_items_total",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "old_delivery_charge",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "new_delivery_charge",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "old_extra_charge",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "new_extra_charge",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "old_manual_discount",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "new_manual_discount",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "old_final_total",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "new_final_total",
            sa.Float(),
            nullable=True
        ),

        sa.Column(
            "reason",
            sa.String(length=500),
            nullable=True
        ),

        sa.Column(
            "edited_by",
            sa.String(length=100),
            nullable=True
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.ForeignKeyConstraint(
            ["order_id"],
            ["order.id"]
        ),

        sa.PrimaryKeyConstraint("id")
    )

    with op.batch_alter_table(
        "order_edit_history",
        schema=None
    ) as batch_op:

        batch_op.create_index(
            batch_op.f(
                "ix_order_edit_history_order_id"
            ),
            ["order_id"],
            unique=False
        )

    # =====================================================
    # ADD ORDER EDIT COLUMNS
    #
    # server_default is required because old orders already
    # exist in the database.
    # =====================================================

    with op.batch_alter_table(
        "order",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "manual_discount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "extra_charge",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_order_edited",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false")
            )
        )

        batch_op.add_column(
            sa.Column(
                "order_edit_reason",
                sa.String(length=500),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "order_edited_at",
                sa.DateTime(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "order_edited_by",
                sa.String(length=100),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "customer_edit_approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false")
            )
        )

    # =====================================================
    # REMOVE TEMPORARY DATABASE DEFAULTS
    #
    # Existing orders have now received values.
    # New orders will use SQLAlchemy model defaults.
    # =====================================================

    with op.batch_alter_table(
        "order",
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            "manual_discount",
            server_default=None
        )

        batch_op.alter_column(
            "extra_charge",
            server_default=None
        )

        batch_op.alter_column(
            "is_order_edited",
            server_default=None
        )

        batch_op.alter_column(
            "customer_edit_approved",
            server_default=None
        )


def downgrade():

    # =====================================================
    # REMOVE ORDER EDIT COLUMNS
    # =====================================================

    with op.batch_alter_table(
        "order",
        schema=None
    ) as batch_op:

        batch_op.drop_column(
            "customer_edit_approved"
        )

        batch_op.drop_column(
            "order_edited_by"
        )

        batch_op.drop_column(
            "order_edited_at"
        )

        batch_op.drop_column(
            "order_edit_reason"
        )

        batch_op.drop_column(
            "is_order_edited"
        )

        batch_op.drop_column(
            "extra_charge"
        )

        batch_op.drop_column(
            "manual_discount"
        )

    # =====================================================
    # REMOVE HISTORY TABLE
    # =====================================================

    with op.batch_alter_table(
        "order_edit_history",
        schema=None
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f(
                "ix_order_edit_history_order_id"
            )
        )

    op.drop_table(
        "order_edit_history"
    )