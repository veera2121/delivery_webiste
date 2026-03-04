from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
from flask_wtf import CSRFProtect

csrf = CSRFProtect()