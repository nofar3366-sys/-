"""Static export for Netlify (flask export)."""
import os

import pytest

from nofai.exporter import ExportError, export_site
from nofai.extensions import db
from nofai.models import Project, SiteText

from conftest import image_bytes, make_project


@pytest.fixture
def exported(app, admin_client, tmp_path):
    # one real uploaded image for a published project, one for a draft
    admin_client.post("/admin/projects/new", data={"title_en": "Live", "is_published": "1",
                                                   "images": [(image_bytes(), "a.png")]}, content_type="multipart/form-data")
    admin_client.post("/admin/projects/new", data={"title_en": "Secret draft",
                                                   "images": [(image_bytes(), "b.png")]}, content_type="multipart/form-data")
    out = tmp_path / "dist"
    stats = export_site(app, str(out))
    return out, stats


def read(path):
    return path.read_text(encoding="utf-8")


def test_all_pages_in_both_languages(exported):
    out, stats = exported
    for lang in ("en", "he"):
        for page in ("index.html", "about/index.html", "work/index.html", "contact/index.html",
                     "contact/thanks/index.html", "work/c/product-campaigns/index.html", "404.html"):
            assert (out / lang / page).exists(), f"{lang}/{page}"
    assert stats["pages"] == 12
    assert 'dir="rtl"' in read(out / "he" / "index.html")


def test_netlify_files(exported):
    out, _ = exported
    redirects = read(out / "_redirects")
    assert "/  /he/  302!  Language=he" in redirects and "/*  /en/404.html  404" in redirects
    assert "script-src 'self'" in read(out / "_headers")
    assert (out / "index.html").exists() and (out / "404.html").exists()
    assert (out / "static" / "css" / "site.css").exists()


def test_contact_form_uses_netlify_forms(exported):
    out, _ = exported
    html = read(out / "en" / "contact" / "index.html")
    assert 'data-netlify="true"' in html and 'name="form-name" value="contact"' in html
    assert 'netlify-honeypot="website"' in html
    assert "csrf_token" not in html   # no server to check it


def test_only_published_images_are_copied(exported, app):
    out, stats = exported
    live = Project.query.filter_by(title_en="Live").one().images[0].filename
    draft = Project.query.filter_by(title_en="Secret draft").one().images[0].filename
    assert (out / "media" / live).exists()
    assert not (out / "media" / draft).exists()
    assert "Secret draft" not in read(out / "en" / "work" / "index.html")
    assert stats["images"] == 1


def test_links_point_to_exported_paths(exported):
    out, _ = exported
    html = read(out / "en" / "index.html")
    for href in ('href="/en/about/"', 'href="/en/work/"', 'href="/en/contact/"', 'href="/he/"'):
        assert href in html
    assert "/admin" not in html


def test_admin_is_not_exported(exported):
    out, _ = exported
    assert not (out / "admin").exists()


def test_normal_mode_restored_after_export(exported, client):
    html = client.get("/en/contact/").get_data(as_text=True)
    assert "data-netlify" not in html and "csrf_token" in html


def test_failed_export_keeps_previous_build(app, tmp_path, monkeypatch):
    out = tmp_path / "dist"
    out.mkdir()
    (out / "keep.txt").write_text("previous build")
    monkeypatch.setattr("nofai.exporter._public_urls", lambda lang, slugs: [f"/{lang}/nope/"])
    with pytest.raises(ExportError):
        export_site(app, str(out))
    assert (out / "keep.txt").exists() and not (tmp_path / "dist.building").exists()


def test_cli_export(app, tmp_path):
    make_project("Cli")
    result = app.test_cli_runner().invoke(args=["export", "--out", str(tmp_path / "site")])
    assert result.exit_code == 0 and "Exported 12 pages" in result.output
