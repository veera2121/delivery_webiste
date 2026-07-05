from app import app, sync_all_restaurants

with app.app_context():
    sync_all_restaurants()

print("✅ Menu sync completed")