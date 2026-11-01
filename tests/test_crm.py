"""Back-office CRM: notes, inquiry -> client conversion, clients, client projects, quotes."""
import pytest

from nofai.extensions import db
from nofai.models import (Client, ClientProject, Inquiry, InquiryStatus, Note, NoteKind, PriceQuote, ProjectStatus,
                          QuoteStatus)

QUOTE = {"project": {"client": "La Fam", "name": "Orchard"}, "settings": {}, "total": 12000, "status": "approved"}


def make_inquiry(**kw):
    inquiry = Inquiry(**{"name": "Dana", "phone": "054-912 2044", "email": "dana@brand.com", "company": "La Fam",
                         "service": "Campaigns", "message": "We'd love a summer campaign for our sunglasses.",
                         "language": "he", **kw})
    db.session.add(inquiry)
    db.session.commit()
    return inquiry


def make_client(**kw):
    client = Client(**{"name": "Noa", "phone": "050-111 2222", "email": "noa@x.com", "company": "Noa Studio", **kw})
    db.session.add(client)
    db.session.commit()
    return client


def make_quote(inquiry=None, client=None, status=QuoteStatus.DRAFT, total=5000, **kw):
    quote = PriceQuote(client="La Fam", name="Q", total=total, status=status,
                       inquiry_id=inquiry.id if inquiry else None, client_id=client.id if client else None, **kw)
    db.session.add(quote)
    db.session.commit()
    return quote


# ---------------------------------------------------------------- access

@pytest.mark.parametrize("method,url", [
    ("get", "/admin/clients"), ("get", "/admin/clients/new"), ("get", "/admin/clients/1"),
    ("get", "/admin/inquiries/1/convert"), ("post", "/admin/inquiries/1/notes"), ("post", "/admin/notes/1/delete"),
    ("get", "/admin/client-projects/1"), ("post", "/admin/clients/1/delete"),
])
def test_crm_requires_login(client, method, url):
    r = getattr(client, method)(url)
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


def test_sidebar_has_clients_link(admin_client):
    html = admin_client.get("/admin/inquiries").get_data(as_text=True)
    assert 'href="/admin/clients"' in html


# ---------------------------------------------------------------- notes

def test_inquiry_notes_add_edit_delete(admin_client):
    inquiry = make_inquiry()
    r = admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "call", "body": "Called, asked for a quote"})
    assert r.status_code == 302
    note = Note.query.one()
    assert (note.kind, note.body, note.inquiry_id, note.client_id) == ("call", "Called, asked for a quote", inquiry.id, None)
    assert "Called, asked for a quote" in admin_client.get(f"/admin/inquiries/{inquiry.id}").get_data(as_text=True)

    admin_client.post(f"/admin/notes/{note.id}/edit", data={"kind": "meeting", "body": "Met on Monday"})
    db.session.refresh(note)
    assert (note.kind, note.body) == ("meeting", "Met on Monday")

    admin_client.post(f"/admin/notes/{note.id}/delete")
    assert Note.query.count() == 0


def test_empty_or_bad_note_is_rejected(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "note", "body": "   "})
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "note", "body": "x" * 5001})
    assert Note.query.count() == 0
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "bogus", "body": "ok"})
    assert Note.query.one().kind == NoteKind.NOTE          # unknown type falls back to a plain note


def test_system_notes_cannot_be_edited_or_deleted(admin_client):
    inquiry = make_inquiry()
    note = Note(kind=NoteKind.SYSTEM, body="auto", inquiry_id=inquiry.id)
    db.session.add(note)
    db.session.commit()
    admin_client.post(f"/admin/notes/{note.id}/edit", data={"kind": "note", "body": "changed"})
    admin_client.post(f"/admin/notes/{note.id}/delete")
    db.session.refresh(note)
    assert (note.kind, note.body) == (NoteKind.SYSTEM, "auto")


def test_notes_next_redirect_stays_on_site(admin_client):
    inquiry = make_inquiry()
    note = Note(kind=NoteKind.NOTE, body="n", inquiry_id=inquiry.id)
    db.session.add(note)
    db.session.commit()
    r = admin_client.post(f"/admin/notes/{note.id}/edit", data={"kind": "note", "body": "m", "next": "https://evil.example/"})
    assert r.headers["Location"].startswith("/admin/")


# ---------------------------------------------------------------- inquiry -> client

