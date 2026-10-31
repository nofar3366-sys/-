import json
import re

import pytest

from nofai.extensions import db
from nofai.models import Inquiry, SiteText

from conftest import make_project


# ---------------------------------------------------------------- languages

@pytest.mark.parametrize("accept,expected", [("he-IL,he;q=0.9", "/he/"), ("en-US", "/en/"), ("fr-FR", "/en/")])
def test_root_redirects_by_browser_language(client, accept, expected):
    r = client.get("/", headers={"Accept-Language": accept})
    assert r.status_code == 302 and r.headers["Location"] == expected


def test_direction_and_language_attributes(client):
    he = client.get("/he/").get_data(as_text=True)
    en = client.get("/en/").get_data(as_text=True)
    assert '<html lang="he" dir="rtl">' in he and '<html lang="en" dir="ltr">' in en
    assert "בית" in he and "Home" in en


def test_language_switch_keeps_page_and_filters(client):
    html = client.get("/en/work/c/product-campaigns/").get_data(as_text=True)
    assert 'href="/he/work/c/product-campaigns/"' in html
    assert 'hreflang="he"' in html


def test_unknown_language_is_404(client):
    r = client.get("/fr/about/")
    assert r.status_code == 404


@pytest.mark.parametrize("url", ["/en/", "/he/", "/en/about/", "/he/about/", "/en/work/", "/he/work/", "/en/contact/", "/he/contact/"])
def test_all_pages_render(client, url):
    make_project()
    assert client.get(url).status_code == 200


# ---------------------------------------------------------------- content

def test_bilingual_fallback(client):
    make_project(title="Eyewear", title_he="")   # Hebrew title missing
    html = client.get("/he/work/").get_data(as_text=True)
    assert "Eyewear" in html


def test_drafts_and_imageless_projects_hidden(client):
    make_project("Visible")
    make_project("Draft", published=False)
    make_project("NoImages", images=0)
    html = client.get("/en/work/").get_data(as_text=True)
    assert "Visible" in html and "Draft" not in html and "NoImages" not in html


def test_home_shows_featured_else_newest(client):
    make_project("Featured", featured=True)
    make_project("Regular", featured=False)
    html = client.get("/en/").get_data(as_text=True)
    assert "Featured" in html and "Regular" not in html


def test_lightbox_payload_is_valid_json(client):
    make_project("Gallery", images=3, client="Brand Co", year=2026)
    html = client.get("/en/work/").get_data(as_text=True)
    raw = re.search(r"data-gallery='([^']+)'", html).group(1)
    data = json.loads(raw.replace("&#34;", '"').replace("&#39;", "'").replace("&amp;", "&"))
    assert data["title"] == "Gallery" and data["client"] == "Brand Co" and len(data["images"]) == 3
    assert data["images"][0]["src"].startswith("/media/")


def test_category_filter(client, app):
    from nofai.models import Category
    other = Category(slug="beauty", name_he="ביוטי", name_en="Beauty")
    db.session.add(other)
    db.session.commit()
    make_project("InCampaigns", category_id=1)
    make_project("InBeauty", category_id=other.id)
    html = client.get("/en/work/c/beauty/").get_data(as_text=True)
    assert "InBeauty" in html and "InCampaigns" not in html
    assert client.get("/en/work/c/nope/").status_code == 404
    assert client.get("/en/work/?category=beauty").headers["Location"] == "/en/work/c/beauty/"


def test_site_text_override_and_fallback(client):
    db.session.add(SiteText(key="about_title", value_en="Hello there", value_he=None))
    db.session.commit()
    assert "Hello there" in client.get("/en/about/").get_data(as_text=True)
    # Hebrew empty -> falls back to the English value the owner wrote
    assert "Hello there" in client.get("/he/about/").get_data(as_text=True)


def test_user_content_is_escaped(client):
    make_project("<script>alert(1)</script>")
    html = client.get("/en/work/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html


# ---------------------------------------------------------------- contact form

JSON = {"Accept": "application/json"}
VALID = {"name": "Dana", "email": "Dana@Brand.com", "company": "Brand", "service": "Campaigns",
         "message": "We'd love a summer campaign for our new sunglasses."}


def test_contact_submit_saves_and_reports(client):
    r = client.post("/he/contact/", data=VALID, headers=JSON)
    assert r.status_code == 201 and r.get_json()["ok"]
    q = Inquiry.query.one()
    assert (q.email, q.language, q.status, q.notified) == ("dana@brand.com", "he", "new", False)


def test_contact_errors_in_page_language(client):
    r = client.post("/he/contact/", data={"name": "", "email": "x", "message": "hi"}, headers=JSON)
    errors = r.get_json()["errors"]
    assert r.status_code == 422 and set(errors) == {"name", "email", "message"}
    assert errors["email"] == "נא להזין כתובת אימייל תקינה"
    r = client.post("/en/contact/", data={"name": "", "email": "x", "message": "hi"}, headers=JSON)
    assert r.get_json()["errors"]["email"] == "Please enter a valid email address"
    assert Inquiry.query.count() == 0


def test_contact_honeypot(client):
    r = client.post("/en/contact/", data={**VALID, "website": "spam"}, headers=JSON)
    assert r.get_json()["ok"] and Inquiry.query.count() == 0


def test_contact_without_js_redirects(client):
    r = client.post("/en/contact/", data=VALID)
    assert r.status_code == 302 and r.headers["Location"] == "/en/contact/thanks/"


def test_contact_email_notification(client, app, monkeypatch):
    sent = []
    monkeypatch.setattr("nofai.routes.public.send_inquiry_notification", lambda q: sent.append(q.name) or True)
    client.post("/en/contact/", data=VALID, headers=JSON)
    assert sent == ["Dana"] and Inquiry.query.one().notified is True


def test_security_headers(client):
    r = client.get("/en/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"


def test_no_inline_styles_or_scripts(client):
    """The CSP forbids them; make sure no template sneaks one in."""
    make_project()
    for url in ("/en/", "/en/about/", "/en/work/", "/en/contact/"):
        html = client.get(url).get_data(as_text=True)
        assert " style=" not in html, url
        assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None, url
