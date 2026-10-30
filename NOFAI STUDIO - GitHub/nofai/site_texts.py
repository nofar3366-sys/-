"""Registry of editable site copy.

Each entry defines a key used by the templates, how the admin form labels it, and
starter copy. Values saved in the SiteText table override the starter copy.

NOTE: the starter copy is a DRAFT written for the project. The owner replaces it
from the admin (טקסטים באתר).
"""
from dataclasses import dataclass

from flask import g

ABOUT_IMAGE_KEY = "about_image"   # SiteText row whose value_en is the portrait's storage filename


@dataclass(frozen=True)
class TextField:
    key: str
    label: str              # Hebrew label in the admin
    group: str              # admin section
    default_en: str
    default_he: str
    multiline: bool = False
    translated: bool = True  # False = one value for both languages (e-mail, handles)


FIELDS = [
    # ---- home
    TextField("hero_tagline", "שורת תיאור מתחת ללוגו", "עמוד הבית",
              "AI Creative Studio", "סטודיו קריאייטיב AI"),
    TextField("hero_intro", "משפט פתיחה", "עמוד הבית",
              "Campaign imagery for brands. Created with artificial intelligence, directed by a human eye.",
              "ויז'ואלים לקמפיינים של מותגים. נוצרים בבינה מלאכותית, בהכוונה של עין אנושית.",
              multiline=True),
    TextField("statement", "משפט המותג (באמצע העמוד)", "עמוד הבית",
              "Every image begins with a feeling, and ends as a brand.",
              "כל תמונה מתחילה ברגש, ונגמרת כמותג.", multiline=True),
    TextField("quote", "ציטוט על רקע תמונה", "עמוד הבית",
              "Imagination is the only limit. The rest is direction.",
              "הדמיון הוא הגבול היחיד. כל השאר זה הכוונה.", multiline=True),

    # ---- about
    TextField("about_title", "כותרת", "מי אני", "Hi, I'm Nofar", "היי, אני נופר"),
    TextField("about_lead", "פסקת פתיחה", "מי אני",
              "I'm the founder of NOFAI, a creative studio that turns ideas into campaign imagery using AI.",
              "אני המייסדת של NOFAI, סטודיו קריאייטיב שהופך רעיונות לוויז'ואלים לקמפיינים בעזרת בינה מלאכותית.",
              multiline=True),
    TextField("about_story", "הסיפור שלי", "מי אני",
              "I work with brands that want striking visuals without the cost and logistics of a full production. "
              "Every project starts with understanding the brand: its audience, its mood and the story it wants "
              "to tell. From there I direct each image until it feels real, intentional and unmistakably yours.",
              "אני עובדת עם מותגים שרוצים ויז'ואלים מרשימים בלי העלויות והלוגיסטיקה של הפקה מלאה. "
              "כל פרויקט מתחיל בהבנת המותג: הקהל, האווירה והסיפור שהוא רוצה לספר. משם אני מכוונת כל תמונה "
              "עד שהיא מרגישה אמיתית, מכוונת, ושלכם לגמרי.",
              multiline=True),
    TextField("process_1", "שלב 1 בתהליך", "מי אני", "Brief: we talk about the brand, the product and the goal",
              "בריף: מדברים על המותג, המוצר והמטרה"),
    TextField("process_2", "שלב 2 בתהליך", "מי אני", "Concept: moodboard, styling and visual direction",
              "קונספט: לוח השראה, סטיילינג וכיוון ויזואלי"),
    TextField("process_3", "שלב 3 בתהליך", "מי אני", "Creation: generating, refining and retouching every image",
              "יצירה: יצירה, דיוק וריטוש של כל תמונה"),
    TextField("process_4", "שלב 4 בתהליך", "מי אני", "Delivery: final files ready for web, social and print",
              "מסירה: קבצים סופיים לאתר, לרשתות ולדפוס"),
    TextField("tools", "כלים (מופרדים בפסיקים)", "מי אני",
              "Midjourney, Photoshop, Lightroom, Runway", "Midjourney, Photoshop, Lightroom, Runway",
              translated=False),

    # ---- contact
    TextField("contact_title", "כותרת", "צור קשר", "Let's talk", "בואו נדבר"),
    TextField("contact_intro", "טקסט פתיחה", "צור קשר",
              "Have a product, a campaign or just an idea? Tell me about it and I'll get back to you within two business days.",
              "יש לכם מוצר, קמפיין או רק רעיון? ספרו לי עליו, ואחזור אליכם תוך שני ימי עסקים.",
              multiline=True),
    TextField("contact_email", "אימייל להצגה באתר", "פרטי קשר", "hello@nofai.studio", "",
              translated=False),
    TextField("instagram", "שם משתמש באינסטגרם (בלי @)", "פרטי קשר", "nofaistudio", "",
              translated=False),
]

FIELDS_BY_KEY = {f.key: f for f in FIELDS}


def resolve(key: str, stored, lang: str | None = None) -> str:
    """The value to display: saved text in the page language, else the other language,
    else the starter copy."""
    field = FIELDS_BY_KEY[key]
    lang = lang or g.get("lang", "en")
    if not field.translated:
        return (stored.value_en if stored and stored.value_en else field.default_en)
    other = "he" if lang == "en" else "en"
    if stored:
        value = getattr(stored, f"value_{lang}") or getattr(stored, f"value_{other}")
        if value:
            return value
    return getattr(field, f"default_{lang}") or getattr(field, f"default_{other}")
