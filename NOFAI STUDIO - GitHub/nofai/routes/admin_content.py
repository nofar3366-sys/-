"""Back-office content management: projects + images, categories, services, site texts.
Registered on the admin blueprint (same /admin prefix and login guard)."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import Category, Project, ProjectImage, Service, SiteText
from ..site_texts import ABOUT_IMAGE_KEY, FIELDS
from ..storage import ImageRejected, delete_image, save_image
from ..validators import unique_slug, slugify, validate_bilingual_name, validate_project
from .admin import admin_bp, get_or_404, safe_next


def renumber(items: list) -> None:
    for order, obj in enumerate(items):
        obj.sort_order = order
    db.session.commit()


def move(items: list, item, direction: str) -> None:
    """Swap `item` with its neighbour ("up"/"down") in an ordered list, then renumber 0..n."""
    if direction in ("up", "down"):
        index = items.index(item)
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
    renumber(items)


# ================================================================ projects

def _ordered_projects():
    return Project.query.order_by(Project.sort_order, Project.created_at.desc()).all()


@admin_bp.route("/projects")
@login_required
def projects():
    return render_template("admin/projects.html", projects=_ordered_projects())


def _project_form(project, form, errors):
    return render_template("admin/project_form.html", project=project, form=form, errors=errors,
                           categories=Category.query.order_by(Category.sort_order).all())


def _save_uploads(project) -> tuple[int, list[str]]:
    """Store every file from the 'images' input. Returns (saved count, error messages)."""
    saved, problems = 0, []
    next_order = len(project.images)
    for upload in request.files.getlist("images"):
        if not upload or not upload.filename:
            continue
        try:
            filename, width, height = save_image(upload)
        except ImageRejected as exc:
            problems.append(f"{upload.filename}: {exc}")
            continue
        project.images.append(ProjectImage(filename=filename, width=width, height=height,
                                           sort_order=next_order, is_cover=not project.images))
        next_order += 1
        saved += 1
    return saved, problems


def _report_uploads(saved, problems):
    if saved:
        flash(f"{saved} תמונות הועלו", "success")
    for problem in problems:
        flash(problem, "error")


@admin_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "POST":
        data, errors = validate_project(request.form)
        if not errors:
            project = Project(**data, sort_order=-1)  # new work goes to the top
            db.session.add(project)
            saved, problems = _save_uploads(project)
            db.session.commit()
            renumber(_ordered_projects())
            flash(f"הפרויקט '{project.title_he}' נוצר", "success")
            _report_uploads(saved, problems)
            return redirect(url_for("admin.project_edit", project_id=project.id))
        flash("נא לתקן את השדות המסומנים", "error")
        return _project_form(None, request.form, errors)
    return _project_form(None, {"is_published": "1"}, {})


@admin_bp.route("/projects/<int:project_id>", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    project = get_or_404(Project, project_id)
    if request.method == "POST":
        data, errors = validate_project(request.form, project)
        if not errors:
            for field, value in data.items():
                setattr(project, field, value)
            # per-image alt texts + cover choice (submitted with the same form)
            cover_id = request.form.get("cover_id", type=int)
            for image in project.images:
                image.alt_he = (request.form.get(f"alt_he_{image.id}") or "").strip()[:200] or None
                image.alt_en = (request.form.get(f"alt_en_{image.id}") or "").strip()[:200] or None
                if cover_id:
                    image.is_cover = image.id == cover_id
            saved, problems = _save_uploads(project)
            db.session.commit()
            flash("השינויים נשמרו", "success")
            _report_uploads(saved, problems)
            return redirect(url_for("admin.project_edit", project_id=project.id))
        flash("נא לתקן את השדות המסומנים", "error")
        return _project_form(project, request.form, errors)

    form = {f: getattr(project, f) for f in ("title_he", "title_en", "client", "description_he",
                                             "description_en", "slug")}
    form.update(year=project.year or "", category_id=str(project.category_id or ""),
                is_featured="1" if project.is_featured else "", is_published="1" if project.is_published else "")
    return _project_form(project, form, {})


@admin_bp.route("/projects/<int:project_id>/move", methods=["POST"])
@login_required
def project_move(project_id):
    move(_ordered_projects(), get_or_404(Project, project_id), request.form.get("direction", ""))
    return redirect(url_for("admin.projects"))


@admin_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def project_delete(project_id):
    project = get_or_404(Project, project_id)
    files = [image.filename for image in project.images]
    title = project.title_he
    db.session.delete(project)
    db.session.commit()
    for filename in files:  # remove files only after the database change succeeded
        delete_image(filename)
    flash(f"הפרויקט '{title}' ו-{len(files)} התמונות שלו נמחקו", "success")
    return redirect(url_for("admin.projects"))


@admin_bp.route("/images/<int:image_id>/move", methods=["POST"])
@login_required
def image_move(image_id):
    image = get_or_404(ProjectImage, image_id)
    move(list(image.project.images), image, request.form.get("direction", ""))
    return redirect(url_for("admin.project_edit", project_id=image.project_id) + "#images")


@admin_bp.route("/images/<int:image_id>/delete", methods=["POST"])
@login_required
def image_delete(image_id):
    image = get_or_404(ProjectImage, image_id)
    project, filename, was_cover = image.project, image.filename, image.is_cover
    # Removing it from the collection (delete-orphan cascade deletes the row) also keeps
    # project.images accurate in memory; session.delete() would leave it in the list.
    project.images.remove(image)
    if was_cover and project.images:
        project.images[0].is_cover = True
    db.session.commit()
    delete_image(filename)
    flash("התמונה נמחקה", "success")
    return redirect(url_for("admin.project_edit", project_id=project.id) + "#images")


# ================================================================ categories

def _ordered_categories():
    return Category.query.order_by(Category.sort_order, Category.id).all()


@admin_bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form
        data, errors = validate_bilingual_name(form)
        if not errors:
            cat = Category(**data, slug=unique_slug(slugify(data["name_en"]) or "category", Category),
                           sort_order=len(_ordered_categories()))
            db.session.add(cat)
            db.session.commit()
            flash(f"הקטגוריה '{cat.name_he}' נוספה", "success")
            return redirect(url_for("admin.categories"))
    rows = [(c, c.projects.count()) for c in _ordered_categories()]
    return render_template("admin/categories.html", rows=rows, errors=errors, form=form)


@admin_bp.route("/categories/<int:category_id>", methods=["POST"])
@login_required
def category_update(category_id):
    cat = get_or_404(Category, category_id)
    data, errors = validate_bilingual_name(request.form)
    if errors:
        flash("יש למלא שם בשתי השפות (עד 80 תווים)", "error")
    else:
        cat.name_he, cat.name_en = data["name_he"], data["name_en"]
        db.session.commit()
        flash("הקטגוריה עודכנה", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/<int:category_id>/move", methods=["POST"])
@login_required
def category_move(category_id):
    move(_ordered_categories(), get_or_404(Category, category_id), request.form.get("direction", ""))
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def category_delete(category_id):
    cat = get_or_404(Category, category_id)
    count = cat.projects.count()
    db.session.delete(cat)   # projects keep existing, without a category (FK ON DELETE SET NULL)
    db.session.commit()
    flash(f"הקטגוריה נמחקה{f'. {count} פרויקטים נשארו בלי קטגוריה' if count else ''}", "success")
    return redirect(url_for("admin.categories"))


# ================================================================ services

SERVICE_FIELDS = ("title_he", "title_en")


def _ordered_services():
    return Service.query.order_by(Service.sort_order, Service.id).all()


def _service_data(form):
    data, errors = validate_bilingual_name(form, limit=120, fields=SERVICE_FIELDS)
    for field in ("description_he", "description_en"):
        value = (form.get(field) or "").strip()
        if len(value) > 600:
            errors[field] = "עד 600 תווים"
        data[field] = value or None
    return data, errors


@admin_bp.route("/services", methods=["GET", "POST"])
@login_required
def services():
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form
        data, errors = _service_data(form)
        if not errors:
            db.session.add(Service(**data, sort_order=len(_ordered_services())))
            db.session.commit()
            flash("השירות נוסף", "success")
            return redirect(url_for("admin.services"))
    return render_template("admin/services.html", services=_ordered_services(), errors=errors, form=form)


@admin_bp.route("/services/<int:service_id>", methods=["POST"])
@login_required
def service_update(service_id):
    service = get_or_404(Service, service_id)
    data, errors = _service_data(request.form)
    if errors:
        flash("יש למלא כותרת בשתי השפות (עד 120 תווים, תיאור עד 600)", "error")
    else:
        for field, value in data.items():
            setattr(service, field, value)
        db.session.commit()
        flash("השירות עודכן", "success")
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:service_id>/toggle", methods=["POST"])
@login_required
def service_toggle(service_id):
    service = get_or_404(Service, service_id)
    service.is_active = not service.is_active
    db.session.commit()
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:service_id>/move", methods=["POST"])
@login_required
def service_move(service_id):
    move(_ordered_services(), get_or_404(Service, service_id), request.form.get("direction", ""))
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:service_id>/delete", methods=["POST"])
@login_required
def service_delete(service_id):
    db.session.delete(get_or_404(Service, service_id))
    db.session.commit()
    flash("השירות נמחק", "success")
    return redirect(url_for("admin.services"))


# ================================================================ site texts

TEXT_LIMIT = 3000


@admin_bp.route("/texts", methods=["GET", "POST"])
@login_required
def texts():
    stored = {row.key: row for row in SiteText.query.all()}
    if request.method == "POST":
        too_long = []
        for field in FIELDS:
            row = stored.get(field.key) or SiteText(key=field.key)
            langs = ("he", "en") if field.translated else ("en",)
            for lang in langs:
                value = (request.form.get(f"{field.key}_{lang}") or "").strip()
                if len(value) > TEXT_LIMIT:
                    too_long.append(field.label)
                    value = value[:TEXT_LIMIT]
                setattr(row, f"value_{lang}", value or None)   # empty = back to the starter copy
            db.session.add(row)
        _update_about_image(stored)
        db.session.commit()
        flash("הטקסטים נשמרו", "success")
        for label in too_long:
            flash(f"'{label}' קוצר ל-{TEXT_LIMIT} תווים", "error")
        return redirect(safe_next(url_for("admin.texts")))

    groups = {}
    for field in FIELDS:
        groups.setdefault(field.group, []).append(field)
    about = stored.get(ABOUT_IMAGE_KEY)
    return render_template("admin/texts.html", groups=groups, stored=stored,
                           about_image=about.value_en if about else None)


def _update_about_image(stored) -> None:
    """Portrait for the About page: replace or remove (old file deleted after the change)."""
    row = stored.get(ABOUT_IMAGE_KEY)
    old = row.value_en if row else None
    upload = request.files.get("about_image")
    if upload and upload.filename:
        try:
            filename, _w, _h = save_image(upload)
        except ImageRejected as exc:
            flash(f"תמונת 'מי אני': {exc}", "error")
            return
        row = row or SiteText(key=ABOUT_IMAGE_KEY)
        row.value_en = filename
        db.session.add(row)
    elif request.form.get("remove_about_image") == "1" and row:
        row.value_en = None
    else:
        return
    db.session.flush()
    if old and old != row.value_en:
        delete_image(old)
