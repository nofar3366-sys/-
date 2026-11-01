"""Project pricing (admin only). The calculator itself runs in the browser (static/js/pricing.js);
the server stores each quote's inputs, the settings it was priced with, and the resulting total."""
import json
from datetime import datetime

from ..extensions import db


class QuoteStatus:
    DRAFT = "draft"
    SENT = "sent"
    APPROVED = "approved"
    DECLINED = "declined"

    ALL = (DRAFT, SENT, APPROVED, DECLINED)
    LABELS_HE = {DRAFT: "טיוטה", SENT: "נשלחה", APPROVED: "אושרה", DECLINED: "לא אושרה"}


class JsonColumnMixin:
    """`data` holds a JSON object as text (portable across SQLite / PostgreSQL)."""

    @property
    def payload(self) -> dict:
        try:
            value = json.loads(self.data or "{}")
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    @payload.setter
    def payload(self, value: dict) -> None:
        self.data = json.dumps(value, ensure_ascii=False)


class PriceQuote(JsonColumnMixin, db.Model):
    __tablename__ = "price_quotes"
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'sent', 'approved', 'declined')", name="ck_quote_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    client = db.Column(db.String(120))
    name = db.Column(db.String(160))
    status = db.Column(db.String(10), nullable=False, default=QuoteStatus.DRAFT, index=True)
    total = db.Column(db.Integer, nullable=False, default=0)     # before VAT, as shown in the quote
    data = db.Column(db.Text, nullable=False, default="{}")      # {"project": {...}, "settings": {...}}
    inquiry_id = db.Column(db.Integer, db.ForeignKey("inquiries.id", ondelete="SET NULL"), index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("client_projects.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, index=True)

    inquiry = db.relationship("Inquiry", backref=db.backref("quotes", passive_deletes=True))
    # NB: `client` is already the free-text client name column above; this is the linked Client record
    owner = db.relationship("Client", backref=db.backref("quotes", order_by="PriceQuote.updated_at.desc()"))
    project = db.relationship("ClientProject", backref=db.backref("quotes", order_by="PriceQuote.updated_at.desc()"))

    @property
    def title(self) -> str:
        return " · ".join(p for p in (self.client, self.name) if p) or "הצעה ללא שם"

    @property
    def status_label(self) -> str:
        return QuoteStatus.LABELS_HE.get(self.status, self.status)


class PricingSettings(JsonColumnMixin, db.Model):
    """Default rates for new quotes (one row). Each quote keeps its own copy, so changing
    a rate later never changes the price of a quote that was already sent."""

    __tablename__ = "pricing_settings"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False, default="{}")

    @classmethod
    def current(cls) -> "PricingSettings":
        row = db.session.get(cls, 1)
        if row is None:
            row = cls(id=1)
            db.session.add(row)
        return row
