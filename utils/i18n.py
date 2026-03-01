"""
i18n Translation Engine — Sprint 26
Loads language JSON files, provides t() function for templates.
Supports: en, hi, ta, te, mr, bn, kn, gu, ur
"""
import json
import os
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

# Global language cache
_translations: Dict[str, Dict] = {}
_default_lang = "en"
_supported_langs = []
_lang_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "lang")


def init_i18n(lang_dir: str = None, default_lang: str = "en"):
    """Initialize i18n system — call once at app startup."""
    global _lang_dir, _default_lang, _translations, _supported_langs

    if lang_dir:
        _lang_dir = lang_dir
    _default_lang = default_lang

    if not os.path.exists(_lang_dir):
        os.makedirs(_lang_dir, exist_ok=True)
        logger.warning(f"Created language directory: {_lang_dir}")
        return

    # Load all language files
    for filename in os.listdir(_lang_dir):
        if filename.endswith(".json"):
            lang_code = filename.replace(".json", "")
            filepath = os.path.join(_lang_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    _translations[lang_code] = json.load(f)
                _supported_langs.append({
                    "code": lang_code,
                    "name": _translations[lang_code].get("_meta", {}).get("name", lang_code),
                    "native": _translations[lang_code].get("_meta", {}).get("native", lang_code),
                    "direction": _translations[lang_code].get("_meta", {}).get("direction", "ltr"),
                })
                logger.info(f"Loaded language: {lang_code} ({filepath})")
            except Exception as e:
                logger.error(f"Failed to load language file {filepath}: {e}")

    if not _translations:
        logger.warning("No language files found. i18n will return keys as-is.")


def get_supported_languages() -> list:
    """Return list of supported languages with metadata."""
    return _supported_langs


def get_translation(key: str, lang: str = None, **kwargs) -> str:
    """
    Get translated string by dot-notation key.
    
    Examples:
        t("common.save")           → "Save" (en) / "सहेजें" (hi)
        t("student.name")          → "Student Name"
        t("fee.due_msg", name="Rahul", amount="5000")
            → "Fee of ₹5000 is due for Rahul"
    
    Falls back: requested_lang → default_lang → key itself
    """
    lang = lang or _default_lang

    # Try requested language
    value = _resolve_key(key, lang)

    # Fallback to default language
    if value is None and lang != _default_lang:
        value = _resolve_key(key, _default_lang)

    # Fallback to key itself
    if value is None:
        return key

    # Interpolate variables
    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return value


def _resolve_key(key: str, lang: str) -> Optional[str]:
    """Resolve a dot-notation key from language dict."""
    data = _translations.get(lang)
    if not data:
        return None

    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current if isinstance(current, str) else None


def get_all_keys_for_js(lang: str = None) -> dict:
    """
    Return flattened dict of all translations for JS.
    Used to inject into base.html as window.T = {...}
    """
    lang = lang or _default_lang
    data = _translations.get(lang, {})
    flat = {}
    _flatten(data, "", flat)
    return flat


def _flatten(d: dict, prefix: str, result: dict):
    """Flatten nested dict with dot notation."""
    for k, v in d.items():
        if k == "_meta":
            continue
        full_key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(v, f"{full_key}.", result)
        else:
            result[full_key] = v


# ═══════════════════════════════════════════════════════════
# JINJA2 INTEGRATION
# ═══════════════════════════════════════════════════════════

def setup_jinja2_i18n(app_templates):
    """
    Add t() function to Jinja2 globals.
    Call in main.py: setup_jinja2_i18n(templates)
    
    Usage in templates:
        {{ t('common.save') }}
        {{ t('fee.due_msg', name='Rahul') }}
    """
    def t(key: str, **kwargs):
        # Try to get language from request context (set by middleware)
        return get_translation(key, **kwargs)

    app_templates.env.globals["t"] = t
    app_templates.env.globals["get_supported_languages"] = get_supported_languages
    app_templates.env.globals["i18n_default_lang"] = _default_lang


# ═══════════════════════════════════════════════════════════
# MIDDLEWARE — Set language per request
# ═══════════════════════════════════════════════════════════

class I18nMiddleware:
    """
    Middleware to detect user language and inject into request.
    Priority: 1) Cookie 2) User preference 3) Accept-Language header 4) Default
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from starlette.requests import Request
            request = Request(scope, receive, send)

            # Detect language
            lang = (
                request.cookies.get("lang") or
                request.query_params.get("lang") or
                _detect_from_header(request.headers.get("accept-language", "")) or
                _default_lang
            )

            # Validate
            valid_codes = [l["code"] for l in _supported_langs]
            if lang not in valid_codes:
                lang = _default_lang

            # Store in scope for templates
            scope["state"] = scope.get("state", {})
            scope["state"]["lang"] = lang

        await self.app(scope, receive, send)


def _detect_from_header(accept_lang: str) -> Optional[str]:
    """Parse Accept-Language header."""
    if not accept_lang:
        return None
    valid_codes = [l["code"] for l in _supported_langs]
    for part in accept_lang.split(","):
        code = part.strip().split(";")[0].split("-")[0].lower()
        if code in valid_codes:
            return code
    return None