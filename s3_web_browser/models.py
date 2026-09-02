from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from botocore.client import Config

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class Connection(db.Model):
    __tablename__ = 'connections'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    endpoint_url: Mapped[str | None] = mapped_column(default=None)
    access_key_id: Mapped[str | None] = mapped_column(default=None)
    secret_access_key: Mapped[str | None] = mapped_column(default=None)
    region: Mapped[str] = mapped_column(default="eu-central-1")
    default_bucket: Mapped[str | None] = mapped_column(default=None)

    def to_boto3_kwargs(self) -> dict:
        kwargs = {
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "region_name": self.region,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs
