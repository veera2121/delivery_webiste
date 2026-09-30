import time

from datetime import datetime

from app import app
from dispatch_service import cleanup_all_expired_assignments


while True:

    try:

        with app.app_context():

            cleanup_all_expired_assignments()

    except Exception as e:

        print(
            "❌ ASSIGNMENT EXPIRY WORKER ERROR:",
            e
        )

    time.sleep(5)