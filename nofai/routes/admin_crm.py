"""Back-office CRM: notes, converting an inquiry into a client, clients and their projects.
Registered on the admin blueprint (same /admin prefix and login guard)."""
from datetime import datetime, time

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import (Client, ClientProject, ClientSource, ClientStatus, Inquiry, InquiryStatus, Note, NoteKind,
                      PriceQuote, ProjectStatus, QuoteStatus)
from ..validators import phone_key, validate_client, validate_client_project, validate_note
from .admin import admin_bp, get_or_404, safe_next

CLIENTS_PER_PAGE = 25
CLIENT_TABS = ("timeline", "projects", "quotes", "details")


def _first_error(errors: dict) -> str:
    return next(iter(errors.values()))


def _like(term: str) -> str:
    """A LIKE pattern for user input (the term's own % and _ are matched literally)."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ---------------------------------------------------------------- notes

@admin_bp.route("/inquiries/<int:inquiry_id>/notes", methods=["POST"])
@login_required
def inquiry_note_add(inquiry_id):
    inquiry = get_or_404(Inquiry, inquiry_id)
    data, errors = validate_note(request.form)
    if errors:
        flash(_first_error(errors), "error")
    else:
        db.session.add(Note(inquiry_id=inquiry.id, client_id=inquiry.client_id, **data))
        if inquiry.client:
            inquiry.client.touch()
        db.session.commit()
        flash("ההערה נוספה", "success")
    return redirect(url_for("admin.inquiry_detail", inquiry_id=inquiry.id) + "#notes")


@admin_bp.route("/clients/<int:client_id>/notes", methods=["POST"])
@login_required
def client_note_add(client_id):
    client = get_or_404(Client, client_id)
    data, errors = validate_note(request.form)
    if errors:
        flash(_first_error(errors), "error")
    else:
        db.session.add(Note(client_id=client.id, **data))
        client.touch()
        db.session.commit()
        flash("ההערה נוספה", "success")
    return redirect(url_for("admin.client_detail", client_id=client.id))


def _note_home(note: Note) -> str:
    if note.inquiry_id and not note.client_id:
        return url_for("admin.inquiry_detail", inquiry_id=note.inquiry_id) + "#notes"
    if note.client_id:
        return url_for("admin.client_detail", client_id=note.client_id)
    return url_for("admin.inquiries")


@admin_bp.route("/notes/<int:note_id>/edit", methods=["POST"])
@login_required
def note_edit(note_id):
    note = get_or_404(Note, note_id)
    if note.is_system:
        flash("אי אפשר לערוך רשומה שנוצרה אוטומטית", "error")
    else:
        data, errors = validate_note(request.form)
        if errors:
            flash(_first_error(errors), "error")
        else:
            note.kind, note.body = data["kind"], data["body"]
            db.session.commit()
            flash("ההערה עודכנה", "success")
    return redirect(safe_next(_note_home(note)))


@admin_bp.route("/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def note_delete(note_id):
    note = get_or_404(Note, note_id)
    target = safe_next(_note_home(note))
    if note.is_system:
        flash("אי אפשר למחוק רשומה שנוצרה אוטומטית", "error")
    else:
        db.session.delete(note)
        db.session.commit()
        flash("ההערה נמחקה", "success")
    return redirect(target)


# ---------------------------------------------------------------- inquiry -> client

def _matching_clients(inquiry: Inquiry) -> list[Client]:
    """Clients that look like the same person: same phone number or same e-mail."""
    key = phone_key(inquiry.phone)
    email = (inquiry.email or "").lower()
    found = []
    for client in Client.query.order_by(Client.updated_at.desc()).all():
        same_phone = len(key) >= 7 and phone_key(client.phone) == key
        same_email = bool(email) and (client.email or "").lower() == email
        if same_phone or same_email:
            found.append(client)
    return found


def _convert_values(inquiry: Inquiry) -> dict:
    default_project = inquiry.service or ""
    return {"name": inquiry.name, "phone": inquiry.phone or "", "email": inquiry.email or "",
            "company": inquiry.company or "", "website": "", "language": inquiry.language,
            "source": ClientSource.SITE, "status": ClientStatus.ACTIVE,
            "project_name": f"{inquiry.company or inquiry.name} · {default_project}".strip(" ·")}


def _attach_inquiry(inquiry: Inquiry, client: Client, converted: bool) -> None:
    """Link the inquiry to the client and carry its notes and quotes into the client's history."""
    inquiry.client_id = client.id
    Note.query.filter_by(inquiry_id=inquiry.id).update({"client_id": client.id}, synchronize_session=False)
    PriceQuote.query.filter_by(inquiry_id=inquiry.id).update({"client_id": client.id}, synchronize_session=False)
    if inquiry.status == InquiryStatus.NEW:
        inquiry.status = InquiryStatus.REPLIED
    when = inquiry.created_at.strftime("%d/%m/%Y")
    verb = "הומרה ללקוח" if converted else "שויכה ללקוח קיים"
    db.session.add(Note(kind=NoteKind.SYSTEM, body=f"הפנייה מתאריך {when} {verb}",
                        inquiry_id=inquiry.id, client_id=client.id))
    client.touch()


