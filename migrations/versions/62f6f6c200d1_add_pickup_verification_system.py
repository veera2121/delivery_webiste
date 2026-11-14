"""add pickup verification system

Revision ID: 62f6f6c200d1
Revises: fd48ec1ce09b
Create Date: 2026-09-07 00:19:08.362997

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '62f6f6c200d1'
down_revision = 'fd48ec1ce09b'
branch_labels = None
depends_on = None


def upgrade():

    # =========================================================
    # RESTAURANT PICKUP QR
    # =========================================================

    op.create_table(
        'restaurant_pickup_qr',

        sa.Column(
            'id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'restaurant_id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'qr_token',
            sa.String(length=255),
            nullable=False
        ),

        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False
        ),

        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.ForeignKeyConstraint(
            ['restaurant_id'],
            ['restaurant.id']
        ),

        sa.PrimaryKeyConstraint('id'),

        sa.UniqueConstraint(
            'restaurant_id'
        )
    )

    with op.batch_alter_table(
        'restaurant_pickup_qr',
        schema=None
    ) as batch_op:

        batch_op.create_index(
            batch_op.f(
                'ix_restaurant_pickup_qr_qr_token'
            ),
            ['qr_token'],
            unique=True
        )


    # =========================================================
    # ORDER PICKUP VERIFICATION
    # =========================================================

    op.create_table(
        'order_pickup_verification',

        sa.Column(
            'id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'order_id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'restaurant_id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'delivery_person_id',
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            'status',
            sa.String(length=30),
            nullable=False
        ),

        sa.Column(
            'qr_scanned_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'verification_token',
            sa.String(length=255),
            nullable=True
        ),

        sa.Column(
            'token_expires_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'restaurant_confirmed_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'restaurant_confirmed_by',
            sa.Integer(),
            nullable=True
        ),

        sa.Column(
            'pickup_verified_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=True
        ),

        sa.ForeignKeyConstraint(
            ['delivery_person_id'],
            ['delivery_person.id']
        ),

        sa.ForeignKeyConstraint(
            ['order_id'],
            ['order.id']
        ),

        sa.ForeignKeyConstraint(
            ['restaurant_confirmed_by'],
            ['restaurant_user.id']
        ),

        sa.ForeignKeyConstraint(
            ['restaurant_id'],
            ['restaurant.id']
        ),

        sa.PrimaryKeyConstraint('id'),

        sa.UniqueConstraint(
            'order_id'
        ),

        sa.UniqueConstraint(
            'verification_token'
        )
    )


    # =========================================================
    # ADD PICKUP FIELDS TO ORDER
    # =========================================================

    with op.batch_alter_table(
        'order',
        schema=None
    ) as batch_op:

        # -----------------------------------------------------
        # IMPORTANT:
        # Existing production orders need a value.
        # -----------------------------------------------------

        batch_op.add_column(
            sa.Column(
                'pickup_status',
                sa.String(length=30),
                nullable=False,
                server_default='waiting'
            )
        )

        batch_op.add_column(
            sa.Column(
                'pickup_verification_started_at',
                sa.DateTime(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                'pickup_qr_scanned_at',
                sa.DateTime(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                'pickup_verified_at',
                sa.DateTime(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                'pickup_restaurant_confirmed_at',
                sa.DateTime(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                'pickup_verified_by',
                sa.Integer(),
                nullable=True
            )
        )

        # -----------------------------------------------------
        # FOREIGN KEY
        # -----------------------------------------------------

        batch_op.create_foreign_key(
            None,
            'restaurant_user',
            ['pickup_verified_by'],
            ['id']
        )

        # -----------------------------------------------------
        # Remove temporary database default
        #
        # Existing production orders have already received
        # "waiting".
        #
        # Your SQLAlchemy model still has:
        # default="waiting"
        # -----------------------------------------------------

        batch_op.alter_column(
            'pickup_status',
            server_default=None
        )


def downgrade():

    # =========================================================
    # REMOVE ORDER PICKUP FIELDS
    # =========================================================

    with op.batch_alter_table(
        'order',
        schema=None
    ) as batch_op:

        batch_op.drop_constraint(
            None,
            type_='foreignkey'
        )

        batch_op.drop_column(
            'pickup_verified_by'
        )

        batch_op.drop_column(
            'pickup_restaurant_confirmed_at'
        )

        batch_op.drop_column(
            'pickup_verified_at'
        )

        batch_op.drop_column(
            'pickup_qr_scanned_at'
        )

        batch_op.drop_column(
            'pickup_verification_started_at'
        )

        batch_op.drop_column(
            'pickup_status'
        )


    # =========================================================
    # REMOVE ORDER PICKUP VERIFICATION
    # =========================================================

    op.drop_table(
        'order_pickup_verification'
    )


    # =========================================================
    # REMOVE RESTAURANT PICKUP QR
    # =========================================================

    with op.batch_alter_table(
        'restaurant_pickup_qr',
        schema=None
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f(
                'ix_restaurant_pickup_qr_qr_token'
            )
        )

    op.drop_table(
        'restaurant_pickup_qr'
    )