"""Public site. Every URL starts with the language: /en/... or /he/..."""
from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)
from flask_wtf.csrf import CSRFError

from ..extensions import db
from ..i18n import t
from ..mailer import send_inquiry_notification
from ..models import Category, Inquiry, Project, Service
from ..validators import validate_inquiry

public_bp = Blueprint("public", __name__, url_prefix="/<lang>")

FEATURED_ON_HOME = 6


@public_bp.url_value_preprocessor
def pull_lang(_endpoint, values):
    g.lang = values.pop("lang", None)
    if g.lang not in current_app.config["LANGUAGES"]:
        abort(404)


@public_bp.url_defaults
def add_lang(endpoint, values):
    if "lang" not in values and g.get("lang"):
        values["lang"] = g.lang


def _published():
    return Project.query.filter_by(is_published=True)


def _active_services():
    return Service.query.filter_by(is_active=True).order_by(Service.sort_order, Service.id).all()


def _wants_json() -> bool:
    return request.accept_mimetypes.best == "application/json"


# ---------------------------------------------------------------- pages

@public_bp.route("/")
def index():
    featured = (_published().filter_by(is_featured=True)
                .order_by(Project.sort_order, Project.created_at.desc()).limit(FEATURED_ON_HOME).all())
    if not featured:  # nothing marked yet: show the newest work instead of an empty section
        featured = _published().order_by(Project.created_at.desc()).limit(FEATURED_ON_HOME).all()
    featured = [p for p in featured if p.cover]
    return render_template("public/index.html", featured=featured, services=_active_services())


# Trailing slashes everywhere: every page maps to <path>/index.html in the static
# export (flask export), so the same URLs work on Netlify without extra redirects.

@public_bp.route("/about/")
def about():
    return render_template("public/about.html", services=_active_services())


def _render_work(active_slug: str = ""):
    categories = Category.query.order_by(Category.sort_order, Category.id).all()
    query = _published()
    if active_slug:
        cat = next((c for c in categories if c.slug == active_slug), None)
        if cat is None:
            abort(404)
        query = query.filter_by(category_id=cat.id)
    projects = [p for p in query.order_by(Project.sort_order, Project.created_at.desc()).all() if p.cover]
    return render_template("public/work.html", projects=projects, categories=categories, active=active_slug)


@public_bp.route("/work/")
def work():
    # old ?category= links still work (static files can't read query strings, hence the path form)
    if request.args.get("category"):
        return redirect(url_for("public.work_category", slug=request.args["category"]), 301)
    return _render_work()


@public_bp.route("/work/c/<slug>/")
def work_category(slug):
    return _render_work(slug)


@public_bp.route("/contact/thanks/")
def contact_thanks():
    """Shown after a no-JavaScript submission (and the Netlify Forms success page)."""
    return render_template("public/contact_thanks.html")


@public_bp.route("/contact/", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("public/contact.html", services=_active_services())

    # Honeypot: humans never see or fill this field
    if request.form.get("website"):
        return jsonify(ok=True, message=t("contact.success")) if _wants_json() else redirect(url_for("public.contact"))

    data, errors = validate_inquiry(request.form)
    if errors:
        messages = {field: t(key) for field, key in errors.items()}
        if _wants_json():
            return jsonify(ok=False, message=t("contact.fix"), errors=messages), 422
        for msg in messages.values():
            flash(msg, "error")
        return redirect(url_for("public.contact"))

    inquiry = Inquiry(**data, language=g.lang)
    db.session.add(inquiry)
    db.session.commit()
    if send_inquiry_notification(inquiry):
        inquiry.notified = True
        db.session.commit()

    if _wants_json():
        return jsonify(ok=True, message=t("contact.success")), 201
    return redirect(url_for("public.contact_thanks"))


@public_bp.app_errorhandler(CSRFError)
def handle_csrf_error(_err):
    if request.path.startswith("/admin"):
        message = "תוקף הטופס פג. נא לרענן את הדף ולנסות שוב."   # the admin is in Hebrew
    else:
        g.lang = g.get("lang") or current_app.config["DEFAULT_LANGUAGE"]
        message = t("contact.expired")
    if _wants_json():
        return jsonify(ok=False, message=message), 400
    flash(message, "error")
    ref = request.referrer
    return redirect(ref if ref and urlparse(ref).netloc == request.host else url_for("root"))
