"""Back-office project pricing: saved quotes + the calculator page.
Registered on the admin blueprint (same /admin prefix and login guard).
The arithmetic runs in the browser (static/js/pricing.js); the server stores what was priced."""
from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from ..extensions import db
from ..models import Client, ClientProject, Inquiry, PriceQuote, PricingSettings, QuoteStatus
from ..validators import validate_quote_payload
from .admin import admin_bp, get_or_404, safe_next

MAX_PAYLOAD_BYTES = 200_000


def _json_body() -> dict:
    if request.content_length and request.content_length > MAX_PAYLOAD_BYTES:
        abort(413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400)
    return body


@admin_bp.route("/pricing")
@login_required
def pricing():
    status = request.args.get("status", "")
    query = PriceQuote.query
    if status in QuoteStatus.ALL:
        query = query.filter_by(status=status)
    else:
        status = ""
    counts = dict(db.session.query(PriceQuote.status, db.func.count(PriceQuote.id)).group_by(PriceQuote.status).all())
    return render_template("admin/pricing.html", quotes=query.order_by(PriceQuote.updated_at.desc()).all(),
                           status=status, counts=counts, statuses=QuoteStatus.ALL, labels=QuoteStatus.LABELS_HE)


def _render_calculator(quote: PriceQuote | None, inquiry: Inquiry | None = None, client: Client | None = None,
                       project: ClientProject | None = None):
    return render_template("admin/pricing_form.html", quote=quote, inquiry=inquiry or (quote.inquiry if quote else None),
                           client=client or (quote.owner if quote else None),
                           project=project or (quote.project if quote else None),
                           defaults=PricingSettings.current().payload,
                           statuses=QuoteStatus.ALL, labels=QuoteStatus.LABELS_HE)


def _save(quote: PriceQuote):
    clean, error = validate_quote_payload(_json_body())
    if error:
        return jsonify(ok=False, error=error), 422
    project = clean["project"]
    quote.client = project.get("client") or None
    quote.name = project.get("name") or None
    quote.status = clean["status"]
    quote.total = clean["total"]
    quote.payload = {"project": project, "settings": clean["settings"]}
    db.session.add(quote)
    if quote.client_id:
        linked = db.session.get(Client, quote.client_id)
        if linked:
            linked.touch()
    db.session.commit()
    return jsonify(ok=True, id=quote.id, url=url_for("admin.pricing_edit", quote_id=quote.id))


@admin_bp.route("/pricing/new", methods=["GET", "POST"])
@login_required
def pricing_new():
    inquiry = db.session.get(Inquiry, request.args.get("inquiry", type=int) or 0)
    client = db.session.get(Client, request.args.get("client", type=int) or 0)
    if client is None and inquiry is not None and inquiry.client_id:
        client = db.session.get(Client, inquiry.client_id)     # a converted inquiry's quotes belong to its client
    project = db.session.get(ClientProject, request.args.get("project", type=int) or 0)
    if project is not None and (client is None or project.client_id != client.id):
        project = None                                          # a project can only hold its own client's quotes
    if request.method == "POST":
        return _save(PriceQuote(inquiry_id=inquiry.id if inquiry else None, client_id=client.id if client else None,
                                project_id=project.id if project else None))
    return _render_calculator(None, inquiry, client, project)


@admin_bp.route("/pricing/<int:quote_id>", methods=["GET", "POST"])
@login_required
def pricing_edit(quote_id):
    quote = get_or_404(PriceQuote, quote_id)
    if request.method == "POST":
        return _save(quote)
    return _render_calculator(quote)


@admin_bp.route("/pricing/defaults", methods=["POST"])
@login_required
def pricing_defaults():
    settings = _json_body().get("settings")
    if not isinstance(settings, dict):
        return jsonify(ok=False, error="הגדרות לא תקינות"), 422
    clean, error = validate_quote_payload({"project": {}, "settings": settings, "total": 0, "status": QuoteStatus.DRAFT})
    if error:
        return jsonify(ok=False, error=error), 422
    PricingSettings.current().payload = clean["settings"]
    db.session.commit()
    return jsonify(ok=True)


@admin_bp.route("/pricing/<int:quote_id>/duplicate", methods=["POST"])
@login_required
def pricing_duplicate(quote_id):
    source = get_or_404(PriceQuote, quote_id)
    payload = source.payload
    project = payload.get("project", {})
    project["name"] = f"{project.get('name') or ''} (עותק)".strip()
    copy = PriceQuote(client=source.client, name=project["name"], total=source.total, inquiry_id=source.inquiry_id,
                      client_id=source.client_id, project_id=source.project_id)
    copy.payload = {**payload, "project": project}
    db.session.add(copy)
    db.session.commit()
    flash("נוצר עותק של ההצעה", "success")
    return redirect(url_for("admin.pricing_edit", quote_id=copy.id))


@admin_bp.route("/pricing/<int:quote_id>/delete", methods=["POST"])
@login_required
def pricing_delete(quote_id):
    quote = get_or_404(PriceQuote, quote_id)
    db.session.delete(quote)
    db.session.commit()
    flash("ההצעה נמחקה", "success")
    return redirect(safe_next(url_for("admin.pricing")))
