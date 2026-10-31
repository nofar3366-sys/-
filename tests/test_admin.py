import os

import pytest

from nofai.extensions import db
from nofai.models import Category, Inquiry, Project, ProjectImage, Service, SiteText

from conftest import image_bytes, make_project


# ---------------------------------------------------------------- access

@pytest.mark.parametrize("url", ["/admin/", "/admin/inquiries", "/admin/projects", "/admin/projects/new",
                                 "/admin/categories", "/admin/services", "/admin/texts", "/admin/account"])
def test_admin_requires_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


@pytest.mark.parametrize("url", ["/admin/", "/admin/inquiries", "/admin/projects", "/admin/projects/new",
                                 "/admin/categories", "/admin/services", "/admin/texts", "/admin/account"])
def test_admin_pages_render(admin_client, url):
    make_project()
    assert admin_client.get(url).status_code == 200


def test_login_lockout(client):
    for _ in range(5):
        client.post("/admin/login", data={"username": "nofar", "password": "wrong"})
    r = client.post("/admin/login", data={"username": "nofar", "password": "secret-123"})
    assert r.status_code == 429


# ---------------------------------------------------------------- projects + uploads

def test_create_project_with_images(admin_client, app):
    r = admin_client.post("/admin/projects/new", data={
        "title_en": "Sun Glasses", "client": "Optica", "year": "2026", "category_id": "1", "is_published": "1",
        "images": [(image_bytes((3000, 2000), "JPEG"), "a.jpg"), (image_bytes(), "b.png")],
    }, content_type="multipart/form-data")
    assert r.status_code == 302
    p = Project.query.one()
    assert (p.slug, p.title_he, p.title_en, p.year) == ("sun-glasses", "Sun Glasses", "Sun Glasses", 2026)
    assert len(p.images) == 2 and p.images[0].is_cover and not p.images[1].is_cover
    first = p.images[0]
    assert max(first.width, first.height) == app.config["IMAGE_MAX_SIDE"]   # resized from 3000px
    assert first.filename.endswith(".webp")
    assert os.path.exists(os.path.join(app.config["UPLOAD_DIR"], first.filename))
    assert admin_client.get(f"/media/{first.filename}").status_code == 200


def test_rejects_non_images(admin_client):
    import io
    admin_client.post("/admin/projects/new", data={
        "title_en": "X", "is_published": "1",
        "images": [(io.BytesIO(b"<?php echo 'hi'; ?>"), "evil.jpg")],
    }, content_type="multipart/form-data", follow_redirects=True)
    assert ProjectImage.query.count() == 0 and Project.query.count() == 1


def test_project_validation(admin_client):
    r = admin_client.post("/admin/projects/new", data={"title_he": "", "title_en": "", "year": "3000", "slug": "Bad Slug!"})
    html = r.get_data(as_text=True)
    assert "יש להזין כותרת" in html and "שנה לא תקינה" in html and "רק אותיות באנגלית" in html
    assert Project.query.count() == 0


def test_slug_is_unique(admin_client):
    make_project("Summer", slug="summer")
    admin_client.post("/admin/projects/new", data={"title_en": "Summer"})
    assert {p.slug for p in Project.query.all()} == {"summer", "summer-2"}


def test_edit_cover_and_alt(admin_client):
    p = make_project("Edit", images=2)
    second = p.images[1]
    admin_client.post(f"/admin/projects/{p.id}", data={
        "title_en": "Edited", "title_he": "נערך", "is_published": "1",
        "cover_id": str(second.id), f"alt_en_{second.id}": "A woman in sunglasses",
    })
    p = db.session.get(Project, p.id)
    assert p.title_he == "נערך" and p.cover.id == second.id and second.alt_en == "A woman in sunglasses"


def test_delete_image_moves_cover(admin_client, app):
    p = make_project("Del", images=2)
    first_id, second_id = p.images[0].id, p.images[1].id
    admin_client.post(f"/admin/images/{first_id}/delete")
    p = db.session.get(Project, p.id)
    assert [i.id for i in p.images] == [second_id] and p.images[0].is_cover


def test_delete_project_removes_files(admin_client, app):
    admin_client.post("/admin/projects/new", data={"title_en": "Gone", "images": [(image_bytes(), "a.png")]},
                      content_type="multipart/form-data")
    p = Project.query.one()
    path = os.path.join(app.config["UPLOAD_DIR"], p.images[0].filename)
    admin_client.post(f"/admin/projects/{p.id}/delete")
    assert Project.query.count() == 0 and ProjectImage.query.count() == 0 and not os.path.exists(path)