def _first_project(inquiry: Inquiry, client: Client, name: str) -> ClientProject:
    quotes = [q for q in inquiry.quotes if q.status != QuoteStatus.DECLINED]
    approved = [q for q in quotes if q.status == QuoteStatus.APPROVED]
    project = ClientProject(
        client_id=client.id, name=(name or "").strip()[:160] or inquiry.service or "פרויקט ראשון",
        service=inquiry.service, brief=inquiry.message[:5000],
        status=ProjectStatus.IN_PROGRESS if approved else ProjectStatus.PROPOSAL,
        amount=approved[0].total if approved else None)
    db.session.add(project)
    db.session.flush()
    for quote in quotes:
        quote.project_id = project.id
    return project


@admin_bp.route("/inquiries/<int:inquiry_id>/convert", methods=["GET", "POST"])
@login_required
def inquiry_convert(inquiry_id):
    inquiry = get_or_404(Inquiry, inquiry_id)
    if inquiry.client_id and db.session.get(Client, inquiry.client_id):
        flash("הפנייה הזו כבר הומרה ללקוח", "error")
        return redirect(url_for("admin.client_detail", client_id=inquiry.client_id))

    values, errors = _convert_values(inquiry), {}
    if request.method == "POST":
        if request.form.get("action") == "existing":
            client = db.session.get(Client, request.form.get("client_id", type=int) or 0)
            if client is None:
                flash("יש לבחור לקוח מהרשימה", "error")
            else:
                _attach_inquiry(inquiry, client, converted=False)
                db.session.commit()
                flash(f"הפנייה שויכה ללקוח {client.display_name}", "success")
                return redirect(url_for("admin.client_detail", client_id=client.id))
        else:
            data, errors = validate_client(request.form)
            values = {**values, **{k: request.form.get(k, "") for k in values}}
            if not errors:
                client = Client(**data)
                db.session.add(client)
                db.session.flush()
                _attach_inquiry(inquiry, client, converted=True)
                if request.form.get("create_project") == "1":
                    _first_project(inquiry, client, request.form.get("project_name", ""))
                db.session.commit()
                flash(f"{client.display_name} נוסף/ה ללקוחות", "success")
                return redirect(url_for("admin.client_detail", client_id=client.id))

    page = render_template("admin/inquiry_convert.html", inquiry=inquiry, values=values, errors=errors,
                           matches=_matching_clients(inquiry), clients=Client.query.order_by(Client.name).all(),
                           sources=ClientSource, statuses=ClientStatus)
    return (page, 422) if errors else page


# ---------------------------------------------------------------- clients

@admin_bp.route("/clients")
@login_required
def clients():
    term = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    query = Client.query
    if term:
        pattern = _like(term)
        query = query.filter(db.or_(*(col.ilike(pattern, escape="\\")
                                      for col in (Client.name, Client.company, Client.email, Client.phone))))
    if status in ClientStatus.ALL:
        query = query.filter_by(status=status)
    else:
        status = ""
    pagination = query.order_by(Client.updated_at.desc()).paginate(page=page, per_page=CLIENTS_PER_PAGE, error_out=False)
    counts = dict(db.session.query(Client.status, db.func.count(Client.id)).group_by(Client.status).all())
    project_counts = dict(db.session.query(ClientProject.client_id, db.func.count(ClientProject.id))
                          .group_by(ClientProject.client_id).all())
    return render_template("admin/clients.html", pagination=pagination, clients=pagination.items, q=term, status=status,
                           counts=counts, project_counts=project_counts, statuses=ClientStatus.ALL,
                           labels=ClientStatus.LABELS_HE)


