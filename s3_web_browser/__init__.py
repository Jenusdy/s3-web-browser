import os

from flask import Flask

from s3_web_browser.models import db
from s3_web_browser.routes import register_routes


def create_app(config_class: str = "config.Config") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Ensure the instance folder exists for fresh installs
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)
    with app.app_context():
        db.create_all()

    register_routes(app)

    return app