def test_convert_creates_client_and_carries_history(admin_client):
    inquiry = make_inquiry()
    note = Note(kind=NoteKind.CALL, body="Spoke on the phone", inquiry_id=inquiry.id)
    db.session.add(note)
    quote = make_quote(inquiry=inquiry, status=QuoteStatus.SENT)
    db.session.commit()

    page = admin_client.get(f"/admin/inquiries/{inquiry.id}/convert").get_data(as_text=True)
    assert 'value="Dana"' in page and 'value="054-912 2044"' in page and 'value="La Fam"' in page   # prefilled

    r = admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={
        "action": "new", "name": "Dana", "phone": "054-912 2044", "email": "Dana@Brand.com", "company": "La Fam",
        "language": "he", "source": "site", "status": "active"})
    client = Client.query.one()
    assert r.status_code == 302 and r.headers["Location"] == f"/admin/clients/{client.id}"
    assert (client.name, client.email, client.company, client.source, client.status) == ("Dana", "dana@brand.com", "La Fam", "site", "active")

    db.session.refresh(inquiry)
    db.session.refresh(note)
    db.session.refresh(quote)
    assert inquiry.client_id == client.id and inquiry.status == InquiryStatus.REPLIED    # a new lead counts as handled
    assert note.client_id == client.id and quote.client_id == client.id
    system = Note.query.filter_by(kind=NoteKind.SYSTEM).one()
    assert system.client_id == client.id and system.inquiry_id == inquiry.id

    history = admin_client.get(f"/admin/clients/{client.id}").get_data(as_text=True)
    assert "Spoke on the phone" in history and "sunglasses" in history and "הומרה ללקוח" in history
    assert "badge-client" in admin_client.get(f"/admin/inquiries/{inquiry.id}").get_data(as_text=True)
    assert f"/admin/clients/{client.id}" in admin_client.get(f"/admin/inquiries/{inquiry.id}/convert").headers["Location"]


def test_convert_can_open_a_first_project_with_the_quotes(admin_client):
    inquiry = make_inquiry()
    approved = make_quote(inquiry=inquiry, status=QuoteStatus.APPROVED, total=9000)
    declined = make_quote(inquiry=inquiry, status=QuoteStatus.DECLINED, total=4000)
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={
        "action": "new", "name": "Dana", "create_project": "1", "project_name": "Orchard campaign"})
    project = ClientProject.query.one()
    assert (project.name, project.status, project.amount, project.service) == (
        "Orchard campaign", ProjectStatus.IN_PROGRESS, 9000, "Campaigns")
    assert "sunglasses" in project.brief
    db.session.refresh(approved)
    db.session.refresh(declined)
    assert approved.project_id == project.id and declined.project_id is None


def test_convert_without_project_by_default(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana"})
    assert Client.query.count() == 1 and ClientProject.query.count() == 0


def test_convert_validation_errors(admin_client):
    inquiry = make_inquiry()
    r = admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "", "phone": "abc", "email": "x"})
    assert r.status_code == 422
    html = r.get_data(as_text=True)
    assert "יש להזין שם" in html and "מספר טלפון לא תקין" in html and "כתובת אימייל לא תקינה" in html
    assert Client.query.count() == 0 and db.session.get(Inquiry, inquiry.id).client_id is None


def test_convert_suggests_duplicates_by_phone_and_email(admin_client):
    existing = make_client(name="Dana B", phone="+972 54 912 2044", email="other@x.com")
    other = make_client(name="Someone", phone="052-000 0000", email="DANA@brand.com")
    unrelated = make_client(name="Unrelated", phone="03-123 4567", email="u@x.com")
    inquiry = make_inquiry(phone="054-912 2044", email="dana@brand.com")
    page = admin_client.get(f"/admin/inquiries/{inquiry.id}/convert").get_data(as_text=True)
    assert "נמצא לקוח דומה" in page
    assert f'value="{existing.id}"' in page and f'value="{other.id}"' in page
    section = page.split("או ליצור לקוח חדש")[0]
    assert f"/admin/clients/{unrelated.id}" not in section          # not offered as a match


def test_convert_attach_to_existing_client(admin_client):
    existing = make_client()
    inquiry = make_inquiry()
    quote = make_quote(inquiry=inquiry)
    r = admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "existing", "client_id": existing.id})
    assert r.headers["Location"] == f"/admin/clients/{existing.id}"
    assert Client.query.count() == 1
    db.session.refresh(inquiry)
    db.session.refresh(quote)
    assert inquiry.client_id == existing.id and quote.client_id == existing.id
    r = admin_client.post(f"/admin/inquiries/{make_inquiry().id}/convert", data={"action": "existing", "client_id": 9999})
    assert r.status_code == 200 and Client.query.count() == 1      # unknown client: nothing happens