@admin_bp.route("/clients/new", methods=["GET", "POST"])
@login_required
def client_new():
    values = {"name": "", "phone": "", "email": "", "company": "", "website": "",
              "language": "he", "source": ClientSource.OTHER, "status": ClientStatus.ACTIVE}
    errors = {}
    if request.method == "POST":
        data, errors = validate_client(request.form)
        values = {k: request.form.get(k, "") for k in values}
        if not errors:
            client = Client(**data)
            db.session.add(client)
            db.session.commit()
            flash("הלקוח נוצר", "success")
            return redirect(url_for("admin.client_detail", client_id=client.id))
    page = render_template("admin/client_form.html", values=values, errors=errors, sources=ClientSource, statuses=ClientStatus)
    return (page, 422) if errors else page


def _timeline(client: Client) -> list[dict]:
    """Everything that happened with this client, newest first."""
    items = []
    for inquiry in client.inquiries:
        items.append({"when": inquiry.created_at, "label": "פנייה התקבלה", "title": inquiry.service,
                      "body": inquiry.message, "href": url_for("admin.inquiry_detail", inquiry_id=inquiry.id), "note": None})
    for note in client.notes:
        items.append({"when": note.created_at, "label": note.kind_label, "title": None, "body": note.body,
                      "href": None, "note": note})
    for quote in client.quotes:
        items.append({"when": quote.updated_at, "label": "הצעת מחיר", "title": f"{quote.title} · {quote.status_label}",
                      "body": f"{quote.total:,} ₪ לפני מע״מ", "href": url_for("admin.pricing_edit", quote_id=quote.id), "note": None})
    for project in client.projects:
        href = url_for("admin.client_project", project_id=project.id)
        items.append({"when": project.created_at, "label": "פרויקט נפתח", "title": project.name, "body": None,
                      "href": href, "note": None})
        if project.delivered_date:
            items.append({"when": datetime.combine(project.delivered_date, time.min), "label": "פרויקט נמסר",
                          "title": project.name, "body": None, "href": href, "note": None})
    return sorted(items, key=lambda item: item["when"], reverse=True)


def _client_values(client: Client) -> dict:
    return {"name": client.name, "phone": client.phone or "", "email": client.email or "",
            "company": client.company or "", "website": client.website or "", "language": client.language,
            "source": client.source, "status": client.status}


def _render_client(client: Client, tab: str, values=None, errors=None, code=200):
    page = render_template(
        "admin/client_detail.html", client=client, tab=tab, values=values or _client_values(client), errors=errors or {},
        timeline=_timeline(client) if tab == "timeline" else [], sources=ClientSource, statuses=ClientStatus,
        note_kinds=NoteKind, project_labels=ProjectStatus.LABELS_HE)
    return (page, code) if code != 200 else page


@admin_bp.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    tab = request.args.get("tab", "timeline")
    return _render_client(get_or_404(Client, client_id), tab if tab in CLIENT_TABS else "timeline")


@admin_bp.route("/clients/<int:client_id>/edit", methods=["POST"])
@login_required
def client_edit(client_id):
    client = get_or_404(Client, client_id)
    data, errors = validate_client(request.form)
    if errors:
        return _render_client(client, "details", values={k: request.form.get(k, "") for k in _client_values(client)},
                              errors=errors, code=422)
    for field, value in data.items():
        setattr(client, field, value)
    client.touch()
    db.session.commit()
    flash("פרטי הלקוח נשמרו", "success")
    return redirect(url_for("admin.client_detail", client_id=client.id, tab="details"))


@admin_bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def client_delete(client_id):
    client = get_or_404(Client, client_id)
    # inquiries and quotes stay (they are detached); notes written on an inquiry stay with it,
    # notes written on the client go with it; the client's projects are deleted with it
    Note.query.filter(Note.client_id == client.id, Note.inquiry_id.is_(None)).delete(synchronize_session=False)
    Note.query.filter(Note.client_id == client.id).update({"client_id": None}, synchronize_session=False)
    db.session.expire_all()
    db.session.delete(client)
    db.session.commit()
    flash("הלקוח נמחק. הפניות וההצעות שלו נשמרו", "success")
    return redirect(url_for("admin.clients"))


