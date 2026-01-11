from datetime import timezone
import pytz

IST = pytz.timezone("Asia/Kolkata")

def utc_to_ist(utc_dt):
    if utc_dt is None:
        return None
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(IST)
