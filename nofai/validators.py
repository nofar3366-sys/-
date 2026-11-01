"""Server-side validation for every form (the browser checks are only a convenience)."""
import re
import unicodedata
from datetime import date

from .extensions import db
from .models import Category, ClientSource, ClientStatus, NoteKind, Project, ProjectStatus

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _get(form, name: str) -> str:
    return (form.get(name) or "").strip()


# ---------------------------------------------------------------- contact form (public)

INQUIRY_LIMITS = {"name": 100, "email": 160, "phone": 30, "company": 120, "service": 120, "message": 5000}
PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,30}$")   # digits with an optional leading +, spaces, dashes, brackets


def validate_inquiry(form) -> tuple[dict, dict]:
    """Returns (clean data, errors). Error values are i18n keys (see i18n.STRINGS)."""
    data = {k: _get(form, k) for k in INQUIRY_LIMITS}
    data["email"] = data["email"].lower()
    errors = {}
    if not data["name"]:
        errors["name"] = "err.name"
    if data["email"] and not EMAIL_RE.match(data["email"]):      # optional, but must be valid when given
        errors["email"] = "err.email"
    if len(data["message"]) < 10:
        errors["message"] = "err.message"
    # the phone is how the visitor gets called back, so it is required
    if not (PHONE_RE.match(data["phone"]) and sum(c.isdigit() for c in data["phone"]) >= 7):
        errors["phone"] = "err.phone"
    for field, limit in INQUIRY_LIMITS.items():
        if len(data[field]) > limit and field not in errors:
            errors[field] = "err.too_long"
    data["company"] = data["company"] or None
    data["service"] = data["service"] or None
    return data, errors


# ---------------------------------------------------------------- clients, client projects, notes (admin, Hebrew)

CLIENT_LIMITS = {"name": 100, "phone": 30, "email": 160, "company": 120, "website": 200}
CLIENT_PROJECT_LIMITS = {"name": 160, "service": 120, "brief": 5000, "links": 2000, "notes": 5000}
NOTE_MAX_LENGTH = 5000
AMOUNT_MAX = 100_000_000


def _too_long(data: dict, limits: dict, errors: dict) -> None:
    for field, limit in limits.items():
        if len(data.get(field) or "") > limit and field not in errors:
            errors[field] = f"עד {limit} תווים"


def phone_key(phone: str | None) -> str:
    """Digits only, last 9: '054-912 2044' and '+972 54 912 2044' are the same number."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 9 else digits


def validate_client(form) -> tuple[dict, dict]:
    data = {k: _get(form, k) for k in CLIENT_LIMITS}
    data["email"] = data["email"].lower()
    errors = {}
    if not data["name"]:
        errors["name"] = "יש להזין שם"
    if data["phone"] and not (PHONE_RE.match(data["phone"]) and sum(c.isdigit() for c in data["phone"]) >= 7):
        errors["phone"] = "מספר טלפון לא תקין"
    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors["email"] = "כתובת אימייל לא תקינה"
    _too_long(data, CLIENT_LIMITS, errors)
    language, source, status = _get(form, "language"), _get(form, "source"), _get(form, "status")
    data["language"] = language if language in ("he", "en") else "he"
    data["source"] = source if source in ClientSource.ALL else ClientSource.OTHER
    data["status"] = status if status in ClientStatus.ALL else ClientStatus.ACTIVE
    for field in ("phone", "email", "company", "website"):
        data[field] = data[field] or None
    return data, errors


def _parse_date(raw: str, errors: dict, field: str):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors[field] = "תאריך לא תקין"
        return None


def validate_client_project(form) -> tuple[dict, dict]:
    data = {k: _get(form, k) for k in CLIENT_PROJECT_LIMITS}
    errors = {}
    if not data["name"]:
        errors["name"] = "יש להזין שם לפרויקט"
    _too_long(data, CLIENT_PROJECT_LIMITS, errors)
    status = _get(form, "status")
    data["status"] = status if status in ProjectStatus.ALL else ProjectStatus.PROPOSAL
    for field in ("start_date", "due_date", "delivered_date"):
        data[field] = _parse_date(_get(form, field), errors, field)
    raw_amount = _get(form, "amount").replace(",", "")
    data["amount"] = None
    if raw_amount:
        if raw_amount.isdigit() and int(raw_amount) <= AMOUNT_MAX:
            data["amount"] = int(raw_amount)
        else:
            errors["amount"] = "סכום לא תקין"
    # links are rendered as <a href>: only web addresses (never javascript: and the like)
    lines = [line.strip() for line in data["links"].splitlines() if line.strip()]
    if any(not re.match(r"^https?://\S+$", line, re.I) for line in lines) and "links" not in errors:
        errors["links"] = "כל קישור צריך להתחיל ב-http:// או https:// (קישור אחד בכל שורה)"
    data["links"] = "\n".join(lines) or None
    for field in ("service", "brief", "notes"):
        data[field] = data[field] or None
    return data, errors


def validate_note(form) -> tuple[dict, dict]:
    kind = _get(form, "kind")
    data = {"kind": kind if kind in NoteKind.USER_KINDS else NoteKind.NOTE, "body": _get(form, "body")}
    errors = {}
    if not data["body"]:
        errors["body"] = "יש לכתוב טקסט להערה"
    elif len(data["body"]) > NOTE_MAX_LENGTH:
        errors["body"] = f"עד {NOTE_MAX_LENGTH} תווים"
    return data, errors


# ---------------------------------------------------------------- admin forms

def slugify(text: str) -> str:
    """'Summer Eyewear 2026' -> 'summer-eyewear-2026' (Latin only; Hebrew is dropped)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:100]