# ---------------------------------------------------------------- client projects

def _project_values(project: ClientProject | None) -> dict:
    if project is None:
        return {"name": "", "service": "", "status": ProjectStatus.PROPOSAL, "brief": "", "start_date": "",
                "due_date": "", "delivered_date": "", "amount": "", "links": "", "notes": ""}
    return {"name": project.name, "service": project.service or "", "status": project.status,
            "brief": project.brief or "", "start_date": project.start_date.isoformat() if project.start_date else "",
            "due_date": project.due_date.isoformat() if project.due_date else "",
            "delivered_date": project.delivered_date.isoformat() if project.delivered_date else "",
            "amount": project.amount if project.amount is not None else "", "links": project.links or "",
            "notes": project.notes or ""}


def _render_project(client: Client, project: ClientProject | None, values: dict, errors: dict, code=200):
    attachable = [q for q in client.quotes if not project or q.project_id != project.id]
    page = render_template("admin/client_project_form.html", client=client, project=project, values=values,
                           errors=errors, attachable=attachable, statuses=ProjectStatus.ALL,
                           labels=ProjectStatus.LABELS_HE)
    return (page, code) if code != 200 else page


@admin_bp.route("/clients/<int:client_id>/projects/new", methods=["GET", "POST"])
@login_required
def client_project_new(client_id):
    client = get_or_404(Client, client_id)
    if request.method == "POST":
        data, errors = validate_client_project(request.form)
        if errors:
            return _render_project(client, None, {k: request.form.get(k, "") for k in _project_values(None)}, errors, 422)
        project = ClientProject(client_id=client.id, **data)
        db.session.add(project)
        client.touch()
        db.session.commit()
        flash("הפרויקט נוצר", "success")
        return redirect(url_for("admin.client_project", project_id=project.id))
    return _render_project(client, None, _project_values(None), {})


@admin_bp.route("/client-projects/<int:project_id>", methods=["GET", "POST"])
@login_required
def client_project(project_id):
    project = get_or_404(ClientProject, project_id)
    if request.method == "POST":
        data, errors = validate_client_project(request.form)
        if errors:
            return _render_project(project.client, project, {k: request.form.get(k, "") for k in _project_values(None)},
                                   errors, 422)
        for field, value in data.items():
            setattr(project, field, value)
        project.client.touch()
        db.session.commit()
        flash("הפרויקט נשמר", "success")
        return redirect(url_for("admin.client_project", project_id=project.id))
    return _render_project(project.client, project, _project_values(project), {})


@admin_bp.route("/client-projects/<int:project_id>/delete", methods=["POST"])
@login_required
def client_project_delete(project_id):
    project = get_or_404(ClientProject, project_id)
    client_id = project.client_id
    db.session.delete(project)     # its quotes stay on the client (project_id is cleared)
    db.session.commit()
    flash("הפרויקט נמחק. ההצעות שלו נשמרו אצל הלקוח", "success")
    return redirect(url_for("admin.client_detail", client_id=client_id, tab="projects"))


@admin_bp.route("/client-projects/<int:project_id>/quotes", methods=["POST"])
@login_required
def client_project_attach_quote(project_id):
    project = get_or_404(ClientProject, project_id)
    quote = db.session.get(PriceQuote, request.form.get("quote_id", type=int) or 0)
    if quote is None or quote.client_id != project.client_id:
        flash("אפשר לשייך לפרויקט רק הצעה של אותו לקוח", "error")
    else:
        quote.project_id = project.id
        if project.amount is None and quote.status == QuoteStatus.APPROVED:
            project.amount = quote.total
        project.client.touch()
        db.session.commit()
        flash("ההצעה שויכה לפרויקט", "success")
    return redirect(url_for("admin.client_project", project_id=project.id))


@admin_bp.route("/client-projects/<int:project_id>/quotes/<int:quote_id>/detach", methods=["POST"])
@login_required
def client_project_detach_quote(project_id, quote_id):
    project = get_or_404(ClientProject, project_id)
    quote = get_or_404(PriceQuote, quote_id)
    if quote.project_id != project.id:
        abort(404)
    quote.project_id = None
    db.session.commit()
    flash("ההצעה הוסרה מהפרויקט (היא נשארה אצל הלקוח)", "success")
    return redirect(url_for("admin.client_project", project_id=project.id))
