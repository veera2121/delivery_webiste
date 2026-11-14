"""update homepage ranking location and add sponsored banners

Revision ID: 713bcc257f4f
Revises: 25f5230cdea1
Create Date: 2026-10-02 23:48:38.042499
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "713bcc257f4f"
down_revision = "25f5230cdea1"
branch_labels = None
depends_on = None


def upgrade():

    bind = op.get_bind()
    inspector = inspect(bind)

    table_name = "restaurant_homepage_ranking"

    # =========================================================
    # EXISTING COLUMNS
    # =========================================================

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    # =========================================================
    # FOREIGN KEYS
    # =========================================================

    foreign_keys = inspector.get_foreign_keys(table_name)

    old_location_fk = None
    new_location_fk = None

    for fk in foreign_keys:
        referred_table = fk.get("referred_table")

        if referred_table == "location":
            old_location_fk = fk["name"]

        elif referred_table == "delivery_location_settings":
            new_location_fk = fk["name"]

    # Remove old location FK if it still exists
    if old_location_fk:
        op.drop_constraint(
            old_location_fk,
            table_name,
            type_="foreignkey"
        )

    # Create new location FK only if it doesn't already exist
    if not new_location_fk:
        op.create_foreign_key(
            "fk_homepage_ranking_delivery_location",
            table_name,
            "delivery_location_settings",
            ["location_id"],
            ["id"]
        )

    # =========================================================
    # SPONSORED ENABLED
    # =========================================================

    if "sponsored_enabled" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false()
            )
        )

    # =========================================================
    # SPONSORED POSITION
    # =========================================================

    if "sponsored_position" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_position",
                sa.Integer(),
                nullable=False,
                server_default="999"
            )
        )

    # =========================================================
    # SPONSORED BANNER URL
    # =========================================================

    if "sponsored_banner_url" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_banner_url",
                sa.Text(),
                nullable=True
            )
        )

    # =========================================================
    # SPONSORED TITLE
    # =========================================================

    if "sponsored_title" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_title",
                sa.String(200),
                nullable=True
            )
        )

    # =========================================================
    # SPONSORED SUBTITLE
    # =========================================================

    if "sponsored_subtitle" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_subtitle",
                sa.String(300),
                nullable=True
            )
        )

    # =========================================================
    # START DATE
    # =========================================================

    if "sponsored_start_at" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_start_at",
                sa.DateTime(),
                nullable=True
            )
        )

    # =========================================================
    # END DATE
    # =========================================================

    if "sponsored_end_at" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_end_at",
                sa.DateTime(),
                nullable=True
            )
        )

    # =========================================================
    # PAYMENT STATUS
    # =========================================================

    if "sponsored_payment_status" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_payment_status",
                sa.String(30),
                nullable=False,
                server_default="pending"
            )
        )

    # =========================================================
    # IMPRESSIONS
    # =========================================================

    if "sponsored_impressions" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_impressions",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )

    # =========================================================
    # CLICKS
    # =========================================================

    if "sponsored_clicks" not in existing_columns:
        op.add_column(
            table_name,
            sa.Column(
                "sponsored_clicks",
                sa.Integer(),
                nullable=False,
                server_default="0"
            )
        )


def downgrade():

    bind = op.get_bind()
    inspector = inspect(bind)

    table_name = "restaurant_homepage_ranking"

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    # =========================================================
    # REMOVE SPONSORED COLUMNS
    # =========================================================

    columns_to_remove = [
        "sponsored_clicks",
        "sponsored_impressions",
        "sponsored_payment_status",
        "sponsored_end_at",
        "sponsored_start_at",
        "sponsored_subtitle",
        "sponsored_title",
        "sponsored_banner_url",
        "sponsored_position",
        "sponsored_enabled",
    ]

    for column_name in columns_to_remove:
        if column_name in existing_columns:
            op.drop_column(
                table_name,
                column_name
            )

    # =========================================================
    # FOREIGN KEY
    # =========================================================

    foreign_keys = inspector.get_foreign_keys(table_name)

    current_location_fk = None

    for fk in foreign_keys:
        if fk.get("referred_table") == "delivery_location_settings":
            current_location_fk = fk["name"]
            break

    if current_location_fk:
        op.drop_constraint(
            current_location_fk,
            table_name,
            type_="foreignkey"
        )

    # Restore old FK
    op.create_foreign_key(
        "restaurant_homepage_ranking_location_id_fkey",
        table_name,
        "location",
        ["location_id"],
        ["id"]
    )