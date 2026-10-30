from datetime import datetime

from ..extensions import db


class InquiryStatus:
    NEW = "new"
    REPLIED = "replied"
    ARCHIVED = "archived"

    ALL = (NEW, REPLIED, ARCHIVED)
    LABELS_HE = {NEW: "חדשה", REPLIED: "נענתה", ARCHIVED: "בארכיון"}


class Inquiry(db.Model):
    """A message sent through the contact form."""

    __tablename__ = "inquiries"
    __table_args__ = (
        db.CheckConstraint("status IN ('new', 'replied', 'archived')", name="ck_inquiry_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), nullable=False)
    company = db.Column(db.String(120))
    service = db.Column(db.String(120))     # the service title as chosen, kept even if the service is renamed
    message = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(2), nullable=False, default="en")
    status = db.Column(db.String(10), nullable=False, default=InquiryStatus.NEW, index=True)
    notified = db.Column(db.Boolean, nullable=False, default=False)   # e-mail notification delivered
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    @property
    def status_label(self) -> str:
        return InquiryStatus.LABELS_HE.get(self.status, self.status)
