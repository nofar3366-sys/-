"""Flask extensions, instantiated here to avoid circular imports."""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "admin.login"
login_manager.login_message = "יש להתחבר כדי לגשת לאזור הניהול"
