from flask import g, has_request_context


def current_lang() -> str:
    return g.get("lang", "en") if has_request_context() else "en"


class Localized:
    """Mixin for models with `<field>_he` / `<field>_en` columns.

    obj.tr("title") returns the value in the current page language, falling back
    to the other language when that translation hasn't been written yet.
    """

    def tr(self, field: str, lang: str | None = None) -> str:
        lang = lang or current_lang()
        other = "he" if lang == "en" else "en"
        return getattr(self, f"{field}_{lang}", None) or getattr(self, f"{field}_{other}", None) or ""
