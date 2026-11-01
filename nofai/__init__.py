"""Application factory."""
import os
import sqlite3
from datetime import datetime

from flask import Flask, g, redirect, render_template, request, send_from_directory, url_for
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import DEV_SECRET_KEY, INSTANCE_DIR, get_config
from .extensions import csrf, db, login_manager
from .security import register_security_headers


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores FOREIGN KEY constraints unless this pragma is on."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())

    if app.config.get("SESSION_COOKIE_SECURE") and app.config["SECRET_KEY"] in ("", DEV_SECRET_KEY):
        raise RuntimeError("SECRET_KEY is not set (required in production).")
    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    register_security_headers(app)

    from . import models  # noqa: F401
    from .routes import admin_content, admin_crm, admin_pricing  # noqa: F401  (add routes to admin_bp)
    from .routes.admin import admin_bp
    from .routes.public import public_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .cli import register_cli
    register_cli(app)

    _register_core_routes(app)
    _register_template_helpers(app)
    return app


def _register_core_routes(app):
    from .i18n import best_language

    @app.route("/")
    def root():
        return redirect(url_for("public.index", lang=best_language()))

    @app.route("/media/<path:filename>")
    def media(filename):
        """Uploaded images (local storage). Names are random, so they can be cached forever."""
        response = send_from_directory(app.config["UPLOAD_DIR"], filename, max_age=31536000)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.errorhandler(404)
    def not_found(_err):
        if g.get("lang") not in app.config["LANGUAGES"]:
            # outside the /<lang>/ pages (e.g. /nonsense): guess from the browser
            g.lang = best_language()
        return render_template("public/404.html"), 404


def _register_template_helpers(app):
    from .i18n import DIRECTION, LANGUAGE_NAMES, t
    from .models import SiteText
    from .site_texts import ABOUT_IMAGE_KEY, resolve
    from .storage import url_for_image

    def site_texts() -> dict:
        """All SiteText rows, loaded once per request."""
        if "site_texts" not in g:
            g.site_texts = {row.key: row for row in SiteText.query.all()}
        return g.site_texts

    def text(key: str) -> str:
        """Editable site copy (SiteText table, falling back to the starter copy)."""
        return resolve(key, site_texts().get(key))

    def about_image() -> str | None:
        """URL of the portrait uploaded for the About page, if any."""
        row = site_texts().get(ABOUT_IMAGE_KEY)
        return url_for_image(row.value_en) if row and row.value_en else None

    def switch_lang_url() -> str:
        """The current page in the other language (same endpoint, same filters)."""
        other = "he" if g.get("lang") == "en" else "en"
        endpoint = request.endpoint or ""
        if not endpoint.startswith("public."):
            return url_for("public.index", lang=other)
        args = dict(request.view_args or {}, lang=other)
        args.update(request.args.to_dict())
        return url_for(endpoint, **args)

    @app.template_filter("image_payload")
    def image_payload(image) -> dict:
        """What the lightbox needs to show one image (sent as JSON in a data attribute)."""
        return {"src": url_for_image(image.filename), "w": image.width, "h": image.height,
                "alt": image.tr("alt")}

    @app.context_processor
    def inject_lang():
        lang = g.get("lang") or app.config["DEFAULT_LANGUAGE"]
        return {"lang": lang, "dir": DIRECTION[lang]}

    app.jinja_env.globals.update(
        t=t, text=text, img=url_for_image, switch_lang_url=switch_lang_url, about_image=about_image,
        now=datetime.now, LANGUAGE_NAMES=LANGUAGE_NAMES, DIRECTION=DIRECTION,
    )