def test_converted_inquiry_cannot_be_converted_twice(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana"})
    r = admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana again"})
    assert r.status_code == 302 and Client.query.count() == 1


def test_new_quote_from_converted_inquiry_goes_to_its_client(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana"})
    client = Client.query.one()
    r = admin_client.post(f"/admin/pricing/new?inquiry={inquiry.id}", json=QUOTE)
    assert r.get_json()["ok"]
    quote = PriceQuote.query.one()
    assert (quote.inquiry_id, quote.client_id) == (inquiry.id, client.id)


# ---------------------------------------------------------------- clients

def test_clients_list_search_and_filter(admin_client):
    make_client(name="Noa", company="Noa Studio", phone="050-111 2222", email="noa@x.com")
    make_client(name="Ron", company=None, phone="052-333 4444", email="ron@y.com", status="inactive")
    html = admin_client.get("/admin/clients").get_data(as_text=True)
    assert "Noa Studio" in html and "Ron" in html
    html = admin_client.get("/admin/clients?q=noa").get_data(as_text=True)
    assert "Noa Studio" in html and "ron@y.com" not in html
    assert "ron@y.com" in admin_client.get("/admin/clients?q=333").get_data(as_text=True)      # by part of the phone
    html = admin_client.get("/admin/clients?status=inactive").get_data(as_text=True)
    assert "ron@y.com" in html and "noa@x.com" not in html
    assert "noa@x.com" not in admin_client.get("/admin/clients?q=%25").get_data(as_text=True)   # % is literal, not a wildcard


def test_client_create_edit_validation(admin_client):
    r = admin_client.post("/admin/clients/new", data={"name": "", "phone": "12", "email": "bad"})
    assert r.status_code == 422 and Client.query.count() == 0
    r = admin_client.post("/admin/clients/new", data={"name": "Gal", "phone": "053-555 6666", "email": "GAL@x.com",
                                                      "language": "en", "source": "referral", "status": "waiting"})
    client = Client.query.one()
    assert r.headers["Location"] == f"/admin/clients/{client.id}"
    assert (client.email, client.language, client.source, client.status) == ("gal@x.com", "en", "referral", "waiting")

    r = admin_client.post(f"/admin/clients/{client.id}/edit", data={"name": "Gal Levi", "company": "Gal Co", "status": "active"})
    db.session.refresh(client)
    assert (client.name, client.company, client.status, client.phone) == ("Gal Levi", "Gal Co", "active", None)
    r = admin_client.post(f"/admin/clients/{client.id}/edit", data={"name": ""})
    assert r.status_code == 422


def test_client_pages_render_every_tab(admin_client):
    client = make_client()
    project = ClientProject(client_id=client.id, name="Shoot", status=ProjectStatus.IN_PROGRESS)
    db.session.add(project)
    make_quote(client=client)
    for tab in ("timeline", "projects", "quotes", "details", "bogus"):
        assert admin_client.get(f"/admin/clients/{client.id}?tab={tab}").status_code == 200, tab
    assert admin_client.get("/admin/clients/9999").status_code == 404


def test_client_note_shows_in_history(admin_client):
    client = make_client()
    admin_client.post(f"/admin/clients/{client.id}/notes", data={"kind": "meeting", "body": "Kickoff on Sunday"})
    note = Note.query.one()
    assert (note.client_id, note.inquiry_id) == (client.id, None)
    assert "Kickoff on Sunday" in admin_client.get(f"/admin/clients/{client.id}").get_data(as_text=True)


def test_delete_client_keeps_inquiry_quotes_and_inquiry_notes(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "note", "body": "from the inquiry"})
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana", "create_project": "1"})
    client = Client.query.one()
    quote = make_quote(inquiry=inquiry, client=client)
    admin_client.post(f"/admin/clients/{client.id}/notes", data={"kind": "note", "body": "only on the client"})

    r = admin_client.post(f"/admin/clients/{client.id}/delete")
    assert r.headers["Location"] == "/admin/clients"
    assert Client.query.count() == 0 and ClientProject.query.count() == 0       # its projects go with it
    db.session.expire_all()
    inquiry = db.session.get(Inquiry, inquiry.id)
    assert inquiry is not None and inquiry.client_id is None
    assert db.session.get(PriceQuote, quote.id).client_id is None
    bodies = {n.body for n in Note.query.all()}
    assert "from the inquiry" in bodies and "only on the client" not in bodies


def test_deleting_a_converted_inquiry_keeps_the_notes_in_the_client_history(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "note", "body": "keep me"})
    admin_client.post(f"/admin/inquiries/{inquiry.id}/convert", data={"action": "new", "name": "Dana"})
    client = Client.query.one()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/delete")
    assert Inquiry.query.count() == 0
    assert "keep me" in admin_client.get(f"/admin/clients/{client.id}").get_data(as_text=True)


def test_deleting_an_unconverted_inquiry_deletes_its_notes(admin_client):
    inquiry = make_inquiry()
    admin_client.post(f"/admin/inquiries/{inquiry.id}/notes", data={"kind": "note", "body": "gone"})
    admin_client.post(f"/admin/inquiries/{inquiry.id}/delete")
    assert Note.query.count() == 0


# ---------------------------------------------------------------- client projects

