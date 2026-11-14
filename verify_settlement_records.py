from two_apis_app import app
from models import RestaurantSettlement, SettlementLine, SettlementPayout, CODCollection

with app.app_context():
    print("Settlement records:", RestaurantSettlement.query.count())
    print("Settlement lines:", SettlementLine.query.count())
    print("Payout records:", SettlementPayout.query.count())
    print("COD collection records:", CODCollection.query.count())
