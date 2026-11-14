from two_apis_app import app
from models import CODCollectionAudit, CODHandoverBatchItem, Order

with app.app_context():
    print("=== COD AUDIT TABLE ===")
    print("Columns:", list(CODCollectionAudit.__table__.columns.keys()))

    for row in CODCollectionAudit.query.order_by(
        CODCollectionAudit.id.desc()
    ).limit(10).all():
        print({
            c.name: str(getattr(row, c.name))
            for c in CODCollectionAudit.__table__.columns
        })

    print("\n=== ORDERS INCLUDED IN BATCH #1 ===")
    print("Order columns:", list(Order.__table__.columns.keys()))

    for item in CODHandoverBatchItem.query.filter_by(batch_id=1).all():
        order = db.session.get(Order, item.order_id) if False else None
        print("Batch item:", {
            c.name: str(getattr(item, c.name))
            for c in CODHandoverBatchItem.__table__.columns
        })
