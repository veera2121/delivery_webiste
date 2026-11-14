from two_apis_app import app
from models import CODHandoverBatch, CODHandoverBatchItem, CODCollection

def show_records(model, title, limit=10):
    print("\n===", title, "===")
    print("Columns:", list(model.__table__.columns.keys()))

    query = model.query
    if "id" in model.__table__.columns:
        query = query.order_by(model.id.desc())

    for obj in query.limit(limit).all():
        print({
            column.name: str(getattr(obj, column.name))
            for column in model.__table__.columns
        })

with app.app_context():
    show_records(CODHandoverBatch, "LATEST COD HANDOVER BATCHES")
    show_records(CODHandoverBatchItem, "LATEST COD HANDOVER ITEMS")
    show_records(CODCollection, "LATEST COD COLLECTIONS")
