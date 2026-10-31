"""Static export of the public site for Netlify (`flask --app app export`).

Every public page is rendered through the app itself (same templates, same data),
in both languages, and written as <path>/index.html. Netlify serves the result;
the admin stays on the owner's computer.

Output (dist/):
  en/…, he/…        pages (index.html per URL), plus en/404.html and he/404.html
  index.html        fallback for "/" (normally _redirects picks the language)
  static/           CSS, JS, favicon
  media/            images of PUBLISHED work + the About portrait (drafts stay private)
  _redirects        browser-language redirect for "/", per-language 404 pages
  _headers          the same security headers the Flask app sends
"""
import os
import shutil

from flask import Flask

from .extensions import db
from .security import CONTENT_SECURITY_POLICY

ROOT_INDEX = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0; url=/en/">
<title>NOFAI Studio</title><link rel="canonical" href="/en/"></head>
<body><p><a href="/en/">NOFAI Studio: English</a> · <a href="/he/" lang="he">עברית</a></p></body></html>
"""

HEADERS = f"""/*
  Content-Security-Policy: {CONTENT_SECURITY_POLICY}
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

/media/*
  Cache-Control: public, max-age=31536000, immutable
"""


class ExportError(Exception):
    pass


def _write(base: str, url_path: str, html: bytes) -> str:
    """'/en/about/' -> base/en/about/index.html"""
    target = os.path.join(base, *url_path.strip("/").split("/"), "index.html")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(html)
    return target


def _public_urls(lang: str, category_slugs: list[str]) -> list[str]:
    urls = [f"/{lang}/", f"/{lang}/about/", f"/{lang}/work/", f"/{lang}/contact/", f"/{lang}/contact/thanks/"]
    urls += [f"/{lang}/work/c/{slug}/" for slug in category_slugs]
    return urls


def export_site(app: Flask, out_dir: str | None = None) -> dict:
    from .models import Category, Project, SiteText
    from .site_texts import ABOUT_IMAGE_KEY

    out_dir = os.path.abspath(out_dir or app.config["STATIC_EXPORT_DIR"])
    staging = out_dir + ".building"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)

    previous = app.config["STATIC_EXPORT"]
    app.config["STATIC_EXPORT"] = True
    stats = {"pages": 0, "images": 0}
    try:
        with app.app_context():
            slugs = [c.slug for c in Category.query.order_by(Category.sort_order).all()]
            images = {img.filename for p in Project.query.filter_by(is_published=True).all()
                      if p.cover for img in p.images}
            portrait = db.session.get(SiteText, ABOUT_IMAGE_KEY)
            if portrait and portrait.value_en:
                images.add(portrait.value_en)

        client = app.test_client()
        for lang in app.config["LANGUAGES"]:
            for url in _public_urls(lang, slugs):
                response = client.get(url)
                if response.status_code != 200:
                    raise ExportError(f"{url} returned HTTP {response.status_code}")
                _write(staging, url, response.data)
                stats["pages"] += 1
            # the 404 page in this language (unknown path under /<lang>/)
            response = client.get(f"/{lang}/__missing__/", headers={"Accept-Language": lang})
            with open(os.path.join(staging, lang, "404.html"), "wb") as f:
                f.write(response.data)

        shutil.copyfile(os.path.join(staging, "en", "404.html"), os.path.join(staging, "404.html"))
        with open(os.path.join(staging, "index.html"), "w", encoding="utf-8") as f:
            f.write(ROOT_INDEX)
        with open(os.path.join(staging, "_redirects"), "w", encoding="utf-8") as f:
            # "!" forces the rule even though a fallback index.html exists at "/"
            f.write("/  /he/  302!  Language=he\n/  /en/  302!\n/he/*  /he/404.html  404\n/*  /en/404.html  404\n")
        with open(os.path.join(staging, "_headers"), "w", encoding="utf-8") as f:
            f.write(HEADERS)

        shutil.copytree(app.static_folder, os.path.join(staging, "static"))
        media_dir = os.path.join(staging, "media")
        os.makedirs(media_dir)
        for filename in sorted(images):
            source = os.path.join(app.config["UPLOAD_DIR"], filename)
            if os.path.exists(source):
                shutil.copy2(source, os.path.join(media_dir, filename))
                stats["images"] += 1
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        app.config["STATIC_EXPORT"] = previous

    # swap in the finished build only after everything succeeded
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(staging, out_dir)
    stats["out_dir"] = out_dir
    return stats