def unique_slug(base: str, model, exclude_id=None) -> str:
    base = base or "item"
    slug, n = base, 2
    while True:
        query = model.query.filter_by(slug=slug)
        if exclude_id is not None:
            query = query.filter(model.id != exclude_id)
        if not query.first():
            return slug
        slug, n = f"{base}-{n}", n + 1


def validate_project(form, project=None) -> tuple[dict, dict]:
    errors = {}
    data = {
        "title_he": _get(form, "title_he"),
        "title_en": _get(form, "title_en"),
        "client": _get(form, "client") or None,
        "description_he": _get(form, "description_he") or None,
        "description_en": _get(form, "description_en") or None,
        "is_featured": form.get("is_featured") == "1",
        "is_published": form.get("is_published") == "1",
        "year": None,
        "category_id": None,
    }
    if not data["title_he"] and not data["title_en"]:
        errors["title_en"] = "יש להזין כותרת לפחות באחת השפות"
    # one language is enough; mirror it so neither column is empty
    data["title_he"] = data["title_he"] or data["title_en"]
    data["title_en"] = data["title_en"] or data["title_he"]
    for field in ("title_he", "title_en"):
        if len(data[field]) > 160:
            errors[field] = "עד 160 תווים"
    if data["client"] and len(data["client"]) > 120:
        errors["client"] = "עד 120 תווים"

    raw_year = _get(form, "year")
    if raw_year:
        if not raw_year.isdigit() or not 1990 <= int(raw_year) <= 2100:
            errors["year"] = "שנה לא תקינה"
        else:
            data["year"] = int(raw_year)

    raw_cat = _get(form, "category_id")
    if raw_cat:
        cat = db.session.get(Category, int(raw_cat)) if raw_cat.isdigit() else None
        if cat is None:
            errors["category_id"] = "קטגוריה לא קיימת"
        else:
            data["category_id"] = cat.id

    raw_slug = _get(form, "slug").lower()
    if raw_slug and not SLUG_RE.match(raw_slug):
        errors["slug"] = "רק אותיות באנגלית, ספרות ומקפים"
    data["slug"] = unique_slug(raw_slug or slugify(data["title_en"]) or "project", Project,
                               exclude_id=project.id if project else None)
    return data, errors


def validate_bilingual_name(form, limit=80, fields=("name_he", "name_en")) -> tuple[dict, dict]:
    """Category / service style forms: both languages required."""
    data, errors = {}, {}
    for field in fields:
        value = _get(form, field)
        if not value:
            errors[field] = "שדה חובה"
        elif len(value) > limit:
            errors[field] = f"עד {limit} תווים"
        data[field] = value
    return data, errors


PASSWORD_MIN_LENGTH = 10
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


def validate_new_password(new: str, confirm: str, username: str) -> tuple[str, str] | None:
    if len(new) < PASSWORD_MIN_LENGTH:
        return "new_password", f"הסיסמה צריכה להכיל לפחות {PASSWORD_MIN_LENGTH} תווים"
    if not (re.search(r"[A-Za-z֐-׿]", new) and re.search(r"\d", new)):
        return "new_password", "הסיסמה צריכה להכיל גם אותיות וגם ספרות"
    if new == DEFAULT_ADMIN_PASSWORD:
        return "new_password", "זו סיסמת ברירת המחדל. יש לבחור סיסמה אחרת"
    if username and username.lower() in new.lower():
        return "new_password", "הסיסמה לא יכולה להכיל את שם המשתמש"
    if new != confirm:
        return "confirm_password", "הסיסמאות אינן תואמות"
    return None


# ---------------------------------------------------------------- pricing quotes

QUOTE_MAX_TOTAL = 100_000_000
_JSON_LIMITS = {"depth": 4, "string": 500, "list": 100, "keys": 60}


def _clean_json(value, depth=0):
    """Plain JSON data only (objects, lists, short strings, finite numbers, booleans), bounded in size."""
    if depth > _JSON_LIMITS["depth"]:
        raise ValueError("nested too deep")
    if isinstance(value, dict):
        if len(value) > _JSON_LIMITS["keys"]:
            raise ValueError("too many keys")
        return {str(k)[:40]: _clean_json(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > _JSON_LIMITS["list"]:
            raise ValueError("list too long")
        return [_clean_json(v, depth + 1) for v in value]
    if isinstance(value, str):
        return value.strip()[:_JSON_LIMITS["string"]]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("not a finite number")
        return value
    raise ValueError("unsupported value")


def validate_quote_payload(body: dict) -> tuple[dict, str | None]:
    """The calculator's save request: {"project": {...}, "settings": {...}, "total": n, "status": s}."""
    from .models import QuoteStatus

    project, settings = body.get("project"), body.get("settings")
    if not isinstance(project, dict) or not isinstance(settings, dict):
        return {}, "נתוני ההצעה חסרים"
    status = body.get("status") or QuoteStatus.DRAFT
    if status not in QuoteStatus.ALL:
        return {}, "סטטוס לא תקין"
    total = body.get("total")
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not 0 <= total <= QUOTE_MAX_TOTAL:
        return {}, "הסכום לא תקין"
    brief = project.get("brief")   # the pasted brief may be longer than other strings
    try:
        project = _clean_json({k: v for k, v in project.items() if k != "brief"})
        settings = _clean_json(settings)
    except ValueError:
        return {}, "נתוני ההצעה לא תקינים"
    if isinstance(brief, str):
        project["brief"] = brief.strip()[:5000]
    for key, limit in (("client", 120), ("name", 160)):
        project[key] = str(project.get(key) or "")[:limit]
    return {"project": project, "settings": settings, "total": round(total), "status": status}, None