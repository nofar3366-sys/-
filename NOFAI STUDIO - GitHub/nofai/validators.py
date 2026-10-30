"""Server-side validation for every form (the browser checks are only a convenience)."""
import re
import unicodedata

from .extensions import db
from .models import Category, Project

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _get(form, name: str) -> str:
    return (form.get(name) or "").strip()


# ---------------------------------------------------------------- contact form (public)

INQUIRY_LIMITS = {"name": 100, "email": 160, "company": 120, "service": 120, "message": 5000}


def validate_inquiry(form) -> tuple[dict, dict]:
    """Returns (clean data, errors). Error values are i18n keys (see i18n.STRINGS)."""
    data = {k: _get(form, k) for k in INQUIRY_LIMITS}
    data["email"] = data["email"].lower()
    errors = {}
    if not data["name"]:
        errors["name"] = "err.name"
    if not EMAIL_RE.match(data["email"]):
        errors["email"] = "err.email"
    if len(data["message"]) < 10:
        errors["message"] = "err.message"
    for field, limit in INQUIRY_LIMITS.items():
        if len(data[field]) > limit and field not in errors:
            errors[field] = "err.too_long"
    data["company"] = data["company"] or None
    data["service"] = data["service"] or None
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