def test_project_create_update_delete(admin_client):
    client = make_client()
    r = admin_client.post(f"/admin/clients/{client.id}/projects/new", data={
        "name": "Perfume campaign", "service": "Campaigns", "status": "in_progress", "amount": "12,000",
        "start_date": "2026-11-01", "due_date": "2026-12-01", "links": "https://drive.example/a\nhttp://x.example/b",
        "brief": "Orchard shoot", "notes": "n"})
    project = ClientProject.query.one()
    assert r.headers["Location"] == f"/admin/client-projects/{project.id}"
    assert (project.amount, project.status, project.start_date.isoformat(), project.link_list) == (
        12000, "in_progress", "2026-11-01", ["https://drive.example/a", "http://x.example/b"])
    assert "Perfume campaign" in admin_client.get(f"/admin/clients/{client.id}?tab=projects").get_data(as_text=True)

    admin_client.post(f"/admin/client-projects/{project.id}", data={"name": "Perfume campaign v2", "status": "delivered",
                                                                    "delivered_date": "2026-12-02"})
    db.session.refresh(project)
    assert (project.name, project.status, project.delivered_date.isoformat(), project.amount) == (
        "Perfume campaign v2", "delivered", "2026-12-02", None)
    assert "פרויקט נמסר" in admin_client.get(f"/admin/clients/{client.id}").get_data(as_text=True)

    admin_client.post(f"/admin/client-projects/{project.id}/delete")
    assert ClientProject.query.count() == 0


def test_project_validation(admin_client):
    client = make_client()
    r = admin_client.post(f"/admin/clients/{client.id}/projects/new", data={
        "name": "", "amount": "-5", "start_date": "31/12/2026", "links": "javascript:alert(1)"})
    html = r.get_data(as_text=True)
    assert r.status_code == 422 and ClientProject.query.count() == 0
    assert "יש להזין שם לפרויקט" in html and "סכום לא תקין" in html and "תאריך לא תקין" in html and "http://" in html
    r = admin_client.post(f"/admin/clients/{client.id}/projects/new", data={"name": "P", "status": "nonsense"})
    assert ClientProject.query.one().status == ProjectStatus.PROPOSAL         # unknown status falls back


def test_project_quotes_attach_detach_and_keep_after_delete(admin_client):
    client, other = make_client(), make_client(name="Other", phone="050-999 8888", email="o@x.com")
    project = ClientProject(client_id=client.id, name="P")
    db.session.add(project)
    db.session.commit()
    mine = make_quote(client=client, status=QuoteStatus.APPROVED, total=7000)
    theirs = make_quote(client=other)

    admin_client.post(f"/admin/client-projects/{project.id}/quotes", data={"quote_id": theirs.id})
    db.session.refresh(theirs)
    assert theirs.project_id is None                                          # another client's quote: refused
    admin_client.post(f"/admin/client-projects/{project.id}/quotes", data={"quote_id": mine.id})
    db.session.refresh(mine)
    db.session.refresh(project)
    assert mine.project_id == project.id and project.amount == 7000            # the approved quote sets the price

    admin_client.post(f"/admin/client-projects/{project.id}/quotes/{mine.id}/detach")
    db.session.refresh(mine)
    assert mine.project_id is None and mine.client_id == client.id
    admin_client.post(f"/admin/client-projects/{project.id}/quotes", data={"quote_id": mine.id})
    admin_client.post(f"/admin/client-projects/{project.id}/delete")
    db.session.refresh(mine)
    assert mine.project_id is None and mine.client_id == client.id and db.session.get(PriceQuote, mine.id)


def test_new_quote_for_a_client_and_project(admin_client):
    client, other = make_client(), make_client(name="Other", phone="050-999 8888", email="o@x.com")
    project = ClientProject(client_id=client.id, name="P")
    foreign = ClientProject(client_id=other.id, name="F")
    db.session.add_all([project, foreign])
    db.session.commit()

    page = admin_client.get(f"/admin/pricing/new?client={client.id}&project={project.id}").get_data(as_text=True)
    assert f'data-prefill-client="{client.display_name}"' in page
    assert f"client={client.id}" in page and f"project={project.id}" in page
    admin_client.post(f"/admin/pricing/new?client={client.id}&project={project.id}", json=QUOTE)
    admin_client.post(f"/admin/pricing/new?client={client.id}&project={foreign.id}", json=QUOTE)   # not this client's project
    first, second = PriceQuote.query.order_by(PriceQuote.id).all()
    assert (first.client_id, first.project_id) == (client.id, project.id)
    assert (second.client_id, second.project_id) == (client.id, None)
    assert admin_client.get(f"/admin/pricing/{first.id}").status_code == 200
    assert "La Fam" in admin_client.get(f"/admin/clients/{client.id}?tab=quotes").get_data(as_text=True)
