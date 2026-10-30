import io
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config  # noqa: E402
from nofai import create_app  # noqa: E402
from nofai.extensions import db  # noqa: E402
from nofai.models import Admin, Category, Project, ProjectImage, Service  # noqa: E402


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


@pytest.fixture(autouse=True)
def _reset_throttle():
    from nofai.security import login_throttle
    login_throttle._failures.clear()
    yield


@pytest.fixture
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_DIR = str(tmp_path / "uploads")
    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        admin = Admin(username="nofar")
        admin.set_password("secret-123")
        db.session.add_all([admin, Category(slug="product-campaigns", name_he="קמפייני מוצר", name_en="Product Campaigns"),
                            Service(title_he="קמפיינים", title_en="Campaigns")])
        db.session.commit()
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(client):
    client.post("/admin/login", data={"username": "nofar", "password": "secret-123"})
    return client


def image_bytes(size=(800, 1000), fmt="PNG", color=(214, 199, 176)) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    buf.seek(0)
    return buf


def make_project(title="Summer", featured=True, published=True, images=1, **kw):
    """A project with fake image rows (no files needed for page rendering)."""
    project = Project(slug=kw.pop("slug", title.lower()), title_en=title, title_he=kw.pop("title_he", title),
                      is_featured=featured, is_published=published, **kw)
    for i in range(images):
        project.images.append(ProjectImage(filename=f"{title}-{i}.webp", width=800, height=1000, sort_order=i, is_cover=i == 0))
    db.session.add(project)
    db.session.commit()
    return project
