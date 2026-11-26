from django.utils import translation

HELP_BASE_URL = "https://docs.ereuse.org/help/"

# The help site keeps English at its root and the other languages under a
# prefix (/help/es/, /help/ca/). Anything else falls back to English.
HELP_LANGUAGES = ("es", "ca")


def help_url(page="", language=None):
    """URL of a help page in the user's language.

    ``page`` is a path relative to the help site, optionally with an anchor
    (``"admin/#states"``). Anchors are the same in every language, so a view
    declares its page once. An empty ``page`` gives the help home.
    """
    language = (language or translation.get_language() or "en")
    language = language.split("-")[0].lower()
    prefix = f"{language}/" if language in HELP_LANGUAGES else ""
    return f"{HELP_BASE_URL}{prefix}{page.lstrip('/')}"
