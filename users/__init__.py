from flask import Flask
from extensions import db

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:9676382650@localhost:5433/testdb"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "your-secret-key"

    # ✅ bind db
    db.init_app(app)

    # ✅ import models AFTER init
    from models import RewardSetting, Restaurant, FoodItem

    # ✅ register blueprints
    from routes.home import home_bp
    app.register_blueprint(home_bp)

    return app
