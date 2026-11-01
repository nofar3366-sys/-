"""Back-office: authentication, dashboard, inquiries, account.
Content management (projects, images, categories, services, texts) is in admin_content.py."""
from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, login_manager
from ..models import Admin, Inquiry, InquiryStatus, Note, Project, ProjectImage
from ..security import login_throttle
from ..validators import DEFAULT_ADMIN_PASSWORD, validate_new_password

admin_bp = Blueprint("admin", __name__)

PUBLIC_ENDPOINTS = {"admin.login"}
INQUIRIES_PER_PAGE = 25


@admin_bp.before_request
def require_admin():
    """Blueprint-wide guard: no admin route can be left unprotected by accident."""
    if request.endpoint not in PUBLIC_ENDPOINTS and not current_user.is_authenticated:
        return login_manager.unauthorized()


def safe_next(default: str) -> str:
    target = request.values.get("next")
    if target and target.startswith("/") and not urlparse(target).netloc:
        return target
    return default


def get_or_404(model, obj_id):
    obj = db.session.get(model, obj_id)
    if obj is None:
        abort(404)
    return obj


# ---------------------------------------------------------------- auth

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        client = request.remote_addr or "unknown"
        cfg = current_app.config
        locked = login_throttle.seconds_locked(client, cfg["LOGIN_MAX_ATTEMPTS"], cfg["LOGIN_LOCKOUT_SECONDS"])
        if locked:
            flash(f"יותר מדי ניסיונות כניסה. נסו שוב בעוד {locked // 60 + 1} דקות.", "error")
            return render_template("admin/login.html"), 429

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_throttle.reset(client)
            session.clear()  # fresh session on login (prevents session fixation)
            login_user(admin)
            session["default_password"] = password == DEFAULT_ADMIN_PASSWORD
            return redirect(safe_next(url_for("admin.dashboard")))

        login_throttle.record_failure(client)
        current_app.logger.warning("Failed admin login for %r from %s", username, client)
        flash("שם משתמש או סיסמה שגויים", "error")
    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("התנתקת בהצלחה", "success")
    return redirect(url_for("admin.login"))


@admin_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    errors = {}
    if request.method == "POST":
        key = f"account:{current_user.id}"
        cfg = current_app.config
        if login_throttle.seconds_locked(key, cfg["LOGIN_MAX_ATTEMPTS"], cfg["LOGIN_LOCKOUT_SECONDS"]):
            flash("יותר מדי ניסיונות שגויים. נסו שוב מאוחר יותר.", "error")
            return render_template("admin/account.html", errors=errors), 429
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current_user.check_password(current):
            login_throttle.record_failure(key)
            errors["current_password"] = "הסיסמה הנוכחית שגויה"
        else:
            problem = validate_new_password(new, confirm, current_user.username)
            if problem:
                errors[problem[0]] = problem[1]
            elif new == current:
                errors["new_password"] = "הסיסמה החדשה זהה לנוכחית"
        if not errors:
            login_throttle.reset(key)
            current_user.set_password(new)
            db.session.commit()
            session["default_password"] = False
            flash("הסיסמה עודכנה בהצלחה", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/account.html", errors=errors)


# ---------------------------------------------------------------- dashboard

@admin_bp.route("/")
@login_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        new_inquiries=Inquiry.query.filter_by(status=InquiryStatus.NEW).order_by(Inquiry.created_at.desc()).limit(5).all(),
        new_count=Inquiry.query.filter_by(status=InquiryStatus.NEW).count(),
        project_count=Project.query.count(),
        published_count=Project.query.filter_by(is_published=True).count(),
        image_count=ProjectImage.query.count(),
    )


# ---------------------------------------------------------------- inquiries

@admin_bp.route("/inquiries")
@login_required
def inquiries():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    query = Inquiry.query
    if status in InquiryStatus.ALL:
        query = query.filter_by(status=status)
    else:
        status = ""
    pagination = query.order_by(Inquiry.created_at.desc()).paginate(page=page, per_page=INQUIRIES_PER_PAGE, error_out=False)
    counts = dict(db.session.query(Inquiry.status, db.func.count(Inquiry.id)).group_by(Inquiry.status).all())
    return render_template("admin/inquiries.html", pagination=pagination, inquiries=pagination.items,
                           status=status, counts=counts, statuses=InquiryStatus.ALL, labels=InquiryStatus.LABELS_HE)


@admin_bp.route("/inquiries/<int:inquiry_id>")
@login_required
def inquiry_detail(inquiry_id):
    return render_template("admin/inquiry_detail.html", inquiry=get_or_404(Inquiry, inquiry_id),
                           statuses=InquiryStatus.ALL, labels=InquiryStatus.LABELS_HE)


@admin_bp.route("/inquiries/<int:inquiry_id>/status", methods=["POST"])
@login_required
def inquiry_status(inquiry_id):
    inquiry = get_or_404(Inquiry, inquiry_id)
    status = request.form.get("status", "")
    if status in InquiryStatus.ALL:
        inquiry.status = status
        db.session.commit()
        flash(f"הפנייה של {inquiry.name} סומנה כ'{inquiry.status_label}'", "success")
    else:
        flash("סטטוס לא תקין", "error")
    return redirect(safe_next(url_for("admin.inquiries")))


@admin_bp.route("/inquiries/<int:inquiry_id>/delete", methods=["POST"])
@login_required
def inquiry_delete(inquiry_id):
    inquiry = get_or_404(Inquiry, inquiry_id)
    # notes that already belong to a client's history stay with the client; the rest go with the inquiry
    Note.query.filter(Note.inquiry_id == inquiry.id, Note.client_id.isnot(None)).update(
        {"inquiry_id": None}, synchronize_session=False)
    db.session.expire(inquiry, ["notes"])
    db.session.delete(inquiry)
    db.session.commit()
    flash("הפנייה נמחקה", "success")
    return redirect(safe_next(url_for("admin.inquiries")))
