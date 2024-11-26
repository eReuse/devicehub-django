from django import template
from django.utils.translation import get_language_info

register = template.Library()

@register.filter
def get_language_code(language_code, languages):
    for lang in languages:
        if lang['code'] == language_code:
            return lang['name_local'].lower()
    return language_code.lower()
