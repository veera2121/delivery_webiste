# utils/timezone.py
from datetime import timezone
import pytz

IST = pytz.timezone("Asia/Kolkata")

def to_ist(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)
