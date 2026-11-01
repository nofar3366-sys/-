"""Interface strings (navigation, buttons, form labels) in both languages.

Marketing copy that the owner edits lives in site_texts.py / the SiteText table instead.
"""
from flask import current_app, g, request

DIRECTION = {"en": "ltr", "he": "rtl"}
LANGUAGE_NAMES = {"en": "English", "he": "עברית"}

STRINGS = {
    # navigation
    "nav.home": {"en": "Home", "he": "בית"},
    "nav.about": {"en": "About", "he": "מי אני"},
    "nav.work": {"en": "Work", "he": "עבודות"},
    "nav.contact": {"en": "Contact", "he": "צור קשר"},
    "nav.menu": {"en": "Menu", "he": "תפריט"},
    "nav.close": {"en": "Close", "he": "סגירה"},
    "nav.switch_lang": {"en": "עברית", "he": "English"},
    "nav.skip": {"en": "Skip to content", "he": "דילוג לתוכן"},
    # home
    "home.scroll": {"en": "Scroll", "he": "גללו"},
    "home.selected": {"en": "Selected work", "he": "עבודות נבחרות"},
    "home.view_all": {"en": "View all work", "he": "לכל העבודות"},
    "home.services": {"en": "What I do", "he": "מה אני עושה"},
    "home.cta_title": {"en": "Let's create something together", "he": "בואו ניצור משהו יחד"},
    "home.cta_button": {"en": "Start a project", "he": "לפתיחת פרויקט"},
    # about
    "about.services": {"en": "Services", "he": "שירותים"},
    "about.process": {"en": "Process", "he": "תהליך העבודה"},
    "about.tools": {"en": "Tools", "he": "כלים"},
    # work
    "work.title": {"en": "Work", "he": "עבודות"},
    "work.all": {"en": "All", "he": "הכל"},
    "work.filter": {"en": "Filter by category", "he": "סינון לפי קטגוריה"},
    "work.empty": {"en": "New work is on its way.", "he": "עבודות חדשות בדרך."},
    "work.images": {"en": "images", "he": "תמונות"},
    "work.open": {"en": "Open", "he": "לצפייה"},
    "work.client": {"en": "Client", "he": "לקוח"},
    "work.year": {"en": "Year", "he": "שנה"},
    # lightbox
    "lb.prev": {"en": "Previous image", "he": "התמונה הקודמת"},
    "lb.next": {"en": "Next image", "he": "התמונה הבאה"},
    "lb.close": {"en": "Close gallery", "he": "סגירת הגלריה"},
    "lb.of": {"en": "of", "he": "מתוך"},
    # contact
    "contact.title": {"en": "Contact", "he": "צור קשר"},
    "contact.name": {"en": "Name", "he": "שם"},
    "contact.email": {"en": "Email", "he": "אימייל"},
    "contact.phone": {"en": "Phone", "he": "טלפון"},
    "contact.company": {"en": "Brand / company", "he": "מותג / חברה"},
    "contact.service": {"en": "What are you looking for?", "he": "מה מעניין אותך?"},
    "contact.service_any": {"en": "Not sure yet", "he": "עוד לא בטוח/ה"},
    "contact.message": {"en": "Tell me about your project", "he": "ספרו לי על הפרויקט"},
    "contact.optional": {"en": "optional", "he": "לא חובה"},
    "contact.send": {"en": "Send message", "he": "שליחה"},
    "contact.sending": {"en": "Sending…", "he": "שולח…"},
    "contact.success_title": {"en": "Thank you", "he": "תודה"},
    "contact.success": {"en": "Your message is on its way. I'll get back to you soon.",
                        "he": "ההודעה נשלחה. אחזור אליכם בהקדם."},
    "contact.fix": {"en": "Please check the highlighted fields", "he": "נא לבדוק את השדות המסומנים"},
    "contact.direct": {"en": "Or write directly", "he": "או ישירות"},
    "contact.expired": {"en": "The form expired. Please refresh the page and try again.",
                        "he": "תוקף הטופס פג. נא לרענן את הדף ולנסות שוב."},
    "contact.offline": {"en": "Couldn't reach the server. Please try again.",
                        "he": "אין חיבור לשרת. נא לנסות שוב."},
    # validation
    "err.name": {"en": "Please enter your name", "he": "נא להזין שם"},
    "err.email": {"en": "Please enter a valid email address", "he": "נא להזין כתובת אימייל תקינה"},
    "err.phone": {"en": "Please enter a valid phone number", "he": "נא להזין מספר טלפון תקין"},
    "err.message": {"en": "Please write a few words about your project", "he": "נא לכתוב כמה מילים על הפרויקט"},
    "err.too_long": {"en": "This is too long", "he": "הטקסט ארוך מדי"},
    # 404 / footer
    "404.title": {"en": "This page drifted away", "he": "הדף הזה התרחק"},
    "404.text": {"en": "The page you're looking for doesn't exist.", "he": "הדף שחיפשת לא קיים."},
    "404.home": {"en": "Back home", "he": "חזרה לדף הבית"},
    "footer.rights": {"en": "All rights reserved", "he": "כל הזכויות שמורות"},
}


def t(key: str) -> str:
    """Interface string in the current page language (the key itself if missing)."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(g.get("lang", "en")) or entry.get("en", key)


def best_language() -> str:
    """Language for a visitor arriving at '/': their browser preference, else the default."""
    languages = current_app.config["LANGUAGES"]
    return request.accept_languages.best_match(languages) or current_app.config["DEFAULT_LANGUAGE"]
