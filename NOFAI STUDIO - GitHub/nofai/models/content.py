"""Editable site copy and services."""
from ..extensions import db
from .localized import Localized


class Service(Localized, db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title_he = db.Column(db.String(120), nullable=False)
    title_en = db.Column(db.String(120), nullable=False)
    description_he = db.Column(db.Text)
    description_en = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class SiteText(Localized, db.Model):
    """One editable piece of copy, addressed by key (see nofai/site_texts.py)."""

    __tablename__ = "site_texts"

    key = db.Column(db.String(60), primary_key=True)
    value_he = db.Column(db.Text)
    value_en = db.Column(db.Text)
