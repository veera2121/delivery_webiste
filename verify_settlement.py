from two_apis_app import app, db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    print("\n=== SETTLEMENT / COD TABLES IN DATABASE ===")
    for table in tables:
        if "settlement" in table.lower() or "cod_" in table.lower():
            print(table)

    print("\n=== SETTLEMENT / COD TABLES IN SQLALCHEMY METADATA ===")
    for table in db.metadata.tables:
        if "settlement" in table.lower() or "cod_" in table.lower():
            print(table)
