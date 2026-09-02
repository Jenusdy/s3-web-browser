import os


class Config:  # noqa: D101
    SECRET_KEY = os.getenv("SECRET_KEY", "your_default_secret_key")  # Replace with a secure key in production
    DEBUG = os.getenv("DEBUG", "False")
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///connections.db")

    PAGE_ITEMS = int(os.getenv("PAGE_ITEMS", "300"))