def test_reorder_projects(admin_client):
    a, b = make_project("A"), make_project("B")
    a.sort_order, b.sort_order = 0, 1
    db.session.commit()
    admin_client.post(f"/admin/projects/{b.id}/move", data={"direction": "up"})
    assert [p.title_en for p in Project.query.order_by(Project.sort_order)] == ["B", "A"]


def test_new_project_goes_first(admin_client):
    make_project("Old")
    admin_client.post("/admin/projects/new", data={"title_en": "New"})
    assert Project.query.order_by(Project.sort_order).first().title_en == "New"


# ---------------------------------------------------------------- categories / services / texts

def test_categories_crud(admin_client):
    admin_client.post("/admin/categories", data={"name_he": "ביוטי", "name_en": "Beauty"})
    cat = Category.query.filter_by(slug="beauty").one()
    admin_client.post(f"/admin/categories/{cat.id}", data={"name_he": "יופי", "name_en": "Beauty"})
    assert db.session.get(Category, cat.id).name_he == "יופי"
    p = make_project("Tagged", category_id=cat.id)
    admin_client.post(f"/admin/categories/{cat.id}/delete")
    assert db.session.get(Category, cat.id) is None and db.session.get(Project, p.id).category_id is None


def test_services_crud_and_toggle(admin_client, client):
    admin_client.post("/admin/services", data={"title_he": "ריטוש", "title_en": "Retouching"})
    s = Service.query.filter_by(title_en="Retouching").one()
    admin_client.post(f"/admin/services/{s.id}/toggle")
    assert db.session.get(Service, s.id).is_active is False
    assert "Retouching" not in client.get("/en/about/").get_data(as_text=True)


def test_texts_save_and_reset(admin_client):
    admin_client.post("/admin/texts", data={"about_title_en": "Hey!", "about_title_he": "", "instagram_en": "nofai.new"})
    assert db.session.get(SiteText, "about_title").value_en == "Hey!"
    assert "@nofai.new" in admin_client.get("/en/contact/").get_data(as_text=True)
    admin_client.post("/admin/texts", data={"about_title_en": ""})   # empty = starter copy again
    assert "Hi, I&#39;m Nofar" in admin_client.get("/en/about/").get_data(as_text=True)


def test_about_portrait_upload_and_remove(admin_client, app):
    admin_client.post("/admin/texts", data={"about_image": (image_bytes(), "me.png")}, content_type="multipart/form-data")
    filename = db.session.get(SiteText, "about_image").value_en
    assert filename and f"/media/{filename}" in admin_client.get("/en/about/").get_data(as_text=True)
    admin_client.post("/admin/texts", data={"remove_about_image": "1"})
    assert db.session.get(SiteText, "about_image").value_en is None
    assert not os.path.exists(os.path.join(app.config["UPLOAD_DIR"], filename))


# ---------------------------------------------------------------- inquiries

def test_inquiry_status_and_delete(admin_client):
    q = Inquiry(name="Dana", email="d@b.com", message="Hello there, campaign please")
    db.session.add(q)
    db.session.commit()
    assert "Dana" in admin_client.get(f"/admin/inquiries/{q.id}").get_data(as_text=True)
    admin_client.post(f"/admin/inquiries/{q.id}/status", data={"status": "replied"})
    assert db.session.get(Inquiry, q.id).status == "replied"
    admin_client.post(f"/admin/inquiries/{q.id}/status", data={"status": "bogus"})
    assert db.session.get(Inquiry, q.id).status == "replied"
    admin_client.post(f"/admin/inquiries/{q.id}/delete")
    assert Inquiry.query.count() == 0


def test_change_password(admin_client):
    r = admin_client.post("/admin/account", data={"current_password": "secret-123",
                                                  "new_password": "Studio-Light-77", "confirm_password": "Studio-Light-77"})
    assert r.status_code == 302


def test_cli_seed_is_idempotent(app):
    db.session.remove()
    db.drop_all()
    db.create_all()
    app.config["ADMIN_PASSWORD"] = "Cream-and-Sand-1"
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0
    assert runner.invoke(args=["seed"]).exit_code == 0
    assert Service.query.count() == 4 and Category.query.count() == 1
