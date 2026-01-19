import requests
import pandas as pd
from io import StringIO


def get_bakery_items_from_sheet(sheet_url):
    """
    Reads bakery menu from Google Sheet CSV
    """
    if not sheet_url:
        return []

    resp = requests.get(sheet_url, timeout=10)
    df = pd.read_csv(StringIO(resp.text))

    items = []

    for _, row in df.iterrows():
        items.append({
            "name": str(row.get("name", "")).strip(),
            "type": str(row.get("type", "")).strip().lower(),
            "description": str(row.get("description", "")).strip(),
            "flavour": "" if pd.isna(row.get("flavour")) else str(row.get("flavour")),
            "availability": str(row.get("availability", "no")).strip().lower(),
            "image_url": "" if pd.isna(row.get("image_url")) else str(row.get("image_url")),
            "weight_prices": "" if pd.isna(row.get("weight_prices")) else str(row.get("weight_prices")),
            "price": float(row.get("price")) if not pd.isna(row.get("price")) else 0,
            # optional category support
            "category": str(row.get("category", "Cakes")).strip()
        })

    return items
