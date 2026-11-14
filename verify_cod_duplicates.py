from two_apis_app import app, db
from sqlalchemy import inspect, func
from models import CODHandoverBatchItem

with app.app_context():
    inspector = inspect(db.engine)

    print("=== HANDOVER ITEM INDEXES ===")
    for index in inspector.get_indexes("cod_handover_batch_item"):
        print(index)

    print("\n=== DUPLICATE ACTIVE ORDERS ===")
    duplicates = (
        db.session.query(
            CODHandoverBatchItem.order_id,
            func.count(CODHandoverBatchItem.id).label("active_count")
        )
        .filter(CODHandoverBatchItem.released_at.is_(None))
        .group_by(CODHandoverBatchItem.order_id)
        .having(func.count(CODHandoverBatchItem.id) > 1)
        .all()
    )

    print("Duplicates:", duplicates if duplicates else "None")
