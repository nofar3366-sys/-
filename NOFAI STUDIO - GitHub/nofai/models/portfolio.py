"""Portfolio content: categories, projects (campaigns) and their images."""
from datetime import datetime

from ..extensions import db
from .localized import Localized


class Category(Localized, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    name_he = db.Column(db.String(80), nullable=False)
    name_en = db.Column(db.String(80), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    projects = db.relationship("Project", back_populates="category", lazy="dynamic")


class Project(Localized, db.Model):
    """A campaign / body of work. Shown as one tile in the gallery; the lightbox
    pages through all of its images."""

    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    title_he = db.Column(db.String(160), nullable=False)
    title_en = db.Column(db.String(160), nullable=False)
    client = db.Column(db.String(120))
    year = db.Column(db.Integer)
    description_he = db.Column(db.Text)
    description_en = db.Column(db.Text)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)   # shown on the home page
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="SET NULL"))
    category = db.relationship("Category", back_populates="projects")

    images = db.relationship(
        "ProjectImage", back_populates="project", order_by="ProjectImage.sort_order",
        cascade="all, delete-orphan",
    )

    @property
    def cover(self):
        """The image marked as cover, else the first one, else None."""
        return next((i for i in self.images if i.is_cover), self.images[0] if self.images else None)


class ProjectImage(Localized, db.Model):
    __tablename__ = "project_images"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project = db.relationship("Project", back_populates="images")

    filename = db.Column(db.String(255), nullable=False)   # storage key (see storage.py)
    width = db.Column(db.Integer, nullable=False)          # stored so pages reserve space (no layout jump)
    height = db.Column(db.Integer, nullable=False)
    alt_he = db.Column(db.String(200))
    alt_en = db.Column(db.String(200))
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_cover = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def orientation(self) -> str:
        ratio = self.width / self.height
        return "landscape" if ratio > 1.15 else "portrait" if ratio < 0.87 else "square"
