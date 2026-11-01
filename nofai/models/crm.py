"""Clients (back-office CRM): a lead converted from an inquiry, its notes and its projects.

`ClientProject` is a project done *for a client*. It is deliberately separate from `Project`
(portfolio.py), which is a public portfolio piece shown on the website."""
from datetime import datetime

from ..extensions import db


class ClientStatus:
    ACTIVE = "active"
    WAITING = "waiting"
    INACTIVE = "inactive"

    ALL = (ACTIVE, WAITING, INACTIVE)
    LABELS_HE = {ACTIVE: "פעיל", WAITING: "בהמתנה", INACTIVE: "לא פעיל"}


class ClientSource:
    SITE = "site"
    REFERRAL = "referral"
    INSTAGRAM = "instagram"
    OTHER = "other"

    ALL = (SITE, REFERRAL, INSTAGRAM, OTHER)
    LABELS_HE = {SITE: "פנייה באתר", REFERRAL: "המלצה", INSTAGRAM: "אינסטגרם", OTHER: "אחר"}


class ProjectStatus:
    PROPOSAL = "proposal"
    IN_PROGRESS = "in_progress"
    AWAITING = "awaiting_approval"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    ALL = (PROPOSAL, IN_PROGRESS, AWAITING, DELIVERED, CANCELLED)
    LABELS_HE = {PROPOSAL: "הצעה", IN_PROGRESS: "בעבודה", AWAITING: "ממתין לאישור",
                 DELIVERED: "נמסר", CANCELLED: "בוטל"}


class NoteKind:
    NOTE = "note"
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    SYSTEM = "system"      # written by the system (conversion etc.); never edited or deleted by hand

    USER_KINDS = (NOTE, CALL, EMAIL, MEETING)
    ALL = USER_KINDS + (SYSTEM,)
    LABELS_HE = {NOTE: "הערה", CALL: "שיחה", EMAIL: "מייל", MEETING: "פגישה", SYSTEM: "מערכת"}


class Client(db.Model):
    """A person/brand we work with. Created by converting an inquiry, or by hand."""

    __tablename__ = "clients"
    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'waiting', 'inactive')", name="ck_client_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(160))
    company = db.Column(db.String(120))
    website = db.Column(db.String(200))                  # the brand's site or Instagram
    language = db.Column(db.String(2), nullable=False, default="he")
    source = db.Column(db.String(12), nullable=False, default=ClientSource.OTHER)
    status = db.Column(db.String(10), nullable=False, default=ClientStatus.ACTIVE, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, index=True)

    projects = db.relationship("ClientProject", back_populates="client", cascade="all, delete-orphan",
                               order_by="ClientProject.created_at.desc()")

    @property
    def display_name(self) -> str:
        return self.company or self.name

    @property
    def status_label(self) -> str:
        return ClientStatus.LABELS_HE.get(self.status, self.status)

    @property
    def source_label(self) -> str:
        return ClientSource.LABELS_HE.get(self.source, self.source)

    def touch(self) -> None:
        """Mark recent activity (the client list is sorted by it)."""
        self.updated_at = datetime.now()


class ClientProject(db.Model):
    """A project done for a client, with its quotes (PriceQuote.project_id)."""

    __tablename__ = "client_projects"
    __table_args__ = (
        db.CheckConstraint("status IN ('proposal', 'in_progress', 'awaiting_approval', 'delivered', 'cancelled')",
                           name="ck_client_project_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    service = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default=ProjectStatus.PROPOSAL, index=True)
    brief = db.Column(db.Text)
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    delivered_date = db.Column(db.Date)
    amount = db.Column(db.Integer)                       # agreed price in ₪ before VAT (usually from the quote)
    links = db.Column(db.Text)                           # one link per line (Drive, Dropbox...)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    client = db.relationship("Client", back_populates="projects")

    @property
    def status_label(self) -> str:
        return ProjectStatus.LABELS_HE.get(self.status, self.status)

    @property
    def link_list(self) -> list[str]:
        return [line.strip() for line in (self.links or "").splitlines() if line.strip()]


class Note(db.Model):
    """A note on an inquiry and/or a client. A note written on an inquiry that is later converted
    keeps its inquiry_id and gains the client_id, so it shows in the client's history."""

    __tablename__ = "notes"
    __table_args__ = (
        db.CheckConstraint("kind IN ('note', 'call', 'email', 'meeting', 'system')", name="ck_note_kind"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False, default=NoteKind.NOTE)
    body = db.Column(db.Text, nullable=False)
    inquiry_id = db.Column(db.Integer, db.ForeignKey("inquiries.id", ondelete="CASCADE"), index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    inquiry = db.relationship("Inquiry", backref=db.backref("notes", order_by="Note.created_at.desc()",
                                                            cascade="all, delete-orphan"))
    client = db.relationship("Client", backref=db.backref("notes", order_by="Note.created_at.desc()"))

    @property
    def kind_label(self) -> str:
        return NoteKind.LABELS_HE.get(self.kind, self.kind)

    @property
    def is_system(self) -> bool:
        return self.kind == NoteKind.SYSTEM
